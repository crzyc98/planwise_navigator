"""Read a completed job's pack back as a Studio result, and judge its currency.

Everything shown comes from files the CLI wrote — ``manifest.json``,
``diagnostics.json``, and ``backtest/scorecard.json`` — so Studio can never
show a number the pack does not contain. Currency (FR-022) is recomputed on
every read: the history files, the pack files, and the base scenario may all
have changed since the job ran.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from planalign_backtest.errors import BacktestError
from planalign_backtest.report import load_scorecard, scorecard_is_current
from planalign_fit.pack import (
    DIAGNOSTICS_FILENAME,
    REPORT_FILENAME,
    PackError,
    ParameterPack,
    load_pack,
    verify_pack,
)

from ...models.param_fit import ParamFitJob, ParamFitResult, StaleReason
from ..provenance.capture import config_fingerprint

SCORECARD_JSON = Path("backtest") / "scorecard.json"
SCORECARD_MD = Path("backtest") / "scorecard.md"


@dataclass(frozen=True)
class PackState:
    """A loaded pack plus whether its files still match its fingerprint."""

    pack: ParameterPack
    verified: bool
    backtest: Optional[dict[str, Any]]


def read_pack_state(pack_dir: Path) -> PackState:
    pack = load_pack(pack_dir)
    return PackState(
        pack=pack,
        verified=verify_pack(pack),
        backtest=_verified_backtest(pack, pack_dir),
    )


def _verified_backtest(pack: ParameterPack, pack_dir: Path) -> Optional[dict[str, Any]]:
    """The pack's backtest only if its scorecard is intact and scores this pack.

    ``load_scorecard`` recomputes the scorecard's own fingerprint, so an edited
    verdict (say ``fail`` -> ``pass``) cannot quietly remove an acknowledgement.
    """
    try:
        scorecard = load_scorecard(pack_dir)
    except BacktestError:
        return None
    if scorecard is None or not scorecard_is_current(scorecard, pack):
        return None
    return {
        "scorecard_fingerprint": scorecard.scorecard_fingerprint,
        "verdict": scorecard.verdict,
        "holdout_years": list(scorecard.split.holdout_years),
    }


def load_result(
    job: ParamFitJob,
    pack_dir: Path,
    *,
    current_history_digest: Optional[str],
    current_base_config: Optional[dict[str, Any]],
) -> ParamFitResult:
    """The result of a completed job, with any staleness spelled out."""
    state = read_pack_state(pack_dir)
    manifest = state.pack.manifest
    diagnostics = _read_json(pack_dir / DIAGNOSTICS_FILENAME) or {}
    scorecard = _scorecard_payload(pack_dir)
    summary = dict(diagnostics.get("summary") or _summary_from_manifest(manifest))
    summary["verdict"] = scorecard.get("verdict") if scorecard else None
    return ParamFitResult(
        summary=summary,
        diagnostics=diagnostics.get("groups") or {},
        unfittable=diagnostics.get("unfittable", manifest.unfittable),
        warnings=diagnostics.get("warnings", manifest.warnings),
        promotion_classification=diagnostics.get("promotion_classification"),
        provenance=_provenance(manifest, state.verified),
        scorecard=scorecard,
        scorecard_current=state.backtest is not None,
        has_fit_report=(pack_dir / REPORT_FILENAME).is_file(),
        stale=stale_reasons(
            job,
            state,
            current_history_digest=current_history_digest,
            current_base_config=current_base_config,
        ),
    )


HISTORY_CHANGED = (
    "The history files this job fitted were changed or removed after it ran."
)
PACK_MODIFIED = (
    "The parameter pack's files no longer match its fingerprint; they were edited "
    "after fitting."
)


def stale_reasons(
    job: ParamFitJob,
    state: PackState,
    *,
    current_history_digest: Optional[str],
    current_base_config: Optional[dict[str, Any]],
) -> list[StaleReason]:
    reasons: list[StaleReason] = []
    if current_history_digest != job.inputs.source_digest:
        reasons.append(StaleReason(reason="history_changed", message=HISTORY_CHANGED))
    if not state.verified:
        reasons.append(StaleReason(reason="pack_modified", message=PACK_MODIFIED))
    base_changed = current_base_config is None or (
        config_fingerprint(current_base_config) != job.inputs.base_scenario_fingerprint
    )
    if base_changed:
        reasons.append(
            StaleReason(
                reason="base_scenario_changed",
                message=(
                    f"Base scenario '{job.inputs.base_scenario_name}' changed or "
                    "was deleted after this job ran; its priors may differ now."
                ),
            )
        )
    return reasons


def report_path(pack_dir: Path, kind: str) -> Optional[Path]:
    path = pack_dir / (REPORT_FILENAME if kind == "fit" else SCORECARD_MD)
    return path if path.is_file() else None


def pack_summary(pack_dir: Path) -> tuple[Optional[str], Optional[str]]:
    """``(pack_id, verdict)`` for the job list, tolerant of missing files."""
    manifest = _read_json(pack_dir / "manifest.json")
    scorecard = _scorecard_payload(pack_dir)
    pack_id = manifest.get("pack_id") if manifest else None
    verdict = scorecard.get("verdict") if scorecard else None
    return pack_id, verdict


def safe_read_pack_state(pack_dir: Path) -> Optional[PackState]:
    try:
        return read_pack_state(pack_dir)
    except PackError:
        return None


def _provenance(manifest, verified: bool) -> dict[str, Any]:
    return {
        "pack_id": manifest.pack_id,
        "fingerprint": manifest.fingerprint,
        "fingerprint_verified": verified,
        "fit_date": manifest.fit_date,
        "source_digest": manifest.source_digest,
        "sources": [
            {
                "year": source.year,
                "filename": Path(source.filename).name,
                "sha256": source.sha256,
                "row_count": source.row_count,
            }
            for source in manifest.sources
        ],
        "snapshot_years": list(manifest.snapshot_years),
        "planalign_version": manifest.planalign_version,
        "credibility_k": manifest.credibility_k,
        "min_exposure": manifest.min_exposure,
        "thresholds_moved": dict(manifest.thresholds),
        "promotion_basis": manifest.promotion_basis,
        "notes": manifest.notes,
    }


def _summary_from_manifest(manifest) -> dict[str, Any]:
    """Fallback for a pack written before ``diagnostics.json`` existed."""
    return {
        "snapshot_years": list(manifest.snapshot_years),
        "linked_employees": None,
        "fitted_count": None,
        "thin_count": None,
        "promotion_basis": manifest.promotion_basis,
        "promotion_basis_label": manifest.promotion_basis,
        "unfittable_count": len(manifest.unfittable),
        "warning_count": len(manifest.warnings),
    }


def _scorecard_payload(pack_dir: Path) -> Optional[dict[str, Any]]:
    """The scorecard as verified by ``load_scorecard``; raw JSON if it fails.

    Verdicts are derived from the comparisons on load, so a verified payload
    can never show a hand-edited verdict. A scorecard that fails verification
    is still shown for inspection, but never counts as current.
    """
    try:
        scorecard = load_scorecard(pack_dir)
    except BacktestError:
        return _read_json(pack_dir / SCORECARD_JSON)
    return scorecard.model_dump(mode="json") if scorecard is not None else None


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
