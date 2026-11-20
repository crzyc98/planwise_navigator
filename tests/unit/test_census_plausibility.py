"""Cross-field census plausibility rules (#1260), on a small synthetic census."""

from pathlib import Path
from typing import Iterator, Optional

import duckdb
import pytest

from planalign_api.services.census_plausibility import (
    RULES,
    DeferralLimits,
    FlaggedRow,
    census_year_from_hires,
    count_violations,
    deferral_limits_for_year,
    flagged_rows,
)
from planalign_api.services.sql_security import SQLSecurityError

pytestmark = pytest.mark.fast

YEAR = 2025
LIMITS = DeferralLimits(elective=23500, with_catch_up=34750)

CLEAN: dict[str, Optional[str]] = {
    "employee_id": "E",
    "employee_birth_date": "1985-04-12",
    "employee_hire_date": "2015-06-01",
    "employee_termination_date": None,
    "employee_gross_compensation": "80000",
    "employee_capped_compensation": "80000",
    "employee_deferral_rate": "0.06",
    "employee_contribution": "4800",
    "pre_tax_contribution": "3000",
    "roth_contribution": "1800",
    "after_tax_contribution": "0",
    "employer_match_contribution": "2400",
    "employer_core_contribution": "1600",
}
COLUMNS = {name: name for name in CLEAN}

# Realistic rows that must not trip any rule.
EDGE_CASES: list[dict[str, Optional[str]]] = [
    # Left mid-year: part-year pay and contributions.
    {
        "employee_termination_date": "2025-06-30",
        "employee_gross_compensation": "40000",
        "employee_capped_compensation": "40000",
        "employee_contribution": "2400",
        "pre_tax_contribution": "2400",
        "roth_contribution": "0",
    },
    # Hired in December: stated rate, nothing deferred yet.
    {
        "employee_hire_date": "2025-12-15",
        "employee_gross_compensation": "2000",
        "employee_capped_compensation": "2000",
        "employee_contribution": "0",
        "pre_tax_contribution": "0",
        "roth_contribution": "0",
        "employer_match_contribution": "0",
        "employer_core_contribution": "0",
    },
    # Non-participant with blank contribution columns.
    {
        "employee_deferral_rate": "0",
        "employee_contribution": None,
        "pre_tax_contribution": None,
        "roth_contribution": None,
        "after_tax_contribution": None,
    },
    # High earner who hit the 402(g) limit before year end.
    {
        "employee_gross_compensation": "400000",
        "employee_capped_compensation": "350000",
        "employee_deferral_rate": "0.20",
        "employee_contribution": "23500",
        "pre_tax_contribution": "23500",
        "roth_contribution": "0",
    },
    # Catch-up on top of the stated rate.
    {
        "employee_birth_date": "1965-01-01",
        "employee_gross_compensation": "60000",
        "employee_capped_compensation": "60000",
        "employee_contribution": "11100",
        "pre_tax_contribution": "11100",
        "roth_contribution": "0",
    },
    # After-tax dollars on top of a maxed-out 402(g).
    {
        "employee_gross_compensation": "300000",
        "employee_capped_compensation": "300000",
        "employee_deferral_rate": "0.10",
        "employee_contribution": "30000",
        "pre_tax_contribution": "23500",
        "roth_contribution": "0",
        "after_tax_contribution": "6500",
    },
    # Large after-tax savings don't count against the stated deferral rate.
    {
        "employee_gross_compensation": "300000",
        "employee_capped_compensation": "300000",
        "employee_deferral_rate": "0.05",
        "employee_contribution": "55000",
        "pre_tax_contribution": "15000",
        "roth_contribution": "0",
        "after_tax_contribution": "40000",
    },
    # October hire who elected 15% but is still in the waiting period.
    {
        "employee_hire_date": "2025-10-01",
        "employee_gross_compensation": "20000",
        "employee_capped_compensation": "20000",
        "employee_deferral_rate": "0.15",
        "employee_contribution": "0",
        "pre_tax_contribution": "0",
        "roth_contribution": "0",
        "employer_match_contribution": "0",
        "employer_core_contribution": "0",
    },
    # Unparseable values are left to the single-column checks.
    {"employee_birth_date": "not a date", "employee_contribution": "$4,800"},
]

