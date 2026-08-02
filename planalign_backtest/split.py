"""Pure fit/holdout split planning."""

from planalign_backtest.errors import BacktestError
from planalign_backtest.models import SnapshotSplit
from planalign_fit.snapshots import SnapshotSet


def plan_split(snapshot_set: SnapshotSet, holdout_years: int) -> SnapshotSplit:
    if holdout_years not in (1, 2):
        raise BacktestError(
            f"--holdout must be 1 or 2; got {holdout_years}. "
            "A longer holdout is not supported."
        )
    years = snapshot_set.years
    if len(years) < 3:
        rendered = ", ".join(str(year) for year in years)
        raise BacktestError(
            "Backtest needs at least 3 snapshots (2 to fit, 1 to hold out); "
            f"found {len(years)}: {rendered}."
        )
    fit_count = len(years) - holdout_years
    if fit_count < 2:
        raise BacktestError(
            f"A {holdout_years}-year holdout of {len(years)} snapshots leaves "
            f"{fit_count} year to fit, but fitting needs at least 2. Use "
            "--holdout 1 or supply a 4th snapshot."
        )
    fit_years = years[:fit_count]
    held_out = years[fit_count:]
    return SnapshotSplit(
        fit_years=fit_years,
        holdout_years=held_out,
        boundary_year=fit_years[-1],
        all_years=years,
    )
