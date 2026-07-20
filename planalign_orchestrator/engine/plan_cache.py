"""Manifest, dbt-native selection, and immutable compiled bundles (#470).

Selector semantics belong to dbt: selection resolves through in-process
``dbt ls`` against a run-cached parsed manifest (research R5) — the
prototype's hand matcher is gone. Compiled SQL is produced by in-process
``dbt compile`` into a unique staging target and atomically published as an
immutable, hash-verified bundle keyed by the full render-context digest
(research R3/R4, contracts/compiled-bundle.md). dbt never targets a
published bundle; execution never reads a mutable target.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .context import (
    StaticProjectContext,
    canonical_digest,
    file_digest,
)
from .workspace import DBT_DIR, RunArtifactWorkspace

logger = logging.getLogger(__name__)


class BundleIntegrityError(RuntimeError):
    """Published bundle content does not match its recorded digests."""


class SelectorResolutionError(RuntimeError):
    """dbt could not resolve the selection (invalid selector syntax/method)."""


@dataclass(frozen=True)
class Bundle:
    root: Path
    index: Dict[str, Dict[str, str]]  # unique_id -> {sql_path, sql_digest}
    context_digest: str


def publish_bundle(
    *,
    workspace: RunArtifactWorkspace,
    staging_dir: Path,
    context_digest: str,
    nodes: Sequence[Dict[str, str]],
) -> Bundle:
    """Contract publication protocol: validate, hash, write bundle.json last,
    atomic rename into ``bundles/<context_digest>/``."""
    index: Dict[str, Dict[str, str]] = {}
    for node in nodes:
        sql_path = staging_dir / node["sql_path"]
        if not sql_path.exists():
            raise BundleIntegrityError(
                f"compiled SQL missing for {node['unique_id']}: {sql_path}"
            )
        index[node["unique_id"]] = {
            "sql_path": node["sql_path"],
            "sql_digest": file_digest(sql_path),
        }
    manifest_file = staging_dir / "manifest.json"
    bundle_json = {
        "schema_version": 1,
        "context_digest": context_digest,
        "manifest_digest": file_digest(manifest_file)
        if manifest_file.exists()
        else None,
        "nodes": [{"unique_id": uid, **meta} for uid, meta in sorted(index.items())],
    }
    bundle_json["bundle_digest"] = canonical_digest(bundle_json)
    (staging_dir / "bundle.json").write_text(json.dumps(bundle_json, indent=2))

    destination = workspace.bundle_root / context_digest
    if destination.exists():
        existing = _load_bundle(destination)
        _verify_bundle(existing)
        shutil.rmtree(staging_dir, ignore_errors=True)
        return existing
    staging_dir.rename(destination)
    return Bundle(root=destination, index=index, context_digest=context_digest)


def _load_bundle(root: Path) -> Bundle:
    payload = json.loads((root / "bundle.json").read_text())
    index = {
        n["unique_id"]: {"sql_path": n["sql_path"], "sql_digest": n["sql_digest"]}
        for n in payload["nodes"]
    }
    return Bundle(root=root, index=index, context_digest=payload["context_digest"])


def _verify_bundle(bundle: Bundle) -> None:
    for uid, meta in bundle.index.items():
        path = bundle.root / meta["sql_path"]
        if not path.exists() or file_digest(path) != meta["sql_digest"]:
            raise BundleIntegrityError(f"bundle content mismatch for {uid}: {path}")


def load_bundle_sql(bundle: Bundle, unique_id: str) -> str:
    meta = bundle.index.get(unique_id)
    if meta is None:
        raise BundleIntegrityError(f"{unique_id} not present in bundle {bundle.root}")
    path = bundle.root / meta["sql_path"]
    if not path.exists():
        raise BundleIntegrityError(f"bundle SQL missing: {path}")
    content = path.read_text()
    if file_digest(path) != meta["sql_digest"]:
        raise BundleIntegrityError(f"bundle SQL digest mismatch: {path}")
    return content


# --------------------------------------------------------------------- #
# dbt-backed manifest / selection / compile                             #
# --------------------------------------------------------------------- #


class PlanCache:
    """Run-scoped dbt artifacts: one parse per vars-fingerprint, dbt-owned
    selection, per-context compiled bundles."""

    def __init__(
        self,
        *,
        workspace: RunArtifactWorkspace,
        db_manager: Optional[Any] = None,
    ) -> None:
        self.workspace = workspace
        self.db_manager = db_manager
        self.static_context = StaticProjectContext.capture(
            DBT_DIR, workspace.profiles_dir / "profiles.yml"
        )
        self._manifests: Dict[str, Any] = {}  # vars_fp -> dbt Manifest
        self._selection_cache: Dict[Tuple[str, str], Tuple[str, ...]] = {}
        self._compiled_staging: Dict[str, Path] = {}  # vars_fp -> staging dir
        self._compile_states: Dict[
            str, Dict[str, str]
        ] = {}  # vars_fp -> uid -> state digest

    # -- dbt invocation plumbing --------------------------------------- #

    def _base_args(
        self, target_dir: Path, log_dir: Path, *, threads: bool = False
    ) -> List[str]:
        args = [
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(self.workspace.profiles_dir),
            "--target-path",
            str(target_dir),
            "--log-path",
            str(log_dir),
        ]
        if threads:  # not every dbt command accepts --threads (e.g. ls)
            args += ["--threads", "1"]
        return args

    def _invoke(self, args: List[str], manifest: Optional[Any] = None):
        from dbt.cli.main import dbtRunner

        if self.db_manager is not None:
            try:
                self.db_manager.close_all()
            except Exception as exc:  # non-fatal, mirrors runner discipline
                logger.warning("close_all before dbt invoke: %s", exc)
        runner = dbtRunner(manifest=manifest) if manifest is not None else dbtRunner()
        return runner.invoke(args)

    @staticmethod
    def vars_fingerprint(dbt_vars: Dict[str, Any]) -> str:
        return canonical_digest(dbt_vars)

    # -- manifest ------------------------------------------------------- #

    def manifest_for(self, dbt_vars: Dict[str, Any]) -> Any:
        fp = self.vars_fingerprint(dbt_vars)
        if fp in self._manifests:
            return self._manifests[fp]
        staging = self.workspace.new_staging_dir()
        log_dir = self.workspace.new_log_dir(0)
        args = ["parse", *self._base_args(staging, log_dir)]
        if dbt_vars:
            args += ["--vars", json.dumps(dbt_vars)]
        result = self._invoke(args)
        if not result.success or result.result is None:
            raise SelectorResolutionError(
                f"dbt parse failed: {getattr(result, 'exception', None)}"
            )
        self._manifests[fp] = result.result
        return result.result

    # -- selection (dbt-owned semantics) -------------------------------- #

    def resolve_selection(
        self,
        select: Sequence[str],
        exclude: Sequence[str],
        dbt_vars: Dict[str, Any],
    ) -> Tuple[str, ...]:
        """Resolve to dbt-ordered model unique_ids; raises on invalid selectors."""
        fp = self.vars_fingerprint(dbt_vars)
        key = (fp, canonical_digest({"s": list(select), "x": list(exclude)}))
        if key in self._selection_cache:
            return self._selection_cache[key]
        manifest = self.manifest_for(dbt_vars)
        staging = self.workspace.new_staging_dir()
        log_dir = self.workspace.new_log_dir(0)
        args = ["ls", *self._base_args(staging, log_dir)]
        args += [
            "--resource-type",
            "model",
            "--output",
            "json",
            "--output-keys",
            "unique_id",
        ]
        if select:
            args += ["--select", *select]
        if exclude:
            args += ["--exclude", *exclude]
        if dbt_vars:
            args += ["--vars", json.dumps(dbt_vars)]
        result = self._invoke(args, manifest=manifest)
        if not result.success:
            raise SelectorResolutionError(
                f"dbt ls failed for select={list(select)}: {getattr(result, 'exception', None)}"
            )
        raw = result.result or []
        unique_ids = []
        for line in raw:
            try:
                unique_ids.append(json.loads(line)["unique_id"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        ordered = self._topological(manifest, set(unique_ids))
        self._selection_cache[key] = ordered
        shutil.rmtree(staging, ignore_errors=True)
        return ordered

    @staticmethod
    def _topological(manifest: Any, selected: set) -> Tuple[str, ...]:
        nodes = manifest.nodes
        ordered: List[str] = []
        visited: set = set()

        def visit(uid: str) -> None:
            if uid in visited or uid not in selected:
                return
            visited.add(uid)
            node = nodes.get(uid)
            for dep in getattr(getattr(node, "depends_on", None), "nodes", []) or []:
                visit(dep)
            ordered.append(uid)

        for uid in sorted(selected):
            visit(uid)
        return tuple(ordered)

    # -- compile + bundle ------------------------------------------------ #

    def compiled_staging_for(self, dbt_vars: Dict[str, Any]) -> Path:
        """One full-project compile per vars-fingerprint (research R3)."""
        fp = self.vars_fingerprint(dbt_vars)
        if fp in self._compiled_staging:
            return self._compiled_staging[fp]
        manifest = self.manifest_for(dbt_vars)
        staging = self.workspace.new_staging_dir()
        log_dir = self.workspace.new_log_dir(0)
        args = ["compile", *self._base_args(staging, log_dir, threads=True)]
        if dbt_vars:
            args += ["--vars", json.dumps(dbt_vars)]
        result = self._invoke(args, manifest=manifest)
        if not result.success:
            raise SelectorResolutionError(
                f"dbt compile failed: {getattr(result, 'exception', None)}"
            )
        self._compiled_staging[fp] = staging
        self._compile_states[fp] = self._snapshot_all_states(manifest)
        return staging

    def _snapshot_all_states(self, manifest: Any) -> Dict[str, str]:
        """Relation-state digest for every model at compile time (research R4)."""
        from .context import inspect_relations

        uids, relations = [], []
        for uid, node in manifest.nodes.items():
            if getattr(node, "resource_type", None) and str(node.resource_type) not in (
                "model",
                "NodeType.Model",
            ):
                continue
            uids.append(uid)
            relations.append(
                (node.database or "main", node.schema, node.alias or node.name)
            )
        states = inspect_relations(self.workspace.database_path, relations)
        # Existence/type only: the render idioms this guard protects
        # (is_incremental, load_relation/get_relation guards) branch on
        # relation existence, never on column details — and column-level
        # digests proved unstable across connections (spurious recompiles).
        return {uid: state.relation_type for uid, state in zip(uids, states)}

    def _render_sensitive_uids(self, manifest: Any) -> set:
        """Models whose RENDERED SQL depends on relation state beyond their
        own: users of adapter.get_relation / load_relation, plus their
        direct dependencies (the relations they typically probe)."""
        import re as _re

        sensitive: set = set()
        for uid, node in manifest.nodes.items():
            raw = getattr(node, "raw_code", "") or ""
            if _re.search(r"adapter\.get_relation|load_relation", raw):
                sensitive.add(uid)
                sensitive.update(
                    getattr(getattr(node, "depends_on", None), "nodes", []) or []
                )
        return sensitive

    def require_compile_state(
        self, dbt_vars: Dict[str, Any], selected_uids: Sequence[str] = ()
    ) -> None:
        """Recompile when render-relevant relation state changed (R4).

        Render-relevant = the selected nodes' OWN relations (their
        ``is_incremental()`` truth) plus the render-sensitive set (models
        using ``adapter.get_relation``/``load_relation`` and their
        dependencies). Changes to other relations cannot alter rendered SQL
        and must not trigger the expensive full recompile.
        """
        fp = self.vars_fingerprint(dbt_vars)
        if fp not in self._compiled_staging:
            self.compiled_staging_for(dbt_vars)
            return
        manifest = self._manifests[fp]
        watch = set(selected_uids) | self._render_sensitive_uids(manifest)
        current = self._snapshot_all_states(manifest)
        recorded = self._compile_states.get(fp, {})
        for uid in watch:
            if uid in current and recorded.get(uid) != current[uid]:
                logger.info(
                    "[compiled] relation-state epoch advanced (%s); recompiling", uid
                )
                self._compiled_staging.pop(fp, None)
                self._compile_states.pop(fp, None)
                self.compiled_staging_for(dbt_vars)
                return

    def invalidate_compiled(self, dbt_vars: Dict[str, Any]) -> None:
        """Relation-state changed for selected nodes — force a fresh compile."""
        fp = self.vars_fingerprint(dbt_vars)
        self._compiled_staging.pop(fp, None)
        self._compile_states.pop(fp, None)

    def node(self, dbt_vars: Dict[str, Any], unique_id: str) -> Any:
        return self.manifest_for(dbt_vars).nodes[unique_id]

    def ensure_bundle(
        self,
        *,
        context_digest: str,
        dbt_vars: Dict[str, Any],
        unique_ids: Sequence[str],
    ) -> Bundle:
        """Assemble/publish the bundle for one invocation context."""
        destination = self.workspace.bundle_root / context_digest
        if destination.exists():
            bundle = _load_bundle(destination)
            _verify_bundle(bundle)
            return bundle
        compile_root = self.compiled_staging_for(dbt_vars)
        manifest = self.manifest_for(dbt_vars)
        assembly = self.workspace.new_staging_dir()
        nodes_meta: List[Dict[str, str]] = []
        for uid in unique_ids:
            node = manifest.nodes[uid]
            if getattr(node.config, "materialized", None) == "ephemeral":
                continue
            rel = Path("compiled") / node.package_name / node.original_file_path
            source = compile_root / rel
            if not source.exists():
                raise BundleIntegrityError(f"compiled SQL absent for {uid}: {source}")
            # dbt injects ephemeral-dependency CTEs into the *run* artifact,
            # not the compiled file — make bundle SQL self-contained using
            # dbt's own injection helper so hashes cover executable SQL.
            sql = self._inline_ephemeral_ctes(
                manifest, uid, source.read_text(), compile_root
            )
            target = assembly / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sql)
            nodes_meta.append({"unique_id": uid, "sql_path": str(rel)})
        manifest_json = compile_root / "manifest.json"
        if manifest_json.exists():
            shutil.copy2(manifest_json, assembly / "manifest.json")
        return publish_bundle(
            workspace=self.workspace,
            staging_dir=assembly,
            context_digest=context_digest,
            nodes=nodes_meta,
        )

    def _inline_ephemeral_ctes(
        self, manifest: Any, uid: str, sql: str, compile_root: Path
    ) -> str:
        """Prepend ephemeral ancestors as __dbt__cte__ CTEs (dbt's own merger)."""
        from dbt.compilation import InjectedCTE, inject_ctes_into_sql

        ordered: List[str] = []
        seen: set = set()

        def collect(node_uid: str) -> None:
            node = manifest.nodes.get(node_uid)
            if node is None:
                return
            for dep in getattr(getattr(node, "depends_on", None), "nodes", []) or []:
                dep_node = manifest.nodes.get(dep)
                if dep_node is None or dep in seen:
                    continue
                if getattr(dep_node.config, "materialized", None) == "ephemeral":
                    seen.add(dep)
                    collect(dep)
                    ordered.append(dep)

        collect(uid)
        if not ordered:
            return sql
        import re

        # dbt's compile output is inconsistent about CTE injection: some
        # compiled files already define __dbt__cte__X, some only reference
        # it. Inject only the missing definitions (idempotent).
        ordered = [
            dep
            for dep in ordered
            if not re.search(
                rf"__dbt__cte__{re.escape(manifest.nodes[dep].name)}\s+as\s*\(",
                sql,
                re.IGNORECASE,
            )
        ]
        if not ordered:
            return sql
        ctes: List[Any] = []
        for dep in ordered:
            dep_node = manifest.nodes[dep]
            dep_path = (
                compile_root
                / "compiled"
                / dep_node.package_name
                / dep_node.original_file_path
            )
            if not dep_path.exists():
                raise BundleIntegrityError(
                    f"compiled SQL absent for ephemeral dependency {dep}: {dep_path}"
                )
            ctes.append(
                InjectedCTE(
                    id=dep,
                    sql=f" __dbt__cte__{dep_node.name} as (\n{dep_path.read_text()}\n)",
                )
            )
        return inject_ctes_into_sql(sql, ctes)
