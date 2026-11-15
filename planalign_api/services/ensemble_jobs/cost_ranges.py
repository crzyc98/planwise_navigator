"""Seed ranges for Cost Comparison: employer-cost bands and paired differences.

A difference from the anchor is taken seed by seed (seed s of a scenario minus
seed s of the anchor), then summarized. Two separate bands can't be subtracted:
the seeds that make a scenario expensive usually make the anchor expensive too,
so the paired spread is far narrower than the bands suggest.

An ensemble is used only when it ran on the same settings as the results on
screen: its config fingerprint (stamped by the ensemble runner) must equal the
one stamped on the scenario's selected run. Both are
``compute_config_fingerprint`` over the merged config Studio writes for the run.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np

from planalign_ensemble.studio_reader import (
    InvalidEnsembleDatabaseError,
    read_seed_values,
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
NO_ANCHOR_ENSEMBLE = "The anchor scenario has no finished ensemble to pair with."
STALE_ENSEMBLE = (
    "Its ensemble was run before this scenario's settings changed; "
    "run a new ensemble to see a range."
)
STALE_ANCHOR = (
    "The anchor's ensemble was run before its settings changed, so they aren't paired."
)
DIFFERENT_SEEDS = (
    "Its ensemble used different seeds from the anchor's, so they aren't paired."
)


@dataclass(frozen=True)
class EnsembleSeedCosts:
    """One scenario's latest finished ensemble: employer cost per seed and year."""

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

    def complete_seeds(self) -> set[int]:
        """Seeds with a cost for every year, so their horizon total is whole."""
        return {
            seed
            for seed, by_year in self.values.items()
            if all(year in by_year for year in self.years)
        }

    def total(self, seed: int) -> float:
        return sum(self.values[seed][year] for year in self.years)


def latest_finished_job(
    jobs: Iterable[EnsembleJob], scenario_id: str
) -> Optional[EnsembleJob]:
    """The newest completed or partial job with results (jobs come newest first)."""
    return next(
        (
            job
            for job in jobs
            if job.scenario_id == scenario_id
            and job.status in FINISHED_STATUSES
            and job.output is not None
        ),
        None,
    )


def load_seed_costs(job: EnsembleJob) -> Optional[EnsembleSeedCosts]:
    """Employer cost per seed and year from a finished job's aggregate."""
    if job.output is None:
        return None
    try:
        database = validate_ensemble_database(Path(job.output.database_path))
        rows = read_seed_values(
            database, job.output.ensemble_scenario_id, job.output.ensemble_id
        )
        fingerprint = _ensemble_fingerprint(database, job.output.ensemble_id)
    except (InvalidEnsembleDatabaseError, duckdb.Error) as exc:
        logger.warning("Ensemble %s results are unreadable: %s", job.job_id, exc)
        return None
    values: dict[int, dict[int, float]] = defaultdict(dict)
    for row in rows:
        if row.metric == COST_METRIC and row.value is not None:
            values[row.seed][row.simulation_year] = row.value
    return EnsembleSeedCosts(
        job_id=job.job_id,
        seeds=tuple(job.seeds),
        start_year=job.start_year,
        end_year=job.end_year,
        completed_at=job.completed_at,
        values=dict(values),
        config_fingerprint=fingerprint,
    )


def _ensemble_fingerprint(database: Path, ensemble_id: str) -> Optional[str]:
    """The config fingerprint the runner stamped on this ensemble's headline run."""
    with duckdb.connect(str(database), read_only=True) as connection:
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


def is_current(
    costs: Optional[EnsembleSeedCosts], results_fingerprint: Optional[str]
) -> bool:
    """Whether the ensemble ran on the settings behind the results shown.

    A missing fingerprint on either side can't be shown to match, so it counts
    as stale rather than risk a range from other settings.
    """
    return (
        costs is not None
        and costs.config_fingerprint is not None
        and costs.config_fingerprint == results_fingerprint
    )


