"""Size limits on fit-history uploads, NDT scenario lists, fits and census segments."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.config import APISettings
from planalign_api.routers import ndt, param_fits
from planalign_api.services.census_analysis_service import (
    MAX_SEGMENTS_PER_DIMENSION,
    CensusAnalysisService,
    _AverageOptions,
)
from planalign_api.services.ndt_service import ACPScenarioResult
from tests.fixtures.param_fit import StubCommands, history_files, make_harness

pytestmark = [pytest.mark.fast]


# -- fit-history uploads -------------------------------------------------------


class UnreadableUpload:
    """An upload whose body must never be read."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.size = None

    async def read(self, size: int = -1) -> bytes:
        raise AssertionError("upload body was read")


@pytest.fixture
def harness(tmp_path: Path):
    return make_harness(tmp_path, StubCommands(fixture_pack=tmp_path / "unused"))


def _upload(harness, workspace_id: str, names: list[str]):
    files = [UnreadableUpload(name) for name in names]
    return asyncio.run(
        param_fits.upload_fit_history(
            workspace_id,
            files=files,  # type: ignore[arg-type]
            service=harness.service(),
        )
    )


@pytest.mark.parametrize(
    "names,status",
    [
        ([f"census_{2020 + i}.csv" for i in range(6)], 422),
        (["census_2022.csv"], 422),
        (["census_2022.csv", "census_2023.txt"], 422),
    ],
)
def test_fit_history_rejected_before_reading(harness, names, status) -> None:
    response = _upload(harness, harness.workspace_id, names)
    assert response.status_code == status


def test_fit_history_unknown_workspace_rejected_before_reading(harness) -> None:
    response = _upload(harness, "nope", ["census_2022.csv", "census_2023.csv"])
    assert response.status_code == 404


def test_six_files_message(harness) -> None:
    names = [f"census_{2020 + i}.csv" for i in range(6)]
    body = json.loads(_upload(harness, harness.workspace_id, names).body)
    assert "at most 5" in body["detail"]


# -- concurrent fit cap --------------------------------------------------------


def test_default_fit_cap_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert APISettings().max_concurrent_fits == 2
    monkeypatch.setenv("PLANALIGN_API_MAX_CONCURRENT_FITS", "3")
    assert APISettings().max_concurrent_fits == 3


def test_third_concurrent_fit_is_refused(tmp_path: Path) -> None:
    harness = make_harness(
        tmp_path, StubCommands(fixture_pack=tmp_path / "unused", behaviour="sleep")
    )
    files = history_files(tmp_path / "history" / "census", years=3)
    history_id = harness.upload(files).json()["history_id"]
    app = harness.client.app
    app.dependency_overrides[param_fits.get_param_fit_service] = lambda: (
        param_fits.ParamFitService(
            harness.storage,
            registry=harness.registry,
            command_factory=harness.commands,
            max_concurrent_fits=2,
        )
    )
    started = [harness.start(history_id) for _ in range(2)]
    try:
        assert [r.status_code for r in started] == [202, 202]
        third = harness.start(history_id)
        assert third.status_code == 429
        assert "fits are already running" in third.json()["detail"]
    finally:
        for response in started:
            job_id = response.json()["job_id"]
            harness.client.post(harness.url(f"/param-fits/{job_id}/cancel"))
            harness.wait(job_id)
    assert harness.start(history_id).status_code == 202


# -- NDT scenario lists --------------------------------------------------------

NDT_PATHS = ["acp", "401a4", "415", "adp"]


@pytest.fixture
def ndt_client(monkeypatch: pytest.MonkeyPatch):
    storage = MagicMock()
    storage.get_scenario.side_effect = lambda _ws, sid: SimpleNamespace(
        name=sid, status="completed"
    )
    service = MagicMock()
    service.run_acp_test.side_effect = lambda **kw: ACPScenarioResult(
        scenario_id=kw["scenario_id"],
        scenario_name="S",
        simulation_year=kw["year"],
        test_result="pass",
    )
    monkeypatch.setattr(ndt, "has_selected_result", lambda *args: True)
    app = FastAPI()
    app.include_router(ndt.router)
    app.dependency_overrides[ndt.get_storage] = lambda: storage
    app.dependency_overrides[ndt.get_ndt_service] = lambda: service
    return TestClient(app), service


