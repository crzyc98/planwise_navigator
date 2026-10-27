"""Keep shipped YAML controls and exported dbt variables connected to readers."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from pydantic import ValidationError

from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.config.export import to_dbt_vars
from tests.test_dbt_var_coverage import _maximal_config

pytestmark = [pytest.mark.fast, pytest.mark.config]
ROOT = Path(__file__).resolve().parents[1]
PYTHON_CONSUMED: dict[str, str] = {
    "setup.clear_tables": "planalign_orchestrator/pipeline/state_manager.py: controls table cleanup",
    "setup.clear_mode": "planalign_orchestrator/pipeline/state_manager.py: controls table cleanup",
    "setup.clear_table_patterns": "planalign_orchestrator/pipeline/state_manager.py: controls table cleanup",
    "orchestrator.threading.enabled": "planalign_orchestrator/construction/builder.py: configures DbtRunner threading",
    "orchestrator.threading.parallelization.enabled": "planalign_orchestrator/orchestrator_setup.py: constructs optional parallel engine",
    "orchestrator.threading.parallelization.max_workers": "planalign_orchestrator/orchestrator_setup.py: constructs optional parallel engine",
    "orchestrator.threading.parallelization.enable_conditional_parallelization": "planalign_orchestrator/pipeline/stage_execution_strategies.py: controls parallel stage safety",
    "orchestrator.threading.parallelization.safety.validate_execution_safety": "planalign_orchestrator/pipeline/stage_execution_strategies.py: controls parallel stage safety",
    "orchestrator.threading.resource_management.memory_monitoring.monitoring_interval_seconds": "planalign_orchestrator/orchestrator_setup.py: forwards monitor sampling configuration to resources/manager.py",
    "orchestrator.threading.resource_management.memory_monitoring.history_size": "planalign_orchestrator/orchestrator_setup.py: forwards monitor sampling configuration to resources/manager.py",
    "orchestrator.threading.resource_management.memory_monitoring.thresholds.moderate_mb": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/memory_monitor.py",
    "orchestrator.threading.resource_management.memory_monitoring.thresholds.high_mb": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/memory_monitor.py",
    "orchestrator.threading.resource_management.memory_monitoring.thresholds.critical_mb": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/memory_monitor.py",
    "orchestrator.threading.resource_management.memory_monitoring.thresholds.gc_trigger_mb": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/memory_monitor.py",
    "orchestrator.threading.resource_management.cpu_monitoring.monitoring_interval_seconds": "planalign_orchestrator/orchestrator_setup.py: forwards monitor sampling configuration to resources/manager.py",
    "orchestrator.threading.resource_management.cpu_monitoring.history_size": "planalign_orchestrator/orchestrator_setup.py: forwards monitor sampling configuration to resources/manager.py",
    "orchestrator.threading.resource_management.cpu_monitoring.thresholds.moderate_percent": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/cpu_monitor.py",
    "orchestrator.threading.resource_management.cpu_monitoring.thresholds.high_percent": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/cpu_monitor.py",
    "orchestrator.threading.resource_management.cpu_monitoring.thresholds.critical_percent": "planalign_orchestrator/orchestrator_setup.py: forwards thresholds to planalign_orchestrator/resources/cpu_monitor.py",
    "storage.max_runs_per_scenario": "planalign_api/services/simulation/run_archiver.py: prunes archived runs",
    "storage.artifact_max_age_days": "planalign_cli/commands/gc.py: selects expired artifacts",
}
EXPORT_PYTHON_CONSUMED: dict[str, str] = {
    "dbt_threads": "planalign_orchestrator/dbt_runner.py: dbt execution threads",
    "event_shards": "planalign_orchestrator/pipeline/stage_execution_strategies.py: shard selectors",
    "max_parallel_years": "planalign_orchestrator/pipeline_orchestrator.py: execution diagnostics",
}


def _leaves(data: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from _leaves(value, path)
        else:
            yield path, value


def _mutate(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value * 0.83 + 0.0071
    if isinstance(value, str):
        return value + "_mut"
    if isinstance(value, list):
        return value + [deepcopy(value[-1]) if value else "_mut"]
    if value is None:
        return 2027
    raise TypeError(f"Unsupported YAML leaf: {value!r}")


def test_each_yaml_leaf_has_a_consumer() -> None:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    baseline = to_dbt_vars(SimulationConfig.model_validate(deepcopy(raw)))
    disconnected = []
    paths = dict(_leaves(raw))
    assert set(PYTHON_CONSUMED) <= paths.keys()
    for path, value in paths.items():
        changed = deepcopy(raw)
        parent = changed
        keys = path.split(".")
        for key in keys[:-1]:
            parent = parent[key]
        parent[keys[-1]] = _mutate(value)
        try:
            exported = to_dbt_vars(SimulationConfig.model_validate(changed))
        except ValidationError:
            continue
        if exported == baseline and path not in PYTHON_CONSUMED:
            disconnected.append(path)
    assert not disconnected, f"YAML settings without consumers: {disconnected}"


def _dbt_var_readers() -> tuple[set[str], set[str]]:
    files = [ROOT / "dbt/dbt_project.yml"]
    for directory in ("models", "macros", "tests"):
        files.extend((ROOT / "dbt" / directory).rglob("*.sql"))
    names: set[str] = set()
    prefixes: set[str] = set()
    pattern = r"\bvar\(\s*['\"]([\w]+)['\"]\s*(~)?"
    for file in files:
        for name, dynamic in re.findall(pattern, file.read_text()):
            (prefixes if dynamic else names).add(name)
    return names, prefixes


def test_every_exported_var_has_a_reader() -> None:
    names, prefixes = _dbt_var_readers()
    exported = set(to_dbt_vars(_maximal_config()))
    unread = {
        name
        for name in exported - names - EXPORT_PYTHON_CONSUMED.keys()
        if not any(name.startswith(prefix) for prefix in prefixes)
    }
    assert not unread, f"Exported dbt vars without readers: {sorted(unread)}"


# Saved Studio configs can still carry every removed modeled control. These
# nested models accept extra keys (Pydantic's default extra='ignore').
LEGACY_CONFIG: dict[str, Any] = {
    "optimization": {
        "level": "baseline",
        "max_workers": 1,
        "batch_size": 1000,
        "memory_limit_gb": 4.0,
        "event_generation": {
            "polars": {
                "enabled": True,
                "max_threads": 16,
                "batch_size": 10000,
                "output_path": "data/parquet/events",
                "enable_compression": True,
                "enable_profiling": False,
                "fallback_on_error": True,
                "use_cohort_engine": True,
                "cohort_output_dir": "outputs/polars_cohorts",
                "state_accumulation_enabled": True,
                "state_accumulation_fallback_on_error": True,
                "state_accumulation_validate_results": True,
            }
        },
    },
    "orchestrator": {
        "threading": {
            "parallelization": {
                "memory_limit_mb": 6000.0,
                "resource_monitoring": True,
                "safety": {
                    "fallback_on_resource_pressure": True,
                    "abort_on_dependency_conflict": True,
                    "max_retries_per_model": 2,
                },
            },
            "resource_management": {
                "enabled": True,
                "adjustment_cooldown_seconds": 30,
                "benchmarking_enabled": True,
                "benchmark_thread_counts": [1, 2, 4],
                "auto_cleanup_enabled": True,
                "cpu_monitoring": {"enabled": True},
            },
        }
    },
    "enrollment": {
        "proactive_enrollment": {
            "enabled": True,
            "probability_by_demographics": {"young": 0.25, "senior": 0.75},
        },
        "timing": {"business_day_adjustment": True},
    },
}


def test_legacy_saved_controls_load_and_do_not_change_exports() -> None:
    raw = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    baseline = to_dbt_vars(SimulationConfig.model_validate(deepcopy(raw)))
    for path, value in _leaves(LEGACY_CONFIG):
        parent = raw
        keys = path.split(".")
        for key in keys[:-1]:
            parent = parent.setdefault(key, {})
        parent[keys[-1]] = value
    assert to_dbt_vars(SimulationConfig.model_validate(raw)) == baseline
