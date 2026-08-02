"""Fast tests for the pure backtest split planner."""

import pytest

from planalign_backtest.errors import BacktestError
from planalign_backtest.split import plan_split
from planalign_fit.snapshots import Snapshot, SnapshotSet

pytestmark = pytest.mark.fast


def _set(*years: int) -> SnapshotSet:
    return SnapshotSet(
        tuple(Snapshot(year, __file__, str(year), 1, ()) for year in years)
    )


def test_default_split_holds_out_latest_year() -> None:
    split = plan_split(_set(2021, 2022, 2023, 2024), 1)

    assert split.fit_years == (2021, 2022, 2023)
    assert split.holdout_years == (2024,)
    assert split.boundary_year == 2023


@pytest.mark.parametrize("holdout", (0, 3))
def test_holdout_out_of_range_names_value(holdout: int) -> None:
    with pytest.raises(BacktestError, match=rf"must be 1 or 2; got {holdout}"):
        plan_split(_set(2021, 2022, 2023), holdout)


def test_infeasible_holdout_names_both_counts() -> None:
    with pytest.raises(BacktestError, match=r"2-year holdout of 3.*leaves 1"):
        plan_split(_set(2021, 2022, 2023), 2)
