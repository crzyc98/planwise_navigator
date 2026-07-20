"""Canonical render-context identity for compiled bundles (#470, research R4).

``is_incremental()`` and friends make compiled SQL a function of far more
than the year: project content, versions, profile target, vars, command
semantics, selected nodes, relation state, and dbt's volatile render
identity. Bundles are keyed by the digest of the complete canonical
structure; reuse requires byte-for-byte identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import duckdb


def canonical_digest(payload: Any) -> str:
    """SHA-256 of a canonical JSON encoding (sorted keys, stable separators)."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path, patterns: Sequence[str]) -> str:
    """Stable digest over matching files' relative paths + content hashes."""
    entries: List[Tuple[str, str]] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                entries.append((str(path.relative_to(root)), file_digest(path)))
    return canonical_digest(entries)


@dataclass(frozen=True)
class StaticProjectContext:
    project_digest: str
    dbt_version: str
    adapter_version: str
    adapter_type: str
    profile_digest: str
    manifest_digest: Optional[str] = None

    @classmethod
    def capture(cls, dbt_dir: Path, profiles_yml: Path) -> "StaticProjectContext":
        from importlib import metadata

        project_digest = tree_digest(
            dbt_dir,
            (
                "dbt_project.yml",
                "packages.yml",
                "package-lock.yml",
                "selectors.yml",
                "models/**/*.sql",
                "models/**/*.yml",
                "macros/**/*.sql",
                "seeds/**/*.csv",
            ),
        )
        return cls(
            project_digest=project_digest,
            dbt_version=metadata.version("dbt-core"),
            adapter_version=metadata.version("dbt-duckdb"),
            adapter_type="duckdb",
            profile_digest=file_digest(profiles_yml),
        )

    def with_manifest(self, manifest_path: Path) -> "StaticProjectContext":
        return StaticProjectContext(
            **{**asdict(self), "manifest_digest": file_digest(manifest_path)}
        )


@dataclass(frozen=True)
class RelationState:
    database: str
    schema: str
    identifier: str
    relation_type: str  # missing | table | view
    columns: Tuple[Tuple[str, str, str], ...]  # (name, type, is_nullable)

    @property
    def state_digest(self) -> str:
        return canonical_digest(asdict(self))


def inspect_relations(
    database_path: Path, relations: Sequence[Tuple[str, str, str]]
) -> List[RelationState]:
    """Read-only snapshot of (database, schema, identifier) relation states."""
    states: List[RelationState] = []
    if not Path(database_path).exists():
        return [
            RelationState(db, schema, ident, "missing", ())
            for db, schema, ident in relations
        ]
    with duckdb.connect(str(database_path), read_only=True) as conn:
        for db, schema, ident in relations:
            row = conn.execute(
                "SELECT table_type FROM information_schema.tables "
                "WHERE table_schema = ? AND table_name = ?",
                [schema, ident],
            ).fetchone()
            if row is None:
                states.append(RelationState(db, schema, ident, "missing", ()))
                continue
            relation_type = "view" if row[0] == "VIEW" else "table"
            columns = tuple(
                (r[0], r[1], r[2])
                for r in conn.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ? "
                    "ORDER BY ordinal_position",
                    [schema, ident],
                ).fetchall()
            )
            states.append(RelationState(db, schema, ident, relation_type, columns))
    return states


@dataclass(frozen=True)
class RenderContext:
    static_project: StaticProjectContext
    database_path_digest: str
    profile_target: str
    schema: str
    command_semantics: Dict[str, Any]
    vars_digest: str
    selected_unique_ids: Tuple[str, ...]
    relation_state_digest: str
    render_identity: str

    @property
    def context_digest(self) -> str:
        payload = {
            "static": asdict(self.static_project),
            "database_path_digest": self.database_path_digest,
            "profile_target": self.profile_target,
            "schema": self.schema,
            "command": self.command_semantics,
            "vars_digest": self.vars_digest,
            "selected": list(self.selected_unique_ids),
            "relation_state": self.relation_state_digest,
            "render_identity": self.render_identity,
        }
        return canonical_digest(payload)


def vars_digest(dbt_vars: Dict[str, Any]) -> str:
    return canonical_digest(dbt_vars)


def database_path_digest(database_path: Path) -> str:
    return canonical_digest(str(Path(database_path).resolve()))


def relation_state_digest(states: Sequence[RelationState]) -> str:
    return canonical_digest([s.state_digest for s in states])
