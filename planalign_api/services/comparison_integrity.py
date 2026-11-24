"""Read-only like-for-like check for compared scenarios (#1179).

A comparison shows the difference between two results as the cost of a plan
change. That only holds when the results differ in plan design alone. For each
compared scenario this service checks the anchor's and the scenario's selected
results: census (provenance SHA-256), random seed, simulated years, engine
version and build, dbt seed tables (provenance SHA-256 per file), and the
archived run configs grouped by what each setting controls.
The same comparison, run between a scenario's previous run and its selected
result, says what changed since the previous run (#1186).

A false "like-for-like" is the worst outcome, so the verdict is
``like_for_like`` only when every check ran and none found a difference.
A check that could not run makes the verdict ``unknown``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Optional, cast, get_args

import yaml
from pydantic import ValidationError

from planalign_orchestrator.config.workforce import AcquisitionSettings

from ..models.comparison import (
    ComparisonIntegrityResponse,
    ComparisonVerdict,
    ConfigDelta,
    ConfigGroup,
    IntegrityCheck,
    IntegrityReason,
    IntegrityReasonCode,
    RunChange,
    RunChangeCode,
    RunChangesResponse,
    RunTrustResult,
    ScenarioIntegrity,
    UnevaluatedCheck,
)
from ..models.provenance import RunProvenanceManifest
from ..models.workspace import Workspace
from ..storage.workspace_storage import WorkspaceStorage
from .config_diff_service import diff_configs
from .config_paths import ignored_delta, matches
from .database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
    create_api_database_path_resolver,
)
from .provenance.capture import MANIFEST_NAME
from .run_history import PreviousRun, find_previous_run, read_run_metadata
from .run_trust import add_current_config_drift, read_run_trust

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config path groups.
#
# Each key is a dotted config path prefix. A prefix matches the path itself,
# any child path ("prefix.child") and any sibling key that extends it with an
# underscore ("dc_plan.match" matches "dc_plan.match_tiers"). The longest
# matching prefix wins, so a narrower entry can carve an exception out of a
# wider one ("dc_plan.match_magnet" is behavior inside the "dc_plan.match"
# plan family).
#
# To extend: add the new setting's prefix with its group. Only map a path to
# "plan_design" when it is a plan provision (what the plan offers), never an
# assumption about people or pay. An unmapped path is "other", which breaks
# like-for-like, so forgetting an entry errs on the safe side.
# ---------------------------------------------------------------------------
CONFIG_GROUP_PREFIXES: dict[str, ConfigGroup] = {
    # Studio's flat DC plan form (planalign_studio/components/config/).
    "dc_plan.eligibility_months": "plan_design",
    "dc_plan.auto_enroll": "plan_design",
    "dc_plan.default_deferral_percent": "plan_design",
    "dc_plan.reenrollment_sweep": "plan_design",
    "dc_plan.reenrollment_sweep_decline_probability": "employee_behavior",
    "dc_plan.max_voluntary_deferral_percent": "plan_design",
    "dc_plan.match": "plan_design",
    "dc_plan.match_magnet": "employee_behavior",
    "dc_plan.tenure_match_tiers": "plan_design",
    "dc_plan.points_match_tiers": "plan_design",
    "dc_plan.tenure_graded_bands": "plan_design",
    "dc_plan.core": "plan_design",
    "dc_plan.auto_escalation": "plan_design",
    "dc_plan.escalation": "plan_design",
    "dc_plan.escalation_participant_elected_signup_probability": "employee_behavior",
    "dc_plan.easy_enroll_enabled": "plan_design",
    "dc_plan.easy_enroll_packages": "plan_design",
    "dc_plan.easy_enroll_escalation_cap": "plan_design",
    "dc_plan.easy_enroll_channel_share": "employee_behavior",
    "dc_plan.opt_out": "employee_behavior",
    "dc_plan.new_hire_opt_out_rate": "employee_behavior",
    "dc_plan.voluntary": "employee_behavior",
    "dc_plan.deferral_spread_max_lift": "employee_behavior",
    "dc_plan.deferral_rate_changes": "employee_behavior",
    "dc_plan.deferral_match_response": "employee_behavior",
    "dc_plan.below_default": "employee_behavior",
    # Engine-shaped sections (config/simulation_config.yaml).
    "employer_match": "plan_design",
    "employer_core_contribution": "plan_design",
    "plan_eligibility": "plan_design",
    "plan_design_parameters": "plan_design",
    "plan_design_assignment": "plan_design",
    "eligibility.waiting_period_days": "plan_design",
    "setup.plan_year_start_date": "plan_design",
    "setup.plan_year_end_date": "plan_design",
    "setup.eligibility_waiting_period_days": "plan_design",
    "enrollment": "employee_behavior",
    "enrollment.auto_enrollment": "plan_design",
    "enrollment.auto_enrollment.opt_out_rates": "employee_behavior",
    "enrollment.auto_enrollment.voluntary_enrollment_rate": "employee_behavior",
    "enrollment.auto_enrollment.new_hire_opt_out_rate": "employee_behavior",
    "enrollment.auto_enrollment.deferral_spread_max_lift": "employee_behavior",
    "enrollment.auto_enrollment.reenrollment_sweep.decline_probability": (
        "employee_behavior"
    ),
    "deferral_auto_escalation": "plan_design",
    "deferral_auto_escalation.participant_elected_signup_probability": (
        "employee_behavior"
    ),
    "easy_enroll": "plan_design",
    "easy_enroll.channel_share": "employee_behavior",
    "deferral_rate_changes": "employee_behavior",
    "deferral_match_response": "employee_behavior",
    # Workforce and pay.
    "simulation.target_growth_rate": "workforce_and_pay",
    "workforce": "workforce_and_pay",
    "compensation": "workforce_and_pay",
    "new_hire": "workforce_and_pay",
    "promotion_hazard": "workforce_and_pay",
    "age_bands": "workforce_and_pay",
    "tenure_bands": "workforce_and_pay",
    "eligibility.new_hire_ineligible_pct": "workforce_and_pay",
    "eligibility.new_hire_eligibility_match_census": "workforce_and_pay",
}

# Engine-only changes; a rerun after an upgrade is not "inputs changed".
_ENGINE_CODES = frozenset({"engine_version_differs", "engine_build_differs"})
_RUN_CHANGE_CODES = frozenset(get_args(RunChangeCode))


def config_group(path: str) -> ConfigGroup:
    """Group a dotted config path; an unmapped path is ``other``."""
    found = [prefix for prefix in CONFIG_GROUP_PREFIXES if matches(path, prefix)]
    if not found:
        return "other"
    return CONFIG_GROUP_PREFIXES[max(found, key=len)]


@dataclass(frozen=True)
class EngineBuild:
    """The code a run executed, from provenance (commit plus local changes)."""

    commit: str
    dirty: bool
    tree_fingerprint: Optional[str] = None

    def same_as(self, other: "EngineBuild") -> bool:
        if self.commit != other.commit or self.dirty != other.dirty:
            return False
        # Two dirty trees are the same build only when their content matches.
        return not self.dirty or (
            self.tree_fingerprint is not None
            and self.tree_fingerprint == other.tree_fingerprint
        )

    def label(self) -> str:
        short = self.commit[:7]
        return f"{short} with local changes" if self.dirty else short


@dataclass(frozen=True)
class RunRecord:
    """What one scenario's selected result ran with."""

    scenario_id: str
    name: str
    has_run_record: bool
    config: Optional[dict[str, Any]] = None
    census_sha256: Optional[str] = None
    census_name: Optional[str] = None
    seed: Optional[int] = None
    years: Optional[tuple[int, int]] = None
    engine_version: Optional[str] = None
    # Logical seed file name -> SHA-256; None when provenance did not record it.
    seed_files: Optional[dict[str, str]] = None
    build: Optional[EngineBuild] = None
    notes: list[IntegrityReason] = field(default_factory=list)


