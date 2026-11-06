"""Simulations must stop at the last year the seed files cover (#1108)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from planalign_orchestrator.calibration_runner import CalibrationRun
from planalign_orchestrator.config import seed_coverage
from planalign_orchestrator.config.seed_coverage import validate_seed_coverage
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator

pytestmark = pytest.mark.fast


def _write_seeds(seed_dir: Path, levers: int, cola: int, irs: int) -> None:
    (seed_dir / "comp_levers.csv").write_text(f"fiscal_year\n2025\n{levers}\n")
    (seed_dir / "config_cola_by_year.csv").write_text(f"year\n2025\n{cola}\n")
    (seed_dir / "config_irs_limits.csv").write_text(f"limit_year\n2025\n{irs}\n")


def test_last_covered_year_is_allowed() -> None:
    validate_seed_coverage(2035)


def test_first_year_past_the_seeds_is_rejected() -> None:
    with pytest.raises(ValueError, match="only run through 2035.*end year is 2036"):
        validate_seed_coverage(2036)


def test_shortest_seed_sets_the_limit_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_seeds(tmp_path, levers=2040, cola=2038, irs=2036)
    monkeypatch.setattr(seed_coverage, "_SEED_DIR", tmp_path)

    validate_seed_coverage(2036)
    with pytest.raises(ValueError) as error:
        validate_seed_coverage(2037)

    assert "only run through 2036" in str(error.value)
    assert "config_irs_limits.csv" in str(error.value)
    assert "comp_levers.csv" not in str(error.value)


def test_calibration_rejects_a_year_past_the_seeds() -> None:
    with pytest.raises(ValueError, match="only run through 2035"):
        CalibrationRun(start_year=2026, end_year=2036)


def test_simulation_stops_before_initializing_when_years_are_not_covered() -> None:
    initialized: list[bool] = []
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.config = SimpleNamespace(
        simulation=SimpleNamespace(start_year=2025, end_year=2026)
    )
    orchestrator._initialization_callback = lambda: initialized.append(True)

    with pytest.raises(ValueError, match="only run through 2035"):
        orchestrator.execute_multi_year_simulation(end_year=2036)

    assert not initialized
