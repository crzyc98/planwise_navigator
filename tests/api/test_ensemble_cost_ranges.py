"""Seed ranges beside Cost Comparison: bands, seed-by-seed pairing, endpoint.

Fixture ensemble databases are written through the real
``write_ensemble_results`` and job records through the real job store, so
nothing here runs a simulation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Optional

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.ensemble_job import (
    EnsembleEstimate,
    EnsembleJob,
    EnsembleOutput,
    EnsembleProgress,
)
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import ensembles
from planalign_api.services.ensemble_jobs import EnsembleJobService
from planalign_api.services.ensemble_jobs.cost_ranges import (
    COST_METRIC,
    DIFFERENT_SEEDS,
    NO_ANCHOR_ENSEMBLE,
    NO_ENSEMBLE,
    EnsembleSeedCosts,
    build_cost_ranges,
)
from planalign_api.services.ensemble_jobs.store import EnsembleJobStore
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_ensemble.aggregate import aggregate_ensemble, write_ensemble_results
from planalign_ensemble.models import MetricSeedValue

pytestmark = [pytest.mark.fast]

SEEDS = (7, 1008, 2009, 3010, 4011, 5012)
YEARS = (2026, 2027)
# Seed-driven swings dominate each scenario's band; the plan change itself is a
# steady +100 per year on every seed.
ANCHOR = {seed: {2026: 1000.0 * i, 2027: 1500.0 * i} for i, seed in enumerate(SEEDS)}
PROPOSED = {
    seed: {year: value + 100.0 + i for year, value in ANCHOR[seed].items()}
    for i, seed in enumerate(SEEDS)
}


def _costs(
    values: Mapping[int, Mapping[int, float]],
    *,
    seeds: tuple[int, ...] = SEEDS,
    years: tuple[int, int] = (YEARS[0], YEARS[-1]),
    job_id: str = "ens_000000000001",
) -> EnsembleSeedCosts:
    return EnsembleSeedCosts(
        job_id=job_id,
        seeds=seeds,
        start_year=years[0],
        end_year=years[1],
        completed_at=None,
        values=values,
    )


def _build(proposed: Optional[EnsembleSeedCosts], anchor: Optional[EnsembleSeedCosts]):
    result = build_cost_ranges(["a", "p"], "a", {"a": anchor, "p": proposed})
    return {item.scenario_id: item for item in result.scenarios}


# ---------------------------------------------------------------------------
# Pairing (pure)
# ---------------------------------------------------------------------------


def test_same_seeds_pair_and_differences_are_taken_seed_by_seed() -> None:
    ranges = _build(_costs(PROPOSED), _costs(ANCHOR))
    proposed, anchor = ranges["p"], ranges["a"]

    assert proposed.paired and proposed.reason is None
    assert not anchor.paired and anchor.difference_total is None
    total = proposed.difference_total
    assert total is not None and total.n_seeds == len(SEEDS)
    # Per seed the total difference is 2 x (100 + i): 200..210.
    assert (total.min, total.max) == (200.0, 210.0)
    assert [(d.year, d.min, d.max) for d in proposed.difference_years] == [
        (2026, 100.0, 105.0),
        (2027, 100.0, 105.0),
    ]
    # Subtracting the two bands would claim a spread thousands wide.
    assert proposed.total is not None and anchor.total is not None
    band_low = proposed.total.p10 - anchor.total.p90
    band_high = proposed.total.p90 - anchor.total.p10
    assert band_high - band_low > 9000
    assert total.max - total.min == 10.0
    assert total.p10 > band_low and total.p90 < band_high


def test_bands_are_p10_p90_of_annual_and_total_cost() -> None:
    anchor = _build(_costs(PROPOSED), _costs(ANCHOR))["a"]

    assert [(b.year, b.p10, b.p90, b.n_seeds) for b in anchor.years] == [
        (2026, 500.0, 4500.0, 6),
        (2027, 750.0, 6750.0, 6),
    ]
    assert anchor.total is not None
    assert (anchor.total.p10, anchor.total.p90) == (1250.0, 11250.0)


def test_different_seed_lists_are_not_paired() -> None:
    other_seeds = tuple(seed + 1 for seed in SEEDS)
    shifted = {seed + 1: by_year for seed, by_year in PROPOSED.items()}
    proposed = _build(_costs(shifted, seeds=other_seeds), _costs(ANCHOR))["p"]

    assert not proposed.paired
    assert proposed.reason == DIFFERENT_SEEDS
    assert proposed.difference_total is None and proposed.difference_years == []
    assert proposed.total is not None  # its own band still shows


def test_different_years_are_not_paired() -> None:
    longer = {seed: {**by_year, 2028: 1.0} for seed, by_year in PROPOSED.items()}
    proposed = _build(_costs(longer, years=(2026, 2028)), _costs(ANCHOR))["p"]

    assert not proposed.paired
    assert proposed.reason == (
        "Its ensemble covers 2026-2028, the anchor's 2026-2027, so they aren't paired."
    )


def test_missing_ensembles_explain_themselves() -> None:
    no_proposed = _build(None, _costs(ANCHOR))
    assert no_proposed["p"].reason == NO_ENSEMBLE
    assert no_proposed["p"].total is None and no_proposed["p"].years == []

    no_anchor = _build(_costs(PROPOSED), None)
    assert no_anchor["a"].reason == NO_ENSEMBLE
    assert no_anchor["p"].reason == NO_ANCHOR_ENSEMBLE
    assert no_anchor["p"].total is not None and not no_anchor["p"].paired


def test_partial_jobs_pair_only_on_seeds_both_finished() -> None:
    # Of seven seeds, 7 failed for the proposal and 5012 for the anchor, which
    # leaves five both finished.
    seeds = SEEDS + (6013,)
    anchor_values = {**ANCHOR, 6013: {2026: 1.0, 2027: 1.0}}
    proposed_values = {**PROPOSED, 6013: {2026: 2.0, 2027: 2.0}}
    del proposed_values[7]
    del anchor_values[5012]

    proposed = _build(
        _costs(proposed_values, seeds=seeds), _costs(anchor_values, seeds=seeds)
    )["p"]

    assert proposed.paired
    assert proposed.difference_total is not None
    assert proposed.difference_total.n_seeds == 5  # 1008, 2009, 3010, 4011, 6013
    assert proposed.difference_total.min == 2.0  # seed 6013: (2+2) - (1+1)


def test_too_few_common_seeds_is_not_paired() -> None:
    proposed_values = {s: v for s, v in PROPOSED.items() if s not in (7, 1008)}
    proposed = _build(_costs(proposed_values), _costs(ANCHOR))["p"]

    assert not proposed.paired
    assert (
        proposed.reason == "Only 4 seeds finished in both ensembles; pairing needs 5."
    )
    assert proposed.total is None  # fewer than five seeds: no band either


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class _Workspace:
    def __init__(self, tmp_path: Path):
        self.storage = WorkspaceStorage(tmp_path / "workspaces")
        census = tmp_path / "census.parquet"
        census.write_bytes(b"stub census")
        base = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
        base["setup"]["census_parquet_path"] = str(census)
        base["simulation"].update(start_year=2026, end_year=2027, random_seed=7)
        workspace = self.storage.create_workspace(WorkspaceCreate(name="W"), base)
        self.workspace_id = workspace.id
        self.store = EnsembleJobStore(self.storage.workspaces_root)

    def scenario(self, name: str) -> str:
        scenario = self.storage.create_scenario(
            self.workspace_id, ScenarioCreate(name=name)
        )
        assert scenario is not None
        return scenario.id

    def finished_job(
        self,
        scenario_id: str,
        values: Mapping[int, Mapping[int, float]],
        *,
        status: str = "completed",
        created_at: datetime = datetime(2026, 11, 1, tzinfo=timezone.utc),
    ) -> str:
        job_id = f"ens_{uuid.uuid4().hex[:12]}"
        database = self.store.job_dir(self.workspace_id, job_id) / "ensemble.duckdb"
        seed_values = [
            MetricSeedValue(
                ensemble_id="ens-x",
                scenario_id="scenario-in-db",
                metric=metric,
                simulation_year=year,
                seed=seed,
                value=value if metric == COST_METRIC else value / 2,
            )
            for seed, by_year in values.items()
            for year, value in by_year.items()
            for metric in (COST_METRIC, "employer_match_cost")
        ]
        write_ensemble_results(
            database, aggregate_ensemble(seed_values, min_seeds=5), seed_values
        )
        estimate = EnsembleEstimate(
            seed_count=len(SEEDS),
            seeds=list(SEEDS),
            start_year=YEARS[0],
            end_year=YEARS[-1],
            run_count=len(SEEDS),
            seconds_per_run=1.0,
            estimated_seconds=1.0,
            time_basis="default",
            estimated_disk_mib=1.0,
        )
        self.store.save(
            EnsembleJob(
                job_id=job_id,
                workspace_id=self.workspace_id,
                scenario_id=scenario_id,
                scenario_name="S",
                status=status,  # type: ignore[arg-type]
                seed_count=len(SEEDS),
                seeds=list(SEEDS),
                start_year=YEARS[0],
                end_year=YEARS[-1],
                estimate=estimate,
                created_at=created_at,
                completed_at=created_at,
                progress=EnsembleProgress(seeds_total=len(SEEDS)),
                output=EnsembleOutput(
                    database_path=str(database.resolve()),
                    ensemble_id="ens-x",
                    ensemble_scenario_id="scenario-in-db",
                ),
            )
        )
        return job_id


@pytest.fixture
def workspace(tmp_path) -> _Workspace:
    return _Workspace(tmp_path)


@pytest.fixture
def client(workspace) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ensembles.router, prefix="/api")
    app.dependency_overrides[ensembles.get_ensemble_job_service] = lambda: (
        EnsembleJobService(workspace.storage)
    )
    with TestClient(app) as test_client:
        yield test_client


def _get(client: TestClient, workspace: _Workspace, scenarios: list[str], anchor: str):
    return client.get(
        f"/api/workspaces/{workspace.workspace_id}/ensembles/cost-ranges",
        params={"scenarios": ",".join(scenarios), "anchor": anchor},
    )


def test_endpoint_pairs_latest_finished_ensembles(client, workspace) -> None:
    anchor, proposed, bare = (workspace.scenario(n) for n in ("A", "P", "B"))
    workspace.finished_job(anchor, ANCHOR)
    stale = {s: {y: 0.0 for y in v} for s, v in PROPOSED.items()}
    workspace.finished_job(
        proposed, stale, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc)
    )
    latest = workspace.finished_job(proposed, PROPOSED, status="partial")

    response = _get(client, workspace, [anchor, proposed, bare], anchor)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["anchor_scenario_id"] == anchor
    by_id = {item["scenario_id"]: item for item in body["scenarios"]}
    assert by_id[proposed]["job_id"] == latest
    assert by_id[proposed]["paired"] is True
    assert by_id[proposed]["difference_total"]["min"] == 200.0
    assert by_id[proposed]["difference_total"]["max"] == 210.0
    assert by_id[anchor]["total"]["p10"] == 1250.0
    assert by_id[bare]["reason"] == NO_ENSEMBLE
    assert by_id[bare]["total"] is None


def test_endpoint_validates_ids_and_anchor(client, workspace) -> None:
    anchor = workspace.scenario("A")

    assert _get(client, workspace, [anchor], str(uuid.uuid4())).status_code == 422
    assert _get(client, workspace, ["not-a-uuid"], "not-a-uuid").status_code == 404
    missing = str(uuid.uuid4())
    assert _get(client, workspace, [anchor, missing], anchor).status_code == 404