BAD_ROWS: dict[str, dict[str, Optional[str]]] = {
    "compensation_not_positive": {"employee_gross_compensation": "0"},
    "deferral_rate_out_of_range": {"employee_deferral_rate": "6"},
    **{
        f"negative_{column}": {column: "-1"}
        for column in (
            "employee_contribution",
            "pre_tax_contribution",
            "roth_contribution",
            "after_tax_contribution",
            "employer_match_contribution",
            "employer_core_contribution",
        )
    },
    "employee_contribution_above_pay": {"employee_contribution": "90000"},
    "pre_tax_contribution_above_pay": {"pre_tax_contribution": "90000"},
    "roth_contribution_above_pay": {"roth_contribution": "90000"},
    "after_tax_contribution_above_pay": {"after_tax_contribution": "90000"},
    "contribution_sources_above_pay": {
        "pre_tax_contribution": "50000",
        "roth_contribution": "40000",
    },
    "employer_match_contribution_above_pay": {"employer_match_contribution": "90000"},
    "employer_core_contribution_above_pay": {"employer_core_contribution": "90000"},
    "employee_capped_compensation_above_pay": {"employee_capped_compensation": "90000"},
    "birth_on_or_after_hire": {"employee_birth_date": "2015-06-01"},
    "termination_before_hire": {"employee_termination_date": "2014-01-01"},
    "hire_date_after_census_year": {"employee_hire_date": "2026-03-01"},
    "birth_date_after_census_year": {"employee_birth_date": "2026-01-01"},
    "hired_under_age_14": {"employee_birth_date": "2005-01-01"},
    "age_over_100": {"employee_birth_date": "1920-01-01"},
    "deferral_rate_mismatch": {
        "employee_contribution": "20000",
        "pre_tax_contribution": "20000",
        "roth_contribution": "0",
    },
    "contribution_split_mismatch": {
        "pre_tax_contribution": "1000",
        "roth_contribution": "1000",
    },
    "contributions_above_irs_limit": {
        "employee_gross_compensation": "400000",
        "employee_capped_compensation": "350000",
        "employee_deferral_rate": "0.10",
        "employee_contribution": "40000",
        "pre_tax_contribution": "40000",
        "roth_contribution": "0",
    },
    "compensation_outlier": {"employee_gross_compensation": "10000000"},
}


@pytest.fixture
def conn() -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


def _load(
    conn: duckdb.DuckDBPyConnection, overrides: list[dict], clean_rows: int = 100
) -> None:
    """Load ``clean_rows`` clean rows, then one row per override."""
    rows = [dict(CLEAN) for _ in range(clean_rows)]
    rows += [{**CLEAN, **o} for o in overrides]
    for index, row in enumerate(rows):
        row["employee_id"] = f"E{index:04d}"
    names = list(CLEAN)
    conn.execute(f"CREATE TABLE census ({', '.join(f'{n} VARCHAR' for n in names)})")
    conn.executemany(
        f"INSERT INTO census VALUES ({', '.join('?' for _ in names)})",
        [[row[n] for n in names] for row in rows],
    )


def _counts(
    conn: duckdb.DuckDBPyConnection,
    columns: dict[str, str] = COLUMNS,
    limits: Optional[DeferralLimits] = LIMITS,
) -> dict[str, int]:
    return {
        r.rule.rule_id: r.count
        for r in count_violations(conn, "census", columns, YEAR, limits)
    }


def test_every_rule_has_a_bad_row_case() -> None:
    assert sorted(BAD_ROWS) == sorted(rule.rule_id for rule in RULES)
    assert len({rule.rule_id for rule in RULES}) == len(RULES)


def test_clean_census_runs_every_rule_and_flags_nothing(conn) -> None:
    _load(conn, EDGE_CASES)

    assert _counts(conn) == {rule.rule_id: 0 for rule in RULES}
    assert flagged_rows(conn, "census", COLUMNS, YEAR, LIMITS) == []


