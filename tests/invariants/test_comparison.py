"""#470 regression 6: parity must compare row multisets, not sets.

RED against the prototype: existing comparisons use set-style EXCEPT /
both-direction anti-joins, which collapse duplicates — baseline (x,x,y)
vs candidate (x,y,y) have equal totals and equal distinct rows, yet they
are different tables and must fail parity.
"""

from pathlib import Path

import duckdb
import pytest

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _make_db(path: Path, rows) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE t (k VARCHAR, v INTEGER)")
        conn.executemany("INSERT INTO t VALUES (?, ?)", rows)
    return path


@pytest.fixture()
def duplicate_swap_dbs(tmp_path):
    baseline = _make_db(tmp_path / "a.duckdb", [("x", 1), ("x", 1), ("y", 2)])
    candidate = _make_db(tmp_path / "b.duckdb", [("x", 1), ("y", 2), ("y", 2)])
    return baseline, candidate


def test_equal_totals_different_multiplicities_diverge(duplicate_swap_dbs):
    from planalign_orchestrator.tools.parity import compare_table_multisets

    baseline, candidate = duplicate_swap_dbs
    result = compare_table_multisets(baseline, candidate, table="t", exclude_columns=())
    assert result.identical is False
    assert result.a_only_all == 1  # one surplus (x,1) on the baseline side
    assert result.b_only_all == 1  # one surplus (y,2) on the candidate side
    diag = {
        (d["row"]["k"], d["baseline_count"], d["candidate_count"])
        for d in result.multiplicity_diffs
    }
    assert ("x", 2, 1) in diag
    assert ("y", 1, 2) in diag


def test_identical_multisets_with_duplicates_pass(tmp_path):
    from planalign_orchestrator.tools.parity import compare_table_multisets

    rows = [("x", 1), ("x", 1), ("y", 2)]
    baseline = _make_db(tmp_path / "a.duckdb", rows)
    candidate = _make_db(tmp_path / "b.duckdb", rows)
    result = compare_table_multisets(baseline, candidate, table="t", exclude_columns=())
    assert result.identical is True
    assert result.a_only_all == 0 and result.b_only_all == 0


def test_schema_difference_reported_before_values(tmp_path):
    from planalign_orchestrator.tools.parity import compare_table_multisets

    baseline = _make_db(tmp_path / "a.duckdb", [("x", 1)])
    candidate_path = tmp_path / "b.duckdb"
    with duckdb.connect(str(candidate_path)) as conn:
        conn.execute("CREATE TABLE t (k VARCHAR, v BIGINT)")  # type differs
        conn.execute("INSERT INTO t VALUES ('x', 1)")
    result = compare_table_multisets(
        baseline, candidate_path, table="t", exclude_columns=()
    )
    assert result.identical is False
    assert result.schema_mismatch, "type change must surface as schema mismatch"
