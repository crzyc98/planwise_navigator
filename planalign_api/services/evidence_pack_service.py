"""Scenario-selected result adapter for the shared evidence-pack core."""

from __future__ import annotations

from planalign_evidence.models import EvidencePackEnvelope, PackWarning
from planalign_evidence.render import build_envelope
from planalign_evidence.service import (
    EvidenceNotFoundError,
    EvidenceTarget,
    build_evidence_pack,
)

from ..config import get_settings
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import create_api_database_path_resolver
from .provenance.locator import (
    ArchiveUnstableError,
    IdentityConflictError,
    RunNotFoundError,
)
from .provenance.report import build_provenance_report
from .run_trust import add_current_config_drift, read_run_trust


def get_scenario_evidence_pack(
    workspace_id: str,
    scenario_id: str,
    metric: str,
    base_year: int,
    target_year: int,
) -> EvidencePackEnvelope:
    """Resolve one selected scenario result once and build both representations."""
    storage = WorkspaceStorage(get_settings().workspaces_root)
    scenario = storage.get_scenario(workspace_id, scenario_id)
    if scenario is None:
        raise EvidenceNotFoundError(
            f"Scenario {scenario_id} was not found in workspace {workspace_id}"
        )
    resolved = create_api_database_path_resolver(storage).resolve(
        workspace_id, scenario_id, verify_database=False
    )
    if not resolved.exists or resolved.source not in {"run", "scenario"}:
        raise EvidenceNotFoundError(
            f"No selected completed result exists for scenario {scenario_id}"
        )
    scenario_path = storage._scenario_path(workspace_id, scenario_id)
    assert resolved.path is not None
    result_store = resolved.path.relative_to(scenario_path).as_posix()
    run_id = resolved.run_id or "legacy"
    warnings: list[PackWarning] = []
    if resolved.source == "scenario":
        warnings.append(
            PackWarning(
                code="legacy_result",
                severity="caution",
                message="This legacy result has no immutable managed-run binding; provenance may be incomplete.",
            )
        )
    if resolved.run_warning == "run_in_progress":
        warnings.append(
            PackWarning(
                code="run_in_progress",
                severity="info",
                message=(
                    f"This pack describes completed run {run_id}, not the active attempt {resolved.active_run_id}."
                ),
            )
        )
    target = EvidenceTarget(
        database_path=resolved.path,
        result_store=result_store,
        workspace_id=workspace_id,
        scenario_id=scenario_id,
        scenario_name=scenario.name,
        run_id=run_id,
        active_run_id=resolved.active_run_id,
        run_dir=resolved.path.parent if resolved.source == "run" else None,
    )
    trust = add_current_config_drift(
        read_run_trust(resolved.path, run_id),
        storage.get_merged_config(workspace_id, scenario_id),
    )
    for reason in trust.reasons:
        warnings.append(
            PackWarning(
                code=reason,
                severity="caution",
                message={
                    "mixed_generation": "The result contains rows produced across different configuration or seed generations.",
                    "current_config_mismatch": "The current scenario configuration differs from the selected result.",
                    "current_seed_mismatch": "The current scenario seed differs from the selected result.",
                }[reason],
            )
        )
    pack = build_evidence_pack(
        target,
        metric,
        base_year,
        target_year,
        warnings=warnings,
    )
    if resolved.source == "run":
        pack, archive_warnings = apply_archive_trust(
            pack, get_settings().workspaces_root, run_id
        )
        warnings.extend(archive_warnings)
    if warnings:
        existing = {warning.code for warning in pack.warnings}
        combined = (
            tuple(warning for warning in warnings if warning.code not in existing)
            + pack.warnings
        )
        severity = {"critical": 0, "caution": 1, "info": 2}
        pack = pack.model_copy(
            update={
                "warnings": tuple(
                    sorted(
                        combined, key=lambda item: (severity[item.severity], item.code)
                    )
                )
            }
        )
    return build_envelope(pack)


def apply_archive_trust(pack, workspaces_root, run_id):
    """Apply the existing archived-provenance verification to a bound pack."""
    warnings: list[PackWarning] = []
    try:
        report = build_provenance_report(workspaces_root, run_id)
    except RunNotFoundError:
        warnings.append(
            PackWarning(
                code="incomplete_provenance",
                severity="caution",
                message="Archived provenance evidence is unavailable for this result.",
            )
        )
        return pack, tuple(warnings)
    except (ArchiveUnstableError, IdentityConflictError) as exc:
        from planalign_evidence.service import EvidenceConflictError

        raise EvidenceConflictError(str(exc)) from exc
    provenance = pack.provenance.model_copy(
        update={"verification_disposition": report.verification_disposition}
    )
    if any(item.code == "integrity_mismatch" for item in report.missing_evidence):
        warnings.append(
            PackWarning(
                code="integrity_mismatch",
                severity="critical",
                message="Archived provenance contains an integrity mismatch.",
            )
        )
    if report.verification_disposition != "fully_verified":
        warnings.append(
            PackWarning(
                code="incomplete_provenance",
                severity="caution",
                message="Archived provenance is incomplete or unverifiable.",
            )
        )
    return pack.model_copy(update={"provenance": provenance}), tuple(warnings)


__all__ = ["apply_archive_trust", "get_scenario_evidence_pack"]