@dataclass(frozen=True)
class _FactCheck:
    check: IntegrityCheck
    code: IntegrityReasonCode
    value: Callable[[RunRecord], Any]
    # What the UI shows; the compared value when unset.
    display: Optional[Callable[[RunRecord], Any]] = None


_FACT_CHECKS = (
    # Census files are compared by content hash but shown by file name.
    _FactCheck(
        "census",
        "census_differs",
        lambda record: record.census_sha256,
        lambda record: record.census_name,
    ),
    _FactCheck("seed", "seed_differs", lambda record: record.seed),
    _FactCheck("years", "years_differ", lambda record: record.years),
    _FactCheck(
        "engine_version",
        "engine_version_differs",
        lambda record: record.engine_version,
    ),
)


class ComparisonIntegrityService:
    """Evaluate like-for-like verdicts from each scenario's selected result."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ) -> None:
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def evaluate(
        self,
        workspace: Workspace,
        scenario_names: Mapping[str, str],
        anchor_id: str,
    ) -> ComparisonIntegrityResponse:
        """Compare every scenario in ``scenario_names`` against ``anchor_id``."""
        records = {
            scenario_id: self.read_record(workspace, scenario_id, name)
            for scenario_id, name in scenario_names.items()
        }
        anchor = records[anchor_id]
        return ComparisonIntegrityResponse(
            anchor_scenario_id=anchor_id,
            anchor_scenario_name=anchor.name,
            anchor_engine_version=anchor.engine_version,
            scenarios=[
                compare_records(anchor, record)
                for scenario_id, record in records.items()
                if scenario_id != anchor_id
            ],
        )

    def read_record(
        self, workspace: Workspace, scenario_id: str, name: str
    ) -> RunRecord:
        """Read one selected result: JSON/YAML files plus one metadata query."""
        resolved = self.db_resolver.resolve(
            workspace.id, scenario_id, verify_database=False
        )
        if not resolved.exists or resolved.source not in {"run", "scenario"}:
            return RunRecord(scenario_id=scenario_id, name=name, has_run_record=False)
        manifest = _read_manifest(resolved)
        trust = add_current_config_drift(
            read_run_trust(resolved.path, resolved.run_id),
            self.storage.get_merged_config_for(workspace, scenario_id),
        )
        config = _read_run_config(resolved.config_path)
        record = RunRecord(
            scenario_id=scenario_id,
            name=name,
            has_run_record=manifest is not None or trust.available,
            config=config,
            census_sha256=_census_sha256(manifest),
            census_name=_census_name(config),
            seed=_seed(trust, manifest),
            years=_years(resolved, manifest),
            engine_version=trust.planalign_version
            or (manifest.software.planalign_version if manifest else None),
            seed_files=_seed_files(manifest),
            build=_build(manifest),
        )
        notes = _notes(scenario_id, trust) + _previous_run_notes(
            record, _selected_run_dir(resolved)
        )
        return replace(record, notes=notes)

    def run_changes(
        self, workspace_id: str, scenario_id: str, name: str
    ) -> RunChangesResponse:
        """What changed between a scenario's previous run and its selected result."""
        resolved = self.db_resolver.resolve(
            workspace_id, scenario_id, verify_database=False
        )
        compared = _since_previous_run(_selected_run_dir(resolved), scenario_id)
        if compared is None:
            return RunChangesResponse(
                scenario_id=scenario_id, scenario_name=name, has_previous_run=False
            )
        previous, integrity = compared
        return RunChangesResponse(
            scenario_id=scenario_id,
            scenario_name=name,
            has_previous_run=True,
            previous_run_id=previous.run_id,
            previous_run_at=previous.started_at,
            changes=_run_changes(integrity),
            unevaluated=list(
                dict.fromkeys(item.check for item in integrity.unevaluated)
            ),
        )


