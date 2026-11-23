"""Fast API containment tests for optimizer and ensemble path parameters."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.config import APISettings
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import ensembles as ensembles_router
from planalign_api.routers import optimizer as optimizer_router
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_ensemble.studio_reader import (
    discover_ensemble_databases,
    validate_ensemble_database,
)
from planalign_optimizer.models import (
    Candidate,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerRun,
)
from planalign_optimizer.paths import resolve_output_paths

pytestmark = [pytest.mark.fast]


def _write_ensemble_db(path: Path, *, with_distributions: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as conn:
        if not with_distributions:
            conn.execute("CREATE TABLE unrelated (id INTEGER)")
            return
        conn.execute(
            "CREATE TABLE fct_metric_distributions ("
            "ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, "
            "simulation_year INTEGER, p10 DOUBLE, p25 DOUBLE, p50 DOUBLE, "
            "p75 DOUBLE, p90 DOUBLE, mean DOUBLE, stddev DOUBLE, "
            "n_seeds INTEGER, n_seeds_requested INTEGER, is_sufficient BOOLEAN, "
            "percentile_method VARCHAR)"
        )
        conn.execute(
            "INSERT INTO fct_metric_distributions VALUES "
            "('ens-1', 'baseline', 'total_employer_plan_cost', 2029, "
            "1.0, 2.0, 3.0, 4.0, 5.0, 3.0, 1.0, 10, 10, TRUE, 'linear')"
        )
        conn.execute(
            "CREATE TABLE fct_metric_seed_values ("
            "ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, "
            "simulation_year INTEGER, seed BIGINT, value DOUBLE)"
        )
        conn.executemany(
            "INSERT INTO fct_metric_seed_values VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("ens-1", "baseline", "total_employer_plan_cost", 2029, s, float(s))
                for s in range(1, 11)
            ],
        )
        conn.execute(
            "CREATE TABLE fct_variance_attribution ("
            "ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, "
            "simulation_year INTEGER, subsystem VARCHAR, variance_share DOUBLE, "
            "ci_low DOUBLE, ci_high DOUBLE, baseline_variance DOUBLE, "
            "frozen_variance DOUBLE, anchor_seeds VARCHAR, n_anchors INTEGER, "
            "n_seeds INTEGER, bootstrap_iterations INTEGER, baselines_reused INTEGER, "
            "baselines_executed INTEGER, stochastic_status VARCHAR)"
        )
        conn.execute(
            "INSERT INTO fct_variance_attribution VALUES "
            "('ens-1', 'baseline', 'total_employer_plan_cost', 2029, 'termination', "
            "0.61, 0.50, 0.70, 10, 3.9, '1,2,3', 3, 10, 2000, 10, 0, 'stochastic')"
        )


def _sample_run(database_dir: Path) -> OptimizerRun:
    return OptimizerRun(
        run_id="run-0000",
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="auto_enrollment.default_deferral_rate",
                    kind="continuous",
                    bounds=(0.03, 0.08),
                ),
            )
        ),
        objective_constraint_spec=ObjectiveConstraintSpec(
            objectives=(
                ObjectiveTerm(metric="participation_rate", direction="maximize"),
            )
        ),
        max_runs=2,
        search_seed=0,
        baseline_config_fingerprint="fp-test",
        candidates=(
            Candidate(
                candidate_id="candidate-0000",
                lever_values={"auto_enrollment.default_deferral_rate": 0.05},
                db_path=database_dir
                / "candidates"
                / "candidate-0000"
                / "scenario.duckdb",
                status="feasible",
                objective_values={"participation_rate": 0.87},
            ),
        ),
        ranked_feasible=("candidate-0000",),
    )


def _spec(
    config_path: str = "simulation_config.yaml",
    ensemble_database: str | None = None,
) -> dict[str, Any]:
    baseline: dict[str, Any] = {"config_path": config_path}
    if ensemble_database is not None:
        baseline["ensemble_database"] = ensemble_database
    return {
        "design_space": {
            "levers": [
                {
                    "name": "auto_enrollment.default_deferral_rate",
                    "kind": "continuous",
                    "bounds": [0.03, 0.08],
                }
            ]
        },
        "objective": {
            "objectives": [{"metric": "participation_rate", "direction": "maximize"}]
        },
        "baseline": baseline,
    }


def _await_optimizer_job(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        resp = client.get(f"/api/optimizer/runs/{run_id}")
        assert resp.status_code == 200
        job = resp.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"Optimizer job {run_id} did not finish")


@pytest.fixture(autouse=True)
def _reset_optimizer_state() -> Iterator[None]:
    optimizer_router._reserved_dirs.clear()
    optimizer_router._jobs.clear()
    yield
    optimizer_router._reserved_dirs.clear()
    optimizer_router._jobs.clear()


@pytest.fixture
def sandbox(tmp_path: Path) -> dict[str, Any]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default_config = config_dir / "simulation_config.yaml"
    shutil.copyfile(Path("config/simulation_config.yaml"), default_config)

    runs_root = tmp_path / "optimizer_runs"
    runs_root.mkdir()
    ensembles_root = tmp_path / "ensembles"
    ensembles_root.mkdir()
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    settings = APISettings(
        default_config_path=default_config,
        optimizer_runs_root=runs_root,
        ensembles_root=ensembles_root,
        workspaces_root=workspaces_root,
    )
    storage = WorkspaceStorage(workspaces_root)

    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api")
    app.include_router(ensembles_router.router, prefix="/api")
    app.dependency_overrides[optimizer_router.get_settings] = lambda: settings
    app.dependency_overrides[optimizer_router.get_storage] = lambda: storage
    app.dependency_overrides[ensembles_router.get_settings] = lambda: settings

    return {
        "client": TestClient(app),
        "settings": settings,
        "storage": storage,
        "config_dir": config_dir,
        "runs_root": runs_root,
        "ensembles_root": ensembles_root,
        "workspaces_root": workspaces_root,
        "outside": outside,
    }


# ---------------------------------------------------------------------------
# Optimizer output directories (database_dir, output_dir)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["database_dir", "output_dir"])
def test_optimizer_rejects_outside_traversal_and_symlink_output_dirs(
    sandbox: dict[str, Any], monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    called = False

    def _never(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("run_optimizer must not run for rejected paths")

    monkeypatch.setattr(optimizer_router, "run_optimizer", _never)
    client: TestClient = sandbox["client"]
    runs_root: Path = sandbox["runs_root"]
    outside: Path = sandbox["outside"]

    symlink_target = outside / f"sym_{field}_target"
    escaping_link = runs_root / f"link_{field}"
    escaping_link.symlink_to(symlink_target)

    bad_values = [
        str(outside / f"abs_{field}"),
        f"../outside/rel_{field}",
        f"nested/../../outside/rel2_{field}",
        str(escaping_link),
        str(escaping_link / "child"),
        f"link_{field}/child",
        ".hidden_dir",
        "-leading_dash",
        "dir with spaces",
        "bad{brace}",
        "bad%pct",
    ]
    # An absolute, valid baseline so nothing but the directory can fail.
    config = str(sandbox["config_dir"] / "simulation_config.yaml")
    for value in bad_values:
        resp = client.post(
            "/api/optimizer/run",
            json={"spec": _spec(config_path=config), "max_runs": 2, field: value},
        )
        assert resp.status_code == 422, (value, resp.text)
        assert resp.json()["detail"] == optimizer_router._OUTPUT_DIR_ERROR
        assert str(runs_root) not in resp.text

    assert not called
    assert list(outside.iterdir()) == []


def test_optimizer_studio_style_runs_write_under_runs_root(
    sandbox: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_run(
        spec: Any, baseline: Any, *, database_dir: Path, **kwargs: Any
    ) -> tuple[OptimizerRun, None]:
        return _sample_run(database_dir), None

    monkeypatch.setattr(optimizer_router, "run_optimizer", _fake_run)
    client: TestClient = sandbox["client"]
    runs_root: Path = sandbox["runs_root"].resolve()
    storage: WorkspaceStorage = sandbox["storage"]

    # Studio default: no workspace_id, no directory overrides.
    resp = client.post("/api/optimizer/run", json={"spec": _spec(), "max_runs": 2})
    assert resp.status_code == 202, resp.text
    job = _await_optimizer_job(client, resp.json()["run_id"])
    assert job["status"] == "completed"
    assert Path(job["output_dir"]).parent == runs_root
    assert (Path(job["output_dir"]) / "optimizer_results.json").is_file()

    # Studio's advanced overrides: relative to the runs root, or absolute in it.
    for field, value in (
        ("database_dir", "named_run"),
        ("output_dir", str(runs_root / "named_out")),
    ):
        resp = client.post(
            "/api/optimizer/run",
            json={"spec": _spec(), "max_runs": 2, field: value},
        )
        assert resp.status_code == 202, resp.text
        assert Path(resp.json()[field]) == runs_root / Path(value).name
        _await_optimizer_job(client, resp.json()["run_id"])

    # Workspace baseline: the caller's config_path is ignored, output stays put.
    base_cfg = yaml.safe_load(
        (sandbox["config_dir"] / "simulation_config.yaml").read_text()
    )
    ws = storage.create_workspace(WorkspaceCreate(name="WS1"), base_cfg)
    ws_resp = client.post(
        "/api/optimizer/run",
        json={
            "spec": _spec(config_path="/nonexistent/ignored.yaml"),
            "max_runs": 2,
            "workspace_id": ws.id,
        },
    )
    assert ws_resp.status_code == 202, ws_resp.text
    ws_job = _await_optimizer_job(client, ws_resp.json()["run_id"])
    assert ws_job["status"] == "completed"
    assert Path(ws_job["output_dir"]).parent == runs_root


def test_optimizer_rejects_non_uuid_workspace_id(sandbox: dict[str, Any]) -> None:
    resp = sandbox["client"].post(
        "/api/optimizer/run",
        json={"spec": _spec(), "max_runs": 2, "workspace_id": "../outside"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workspace not found"


def test_optimizer_validate_accepts_studio_default_config_path() -> None:
    """Studio's default baseline path works with the server's default settings."""
    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api")
    resp = TestClient(app).post(
        "/api/optimizer/validate",
        json={"spec": _spec(config_path="config/simulation_config.yaml")},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True, resp.json()


# ---------------------------------------------------------------------------
# Optimizer compare_baseline_to
# ---------------------------------------------------------------------------


def test_optimizer_compare_baseline_to_rejects_outside_traversal_and_symlink(
    sandbox: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    spy_calls: list[Path] = []
    real_warning = optimizer_router.stale_baseline_warning

    def _spy(baseline: Any, path: Path) -> str | None:
        spy_calls.append(path)
        return real_warning(baseline, path)

    monkeypatch.setattr(optimizer_router, "stale_baseline_warning", _spy)
    monkeypatch.setattr(
        optimizer_router,
        "run_optimizer",
        lambda spec, baseline, *, database_dir, **kw: (_sample_run(database_dir), None),
    )

    client: TestClient = sandbox["client"]
    runs_root: Path = sandbox["runs_root"]
    outside: Path = sandbox["outside"]
    outside_json = outside / "prior.json"
    outside_json.write_text(
        '{"baseline_config_fingerprint": "SECRET_FP"}', encoding="utf-8"
    )
    link_json = runs_root / "escape_prior.json"
    link_json.symlink_to(outside_json)

    for bad in (
        str(outside_json),
        "../outside/prior.json",
        str(link_json),
        "escape_prior.json",
    ):
        resp = client.post(
            "/api/optimizer/run",
            json={
                "spec": _spec(),
                "max_runs": 2,
                "compare_baseline_to": bad,
            },
        )
        assert resp.status_code == 422, (bad, resp.text)
        assert resp.json()["detail"] == optimizer_router._COMPARE_BASELINE_ERROR
        assert "SECRET_FP" not in resp.text
        assert str(outside) not in resp.text

    assert spy_calls == []

    # Valid contained prior results file works; malformed contained file fails cleanly.
    contained_json = runs_root / "prior_ok" / "optimizer_results.json"
    contained_json.parent.mkdir()
    contained_json.write_text(
        '{"baseline_config_fingerprint": "old"}', encoding="utf-8"
    )
    ok = client.post(
        "/api/optimizer/run",
        json={
            "spec": _spec(),
            "max_runs": 2,
            "database_dir": "compare_ok",
            "compare_baseline_to": "prior_ok/optimizer_results.json",
        },
    )
    assert ok.status_code == 202, ok.text
    _await_optimizer_job(client, ok.json()["run_id"])
    assert spy_calls == [contained_json.resolve()]

    bad_json = runs_root / "bad_prior.json"
    bad_json.write_text("NOT_JSON_SECRET_TOKEN", encoding="utf-8")
    malformed = client.post(
        "/api/optimizer/run",
        json={
            "spec": _spec(),
            "max_runs": 2,
            "database_dir": "compare_bad",
            "compare_baseline_to": "bad_prior.json",
        },
    )
    assert malformed.status_code == 422
    assert "NOT_JSON_SECRET_TOKEN" not in malformed.text
    assert str(runs_root) not in malformed.text


# ---------------------------------------------------------------------------
# Optimizer spec.baseline.config_path & spec.baseline.ensemble_database
# ---------------------------------------------------------------------------


def test_optimizer_baseline_config_path_confined_and_no_oracle_or_content_leak(
    sandbox: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded_paths: list[Path] = []
    real_load = optimizer_router.load_baseline

    def _spy_load(path: Path | str) -> Any:
        loaded_paths.append(Path(path))
        return real_load(path)

    monkeypatch.setattr(optimizer_router, "load_baseline", _spy_load)

    client: TestClient = sandbox["client"]
    config_dir: Path = sandbox["config_dir"]
    outside: Path = sandbox["outside"]

    secret_yaml = outside / "secret.yaml"
    secret_yaml.write_text("simulation:\n  start_year: SECRET_LEAK_MARKER\n")
    link_yaml = config_dir / "escape.yaml"
    link_yaml.symlink_to(secret_yaml)

    # Existing outside, missing outside, traversal, and escaping symlink all
    # return the exact same generic error without ever invoking load_baseline.
    outside_cases = [
        str(secret_yaml),
        str(outside / "does_not_exist.yaml"),
        "../outside/secret.yaml",
        str(link_yaml),
        "escape.yaml",
    ]
    run_details: set[str] = set()
    validate_errors: set[str] = set()
    for bad in outside_cases:
        run_resp = client.post(
            "/api/optimizer/run",
            json={"spec": _spec(config_path=bad), "max_runs": 2},
        )
        assert run_resp.status_code == 422, (bad, run_resp.text)
        run_details.add(run_resp.json()["detail"])
        assert "SECRET_LEAK_MARKER" not in run_resp.text
        assert str(outside) not in run_resp.text

        val_resp = client.post(
            "/api/optimizer/validate",
            json={"spec": _spec(config_path=bad)},
        )
        assert val_resp.status_code == 200
        assert val_resp.json()["valid"] is False
        validate_errors.add(val_resp.json()["error"])
        assert "SECRET_LEAK_MARKER" not in val_resp.text
        assert str(outside) not in val_resp.text

    assert loaded_paths == []

    # Missing file inside config_root produces the exact same error as outside.
    missing_run = client.post(
        "/api/optimizer/run",
        json={"spec": _spec(config_path="missing.yaml"), "max_runs": 2},
    )
    assert missing_run.status_code == 422
    run_details.add(missing_run.json()["detail"])
    assert len(run_details) == 1

    missing_val = client.post(
        "/api/optimizer/validate",
        json={"spec": _spec(config_path="missing.yaml")},
    )
    assert missing_val.status_code == 200
    assert missing_val.json()["valid"] is False
    validate_errors.add(missing_val.json()["error"])
    assert len(validate_errors) == 1

    # Invalid YAML inside config_root must not echo file contents or abs paths.
    broken = config_dir / "broken.yaml"
    broken.write_text("simulation:\n  start_year: INTERNAL_ONLY_VALUE\n")
    broken_run = client.post(
        "/api/optimizer/run",
        json={"spec": _spec(config_path="broken.yaml"), "max_runs": 2},
    )
    assert broken_run.status_code == 422
    assert "INTERNAL_ONLY_VALUE" not in broken_run.text
    assert str(config_dir) not in broken_run.text

    broken_val = client.post(
        "/api/optimizer/validate",
        json={"spec": _spec(config_path="broken.yaml")},
    )
    assert broken_val.status_code == 200
    assert broken_val.json()["valid"] is False
    assert "INTERNAL_ONLY_VALUE" not in broken_val.text
    assert str(config_dir) not in broken_val.text

    # A config inside the config directory works, given absolute or relative.
    for good in (str(config_dir / "simulation_config.yaml"), "simulation_config.yaml"):
        ok_val = client.post(
            "/api/optimizer/validate",
            json={"spec": _spec(config_path=good), "max_runs": 4},
        )
        assert ok_val.status_code == 200
        assert ok_val.json()["valid"] is True, ok_val.json()


def test_optimizer_ensemble_database_field_is_confined(
    sandbox: dict[str, Any],
) -> None:
    client: TestClient = sandbox["client"]
    ensembles_root: Path = sandbox["ensembles_root"]
    outside: Path = sandbox["outside"]
    outside_db = outside / "ensemble.duckdb"
    _write_ensemble_db(outside_db)
    link_db = ensembles_root / "escape.duckdb"
    link_db.symlink_to(outside_db)

    for bad in (str(outside_db), "../outside/ensemble.duckdb", str(link_db)):
        run_resp = client.post(
            "/api/optimizer/run",
            json={"spec": _spec(ensemble_database=bad), "max_runs": 2},
        )
        assert run_resp.status_code == 422, (bad, run_resp.text)
        val_resp = client.post(
            "/api/optimizer/validate",
            json={"spec": _spec(ensemble_database=bad)},
        )
        assert val_resp.status_code == 200
        assert val_resp.json()["valid"] is False

    inside_db = ensembles_root / "run-1" / "ensemble.duckdb"
    _write_ensemble_db(inside_db)
    ok_val = client.post(
        "/api/optimizer/validate",
        json={"spec": _spec(ensemble_database=str(inside_db))},
    )
    assert ok_val.status_code == 200
    assert ok_val.json()["valid"] is True


# ---------------------------------------------------------------------------
# Ensembles root and database confinement
# ---------------------------------------------------------------------------


def test_ensembles_discover_confines_root_and_skips_escaping_symlinks(
    sandbox: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    scan_calls: list[Path] = []
    real_discover = ensembles_router.discover_ensemble_databases

    def _spy_discover(root: Path, **kwargs: Any) -> Any:
        scan_calls.append(root)
        return real_discover(root, **kwargs)

    monkeypatch.setattr(ensembles_router, "discover_ensemble_databases", _spy_discover)

    client: TestClient = sandbox["client"]
    ensembles_root: Path = sandbox["ensembles_root"]
    workspaces_root: Path = sandbox["workspaces_root"]
    outside: Path = sandbox["outside"]

    outside_db = outside / "hidden" / "ensemble.duckdb"
    _write_ensemble_db(outside_db)
    link_root = ensembles_root / "link_outside"
    link_root.symlink_to(outside)

    bad_roots = [
        str(outside),
        str(outside / "missing_dir"),
        "../outside",
        "sub/../../outside",
        str(link_root),
        "link_outside",
    ]
    details: set[str] = set()
    for bad in bad_roots:
        resp = client.get("/api/ensembles/discover", params={"root": bad})
        assert resp.status_code == 404, (bad, resp.text)
        details.add(resp.json()["detail"])
        assert str(outside) not in resp.text

    assert scan_calls == []

    # Missing directory inside ensembles_root produces the exact same 404 detail.
    missing_inside = client.get(
        "/api/ensembles/discover",
        params={"root": str(ensembles_root / "does_not_exist")},
    )
    assert missing_inside.status_code == 404
    details.add(missing_inside.json()["detail"])
    assert len(details) == 1

    # Escaping file symlink nested inside ensembles_root is skipped during scan.
    legit_db = ensembles_root / "good" / "ensemble.duckdb"
    _write_ensemble_db(legit_db)
    nested_link_dir = ensembles_root / "sneaky"
    nested_link_dir.mkdir()
    (nested_link_dir / "ensemble.duckdb").symlink_to(outside_db)

    default_resp = client.get("/api/ensembles/discover")
    assert default_resp.status_code == 200
    found_paths = [
        Path(item["database_path"]).resolve() for item in default_resp.json()
    ]
    assert found_paths == [legit_db.resolve()]

    # Workspace ensemble output directory is allowed.
    ws_job_dir = workspaces_root / "ws-1" / "ensembles" / "ens_000000000001"
    _write_ensemble_db(ws_job_dir / "ensemble.duckdb")
    ws_resp = client.get("/api/ensembles/discover", params={"root": str(ws_job_dir)})
    assert ws_resp.status_code == 200
    assert len(ws_resp.json()) == 1


@pytest.mark.parametrize(
    "endpoint,extra_params",
    [
        ("/api/ensembles/distributions", {}),
        ("/api/ensembles/risk", {"threshold": ["total_employer_plan_cost:5"]}),
        ("/api/ensembles/attribution", {}),
    ],
)
def test_ensembles_readers_confine_database_without_existence_oracle(
    sandbox: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    extra_params: dict[str, Any],
) -> None:
    opened_paths: list[Path] = []
    real_validate = ensembles_router.validate_ensemble_database

    def _spy_validate(path: Path) -> Path:
        opened_paths.append(path)
        return real_validate(path)

    monkeypatch.setattr(ensembles_router, "validate_ensemble_database", _spy_validate)

    client: TestClient = sandbox["client"]
    ensembles_root: Path = sandbox["ensembles_root"]
    workspaces_root: Path = sandbox["workspaces_root"]
    outside: Path = sandbox["outside"]

    outside_db = outside / "ensemble.duckdb"
    _write_ensemble_db(outside_db)
    link_db = ensembles_root / "escape.duckdb"
    link_db.symlink_to(outside_db)

    base_params = {
        "ensemble_scenario_id": "baseline",
        "ensemble_id": "ens-1",
        **extra_params,
    }
    bad_databases = [
        str(outside_db),
        str(outside / "nonexistent.duckdb"),
        "../outside/ensemble.duckdb",
        str(link_db),
        "escape.duckdb",
    ]
    details: set[str] = set()
    for bad in bad_databases:
        resp = client.get(endpoint, params={"database": bad, **base_params})
        assert resp.status_code == 404, (bad, resp.text)
        details.add(resp.json()["detail"])
        assert str(outside) not in resp.text

    assert opened_paths == []

    # Missing file and invalid-table file inside ensembles_root share the exact
    # same 404 detail as outside paths (no existence or table oracle).
    missing_inside = client.get(
        endpoint,
        params={"database": str(ensembles_root / "missing.duckdb"), **base_params},
    )
    assert missing_inside.status_code == 404
    details.add(missing_inside.json()["detail"])

    stray_db = ensembles_root / "stray.duckdb"
    _write_ensemble_db(stray_db, with_distributions=False)
    missing_table = client.get(
        endpoint,
        params={"database": str(stray_db), **base_params},
    )
    assert missing_table.status_code == 404
    details.add(missing_table.json()["detail"])
    assert len(details) == 1

    # Studio-style reads from ensembles_root and workspaces_root succeed.
    ens_db = ensembles_root / "run-1" / "ensemble.duckdb"
    _write_ensemble_db(ens_db)
    ws_db = (
        workspaces_root / "ws-1" / "ensembles" / "ens_000000000001" / "ensemble.duckdb"
    )
    _write_ensemble_db(ws_db)

    for allowed in (ens_db, ws_db):
        ok = client.get(endpoint, params={"database": str(allowed), **base_params})
        assert ok.status_code == 200, (allowed, ok.text)
        assert len(ok.json()) >= 1


# ---------------------------------------------------------------------------
# CLI path helpers remain unrestricted
# ---------------------------------------------------------------------------


def test_cli_path_helpers_still_accept_arbitrary_paths(tmp_path: Path) -> None:
    arb_db = tmp_path / "arbitrary" / "db"
    arb_out = tmp_path / "other_arbitrary" / "out"
    db_dir, out_dir = resolve_output_paths(arb_db, arb_out)
    assert db_dir == arb_db.resolve()
    assert out_dir == arb_out.resolve()

    arb_ens_root = tmp_path / "cli_ensembles"
    arb_ens_db = arb_ens_root / "run" / "ensemble.duckdb"
    _write_ensemble_db(arb_ens_db)
    assert validate_ensemble_database(arb_ens_db) == arb_ens_db.resolve()
    discovered = discover_ensemble_databases(arb_ens_root)
    assert [Path(item.database_path).resolve() for item in discovered] == [
        arb_ens_db.resolve()
    ]
