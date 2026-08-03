"""Unit tests for the change-validation campaign's pure logic (no DB/sim needed).

The end-to-end stash/build/compare flow is exercised by `planalign validate-change`
itself; here we lock the verdict logic that decides PASS/FAIL.
"""

from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.change_validation import (
    BuildMetrics,
    ChangeValidationError,
    ScaleResult,
    ValidationResult,
    _assert_comparable_configs,
    _parse_horizon,
    compare_marts_detailed,
)
from planalign_orchestrator.state_pipeline_validation import (
    CharacterizationRecord,
    ExclusionEntry,
)


def _ok_build(count=30):
    return BuildMetrics(True, 100.0, 1200.0, count, Path("/tmp/x.duckdb"))


def test_parse_horizon():
    assert _parse_horizon("2025-2029") == (2025, 2029)
    assert _parse_horizon("2025") == (2025, 2025)
    assert _parse_horizon("  2025-2027 ") == (2025, 2027)


def test_scale_result_identical_passes():
    s = ScaleResult(
        census_label="dev",
        census_rows=7505,
        baseline=_ok_build(30),
        candidate=_ok_build(20),
        mart_diffs={
            "fct_yearly_events": (0, 0),
            "fct_workforce_snapshot": (0, 0),
            "dim_absent": ("absent", "absent"),
        },
        small_census_warning=True,
    )
    assert s.parity_ok is True
    assert s.parity_offenders == {}
    assert s.marts_compared == 2  # the two real (int,int) comparisons


def test_scale_result_mismatch_fails():
    s = ScaleResult(
        census_label="studio",
        census_rows=60040,
        baseline=_ok_build(),
        candidate=_ok_build(),
        mart_diffs={"fct_yearly_events": (27748, 0), "fct_workforce_snapshot": (0, 0)},
    )
    assert s.parity_ok is False
    assert "fct_yearly_events" in s.parity_offenders


def test_scale_result_build_failure_is_not_ok():
    failed = BuildMetrics(False, 1.0, None, None, Path("/tmp/x.duckdb"), error="boom")
    s = ScaleResult("dev", 7505, baseline=_ok_build(), candidate=failed, mart_diffs={})
    assert s.parity_ok is False


def test_validation_result_passed_requires_parity_and_shared_db_guard():
    good_scale = ScaleResult(
        "dev", 7505, _ok_build(30), _ok_build(20), {"fct_yearly_events": (0, 0)}
    )
    # Parity clean + shared DB unchanged -> PASS.
    ok = ValidationResult([good_scale], "abc", "abc")
    assert ok.passed is True and ok.shared_db_unchanged is True
    # Shared DB changed -> FAIL even with clean parity.
    tampered = ValidationResult([good_scale], "abc", "def")
    assert tampered.shared_db_unchanged is False and tampered.passed is False
    # No scales -> not a pass.
    assert ValidationResult([], "abc", "abc").passed is False


def _database(path: Path, statements: list[str]) -> Path:
    with duckdb.connect(str(path)) as connection:
        for statement in statements:
            connection.execute(statement)
    return path


def test_detailed_parity_requires_exact_schema_order_type_and_nullability(tmp_path):
    baseline = _database(
        tmp_path / "baseline.duckdb",
        ["CREATE TABLE fct_test (id INTEGER NOT NULL, amount DECIMAL(12,2))"],
    )
    candidate = _database(
        tmp_path / "candidate.duckdb",
        ["CREATE TABLE fct_test (amount DECIMAL(12,2), id BIGINT NOT NULL)"],
    )

    result = compare_marts_detailed(baseline, candidate, ["fct_test"])["fct_test"]

    assert result.status == "schema_mismatch"
    assert [column.name for column in result.baseline_schema] == ["id", "amount"]
    assert [column.name for column in result.candidate_schema] == ["amount", "id"]
    assert result.passed is False


def test_detailed_parity_distinguishes_one_sided_and_both_absent(tmp_path):
    baseline = _database(
        tmp_path / "baseline.duckdb", ["CREATE TABLE fct_only_base (id INTEGER)"]
    )
    candidate = _database(tmp_path / "candidate.duckdb", [])

    results = compare_marts_detailed(
        baseline, candidate, ["fct_only_base", "fct_absent"]
    )

    assert results["fct_only_base"].status == "missing_candidate"
    assert results["fct_only_base"].passed is False
    assert results["fct_absent"].status == "not_built_in_either"
    assert results["fct_absent"].passed is True


def test_detailed_parity_is_bidirectional_and_duplicate_preserving(tmp_path):
    baseline = _database(
        tmp_path / "baseline.duckdb",
        [
            "CREATE TABLE fct_test (id INTEGER)",
            "INSERT INTO fct_test VALUES (1), (1), (2)",
        ],
    )
    candidate = _database(
        tmp_path / "candidate.duckdb",
        [
            "CREATE TABLE fct_test (id INTEGER)",
            "INSERT INTO fct_test VALUES (1), (2), (2)",
        ],
    )

    result = compare_marts_detailed(baseline, candidate, ["fct_test"])["fct_test"]

    assert (result.baseline_minus_candidate, result.candidate_minus_baseline) == (1, 1)
    assert result.baseline_metrics.extra_duplicate_rows == 1
    assert result.candidate_metrics.extra_duplicate_rows == 1
    assert result.status == "content_mismatch"


