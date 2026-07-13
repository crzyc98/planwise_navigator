#!/usr/bin/env python3
"""
Run Provenance Stamping and Config Drift Detection (Feature 109)

Stamps every simulation run's effective-config fingerprint, random seed, and
year range into an append-only ``run_metadata`` table inside the target
database, and warns (never blocks) when the database was last written under a
different configuration or seed — turning silent mixed-generation results into
a loud, actionable signal.

Contract: specs/109-config-drift-detection/contracts/run-metadata.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional

import duckdb

from _version import __version__
from planalign_orchestrator.config import to_dbt_vars

if TYPE_CHECKING:
    from planalign_orchestrator.config import SimulationConfig
    from planalign_orchestrator.utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)

RUN_METADATA_TABLE = "run_metadata"

RunType = Literal["simulate", "batch", "calibration"]

# NOTE: run_metadata must match neither the 'int_' nor 'fct_' clear patterns so
# history survives setup.clear_tables full resets (append-only audit trail).
_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {RUN_METADATA_TABLE} (
    run_id             VARCHAR   NOT NULL,
    run_timestamp      TIMESTAMP NOT NULL,
    run_type           VARCHAR   NOT NULL,
    config_fingerprint VARCHAR   NOT NULL,
    random_seed        BIGINT,
    start_year         INTEGER   NOT NULL,
    end_year           INTEGER   NOT NULL,
    scenario_id        VARCHAR,
    plan_design_id     VARCHAR,
    planalign_version  VARCHAR,
    full_reset         BOOLEAN   NOT NULL DEFAULT FALSE
)
"""

_REMEDIES = (
    "If this drift is unintentional, obtain clean results by re-running into a "
    "fresh or isolated database (e.g. planalign batch --clean, or "
    "--database <new>.duckdb), or perform a clean rerun into this database with "
    "setup.clear_tables: true and setup.clear_mode: all."
)


class DriftStatus(Enum):
    """Outcome of comparing this run's config/seed to the database's history."""

    NO_HISTORY = "no_history"
    MATCH = "match"
    DRIFT = "drift"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DriftCheckResult:
    """Result of a drift check against the target database's latest run record."""

    status: DriftStatus
    config_changed: bool
    seed_changed: bool
    prior_seed: Optional[int]
    current_seed: Optional[int]
    prior_fingerprint: Optional[str]
    current_fingerprint: str
    prior_timestamp: Optional[datetime]
    suppressed_by_full_reset: bool


