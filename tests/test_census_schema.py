"""Unit tests for census_schema — canonical field definitions."""

import pytest

from planalign_api.services.census_schema import (
    CANONICAL_NAMES,
    FIELDS,
    get_field,
    get_required_fields,
    is_canonical,
)

pytestmark = pytest.mark.fast

REQUIRED_FIELD_NAMES = {
    "employee_id",
    "employee_birth_date",
    "employee_hire_date",
    "employee_gross_compensation",
    "active",
}


def test_field_count():
    assert len(FIELDS) == 16


def test_exactly_five_required_fields():
    required = {f.field_name for f in FIELDS if f.required}
    assert required == REQUIRED_FIELD_NAMES


def test_is_canonical_true_for_all_fields():
    for f in FIELDS:
        assert is_canonical(f.field_name), f"{f.field_name} should be canonical"


def test_is_canonical_false_for_free_form_names():
    assert not is_canonical("salary")
    assert not is_canonical("EmpID")
    assert not is_canonical("hire date")
    assert not is_canonical("custom_field")
    assert not is_canonical("")


def test_get_field_returns_correct_definition():
    field = get_field("employee_hire_date")
    assert field is not None
    assert field.required is True
    assert field.data_type == "date"
    assert "hire" in field.description.lower()


def test_get_field_returns_none_for_unknown():
    assert get_field("nonexistent_field") is None
    assert get_field("salary") is None


def test_get_required_fields_returns_five():
    required = get_required_fields()
    assert len(required) == 5
    assert set(required) == REQUIRED_FIELD_NAMES


def test_canonical_names_frozenset_contains_all_field_names():
    for f in FIELDS:
        assert f.field_name in CANONICAL_NAMES


def test_canonical_names_count():
    assert len(CANONICAL_NAMES) == 16


def test_all_fields_have_aliases():
    for f in FIELDS:
        assert isinstance(f.aliases, tuple), f"{f.field_name} aliases must be a tuple"


def test_all_fields_are_frozen():
    field = get_field("employee_id")
    assert field is not None
    with pytest.raises((AttributeError, TypeError)):
        field.field_name = "changed"  # type: ignore[misc]


def test_data_types_are_valid():
    valid_types = {"string", "date", "decimal", "boolean"}
    for f in FIELDS:
        assert (
            f.data_type in valid_types
        ), f"{f.field_name} has invalid data_type {f.data_type!r}"


def test_required_fields_have_date_and_decimal_and_boolean_and_string():
    required = {f.field_name: f for f in FIELDS if f.required}
    assert required["employee_id"].data_type == "string"
    assert required["employee_birth_date"].data_type == "date"
    assert required["employee_hire_date"].data_type == "date"
    assert required["employee_gross_compensation"].data_type == "decimal"
    assert required["active"].data_type == "boolean"
