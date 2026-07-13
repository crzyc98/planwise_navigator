"""Read-only assembly of one archived run provenance report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import]
from pydantic import ValidationError

from planalign_api.models.provenance import (
    ConfigurationEvidence,
    EvidenceFinding,
    ExecutionTimingEvidence,
    ReportEvidence,
    RunIdentityEvidence,
    RunProvenanceManifest,
    SoftwareEvidence,
)
from .capture import config_fingerprint, safe_effective_config
from .locator import LocatedArchive, locate_run_archive
from .render import attach_digest

_KNOWN_EVENT_TYPES = {
    "TOTAL",
    "HIRE",
    "PROMOTION",
    "TERMINATION",
    "RAISE",
    "MERIT",
    "SABBATICAL",
    "ELIGIBILITY",
    "ENROLLMENT",
    "CONTRIBUTION",
    "VESTING",
    "AUTO_ENROLLMENT_WINDOW",
    "ENROLLMENT_CHANGE",
    "FORFEITURE",
    "HCE_STATUS",
    "COMPLIANCE",
    "DEFERRAL_ESCALATION",
    "BENEFIT_ENROLLMENT",
    "DC_PLAN_ELIGIBILITY",
    "DC_PLAN_ENROLLMENT",
    "DC_PLAN_CONTRIBUTION",
    "DC_PLAN_VESTING",
    "MATCH_RESPONSE",
}
_KNOWN_SEVERITIES = {"error", "warning", "info"}


def build_provenance_report(workspaces_root: Path, run_id: str):
    archive = locate_run_archive(workspaces_root, run_id)
    report = (
        _from_manifest(archive)
        if "provenance.json" in archive.files
        else _from_legacy(archive)
    )
    archive.assert_unchanged()
    return report


def _from_manifest(archive: LocatedArchive):
    try:
        manifest = RunProvenanceManifest.model_validate_json(
            archive.files["provenance.json"]
        )
    except (ValidationError, ValueError):
        return _from_legacy(archive, malformed_manifest=True)
    findings = list(manifest.capture_findings)
    findings.extend(_binding_findings(archive, manifest))
    evidence = ReportEvidence(
        run=manifest.run_identity,
        timing=manifest.execution_timing,
        software=manifest.software,
        configuration=manifest.configuration,
        random_seed=manifest.random_seed,
        census_input=manifest.census_input,
        seed_files=manifest.seed_files,
        event_counts=manifest.event_counts,
        workforce_reconciliations=manifest.workforce_reconciliations,
        validation_results=manifest.validation_results,
        validation_disposition=manifest.validation_disposition,
    )
    findings.extend(_required_findings(evidence, manifest.capture_state))
    return _finish(evidence, findings)


def _binding_findings(
    archive: LocatedArchive, manifest: RunProvenanceManifest
) -> list[EvidenceFinding]:
    findings: list[EvidenceFinding] = []
    try:
        metadata = json.loads(archive.files.get("run_metadata.json", b"{}"))
        archived_status = metadata.get("status")
        if (
            archived_status is not None
            and archived_status != manifest.run_identity.status
        ):
            findings.append(
                _finding(
                    "evidence.run.status",
                    "integrity_mismatch",
                    "archived status conflicts with the execution provenance manifest",
                )
            )
        for metadata_key, evidence_field in (
            ("start_year", "intended_start_year"),
            ("end_year", "intended_end_year"),
        ):
            archived_value = metadata.get(metadata_key)
            if archived_value is not None and archived_value != getattr(
                manifest.run_identity, evidence_field
            ):
                findings.append(
                    _finding(
                        f"evidence.run.{evidence_field}",
                        "integrity_mismatch",
                        "archived simulation years conflict with the execution provenance manifest",
                    )
                )
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        findings.append(
            _finding(
                "archive.run_metadata",
                "malformed",
                "archived run metadata is malformed",
            )
        )
    if "config.yaml" in archive.files:
        try:
            archived_config = yaml.safe_load(archive.files["config.yaml"]) or {}
            if (
                config_fingerprint(archived_config)
                != manifest.configuration.fingerprint
            ):
                findings.append(
                    _finding(
                        "evidence.configuration.fingerprint",
                        "integrity_mismatch",
                        "archived configuration does not match its execution-time fingerprint",
                    )
                )
        except (yaml.YAMLError, ValueError, TypeError):
            findings.append(
                _finding(
                    "archive.config", "malformed", "archived configuration is malformed"
                )
            )
    return findings


def _from_legacy(archive: LocatedArchive, malformed_manifest: bool = False):
    metadata: dict[str, Any] = {}
    findings: list[EvidenceFinding] = []
    try:
        metadata = json.loads(archive.files.get("run_metadata.json", b"{}"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        findings.append(
            _finding("evidence.run", "malformed", "archived run metadata is malformed")
        )
    config = None
    if "config.yaml" in archive.files:
        try:
            loaded = yaml.safe_load(archive.files["config.yaml"]) or {}
            config, redactions = safe_effective_config(loaded)
            configuration = ConfigurationEvidence(
                effective=config,
                fingerprint=None,
                fingerprint_method=None,
                redactions=redactions,
            )
        except (yaml.YAMLError, ValueError, TypeError):
            configuration = ConfigurationEvidence()
            findings.append(
                _finding(
                    "evidence.configuration",
                    "malformed",
                    "archived effective configuration is malformed",
                )
            )
    else:
        configuration = ConfigurationEvidence()
    if malformed_manifest:
        findings.append(
            _finding(
                "provenance_manifest",
                "malformed",
                "execution provenance manifest is malformed",
            )
        )
    simulation = (config or {}).get("simulation", {})
    run = RunIdentityEvidence(
        run_id=archive.run_id,
        workspace_id=metadata.get("workspace_id"),
        scenario_id=metadata.get("scenario_id"),
        plan_design_id=(config or {}).get("plan_design_id")
        or (config or {}).get("plan_design", {}).get("plan_design_id"),
        status=metadata.get("status", "unknown"),
        intended_start_year=metadata.get("start_year"),
        intended_end_year=metadata.get("end_year"),
        completed_years=[],
    )
    seed = simulation.get("random_seed")
    if (
        metadata.get("seed") is not None
        and seed is not None
        and metadata["seed"] != seed
    ):
        findings.append(
            _finding(
                "evidence.random_seed",
                "unbound",
                "legacy seed conflicts with archived effective configuration",
            )
        )
        seed = None
    evidence = ReportEvidence(
        run=run,
        timing=ExecutionTimingEvidence(
            started_at=metadata.get("started_at"),
            completed_at=metadata.get("completed_at"),
            duration_seconds=metadata.get("duration_seconds"),
        ),
        software=SoftwareEvidence(),
        configuration=configuration,
        random_seed=seed,
        census_input=None,
        seed_files=[],
        event_counts=[],
        workforce_reconciliations=[],
        validation_results=[],
        validation_disposition="unavailable",
    )
    findings.extend(_required_findings(evidence, "legacy"))
    return _finish(evidence, findings)


def _required_findings(e: ReportEvidence, capture_state: str) -> list[EvidenceFinding]:
    checks = {
        "evidence.run.scenario_id": e.run.scenario_id,
        "evidence.run.plan_design_id": e.run.plan_design_id,
        "evidence.timing.started_at": e.timing.started_at,
        "evidence.software.planalign_version": e.software.planalign_version,
        "evidence.software.git_commit_sha": e.software.git_commit_sha,
        "evidence.configuration.effective": e.configuration.effective,
        "evidence.configuration.fingerprint": e.configuration.fingerprint,
        "evidence.random_seed": e.random_seed,
        "evidence.census_input": e.census_input,
        "evidence.seed_files": e.seed_files,
        "evidence.validation_results": e.validation_results,
    }
    findings = [
        _finding(path, "unavailable", "required execution-time evidence is unavailable")
        for path, value in checks.items()
        if value is None or value == []
    ]
    if e.software.working_tree_state == "unavailable":
        findings.append(
            _finding(
                "evidence.software.working_tree_state",
                "unavailable",
                "execution-time source state is unavailable",
            )
        )
    intended = (
        set(range(e.run.intended_start_year, e.run.intended_end_year + 1))
        if e.run.intended_start_year is not None and e.run.intended_end_year is not None
        else set()
    )
    completed = set(e.run.completed_years)
    for year in sorted(intended - completed):
        findings.append(
            _finding(
                f"evidence.run.completed_years[{year}]",
                "incomplete_capture",
                "simulation year was not captured as completed",
            )
        )
    for year in sorted(completed):
        if not any(x.simulation_year == year for x in e.event_counts):
            findings.append(
                _finding(
                    f"evidence.event_counts[{year}]",
                    "unavailable",
                    "completed-year event counts are unavailable",
                )
            )
        if not any(x.simulation_year == year for x in e.workforce_reconciliations):
            findings.append(
                _finding(
                    f"evidence.workforce_reconciliations[{year}]",
                    "unavailable",
                    "completed-year workforce reconciliation is unavailable",
                )
            )
        else:
            reconciliation = next(
                x for x in e.workforce_reconciliations if x.simulation_year == year
            )
            for field in (
                "opening_workforce",
                "hires",
                "terminations",
                "expected_closing_workforce",
                "actual_closing_workforce",
                "variance",
                "opening_source",
            ):
                if (
                    getattr(reconciliation, field) is None
                    or getattr(reconciliation, field) == "unavailable"
                ):
                    findings.append(
                        _finding(
                            f"evidence.workforce_reconciliations[{year}].{field}",
                            "unavailable",
                            "reconciliation component is unavailable",
                        )
                    )
        if not any(x.simulation_year == year for x in e.validation_results):
            findings.append(
                _finding(
                    f"evidence.validation_results[{year}]",
                    "unavailable",
                    "completed-year validation results are unavailable",
                )
            )
    for event_count in e.event_counts:
        if event_count.simulation_year not in completed:
            findings.append(
                _finding(
                    f"evidence.event_counts[{event_count.simulation_year}]",
                    "unbound",
                    "event counts are not bound to a captured completed year",
                )
            )
        if event_count.event_type.upper() not in _KNOWN_EVENT_TYPES:
            findings.append(
                _finding(
                    f"evidence.event_counts[{event_count.simulation_year}].event_type",
                    "unavailable",
                    "event type is preserved but not supported by this report schema",
                )
            )
    for validation in e.validation_results:
        if validation.affected_record_count is None:
            findings.append(
                _finding(
                    f"evidence.validation_results[{validation.simulation_year}].affected_record_count",
                    "unavailable",
                    "affected-record count was not captured",
                )
            )
        if validation.severity.lower() not in _KNOWN_SEVERITIES:
            findings.append(
                _finding(
                    f"evidence.validation_results[{validation.simulation_year}].severity",
                    "unavailable",
                    "validation severity is preserved but not supported by this report schema",
                )
            )
    for reconciliation in e.workforce_reconciliations:
        opening = reconciliation.opening_workforce
        hires = reconciliation.hires
        terminations = reconciliation.terminations
        if opening is not None and hires is not None and terminations is not None:
            expected = opening + hires - terminations
            if reconciliation.expected_closing_workforce != expected:
                findings.append(
                    _finding(
                        f"evidence.workforce_reconciliations[{reconciliation.simulation_year}].expected_closing_workforce",
                        "integrity_mismatch",
                        "captured workforce equation does not reconcile",
                    )
                )
    if capture_state == "capturing":
        findings.append(
            _finding(
                "capture_state",
                "incomplete_capture",
                "run provenance capture did not reach a terminal state",
                required=False,
            )
        )
    return findings


def _finding(
    path: str, code: str, reason: str, required: bool = True
) -> EvidenceFinding:
    return EvidenceFinding(field_path=path, code=code, reason=reason, required=required)  # type: ignore[arg-type]


def _finish(evidence: ReportEvidence, findings: list[EvidenceFinding]):
    unique = {(x.field_path, x.code): x for x in findings}
    ordered = sorted(unique.values(), key=lambda x: (x.field_path, x.code, x.reason))
    if any(x.required and x.code != "incomplete_capture" for x in ordered):
        disposition = "unverifiable"
    elif (
        evidence.run.status != "completed"
        or ordered
        or evidence.validation_disposition in {"failed", "incomplete", "unavailable"}
    ):
        disposition = "incomplete"
    else:
        disposition = "fully_verified"
    return attach_digest(
        {
            "report_schema_version": "1.0",
            "evidence": evidence.model_dump(mode="python"),
            "missing_evidence": [x.model_dump() for x in ordered],
            "verification_disposition": disposition,
        }
    )
