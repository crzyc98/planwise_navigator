"""Run warnings for impossible census values in stg_census_data (#1262)."""

from pathlib import Path
from typing import Iterator, Optional

import duckdb
import pytest

from planalign_api.services.simulation.output_parser import SimulationOutputParser
from planalign_core.census_plausibility import DATE_COLUMNS, RULES
from planalign_orchestrator import census_plausibility_warnings as module
from planalign_orchestrator.census_plausibility_warnings import (
    report_census_plausibility,
)

pytestmark = pytest.mark.fast

Row = dict[str, Optional[str]]

CLEAN: Row = {
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
HIRED_2025: Row = {
    "employee_hire_date": "2025-02-01",
    "employee_birth_date": "1990-01-01",
}


class _Sink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def log_warning(self, message: str, **kwargs: object) -> None:
        self.messages.append(message)


def _census(*bad_rows: Row) -> list[Row]:
    clean: list[Row] = [{}] * 20
    hired: list[Row] = [dict(HIRED_2025)] * 5
    return clean + hired + list(bad_rows)


@pytest.fixture
def stage(tmp_path: Path) -> Iterator:
    """Build stg_census_data plus the census parquet the run would read."""
    conns: list[duckdb.DuckDBPyConnection] = []

    def build(rows: list[Row]) -> tuple[duckdb.DuckDBPyConnection, Path]:
        conn = duckdb.connect()
        conns.append(conn)
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
        path = tmp_path / "census.parquet"
        conn.execute(f"COPY stg_census_data TO '{path}' (FORMAT PARQUET)")
        return conn, path

    yield build
    for conn in conns:
        conn.close()


def test_clean_census_is_silent(stage) -> None:
    conn, path = stage(_census())
    sink = _Sink()
    assert report_census_plausibility(conn, path, sink) is None
    assert sink.messages == []


def test_one_summary_warning_most_rows_first(stage) -> None:
    conn, path = stage(
        _census(
            {"employee_birth_date": "2016-01-01"},
            {"employee_contribution": "-5", "pre_tax_contribution": "-5"},
            {"employee_contribution": "-5", "pre_tax_contribution": "-5"},
        )
    )
    sink = _Sink()
    message = report_census_plausibility(conn, path, sink)
    assert sink.messages == [message]
    assert message == (
        "Census check: 4 plausibility rule(s) flagged census rows: "
        "negative_employee_contribution (2), negative_pre_tax_contribution (2), "
        "contribution_split_mismatch (2), birth_on_or_after_hire (1). "
        "Census Analysis lists each rule."
    )
    assert "E2" not in message


def test_summary_truncates_long_lists(stage) -> None:
    conn, path = stage(
        _census(
            {"employee_contribution": "-5", "pre_tax_contribution": "-5"},
            {"employer_match_contribution": "-1", "employer_core_contribution": "-1"},
            {"roth_contribution": "-1", "after_tax_contribution": "-1"},
            {"employee_birth_date": "2016-01-01"},
            {"employee_termination_date": "2014-01-01"},
        )
    )
    message = report_census_plausibility(conn, path, _Sink())
    assert message is not None
    broken = len(module.census_rule_counts(conn, 2025))
    assert broken > module.SUMMARY_RULE_LIMIT
    assert message.endswith(
        f"and {broken - module.SUMMARY_RULE_LIMIT} more. Census Analysis lists each rule."
    )


def test_any_failure_is_skipped_not_raised(
    stage, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    conn, path = stage(_census({"employee_birth_date": "2016-01-01"}))

    def broken_seed(year: int) -> None:
        raise TypeError("int() argument must be a string, not 'NoneType'")

    monkeypatch.setattr(module, "deferral_limits_for_year", broken_seed)
    sink = _Sink()
    with caplog.at_level("DEBUG", logger=module.__name__):
        assert report_census_plausibility(conn, path, sink) is None
    assert sink.messages == []
    shown = [r.getMessage() for r in caplog.records if r.levelname != "DEBUG"]
    assert shown == ["Census plausibility checks skipped"]
    assert all(SimulationOutputParser.classify_line(m) == "debug" for m in shown)


def test_missing_census_never_raises(tmp_path: Path) -> None:
    sink = _Sink()
    with duckdb.connect() as conn:
        assert (
            report_census_plausibility(conn, tmp_path / "missing.parquet", sink) is None
        )
        assert report_census_plausibility(conn, None, sink) is None
    assert sink.messages == []


def test_without_a_sink_the_summary_goes_to_the_log(
    stage, caplog: pytest.LogCaptureFixture
) -> None:
    conn, path = stage(_census({"employee_birth_date": "2016-01-01"}))
    with caplog.at_level("WARNING"):
        message = report_census_plausibility(conn, path, None)
    assert message and message in caplog.text


def test_summary_reads_as_a_studio_warning_not_an_error() -> None:
    message = module.summary_message([module.RuleCount(rule, 1) for rule in RULES])
    assert message is not None
    assert SimulationOutputParser.classify_line(message) == "debug"
    line = f"2026-11-20 09:39:47 [WARNING] [navigator.x] Run warning: {message}"
    assert SimulationOutputParser.classify_line(line) == "warning"


def test_detail_lines_do_not_read_as_studio_warnings() -> None:
    for rule in RULES:
        line = f"Census check detail: {rule.format_message(3)}"
        assert SimulationOutputParser.classify_line(line) == "debug", rule.rule_id


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