def compare_records(anchor: RunRecord, scenario: RunRecord) -> ScenarioIntegrity:
    """Like-for-like verdict for ``scenario`` against ``anchor``."""
    reasons, unevaluated = _fact_reasons(anchor, scenario)
    reasons.extend(_build_reasons(anchor, scenario))
    if anchor.seed_files is None or scenario.seed_files is None:
        unevaluated.extend(
            _missing(
                "seed_files",
                (anchor, anchor.seed_files),
                (scenario, scenario.seed_files),
            )
        )
    else:
        reasons.extend(_seed_file_reasons(anchor.seed_files, scenario.seed_files))
    plan_differences: list[ConfigDelta] = []
    if anchor.config is None or scenario.config is None:
        unevaluated.extend(
            _missing("config", (anchor, anchor.config), (scenario, scenario.config))
        )
    else:
        config_reasons, plan_differences = _config_reasons(
            anchor.config, scenario.config
        )
        reasons.extend(config_reasons)
    reasons.extend(anchor.notes + scenario.notes)
    return ScenarioIntegrity(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        verdict=_verdict(reasons, unevaluated),
        reasons=reasons,
        unevaluated=unevaluated,
        plan_design_differences=plan_differences,
        engine_version=scenario.engine_version,
    )


def _fact_reasons(
    anchor: RunRecord, scenario: RunRecord
) -> tuple[list[IntegrityReason], list[UnevaluatedCheck]]:
    reasons: list[IntegrityReason] = []
    unevaluated: list[UnevaluatedCheck] = []
    for fact in _FACT_CHECKS:
        anchor_value, scenario_value = fact.value(anchor), fact.value(scenario)
        missing = _missing(
            fact.check, (anchor, anchor_value), (scenario, scenario_value)
        )
        unevaluated.extend(missing)
        if not missing and anchor_value != scenario_value:
            display = fact.display or fact.value
            reasons.append(
                IntegrityReason(
                    code=fact.code,
                    effect="breaks",
                    anchor_value=_display(display(anchor)),
                    scenario_value=_display(display(scenario)),
                )
            )
    return reasons, unevaluated