@pytest.mark.parametrize("path", NDT_PATHS)
@pytest.mark.parametrize(
    "scenarios", ["a,b,a", "a, a", ",".join(f"s{i}" for i in range(7)), " , ,"]
)
def test_ndt_rejects_bad_scenario_lists(ndt_client, path: str, scenarios: str) -> None:
    client, service = ndt_client
    response = client.get(
        f"/w/analytics/ndt/{path}", params={"scenarios": scenarios, "year": 2025}
    )
    assert response.status_code == 422
    assert not service.method_calls


def test_ndt_valid_list_still_works(ndt_client) -> None:
    client, service = ndt_client
    ids = [f"s{i}" for i in range(6)]
    response = client.get(
        "/w/analytics/ndt/acp", params={"scenarios": " , ".join(ids), "year": 2025}
    )
    assert response.status_code == 200, response.text
    assert [r["scenario_id"] for r in response.json()["results"]] == ids


# -- census segments -----------------------------------------------------------

ROWS = [
    # department, compensation, deferral, match, core, hce, eligible
    ("Eng", 120000.0, 0.06, 3000.0, 1000.0, "HCE", True),
    ("Eng", 80000.0, None, 0.0, 800.0, "NHCE", True),
    ("Eng", None, 0.0, 0.0, 0.0, None, False),
    ("Ops", 50000.0, 0.03, 1500.0, 0.0, "NHCE", True),
    ("Ops", 0.0, 0.1, 0.0, 0.0, "NHCE", True),
    ("O'Hare", 70000.0, 0.04, 2100.0, 700.0, "NHCE", False),
    (None, 90000.0, 0.05, 2000.0, 900.0, "NHCE", True),
]


def _analyzed(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("""
        CREATE TABLE analyzed (
          _department VARCHAR, _compensation DOUBLE, _deferral_rate DOUBLE,
          _employer_match DOUBLE, _employer_core DOUBLE, _hce_label VARCHAR,
          _eligible BOOLEAN
        )
        """)
    conn.executemany("INSERT INTO analyzed VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return conn


def _per_value(service, conn, averages: _AverageOptions) -> list[dict]:
    """The previous approach: one filtered scan per distinct value."""
    values = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT _department FROM analyzed "
            "WHERE _department IS NOT NULL ORDER BY 1"
        ).fetchall()
    ]
    result = []
    for value in values:
        literal = "'" + value.replace("'", "''") + "'"
        metrics = service._metrics_for_filter(
            conn, f"_department = {literal}", averages
        )
        result.append(
            {"dimension": "department", "value": value, **metrics.model_dump()}
        )
    return result


@pytest.mark.parametrize("exclude_zeros", [False, True])
@pytest.mark.parametrize("has_deferral", [False, True])
def test_grouped_segments_match_per_value_scans(
    tmp_path: Path, exclude_zeros: bool, has_deferral: bool
) -> None:
    service = CensusAnalysisService(tmp_path)
    averages = _AverageOptions(exclude_zeros=exclude_zeros, has_deferral=has_deferral)
    conn = _analyzed(ROWS)
    grouped = service._segment_by_column(conn, "department", "_department", averages)
    assert [s.model_dump() for s in grouped] == _per_value(service, conn, averages)
    assert [s.value for s in grouped] == ["Eng", "O'Hare", "Ops"]


def test_segments_are_capped_by_headcount(tmp_path: Path) -> None:
    service = CensusAnalysisService(tmp_path)
    total = MAX_SEGMENTS_PER_DIMENSION + 5
    # Departments d000..d004 have one employee each; the rest have two.
    rows = []
    for i in range(total):
        for _ in range(1 if i < 5 else 2):
            rows.append((f"d{i:03d}", 1000.0, 0.05, 0.0, 0.0, "NHCE", True))
    averages = _AverageOptions(exclude_zeros=False, has_deferral=True)
    segments = service._segment_by_column(
        _analyzed(rows), "department", "_department", averages
    )
    values = [s.value for s in segments]
    assert len(values) == MAX_SEGMENTS_PER_DIMENSION
    assert values == sorted(values)
    assert values[0] == "d005"
