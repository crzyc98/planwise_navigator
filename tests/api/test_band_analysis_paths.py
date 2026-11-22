"""Tests for census path containment order on band and analysis endpoints."""

from pathlib import Path

import pytest


@pytest.mark.fast
class TestBandAnalysisPathContainmentOrder:
    """Band and census analysis endpoints check workspaces_root containment before filesystem checks."""

    _ENDPOINTS: list[tuple[str, dict[str, object]]] = [
        ("analyze-age-bands", {}),
        ("analyze-tenure-bands", {}),
        ("analyze-turnover", {}),
        ("analyze-opt-out-rate", {}),
        ("analyze-deferral-segments", {}),
        ("analyze-census", {}),
    ]

    @staticmethod
    def _seed_workspace_with_census(client, tmp_path: Path) -> tuple[str, Path]:
        ws_resp = client.post("/api/workspaces", json={"name": "Band Containment WS"})
        assert ws_resp.status_code == 201
        workspace_id = ws_resp.json()["id"]
        data_dir = tmp_path / "workspaces" / workspace_id / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        census_path = data_dir / "census.csv"
        census_path.write_text(
            "employee_id,employee_birth_date,employee_hire_date,"
            "employee_termination_date,employee_gross_compensation,"
            "employee_deferral_rate,active\n"
            "E001,1985-04-10,2020-01-15,,75000,0.06,true\n"
            "E002,1990-08-20,2022-06-01,,85000,0.00,true\n"
            "E003,1978-11-05,2018-03-10,2024-02-01,110000,0.08,false\n",
            encoding="utf-8",
        )
        return workspace_id, census_path

    @pytest.mark.parametrize(("endpoint", "extra_payload"), _ENDPOINTS)
    def test_outside_paths_return_identical_400_regardless_of_existence(
        self,
        client_factory,
        tmp_path: Path,
        endpoint: str,
        extra_payload: dict,
    ) -> None:
        client = client_factory(None)
        workspace_id, _ = self._seed_workspace_with_census(client, tmp_path)

        outside_file = tmp_path / "outside_existing.csv"
        outside_file.write_text("employee_id\nE1\n", encoding="utf-8")
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        outside_missing = tmp_path / "outside_missing.csv"

        link_escape = (
            tmp_path / "workspaces" / workspace_id / "data" / "escape_link.csv"
        )
        link_escape.symlink_to(outside_file)

        outside_cases = [
            str(outside_file),
            str(outside_dir),
            str(outside_missing),
            "data/../../../outside_existing.csv",
            "data/escape_link.csv",
        ]

        url = f"/api/workspaces/{workspace_id}/{endpoint}"
        responses = [
            client.post(url, json={"file_path": candidate, **extra_payload})
            for candidate in outside_cases
        ]

        first = responses[0]
        assert first.status_code == 400
        assert first.json() == {"detail": "Invalid census file path"}
        for resp in responses:
            assert resp.status_code == first.status_code
            assert resp.json() == first.json()
            assert str(tmp_path) not in resp.text

    @pytest.mark.parametrize(("endpoint", "extra_payload"), _ENDPOINTS)
    def test_inside_root_relative_and_absolute_paths_still_work(
        self,
        client_factory,
        tmp_path: Path,
        endpoint: str,
        extra_payload: dict,
    ) -> None:
        client = client_factory(None)
        workspace_id, census_path = self._seed_workspace_with_census(client, tmp_path)
        url = f"/api/workspaces/{workspace_id}/{endpoint}"

        for valid_path in ("data/census.csv", str(census_path.resolve())):
            resp = client.post(url, json={"file_path": valid_path, **extra_payload})
            assert resp.status_code == 200, (endpoint, valid_path, resp.text)

        missing_resp = client.post(
            url, json={"file_path": "data/does_not_exist.csv", **extra_payload}
        )
        assert missing_resp.status_code == 400
        assert "File not found" in missing_resp.json()["detail"]
