"""Rolling an old workspace census forward from Studio (#1078)."""

import json
from pathlib import Path
from typing import Dict, List

import duckdb
import pytest

from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services import census_rollforward_jobs as jobs
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast

HEADERS = {"Authorization": "Bearer secret"}


@pytest.fixture(autouse=True)
def no_jobs(monkeypatch):
    monkeypatch.setattr(jobs, "_jobs", {})


def _census(path: Path, hire_year: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as conn:
        conn.execute(f"""COPY (SELECT 'E' || i AS employee_id,
                  MAKE_DATE({hire_year} - (i % 5), 3, 1) AS employee_hire_date
                FROM range(50) t(i))
            TO '{path}' (FORMAT parquet)""")
    return path


def _workspace(tmp_path: Path, census_year: int, start_year: int = 2026) -> str:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    census = _census(tmp_path / "census.parquet", census_year)
    workspace = storage.create_workspace(
        WorkspaceCreate(name="W"),
        {
            "simulation": {"start_year": start_year, "end_year": start_year + 2},
            "setup": {"census_parquet_path": str(census)},
        },
    )
    return workspace.id


def _arg(command: List[str], flag: str) -> Path:
    return Path(command[command.index(flag) + 1])


async def _fake_cli(command: List[str], env: Dict[str, str]) -> None:
    output = _census(_arg(command, "--output"), 2025)
    _arg(command, "--summary-json").write_text(
        json.dumps(
            {
                "census_path": str(output),
                "census_year": 2024,
                "bridge_year": 2025,
                "hires": 12,
                "terminations": 9,
                "ending_headcount": 50,
                "simulated_employees": 10,
            }
        )
    )


async def _failing_cli(command: List[str], env: Dict[str, str]) -> None:
    raise RuntimeError("roll-forward exited 1: dbt failed")


def _base_census(tmp_path: Path, workspace_id: str) -> str:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    return storage.get_workspace(workspace_id).base_config["setup"][
        "census_parquet_path"
    ]


def test_status_flags_a_census_two_years_behind(client_factory, tmp_path) -> None:
    workspace_id = _workspace(tmp_path, census_year=2024)
    client = client_factory("secret")

    body = client.get(
        f"/api/workspaces/{workspace_id}/census/status", headers=HEADERS
    ).json()

    assert (body["census_year"], body["start_year"]) == (2024, 2026)
    assert (body["behind"], body["bridge_year"]) == (True, 2025)
    assert body["active_job"] is None


def test_a_current_census_cannot_be_rolled_forward(client_factory, tmp_path) -> None:
    workspace_id = _workspace(tmp_path, census_year=2025)
    client = client_factory("secret")

    status = client.get(
        f"/api/workspaces/{workspace_id}/census/status", headers=HEADERS
    ).json()
    started = client.post(
        f"/api/workspaces/{workspace_id}/census/roll-forward", headers=HEADERS
    )

    assert status["behind"] is False
    assert started.status_code == 409


def test_roll_forward_saves_lists_and_activates_the_bridge(
    client_factory, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(jobs, "run_cli", _fake_cli)
    workspace_id = _workspace(tmp_path, census_year=2024)
    client = client_factory("secret")

    started = client.post(
        f"/api/workspaces/{workspace_id}/census/roll-forward", headers=HEADERS
    )
    job = client.get(
        f"/api/workspaces/{workspace_id}/census/roll-forward/{started.json()['id']}",
        headers=HEADERS,
    ).json()
    files = client.get(
        f"/api/workspaces/{workspace_id}/parquet-files", headers=HEADERS
    ).json()["parquet_files"]

    assert started.status_code == 202
    assert job["status"] == "completed"
    assert job["summary"]["hires"] == 12
    bridge = job["summary"]["census_path"]
    assert bridge.endswith("data/census_bridge_2025.parquet")
    assert _base_census(tmp_path, workspace_id) == bridge
    assert [f["storage_path"] for f in files] == [bridge]
    work = tmp_path / "workspaces" / workspace_id / "census_rollforward" / job["id"]
    assert not work.exists()


def test_a_failed_roll_forward_keeps_the_original_census(
    client_factory, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(jobs, "run_cli", _failing_cli)
    workspace_id = _workspace(tmp_path, census_year=2024)
    original = _base_census(tmp_path, workspace_id)
    client = client_factory("secret")

    started = client.post(
        f"/api/workspaces/{workspace_id}/census/roll-forward", headers=HEADERS
    ).json()
    job = client.get(
        f"/api/workspaces/{workspace_id}/census/roll-forward/{started['id']}",
        headers=HEADERS,
    ).json()

    assert job["status"] == "failed"
    assert "error_id" in job["error_message"]
    assert "dbt failed" not in job["error_message"]
    assert _base_census(tmp_path, workspace_id) == original


def test_hand_set_plan_year_dates_follow_the_bridge(
    client_factory, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(jobs, "run_cli", _fake_cli)
    workspace_id = _workspace(tmp_path, census_year=2024)
    storage = WorkspaceStorage(tmp_path / "workspaces")
    storage.update_base_config_key(
        workspace_id, "setup.plan_year_start_date", "2024-01-01"
    )
    client = client_factory("secret")

    client.post(f"/api/workspaces/{workspace_id}/census/roll-forward", headers=HEADERS)

    setup = storage.get_workspace(workspace_id).base_config["setup"]
    assert setup["plan_year_start_date"] == "2025-01-01"
    assert "plan_year_end_date" not in setup


def test_unknown_workspace_and_job_are_not_found(client_factory, tmp_path) -> None:
    workspace_id = _workspace(tmp_path, census_year=2024)
    client = client_factory("secret")

    assert (
        client.get("/api/workspaces/nope/census/status", headers=HEADERS).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/workspaces/{workspace_id}/census/roll-forward/nope",
            headers=HEADERS,
        ).status_code
        == 404
    )
