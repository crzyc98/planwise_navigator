"""Seed ranges for Cost Comparison: employer-cost bands and paired differences.

A difference from the anchor is taken seed by seed (seed s of a scenario minus
seed s of the anchor), then summarized. Two separate bands can't be subtracted:
the seeds that make a scenario expensive usually make the anchor expensive too,
so the paired spread is far narrower than the bands suggest.

An ensemble is used only when it ran on the same settings as the results on
screen: its config fingerprint (stamped by the ensemble runner) must equal the
one stamped on the scenario's selected run. Both are
``compute_config_fingerprint`` over the merged config Studio writes for the run,
which includes the start and end year, so a match also means the same horizon.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np

from planalign_ensemble.studio_reader import (
    InvalidEnsembleDatabaseError,
    validate_ensemble_database,
)

from ...models.ensemble_job import (
    MIN_SEED_COUNT,
    CostBand,
    DifferenceRange,
    EnsembleCostRanges,
    EnsembleJob,
    ScenarioCostRange,
    YearCostBand,
    YearDifferenceRange,
)

logger = logging.getLogger(__name__)

# SUM(employer_match_amount + employer_core_amount) over every snapshot row:
# the page's gross employer cost for all employees (GROSS_EMPLOYER_COST_SQL).
COST_METRIC = "total_employer_plan_cost"
FINISHED_STATUSES = frozenset({"completed", "partial"})

NO_ENSEMBLE = "No finished ensemble for this scenario."
STALE_ENSEMBLE = (
    "Its ensemble was run before this scenario's settings changed; "
    "run a new ensemble to see a range."
)
UNREADABLE_ENSEMBLE = "Its ensemble couldn't be read, so no range is shown."
MIXED_RESULTS = "Its results mix runs made on different settings, so no range is shown."
UNRECORDED_RESULTS = "Its results don't record their settings, so no range is shown."
DIFFERENT_SEEDS = (
    "Its ensemble used different seeds from the anchor's, so they aren't paired."
)
NO_ANCHOR_ENSEMBLE = "The anchor scenario has no finished ensemble to pair with."
# Why another scenario can't pair, keyed by why the anchor has no usable ensemble.
ANCHOR_REASONS = {
    NO_ENSEMBLE: NO_ANCHOR_ENSEMBLE,
    STALE_ENSEMBLE: (
        "The anchor's ensemble was run before its settings changed, "
        "so they aren't paired."
    ),
    UNREADABLE_ENSEMBLE: "The anchor's ensemble couldn't be read, so they aren't paired.",
    MIXED_RESULTS: "The anchor's results mix runs on different settings, so they aren't paired.",
    UNRECORDED_RESULTS: "The anchor's results don't record their settings, so they aren't paired.",
}


@dataclass(frozen=True)
class EnsembleSeedCosts:
    """One finished ensemble: employer cost per seed and year."""

    job_id: str
    seeds: tuple[int, ...]
    start_year: int
    end_year: int
    completed_at: Optional[datetime]
    values: Mapping[int, Mapping[int, float]]  # seed -> year -> cost
    config_fingerprint: Optional[str] = None

    @property
    def years(self) -> range:
        return range(self.start_year, self.end_year + 1)

    def complete_seeds(self) -> list[int]:
        """Seeds with a cost for every year: the one seed set every figure uses."""
        return sorted(
            seed
            for seed, by_year in self.values.items()
            if all(year in by_year for year in self.years)
        )

    def total(self, seed: int) -> float:
        return sum(self.values[seed][year] for year in self.years)


@dataclass(frozen=True)
class ResultsIdentity:
    """The settings behind the results on screen, or why they can't be trusted."""

    fingerprint: Optional[str]
    reason: Optional[str] = None


@dataclass(frozen=True)
class ScenarioEnsemble:
    """The ensemble chosen for a scenario: usable costs, or the job and why not."""

    costs: Optional[EnsembleSeedCosts] = None
    job_id: Optional[str] = None
    reason: Optional[str] = NO_ENSEMBLE


def choose_ensemble(
    jobs: Iterable[EnsembleJob],
    scenario_id: str,
    results: ResultsIdentity,
    load: Callable[[EnsembleJob], Optional[EnsembleSeedCosts]],
) -> ScenarioEnsemble:
    """The newest finished ensemble run on the same settings as the results.

    Jobs come newest first. With none matching, the newest finished job and
    why it can't be used are reported, so the page can say so.
    """
    finished = [
        job
        for job in jobs
        if job.scenario_id == scenario_id
        and job.status in FINISHED_STATUSES
        and job.output is not None
    ]
    if not finished:
        return ScenarioEnsemble()
    newest = finished[0].job_id
    if results.reason is not None:
        return ScenarioEnsemble(job_id=newest, reason=results.reason)
    newest_reason: Optional[str] = None
    for job in finished:
        costs = load(job)
        if costs is not None and costs.config_fingerprint == results.fingerprint:
            return ScenarioEnsemble(costs=costs, job_id=job.job_id, reason=None)
        if newest_reason is None:
            newest_reason = UNREADABLE_ENSEMBLE if costs is None else STALE_ENSEMBLE
    return ScenarioEnsemble(job_id=newest, reason=newest_reason)


