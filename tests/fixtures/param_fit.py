"""Shared fixtures for the Studio fit & backtest API tests (#588)."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.param_fit import ParamFitJob
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import param_fits
from planalign_api.services.param_fit import ParamFitService
from planalign_api.services.param_fit.runner import JobPaths, ProcessRegistry
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_fit import FitOptions, fit_parameter_pack, render_fit_report, write_pack
from planalign_fit.diagnostics import build_diagnostics
from tests.fixtures.synthetic_census import generate_history

STUB = Path(__file__).with_name("param_fit_stub.py")
TERMINAL = {"completed", "failed", "cancelled"}


def history_files(
    directory: Path, *, years: int = 3, headcount: int = 1_200
) -> list[Path]:
    """Synthetic annual census CSVs (``census_<year>.csv``)."""
    history = generate_history(directory, headcount=headcount, years=years)
    return sorted(Path(history.directory).glob("*.csv"))


def build_fixture_pack(history_dir: Path, destination: Path) -> Path:
    """A real pack (with report + diagnostics) the stub CLI copies into jobs."""
    run = fit_parameter_pack(history_dir, FitOptions())
    return write_pack(
        run.pack,
        destination,
        report=render_fit_report(run),
        diagnostics=build_diagnostics(run),
    )


def add_current_scorecard(pack_dir: Path, verdict: str = "pass") -> None:
    """A minimal scorecard bound to the pack's fingerprint (so it is current)."""
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    scorecard = {
        "verdict": verdict,
        "verdict_summary": f"1 {verdict}",
        "scorecard_fingerprint": "f" * 64,
        "split": {"fit_years": [2022, 2023], "holdout_years": [2024]},
        "seeds": [42],
        "comparisons": [],
        "provenance": {"pack_fingerprint": manifest["fingerprint"]},
    }
    target = pack_dir / "backtest"
    target.mkdir(parents=True, exist_ok=True)
    (target / "scorecard.json").write_text(json.dumps(scorecard))
    (target / "scorecard.md").write_text("# Backtest scorecard\n")


@dataclass
class StubCommands:
    """Command factory routing each job to a stub behaviour."""

    fixture_pack: Path
    behaviour: str = "success"
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, job: ParamFitJob, paths: JobPaths) -> list[str]:
        command = [
            sys.executable,
            str(STUB),
            self.behaviour,
            str(paths.pack_dir),
            str(self.fixture_pack),
        ]
        self.calls.append(command)
        return command


@dataclass
class Harness:
    storage: WorkspaceStorage
    workspace_id: str
    scenario_id: str
    client: TestClient
    registry: ProcessRegistry
    commands: Callable
    max_jobs: int = 20

    def service(self, registry: Optional[ProcessRegistry] = None) -> ParamFitService:
        return ParamFitService(
            self.storage,
            registry=registry or self.registry,
            command_factory=self.commands,
            max_jobs_per_workspace=self.max_jobs,
        )

    def url(self, suffix: str = "") -> str:
        return f"/api/workspaces/{self.workspace_id}{suffix}"

    def upload(self, files: list[Path]):
        return self.client.post(
            self.url("/fit-history"),
            files=[("files", (p.name, p.read_bytes(), "text/csv")) for p in files],
        )

    def start(self, history_id: str, /, **overrides):
        body = {"history_id": history_id, "base_scenario_id": self.scenario_id}
        body.update(overrides)
        return self.client.post(self.url("/param-fits"), json=body)

    def wait(self, job_id: str, timeout: float = 60.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.client.get(self.url(f"/param-fits/{job_id}")).json()
            if job["status"] in TERMINAL:
                return job
            time.sleep(0.1)
        raise AssertionError(f"job {job_id} did not finish within {timeout}s")

    def wait_for_stage(self, job_id: str, stage: str, timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.client.get(self.url(f"/param-fits/{job_id}")).json()
            if job["progress"]["stage"] == stage or job["status"] in TERMINAL:
                return job
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} never reached stage {stage}")


def make_harness(
    root: Path,
    commands: Callable,
    *,
    registry: Optional[ProcessRegistry] = None,
    max_jobs: int = 20,
) -> Harness:
    storage = WorkspaceStorage(root / "workspaces")
    base_config = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    workspace = storage.create_workspace(
        WorkspaceCreate(name="Fit workspace"), base_config
    )
    scenario = storage.create_scenario(
        workspace.id, ScenarioCreate(name="Baseline", config_overrides={})
    )
    assert scenario is not None
    registry = registry or ProcessRegistry()
    app = FastAPI()
    app.include_router(param_fits.router, prefix="/api/workspaces")
    harness = Harness(
        storage=storage,
        workspace_id=workspace.id,
        scenario_id=scenario.id,
        client=TestClient(app),
        registry=registry,
        commands=commands,
        max_jobs=max_jobs,
    )
    app.dependency_overrides[
        param_fits.get_param_fit_service
    ] = lambda: harness.service()
    return harness