def build_cost_ranges(
    scenario_ids: Sequence[str],
    anchor_id: str,
    ensembles: Mapping[str, Optional[EnsembleSeedCosts]],
    result_fingerprints: Mapping[str, Optional[str]],
) -> EnsembleCostRanges:
    current = {
        sid: is_current(ensembles.get(sid), result_fingerprints.get(sid))
        for sid in scenario_ids
    }
    anchor = ensembles.get(anchor_id) if current.get(anchor_id) else None
    anchor_missing = (
        NO_ANCHOR_ENSEMBLE if ensembles.get(anchor_id) is None else STALE_ANCHOR
    )
    scenarios: list[ScenarioCostRange] = []
    for sid in scenario_ids:
        costs = ensembles.get(sid)
        if costs is None:
            scenarios.append(ScenarioCostRange(scenario_id=sid, reason=NO_ENSEMBLE))
        elif not current[sid]:
            scenarios.append(_stale_range(sid, costs))
        elif sid == anchor_id:
            scenarios.append(_bands(sid, costs))
        else:
            scenarios.append(
                _paired_range(_bands(sid, costs), costs, anchor, anchor_missing)
            )
    return EnsembleCostRanges(anchor_scenario_id=anchor_id, scenarios=scenarios)


def _stale_range(scenario_id: str, costs: EnsembleSeedCosts) -> ScenarioCostRange:
    return ScenarioCostRange(
        scenario_id=scenario_id,
        job_id=costs.job_id,
        completed_at=costs.completed_at,
        start_year=costs.start_year,
        end_year=costs.end_year,
        reason=STALE_ENSEMBLE,
    )


def _bands(scenario_id: str, costs: EnsembleSeedCosts) -> ScenarioCostRange:
    return ScenarioCostRange(
        scenario_id=scenario_id,
        job_id=costs.job_id,
        completed_at=costs.completed_at,
        start_year=costs.start_year,
        end_year=costs.end_year,
        current=True,
        years=_year_bands(costs),
        total=_band(costs.total(seed) for seed in costs.complete_seeds()),
    )


def _paired_range(
    result: ScenarioCostRange,
    costs: EnsembleSeedCosts,
    anchor: Optional[EnsembleSeedCosts],
    anchor_missing: str,
) -> ScenarioCostRange:
    if anchor is None:
        return result.model_copy(update={"reason": anchor_missing})
    common, reason = pair_seeds(costs, anchor)
    if reason is not None:
        return result.model_copy(update={"reason": reason})
    return result.model_copy(
        update={
            "paired": True,
            "difference_years": _year_differences(costs, anchor, common),
            "difference_total": _difference(
                costs.total(seed) - anchor.total(seed) for seed in common
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
    common = sorted(costs.complete_seeds() & anchor.complete_seeds())
    if len(common) < MIN_SEED_COUNT:
        return [], (
            f"Only {len(common)} seeds finished in both ensembles; "
            f"pairing needs {MIN_SEED_COUNT}."
        )
    return common, None


def _year_bands(costs: EnsembleSeedCosts) -> list[YearCostBand]:
    bands: list[YearCostBand] = []
    for year in costs.years:
        band = _band(
            by_year[year] for by_year in costs.values.values() if year in by_year
        )
        if band is not None:
            bands.append(YearCostBand(year=year, **band.model_dump()))
    return bands


def _year_differences(
    costs: EnsembleSeedCosts, anchor: EnsembleSeedCosts, seeds: Sequence[int]
) -> list[YearDifferenceRange]:
    ranges: list[YearDifferenceRange] = []
    for year in costs.years:
        spread = _difference(
            costs.values[seed][year] - anchor.values[seed][year] for seed in seeds
        )
        if spread is not None:
            ranges.append(YearDifferenceRange(year=year, **spread.model_dump()))
    return ranges


def _band(values: Iterable[float]) -> Optional[CostBand]:
    observed = np.asarray(list(values), dtype=float)
    if len(observed) < MIN_SEED_COUNT:
        return None
    p10, p90 = np.percentile(observed, (10, 90), method="linear")
    return CostBand(p10=float(p10), p90=float(p90), n_seeds=len(observed))


def _difference(values: Iterable[float]) -> Optional[DifferenceRange]:
    observed = np.asarray(list(values), dtype=float)
    if len(observed) < MIN_SEED_COUNT:
        return None
    p10, p90 = np.percentile(observed, (10, 90), method="linear")
    return DifferenceRange(
        min=float(observed.min()),
        max=float(observed.max()),
        p10=float(p10),
        p90=float(p90),
        n_seeds=len(observed),
    )
