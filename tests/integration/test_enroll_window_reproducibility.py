"""Feature 101 follow-up (issue #336, item 2 / spec T018).

Reproducibility double-run: the same scenario built twice with the same
random seed must produce byte-for-byte identical contribution and match
outputs (FR-009 determinism).

This is an expensive end-to-end check — it runs two full multi-year
simulations into two isolated DuckDB databases — so it is marked `slow`
(excluded from the CI `pytest -m "not slow"` lane) AND gated behind the
`RUN_REPRODUCIBILITY=1` environment variable so a normal local `pytest`
run does not pay the cost. Run it deliberately:

    RUN_REPRODUCIBILITY=1 pytest tests/integration/test_enroll_window_reproducibility.py -v
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest
import yaml

from planalign_orchestrator.config import load_simulation_config

pytestmark = [
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("RUN_REPRODUCIBILITY"),
        reason="Expensive double-run E2E; set RUN_REPRODUCIBILITY=1 to enable.",
    ),
]

START_YEAR = 2025
END_YEAR = 2026  # two years — enough to exercise cross-year state, kept short for cost

# Tables whose row-for-row identity proves contribution/match determinism.
OUTPUT_TABLES = (
    "int_employee_contributions",
    "fct_employer_match_events",
)

# Audit columns that legitimately differ between runs (wall-clock timestamps,
# generated ids) and must be excluded from the determinism fingerprint.
NON_DETERMINISTIC_COL = re.compile(
    r"(_at$|created|calculated|timestamp|uuid|run_id|loaded)", re.IGNORECASE
)


def _write_short_config(tmp_path: Path) -> Path:
    """Derive a 2-year, fixed-seed config from the base simulation config."""
    cfg = load_simulation_config("config/simulation_config.yaml")
    cfg.simulation.start_year = START_YEAR
    cfg.simulation.end_year = END_YEAR
    cfg.simulation.random_seed = 100
    out = tmp_path / "repro_config.yaml"
    out.write_text(yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False))
    return out


def _run_simulation(config_path: Path, db_path: Path) -> None:
    """Run one isolated simulation into db_path via the CLI (faithful E2E path)."""
    env = {**os.environ, "DATABASE_PATH": str(db_path)}
    # Ensure the sqlparse token fix is installed before dbt subprocesses run.
    subprocess.run(
        [sys.executable, "-c", "import planalign_orchestrator"],
        check=True,
        env=env,
    )
    result = subprocess.run(
        [
            "planalign",
            "simulate",
            f"{START_YEAR}-{END_YEAR}",
            "--config",
            str(config_path),
            "--database",
            str(db_path),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Simulation failed for {db_path}:\n{result.stdout[-3000:]}\n{result.stderr[-2000:]}"


def _table_fingerprint(db_path: Path, table: str) -> str:
    """Order-independent content hash of a table's rows."""
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        cols = [
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY column_name",
                [table],
            ).fetchall()
            if not NON_DETERMINISTIC_COL.search(r[0])
        ]
        assert cols, f"Table {table!r} not found in {db_path}"
        col_list = ", ".join(f'"{c}"' for c in cols)
        # Deterministic order so the hash is independent of row return order.
        rows = conn.execute(
            f"SELECT {col_list} FROM {table} ORDER BY {col_list}"
        ).fetchall()
    finally:
        conn.close()
    digest = hashlib.sha256()
    digest.update(repr(rows).encode("utf-8"))
    return digest.hexdigest()


def test_same_seed_produces_identical_contribution_and_match_outputs(tmp_path):
    config_path = _write_short_config(tmp_path)
    db_a = tmp_path / "run_a.duckdb"
    db_b = tmp_path / "run_b.duckdb"

    _run_simulation(config_path, db_a)
    _run_simulation(config_path, db_b)

    mismatches = []
    for table in OUTPUT_TABLES:
        fp_a = _table_fingerprint(db_a, table)
        fp_b = _table_fingerprint(db_b, table)
        if fp_a != fp_b:
            mismatches.append(f"{table}: {fp_a[:12]} != {fp_b[:12]}")

    assert (
        not mismatches
    ), "Non-deterministic outputs across same-seed runs: " + "; ".join(mismatches)
