"""Unit tests for config, band label, path, and template validation hardening."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.config import APISettings
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import optimizer as optimizer_router
from planalign_api.routers import workspaces as workspaces_router
from planalign_api.services.param_fit.service import ParamFitError, ParamFitService
from planalign_api.services.seed_config_validator import validate_bands
from planalign_api.services.sql_security import (
    SQLSecurityError,
    validate_file_path_for_sql,
)
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_fit.bands import (
    MAX_BAND_LABEL_LENGTH,
    Band,
    BandDefinitionError,
    _band_case,
    _parse_bands,
)

pytestmark = pytest.mark.fast

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT_ROOT = REPO_ROOT / "dbt"


def _valid_age_bands() -> list[dict[str, Any]]:
    return [
        {
            "band_id": 1,
            "band_label": "< 25",
            "min_value": 0,
            "max_value": 25,
            "display_order": 1,
        },
        {
            "band_id": 2,
            "band_label": "25+",
            "min_value": 25,
            "max_value": 120,
            "display_order": 2,
        },
    ]


# ---------------------------------------------------------------------------
# Part 1: fit band labels, seed validator, POST /workspaces, param_fit inputs
# ---------------------------------------------------------------------------


def test_band_case_escapes_single_quotes() -> None:
    bands = [
        Band(
            band_id=1,
            label="O'Brien",
            min_value=0.0,
            max_value=25.0,
            display_order=1,
        )
    ]
    sql = _band_case("age", bands)
    assert "THEN 'O''Brien'" in sql
    assert "ELSE 'O''Brien'" in sql
    assert "THEN 'O'Brien'" not in sql


@pytest.mark.parametrize(
    "bad_label",
    [
        "x' END --",
        "line\nbreak",
        "tab\there",
        "null\x00byte",
        "del\x7fchar",
        "x" * (MAX_BAND_LABEL_LENGTH + 1),
        "",
    ],
)
def test_parse_bands_rejects_bad_labels(bad_label: str, tmp_path: Path) -> None:
    rows = [
        {
            "band_id": "1",
            "band_label": bad_label,
            "min_value": "0",
            "max_value": "25",
            "display_order": "1",
        }
    ]
    with pytest.raises(BandDefinitionError):
        _parse_bands(rows, tmp_path / "config_age_bands.csv")


@pytest.mark.parametrize(
    "bad_label",
    [
        "x' END --",
        "bad\nlabel",
        "bad\x00label",
        "x" * (MAX_BAND_LABEL_LENGTH + 1),
    ],
)
def test_seed_config_validator_rejects_bad_band_labels(bad_label: str) -> None:
    bands = _valid_age_bands()
    bands[0]["band_label"] = bad_label
    errors = validate_bands(bands, "age")
    assert [e.field for e in errors] == ["band[0].band_label"]


def test_post_workspace_rejects_bad_band_label_with_422(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    app = FastAPI()
    app.include_router(workspaces_router.router, prefix="/api/workspaces")
    app.dependency_overrides[workspaces_router.get_storage] = lambda: storage
    app.dependency_overrides[workspaces_router.get_default_config] = lambda: {}
    client = TestClient(app)

    bad_bands = _valid_age_bands()
    bad_bands[0]["band_label"] = "bad'label"

    resp = client.post(
        "/api/workspaces",
        json={"name": "Bad Bands WS", "base_config": {"age_bands": bad_bands}},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["message"] == "Validation failed"
    assert detail["errors"] == [
        {
            "section": "age_bands",
            "field": "band[0].band_label",
            "message": "band_label must be text without single quotes",
        }
    ]

    ok_resp = client.post(
        "/api/workspaces",
        json={
            "name": "Good Bands WS",
            "base_config": {"age_bands": _valid_age_bands()},
        },
    )
    assert ok_resp.status_code == 201


def test_param_fit_prepare_inputs_rejects_invalid_stored_seed_config(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path)
    bad_bands = _valid_age_bands()
    bad_bands[0]["band_label"] = "legacy'bad"
    workspace = storage.create_workspace(
        WorkspaceCreate(name="Legacy WS"),
        {"age_bands": bad_bands},
    )
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="Baseline"))
    assert scenario is not None
    service = ParamFitService(storage)

    from datetime import datetime, timezone

    from planalign_api.models.param_fit import JobInputs, ParamFitJob, ParamFitRequest

    job = ParamFitJob(
        job_id="fit_test123",
        workspace_id=workspace.id,
        mode="fit",
        status="queued",
        created_at=datetime.now(timezone.utc),
        request=ParamFitRequest(history_id="hist_1", base_scenario_id=scenario.id),
        inputs=JobInputs(
            history_id="hist_1",
            source_digest="d",
            snapshots=[],
            base_scenario_id=scenario.id,
            base_scenario_name=scenario.name,
            base_scenario_fingerprint="f",
        ),
    )

    merged = storage.get_merged_config(workspace.id, scenario.id) or {}
    with pytest.raises(ParamFitError) as exc_info:
        service._prepare_inputs(job, merged, scenario)
    assert exc_info.value.status == 422
    assert "age_bands" in exc_info.value.detail
    assert not service.jobs.inputs_dir(workspace.id, job.job_id).exists()


# ---------------------------------------------------------------------------
# Part 3: optimizer output path components and sql_security path characters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_dir",
    [
        ".hidden",
        "-leading-dash",
        "dir with spaces",
        "bad'quote",
        "bad{brace}",
        "bad%pct",
        "nested/.hidden",
        "good/../also_good",
    ],
)
def test_optimizer_output_paths_reject_unsafe_components(
    tmp_path: Path, bad_dir: str
) -> None:
    runs_root = tmp_path / "optimizer_runs"
    runs_root.mkdir()
    settings = APISettings(optimizer_runs_root=runs_root)

    with pytest.raises(ValueError, match="optimizer output directories"):
        optimizer_router._api_output_paths(bad_dir, None, settings)
    with pytest.raises(ValueError, match="optimizer output directories"):
        optimizer_router._api_output_paths(None, bad_dir, settings)
    if "/" not in bad_dir:
        with pytest.raises(ValueError, match="optimizer output directories"):
            optimizer_router._api_output_paths(str(runs_root / bad_dir), None, settings)


def test_optimizer_output_paths_accept_valid_components(tmp_path: Path) -> None:
    runs_root = tmp_path / "optimizer_runs"
    runs_root.mkdir()
    settings = APISettings(optimizer_runs_root=runs_root)

    db_dir, out_dir = optimizer_router._api_output_paths(
        "run_1.0/sub-dir", str(runs_root / "out_2.0"), settings
    )
    assert db_dir == (runs_root / "run_1.0" / "sub-dir").resolve()
    assert out_dir == (runs_root / "out_2.0").resolve()


@pytest.mark.parametrize("bad_char", ["{", "}", "%"])
def test_validate_file_path_for_sql_rejects_template_characters(
    tmp_path: Path, bad_char: str
) -> None:
    target = tmp_path / f"census_{bad_char}_2025.parquet"
    with pytest.raises(SQLSecurityError):
        validate_file_path_for_sql(target, [tmp_path], context="census")


def test_validate_file_path_for_sql_accepts_normal_path(tmp_path: Path) -> None:
    target = tmp_path / "census_2025.parquet"
    assert validate_file_path_for_sql(target, [tmp_path], context="census") == str(
        target.resolve()
    )


# ---------------------------------------------------------------------------
# Part 2b: Jinja macro rendering preserves exact SQL semantics
# ---------------------------------------------------------------------------


def test_jinja_macros_render_expected_typed_sql() -> None:
    env = jinja2.Environment()

    pay_scale_src = (DBT_ROOT / "macros" / "pay_scale_level.sql").read_text()
    env.globals["var"] = lambda name, default=None: (
        [
            {"level": 1, "min_compensation": 50000, "max_compensation": 80000},
            {"level": 2, "min_compensation": 80000, "max_compensation": 120000},
        ]
        if name == "job_level_compensation"
        else default
    )
    pay_sql = env.from_string(pay_scale_src).module.pay_scale_level("comp")
    assert "WHEN comp >= 80000.0 THEN 2" in pay_sql
    assert "ELSE 1" in pay_sql

    tiers_src = (DBT_ROOT / "macros" / "get_tenure_graded_match_tiers.sql").read_text()
    tiers_sql = env.from_string(tiers_src).module.get_tenure_graded_match_tiers(
        [
            {
                "min_years": 0,
                "max_years": None,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.05, "match_rate": 1.0}
                ],
            }
        ]
    )
    assert "0 AS band_min_years" in tiers_sql
    assert "NULL AS band_max_years" in tiers_sql
    assert "0.05 AS employee_max" in tiers_sql

    cal_src = (DBT_ROOT / "macros" / "utils" / "census_plan_calendar.sql").read_text()
    env.globals["var"] = lambda name, default=None: {
        "plan_year_start_date": "2025-01-01",
        "plan_year_end_date": "2025-12-31",
    }.get(name, default)
    cal_sql = env.from_string(cal_src).module.census_plan_calendar("raw_data")
    assert "CAST('2025-01-01' AS DATE)" in cal_sql
    assert "CAST('2025-12-31' AS DATE)" in cal_sql
