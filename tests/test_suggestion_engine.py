"""Unit tests for suggestion_engine — scoring, format detection, DQ scan."""

from __future__ import annotations

from typing import Any

import pytest

from planalign_api.models.imports import (
    DetectedColumn,
    ImportSession,
)
from planalign_api.services.suggestion_engine import SuggestionEngine

pytestmark = pytest.mark.fast


def _col(
    name: str, samples: list[str] | None = None, null_count: int = 0
) -> DetectedColumn:
    return DetectedColumn(
        name=name,
        inferred_type="string",
        null_count=null_count,
        sample_values=samples or [],
    )


def _session(
    detected: list[DetectedColumn],
    preview_rows: list[dict[str, Any]] | None = None,
    row_count: int = 100,
) -> ImportSession:
    return ImportSession(
        workspace_id="ws-test",
        original_filename="test.csv",
        source_format="csv",
        detected_columns=detected,
        row_count=row_count,
        column_count=len(detected),
        preview_rows=preview_rows or [],
    )


engine = SuggestionEngine()


# ---------------------------------------------------------------------------
# Core matching tests
# ---------------------------------------------------------------------------


def test_high_confidence_empid_to_employee_id():
    suggestions = engine.suggest([_col("EmpID")])
    s = suggestions[0]
    assert s.suggested_canonical_field == "employee_id"
    assert s.confidence == "high"
    assert s.confidence_score >= 0.85


def test_high_confidence_exact_alias_hire_date():
    suggestions = engine.suggest([_col("Hire Date")])
    s = suggestions[0]
    assert s.suggested_canonical_field == "employee_hire_date"
    assert s.confidence == "high"


def test_low_or_no_match_q1_revenue():
    # Completely unrelated column — should not match any census field
    suggestions = engine.suggest([_col("Q1_Revenue_Forecast")])
    s = suggestions[0]
    assert s.suggested_canonical_field is None
    assert s.reason == "no_match"


def test_duplicate_canonical_target_resolved():
    # Both "EmpID" and "Employee_ID" could match employee_id — higher scorer wins
    suggestions = engine.suggest([_col("EmpID"), _col("EmployeeNumber")])
    matched = [s for s in suggestions if s.suggested_canonical_field == "employee_id"]
    assert len(matched) == 1  # only one wins


def test_salary_alias_matches_gross_compensation():
    suggestions = engine.suggest([_col("Salary")])
    s = suggestions[0]
    assert s.suggested_canonical_field == "employee_gross_compensation"
    assert s.confidence == "high"


def test_dob_matches_birth_date():
    suggestions = engine.suggest([_col("DOB")])
    s = suggestions[0]
    assert s.suggested_canonical_field == "employee_birth_date"
    assert s.confidence == "high"


def test_status_matches_active():
    suggestions = engine.suggest([_col("Status")])
    s = suggestions[0]
    assert s.suggested_canonical_field == "active"


def test_fingerprint_is_hex_64_chars():
    fp = SuggestionEngine.get_auto_fingerprint(["A", "B", "C"])
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_is_deterministic():
    fp1 = SuggestionEngine.get_auto_fingerprint(["A", "B"])
    fp2 = SuggestionEngine.get_auto_fingerprint(["A", "B"])
    assert fp1 == fp2


def test_fingerprint_differs_for_different_inputs():
    fp1 = SuggestionEngine.get_auto_fingerprint(["A", "B"])
    fp2 = SuggestionEngine.get_auto_fingerprint(["A", "C"])
    assert fp1 != fp2


def test_fingerprint_order_independent():
    fp1 = SuggestionEngine.get_auto_fingerprint(["A", "B", "C"])
    fp2 = SuggestionEngine.get_auto_fingerprint(["C", "A", "B"])
    assert fp1 == fp2


# ---------------------------------------------------------------------------
# Date format detection tests
# ---------------------------------------------------------------------------