def _build_reasons(anchor: RunRecord, scenario: RunRecord) -> list[IntegrityReason]:
    """Same engine version but different code. Skipped when a run has no commit
    (e.g. a non-git install), so that never makes a comparison ``unknown``."""
    if anchor.engine_version is None or anchor.engine_version != (
        scenario.engine_version
    ):
        return []
    if anchor.build is None or scenario.build is None:
        return []
    if anchor.build.same_as(scenario.build):
        return []
    return [
        IntegrityReason(
            code="engine_build_differs",
            effect="breaks",
            anchor_value=anchor.build.label(),
            scenario_value=scenario.build.label(),
        )
    ]


def _seed_file_reasons(
    anchor_files: Mapping[str, str], scenario_files: Mapping[str, str]
) -> list[IntegrityReason]:
    """One reason naming the differing seed tables (file names, never paths)."""
    names = sorted(
        name
        for name in anchor_files.keys() | scenario_files.keys()
        if anchor_files.get(name) != scenario_files.get(name)
    )
    if not names:
        return []
    return [
        IntegrityReason(
            code="seed_files_differ",
            effect="breaks",
            files=list(dict.fromkeys(Path(name).name for name in names)),
        )
    ]


def read_run_files(run_dir: Path, scenario_id: str, name: str) -> RunRecord:
    """What one run ran with, from its JSON/YAML files only (no database)."""
    manifest = read_run_manifest(run_dir)
    metadata = read_run_metadata(run_dir) or {}
    config_path = run_dir / "config.yaml"
    config = _read_run_config(config_path if config_path.is_file() else None)
    seed = manifest.random_seed if manifest is not None else None
    return RunRecord(
        scenario_id=scenario_id,
        name=name,
        has_run_record=manifest is not None or bool(metadata),
        config=config,
        census_sha256=_census_sha256(manifest),
        census_name=_census_name(config),
        seed=seed if seed is not None else _int_or_none(metadata.get("seed")),
        years=_file_years(metadata, manifest),
        engine_version=manifest.software.planalign_version if manifest else None,
        seed_files=_seed_files(manifest),
        build=_build(manifest),
    )


def _selected_run_dir(resolved: ResolvedDatabasePath) -> Optional[Path]:
    if resolved.source != "run" or resolved.path is None:
        return None
    return resolved.path.parent


def _since_previous_run(
    run_dir: Optional[Path], scenario_id: str, selected: Optional[RunRecord] = None
) -> Optional[tuple[PreviousRun, ScenarioIntegrity]]:
    """Compare the previous run (as anchor) with the selected result.

    ``selected`` is the already-read selected result, if any; otherwise it is
    read from its run files. The previous run is always read from files only.
    """
    previous = find_previous_run(run_dir) if run_dir is not None else None
    if run_dir is None or previous is None:
        return None
    current = selected or read_run_files(run_dir, scenario_id, "")
    integrity = compare_records(read_run_files(previous.path, scenario_id, ""), current)
    return previous, integrity


