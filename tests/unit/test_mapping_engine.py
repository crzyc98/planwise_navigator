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
# Security: calculated_field AST whitelist
# ---------------------------------------------------------------------------


_BYPASS_PAYLOADS = [
    # Original obvious payloads (kept as regressions)
    "__import__('os').system('rm -rf /')",
    "exec('print(1)')",
    "eval('1+1')",
    "open('/etc/passwd').read()",
    "os.listdir('.')",
    "__builtins__",
    # Attribute traversal on namespace objects
    "A.str.upper",
    "A.dtype",
    "().__class__",
    "(1).__class__.__bases__",
    "'x'.__class__",
    # Calls (direct, bound, dynamic)
    "getattr(A, 'dtype')",
    "A.sum()",
    "(lambda: 1)()",
    "(lambda x: x)(A)",
    "type(A)",
    "vars()['A']",
    # Subscripts / slicing into namespace objects
    "A.iloc[0]",
    "A.loc[0]",
    "A[0]",
    "A[:5]",
    "['A'][0]",
    # Comprehensions and generators
    "[x for x in A]",
    "{x for x in A}",
    "{k: v for k, v in A.items()}",
    "(x for x in A)",
    "[].append(1)",
    # Lambdas, walrus, f-strings
    "lambda: 1",
    "(y := 1)",
    "f'{A}'",
    # Non-documented operators
    "A % 2",
    "A // 2",
    "A ** 2",
    "A @ B",
    "A << 1",
    "A >> 1",
    "A & B",
    "A | B",
    "A ^ B",
    "~A",
    "not A",
    "A == B",
    "A != B",
    "A < B",
    "A > B",
    "A and B",
    "A or B",
    "A if A else B",
    "3j",
    "True",
    "None",
    # Structural tricks
    "A; __import__('os')",
    "import os",
    "from os import path",
    "*[1]",
    "",
    "   ",
    "(",
]


@pytest.mark.parametrize("dangerous_expr", _BYPASS_PAYLOADS)
def test_calculated_field_rejects_bypass_expressions(dangerous_expr: str):
    engine = _engine()
    df = pd.DataFrame({"A": [1, 2], "B": [10, 20]})
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
    with pytest.raises(
        ValueError, match=r"(unsafe|forbidden|not allowed|blocked|Unknown column)"
    ):
        engine.apply(df, mappings)


def test_calculated_field_rejects_non_string_expression():
    engine = _engine()
    df = pd.DataFrame({"A": [1, 2]})
    mappings = [
        _mapping(
            "A",
            "b",
            [{"transform_type": "calculated_field", "params": {"expression": 123}}],
        )
    ]
    with pytest.raises(ValueError, match=r"(unsafe|forbidden|not allowed|blocked)"):
        engine.apply(df, mappings)


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("A", [1, 2]),
        ("A + B", [11, 22]),
        ("A - B", [-9, -18]),
        ("A * B", [10, 40]),
        ("B / A", [10.0, 10.0]),
        ("-A", [-1, -2]),
        ("+B", [10, 20]),
        ("2 * A + B", [12, 24]),
        ("(A + B) / 2", [5.5, 11.0]),
        ("A + 0.5", [1.5, 2.5]),
        ("'v-' + S", ["v-x", "v-y"]),
        ("100", [100, 100]),
    ],
)
def test_calculated_field_allows_documented_forms(expr: str, expected: list[object]):
    engine = _engine()
    df = pd.DataFrame({"A": [1, 2], "B": [10, 20], "S": ["x", "y"]})
    mappings = [
        _mapping(
            "A",
            "out",
            [{"transform_type": "calculated_field", "params": {"expression": expr}}],
        )
    ]
    result = engine.apply(df, mappings)
    assert list(result["out"]) == expected


def test_calculated_field_rejects_unknown_column_reference():
    engine = _engine()
    df = pd.DataFrame({"A": [1, 2]})
    mappings = [
        _mapping(
            "A",
            "b",
            [
                {
                    "transform_type": "calculated_field",
                    "params": {"expression": "A + MISSING"},
                }
            ],
        )
    ]
    with pytest.raises(ValueError, match="not allowed|Unknown column"):
        engine.apply(df, mappings)
