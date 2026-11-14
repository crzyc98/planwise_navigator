"""Like-for-like verdicts for compared scenarios (#1179).

Every fixture is synthetic and lives under pytest's tmp_path.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from _version import __version__
from planalign_api.models.comparison import ComparisonIntegrityResponse
from planalign_api.models.provenance import (
    ConfigurationEvidence,
    ExecutionTimingEvidence,
    InputFingerprint,
    RunIdentityEvidence,
    RunProvenanceManifest,
    SoftwareEvidence,
)
from planalign_api.models.scenario import Scenario
from planalign_api.routers import analytics as analytics_router
from planalign_api.services import run_trust as run_trust_module
from planalign_api.services.comparison_integrity import (
    ComparisonIntegrityService,
    config_group,
)
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from tests.fixtures.scenario_diff import create_scenario_database

pytestmark = [pytest.mark.fast]

CENSUS_A = "a" * 64
CENSUS_B = "b" * 64
BASE_CONFIG: dict[str, Any] = {
    "simulation": {
        "name": "Baseline",
        "start_year": 2026,
        "end_year": 2028,
        "random_seed": 42,
        "target_growth_rate": 0.03,
    },
    "setup": {"census_parquet_path": "data/census_a.parquet"},
    "workforce": {"total_termination_rate": 0.12},
    "dc_plan": {"match_template": "simple", "match_cap_percent": 0.04},
}


def _run(
    root: Path,
    scenario_id: str,
    *,
    config: dict[str, Any] | None = None,
    seed: int = 42,
    census: str | None = CENSUS_A,
    version: str = __version__,
    years: tuple[int, int] = (2026, 2028),
    manifest: bool = True,
) -> ResolvedDatabasePath:
    """Write one synthetic managed run and return how the resolver sees it."""
    run_id = str(uuid.uuid4())
    run_dir = root / scenario_id / "runs" / run_id
    run_dir.mkdir(parents=True)
    run_config = copy.deepcopy(config if config is not None else BASE_CONFIG)
    config_path = run_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(run_config), encoding="utf-8")
    database = create_scenario_database(
        run_dir,
        "simulation",
        metadata=[
            {
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc),
                "fingerprint": "1" * 64,
                "seed": seed,
                "version": version,
            }
        ],
    )
    if manifest:
        _write_manifest(run_dir, run_id, seed=seed, census=census, version=version)
    return ResolvedDatabasePath(
        path=database,
        source="run",
        run_id=run_id,
        config_path=config_path,
        start_year=years[0],
        end_year=years[1],
    )


def _write_manifest(
    run_dir: Path, run_id: str, *, seed: int, census: str | None, version: str
) -> None:
    manifest = RunProvenanceManifest(
        run_id=run_id,
        capture_state="completed",
        run_identity=RunIdentityEvidence(run_id=run_id, status="completed"),
        execution_timing=ExecutionTimingEvidence(),
        software=SoftwareEvidence(planalign_version=version),
        configuration=ConfigurationEvidence(),
        random_seed=seed,
        census_input=(
            InputFingerprint(logical_name="census.parquet", sha256=census)
            if census
            else None
        ),
        started_at=datetime.now(timezone.utc),
        finalized_at=datetime.now(timezone.utc),
    )
    (run_dir / "provenance.json").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )


def _evaluate(
    runs: dict[str, ResolvedDatabasePath],
    current: dict[str, dict[str, Any]] | None = None,
    anchor: str = "a",
) -> ComparisonIntegrityResponse:
    storage = MagicMock()
    storage.get_merged_config_for.side_effect = lambda _, scenario_id: (
        (current or {}).get(scenario_id)
    )
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda _ws, scenario_id, **_: runs[scenario_id]
    workspace = MagicMock()
    workspace.id = "ws"
    service = ComparisonIntegrityService(storage, resolver)
    return service.evaluate(
        workspace, {sid: sid.upper() for sid in runs}, anchor_id=anchor
    )


def _with(path: str, value: Any) -> dict[str, Any]:
    config = copy.deepcopy(BASE_CONFIG)
    section, key = path.split(".", 1)
    config.setdefault(section, {})[key] = value
    return config


def _codes(result: ComparisonIntegrityResponse) -> list[str]:
    return [reason.code for reason in result.scenarios[0].reasons]


def test_plan_design_only_difference_is_like_for_like(tmp_path: Path) -> None:
    result = _evaluate(
        {
            "a": _run(tmp_path, "a"),
            "b": _run(tmp_path, "b", config=_with("dc_plan.match_cap_percent", 0.06)),
        }
    )

    verdict = result.scenarios[0]
    assert verdict.verdict == "like_for_like"
    assert verdict.reasons == []
    assert [d.path for d in verdict.plan_design_differences] == [
        "dc_plan.match_cap_percent"
    ]
    assert result.anchor_engine_version == __version__


def test_scenario_name_and_census_path_alone_do_not_break(tmp_path: Path) -> None:
    renamed = _with("simulation.name", "Richer match")
    renamed["setup"]["census_parquet_path"] = "elsewhere/census_a.parquet"
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b", config=renamed)}
    )

    assert result.scenarios[0].verdict == "like_for_like"


@pytest.mark.parametrize(
    ("overrides", "code", "anchor_value", "scenario_value"),
    [
        ({"seed": 7}, "seed_differs", 42, 7),
        (
            {
                "census": CENSUS_B,
                "config": {
                    **BASE_CONFIG,
                    "setup": {"census_parquet_path": "data/census_b.parquet"},
                },
            },
            "census_differs",
            "census_a.parquet",
            "census_b.parquet",
        ),
        ({"years": (2026, 2030)}, "years_differ", "2026–2028", "2026–2030"),
        ({"version": "3.1.9"}, "engine_version_differs", __version__, "3.1.9"),
    ],
)
def test_each_run_mismatch_breaks_with_both_values(
    tmp_path: Path,
    overrides: dict[str, Any],
    code: str,
    anchor_value: Any,
    scenario_value: Any,
) -> None:
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b", **overrides)}
    )

    verdict = result.scenarios[0]
    assert verdict.verdict == "not_like_for_like"
    reason = next(item for item in verdict.reasons if item.code == code)
    assert reason.effect == "breaks"
    assert (reason.anchor_value, reason.scenario_value) == (
        anchor_value,
        scenario_value,
    )


def test_growth_rate_difference_is_workforce_and_pay(tmp_path: Path) -> None:
    result = _evaluate(
        {
            "a": _run(tmp_path, "a"),
            "b": _run(
                tmp_path, "b", config=_with("simulation.target_growth_rate", 0.05)
            ),
        }
    )

    verdict = result.scenarios[0]
    assert verdict.verdict == "not_like_for_like"
    [reason] = verdict.reasons
    assert reason.code == "config_differs"
    assert reason.group == "workforce_and_pay"
    assert reason.path == "simulation.target_growth_rate"
    assert (reason.anchor_value, reason.scenario_value) == (0.03, 0.05)


def test_unmapped_config_path_counts_as_other_and_breaks(tmp_path: Path) -> None:
    config = copy.deepcopy(BASE_CONFIG)
    config["brand_new_section"] = {"knob": 1}
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b", config=config)}
    )

    verdict = result.scenarios[0]
    assert verdict.verdict == "not_like_for_like"
    assert verdict.reasons[0].group == "other"


def test_behavior_assumption_breaks(tmp_path: Path) -> None:
    result = _evaluate(
        {
            "a": _run(tmp_path, "a"),
            "b": _run(tmp_path, "b", config=_with("dc_plan.opt_out_rate_target", 0.2)),
        }
    )

    assert result.scenarios[0].reasons[0].group == "employee_behavior"
    assert result.scenarios[0].verdict == "not_like_for_like"


def test_edited_since_run_is_a_note_and_keeps_the_verdict(tmp_path: Path) -> None:
    edited = _with("simulation.random_seed", 99)
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b")},
        current={"a": BASE_CONFIG, "b": edited},
    )

    verdict = result.scenarios[0]
    assert verdict.verdict == "like_for_like"
    [note] = verdict.reasons
    assert (note.code, note.effect, note.scenario_id) == (
        "edited_since_run",
        "note",
        "b",
    )


def test_config_edit_after_run_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        run_trust_module.SimulationConfig, "model_validate", lambda _: object()
    )
    monkeypatch.setattr(
        run_trust_module, "compute_config_fingerprint", lambda _: "f" * 64
    )
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b")},
        current={"a": BASE_CONFIG, "b": BASE_CONFIG},
    )

    notes = {(item.code, item.scenario_id) for item in result.scenarios[0].reasons}
    assert notes == {("edited_since_run", "a"), ("edited_since_run", "b")}
    assert result.scenarios[0].verdict == "like_for_like"


def test_missing_provenance_is_unknown_never_like_for_like(tmp_path: Path) -> None:
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b", manifest=False)}
    )

    verdict = result.scenarios[0]
    assert verdict.verdict == "unknown"
    assert [(item.check, item.scenario_id) for item in verdict.unevaluated] == [
        ("census", "b")
    ]


def test_missing_census_hash_is_unknown(tmp_path: Path) -> None:
    result = _evaluate(
        {"a": _run(tmp_path, "a", census=None), "b": _run(tmp_path, "b")}
    )

    [missing] = result.scenarios[0].unevaluated
    assert (missing.check, missing.scenario_id, missing.cause) == (
        "census",
        "a",
        "not_recorded",
    )
    assert result.scenarios[0].verdict == "unknown"


def test_no_result_database_is_unknown(tmp_path: Path) -> None:
    result = _evaluate({"a": _run(tmp_path, "a"), "b": ResolvedDatabasePath()})

    verdict = result.scenarios[0]
    assert verdict.verdict == "unknown"
    assert {item.cause for item in verdict.unevaluated} == {"no_run_record"}
    assert {item.check for item in verdict.unevaluated} == {
        "census",
        "seed",
        "years",
        "engine_version",
        "config",
    }


def test_breaking_reason_wins_over_unknown(tmp_path: Path) -> None:
    result = _evaluate(
        {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b", manifest=False, seed=1)}
    )

    assert result.scenarios[0].verdict == "not_like_for_like"


def test_anchor_choice_and_multiple_scenarios(tmp_path: Path) -> None:
    runs = {
        "a": _run(tmp_path, "a"),
        "b": _run(tmp_path, "b", seed=7),
        "c": _run(tmp_path, "c", seed=7),
    }
    result = _evaluate(runs, anchor="b")

    by_id = {item.scenario_id: item.verdict for item in result.scenarios}
    assert result.anchor_scenario_id == "b"
    assert by_id == {"a": "not_like_for_like", "c": "like_for_like"}


def test_databases_open_read_only_once_per_scenario(
    tmp_path: Path, monkeypatch
) -> None:
    runs = {"a": _run(tmp_path, "a"), "b": _run(tmp_path, "b")}
    calls: list[tuple[str, bool]] = []
    real_connect = run_trust_module.duckdb.connect

    def counting_connect(path: str, read_only: bool = False) -> Any:
        calls.append((Path(path).parent.parent.parent.name, read_only))
        return real_connect(path, read_only=read_only)

    monkeypatch.setattr(run_trust_module.duckdb, "connect", counting_connect)
    _evaluate(runs)

    assert sorted(calls) == [("a", True), ("b", True)]


@pytest.mark.parametrize(
    ("path", "group"),
    [
        ("dc_plan.match_tiers", "plan_design"),
        ("dc_plan.match_magnet_probability", "employee_behavior"),
        ("dc_plan.core_contribution_rate_percent", "plan_design"),
        (
            "dc_plan.escalation_participant_elected_signup_probability",
            "employee_behavior",
        ),
        ("dc_plan.escalation_rate_percent", "plan_design"),
        ("dc_plan.auto_enroll_scope", "plan_design"),
        ("enrollment.auto_enrollment.scope", "plan_design"),
        ("enrollment.auto_enrollment.opt_out_rates.target", "employee_behavior"),
        ("enrollment.voluntary_enrollment.base_rates_by_age", "employee_behavior"),
        ("compensation.merit_budget_percent", "workforce_and_pay"),
        ("simulation.target_growth_rate", "workforce_and_pay"),
        ("employer_matchmaker", "other"),
        ("advanced.engine", "other"),
    ],
)
def test_config_group_map(path: str, group: str) -> None:
    assert config_group(path) == group


def _scenario(scenario_id: str) -> Scenario:
    return Scenario(
        id=scenario_id,
        workspace_id="ws",
        name=scenario_id.upper(),
        status="completed",
        created_at=datetime.now(timezone.utc),
    )


def _client(storage: MagicMock, service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(analytics_router.router, prefix="/api/workspaces")
    app.dependency_overrides[analytics_router.get_storage] = lambda: storage
    app.dependency_overrides[analytics_router.get_comparison_integrity_service] = (
        lambda: service
    )
    return TestClient(app)


def test_endpoint_defaults_anchor_and_validates(tmp_path: Path) -> None:
    storage = MagicMock()
    storage.get_workspace.return_value = MagicMock(id="ws")
    storage.get_scenario.side_effect = lambda _, scenario_id: _scenario(scenario_id)
    storage._scenario_path.side_effect = lambda _, scenario_id: tmp_path / scenario_id
    service = MagicMock()
    service.evaluate.return_value = ComparisonIntegrityResponse(
        anchor_scenario_id="a", anchor_scenario_name="A", scenarios=[]
    )
    client = _client(storage, service)
    url = "/api/workspaces/ws/analytics/compare/integrity"

    assert client.get(f"{url}?scenarios=a,b").status_code == 200
    assert service.evaluate.call_args.args[2] == "a"
    assert client.get(f"{url}?scenarios=a,b&anchor=b").status_code == 200
    assert service.evaluate.call_args.args[2] == "b"
    assert client.get(f"{url}?scenarios=a").status_code == 400
    assert client.get(f"{url}?scenarios=a,b&anchor=z").status_code == 400
    too_many = ",".join(
        f"s{i}" for i in range(analytics_router.MAX_SCENARIO_COMPARISON + 1)
    )
    assert client.get(f"{url}?scenarios={too_many}").status_code == 400