def _previous_run_notes(
    record: RunRecord, run_dir: Optional[Path]
) -> list[IntegrityReason]:
    """A note when inputs or assumptions (not plan design, not only the engine)
    changed since the previous run. ``record`` must not carry notes yet."""
    compared = _since_previous_run(run_dir, record.scenario_id, record)
    if compared is None or not any(
        reason.effect == "breaks" and reason.code not in _ENGINE_CODES
        for reason in compared[1].reasons
    ):
        return []
    return [
        IntegrityReason(
            code="changed_since_previous_run",
            effect="note",
            scenario_id=record.scenario_id,
        )
    ]


def _run_changes(integrity: ScenarioIntegrity) -> list[RunChange]:
    """Non-plan differences first, then plan design (previous=anchor side)."""
    changes = [
        RunChange(
            code=cast(RunChangeCode, reason.code),
            path=reason.path,
            group=reason.group,
            files=reason.files,
            previous_value=reason.anchor_value,
            current_value=reason.scenario_value,
        )
        for reason in integrity.reasons
        if reason.effect == "breaks" and reason.code in _RUN_CHANGE_CODES
    ]
    changes.extend(
        RunChange(
            code="config_differs",
            path=delta.path,
            group="plan_design",
            previous_value=delta.a,
            current_value=delta.b,
        )
        for delta in integrity.plan_design_differences
    )
    return changes


def _verdict(
    reasons: list[IntegrityReason], unevaluated: list[UnevaluatedCheck]
) -> ComparisonVerdict:
    if any(reason.effect == "breaks" for reason in reasons):
        return "not_like_for_like"
    if unevaluated:
        return "unknown"
    return "like_for_like"


def _missing(
    check: IntegrityCheck, *sides: tuple[RunRecord, Any]
) -> list[UnevaluatedCheck]:
    return [
        UnevaluatedCheck(
            check=check,
            scenario_id=record.scenario_id,
            cause="not_recorded" if record.has_run_record else "no_run_record",
        )
        for record, value in sides
        if value is None
    ]


def _config_reasons(
    anchor_config: Mapping[str, Any], scenario_config: Mapping[str, Any]
) -> tuple[list[IntegrityReason], list[ConfigDelta]]:
    differences, _ = diff_configs(anchor_config, scenario_config)
    reasons: list[IntegrityReason] = []
    plan_differences: list[ConfigDelta] = []
    for delta in differences:
        if ignored_delta(delta) or _same_engine_acquisitions(delta):
            continue
        group = config_group(delta.path)
        if group == "plan_design":
            plan_differences.append(delta)
            continue
        reasons.append(
            IntegrityReason(
                code="config_differs",
                effect="breaks",
                anchor_value=delta.a,
                scenario_value=delta.b,
                path=delta.path,
                group=group,
            )
        )
    return reasons, plan_differences


def _same_engine_acquisitions(delta: ConfigDelta) -> bool:
    """Acquisitions the engine runs the same: ``name`` is display-only, a key
    left at its default means the same as unset (Studio omits defaults), and
    the ``[]`` Studio saves when every group is removed means the same as unset."""
    if delta.path != "workforce.acquisitions":
        return False
    return _engine_acquisitions(delta.a) == _engine_acquisitions(delta.b)


def _engine_acquisitions(value: Any) -> Any:
    if not value:
        return []
    if not isinstance(value, list):
        return value
    return [_engine_fields(item) for item in value]


# Optional AcquisitionSettings fields and their defaults.
_ACQUISITION_DEFAULTS = {
    name: info.default
    for name, info in AcquisitionSettings.model_fields.items()
    if not info.is_required()
}


def _engine_fields(item: Any) -> Any:
    if not isinstance(item, Mapping):
        return item
    return {
        key: item_value
        for key, item_value in item.items()
        if key != "name"
        and not (
            key in _ACQUISITION_DEFAULTS and _ACQUISITION_DEFAULTS[key] == item_value
        )
    }


