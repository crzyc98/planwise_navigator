"""Integration tests for schema-aware import — suggestions endpoint and canonical enforcement."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_workspaces(tmp_path: Path):
    """Temporary workspaces root with a pre-created workspace."""
    ws_root = tmp_path / "workspaces"
    ws_root.mkdir()
    ws_dir = ws_root / "ws-test"
    ws_dir.mkdir()
    (ws_dir / "workspace.json").write_text(
        json.dumps({
            "id": "ws-test",
            "name": "Test",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        })
    )
    return ws_root


@pytest.fixture()
def client(tmp_workspaces: Path):
    """FastAPI TestClient with workspaces_root pointed at tmp dir."""
    from planalign_api.config import APISettings
    from planalign_api.main import app
    from planalign_api.routers.imports import get_import_service, get_workspace_storage
    from planalign_api.services.import_service import ImportService
    from planalign_api.storage.workspace_storage import WorkspaceStorage

    def override_import_service():
        return ImportService(workspaces_root=tmp_workspaces)

    def override_workspace_storage():
        return WorkspaceStorage(tmp_workspaces)

    app.dependency_overrides[get_import_service] = override_import_service
    app.dependency_overrides[get_workspace_storage] = override_workspace_storage
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload_csv(client: TestClient, csv_content: str, filename: str = "test.csv") -> dict:
    """Helper to upload a CSV and return the session JSON."""
    response = client.post(
        "/api/workspaces/ws-test/imports/upload",
        files={"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Suggestions endpoint (US1)
# ---------------------------------------------------------------------------


def test_suggestions_returns_200_with_suggestions(client: TestClient):
    csv = "EmpID,DOB,Hire Date,Annual Salary,Active\nE001,1980-01-01,2020-03-15,95000,Y\n"
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    resp = client.get(f"/api/workspaces/ws-test/imports/{import_id}/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["import_id"] == import_id
    assert len(data["suggestions"]) == 5
    assert len(data["canonical_schema"]) == 16


def test_suggestions_auto_maps_empid_to_employee_id(client: TestClient):
    csv = "EmpID,DOB,Hire Date,Annual Salary,Active\nE001,1980-01-01,2020-03-15,95000,Y\n"
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    resp = client.get(f"/api/workspaces/ws-test/imports/{import_id}/suggestions")
    data = resp.json()
    suggestions = {s["input_column"]: s for s in data["suggestions"]}
    assert suggestions["EmpID"]["suggested_canonical_field"] == "employee_id"
    assert suggestions["EmpID"]["confidence"] in ("high", "medium")


def test_suggestions_returns_404_for_unknown_session(client: TestClient):
    resp = client.get("/api/workspaces/ws-test/imports/nonexistent-id/suggestions")
    assert resp.status_code == 404


def test_suggestions_includes_format_detection_for_date_column(client: TestClient):
    csv = "EmpID,Hire Date\nE001,03/15/2020\nE002,07/22/2019\n"
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    resp = client.get(f"/api/workspaces/ws-test/imports/{import_id}/suggestions")
    data = resp.json()
    suggestions = {s["input_column"]: s for s in data["suggestions"]}
    hire_suggestion = suggestions.get("Hire Date", {})
    if hire_suggestion.get("suggested_canonical_field") == "employee_hire_date":
        fmt = hire_suggestion.get("format_detection")
        assert fmt is not None


def test_suggestions_data_quality_has_expected_keys(client: TestClient):
    csv = "EmpID,Hire Date,DOB,Salary,Active\nE001,2020-01-01,1980-01-01,95000,Y\n"
    session = _upload_csv(client, csv)
    resp = client.get(f"/api/workspaces/ws-test/imports/{session['import_id']}/suggestions")
    data = resp.json()
    dq = data["data_quality"]
    assert "duplicate_employee_id_count" in dq
    assert "null_required_field_counts" in dq
    assert "compensation_outlier_count" in dq


# ---------------------------------------------------------------------------
# Canonical field validation (US2)
# ---------------------------------------------------------------------------


def test_save_mapping_with_canonical_field_returns_200(client: TestClient):
    csv = "EmpID,DOB,Hire Date,Salary,Active\nE001,1980-01-01,2020-01-01,95000,Y\n"
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    mapping_payload = {"field_mappings": [
        {"input_column": "EmpID", "output_column": "employee_id", "output_type": "string",
         "is_excluded": False, "transformations": []},
        {"input_column": "DOB", "output_column": "employee_birth_date", "output_type": "date",
         "is_excluded": False, "transformations": []},
        {"input_column": "Hire Date", "output_column": "employee_hire_date", "output_type": "date",
         "is_excluded": False, "transformations": []},
        {"input_column": "Salary", "output_column": "employee_gross_compensation",
         "output_type": "decimal", "is_excluded": False, "transformations": []},
        {"input_column": "Active", "output_column": "active", "output_type": "boolean",
         "is_excluded": False, "transformations": []},
    ]}
    resp = client.put(
        f"/api/workspaces/ws-test/imports/{import_id}/mapping",
        json=mapping_payload,
    )
    assert resp.status_code == 200
    assert resp.json()["validation_errors"] == []


def test_save_mapping_with_free_form_name_returns_422(client: TestClient):
    csv = "EmpID\nE001\n"
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    mapping_payload = {"field_mappings": [
        {"input_column": "EmpID", "output_column": "my_custom_field", "output_type": "string",
         "is_excluded": False, "transformations": []},
    ]}
    resp = client.put(
        f"/api/workspaces/ws-test/imports/{import_id}/mapping",
        json=mapping_payload,
    )
    assert resp.status_code == 422
    errors = resp.json()
    # Should contain validation error about non-canonical field
    err_text = str(errors)
    assert "my_custom_field" in err_text or "not a recognized census field" in err_text


def test_generate_without_required_fields_returns_422(client: TestClient):
    csv = "EmpID\nE001\n"
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    # Save a mapping with only one field (missing required fields)
    mapping_payload = {"field_mappings": [
        {"input_column": "EmpID", "output_column": "employee_id", "output_type": "string",
         "is_excluded": False, "transformations": []},
    ]}
    client.put(f"/api/workspaces/ws-test/imports/{import_id}/mapping", json=mapping_payload)

    resp = client.post(f"/api/workspaces/ws-test/imports/{import_id}/generate")
    assert resp.status_code == 422
    assert "Required census fields" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Prior-mapping fingerprint (US4)
# ---------------------------------------------------------------------------


def test_fingerprint_file_saved_after_successful_generation(client: TestClient, tmp_workspaces: Path):
    csv = (
        "EmpID,DOB,Hire Date,Salary,Active\n"
        "E001,1980-01-01,2020-01-01,95000,Y\n"
        "E002,1975-05-15,2018-06-01,72000,Y\n"
    )
    session = _upload_csv(client, csv)
    import_id = session["import_id"]

    mapping_payload = {"field_mappings": [
        {"input_column": "EmpID", "output_column": "employee_id", "output_type": "string",
         "is_excluded": False, "transformations": []},
        {"input_column": "DOB", "output_column": "employee_birth_date", "output_type": "date",
         "is_excluded": False, "transformations": [{"transform_type": "date_parse", "params": {"format": "%Y-%m-%d"}}]},
        {"input_column": "Hire Date", "output_column": "employee_hire_date", "output_type": "date",
         "is_excluded": False, "transformations": [{"transform_type": "date_parse", "params": {"format": "%Y-%m-%d"}}]},
        {"input_column": "Salary", "output_column": "employee_gross_compensation",
         "output_type": "decimal", "is_excluded": False, "transformations": []},
        {"input_column": "Active", "output_column": "active", "output_type": "boolean",
         "is_excluded": False, "transformations": []},
    ]}
    client.put(f"/api/workspaces/ws-test/imports/{import_id}/mapping", json=mapping_payload)
    resp = client.post(f"/api/workspaces/ws-test/imports/{import_id}/generate")
    assert resp.status_code == 202

    from planalign_api.services.suggestion_engine import SuggestionEngine
    fp = SuggestionEngine.get_auto_fingerprint(["EmpID", "DOB", "Hire Date", "Salary", "Active"])
    auto_path = tmp_workspaces / "ws-test" / "templates" / "imports" / f"_auto_{fp}.json"
    assert auto_path.exists(), f"Fingerprint file not found at {auto_path}"


def test_second_upload_same_headers_gets_prior_mapping_reason(client: TestClient, tmp_workspaces: Path):
    csv = (
        "EmpID,DOB,Hire Date,Salary,Active\n"
        "E001,1980-01-01,2020-01-01,95000,Y\n"
    )
    # First import — generate to create fingerprint
    session1 = _upload_csv(client, csv)
    mapping_payload = {"field_mappings": [
        {"input_column": "EmpID", "output_column": "employee_id", "output_type": "string",
         "is_excluded": False, "transformations": []},
        {"input_column": "DOB", "output_column": "employee_birth_date", "output_type": "date",
         "is_excluded": False, "transformations": [{"transform_type": "date_parse", "params": {"format": "%Y-%m-%d"}}]},
        {"input_column": "Hire Date", "output_column": "employee_hire_date", "output_type": "date",
         "is_excluded": False, "transformations": [{"transform_type": "date_parse", "params": {"format": "%Y-%m-%d"}}]},
        {"input_column": "Salary", "output_column": "employee_gross_compensation",
         "output_type": "decimal", "is_excluded": False, "transformations": []},
        {"input_column": "Active", "output_column": "active", "output_type": "boolean",
         "is_excluded": False, "transformations": []},
    ]}
    client.put(f"/api/workspaces/ws-test/imports/{session1['import_id']}/mapping", json=mapping_payload)
    client.post(f"/api/workspaces/ws-test/imports/{session1['import_id']}/generate")

    # Second import — same headers
    session2 = _upload_csv(client, csv)
    resp = client.get(f"/api/workspaces/ws-test/imports/{session2['import_id']}/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    prior_mapped = [s for s in data["suggestions"] if s["reason"] == "prior_mapping"]
    assert len(prior_mapped) == 5, f"Expected 5 prior_mapping suggestions, got {prior_mapped}"
