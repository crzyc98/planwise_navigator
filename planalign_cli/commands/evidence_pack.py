"""CLI adapter for deterministic, read-only scenario evidence packs."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import typer

from planalign_api.services.current_result import (
    CurrentResultIntegrityError,
    resolve_scenario_read_context,
)
from planalign_api.services.evidence_pack_service import apply_archive_trust
from planalign_evidence.models import PackWarning
from planalign_evidence.render import build_envelope
from planalign_evidence.service import (
    EvidenceConflictError,
    EvidenceNotFoundError,
    EvidenceTarget,
    UnsupportedEvidenceError,
    build_evidence_pack,
)


def generate_evidence_pack(
    scenario_path: Path,
    metric: str,
    base_year: int,
    target_year: int,
    output: Path | None = None,
    force: bool = False,
) -> None:
    """Render the same canonical pack as the API for a supplied scenario path."""
    try:
        target, warnings = _resolve_target(scenario_path)
        pack = build_evidence_pack(
            target, metric, base_year, target_year, warnings=warnings
        )
        if target.run_id != "legacy":
            workspaces_root = scenario_path.resolve().parents[2]
            pack, archive_warnings = apply_archive_trust(
                pack, workspaces_root, target.run_id
            )
            if archive_warnings:
                severity = {"critical": 0, "caution": 1, "info": 2}
                combined = tuple(
                    sorted(
                        (*pack.warnings, *archive_warnings),
                        key=lambda item: (severity[item.severity], item.code),
                    )
                )
                pack = pack.model_copy(update={"warnings": combined})
        envelope = build_envelope(pack)
        if output is None:
            typer.echo(envelope.text_export, nl=False)
            return
        _write_output(output, envelope.text_export, target, force)
        typer.echo(str(output), err=True)
    except (ValueError, UnsupportedEvidenceError) as exc:
        typer.echo(f"Unsupported evidence request: {exc}", err=True)
        raise typer.Exit(2) from exc
    except EvidenceNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(3) from exc
    except (EvidenceConflictError, CurrentResultIntegrityError) as exc:
        typer.echo(f"Result integrity conflict: {exc}", err=True)
        raise typer.Exit(4) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Evidence pack generation failed: {exc}", err=True)
        raise typer.Exit(1) from exc


def _resolve_target(
    scenario_path: Path,
) -> tuple[EvidenceTarget, tuple[PackWarning, ...]]:
    if scenario_path.is_symlink() or not scenario_path.is_dir():
        raise EvidenceNotFoundError(f"Scenario path not found: {scenario_path}")
    resolved_path = scenario_path.resolve()
    context = resolve_scenario_read_context(resolved_path)
    warnings: list[PackWarning] = []
    if context.database_path is not None and context.result_run_id is not None:
        database_path = context.database_path
        run_id = str(context.result_run_id)
        result_store = database_path.relative_to(resolved_path).as_posix()
        run_dir = database_path.parent
    else:
        database_path = resolved_path / "simulation.duckdb"
        if not database_path.is_file():
            raise EvidenceNotFoundError(
                f"No managed or legacy result exists at {scenario_path}"
            )
        run_id = "legacy"
        result_store = "simulation.duckdb"
        run_dir = None
        warnings.append(
            PackWarning(
                code="legacy_result",
                severity="caution",
                message="This legacy result has no immutable managed-run binding; provenance may be incomplete.",
            )
        )
    metadata = _scenario_metadata(resolved_path)
    if context.warning == "run_in_progress":
        warnings.append(
            PackWarning(
                code="run_in_progress",
                severity="info",
                message=f"This pack describes completed run {run_id}, not the active attempt {context.active_run_id}.",
            )
        )
    return (
        EvidenceTarget(
            database_path=database_path,
            result_store=result_store,
            scenario_id=str(metadata.get("id") or resolved_path.name),
            scenario_name=metadata.get("name"),
            workspace_id=metadata.get("workspace_id"),
            run_id=run_id,
            active_run_id=str(context.active_run_id) if context.active_run_id else None,
            run_dir=run_dir,
        ),
        tuple(warnings),
    )


def _scenario_metadata(scenario_path: Path) -> dict:
    path = scenario_path / "scenario.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurrentResultIntegrityError("invalid scenario metadata") from exc
    if not isinstance(data, dict):
        raise CurrentResultIntegrityError("invalid scenario metadata")
    return data


def _write_output(output: Path, text: str, target: EvidenceTarget, force: bool) -> None:
    destination = output.resolve()
    if target.run_dir is not None and destination.is_relative_to(
        target.run_dir.resolve()
    ):
        raise ValueError("output must not be written inside the immutable run archive")
    if destination.exists() and not force:
        raise ValueError("output already exists; pass --force to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


__all__ = ["generate_evidence_pack"]