def _notes(scenario_id: str, trust: RunTrustResult) -> list[IntegrityReason]:
    notes: list[IntegrityReason] = []
    if {"current_config_mismatch", "current_seed_mismatch"} & set(trust.reasons):
        notes.append(
            IntegrityReason(
                code="edited_since_run", effect="note", scenario_id=scenario_id
            )
        )
    # Rows from runs with different settings: the result itself is not one
    # run, so it can never be like-for-like with anything.
    if "mixed_generation" in trust.reasons:
        notes.append(
            IntegrityReason(
                code="mixed_generation", effect="breaks", scenario_id=scenario_id
            )
        )
    return notes


def _seed(
    trust: RunTrustResult, manifest: Optional[RunProvenanceManifest]
) -> Optional[int]:
    if trust.available and trust.random_seed is not None:
        return trust.random_seed
    return manifest.random_seed if manifest is not None else None


def _years(
    resolved: ResolvedDatabasePath, manifest: Optional[RunProvenanceManifest]
) -> Optional[tuple[int, int]]:
    if resolved.start_year is not None and resolved.end_year is not None:
        return (resolved.start_year, resolved.end_year)
    return _manifest_years(manifest)


def _file_years(
    metadata: Mapping[str, Any], manifest: Optional[RunProvenanceManifest]
) -> Optional[tuple[int, int]]:
    start = _int_or_none(metadata.get("start_year"))
    end = _int_or_none(metadata.get("end_year"))
    if start is not None and end is not None:
        return (start, end)
    return _manifest_years(manifest)


def _manifest_years(
    manifest: Optional[RunProvenanceManifest],
) -> Optional[tuple[int, int]]:
    if manifest is None:
        return None
    identity = manifest.run_identity
    if identity.intended_start_year is None or identity.intended_end_year is None:
        return None
    return (identity.intended_start_year, identity.intended_end_year)


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _seed_files(
    manifest: Optional[RunProvenanceManifest],
) -> Optional[dict[str, str]]:
    # An empty list means capture failed (the seed directory is never empty).
    if manifest is None or not manifest.seed_files:
        return None
    return {seed.logical_name: seed.sha256 for seed in manifest.seed_files}


def _build(manifest: Optional[RunProvenanceManifest]) -> Optional[EngineBuild]:
    software = manifest.software if manifest is not None else None
    if software is None or software.git_commit_sha is None:
        return None
    return EngineBuild(
        commit=software.git_commit_sha,
        dirty=software.working_tree_state == "dirty",
        tree_fingerprint=software.working_tree_fingerprint,
    )


def _census_sha256(manifest: Optional[RunProvenanceManifest]) -> Optional[str]:
    if manifest is None or manifest.census_input is None:
        return None
    return manifest.census_input.sha256


def _census_name(config: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The census file name the run read (name only, never the full path)."""
    for section in ("setup", "data_sources"):
        values = config.get(section) if config else None
        path = values.get("census_parquet_path") if isinstance(values, dict) else None
        if isinstance(path, str) and path:
            return Path(path).name
    return None


def _display(value: Any) -> Any:
    if isinstance(value, tuple):
        return f"{value[0]}–{value[1]}"
    return value


def _read_manifest(resolved: ResolvedDatabasePath) -> Optional[RunProvenanceManifest]:
    if resolved.source != "run" or resolved.path is None:
        return None
    return read_run_manifest(resolved.path.parent)


def read_run_manifest(run_dir: Path) -> Optional[RunProvenanceManifest]:
    """Parse a run's ``provenance.json``; ``None`` when absent or unreadable."""
    path = run_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return RunProvenanceManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        logger.info("Run provenance unreadable in %s: %s", run_dir.name, exc)
        return None


def _read_run_config(config_path: Optional[Path]) -> Optional[dict[str, Any]]:
    if config_path is None:
        return None
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.info("Run config unreadable in %s: %s", config_path.parent.name, exc)
        return None
    return config if isinstance(config, dict) else None


__all__ = [
    "CONFIG_GROUP_PREFIXES",
    "ComparisonIntegrityService",
    "RunRecord",
    "compare_records",
    "config_group",
    "read_run_files",
    "read_run_manifest",
]