def test_detailed_parity_applies_only_exact_relation_column_exclusions(tmp_path):
    baseline = _database(
        tmp_path / "baseline.duckdb",
        [
            "CREATE TABLE fct_test (id INTEGER, created_at TIMESTAMP)",
            "INSERT INTO fct_test VALUES (1, TIMESTAMP '2025-01-01')",
        ],
    )
    candidate = _database(
        tmp_path / "candidate.duckdb",
        [
            "CREATE TABLE fct_test (id INTEGER, created_at TIMESTAMP)",
            "INSERT INTO fct_test VALUES (1, TIMESTAMP '2025-02-01')",
        ],
    )
    exclusion = ExclusionEntry(
        relation="fct_test", column="created_at", reason="runtime timestamp"
    )

    excluded = compare_marts_detailed(
        baseline, candidate, ["fct_test"], exclusions=[exclusion]
    )["fct_test"]
    unscoped = compare_marts_detailed(
        baseline,
        candidate,
        ["fct_test"],
        exclusions=[
            ExclusionEntry(
                relation="fct_other", column="created_at", reason="other timestamp"
            )
        ],
    )["fct_test"]

    assert excluded.status == "compared" and excluded.passed
    assert [column.name for column in excluded.compared_schema] == ["id"]
    assert unscoped.status == "content_mismatch"


def test_detailed_parity_rejects_exclusion_for_unknown_column(tmp_path):
    baseline = _database(
        tmp_path / "baseline.duckdb", ["CREATE TABLE fct_test (id INTEGER)"]
    )
    candidate = _database(
        tmp_path / "candidate.duckdb", ["CREATE TABLE fct_test (id INTEGER)"]
    )

    with pytest.raises(ValueError, match="unknown column"):
        compare_marts_detailed(
            baseline,
            candidate,
            ["fct_test"],
            exclusions=[
                ExclusionEntry(
                    relation="fct_test", column="created_at", reason="timestamp"
                )
            ],
        )


# --------------------------------------------------------------------------- #
# Config-fingerprint precondition (#520)
# --------------------------------------------------------------------------- #
SHA_A = "a" * 64
SHA_B = "b" * 64


def _characterization(recorded_config_fingerprint):
    aggregate = {"mart_row_counts": {}}
    if recorded_config_fingerprint is not None:
        aggregate["recorded_config_fingerprint"] = recorded_config_fingerprint
    return CharacterizationRecord(
        baseline_id="f122-ab-test",
        code_fingerprint=SHA_A,
        normalized_config_fingerprint=SHA_A,
        census_fingerprint=SHA_A,
        seed_fingerprint=SHA_A,
        construction_fingerprint=SHA_A,
        database_fingerprint=SHA_A,
        horizon=(2025, 2029),
        census_rows=60040,
        aggregate=aggregate,
    )


def _database_with_config(path: Path, fingerprint) -> Path:
    statements = [
        "CREATE TABLE run_metadata (run_timestamp TIMESTAMP, config_fingerprint VARCHAR)"
    ]
    if fingerprint is not None:
        statements.append(
            "INSERT INTO run_metadata VALUES "
            f"(TIMESTAMP '2026-01-01 00:00:00', '{fingerprint}')"
        )
    return _database(path, statements)


def test_matching_config_fingerprints_are_comparable(tmp_path):
    _assert_comparable_configs(
        _characterization(SHA_A),
        _database_with_config(tmp_path / "baseline.duckdb", SHA_A),
        _database_with_config(tmp_path / "candidate.duckdb", SHA_A),
    )


def test_cross_config_comparison_is_refused_not_reported_as_a_difference(tmp_path):
    """A candidate built under a different config cannot be compared at all.

    Event counts are config-dominated (#520: a 142,592-event swing from config
    alone), so the diff would be meaningless rather than merely failing.
    """
    with pytest.raises(ChangeValidationError, match="different config"):
        _assert_comparable_configs(
            _characterization(SHA_A),
            _database_with_config(tmp_path / "baseline.duckdb", SHA_A),
            _database_with_config(tmp_path / "candidate.duckdb", SHA_B),
        )


def test_baseline_built_under_a_different_config_is_also_refused(tmp_path):
    with pytest.raises(ChangeValidationError, match="baseline database"):
        _assert_comparable_configs(
            _characterization(SHA_A),
            _database_with_config(tmp_path / "baseline.duckdb", SHA_B),
            _database_with_config(tmp_path / "candidate.duckdb", SHA_A),
        )


def test_unrecorded_config_is_refused_rather_than_assumed_to_match(tmp_path):
    with pytest.raises(ChangeValidationError, match="recorded no run_metadata"):
        _assert_comparable_configs(
            _characterization(SHA_A),
            _database_with_config(tmp_path / "baseline.duckdb", SHA_A),
            _database_with_config(tmp_path / "candidate.duckdb", None),
        )


def test_missing_run_metadata_table_is_refused(tmp_path):
    with pytest.raises(ChangeValidationError, match="recorded no run_metadata"):
        _assert_comparable_configs(
            _characterization(SHA_A),
            _database_with_config(tmp_path / "baseline.duckdb", SHA_A),
            _database(tmp_path / "candidate.duckdb", []),
        )


def test_characterization_without_a_recorded_config_cannot_gate(tmp_path):
    """Pre-#520 characterizations recorded no config; there is nothing to compare."""
    _assert_comparable_configs(
        _characterization(None),
        _database(tmp_path / "baseline.duckdb", []),
        _database(tmp_path / "candidate.duckdb", []),
    )
