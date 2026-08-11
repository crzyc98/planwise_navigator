"""Optimizer CLI wiring tests — no real scenario execution."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from planalign_cli.main import app
from planalign_optimizer.paths import resolve_output_paths

pytestmark = pytest.mark.fast
runner = CliRunner()


def _write_spec(tmp_path: Path) -> Path:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
design_space:
  levers:
    - name: auto_enrollment.default_deferral_rate
      kind: continuous
      bounds: [0.03, 0.08]
objective:
  objectives:
    - metric: participation_rate
      direction: maximize
baseline:
  config_path: config/simulation_config.yaml
""",
        encoding="utf-8",
    )
    return spec_path


def test_dry_run_surfaces_stale_baseline_warning(tmp_path: Path) -> None:
    prior = tmp_path / "prior_results.json"
    prior.write_text(
        '{"baseline_config_fingerprint": "not-the-real-fingerprint"}',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "optimize",
            str(_write_spec(tmp_path)),
            "--max-runs",
            "3",
            "--seed",
            "1",
            "--dry-run",
            "--compare-baseline-to",
            str(prior),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "resolved baseline differs from the prior optimizer run" in result.output


def test_dry_run_rejects_unresolvable_lever(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
design_space:
  levers:
    - name: employer_match.tier_2_rate
      kind: continuous
      bounds: [0.1, 0.9]
objective:
  objectives:
    - metric: participation_rate
      direction: maximize
baseline:
  config_path: config/simulation_config.yaml
""",
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["optimize", str(spec_path), "--max-runs", "3", "--dry-run"]
    )
    assert result.exit_code != 0
    assert "tier_2_rate" in result.output


def test_output_path_cannot_be_the_shared_dev_database() -> None:
    with pytest.raises(ValueError, match="--output"):
        resolve_output_paths(Path("/tmp/optimizer-iso"), Path("dbt/simulation.duckdb"))
