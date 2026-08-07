"""Optimizer specification validation tests."""

from pathlib import Path

import pytest
import yaml

from planalign_optimizer.spec_io import OptimizerSpecError, load_spec
from planalign_optimizer.baseline import fingerprint_baseline, stale_baseline_warning
from planalign_orchestrator.config import load_simulation_config

pytestmark = pytest.mark.fast


def _write_spec(
    tmp_path: Path,
    *,
    lever_name: str = "auto_enrollment.default_deferral_rate",
    metric: str = "participation_rate",
    lever_count: int = 1,
) -> Path:
    levers = [
        {"name": lever_name, "kind": "continuous", "bounds": [0.03, 0.08]}
        for _ in range(lever_count)
    ]
    if lever_count > 1:
        names = list(
            __import__(
                "planalign_optimizer.design_space", fromlist=["LEVER_REGISTRY"]
            ).LEVER_REGISTRY
        )
        levers = [
            {"name": names[index], "kind": "continuous", "bounds": [0.01, 0.02]}
            for index in range(lever_count)
        ]
    payload = {
        "design_space": {"levers": levers},
        "objective": {"objectives": [{"metric": metric, "direction": "maximize"}]},
        "baseline": {"config_path": "config/simulation_config.yaml"},
    }
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_valid_two_lever_spec_loads(tmp_path: Path) -> None:
    path = _write_spec(tmp_path, lever_count=2)
    assert len(load_spec(path).design_space.levers) == 2


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("lever", "unknown.lever"), ("metric", "unknown_metric")],
)
def test_unknown_values_are_named(tmp_path: Path, field: str, bad_value: str) -> None:
    kwargs = {"lever_name" if field == "lever" else "metric": bad_value}
    with pytest.raises(OptimizerSpecError, match=bad_value):
        load_spec(_write_spec(tmp_path, **kwargs))


def test_more_than_eight_levers_names_limit(tmp_path: Path) -> None:
    with pytest.raises(OptimizerSpecError, match="at most 8"):
        load_spec(_write_spec(tmp_path, lever_count=9))


def test_stale_baseline_warning_names_fingerprint_change(tmp_path: Path) -> None:
    config = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    prior = tmp_path / "optimizer_results.json"
    prior.write_text(
        '{"baseline_config_fingerprint": "old-fingerprint"}', encoding="utf-8"
    )
    warning = stale_baseline_warning(config, prior)
    assert warning is not None
    assert "old-fingerpr" in warning
    assert fingerprint_baseline(config)[:12] in warning