@pytest.mark.parametrize("rule_id", sorted(BAD_ROWS))
def test_rule_flags_bad_row(conn, rule_id: str) -> None:
    _load(conn, [BAD_ROWS[rule_id]])

    assert _counts(conn)[rule_id] == 1


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.rule_id)
def test_rule_skipped_when_a_required_column_is_missing(conn, rule) -> None:
    _load(conn, [BAD_ROWS[rule.rule_id]])

    for column in rule.columns:
        columns = {k: v for k, v in COLUMNS.items() if k != column}
        assert rule.rule_id not in _counts(conn, columns)
    if rule.any_columns:
        columns = {k: v for k, v in COLUMNS.items() if k not in rule.any_columns}
        assert rule.rule_id not in _counts(conn, columns)


def test_source_rules_run_on_a_pre_tax_only_census(conn) -> None:
    _load(conn, [{"pre_tax_contribution": "500000"}])
    columns = {
        k: v
        for k, v in COLUMNS.items()
        if k not in ("roth_contribution", "after_tax_contribution")
    }

    counts = _counts(conn, columns)

    assert counts["pre_tax_contribution_above_pay"] == 1
    assert counts["contribution_sources_above_pay"] == 1
    assert "roth_contribution_above_pay" not in counts


def test_split_rule_runs_with_one_source_column(conn) -> None:
    _load(conn, [{"pre_tax_contribution": "1000"}], clean_rows=0)
    columns = {
        k: v
        for k, v in COLUMNS.items()
        if k not in ("roth_contribution", "after_tax_contribution")
    }

    # Clean rows would mismatch too (Roth isn't mapped), so load only one.
    assert _counts(conn, columns)["contribution_split_mismatch"] == 1


@pytest.mark.parametrize(
    "clean_rows, bad_rows", [(49, 1), (197, 3)], ids=["50-row-file", "1.5pct-bad"]
)
def test_compensation_outlier_in_small_or_heavily_affected_files(
    conn, clean_rows: int, bad_rows: int
) -> None:
    # Pay keyed in cents instead of dollars.
    bad = {"employee_gross_compensation": "8000000"}
    _load(conn, [bad] * bad_rows, clean_rows=clean_rows)

    assert _counts(conn)["compensation_outlier"] == bad_rows


def test_deferral_rate_mismatch_ignores_under_contribution(conn) -> None:
    _load(
        conn,
        [
            {"employee_deferral_rate": "0.50", "employee_contribution": "0"},
            {"employee_deferral_rate": "0.15", "employee_contribution": "100"},
        ],
    )

    assert _counts(conn)["deferral_rate_mismatch"] == 0


@pytest.mark.parametrize(
    "rule_id",
    ["termination_before_hire", "employee_capped_compensation_above_pay"],
)
def test_rules_with_legitimate_explanations_are_warnings(rule_id: str) -> None:
    rule = next(r for r in RULES if r.rule_id == rule_id)

    assert (rule.severity, rule.issue_type) == ("warning", "implausible_value")


@pytest.mark.parametrize(
    "rule_id", [rule.rule_id for rule in RULES if rule.needs_limits]
)
def test_limit_rules_skipped_without_limits(conn, rule_id: str) -> None:
    _load(conn, [BAD_ROWS[rule_id]])

    counts = _counts(conn, limits=None)

    assert rule_id not in counts
    assert "compensation_not_positive" in counts


def test_optional_column_may_be_absent(conn) -> None:
    _load(conn, [BAD_ROWS["contribution_sources_above_pay"]])
    columns = {k: v for k, v in COLUMNS.items() if k != "after_tax_contribution"}

    assert _counts(conn, columns)["contribution_sources_above_pay"] == 1


