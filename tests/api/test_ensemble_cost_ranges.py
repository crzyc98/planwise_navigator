"""Seed ranges beside Cost Comparison: bands, seed-by-seed pairing, endpoint.

Fixture ensemble databases are written through the real
``write_ensemble_results`` and ``write_ensemble_provenance``, and job records
through the real job store, so nothing here runs a simulation. The fingerprint
test prepares a Studio run and an ensemble job through their real input code
and loads each config the way its CLI path does.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Optional

import duckdb
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
    ANCHOR_REASONS,
    COST_METRIC,
    DIFFERENT_SEEDS,
    MIXED_RESULTS,
    NO_ANCHOR_ENSEMBLE,
    NO_ENSEMBLE,
    STALE_ENSEMBLE,
    UNREADABLE_ENSEMBLE,
    UNRECORDED_RESULTS,
    EnsembleSeedCosts,
    ResultsIdentity,
    ScenarioEnsemble,
    build_cost_ranges,
    choose_ensemble,
)
from planalign_api.services.ensemble_jobs.store import EnsembleJobStore
from planalign_api.services.simulation.service import SimulationService
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_cli.commands.simulate import _build_ensemble_spec
from planalign_cli.integration.orchestrator_wrapper import OrchestratorWrapper
from planalign_ensemble.aggregate import aggregate_ensemble, write_ensemble_results
from planalign_ensemble.models import EnsembleSpec, MetricSeedValue
from planalign_ensemble.planner import plan_ensemble
from planalign_ensemble.provenance import write_ensemble_provenance
from planalign_ensemble.runner import _with_config_fingerprint
from planalign_orchestrator.run_metadata import (
    RUN_METADATA_TABLE,
    _CREATE_TABLE_SQL,
    compute_config_fingerprint,
)

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
    fingerprint: Optional[str] = "fp",
) -> EnsembleSeedCosts:
    return EnsembleSeedCosts(
        job_id=job_id,
        seeds=seeds,
        start_year=years[0],
        end_year=years[1],
        completed_at=None,
        values=values,
        config_fingerprint=fingerprint,
    )


Chosen = Optional["EnsembleSeedCosts | ScenarioEnsemble"]


def _chosen(value: Chosen) -> ScenarioEnsemble:
    if value is None:
        return ScenarioEnsemble()
    if isinstance(value, ScenarioEnsemble):
        return value
    return ScenarioEnsemble(costs=value, job_id=value.job_id, reason=None)


def _build(proposed: Chosen, anchor: Chosen):
    result = build_cost_ranges(
        ["a", "p"], "a", {"a": _chosen(anchor), "p": _chosen(proposed)}
    )
    return {item.scenario_id: item for item in result.scenarios}


def _job(job_id: str, scenario_id: str = "p", status: str = "completed") -> EnsembleJob:
    created = datetime(2026, 11, 1, tzinfo=timezone.utc)
    return EnsembleJob(
        job_id=job_id,
        workspace_id="w",
        scenario_id=scenario_id,
        scenario_name="S",
        status=status,  # type: ignore[arg-type]
        seed_count=len(SEEDS),
        seeds=list(SEEDS),
        start_year=YEARS[0],
        end_year=YEARS[-1],
        estimate=EnsembleEstimate(
            seed_count=len(SEEDS),
            seeds=list(SEEDS),
            start_year=YEARS[0],
            end_year=YEARS[-1],
            run_count=len(SEEDS),
            seconds_per_run=1.0,
            estimated_seconds=1.0,
            time_basis="default",
            estimated_disk_mib=1.0,
        ),
        created_at=created,
        completed_at=created,
        progress=EnsembleProgress(seeds_total=len(SEEDS)),
        output=EnsembleOutput(
            database_path="unused.duckdb",
            ensemble_id="e",
            ensemble_scenario_id="s",
        ),
    )


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
    assert total.min > band_low and total.max < band_high


def test_bands_are_p10_p90_of_annual_and_total_cost() -> None:
    anchor = _build(_costs(PROPOSED), _costs(ANCHOR))["a"]

    assert [(b.year, b.p10, b.p90, b.n_seeds) for b in anchor.years] == [
        (2026, 500.0, 4500.0, 6),
        (2027, 750.0, 6750.0, 6),
    ]
    assert anchor.total is not None
    assert (anchor.total.p10, anchor.total.p90) == (1250.0, 11250.0)


def test_every_figure_in_a_row_uses_the_same_seeds() -> None:
    # Seed 7 is missing its 2027 cost: it can't count toward any figure.
    gappy = {**ANCHOR, 7: {2026: ANCHOR[7][2026]}}
    anchor = _build(_costs(PROPOSED), _costs(gappy))["a"]

    assert {band.n_seeds for band in anchor.years} == {5}
    assert anchor.total is not None and anchor.total.n_seeds == 5


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
    assert no_proposed["p"].job_id is None
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


def test_an_unusable_anchor_says_why_nothing_pairs() -> None:
    for reason in (STALE_ENSEMBLE, UNREADABLE_ENSEMBLE, MIXED_RESULTS):
        anchor = ScenarioEnsemble(job_id="ens_a", reason=reason)
        ranges = _build(_costs(PROPOSED), anchor)

        assert ranges["a"].reason == reason and ranges["a"].job_id == "ens_a"
        assert not ranges["a"].current and ranges["a"].total is None
        assert ranges["p"].reason == ANCHOR_REASONS[reason]
        assert ranges["p"].total is not None and not ranges["p"].paired


# ---------------------------------------------------------------------------
# Choosing a scenario's ensemble (pure)
# ---------------------------------------------------------------------------


def _loader(costs: Mapping[str, Optional[EnsembleSeedCosts]]):
    return lambda job: costs.get(job.job_id)


def test_the_newest_ensemble_on_current_settings_is_used() -> None:
    jobs = [_job("ens_new"), _job("ens_old"), _job("ens_a", scenario_id="a")]
    loads = {
        "ens_new": _costs(PROPOSED, job_id="ens_new", fingerprint="fp-old"),
        "ens_old": _costs(PROPOSED, job_id="ens_old", fingerprint="fp"),
    }

    chosen = choose_ensemble(jobs, "p", ResultsIdentity("fp"), _loader(loads))

    assert chosen.costs is not None and chosen.job_id == "ens_old"
    assert chosen.reason is None


def test_with_none_current_the_newest_job_and_its_reason_are_reported() -> None:
    jobs = [_job("ens_new"), _job("ens_old"), _job("ens_failed", status="failed")]
    stale = {"ens_old": _costs(PROPOSED, job_id="ens_old", fingerprint="fp-old")}

    unreadable = choose_ensemble(jobs, "p", ResultsIdentity("fp"), _loader(stale))
    assert (unreadable.job_id, unreadable.reason) == ("ens_new", UNREADABLE_ENSEMBLE)
    assert unreadable.costs is None

    both_stale = {**stale, "ens_new": _costs(PROPOSED, fingerprint="fp-old")}
    chosen = choose_ensemble(jobs, "p", ResultsIdentity("fp"), _loader(both_stale))
    assert (chosen.job_id, chosen.reason) == ("ens_new", STALE_ENSEMBLE)

    unstamped = {"ens_new": _costs(PROPOSED, fingerprint=None)}
    chosen = choose_ensemble(jobs, "p", ResultsIdentity("fp"), _loader(unstamped))
    assert chosen.reason == STALE_ENSEMBLE


def test_untrusted_results_use_no_ensemble() -> None:
    jobs = [_job("ens_new")]
    loads = {"ens_new": _costs(PROPOSED, job_id="ens_new", fingerprint="fp")}

    for reason in (MIXED_RESULTS, UNRECORDED_RESULTS):
        chosen = choose_ensemble(
            jobs, "p", ResultsIdentity(None, reason), _loader(loads)
        )
        assert (chosen.costs, chosen.job_id, chosen.reason) == (None, "ens_new", reason)


def test_no_finished_job_is_no_ensemble() -> None:
    chosen = choose_ensemble(
        [_job("ens_failed", status="failed")], "p", ResultsIdentity("fp"), _loader({})
    )
    assert chosen == ScenarioEnsemble()


# ---------------------------------------------------------------------------
# Fingerprints: a Studio run and an ensemble of the same scenario agree
# ---------------------------------------------------------------------------


def _studio_run_fingerprint(storage, workspace_id: str, scenario_id: str, tmp: Path):
    """What the orchestrator stamps on a Studio run's run_metadata.

    Studio writes config.yaml through ``_prepare_simulation`` and runs
    ``planalign simulate --config``, whose OrchestratorWrapper loads it and
    hands that config unchanged to ``check_and_record_run``.
    """
    run_dir = tmp / f"run-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir()
    config = storage.get_merged_config(workspace_id, scenario_id)
    SimulationService(storage)._prepare_simulation(
        workspace_id, scenario_id, config, run_dir
    )
    wrapper = OrchestratorWrapper(run_dir / "config.yaml", run_dir / "sim.duckdb")
    return compute_config_fingerprint(wrapper.config)


def _ensemble_fingerprint(storage, workspace_id: str, scenario_id: str, tmp: Path):
    """What the ensemble runner stamps for a Studio ensemble job."""
    service = EnsembleJobService(storage)
    scenario = storage.get_scenario(workspace_id, scenario_id)
    config = service._config(scenario)
    job = service._new_job(scenario, service._estimate(scenario, config, 5))
    paths = service._prepare_inputs(job, scenario, config)
    spec, loaded = _build_ensemble_spec(
        job.start_year,
        job.end_year,
        paths.config,
        paths.dbt_project,
        None,
        ",".join(str(seed) for seed in job.seeds),
        False,
        None,
        None,
        5,
        True,
        None,
        EnsembleSpec,
    )
    plan = plan_ensemble(spec, output_root=tmp / "plans")
    return _with_config_fingerprint(plan, loaded).config_fingerprint


def test_studio_run_and_ensemble_fingerprints_match_until_the_match_changes(
    tmp_path,
) -> None:
    workspace = _Workspace(tmp_path)
    scenario_id = workspace.scenario("Proposed")
    storage, ws = workspace.storage, workspace.workspace_id

    ensemble = _ensemble_fingerprint(storage, ws, scenario_id, tmp_path)
    assert ensemble
    assert _studio_run_fingerprint(storage, ws, scenario_id, tmp_path) == ensemble

    storage.update_scenario(
        ws, scenario_id, config_overrides={"dc_plan": {"match_cap_percent": 0.06}}
    )
    rerun = _studio_run_fingerprint(storage, ws, scenario_id, tmp_path)
    assert rerun != ensemble
    assert _ensemble_fingerprint(storage, ws, scenario_id, tmp_path) == rerun

    # The horizon is part of the fingerprint, so a match also means the
    # ensemble covers the years the results show.
    storage.update_scenario(
        ws,
        scenario_id,
        config_overrides={
            "dc_plan": {"match_cap_percent": 0.06},
            "simulation": {"end_year": 2028},
        },
    )
    assert _studio_run_fingerprint(storage, ws, scenario_id, tmp_path) != rerun


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class _Workspace:
    def __init__(self, tmp_path: Path):
        self.storage = WorkspaceStorage(tmp_path / "workspaces")
        census = self.storage.workspaces_root / "census.parquet"
        census.parent.mkdir(parents=True, exist_ok=True)
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
        fingerprint: str = "fp",
    ) -> str:
        job_id = f"ens_{uuid.uuid4().hex[:12]}"
        database = self.store.job_dir(self.workspace_id, job_id) / "ensemble.duckdb"
        plan = plan_ensemble(
            EnsembleSpec(
                scenario_id="scenario-in-db",
                seed_count=len(SEEDS),
                base_seed=SEEDS[0],
                start_year=YEARS[0],
                end_year=YEARS[-1],
            ),
            output_root=database.parent / "plan",
            config_fingerprint=fingerprint,
        )
        plan = plan.model_copy(update={"ensemble_db_path": database})
        seed_values = [
            MetricSeedValue(
                ensemble_id=plan.ensemble_id,
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
        write_ensemble_provenance(plan)
        self.store.save(
            _job(job_id, scenario_id, status).model_copy(
                update={
                    "workspace_id": self.workspace_id,
                    "created_at": created_at,
                    "completed_at": created_at,
                    "output": EnsembleOutput(
                        database_path=str(database.resolve()),
                        ensemble_id=plan.ensemble_id,
                        ensemble_scenario_id="scenario-in-db",
                    ),
                }
            )
        )
        return job_id

    def results(
        self, scenario_id: str, fingerprint: str = "fp", *, earlier: str = ""
    ) -> None:
        """A (legacy-located) result database stamped like a real run.

        ``earlier`` adds an older generation on other settings beneath it.
        """
        path = (
            self.storage._scenario_path(self.workspace_id, scenario_id)
            / "simulation.duckdb"
        )
        with duckdb.connect(str(path)) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(
                f"INSERT INTO {RUN_METADATA_TABLE} (run_id, run_timestamp, run_type, "
                "config_fingerprint, random_seed, start_year, end_year) "
                "VALUES ('run-1', now(), 'simulate', ?, 7, 2026, 2027)",
                [fingerprint],
            )
            if earlier:
                conn.execute(
                    f"INSERT INTO {RUN_METADATA_TABLE} (run_id, run_timestamp, "
                    "run_type, config_fingerprint, random_seed, start_year, end_year) "
                    "VALUES ('run-0', now() - INTERVAL 1 DAY, 'simulate', ?, 7, "
                    "2026, 2027)",
                    [earlier],
                )


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
    for scenario_id in (anchor, proposed, bare):
        workspace.results(scenario_id)
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


def test_endpoint_hides_an_ensemble_from_before_a_settings_change(
    client, workspace
) -> None:
    anchor, proposed = workspace.scenario("A"), workspace.scenario("P")
    workspace.results(anchor)
    workspace.results(proposed, fingerprint="fp-after-match-change")
    workspace.finished_job(anchor, ANCHOR)
    workspace.finished_job(proposed, PROPOSED)

    body = _get(client, workspace, [anchor, proposed], anchor).json()

    by_id = {item["scenario_id"]: item for item in body["scenarios"]}
    assert by_id[proposed]["reason"] == STALE_ENSEMBLE
    assert by_id[proposed]["current"] is False
    assert by_id[proposed]["total"] is None and by_id[proposed]["years"] == []
    assert by_id[anchor]["current"] is True and by_id[anchor]["total"] is not None


def test_endpoint_falls_back_to_an_older_current_ensemble(client, workspace) -> None:
    anchor, proposed = workspace.scenario("A"), workspace.scenario("P")
    workspace.results(anchor)
    workspace.results(proposed)
    workspace.finished_job(anchor, ANCHOR)
    older = workspace.finished_job(
        proposed, PROPOSED, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc)
    )
    workspace.finished_job(proposed, PROPOSED, fingerprint="fp-other-settings")

    body = _get(client, workspace, [anchor, proposed], anchor).json()

    chosen = next(i for i in body["scenarios"] if i["scenario_id"] == proposed)
    assert chosen["job_id"] == older and chosen["current"] and chosen["paired"]


def test_endpoint_reports_an_unreadable_ensemble(client, workspace) -> None:
    anchor, proposed = workspace.scenario("A"), workspace.scenario("P")
    workspace.results(anchor)
    workspace.results(proposed)
    workspace.finished_job(anchor, ANCHOR)
    broken = workspace.finished_job(proposed, PROPOSED)
    database = workspace.store.job_dir(workspace.workspace_id, broken)
    (database / "ensemble.duckdb").write_bytes(b"not a database")

    body = _get(client, workspace, [anchor, proposed], anchor).json()

    chosen = next(i for i in body["scenarios"] if i["scenario_id"] == proposed)
    assert (chosen["job_id"], chosen["reason"]) == (broken, UNREADABLE_ENSEMBLE)
    assert chosen["current"] is False


def test_endpoint_refuses_results_from_mixed_settings(client, workspace) -> None:
    anchor, proposed = workspace.scenario("A"), workspace.scenario("P")
    workspace.results(anchor)
    workspace.results(proposed, earlier="fp-before")
    workspace.finished_job(anchor, ANCHOR)
    workspace.finished_job(proposed, PROPOSED)

    body = _get(client, workspace, [anchor, proposed], anchor).json()

    chosen = next(i for i in body["scenarios"] if i["scenario_id"] == proposed)
    assert chosen["reason"] == MIXED_RESULTS and chosen["total"] is None


def test_endpoint_validates_ids_and_anchor(client, workspace) -> None:
    anchor = workspace.scenario("A")

    assert _get(client, workspace, [anchor], str(uuid.uuid4())).status_code == 422
    assert _get(client, workspace, ["not-a-uuid"], "not-a-uuid").status_code == 404
    missing = str(uuid.uuid4())
    assert _get(client, workspace, [anchor, missing], anchor).status_code == 404
