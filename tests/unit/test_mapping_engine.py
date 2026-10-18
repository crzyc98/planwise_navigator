"""Unit tests for MappingEngine — all transforms, chaining, and security.

Written BEFORE implementation (TDD). These tests MUST FAIL until mapping_engine.py exists.
"""

import pytest
import pandas as pd

from planalign_api.models.imports import FieldMapping, Transformation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mapping(
    input_col: str,
    output_col: str,
    transforms: list[dict],
    *,
    output_type: str = "string",
) -> FieldMapping:
    return FieldMapping(
        input_column=input_col,
        output_column=output_col,
        output_type=output_type,
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


def test_employee_id_is_trimmed():
    engine = _engine()
    df = pd.DataFrame({"EMP_ID": [" E001 ", 2002]})
    mappings = [_mapping("EMP_ID", "employee_id", [])]

    result = engine.apply(df, mappings)

    assert result["employee_id"].tolist() == ["E001", "2002"]


def test_blank_employee_id_is_rejected():
    engine = _engine()
    df = pd.DataFrame({"EMP_ID": ["E001", " ", None]})
    mappings = [_mapping("EMP_ID", "employee_id", [])]

    with pytest.raises(ValueError, match="2 blank or null employee ID"):
        engine.apply(df, mappings)


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


def test_date_output_rejects_unparseable_source_values():
    engine = _engine()
    df = pd.DataFrame({"HIRE_DATE": ["2020-01-15", "not-a-date"]})
    mappings = [
        _mapping(
            "HIRE_DATE",
            "employee_hire_date",
            [{"transform_type": "date_parse", "params": {"format": "%Y-%m-%d"}}],
            output_type="date",
        )
    ]

    with pytest.raises(ValueError, match="cannot be parsed as a date") as exc_info:
        engine.apply(df, mappings)

    assert "'not-a-date'" in str(exc_info.value)


def test_date_output_is_saved_as_date_values():
    engine = _engine()
    df = pd.DataFrame({"HIRE_DATE": ["2020-01-15", None]})
    mappings = [_mapping("HIRE_DATE", "employee_hire_date", [], output_type="date")]

    result = engine.apply(df, mappings)

    assert str(result["employee_hire_date"].iloc[0]) == "2020-01-15"
    assert pd.isna(result["employee_hire_date"].iloc[1])


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


def test_decimal_output_normalizes_currency_values():
    engine = _engine()
    df = pd.DataFrame({"SALARY": ["$75,000.50", "(1,250.25)", None]})
    mappings = [
        _mapping("SALARY", "employee_gross_compensation", [], output_type="decimal")
    ]

    result = engine.apply(df, mappings)

    assert str(result["employee_gross_compensation"].dtype) == "Float64"
    assert result["employee_gross_compensation"].tolist() == [
        75000.5,
        -1250.25,
        pd.NA,
    ]


def test_decimal_output_rejects_unparseable_values():
    engine = _engine()
    df = pd.DataFrame({"SALARY": ["75000", "competitive"]})
    mappings = [
        _mapping("SALARY", "employee_gross_compensation", [], output_type="decimal")
    ]

    with pytest.raises(ValueError, match="cannot be parsed as a number") as exc_info:
        engine.apply(df, mappings)

    assert "'competitive'" in str(exc_info.value)


@pytest.mark.parametrize("raw", ["1.234,56", "12,5", "12,345,67"])
def test_decimal_output_rejects_invalid_comma_grouping(raw):
    mapping = _mapping(
        "SALARY", "employee_gross_compensation", [], output_type="decimal"
    )
    with pytest.raises(ValueError, match="cannot be parsed as a number"):
        _engine().apply(pd.DataFrame({"SALARY": [raw]}), [mapping])


def test_date_output_uses_one_format_for_every_row():
    mapping = _mapping("DATE", "employee_hire_date", [], output_type="date")
    result = _engine().apply(
        pd.DataFrame({"DATE": ["03/04/2020", "25/04/2020"]}), [mapping]
    )
    assert [str(value) for value in result["employee_hire_date"]] == [
        "2020-04-03",
        "2020-04-25",
    ]


def test_ambiguous_date_requires_selected_order():
    mapping = _mapping("DATE", "employee_hire_date", [], output_type="date")
    with pytest.raises(ValueError, match="ambiguous"):
        _engine().apply(pd.DataFrame({"DATE": ["03/04/2020"]}), [mapping])


def test_selected_date_order_applies_to_entire_column():
    mapping = _mapping(
        "DATE",
        "employee_hire_date",
        [{"transform_type": "date_parse", "params": {"format": "%d/%m/%Y"}}],
        output_type="date",
    )
    result = _engine().apply(
        pd.DataFrame({"DATE": ["03/04/2020", "05/06/2020"]}), [mapping]
    )
    assert [str(value) for value in result["employee_hire_date"]] == [
        "2020-04-03",
        "2020-06-05",
    ]


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
# boolean normalization
# ---------------------------------------------------------------------------


def test_boolean_output_normalizes_supported_aliases():
    engine = _engine()
    df = pd.DataFrame(
        {
            "ACTIVE": [
                1,
                0,
                1.0,
                0.0,
                "true",
                "false",
                "Y",
                "N",
                "active",
                "inactive",
                None,
            ]
        }
    )
    mappings = [_mapping("ACTIVE", "active", [], output_type="boolean")]

    result = engine.apply(df, mappings)

    assert str(result["active"].dtype) == "boolean"
    assert result["active"].tolist() == [
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        pd.NA,
    ]


def test_boolean_output_rejects_unsupported_values():
    engine = _engine()
    df = pd.DataFrame({"ACTIVE": [1, "sometimes", "unknown"]})
    mappings = [_mapping("ACTIVE", "active", [], output_type="boolean")]

    with pytest.raises(ValueError, match="2 unsupported boolean value") as exc_info:
        engine.apply(df, mappings)

    assert "'sometimes'" in str(exc_info.value)
    assert "'unknown'" in str(exc_info.value)


def test_boolean_preview_warns_for_unsupported_values():
    engine = _engine()
    df = pd.DataFrame({"ACTIVE": [1, "sometimes"]})
    mappings = [_mapping("ACTIVE", "active", [], output_type="boolean")]

    _, warnings = engine.apply_preview(df, mappings)

    assert len(warnings) == 1
    assert warnings[0].input_column == "ACTIVE"
    assert warnings[0].rows_affected == 1
    assert "'sometimes'" in warnings[0].message


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