def load_seed_costs(job: EnsembleJob) -> Optional[EnsembleSeedCosts]:
    """Employer cost per seed and year, and the stamped fingerprint, in one read."""
    if job.output is None:
        return None
    try:
        database = validate_ensemble_database(Path(job.output.database_path))
        with duckdb.connect(str(database), read_only=True) as connection:
            rows = connection.execute(
                "SELECT seed, simulation_year, value FROM fct_metric_seed_values "
                "WHERE scenario_id = ? AND ensemble_id = ? AND metric = ? "
                "AND value IS NOT NULL",
                [job.output.ensemble_scenario_id, job.output.ensemble_id, COST_METRIC],
            ).fetchall()
            fingerprint = _stamped_fingerprint(connection, job.output.ensemble_id)
    except (InvalidEnsembleDatabaseError, duckdb.Error) as exc:
        logger.warning("Ensemble %s results are unreadable: %s", job.job_id, exc)
        return None
    values: dict[int, dict[int, float]] = defaultdict(dict)
    for seed, year, value in rows:
        values[int(seed)][int(year)] = float(value)
    return EnsembleSeedCosts(
        job_id=job.job_id,
        seeds=tuple(job.seeds),
        start_year=job.start_year,
        end_year=job.end_year,
        completed_at=job.completed_at,
        values=dict(values),
        config_fingerprint=fingerprint,
    )


def _stamped_fingerprint(
    connection: duckdb.DuckDBPyConnection, ensemble_id: str
) -> Optional[str]:
    """The config fingerprint the runner stamped on this ensemble's headline run."""
    has_table = connection.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'run_metadata'"
    ).fetchone()
    if has_table is None:
        return None
    row = connection.execute(
        "SELECT config_fingerprint FROM run_metadata "
        "WHERE ensemble_id = ? AND ensemble_role = 'headline' "
        "ORDER BY run_timestamp DESC LIMIT 1",
        [ensemble_id],
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def build_cost_ranges(
    scenario_ids: Sequence[str],
    anchor_id: str,
    ensembles: Mapping[str, ScenarioEnsemble],
) -> EnsembleCostRanges:
    anchor = ensembles.get(anchor_id, ScenarioEnsemble())
    scenarios: list[ScenarioCostRange] = []
    for sid in scenario_ids:
        chosen = ensembles.get(sid, ScenarioEnsemble())
        if chosen.costs is None:
            scenarios.append(
                ScenarioCostRange(
                    scenario_id=sid, job_id=chosen.job_id, reason=chosen.reason
                )
            )
        elif sid == anchor_id:
            scenarios.append(_bands(sid, chosen.costs))
        else:
            scenarios.append(_paired_range(sid, chosen.costs, anchor))
    return EnsembleCostRanges(anchor_scenario_id=anchor_id, scenarios=scenarios)


def _bands(scenario_id: str, costs: EnsembleSeedCosts) -> ScenarioCostRange:
    seeds = costs.complete_seeds()
    years = []
    for year in costs.years:
        band = _band(costs.values[seed][year] for seed in seeds)
        if band is not None:
            years.append(YearCostBand(year=year, **band.model_dump()))
    return ScenarioCostRange(
        scenario_id=scenario_id,
        job_id=costs.job_id,
        completed_at=costs.completed_at,
        start_year=costs.start_year,
        end_year=costs.end_year,
        current=True,
        years=years,
        total=_band(costs.total(seed) for seed in seeds),
    )


def _paired_range(
    scenario_id: str, costs: EnsembleSeedCosts, anchor: ScenarioEnsemble
) -> ScenarioCostRange:
    result = _bands(scenario_id, costs)
    if anchor.costs is None:
        reason = ANCHOR_REASONS.get(anchor.reason or NO_ENSEMBLE, NO_ANCHOR_ENSEMBLE)
        return result.model_copy(update={"reason": reason})
    common, unpaired = pair_seeds(costs, anchor.costs)
    if unpaired is not None:
        return result.model_copy(update={"reason": unpaired})
    years = []
    for year in costs.years:
        spread = _difference(
            costs.values[seed][year] - anchor.costs.values[seed][year]
            for seed in common
        )
        if spread is not None:
            years.append(YearDifferenceRange(year=year, **spread.model_dump()))
    return result.model_copy(
        update={
            "paired": True,
            "difference_years": years,
            "difference_total": _difference(
                costs.total(seed) - anchor.costs.total(seed) for seed in common
            ),
        }
    )


def pair_seeds(
    costs: EnsembleSeedCosts, anchor: EnsembleSeedCosts
) -> tuple[list[int], Optional[str]]:
    """Seeds both ensembles finished, or why the two can't be paired."""
    if sorted(costs.seeds) != sorted(anchor.seeds):
        return [], DIFFERENT_SEEDS
    if (costs.start_year, costs.end_year) != (anchor.start_year, anchor.end_year):
        return [], (
            f"Its ensemble covers {costs.start_year}-{costs.end_year}, the anchor's "
            f"{anchor.start_year}-{anchor.end_year}, so they aren't paired."
        )
    common = sorted(set(costs.complete_seeds()) & set(anchor.complete_seeds()))
    if len(common) < MIN_SEED_COUNT:
        return [], (
            f"Only {len(common)} seeds finished in both ensembles; "
            f"pairing needs {MIN_SEED_COUNT}."
        )
    return common, None


def _sufficient(values: Iterable[float]) -> Optional[np.ndarray]:
    observed = np.asarray(list(values), dtype=float)
    return observed if len(observed) >= MIN_SEED_COUNT else None


def _band(values: Iterable[float]) -> Optional[CostBand]:
    observed = _sufficient(values)
    if observed is None:
        return None
    p10, p90 = np.percentile(observed, (10, 90), method="linear")
    return CostBand(p10=float(p10), p90=float(p90), n_seeds=len(observed))


def _difference(values: Iterable[float]) -> Optional[DifferenceRange]:
    observed = _sufficient(values)
    if observed is None:
        return None
    return DifferenceRange(
        min=float(observed.min()), max=float(observed.max()), n_seeds=len(observed)
    )
