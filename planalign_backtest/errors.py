"""Errors raised by the backtest harness."""


class BacktestError(ValueError):
    """A backtest could not be completed or materialized."""


class SimulationFailure(BacktestError):
    """One constituent seed/year simulation failed."""

    def __init__(self, seed: int, year: int, detail: str) -> None:
        self.seed = seed
        self.year = year
        super().__init__(
            f"Backtest simulation failed for seed {seed}, year {year}. "
            f"No scorecard was written. {detail}"
        )
