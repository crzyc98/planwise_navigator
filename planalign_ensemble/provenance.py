"""Append-only ensemble provenance stored beside aggregate distributions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Literal

import duckdb

from _version import __version__
from planalign_orchestrator.run_metadata import (
    RUN_METADATA_TABLE,
    _CREATE_TABLE_SQL,
    _evolve_provenance_schema,
)

from .models import SeedPlan, Subsystem


EnsembleRole = Literal["headline", "attribution_frozen", "attribution_baseline"]


def write_ensemble_provenance(
    plan: SeedPlan,
    *,
    role: EnsembleRole = "headline",
    frozen_subsystem: Subsystem | None = None,
) -> None:
    """Append the aggregate's seed lineage to its dedicated ensemble database."""
    if role == "attribution_frozen" and frozen_subsystem is None:
        raise ValueError(
            "frozen_subsystem is required for attribution_frozen provenance"
        )
    if role != "attribution_frozen" and frozen_subsystem is not None:
        raise ValueError("frozen_subsystem is only valid for attribution_frozen")
    plan.ensemble_db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(plan.ensemble_db_path)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        _evolve_provenance_schema(conn)
        conn.execute(
            f"""
            INSERT INTO {RUN_METADATA_TABLE} (
                run_id, run_timestamp, run_type, config_fingerprint, random_seed,
                start_year, end_year, scenario_id, plan_design_id,
                planalign_version, full_reset, ensemble_id, ensemble_seed_list,
                ensemble_seed_count, ensemble_role, ensemble_frozen_subsystem,
                ensemble_member_paths
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                datetime.now(timezone.utc),
                "simulate",
                plan.config_fingerprint,
                None,
                plan.spec.start_year,
                plan.spec.end_year,
                plan.scenario_id,
                None,
                __version__,
                False,
                plan.ensemble_id,
                json.dumps(list(plan.seeds), separators=(",", ":")),
                len(plan.seeds),
                role,
                frozen_subsystem.value if frozen_subsystem is not None else None,
                json.dumps(
                    [str(path) for path in plan.seed_db_paths.values()],
                    separators=(",", ":"),
                ),
            ],
        )


__all__ = ["EnsembleRole", "write_ensemble_provenance"]