def test_us_date_format_detected():
    col = _col("Hire Date", samples=["03/15/2018", "07/22/2019", "01/08/2021"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_hire_date")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.detected_format == "%m/%d/%Y"
    assert "2018-03-15" in result.parsed_sample_values
    assert not result.is_ambiguous


def test_iso_date_format_detected():
    col = _col("Hire Date", samples=["2018-03-15", "2019-07-22"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_hire_date")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.detected_format == "%Y-%m-%d"


def test_ambiguous_date_returns_is_ambiguous():
    # "01/05/2024" is ambiguous between %m/%d/%Y and %d/%m/%Y
    col = _col("Hire Date", samples=["01/05/2024", "02/03/2024", "03/01/2024"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_hire_date")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.is_ambiguous
    assert result.format_options is not None
    assert len(result.format_options) >= 2


def test_no_date_format_for_garbage_values():
    col = _col("Hire Date", samples=["not a date", "also not", "nope"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_hire_date")
    result = engine.detect_format(col, field_def)
    assert result is None


# ---------------------------------------------------------------------------
# Currency detection tests
# ---------------------------------------------------------------------------


def test_currency_string_detected():
    col = _col("Salary", samples=["$95,000.00", "$72,500.00", "$110,000.00"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_gross_compensation")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.detected_format == "currency_string"
    assert "95000.00" in result.parsed_sample_values[0]


def test_parenthetical_negative_stripped():
    col = _col("Salary", samples=["(1500.00)"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_gross_compensation")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.parsed_sample_values[0] == "-1500.00"


def test_plain_decimal_no_currency_detection():
    col = _col("Salary", samples=["95000.00", "72500.00"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("employee_gross_compensation")
    result = engine.detect_format(col, field_def)
    assert result is None


# ---------------------------------------------------------------------------
# Boolean detection tests
# ---------------------------------------------------------------------------


def test_yn_boolean_detected():
    col = _col("Active", samples=["Y", "N", "Y", "Y", "N"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("active")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.detected_format == "boolean_alias"
    assert "y → true" in result.parsed_sample_values[0]
    assert "n → false" in result.parsed_sample_values[0]


def test_active_terminated_boolean_detected():
    col = _col("Status", samples=["Active", "Terminated", "Active"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("active")
    result = engine.detect_format(col, field_def)
    assert result is not None
    assert result.detected_format == "boolean_alias"


def test_mixed_unrecognized_boolean_returns_none():
    col = _col("Status", samples=["Employed", "OnLeave", "Contractor"])
    from planalign_api.services.census_schema import get_field

    field_def = get_field("active")
    result = engine.detect_format(col, field_def)
    assert result is None


# ---------------------------------------------------------------------------
# Data quality scan tests
# ---------------------------------------------------------------------------


def test_duplicate_employee_id_count():
    cols = [_col("EmpID")]
    preview = [
        {"EmpID": "E001"},
        {"EmpID": "E002"},
        {"EmpID": "E001"},  # duplicate
        {"EmpID": "E001"},  # duplicate (same ID)
        {"EmpID": "E003"},
    ]
    sess = _session(cols, preview_rows=preview, row_count=5)
    suggestions = engine.suggest(cols)
    dq = engine.scan_data_quality(sess, suggestions)
    assert dq.duplicate_employee_id_count == 1  # 1 unique ID that is duplicated


def test_null_required_field_counts_from_detected_columns():
    cols = [
        _col("EmpID", null_count=0),
        _col("Hire Date", null_count=2),
        _col("DOB", null_count=0),
        _col("Salary", null_count=0),
        _col("Active", null_count=0),
    ]
    sess = _session(cols, row_count=100)
    suggestions = engine.suggest(cols)
    dq = engine.scan_data_quality(sess, suggestions)
    assert dq.null_required_field_counts.get("employee_hire_date", 0) == 2


def test_compensation_outlier_detected():
    cols = [_col("Salary")]
    preview = [
        {"Salary": "95000"},
        {"Salary": "500"},  # outlier — too low
        {"Salary": "72000"},
    ]
    sess = _session(cols, preview_rows=preview, row_count=3)
    suggestions = engine.suggest(cols)
    dq = engine.scan_data_quality(sess, suggestions)
    assert dq.compensation_outlier_count == 1


def test_no_issues_returns_zeros():
    cols = [
        _col("EmpID"),
        _col("DOB"),
        _col("Hire Date"),
        _col("Salary"),
        _col("Active"),
    ]
    preview = [
        {
            "EmpID": "E001",
            "DOB": "1980-01-01",
            "Hire Date": "2020-01-01",
            "Salary": "80000",
            "Active": "Y",
        }
    ]
    sess = _session(cols, preview_rows=preview, row_count=1)
    suggestions = engine.suggest(cols)
    dq = engine.scan_data_quality(sess, suggestions)
    assert dq.duplicate_employee_id_count == 0
    assert dq.compensation_outlier_count == 0
