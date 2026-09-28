"""Scenario-selected result adapter for the shared evidence-pack core."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planalign_evidence.cross_models import (
    ConfigDifference,
    CrossScenarioEvidencePackEnvelope,
)
from planalign_evidence.cross_render import build_cross_envelope
from planalign_evidence.cross_service import build_cross_scenario_evidence_pack
from planalign_evidence.models import (
    EvidencePack,
    EvidencePackEnvelope,
    PackProvenance,
    PackWarning,
)
from planalign_evidence.render import build_envelope
from planalign_evidence.service import (
    EvidenceConflictError,
    EvidenceNotFoundError,
    EvidenceTarget,
    UnsupportedEvidenceError,
    build_evidence_pack,
)

from ..config import get_settings
from ..models.comparison import ConfigDelta
from ..storage.workspace_storage import WorkspaceStorage
from .config_diff_service import ConfigDiffService
from .database_path_resolver import create_api_database_path_resolver
from .provenance.locator import (
    ArchiveUnstableError,
    IdentityConflictError,
    RunNotFoundError,
)
from .provenance.report import build_provenance_report
from .run_trust import add_current_config_drift, read_run_trust

_SEVERITY_ORDER = {"critical": 0, "caution": 1, "info": 2}
_DRIFT_MESSAGES = {
    "mixed_generation": "The result contains rows produced across different configuration or seed generations.",
    "current_config_mismatch": "The current scenario configuration differs from the selected result.",
    "current_seed_mismatch": "The current scenario seed differs from the selected result.",
}
_CENSUS_PATH = "setup.census_parquet_path"


@dataclass(frozen=True)
class _ResolvedSide:
    """One scenario's selected completed result plus its trust warnings."""

    target: EvidenceTarget
    warnings: tuple[PackWarning, ...]
    archived: bool


def _resolve_side(
    storage: WorkspaceStorage, workspace_id: str, scenario_id: str
) -> _ResolvedSide:
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
    trust = add_current_config_drift(
        read_run_trust(resolved.path, run_id),
        storage.get_merged_config(workspace_id, scenario_id),
    )
    warnings.extend(
        PackWarning(code=reason, severity="caution", message=_DRIFT_MESSAGES[reason])
        for reason in trust.reasons
    )
    target = EvidenceTarget(
        database_path=resolved.path,
        result_store=resolved.path.relative_to(scenario_path).as_posix(),
        workspace_id=workspace_id,
        scenario_id=scenario_id,
        scenario_name=scenario.name,
        run_id=run_id,
        active_run_id=resolved.active_run_id,
        run_dir=resolved.path.parent if resolved.source == "run" else None,
    )
    return _ResolvedSide(target, tuple(warnings), resolved.source == "run")


def _merge_warnings(
    extra: tuple[PackWarning, ...],
    existing: tuple[PackWarning, ...],
    *,
    per_message: bool = False,
) -> tuple[PackWarning, ...]:
    """Prepend unseen warnings; cross packs repeat codes per side, so key on message."""

    def key(warning: PackWarning) -> tuple[str, str]:
        return (warning.code, warning.message if per_message else "")

    seen = {key(warning) for warning in existing}
    combined = tuple(w for w in extra if key(w) not in seen) + existing
    return tuple(
        sorted(combined, key=lambda item: (_SEVERITY_ORDER[item.severity], item.code))
    )


def get_scenario_evidence_pack(
    workspace_id: str,
    scenario_id: str,
    metric: str,
    base_year: int,
    target_year: int,
) -> EvidencePackEnvelope:
    """Resolve one selected scenario result once and build both representations."""
    storage = WorkspaceStorage(get_settings().workspaces_root)
    side = _resolve_side(storage, workspace_id, scenario_id)
    warnings = list(side.warnings)
    pack = build_evidence_pack(
        side.target, metric, base_year, target_year, warnings=warnings
    )
    if side.archived:
        pack, archive_warnings = apply_archive_trust(
            pack, get_settings().workspaces_root, side.target.run_id
        )
        warnings.extend(archive_warnings)
    if warnings:
        pack = pack.model_copy(
            update={"warnings": _merge_warnings(tuple(warnings), pack.warnings)}
        )
    return build_envelope(pack)


