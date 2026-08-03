"""Fast tests for additive ensemble provenance stored with aggregates."""

from __future__ import annotations

import json

import duckdb
import pytest

from planalign_ensemble.planner import plan_ensemble
from planalign_ensemble.models import EnsembleSpec
from planalign_ensemble.provenance import write_ensemble_provenance


@pytest.mark.fast
def test_ensemble_provenance_uses_additive_run_metadata_columns(tmp_path) -> None:
    """Aggregate provenance retains ordered seeds and immutable member paths."""
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="baseline",
            seed_count=2,
            start_year=2025,
            end_year=2026,
        ),
        output_root=tmp_path,
        config_fingerprint="same-config",
    )

    write_ensemble_provenance(plan)

    with duckdb.connect(str(plan.ensemble_db_path), read_only=True) as conn:
        row = conn.execute(
            "SELECT ensemble_id, ensemble_seed_list, ensemble_seed_count, "
            "ensemble_role, ensemble_member_paths, config_fingerprint "
            "FROM run_metadata"
        ).fetchone()

    assert row is not None
    assert row[0] == plan.ensemble_id
    assert json.loads(row[1]) == list(plan.seeds)
    assert row[2] == 2
    assert row[3] == "headline"
    assert json.loads(row[4]) == [str(path) for path in plan.seed_db_paths.values()]
    assert row[5] == "same-config"