def test_mapping_uses_actual_column_names(conn) -> None:
    conn.execute(
        "CREATE TABLE raw AS SELECT '2016-01-01' AS dob, '2015-06-01' AS hire_date"
    )
    columns = {"employee_birth_date": "dob", "employee_hire_date": "hire_date"}

    results = count_violations(conn, "raw", columns, YEAR)

    assert {r.rule.rule_id: r.count for r in results}["birth_on_or_after_hire"] == 1


def test_flagged_rows_list_ids_and_every_broken_rule(conn) -> None:
    _load(conn, [{"employee_contribution": "90000"}, {}])

    assert flagged_rows(conn, "census", COLUMNS, YEAR, LIMITS) == [
        FlaggedRow(
            row_number=101,
            employee_id="E0100",
            rule_ids=(
                "employee_contribution_above_pay",
                "deferral_rate_mismatch",
                "contribution_split_mismatch",
                "contributions_above_irs_limit",
            ),
        )
    ]


def test_flagged_rows_without_id_column(conn) -> None:
    _load(conn, [{"employee_birth_date": "1920-01-01"}])
    columns = {k: v for k, v in COLUMNS.items() if k != "employee_id"}

    (row,) = flagged_rows(conn, "census", columns, YEAR)

    assert (row.row_number, row.employee_id, row.rule_ids) == (
        101,
        None,
        ("age_over_100",),
    )


def test_no_applicable_rules_returns_empty(conn) -> None:
    conn.execute("CREATE TABLE census AS SELECT 'E1' AS employee_id")
    columns = {"employee_id": "employee_id"}

    assert count_violations(conn, "census", columns, YEAR) == []
    assert flagged_rows(conn, "census", columns, YEAR) == []


@pytest.mark.parametrize(
    "columns, relation",
    [
        ({"employee_gross_compensation": "pay; DROP TABLE census"}, "census"),
        ({"employee_gross_compensation": "pay"}, "census; DROP TABLE census"),
    ],
)
def test_unsafe_identifiers_are_rejected(conn, columns, relation) -> None:
    with pytest.raises(SQLSecurityError):
        count_violations(conn, relation, columns, YEAR)


def test_messages_carry_counts_only() -> None:
    rule = next(r for r in RULES if r.rule_id == "termination_before_hire")

    assert rule.format_message(3) == (
        "3 row(s) have a termination date before the hire date. "
        "Rehires who still carry an old termination date cause this."
    )


def test_census_year_ignores_a_few_future_hire_dates(conn) -> None:
    rows = [("2015-03-01",)] * 150 + [("2014-06-01",)] * 150 + [("2052-01-01",)]
    conn.execute("CREATE TABLE census (hire VARCHAR)")
    conn.executemany("INSERT INTO census VALUES (?)", rows)

    assert census_year_from_hires(conn, "census", "hire") == 2015


def test_census_year_none_without_parseable_hires(conn) -> None:
    conn.execute("CREATE TABLE census AS SELECT 'soon' AS hire")

    assert census_year_from_hires(conn, "census", "hire") is None


def test_deferral_limits_read_from_seed() -> None:
    assert deferral_limits_for_year(2025) == DeferralLimits(
        elective=23500, with_catch_up=34750
    )


def test_deferral_limits_outside_seed_use_nearest_year() -> None:
    assert deferral_limits_for_year(2023) == deferral_limits_for_year(2024)
    assert deferral_limits_for_year(1999) == DeferralLimits(
        elective=23000, with_catch_up=30500
    )
    assert deferral_limits_for_year(2200) is not None


def test_deferral_limits_missing_seed(tmp_path: Path) -> None:
    assert deferral_limits_for_year(2025, tmp_path / "missing.csv") is None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "limit_year,base_limit\n2025,23500\n",
        "limit_year\nnot-a-year\n",
        "limit_year,base_limit,catch_up_limit,super_catch_up_limit\n2025,23500\n",
    ],
    ids=["empty", "missing-columns", "bad-year", "short-row"],
)
def test_deferral_limits_unreadable_seed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    seed = tmp_path / "seed.csv"
    seed.write_text(content)

    assert deferral_limits_for_year(2025, seed) is None
    assert "IRS limits seed unreadable" in caplog.text