def compute_config_fingerprint(config: "SimulationConfig") -> str:
    """SHA-256 hex digest of the effective, result-affecting configuration.

    Canonical JSON of ``to_dbt_vars(config)`` with ``random_seed`` removed —
    the seed is stored and compared separately so drift messages can
    distinguish a seed change from a configuration change (FR-004).
    """
    dbt_vars = dict(to_dbt_vars(config))
    dbt_vars.pop("random_seed", None)
    canonical = json.dumps(dbt_vars, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_and_record_run(
    db_manager: "DatabaseConnectionManager",
    config: "SimulationConfig",
    *,
    start_year: int,
    end_year: int,
    run_type: RunType,
    full_reset: bool = False,
    run_id: Optional[str] = None,
) -> DriftCheckResult:
    """Compare current config/seed to the latest run record, log, and append.

    Never raises for database errors (FR-005): any ``duckdb.Error`` degrades
    to a single logged note and a ``DriftStatus.UNKNOWN`` result.
    """
    authoritative_run_id = _validated_run_id(run_id)
    current_fingerprint = compute_config_fingerprint(config)
    current_seed = getattr(config.simulation, "random_seed", None)

    try:
        with db_manager.get_connection() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            prior = conn.execute(
                f"SELECT config_fingerprint, random_seed, run_timestamp "
                f"FROM {RUN_METADATA_TABLE} ORDER BY run_timestamp DESC LIMIT 1"
            ).fetchone()
            prior_fingerprint, prior_seed, prior_timestamp = (
                prior if prior is not None else (None, None, None)
            )
            result = evaluate_drift(
                prior_fingerprint,
                prior_seed,
                current_fingerprint,
                current_seed,
                full_reset=full_reset,
                prior_timestamp=prior_timestamp,
            )
            _log_result(result, run_type)
            _append_record(
                conn,
                config,
                fingerprint=current_fingerprint,
                seed=current_seed,
                start_year=start_year,
                end_year=end_year,
                run_type=run_type,
                full_reset=full_reset,
                run_id=authoritative_run_id,
            )
        return result
    except duckdb.Error as exc:
        logger.info(
            "Config drift detection skipped for this run (run metadata "
            "unavailable: %s). The simulation proceeds normally.",
            exc,
        )
        return DriftCheckResult(
            status=DriftStatus.UNKNOWN,
            config_changed=False,
            seed_changed=False,
            prior_seed=None,
            current_seed=current_seed,
            prior_fingerprint=None,
            current_fingerprint=current_fingerprint,
            prior_timestamp=None,
            suppressed_by_full_reset=False,
        )


def evaluate_drift(
    prior_fingerprint: Optional[str],
    prior_seed: Optional[int],
    current_fingerprint: str,
    current_seed: Optional[int],
    *,
    full_reset: bool = False,
    prior_timestamp: Optional[datetime] = None,
) -> DriftCheckResult:
    """Classify a fingerprint/seed pair against a prior recorded run (if any).

    Pure comparison primitive with no I/O — shared by ``check_and_record_run``
    (the write path, called with a freshly-read prior row) and read-only
    consumers that already hold prior/current fingerprints (e.g. the scenario
    config-diff view), so drift semantics live in exactly one place.
    """
    if prior_fingerprint is None:
        return DriftCheckResult(
            status=DriftStatus.NO_HISTORY,
            config_changed=False,
            seed_changed=False,
            prior_seed=None,
            current_seed=current_seed,
            prior_fingerprint=None,
            current_fingerprint=current_fingerprint,
            prior_timestamp=None,
            suppressed_by_full_reset=False,
        )

    config_changed = prior_fingerprint != current_fingerprint
    seed_changed = prior_seed != current_seed
    status = (
        DriftStatus.DRIFT if (config_changed or seed_changed) else DriftStatus.MATCH
    )
    return DriftCheckResult(
        status=status,
        config_changed=config_changed,
        seed_changed=seed_changed,
        prior_seed=prior_seed,
        current_seed=current_seed,
        prior_fingerprint=prior_fingerprint,
        current_fingerprint=current_fingerprint,
        prior_timestamp=prior_timestamp,
        suppressed_by_full_reset=full_reset and status is DriftStatus.DRIFT,
    )


def _log_result(result: DriftCheckResult, run_type: RunType) -> None:
    """Emit the drift message: warning on real drift, info otherwise, silent on match."""
    if result.status is DriftStatus.MATCH:
        return
    if result.status is DriftStatus.NO_HISTORY:
        logger.info(
            "No prior run record in this database; recording this run for "
            "future config drift detection."
        )
        return

    message = _compose_drift_message(result)
    if result.suppressed_by_full_reset:
        logger.info(
            "%s\nA full reset (setup.clear_tables: true, clear_mode: all) wipes "
            "prior results this run, so mixed-generation results are not possible.",
            message,
        )
    elif run_type == "calibration":
        logger.info(
            "%s\nCalibration runs intentionally diverge from the run that built "
            "this database (comp levers change; DC-plan tables go stale by design).",
            message,
        )
    else:
        logger.warning("%s\n%s", message, _REMEDIES)


def _compose_drift_message(result: DriftCheckResult) -> str:
    """Name what drifted (FR-004): configuration, random seed, or both."""
    changes = []
    if result.config_changed:
        prior_short = (result.prior_fingerprint or "")[:12]
        changes.append(
            f"configuration changed ({prior_short} -> "
            f"{result.current_fingerprint[:12]})"
        )
    if result.seed_changed:
        changes.append(
            f"random seed changed ({result.prior_seed} -> {result.current_seed})"
        )
    return (
        "CONFIG DRIFT DETECTED: this database was last written "
        f"{result.prior_timestamp} under a different "
        f"{'configuration and random seed' if len(changes) == 2 else ('random seed' if result.seed_changed else 'configuration')}; "
        "existing results may be mixed-generation.\n  - " + "\n  - ".join(changes)
    )


def _append_record(
    conn,
    config: "SimulationConfig",
    *,
    fingerprint: str,
    seed: Optional[int],
    start_year: int,
    end_year: int,
    run_type: RunType,
    full_reset: bool,
    run_id: str,
) -> None:
    """Append this run's record (FR-008: append-only; no update/delete exists)."""
    conn.execute(
        f"INSERT INTO {RUN_METADATA_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            run_id,
            datetime.now(timezone.utc),
            run_type,
            fingerprint,
            seed,
            start_year,
            end_year,
            config.scenario_id,
            config.plan_design_id,
            __version__,
            full_reset,
        ],
    )


def _validated_run_id(run_id: Optional[str]) -> str:
    """Use a caller's UUID exactly, retaining generated IDs for direct runs."""
    if run_id is None:
        return str(uuid.uuid4())
    try:
        parsed = uuid.UUID(run_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("run_id must be a UUID") from exc
    if str(parsed) != run_id.lower():
        raise ValueError("run_id must use canonical UUID form")
    return str(parsed)
