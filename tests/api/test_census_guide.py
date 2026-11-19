"""The Studio census guide endpoint serves census_schema.FIELDS unchanged."""

from __future__ import annotations

import pytest

from planalign_api.routers import census_guide
from planalign_api.services.census_schema import (
    CENSUS_FIELD_GROUPS,
    FIELDS,
    CensusFieldDefinition,
)

pytestmark = [pytest.mark.fast]


def test_endpoint_returns_every_field_with_its_metadata(client_factory) -> None:
    response = client_factory(None).get("/api/census/schema")

    assert response.status_code == 200
    body = response.json()
    assert [f["field_name"] for f in body["fields"]] == [f.field_name for f in FIELDS]
    for served, field in zip(body["fields"], FIELDS, strict=True):
        assert served == {
            "field_name": field.field_name,
            "label": field.display_label,
            "required": field.required,
            "data_type": field.data_type,
            "description": field.description,
            "aliases": list(field.aliases),
            "group": field.group,
            "example": field.example_value,
            "when_missing": field.when_missing,
        }
    assert [g["key"] for g in body["groups"]] == [k for k, _ in CENSUS_FIELD_GROUPS]


def test_file_rules_come_from_the_upload_code(client_factory) -> None:
    rules = client_factory(None).get("/api/census/schema").json()["file_rules"]

    assert rules["import_file_types"] == ["csv", "xlsx"]
    assert rules["import_max_mb"] == 500
    assert rules["parquet_max_mb"] == 50
    assert rules["date_formats"][0] == "YYYY-MM-DD"
    assert "yes" in rules["true_values"] and "no" in rules["false_values"]


def test_field_without_guide_metadata_gets_sensible_defaults(monkeypatch) -> None:
    bare = CensusFieldDefinition(
        field_name="hours_worked",
        required=False,
        data_type="decimal",
        description="Hours worked in the plan year",
    )
    unknown_group = CensusFieldDefinition(
        field_name="weekly_hours_flag",
        required=False,
        data_type="boolean",
        description="x",
        group="not_a_group",
    )
    monkeypatch.setattr(census_guide, "FIELDS", (bare, unknown_group))

    fields = census_guide.get_census_schema().fields

    assert fields[0].label == "Hours worked"
    assert fields[0].group == "other"
    assert fields[0].example == "0"
    assert fields[0].when_missing == ""
    assert fields[1].group == "other"
    assert fields[1].example == "true"
