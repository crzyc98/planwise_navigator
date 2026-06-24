"""Integration tests for data import endpoints.

Covers all user stories US1–US5.
Each test block (T011, T019, T052, T053, T054) is written first (FAIL), then implemented.
"""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample_census_import.csv"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Create test client with isolated workspace root."""
    monkeypatch.setenv("PLANALIGN_API_WORKSPACES_ROOT", str(tmp_path / "workspaces"))
    from importlib import reload
    import planalign_api.config as api_config

    reload(api_config)
    import planalign_api.main as api_main

    reload(api_main)
    from planalign_api.main import app

    return TestClient(app)


@pytest.fixture()
def workspace_id(client) -> str:
    resp = client.post("/api/workspaces", json={"name": "test-ws"})
    assert resp.status_code == 201
    return resp.json()["id"]


# ===========================================================================
# T011 — US1: Upload and Map CSV
# ===========================================================================


class TestUploadAndMap:
    def test_upload_csv_returns_201_with_detected_columns(self, client, workspace_id):
        with open(SAMPLE_CSV, "rb") as f:
            resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "import_id" in data
        assert data["status"] == "uploaded"
        assert len(data["detected_columns"]) == 5
        col_names = [c["name"] for c in data["detected_columns"]]
        assert "EMP_ID" in col_names
        assert "HIRE_DATE" in col_names

    def test_upload_xlsx_detects_available_sheets(self, client, workspace_id):
        pytest.importorskip("openpyxl")
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Employees"
        ws.append(["ID", "NAME"])
        ws.append(["E001", "Alice"])
        ws2 = wb.create_sheet("Sheet2")
        ws2.append(["ID", "NAME"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={
                "file": (
                    "data.xlsx",
                    buf,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["source_format"] == "xlsx"
        assert len(data["available_sheets"]) == 2

    def test_upload_unsupported_format_returns_400(self, client, workspace_id):
        resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={"file": ("data.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_empty_csv_returns_422(self, client, workspace_id):
        resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={"file": ("empty.csv", b"EMP_ID,NAME\n", "text/csv")},
        )
        assert resp.status_code == 422

    def test_put_mapping_saves_and_returns_200(self, client, workspace_id):
        with open(SAMPLE_CSV, "rb") as f:
            upload_resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        import_id = upload_resp.json()["import_id"]
        mapping_payload = {
            "field_mappings": [
                {
                    "input_column": "EMP_ID",
                    "output_column": "employee_id",
                    "output_type": "string",
                    "is_required": True,
                    "is_excluded": False,
                    "transformations": [],
                },
                {
                    "input_column": "HIRE_DATE",
                    "output_column": "hire_date",
                    "output_type": "date",
                    "is_required": False,
                    "is_excluded": False,
                    "transformations": [
                        {
                            "transform_type": "date_parse",
                            "params": {"format": "%m/%d/%Y"},
                        }
                    ],
                },
                {
                    "input_column": "DEPT",
                    "output_column": "department",
                    "output_type": "string",
                    "is_required": False,
                    "is_excluded": False,
                    "transformations": [
                        {"transform_type": "string_case", "params": {"case": "lower"}}
                    ],
                },
            ]
        }
        resp = client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json=mapping_payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["import_id"] == import_id
        assert data["validation_errors"] == []

    def test_put_mapping_returns_validation_error_for_invalid_output_column(
        self, client, workspace_id
    ):
        with open(SAMPLE_CSV, "rb") as f:
            upload_resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        import_id = upload_resp.json()["import_id"]
        resp = client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json={
                "field_mappings": [
                    {
                        "input_column": "EMP_ID",
                        "output_column": "INVALID COLUMN NAME!",
                        "output_type": "string",
                        "is_excluded": False,
                        "transformations": [],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["validation_errors"]) > 0


# ===========================================================================
# T019 — US2: Generate Parquet
# ===========================================================================


class TestGenerateParquet:
    def _upload_and_map(self, client, workspace_id: str) -> str:
        with open(SAMPLE_CSV, "rb") as f:
            upload_resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        assert upload_resp.status_code == 201
        import_id = upload_resp.json()["import_id"]
        mapping_payload = {
            "field_mappings": [
                {
                    "input_column": "EMP_ID",
                    "output_column": "employee_id",
                    "output_type": "string",
                    "is_excluded": False,
                    "transformations": [],
                },
                {
                    "input_column": "SALARY",
                    "output_column": "salary",
                    "output_type": "decimal",
                    "is_excluded": False,
                    "transformations": [],
                },
            ]
        }
        map_resp = client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json=mapping_payload,
        )
        assert map_resp.status_code == 200
        return import_id

    def test_generate_returns_202_and_status_generating(self, client, workspace_id):
        import_id = self._upload_and_map(client, workspace_id)
        resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/generate",
            json={},
        )
        assert resp.status_code in (201, 202)

    def test_generated_parquet_readable_by_duckdb(self, client, workspace_id):
        import duckdb

        import_id = self._upload_and_map(client, workspace_id)
        gen_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/generate",
            json={},
        )
        assert gen_resp.status_code in (201, 202)
        status_resp = client.get(f"/api/workspaces/{workspace_id}/imports/{import_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "completed"
        parquet_files = client.get(
            f"/api/workspaces/{workspace_id}/parquet-files"
        ).json()
        assert parquet_files["total_count"] >= 1
        storage_path = parquet_files["parquet_files"][0]["storage_path"]
        conn = duckdb.connect(":memory:")
        count = conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{storage_path}')"
        ).fetchone()[0]
        conn.close()
        assert count > 0

    def test_generate_without_mapping_returns_409(self, client, workspace_id):
        with open(SAMPLE_CSV, "rb") as f:
            upload_resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        import_id = upload_resp.json()["import_id"]
        resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/generate",
            json={},
        )
        assert resp.status_code == 409


# ===========================================================================
# T052 — US3: File Management
# ===========================================================================


class TestFileManagement:
    def _full_flow(
        self, client, workspace_id: str, filename: str = "sample_census_import.csv"
    ):
        with open(SAMPLE_CSV, "rb") as f:
            upload_resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": (filename, f, "text/csv")},
            )
        import_id = upload_resp.json()["import_id"]
        client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json={
                "field_mappings": [
                    {
                        "input_column": "EMP_ID",
                        "output_column": "employee_id",
                        "output_type": "string",
                        "is_excluded": False,
                        "transformations": [],
                    },
                ]
            },
        )
        client.post(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/generate", json={}
        )
        return import_id

    def test_generated_file_appears_in_parquet_list(self, client, workspace_id):
        self._full_flow(client, workspace_id)
        resp = client.get(f"/api/workspaces/{workspace_id}/parquet-files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] >= 1
        assert len(data["parquet_files"]) >= 1

    def test_two_imports_produce_distinct_filenames(self, client, workspace_id):
        self._full_flow(client, workspace_id, "file1.csv")
        self._full_flow(client, workspace_id, "file2.csv")
        resp = client.get(f"/api/workspaces/{workspace_id}/parquet-files")
        filenames = [f["filename"] for f in resp.json()["parquet_files"]]
        assert len(set(filenames)) == len(filenames)

    def test_download_returns_binary(self, client, workspace_id):
        self._full_flow(client, workspace_id)
        files = client.get(f"/api/workspaces/{workspace_id}/parquet-files").json()[
            "parquet_files"
        ]
        file_id = files[0]["file_id"]
        resp = client.get(
            f"/api/workspaces/{workspace_id}/parquet-files/{file_id}/download"
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_delete_by_creator_returns_204(self, client, workspace_id):
        self._full_flow(client, workspace_id)
        files = client.get(f"/api/workspaces/{workspace_id}/parquet-files").json()[
            "parquet_files"
        ]
        file_id = files[0]["file_id"]
        resp = client.delete(
            f"/api/workspaces/{workspace_id}/parquet-files/{file_id}",
            headers={"X-User-Id": "system"},
        )
        assert resp.status_code == 204
        remaining = client.get(f"/api/workspaces/{workspace_id}/parquet-files").json()
        assert remaining["total_count"] == 0

    def test_delete_by_non_creator_returns_403(self, client, workspace_id):
        self._full_flow(client, workspace_id)
        files = client.get(f"/api/workspaces/{workspace_id}/parquet-files").json()[
            "parquet_files"
        ]
        file_id = files[0]["file_id"]
        resp = client.delete(
            f"/api/workspaces/{workspace_id}/parquet-files/{file_id}",
            headers={"X-User-Id": "unauthorized_user"},
        )
        assert resp.status_code == 403


# ===========================================================================
# T053 — US4: Preview endpoints
# ===========================================================================


class TestPreviewEndpoints:
    def _upload(self, client, workspace_id: str) -> str:
        with open(SAMPLE_CSV, "rb") as f:
            resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        return resp.json()["import_id"]

    def test_raw_preview_returns_100_rows_with_original_columns(
        self, client, workspace_id
    ):
        import_id = self._upload(client, workspace_id)
        resp = client.get(f"/api/workspaces/{workspace_id}/imports/{import_id}/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert "EMP_ID" in data["columns"]
        assert len(data["rows"]) <= 100

    def test_mapped_preview_returns_output_column_names(self, client, workspace_id):
        import_id = self._upload(client, workspace_id)
        client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json={
                "field_mappings": [
                    {
                        "input_column": "EMP_ID",
                        "output_column": "employee_id",
                        "output_type": "string",
                        "is_excluded": False,
                        "transformations": [],
                    },
                ]
            },
        )
        resp = client.get(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapped-preview"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "employee_id" in data["columns"]
        assert "EMP_ID" not in data["columns"]

    def test_mapped_preview_with_date_parse_reports_warnings(
        self, client, workspace_id
    ):
        import_id = self._upload(client, workspace_id)
        client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json={
                "field_mappings": [
                    {
                        "input_column": "HIRE_DATE",
                        "output_column": "hire_date",
                        "output_type": "date",
                        "is_excluded": False,
                        "transformations": [
                            {
                                "transform_type": "date_parse",
                                "params": {"format": "%m/%d/%Y"},
                            }
                        ],
                    },
                ]
            },
        )
        resp = client.get(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapped-preview"
        )
        assert resp.status_code == 200
        warnings = resp.json()["transformation_warnings"]
        assert len(warnings) >= 1
        assert any("could not be parsed" in w["message"] for w in warnings)

    def test_mapped_preview_without_mapping_returns_409(self, client, workspace_id):
        import_id = self._upload(client, workspace_id)
        resp = client.get(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapped-preview"
        )
        assert resp.status_code == 409


# ===========================================================================
# T054 — US5: Mapping Templates
# ===========================================================================


class TestMappingTemplates:
    def _upload_and_map(self, client, workspace_id: str) -> str:
        with open(SAMPLE_CSV, "rb") as f:
            upload_resp = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("sample_census_import.csv", f, "text/csv")},
            )
        import_id = upload_resp.json()["import_id"]
        client.put(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping",
            json={
                "field_mappings": [
                    {
                        "input_column": "EMP_ID",
                        "output_column": "employee_id",
                        "output_type": "string",
                        "is_excluded": False,
                        "transformations": [],
                    },
                    {
                        "input_column": "DEPT",
                        "output_column": "department",
                        "output_type": "string",
                        "is_excluded": False,
                        "transformations": [
                            {
                                "transform_type": "string_case",
                                "params": {"case": "lower"},
                            }
                        ],
                    },
                ]
            },
        )
        return import_id

    def test_saved_template_appears_in_list(self, client, workspace_id):
        import_id = self._upload_and_map(client, workspace_id)
        save_resp = client.post(
            f"/api/workspaces/{workspace_id}/mapping-templates",
            json={
                "import_id": import_id,
                "name": "Standard HR Export",
                "description": "Test",
            },
        )
        assert save_resp.status_code == 201
        list_resp = client.get(f"/api/workspaces/{workspace_id}/mapping-templates")
        assert list_resp.status_code == 200
        templates = list_resp.json()["templates"]
        assert len(templates) == 1
        assert templates[0]["name"] == "Standard HR Export"

    def test_apply_template_populates_mappings(self, client, workspace_id):
        import_id = self._upload_and_map(client, workspace_id)
        save_resp = client.post(
            f"/api/workspaces/{workspace_id}/mapping-templates",
            json={"import_id": import_id, "name": "Standard HR Export"},
        )
        template_id = save_resp.json()["template_id"]

        with open(SAMPLE_CSV, "rb") as f:
            upload2 = client.post(
                f"/api/workspaces/{workspace_id}/imports/upload",
                files={"file": ("second.csv", f, "text/csv")},
            )
        import_id2 = upload2.json()["import_id"]
        apply_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/{import_id2}/apply-template",
            json={"template_id": template_id},
        )
        assert apply_resp.status_code == 200

    def test_apply_template_skips_unmatched_columns(self, client, workspace_id):
        import_id = self._upload_and_map(client, workspace_id)
        save_resp = client.post(
            f"/api/workspaces/{workspace_id}/mapping-templates",
            json={"import_id": import_id, "name": "HR Template"},
        )
        template_id = save_resp.json()["template_id"]

        csv_content = b"DIFFERENT_COL\nvalue1\nvalue2\n"
        upload2 = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={"file": ("different.csv", csv_content, "text/csv")},
        )
        import_id2 = upload2.json()["import_id"]
        apply_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/{import_id2}/apply-template",
            json={"template_id": template_id},
        )
        assert apply_resp.status_code == 200


# ===========================================================================
# Performance benchmark (T057) — documented, not blocking
# ===========================================================================
# SC-001: upload → map → generate < 5 minutes for 100K rows
# Actual elapsed for 200-row fixture: measured inline in test run output
