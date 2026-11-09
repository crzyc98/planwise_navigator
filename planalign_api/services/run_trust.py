"""Shared read-only evaluation of latest run-metadata trust signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import duckdb

from planalign_orchestrator.run_metadata import DriftStatus, evaluate_drift
from planalign_orchestrator.run_metadata import compute_config_fingerprint
from planalign_orchestrator.config import SimulationConfig
from pydantic import ValidationError
from _version import __version__

from ..models.comparison import RunTrustResult


def evaluate_run_trust(
    rows: list[tuple[Any, ...]], *, selected_run_id: str | None = None
) -> RunTrustResult:
    """Evaluate selected identity and mixed-generation state from newest rows.

    Rows are ``run_id, timestamp, type, fingerprint, seed, full_reset, version``.
    A selected run is never silently replaced by the latest row.
    """
    if not rows:
        return RunTrustResult(available=False, run_id=selected_run_id)
    selected = (
        next((row for row in rows if str(row[0]) == selected_run_id), None)
        if selected_run_id
        else rows[0]
    )
    if selected is None:
        return RunTrustResult(available=False, run_id=selected_run_id)
    reasons: list[str] = []
    index = rows.index(selected)
    if index + 1 < len(rows) and _mixed(selected, rows[index + 1]):
        reasons.append("mixed_generation")
    return RunTrustResult(
        available=True,
        run_id=str(selected[0]),
        run_timestamp=_datetime(selected[1]),
        config_fingerprint=str(selected[3]) if selected[3] is not None else None,
        random_seed=selected[4],
        planalign_version=selected[6],
        reasons=reasons,
    )


def _mixed(latest: tuple[Any, ...], prior: tuple[Any, ...]) -> bool:
    _, _, run_type, fingerprint, seed, full_reset, _ = latest
    _, _, _, prior_fingerprint, prior_seed, _, _ = prior
    if full_reset or run_type == "calibration":
        return False
    return (
        evaluate_drift(prior_fingerprint, prior_seed, fingerprint, seed).status
        is DriftStatus.DRIFT
    )


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


__all__ = ["evaluate_run_trust"]


def read_run_trust(database_path, run_id: str | None) -> RunTrustResult:
    """Read at most the selected and prior metadata generations read-only."""
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            columns = {
                row[0]
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'main' AND table_name = 'run_metadata'"
                ).fetchall()
            }
            required = {"run_timestamp", "run_type", "config_fingerprint"}
            if not required.issubset(columns):
                return RunTrustResult(available=False, run_id=run_id)
            run_id_expression = "run_id" if "run_id" in columns else "NULL"
            seed_expression = "random_seed" if "random_seed" in columns else "NULL"
            reset_expression = "full_reset" if "full_reset" in columns else "FALSE"
            version_expression = (
                "planalign_version" if "planalign_version" in columns else "NULL"
            )
            rows = connection.execute(
                f"SELECT {run_id_expression}, run_timestamp, run_type, config_fingerprint, {seed_expression}, {reset_expression}, {version_expression} FROM run_metadata ORDER BY run_timestamp DESC"
            ).fetchall()
    except duckdb.Error:
        return RunTrustResult(available=False, run_id=run_id)
    return evaluate_run_trust(
        rows, selected_run_id=run_id if run_id != "legacy" else None
    )


def add_current_config_drift(
    trust: RunTrustResult, effective_config: dict[str, Any] | None
) -> RunTrustResult:
    """Add current seed/config mismatch reasons using comparison semantics."""
    if not trust.available or not effective_config:
        return trust
    simulation = effective_config.get("simulation")
    current_seed = (
        simulation.get("random_seed") if isinstance(simulation, dict) else None
    )
    try:
        current_fingerprint = compute_config_fingerprint(
            SimulationConfig.model_validate(effective_config)
        )
    except (ValidationError, ValueError, TypeError):
        current_fingerprint = None
    stored_fingerprint = trust.config_fingerprint or current_fingerprint or ""
    drift = evaluate_drift(
        stored_fingerprint,
        trust.random_seed,
        current_fingerprint or stored_fingerprint,
        current_seed,
    )
    reasons = list(trust.reasons)
    if current_seed is not None and drift.seed_changed:
        reasons.append("current_seed_mismatch")
    if (
        current_fingerprint is not None
        and trust.planalign_version == __version__
        and drift.config_changed
    ):
        reasons.append("current_config_mismatch")
    return trust.model_copy(update={"reasons": list(dict.fromkeys(reasons))})


__all__ = ["add_current_config_drift", "evaluate_run_trust", "read_run_trust"]
