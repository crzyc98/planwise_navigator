"""Baseline configuration loading, fingerprinting, and drift checks."""

from __future__ import annotations

import json
from pathlib import Path

from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from planalign_orchestrator.run_metadata import compute_config_fingerprint


def load_baseline(path: Path | str) -> SimulationConfig:
    """Load a baseline without environment-dependent overrides."""
    return load_simulation_config(path, env_overrides=False)


def fingerprint_baseline(config: SimulationConfig) -> str:
    """Return the canonical config fingerprint used by scenario provenance."""
    return compute_config_fingerprint(config)


def baseline_changed(config: SimulationConfig, prior_fingerprint: str) -> bool:
    """Return whether a resolved baseline differs from a prior optimizer run."""
    return fingerprint_baseline(config) != prior_fingerprint


def stale_baseline_warning(
    config: SimulationConfig, prior_run_path: Path
) -> str | None:
    """Describe baseline drift against a persisted optimizer result, if present."""
    if not prior_run_path.exists():
        return None
    payload = json.loads(prior_run_path.read_text(encoding="utf-8"))
    prior = payload.get("baseline_config_fingerprint")
    if not isinstance(prior, str) or not baseline_changed(config, prior):
        return None
    return (
        "resolved baseline differs from the prior optimizer run "
        f"({prior[:12]} -> {fingerprint_baseline(config)[:12]})"
    )
