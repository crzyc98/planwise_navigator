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
from tests.test_dbt_var_coverage import _all_exported_vars

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


_STEPS = "deferral_rate_changes"
_MULT = "deferral_rate_changes.multipliers"
_DMR = "deferral_match_response"
# Enums and constrained lists reject the generic mutation; each entry is a valid
# change (linked sub-rates move together so they still sum to 1).
VALID_ALTERNATES: dict[str, dict[str, Any]] = {
    **{
        f"enrollment.auto_enrollment.opt_out_rates.multipliers.{dim}": {
            f"enrollment.auto_enrollment.opt_out_rates.multipliers.{dim}": [
                {"min": 0, "multiplier": 1.0}
            ]
        }
        for dim in ("age", "income")
    },
    "enrollment.auto_enrollment.reenrollment_sweep.method": {
        "enrollment.auto_enrollment.reenrollment_sweep.method": "into_aip"
    },
    "enrollment.below_default.share_tiers": {
        "enrollment.below_default.share_tiers": [
            {"max_auto_enroll_default_rate": None, "share": 0.05}
        ]
    },
    "enrollment.below_default.steps": {
        "enrollment.below_default.steps": [{"pp": 1, "weight": 1.0}]
    },
    "employer_core_contribution.integration.level_mode": {
        "employer_core_contribution.integration.level_mode": "percent_of_ss_wage_base"
    },
    "deferral_auto_escalation.mode": {
        "deferral_auto_escalation.mode": "participant_elected"
    },
    "easy_enroll.packages": {"easy_enroll.packages": [{"rate": 0.06, "share": 1.0}]},
    **{
        f"{_DMR}.{rate}": {f"{_DMR}.{rate}": 0.55, f"{_DMR}.{other}": 0.45}
        for rate, other in [
            ("upward_maximize_rate", "upward_partial_increase_rate"),
            ("upward_partial_increase_rate", "upward_maximize_rate"),
            ("downward_reduce_to_max_rate", "downward_partial_decrease_rate"),
            ("downward_partial_decrease_rate", "downward_reduce_to_max_rate"),
        ]
    },
    **{
        f"{_MULT}.{direction}.{dimension}": {
            f"{_MULT}.{direction}.{dimension}": [{"min": 0, "multiplier": 1.0}]
        }
        for direction in ("increase", "decrease")
        for dimension in ("age", "income", "tenure")
    },
    **{
        f"{_STEPS}.{name}": {f"{_STEPS}.{name}": [{"pp": 1, "weight": 1.0}]}
        for name in ("increase_steps", "decrease_steps")
    },
}
SINGLE_VALUE: dict[str, str] = {
    "deferral_match_response.effective_timing": "Literal['first_year'] allows one value",
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
    untestable = []
    for path, value in paths.items():
        if path in SINGLE_VALUE:
            continue
        changed = deepcopy(raw)
        for target, new in VALID_ALTERNATES.get(path, {path: _mutate(value)}).items():
            _set(changed, target, new)
        try:
            exported = to_dbt_vars(SimulationConfig.model_validate(changed))
        except ValidationError:
            untestable.append(path)
            continue
        if exported == baseline and path not in PYTHON_CONSUMED:
            disconnected.append(path)
    assert not untestable, f"Add a valid alternate to VALID_ALTERNATES: {untestable}"
    assert not disconnected, f"YAML settings without consumers: {disconnected}"


def _set(data: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    for key in keys[:-1]:
        data = data[key]
    data[keys[-1]] = value


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
    exported = _all_exported_vars()
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
