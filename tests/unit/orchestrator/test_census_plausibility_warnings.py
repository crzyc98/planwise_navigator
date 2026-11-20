"""Run warnings for impossible census values in stg_census_data (#1262)."""

from typing import Iterator, Optional

import duckdb
import pytest

from planalign_core.census_plausibility import DATE_COLUMNS, RULES
from planalign_orchestrator.census_plausibility_warnings import (
    census_plausibility_warnings,
    report_census_plausibility,
)

pytestmark = pytest.mark.fast

CLEAN: dict[str, Optional[str]] = {
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
# A 2025 census: enough 2025 hires that the census year resolves to 2025.
HIRED_2025 = {"employee_hire_date": "2025-02-01", "employee_birth_date": "1990-01-01"}


def _stage(rows: list[dict[str, Optional[str]]]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    columns = ", ".join(
        f"{name} {'DATE' if name in DATE_COLUMNS else 'DOUBLE'}" for name in CLEAN
    )
    conn.execute(f"CREATE TABLE stg_census_data (employee_id VARCHAR, {columns})")
    for i, overrides in enumerate(rows):
        row = {**CLEAN, **overrides}
        conn.execute(
            f"INSERT INTO stg_census_data VALUES (?, {', '.join('?' * len(CLEAN))})",
            [f"E{i}", *(row[name] for name in CLEAN)],
        )
    return conn


Row = dict[str, Optional[str]]


def _census(*bad_rows: Row) -> list[Row]:
    clean: list[Row] = [{}] * 20
    hired: list[Row] = [dict(HIRED_2025)] * 5
    return clean + hired + list(bad_rows)


class _Sink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def log_warning(self, message: str, **kwargs: object) -> None:
        self.messages.append(message)


@pytest.fixture
def clean_conn() -> Iterator[duckdb.DuckDBPyConnection]:
    conn = _stage(_census())
    yield conn
    conn.close()


def test_clean_census_is_silent(clean_conn: duckdb.DuckDBPyConnection) -> None:
    sink = _Sink()
    assert report_census_plausibility(clean_conn, sink) == []
    assert sink.messages == []


def test_broken_rules_report_counts() -> None:
    conn = _stage(
        _census(
            {"employee_contribution": "-5", "pre_tax_contribution": "-5"},
            {"employee_contribution": "-5", "pre_tax_contribution": "-5"},
            {"employee_birth_date": "2016-01-01"},
            {"employee_termination_date": "2014-01-01"},
        )
    )
    messages = census_plausibility_warnings(conn)
    by_rule = {r.rule_id: r for r in RULES}
    assert (
        f"Census check: {by_rule['negative_employee_contribution'].format_message(2)}"
        in messages
    )
    assert (
        f"Census check: {by_rule['birth_on_or_after_hire'].format_message(1)}"
        in messages
    )
    assert (
        f"Census check: {by_rule['termination_before_hire'].format_message(1)}"
        in messages
    )


def test_rewritten_deferral_rates_are_counted_separately() -> None:
    conn = _stage(
        _census(
            # 6 (a percentage): divided by 100, then under the cap.
            {"employee_deferral_rate": "6"},
            # 95: divided by 100, then still above the cap.
            {"employee_deferral_rate": "95"},
            # 0.9: not divided, but above the cap.
            {"employee_deferral_rate": "0.9"},
            # Terminated rows never reach the macro.
            {"employee_deferral_rate": "6", "employee_termination_date": "2025-06-30"},
        )
    )
    messages = census_plausibility_warnings(conn, deferral_cap=0.75)
    assert any(
        "2 active census row(s) have a deferral rate above 1.0" in m for m in messages
    )
    assert any(
        "2 active census row(s) have a deferral rate above the plan deferral cap of 0.75"
        in m
        for m in messages
    )


def test_messages_carry_counts_not_ids() -> None:
    conn = _stage(_census({"employee_contribution": "90000"}))
    messages = census_plausibility_warnings(conn)
    assert messages
    assert not any("E25" in m for m in messages)


def test_missing_census_never_raises() -> None:
    sink = _Sink()
    with duckdb.connect() as conn:
        assert report_census_plausibility(conn, sink) == []
    assert sink.messages == []


def test_without_a_sink_warnings_go_to_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    conn = _stage(_census({"employee_birth_date": "2016-01-01"}))
    with caplog.at_level("WARNING"):
        messages = report_census_plausibility(conn, None)
    assert messages and messages[0] in caplog.text


def test_date_columns_match_census_schema() -> None:
    from planalign_api.services.census_schema import get_field

    referenced = {
        c for r in RULES for c in (*r.columns, *r.optional_columns, *r.any_columns)
    }
    schema_dates = {
        name
        for name in referenced
        if (field := get_field(name)) is not None and field.data_type == "date"
    }
    assert schema_dates == DATE_COLUMNS