def _config_value(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _config_deltas(
    storage: WorkspaceStorage, workspace_id: str, scenario_a: str, scenario_b: str
) -> list[ConfigDelta]:
    """Diff the configs archived with each selected run (the ones that produced it)."""
    try:
        diff = ConfigDiffService(storage).compare(
            workspace_id, scenario_a, scenario_b, {}
        )
    except ValueError as exc:
        raise UnsupportedEvidenceError(
            f"{exc}, so the configuration differences behind this comparison cannot be cited"
        ) from exc
    return diff.differences


def _nested(value: Any, keys: list[str]) -> Any:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _census_differs(deltas: list[ConfigDelta]) -> bool:
    """True if the census path differs, whether diffed as a leaf or inside a section."""
    for delta in deltas:
        if delta.path != _CENSUS_PATH and not _CENSUS_PATH.startswith(f"{delta.path}."):
            continue
        rest = _CENSUS_PATH[len(delta.path) :].lstrip(".").split(".")
        rest = [key for key in rest if key]
        if _nested(delta.a, rest) != _nested(delta.b, rest):
            return True
    return False


def _census_warnings(deltas: list[ConfigDelta]) -> tuple[PackWarning, ...]:
    if not _census_differs(deltas):
        return ()
    return (
        PackWarning(
            code="census_mismatch",
            severity="caution",
            message="The scenarios read different census inputs, so part of the difference "
            "reflects the starting population rather than configuration.",
        ),
    )


def _labelled(label: str, warnings: tuple[PackWarning, ...]) -> tuple[PackWarning, ...]:
    return tuple(
        warning.model_copy(update={"message": f"{label}: {warning.message}"})
        for warning in warnings
    )


def _side_archive_trust(
    side: _ResolvedSide, provenance: PackProvenance, label: str
) -> tuple[PackProvenance, tuple[PackWarning, ...]]:
    if not side.archived:
        return provenance, ()
    verified, warnings = archive_trust_for(
        provenance, get_settings().workspaces_root, side.target.run_id
    )
    return verified, _labelled(label, warnings)


def get_cross_scenario_evidence_pack(
    workspace_id: str,
    scenario_a: str,
    scenario_b: str,
    metric: str,
    year: int,
) -> CrossScenarioEvidencePackEnvelope:
    """Compare two scenarios' selected results at one year, citing their config diff."""
    if scenario_a == scenario_b:
        raise UnsupportedEvidenceError("Select two distinct scenarios")
    storage = WorkspaceStorage(get_settings().workspaces_root)
    side_a = _resolve_side(storage, workspace_id, scenario_a)
    side_b = _resolve_side(storage, workspace_id, scenario_b)
    deltas = _config_deltas(storage, workspace_id, scenario_a, scenario_b)
    pack = build_cross_scenario_evidence_pack(
        side_a.target,
        side_b.target,
        metric,
        year,
        config_differences=tuple(
            ConfigDifference(
                path=delta.path,
                value_a=_config_value(delta.a),
                value_b=_config_value(delta.b),
                status=delta.status,
            )
            for delta in deltas
        ),
        warnings=_labelled("Scenario A", side_a.warnings)
        + _labelled("Scenario B", side_b.warnings)
        + _census_warnings(deltas),
    )
    provenance_a, archive_a = _side_archive_trust(
        side_a, pack.provenance_a, "Scenario A"
    )
    provenance_b, archive_b = _side_archive_trust(
        side_b, pack.provenance_b, "Scenario B"
    )
    pack = pack.model_copy(
        update={
            "provenance_a": provenance_a,
            "provenance_b": provenance_b,
            "warnings": _merge_warnings(
                archive_a + archive_b, pack.warnings, per_message=True
            ),
        }
    )
    return build_cross_envelope(pack)


def archive_trust_for(
    provenance: PackProvenance, workspaces_root: Path, run_id: str
) -> tuple[PackProvenance, tuple[PackWarning, ...]]:
    """Verify one run's archived provenance and return the updated disposition."""
    try:
        report = build_provenance_report(workspaces_root, run_id)
    except RunNotFoundError:
        return provenance, (
            PackWarning(
                code="incomplete_provenance",
                severity="caution",
                message="Archived provenance evidence is unavailable for this result.",
            ),
        )
    except (ArchiveUnstableError, IdentityConflictError) as exc:
        raise EvidenceConflictError(str(exc)) from exc
    warnings: list[PackWarning] = []
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
    verified = provenance.model_copy(
        update={"verification_disposition": report.verification_disposition}
    )
    return verified, tuple(warnings)


def apply_archive_trust(
    pack: EvidencePack, workspaces_root: Path, run_id: str
) -> tuple[EvidencePack, tuple[PackWarning, ...]]:
    """Apply the existing archived-provenance verification to a bound pack."""
    provenance, warnings = archive_trust_for(pack.provenance, workspaces_root, run_id)
    return pack.model_copy(update={"provenance": provenance}), warnings


__all__ = [
    "apply_archive_trust",
    "archive_trust_for",
    "get_cross_scenario_evidence_pack",
    "get_scenario_evidence_pack",
]
