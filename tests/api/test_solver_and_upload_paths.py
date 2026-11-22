"""Fast API tests for compensation solver path validation and import upload naming."""

from __future__ import annotations

import io
import json
from pathlib import Path

import duckdb
import openpyxl
import pytest

from planalign_api.services.compensation_solver import CompensationSolver
from planalign_api.services.sql_security import SQLSecurityError

pytestmark = pytest.mark.fast


def _create_workspace(client) -> str:
    resp = client.post("/api/workspaces", json={"name": "Path Test Workspace"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _write_census_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "employee_id,active,employee_gross_compensation,level_id\n"
        "E1,true,120000,1\n"
        "E2,true,150000,2\n"
        "E3,true,180000,3\n",
        encoding="utf-8",
    )


def _write_census_parquet(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(
            """
            COPY (
                SELECT * FROM (VALUES
                    ('E1', true, 120000.0, 1),
                    ('E2', true, 150000.0, 2),
                    ('E3', true, 180000.0, 3)
                ) AS t(employee_id, active, employee_gross_compensation, level_id)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(path)],
        )
    finally:
        conn.close()


def _make_two_sheet_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws1 = wb.active
    assert ws1 is not None
    ws1.title = "SheetA"
    ws1.append(["COL_A", "SALARY"])
    ws1.append(["E001", "90000"])

    ws2 = wb.create_sheet("SheetB")
    ws2.append(["COL_B", "SALARY"])
    ws2.append(["E001", "90000"])
    ws2.append(["E002", "110000"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCompensationSolverPathContainment:
    """Compensation solver rejects paths outside the workspaces root."""

    def test_rejects_absolute_path_outside_workspaces_root_without_reading(
        self, client_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        outside_file = tmp_path / "outside_census.csv"
        _write_census_csv(outside_file)

        duckdb_called = False
        real_connect = duckdb.connect

        def _fail_if_called(*args: object, **kwargs: object) -> object:
            nonlocal duckdb_called
            duckdb_called = True
            return real_connect(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(duckdb, "connect", _fail_if_called)

        resp = client.post(
            f"/api/workspaces/{workspace_id}/solve-compensation-growth",
            json={
                "file_path": str(outside_file),
                "target_growth_rate": 0.03,
            },
        )

        assert 400 <= resp.status_code < 500
        assert resp.json()["detail"] == "Invalid census file path"
        assert str(tmp_path) not in resp.text
        assert str(outside_file) not in resp.text
        assert duckdb_called is False

    @pytest.mark.parametrize(
        "traversal_path",
        [
            "data/../../../outside_census.csv",
            "../../outside_census.csv",
        ],
    )
    def test_rejects_relative_traversal_without_reading(
        self,
        client_factory,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        traversal_path: str,
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        outside_file = tmp_path / "outside_census.csv"
        _write_census_csv(outside_file)

        duckdb_called = False
        real_connect = duckdb.connect

        def _fail_if_called(*args: object, **kwargs: object) -> object:
            nonlocal duckdb_called
            duckdb_called = True
            return real_connect(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(duckdb, "connect", _fail_if_called)

        resp = client.post(
            f"/api/workspaces/{workspace_id}/solve-compensation-growth",
            json={
                "file_path": traversal_path,
                "target_growth_rate": 0.03,
            },
        )

        assert 400 <= resp.status_code < 500
        assert resp.json()["detail"] == "Invalid census file path"
        assert str(tmp_path) not in resp.text
        assert duckdb_called is False

    def test_rejects_symlink_pointing_outside_workspaces_root(
        self, client_factory, tmp_path: Path
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        outside_file = tmp_path / "outside_census.csv"
        _write_census_csv(outside_file)

        link_path = tmp_path / "workspaces" / workspace_id / "data" / "link.csv"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(outside_file)

        resp = client.post(
            f"/api/workspaces/{workspace_id}/solve-compensation-growth",
            json={
                "file_path": "data/link.csv",
                "target_growth_rate": 0.03,
            },
        )

        assert 400 <= resp.status_code < 500
        assert resp.json()["detail"] == "Invalid census file path"
        assert str(tmp_path) not in resp.text

    def test_solve_with_census_does_not_swallow_outside_path(
        self, tmp_path: Path
    ) -> None:
        workspaces_root = tmp_path / "workspaces"
        workspaces_root.mkdir()
        outside_file = tmp_path / "outside.csv"
        _write_census_csv(outside_file)

        solver = CompensationSolver(workspaces_root)

        with pytest.raises(SQLSecurityError):
            solver.solve_with_census("ws-1", str(outside_file), 0.03)

        with pytest.raises(SQLSecurityError):
            solver.solve_with_census("ws-1", "data/../../../outside.csv", 0.03)

    def test_accepts_workspace_census_via_relative_and_absolute_paths(
        self, client_factory, tmp_path: Path
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        ws_data = tmp_path / "workspaces" / workspace_id / "data"

        csv_path = ws_data / "census.csv"
        _write_census_csv(csv_path)
        parquet_path = ws_data / "imports" / "census.parquet"
        _write_census_parquet(parquet_path)

        rel_resp = client.post(
            f"/api/workspaces/{workspace_id}/solve-compensation-growth",
            json={
                "file_path": "data/census.csv",
                "target_growth_rate": 0.03,
            },
        )
        assert rel_resp.status_code == 200, rel_resp.text
        rel_body = rel_resp.json()
        assert rel_body["total_headcount"] == 3
        assert rel_body["avg_compensation"] == pytest.approx(150000.0)
        assert rel_body["level_distribution"] is not None
        assert len(rel_body["level_distribution"]) == 3

        abs_resp = client.post(
            f"/api/workspaces/{workspace_id}/solve-compensation-growth",
            json={
                "file_path": str(parquet_path.resolve()),
                "target_growth_rate": 0.03,
            },
        )
        assert abs_resp.status_code == 200, abs_resp.text
        abs_body = abs_resp.json()
        assert abs_body["total_headcount"] == 3
        assert abs_body["avg_compensation"] == pytest.approx(150000.0)
        assert abs_body["level_distribution"] is not None
        assert len(abs_body["level_distribution"]) == 3


class TestImportUploadRetainedFilename:
    """Import uploads retain files under a fixed session-local name."""

    @pytest.mark.parametrize(
        "client_filename",
        [
            "../escape.csv",
            "../../outside.csv",
            "nested/dir/census.csv",
            "/abs/path/census.csv",
        ],
    )
    def test_upload_with_path_separators_stores_direct_child_and_preserves_name(
        self, client_factory, tmp_path: Path, client_filename: str
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        csv_bytes = b"EMP_ID,SALARY\nE001,85000\nE002,95000\n"

        resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={"file": (client_filename, io.BytesIO(csv_bytes), "text/csv")},
        )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["original_filename"] == client_filename

        import_id = data["import_id"]
        status_resp = client.get(f"/api/workspaces/{workspace_id}/imports/{import_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["original_filename"] == client_filename

        session_dir = (
            tmp_path / "workspaces" / workspace_id / "imports" / import_id
        ).resolve()
        retained = session_dir / "_orig.csv"
        assert retained.is_file()
        assert retained.resolve().parent == session_dir
        assert not (session_dir.parent / "escape.csv").exists()
        assert not (session_dir.parent.parent / "outside.csv").exists()

    def test_sheet_reselection_works_for_new_session_with_traversal_filename(
        self, client_factory, tmp_path: Path
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        xlsx_bytes = _make_two_sheet_xlsx()
        client_filename = "../nested/workforce.xlsx"

        upload_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={
                "file": (
                    client_filename,
                    io.BytesIO(xlsx_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_resp.status_code == 201, upload_resp.text
        session = upload_resp.json()
        import_id = session["import_id"]
        assert session["original_filename"] == client_filename
        assert session["available_sheets"] == ["SheetA", "SheetB"]

        session_dir = (
            tmp_path / "workspaces" / workspace_id / "imports" / import_id
        ).resolve()
        retained = session_dir / "_orig.xlsx"
        assert retained.is_file()
        assert retained.resolve().parent == session_dir

        patch_resp = client.patch(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/sheet",
            json={"sheet_name": "SheetB"},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        updated = patch_resp.json()
        assert updated["sheet_name"] == "SheetB"
        assert updated["row_count"] == 2
        assert updated["original_filename"] == client_filename
        assert [c["name"] for c in updated["detected_columns"]] == ["COL_B", "SALARY"]

    def test_sheet_reselection_works_for_legacy_orig_filename_session(
        self, client_factory, tmp_path: Path
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        xlsx_bytes = _make_two_sheet_xlsx()

        upload_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={
                "file": (
                    "legacy_census.xlsx",
                    io.BytesIO(xlsx_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_resp.status_code == 201, upload_resp.text
        import_id = upload_resp.json()["import_id"]

        session_dir = tmp_path / "workspaces" / workspace_id / "imports" / import_id
        (session_dir / "_orig.xlsx").rename(session_dir / "_orig_legacy_census.xlsx")

        patch_resp = client.patch(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/sheet",
            json={"sheet_name": "SheetB"},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        updated = patch_resp.json()
        assert updated["sheet_name"] == "SheetB"
        assert updated["row_count"] == 2
        assert [c["name"] for c in updated["detected_columns"]] == ["COL_B", "SALARY"]

    def test_sheet_reselection_ignores_legacy_fallback_outside_session_dir(
        self, client_factory, tmp_path: Path
    ) -> None:
        client = client_factory(None)
        workspace_id = _create_workspace(client)
        xlsx_bytes = _make_two_sheet_xlsx()

        upload_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={
                "file": (
                    "legacy.xlsx",
                    io.BytesIO(xlsx_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_resp.status_code == 201, upload_resp.text
        import_id = upload_resp.json()["import_id"]

        session_dir = tmp_path / "workspaces" / workspace_id / "imports" / import_id
        (session_dir / "_orig.xlsx").unlink()

        outside_xlsx = session_dir.parent / "outside.xlsx"
        outside_xlsx.write_bytes(xlsx_bytes)

        # Case 1: tampered original_filename with parent traversal
        metadata_path = session_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["original_filename"] = "../outside.xlsx"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        resp = client.patch(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/sheet",
            json={"sheet_name": "SheetB"},
        )
        assert resp.status_code == 422

        # Case 2: symlink inside session_dir pointing outside
        metadata["original_filename"] = "symlink.xlsx"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        (session_dir / "_orig_symlink.xlsx").symlink_to(outside_xlsx)

        resp_symlink = client.patch(
            f"/api/workspaces/{workspace_id}/imports/{import_id}/sheet",
            json={"sheet_name": "SheetB"},
        )
        assert resp_symlink.status_code == 422
