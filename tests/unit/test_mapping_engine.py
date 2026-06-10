"""Unit tests for MappingEngine — all transforms, chaining, and security.

Written BEFORE implementation (TDD). These tests MUST FAIL until mapping_engine.py exists.
"""

import pytest
import pandas as pd

from planalign_api.models.imports import FieldMapping, Transformation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mapping(input_col: str, output_col: str, transforms: list[dict]) -> FieldMapping:
    return FieldMapping(
        input_column=input_col,
        output_column=output_col,
        output_type="string",
        transformations=[Transformation(**t) for t in transforms],
    )


def _engine():
    from planalign_api.services.mapping_engine import MappingEngine

    return MappingEngine()


# ---------------------------------------------------------------------------
# Rename (output_column acts as rename; no explicit transform needed)
# ---------------------------------------------------------------------------


def test_rename_applies_output_column_name():
    engine = _engine()
    df = pd.DataFrame({"EMP_ID": ["E001", "E002"]})
    mappings = [_mapping("EMP_ID", "employee_id", [])]
    result = engine.apply(df, mappings)
    assert "employee_id" in result.columns
    assert "EMP_ID" not in result.columns


# ---------------------------------------------------------------------------
# string_case
# ---------------------------------------------------------------------------


def test_string_case_upper():
    engine = _engine()
    df = pd.DataFrame({"DEPT": ["engineering", "finance"]})
    mappings = [
        _mapping(
            "DEPT",
            "department",
            [{"transform_type": "string_case", "params": {"case": "upper"}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["department"]) == ["ENGINEERING", "FINANCE"]


def test_string_case_lower():
    engine = _engine()
    df = pd.DataFrame({"DEPT": ["Engineering", "Finance"]})
    mappings = [
        _mapping(
            "DEPT",
            "department",
            [{"transform_type": "string_case", "params": {"case": "lower"}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["department"]) == ["engineering", "finance"]


def test_string_case_title():
    engine = _engine()
    df = pd.DataFrame({"DEPT": ["ENGINEERING", "FINANCE"]})
    mappings = [
        _mapping(
            "DEPT",
            "department",
            [{"transform_type": "string_case", "params": {"case": "title"}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["department"]) == ["Engineering", "Finance"]


# ---------------------------------------------------------------------------
# date_parse
# ---------------------------------------------------------------------------


def test_date_parse_valid_format():
    engine = _engine()
    df = pd.DataFrame({"HIRE_DATE": ["01/15/2020", "03/22/2021"]})
    mappings = [
        _mapping(
            "HIRE_DATE",
            "hire_date",
            [{"transform_type": "date_parse", "params": {"format": "%m/%d/%Y"}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert result["hire_date"].notna().all()


def test_date_parse_invalid_values_coerced_to_null():
    engine = _engine()
    df = pd.DataFrame({"HIRE_DATE": ["01/15/2020", "not-a-date", "13/45/2020"]})
    mappings = [
        _mapping(
            "HIRE_DATE",
            "hire_date",
            [{"transform_type": "date_parse", "params": {"format": "%m/%d/%Y"}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert pd.isna(result["hire_date"].iloc[1])
    assert pd.isna(result["hire_date"].iloc[2])
    assert result["hire_date"].notna().sum() == 1


# ---------------------------------------------------------------------------
# null_replace
# ---------------------------------------------------------------------------


def test_null_replace_fills_nulls():
    engine = _engine()
    df = pd.DataFrame({"SALARY": [50000.0, None, 70000.0]})
    mappings = [
        _mapping(
            "SALARY",
            "salary",
            [{"transform_type": "null_replace", "params": {"value": 0}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["salary"]) == [50000.0, 0, 70000.0]


# ---------------------------------------------------------------------------
# null_drop
# ---------------------------------------------------------------------------


def test_null_drop_removes_null_rows():
    engine = _engine()
    df = pd.DataFrame({"SALARY": [50000.0, None, 70000.0]})
    mappings = [
        _mapping("SALARY", "salary", [{"transform_type": "null_drop", "params": {}}])
    ]
    result = engine.apply(df, mappings)
    assert len(result) == 2
    assert result["salary"].notna().all()


# ---------------------------------------------------------------------------
# calculated_field
# ---------------------------------------------------------------------------


def test_calculated_field_string_concat():
    engine = _engine()
    df = pd.DataFrame({"FIRST": ["John", "Jane"], "LAST": ["Doe", "Smith"]})
    mappings = [
        _mapping(
            "FIRST",
            "full_name",
            [
                {
                    "transform_type": "calculated_field",
                    "params": {"expression": "FIRST + ' ' + LAST"},
                }
            ],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["full_name"]) == ["John Doe", "Jane Smith"]


def test_calculated_field_arithmetic():
    engine = _engine()
    df = pd.DataFrame({"BASE": [100.0, 200.0], "BONUS": [10.0, 20.0]})
    mappings = [
        _mapping(
            "BASE",
            "total",
            [
                {
                    "transform_type": "calculated_field",
                    "params": {"expression": "BASE + BONUS"},
                }
            ],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["total"]) == [110.0, 220.0]


# ---------------------------------------------------------------------------
# Chaining
# ---------------------------------------------------------------------------


def test_chain_case_then_null_replace():
    engine = _engine()
    df = pd.DataFrame({"DEPT": [None, "engineering"]})
    mappings = [
        _mapping(
            "DEPT",
            "department",
            [
                {"transform_type": "string_case", "params": {"case": "upper"}},
                {"transform_type": "null_replace", "params": {"value": "UNKNOWN"}},
            ],
        )
    ]
    result = engine.apply(df, mappings)
    assert result["department"].iloc[0] == "UNKNOWN"
    assert result["department"].iloc[1] == "ENGINEERING"


# ---------------------------------------------------------------------------
# Security: reject dangerous expressions in calculated_field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dangerous_expr",
    [
        "__import__('os').system('rm -rf /')",
        "exec('print(1)')",
        "eval('1+1')",
        "open('/etc/passwd').read()",
        "os.listdir('.')",
        "__builtins__",
    ],
)
def test_calculated_field_rejects_dangerous_expressions(dangerous_expr: str):
    engine = _engine()
    df = pd.DataFrame({"A": [1, 2]})
    mappings = [
        _mapping(
            "A",
            "b",
            [
                {
                    "transform_type": "calculated_field",
                    "params": {"expression": dangerous_expr},
                }
            ],
        )
    ]
    with pytest.raises(ValueError, match=r"(unsafe|forbidden|not allowed|blocked)"):
        engine.apply(df, mappings)
