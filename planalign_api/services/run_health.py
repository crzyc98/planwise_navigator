"""Derive a run-health summary from one archived run's provenance manifest.

Read-only: consumes ``provenance.json`` exactly as captured during
orchestration and projects a concise, safe summary. Messages are derived
from structured fields only — raw rule messages and details are never
exposed (mirroring ``DataValidator.to_safe_results``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from pydantic import ValidationError

from ..models.census_tie_out import CensusTieOut
from ..models.provenance import CapturedValidationResult, RunProvenanceManifest
from ..models.run_health import (
    RunHealthCounts,
    RunHealthFinding,
    RunHealthReport,
    RunHealthTieOut,
)

logger = logging.getLogger(__name__)

# Returns the tie-out for the run, or None when it shouldn't be computed.
TieOutLoader = Callable[[], Optional[CensusTieOut]]

MANIFEST_FILENAME = "provenance.json"
_VALIDATION_STAGE = "VALIDATION"

_ZERO_COUNTS = RunHealthCounts(passed=0, warning=0, failed=0, total=0)


def build_run_health(scenario_id: str, run_id: str, run_dir: Path) -> RunHealthReport:
    """Summarize validation evidence for one resolved archived-run directory."""
    manifest_path = run_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return RunHealthReport(
            status="missing_provenance",
            scenario_id=scenario_id,
            run_id=run_id,
            counts=_ZERO_COUNTS,
        )
    try:
        manifest = RunProvenanceManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        return RunHealthReport(
            status="unavailable",
            scenario_id=scenario_id,
            run_id=run_id,
            counts=_ZERO_COUNTS,
        )
    return _summarize_manifest(scenario_id, str(manifest.run_id), manifest)


def _summarize_manifest(
    scenario_id: str, run_id: str, manifest: RunProvenanceManifest
) -> RunHealthReport:
    results = sorted(
        manifest.validation_results,
        key=lambda item: (item.simulation_year, item.check_name, item.severity),
    )
    failed = [r for r in results if not r.passed and _is_error(r)]
    warned = [r for r in results if not r.passed and not _is_error(r)]
    passed_count = len(results) - len(failed) - len(warned)
    counts = RunHealthCounts(
        passed=passed_count,
        warning=len(warned),
        failed=len(failed),
        total=len(results),
    )

    if failed:
        status: str = "failed"
    elif warned:
        status = "warnings"
    elif results:
        status = "clean"
    else:
        # No captured outcomes at all: never present this as a clean run.
        status = "unavailable"

    findings = [_finding(result) for result in failed + warned]
    return RunHealthReport(
        status=status,  # type: ignore[arg-type]
        scenario_id=scenario_id,
        run_id=run_id,
        disposition=manifest.validation_disposition,
        counts=counts,
        findings=findings,
    )


def _is_error(result: CapturedValidationResult) -> bool:
    return result.severity.lower() == "error"


def _finding(result: CapturedValidationResult) -> RunHealthFinding:
    return RunHealthFinding(
        check_name=result.check_name,
        severity=result.severity.lower(),
        simulation_year=result.simulation_year,
        stage=_VALIDATION_STAGE,
        passed=result.passed,
        affected_record_count=result.affected_record_count,
        message=_safe_message(result),
    )


def _safe_message(result: CapturedValidationResult) -> str:
    noun = "Error" if _is_error(result) else "Warning"
    affected = result.affected_record_count
    if affected is None:
        detail = "see audit report for details"
    else:
        plural = "" if affected == 1 else "s"
        detail = f"{affected} record{plural} affected"
    return f"{noun} in {result.simulation_year}: {detail}."


def with_census_tie_out(report: RunHealthReport, load: TieOutLoader) -> RunHealthReport:
    """Add one tie-out line when the run's census tie-out has a gap.

    The tie-out is advisory: any failure is logged and Run Health is returned
    unchanged, and a tie-out for a different run than ``report`` is ignored.
    """
    try:
        tie_out = load()
    except Exception:  # the tie-out is advisory and must never break Run Health
        logger.exception(
            "Census tie-out failed for run %s; Run Health omits it", report.run_id
        )
        return report
    if tie_out is None or tie_out.run_id != report.run_id:
        return report
    summary = tie_out_summary(tie_out)
    return report.model_copy(update={"census_tie_out": summary}) if summary else report


def tie_out_summary(tie_out: CensusTieOut) -> Optional[RunHealthTieOut]:
    """The single Run Health line for a tie-out's gaps (None when none)."""
    labels = [row.label for row in tie_out.rows if row.status == "gap"]
    if not tie_out.available or not labels:
        return None
    rows = "row differs" if len(labels) == 1 else "rows differ"
    return RunHealthTieOut(
        labels=labels,
        message=(
            f"{len(labels)} census tie-out {rows} from the census: "
            f"{', '.join(labels)}"
        ),
    )
