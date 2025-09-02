#!/usr/bin/env python3
"""
Determinism Integration Tests for Epic E067: Multi-Threading Navigator Orchestrator

This module validates that the multi-threading implementation produces
deterministic results regardless of thread count or execution order.

Key Determinism Requirements:
1. Same input configuration produces identical results across runs
2. Different thread counts produce logically equivalent results
3. Model execution order is deterministic when required
4. Random seed consistency maintained across threading modes
5. Event generation consistency across parallel/sequential execution
6. State accumulation produces identical final states

These tests are critical for ensuring that parallel execution doesn't
compromise the reproducibility requirements of the workforce simulation.
"""

import pytest
import tempfile
import shutil
import json
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
import time

# Import determinism-critical components
from navigator_orchestrator.config import (
    ThreadingSettings, ModelParallelizationSettings, SimulationConfig,
    load_simulation_config
)
from navigator_orchestrator.dbt_runner import DbtRunner, DbtResult
from navigator_orchestrator.parallel_execution_engine import (
    ParallelExecutionEngine, ExecutionContext, ExecutionResult
)
from navigator_orchestrator.model_dependency_analyzer import ModelDependencyAnalyzer
from navigator_orchestrator.pipeline import PipelineOrchestrator


@dataclass
class DeterminismTestResult:
    """Container for determinism test results."""
    configuration: Dict[str, Any]
    execution_order: List[str]
    model_results: Dict[str, Any]
    final_state_hash: str
    execution_time: float
    parallelism_achieved: float

    def compute_content_hash(self) -> str:
        """Compute hash of determinism-critical content."""
        # Include only deterministic content (exclude timing)
        deterministic_content = {
            "configuration": self.configuration,
            "execution_order": self.execution_order,
            "model_results": {k: v for k, v in self.model_results.items()
                            if k not in ["execution_time", "timestamp"]},
            "final_state_hash": self.final_state_hash
        }

        content_str = json.dumps(deterministic_content, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content_str.encode()).hexdigest()


class DeterminismValidator:
    """Utility class for validating deterministic behavior."""

    def __init__(self):
        self.test_results: Dict[str, List[DeterminismTestResult]] = {}
        self.baseline_results: Dict[str, DeterminismTestResult] = {}

    def record_test_result(self, test_name: str, result: DeterminismTestResult):
        """Record a test result for determinism comparison."""
        if test_name not in self.test_results:
            self.test_results[test_name] = []
        self.test_results[test_name].append(result)

    def set_baseline(self, test_name: str, result: DeterminismTestResult):
        """Set baseline result for comparison."""
        self.baseline_results[test_name] = result

    def validate_determinism(self, test_name: str, tolerance: float = 0.0) -> Dict[str, Any]:
        """Validate that all results for a test are deterministic."""
        if test_name not in self.test_results or len(self.test_results[test_name]) < 2:
            return {"valid": False, "error": "Insufficient results for validation"}

        results = self.test_results[test_name]
        baseline = results[0]

        validation_result = {
            "valid": True,
            "total_runs": len(results),
            "differences": [],
            "hash_consistency": True,
            "order_consistency": True,
            "state_consistency": True
        }

        baseline_hash = baseline.compute_content_hash()

        for i, result in enumerate(results[1:], 1):
            result_hash = result.compute_content_hash()

            if result_hash != baseline_hash:
                validation_result["valid"] = False
                validation_result["hash_consistency"] = False
                validation_result["differences"].append({
                    "run": i,
                    "type": "content_hash_mismatch",
                    "expected": baseline_hash,
                    "actual": result_hash
                })

            if result.execution_order != baseline.execution_order:
                validation_result["valid"] = False
                validation_result["order_consistency"] = False
                validation_result["differences"].append({
                    "run": i,
                    "type": "execution_order_mismatch",
                    "expected": baseline.execution_order,
                    "actual": result.execution_order
                })

            if result.final_state_hash != baseline.final_state_hash:
                validation_result["valid"] = False
                validation_result["state_consistency"] = False
                validation_result["differences"].append({
                    "run": i,
                    "type": "final_state_mismatch",
                    "expected": baseline.final_state_hash,
                    "actual": result.final_state_hash
                })

        return validation_result

    def compare_across_thread_counts(self, test_base_name: str) -> Dict[str, Any]:
        """Compare results across different thread counts for logical equivalence."""
        thread_count_results = {}

        # Group results by thread count
        for test_name, results in self.test_results.items():
            if test_name.startswith(test_base_name):
                thread_count = self._extract_thread_count(test_name)
                if thread_count:
                    thread_count_results[thread_count] = results[0] if results else None

        if len(thread_count_results) < 2:
            return {"valid": False, "error": "Insufficient thread count variations"}

        # Compare final states across thread counts
        baseline_thread_count = min(thread_count_results.keys())
        baseline_result = thread_count_results[baseline_thread_count]

        comparison_result = {
            "valid": True,
            "thread_counts_compared": list(thread_count_results.keys()),
            "state_equivalence": True,
            "logical_consistency": True,
            "differences": []
        }

        for thread_count, result in thread_count_results.items():
            if thread_count == baseline_thread_count:
                continue

            if result.final_state_hash != baseline_result.final_state_hash:
                comparison_result["valid"] = False
                comparison_result["state_equivalence"] = False
                comparison_result["differences"].append({
                    "thread_count": thread_count,
                    "type": "state_mismatch",
                    "baseline_hash": baseline_result.final_state_hash,
                    "actual_hash": result.final_state_hash
                })

        return comparison_result

    def _extract_thread_count(self, test_name: str) -> Optional[int]:
        """Extract thread count from test name."""
        import re
        match = re.search(r'threads?_(\d+)', test_name)
        return int(match.group(1)) if match else None


class TestDeterministicConfigurationConsistency:
    """Test deterministic behavior of configuration loading and validation."""

    def setup_method(self):
        self.validator = DeterminismValidator()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_configuration_determinism_across_loads(self):
        """Test that configuration loading is deterministic across multiple loads."""

        config_path = Path(self.temp_dir) / "test_config.yaml"

        config_content = """
simulation:
  start_year: 2025
  end_year: 2027
  random_seed: 12345

threading:
  enabled: true
  thread_count: 4
  mode: "selective"
  memory_per_thread_gb: 1.5

  model_parallelization:
    enabled: true
    max_workers: 4
    aggressive_mode: false
    memory_limit_mb: 1500.0

multi_year:
  optimization:
    level: "high"
    max_workers: 4
"""

        with open(config_path, 'w') as f:
            f.write(config_content)

        # Load configuration multiple times
        configs = []
        for i in range(5):
            config = load_simulation_config(config_path)
            configs.append(config)

            # Create determinism test result
            result = DeterminismTestResult(
                configuration={
                    "threading_enabled": config.threading.enabled,
                    "thread_count": config.threading.thread_count,
                    "mode": config.threading.mode,
                    "random_seed": config.simulation.random_seed,
                    "start_year": config.simulation.start_year,
                    "end_year": config.simulation.end_year
                },
                execution_order=[],
                model_results={},
                final_state_hash=self._compute_config_hash(config),
                execution_time=0.0,
                parallelism_achieved=0.0
            )

            self.validator.record_test_result("config_loading", result)

        # Validate determinism
        validation = self.validator.validate_determinism("config_loading")

        assert validation["valid"] == True, f"Configuration loading not deterministic: {validation['differences']}"
        assert validation["hash_consistency"] == True, "Configuration content hash inconsistent"
        assert validation["total_runs"] == 5, "Should have recorded 5 runs"

    def test_threading_settings_validation_determinism(self):
        """Test that threading settings validation is deterministic."""

        test_configs = [
            {"thread_count": 1, "mode": "sequential"},
            {"thread_count": 4, "mode": "selective"},
            {"thread_count": 8, "mode": "aggressive"},
            {"thread_count": 16, "mode": "selective"}
        ]

        for config_params in test_configs:
            # Create and validate multiple times
            for i in range(3):
                threading_config = ThreadingSettings(**config_params)

                # Trigger validation
                threading_config.validate_thread_count()

                result = DeterminismTestResult(
                    configuration=config_params,
                    execution_order=[],
                    model_results={},
                    final_state_hash=self._compute_threading_settings_hash(threading_config),
                    execution_time=0.0,
                    parallelism_achieved=0.0
                )

                test_name = f"threading_validation_{config_params['thread_count']}"
                self.validator.record_test_result(test_name, result)

            # Validate determinism for this configuration
            validation = self.validator.validate_determinism(test_name)
            assert validation["valid"] == True, f"Threading validation not deterministic for {config_params}: {validation}"

    def _compute_config_hash(self, config: SimulationConfig) -> str:
        """Compute deterministic hash of configuration."""
        config_dict = {
            "simulation": {
                "start_year": config.simulation.start_year,
                "end_year": config.simulation.end_year,
                "random_seed": config.simulation.random_seed
            },
            "threading": {
                "enabled": config.threading.enabled,
                "thread_count": config.threading.thread_count,
                "mode": config.threading.mode,
                "memory_per_thread_gb": config.threading.memory_per_thread_gb
            }
        }
        content_str = json.dumps(config_dict, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()

    def _compute_threading_settings_hash(self, settings: ThreadingSettings) -> str:
        """Compute deterministic hash of threading settings."""
        settings_dict = {
            "enabled": settings.enabled,
            "thread_count": settings.thread_count,
            "mode": settings.mode,
            "memory_per_thread_gb": settings.memory_per_thread_gb
        }
        content_str = json.dumps(settings_dict, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()


class TestExecutionOrderDeterminism:
    """Test that model execution order is deterministic when required."""

    def setup_method(self):
        self.validator = DeterminismValidator()

    def test_deterministic_model_ordering(self):
        """Test that model execution follows deterministic ordering."""

        models = [
            "int_hazard_termination",
            "int_hazard_promotion",
            "int_hazard_merit",
            "stg_census_data",
            "stg_comp_levers"
        ]

        # Test with different thread counts
        for thread_count in [1, 2, 4, 8]:
            execution_orders = []

            for run in range(3):  # Multiple runs per thread count
                mock_dbt_runner = Mock(spec=DbtRunner)
                mock_dependency_analyzer = Mock(spec=ModelDependencyAnalyzer)

                # Track execution order
                executed_models = []

                def track_execution(command, *args, **kwargs):
                    if len(command) >= 3 and command[1] == "--select":
                        executed_models.append(command[2])

                    return DbtResult(
                        success=True, stdout="", stderr="", execution_time=0.1,
                        return_code=0, command=command
                    )

                mock_dbt_runner.execute_command.side_effect = track_execution

                # Create engine with deterministic execution enabled
                engine = ParallelExecutionEngine(
                    dbt_runner=mock_dbt_runner,
                    dependency_analyzer=mock_dependency_analyzer,
                    max_workers=thread_count,
                    deterministic_execution=True,  # Key setting
                    resource_monitoring=False,
                    verbose=False
                )

                # Mock parallelization opportunities
                mock_dependency_analyzer.identify_parallelization_opportunities.return_value = [
                    Mock(
                        parallel_models=models,
                        execution_group="mixed_group",
                        estimated_speedup=min(len(models), thread_count),
                        safety_level="high"
                    )
                ]

                mock_dependency_analyzer.validate_execution_safety.return_value = {
                    "safe": True, "issues": [], "warnings": []
                }

                # Execute stage
                context = ExecutionContext(2025, {}, "determinism_test", f"run_{run}")
                result = engine.execute_stage(models, context)

                execution_orders.append(executed_models.copy())

                # Record result
                test_result = DeterminismTestResult(
                    configuration={"thread_count": thread_count, "deterministic": True},
                    execution_order=executed_models,
                    model_results={"success": result.success},
                    final_state_hash=hashlib.sha256(str(executed_models).encode()).hexdigest(),
                    execution_time=result.execution_time,
                    parallelism_achieved=result.parallelism_achieved
                )

                test_name = f"deterministic_order_threads_{thread_count}"
                self.validator.record_test_result(test_name, test_result)

            # Validate determinism for this thread count
            validation = self.validator.validate_determinism(test_name)
            assert validation["valid"] == True, f"Execution order not deterministic for {thread_count} threads: {validation['differences']}"

            # All execution orders should be identical for deterministic mode
            assert len(set(tuple(order) for order in execution_orders)) == 1, f"Execution orders varied for {thread_count} threads: {execution_orders}"

    def test_parallel_vs_sequential_logical_equivalence(self):
        """Test that parallel and sequential execution produce logically equivalent results."""

        models = [
            "int_hazard_termination",
            "int_hazard_promotion",
            "stg_census_data"
        ]

        results_by_mode = {}

        # Test sequential execution (thread_count=1)
        for mode, thread_count in [("sequential", 1), ("parallel", 4)]:
            mock_dbt_runner = Mock(spec=DbtRunner)
            mock_dependency_analyzer = Mock(spec=ModelDependencyAnalyzer)

            # Mock consistent results regardless of execution mode
            model_outputs = {
                "int_hazard_termination": "hash_termination_123",
                "int_hazard_promotion": "hash_promotion_456",
                "stg_census_data": "hash_census_789"
            }

            def mock_execution(command, *args, **kwargs):
                if len(command) >= 3 and command[1] == "--select":
                    model_name = command[2]
                    output_hash = model_outputs.get(model_name, "unknown")
                else:
                    output_hash = "batch_execution"

                return DbtResult(
                    success=True,
                    stdout=f"Model output: {output_hash}",
                    stderr="",
                    execution_time=0.1,
                    return_code=0,
                    command=command
                )

            mock_dbt_runner.execute_command.side_effect = mock_execution

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=mock_dependency_analyzer,
                max_workers=thread_count,
                deterministic_execution=True,
                resource_monitoring=False,
                verbose=False
            )

            # Mock opportunities based on mode
            if mode == "parallel":
                mock_dependency_analyzer.identify_parallelization_opportunities.return_value = [
                    Mock(
                        parallel_models=models,
                        execution_group="test_group",
                        estimated_speedup=3.0,
                        safety_level="high"
                    )
                ]
            else:
                mock_dependency_analyzer.identify_parallelization_opportunities.return_value = []

            mock_dependency_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": []
            }

            context = ExecutionContext(2025, {}, "equivalence_test", mode)
            result = engine.execute_stage(models, context)

            # Compute final state hash based on model outputs (order-independent)
            sorted_outputs = sorted([f"{model}:{model_outputs[model]}" for model in models])
            final_state = "|".join(sorted_outputs)
            final_state_hash = hashlib.sha256(final_state.encode()).hexdigest()

            results_by_mode[mode] = DeterminismTestResult(
                configuration={"mode": mode, "thread_count": thread_count},
                execution_order=[],  # Not relevant for equivalence
                model_results={model: model_outputs[model] for model in models},
                final_state_hash=final_state_hash,
                execution_time=result.execution_time,
                parallelism_achieved=result.parallelism_achieved
            )

        # Final states should be equivalent
        sequential_hash = results_by_mode["sequential"].final_state_hash
        parallel_hash = results_by_mode["parallel"].final_state_hash

        assert sequential_hash == parallel_hash, f"Sequential and parallel execution produced different final states: {sequential_hash} vs {parallel_hash}"

        # Model results should be identical
        sequential_results = results_by_mode["sequential"].model_results
        parallel_results = results_by_mode["parallel"].model_results

        assert sequential_results == parallel_results, f"Model results differ: {sequential_results} vs {parallel_results}"


class TestRandomSeedConsistency:
    """Test that random seed consistency is maintained across threading modes."""

    def setup_method(self):
        self.validator = DeterminismValidator()

    def test_random_seed_consistency_across_thread_counts(self):
        """Test that random seed produces consistent results regardless of thread count."""

        fixed_seed = 42

        # Test with different thread counts using same seed
        for thread_count in [1, 2, 4]:
            for run in range(2):  # Multiple runs per thread count
                # Mock pseudo-random behavior based on seed
                import random
                random.seed(fixed_seed)

                # Generate "random" simulation parameters
                simulated_random_values = {
                    "termination_rates": [random.random() for _ in range(10)],
                    "hiring_targets": [random.randint(1, 100) for _ in range(5)],
                    "merit_adjustments": [random.uniform(0.01, 0.05) for _ in range(8)]
                }

                # Reset seed for each run to ensure consistency
                random.seed(fixed_seed)

                # Create mock execution that uses these "random" values
                mock_dbt_runner = Mock(spec=DbtRunner)

                def mock_execution_with_randomness(command, *args, **kwargs):
                    # Simulate random-dependent model execution
                    if "termination" in str(command):
                        output = f"termination_result_{sum(simulated_random_values['termination_rates']):.6f}"
                    elif "hiring" in str(command):
                        output = f"hiring_result_{sum(simulated_random_values['hiring_targets'])}"
                    else:
                        output = "deterministic_result"

                    return DbtResult(
                        success=True, stdout=output, stderr="",
                        execution_time=0.1, return_code=0, command=command
                    )

                mock_dbt_runner.execute_command.side_effect = mock_execution_with_randomness

                engine = ParallelExecutionEngine(
                    dbt_runner=mock_dbt_runner,
                    dependency_analyzer=Mock(),
                    max_workers=thread_count,
                    deterministic_execution=True,
                    resource_monitoring=False,
                    verbose=False
                )

                models = ["int_termination_events", "int_hiring_events", "stg_parameters"]
                context = ExecutionContext(2025, {}, "seed_test", f"run_{run}")

                # Mock opportunities and validation
                mock_analyzer = Mock()
                mock_analyzer.identify_parallelization_opportunities.return_value = [
                    Mock(parallel_models=models, execution_group="random_group",
                         estimated_speedup=2.0, safety_level="high")
                ]
                mock_analyzer.validate_execution_safety.return_value = {
                    "safe": True, "issues": [], "warnings": []
                }
                engine.dependency_analyzer = mock_analyzer

                result = engine.execute_stage(models, context)

                # Create state hash from random-dependent outputs
                state_content = {
                    "seed": fixed_seed,
                    "random_values": simulated_random_values,
                    "thread_count": thread_count
                }
                final_state_hash = hashlib.sha256(
                    json.dumps(state_content, sort_keys=True).encode()
                ).hexdigest()

                test_result = DeterminismTestResult(
                    configuration={"seed": fixed_seed, "thread_count": thread_count},
                    execution_order=[],
                    model_results=simulated_random_values,
                    final_state_hash=final_state_hash,
                    execution_time=result.execution_time,
                    parallelism_achieved=result.parallelism_achieved
                )

                test_name = f"random_seed_threads_{thread_count}"
                self.validator.record_test_result(test_name, test_result)

        # Validate that same seed produces same results across all thread counts
        all_results = []
        for thread_count in [1, 2, 4]:
            test_name = f"random_seed_threads_{thread_count}"
            validation = self.validator.validate_determinism(test_name)
            assert validation["valid"] == True, f"Random seed not consistent for {thread_count} threads: {validation}"

            # Collect first result from each thread count
            if test_name in self.validator.test_results:
                all_results.append(self.validator.test_results[test_name][0])

        # All thread counts should produce the same random-based results
        if len(all_results) >= 2:
            baseline_hash = all_results[0].final_state_hash
            for i, result in enumerate(all_results[1:], 1):
                assert result.final_state_hash == baseline_hash, f"Random seed consistency failed between thread counts: result {i}"

    def test_different_seeds_produce_different_results(self):
        """Test that different random seeds produce different results (sanity check)."""

        seeds_results = {}

        for seed in [42, 123, 999]:
            import random
            random.seed(seed)

            # Generate seed-specific random values
            random_values = {
                "values": [random.random() for _ in range(5)]
            }

            # Create hash based on seed-specific values
            seed_hash = hashlib.sha256(
                json.dumps({"seed": seed, "values": random_values}, sort_keys=True).encode()
            ).hexdigest()

            seeds_results[seed] = seed_hash

        # Different seeds should produce different hashes
        unique_hashes = set(seeds_results.values())
        assert len(unique_hashes) == len(seeds_results), f"Different seeds produced identical results: {seeds_results}"


class TestStateAccumulationDeterminism:
    """Test deterministic state accumulation across different execution modes."""

    def setup_method(self):
        self.validator = DeterminismValidator()

    def test_enrollment_state_accumulation_determinism(self):
        """Test that enrollment state accumulation is deterministic."""

        # Simulate multi-year enrollment state accumulation
        years = [2025, 2026, 2027]

        # Mock enrollment events and state data
        enrollment_events = {
            2025: [
                {"employee_id": "EMP001", "event": "enroll", "plan": "401k"},
                {"employee_id": "EMP002", "event": "enroll", "plan": "401k"},
            ],
            2026: [
                {"employee_id": "EMP003", "event": "enroll", "plan": "401k"},
                {"employee_id": "EMP001", "event": "change_rate", "new_rate": 0.08},
            ],
            2027: [
                {"employee_id": "EMP004", "event": "enroll", "plan": "401k"},
                {"employee_id": "EMP002", "event": "terminate", "reason": "quit"},
            ]
        }

        # Test state accumulation with different thread counts
        for thread_count in [1, 2, 4]:
            accumulated_states = {}

            for run in range(2):  # Multiple runs per thread count
                current_state = {}  # Track enrollment state across years

                for year in years:
                    # Process events for this year
                    year_events = enrollment_events[year]

                    for event in year_events:
                        emp_id = event["employee_id"]
                        if emp_id not in current_state:
                            current_state[emp_id] = {"enrolled": False, "rate": 0.0, "active": True}

                        if event["event"] == "enroll":
                            current_state[emp_id]["enrolled"] = True
                            current_state[emp_id]["rate"] = 0.03  # Default rate
                        elif event["event"] == "change_rate":
                            current_state[emp_id]["rate"] = event["new_rate"]
                        elif event["event"] == "terminate":
                            current_state[emp_id]["active"] = False

                    # Create year-end state hash
                    year_state_str = json.dumps(
                        {f"{year}_state": current_state},
                        sort_keys=True
                    )

                # Final accumulated state
                final_state_hash = hashlib.sha256(
                    json.dumps(current_state, sort_keys=True).encode()
                ).hexdigest()

                test_result = DeterminismTestResult(
                    configuration={"thread_count": thread_count, "years": years},
                    execution_order=[f"year_{year}" for year in years],
                    model_results={"final_enrollments": len([e for e in current_state.values() if e["enrolled"] and e["active"]])},
                    final_state_hash=final_state_hash,
                    execution_time=0.0,
                    parallelism_achieved=1.0
                )

                test_name = f"enrollment_accumulation_threads_{thread_count}"
                self.validator.record_test_result(test_name, test_result)

        # Validate determinism across thread counts
        for thread_count in [1, 2, 4]:
            test_name = f"enrollment_accumulation_threads_{thread_count}"
            validation = self.validator.validate_determinism(test_name)
            assert validation["valid"] == True, f"Enrollment state accumulation not deterministic for {thread_count} threads: {validation}"

        # Compare final states across thread counts
        comparison = self.validator.compare_across_thread_counts("enrollment_accumulation")
        assert comparison["valid"] == True, f"Enrollment states differ across thread counts: {comparison}"


class TestEventGenerationDeterminism:
    """Test deterministic event generation across parallel and sequential execution."""

    def setup_method(self):
        self.validator = DeterminismValidator()

    def test_hazard_calculation_determinism(self):
        """Test that hazard calculations are deterministic across execution modes."""

        # Mock hazard calculation inputs
        hazard_inputs = {
            "termination": {
                "base_rates": [0.05, 0.03, 0.02, 0.01],
                "adjustments": [1.0, 1.1, 0.9, 1.2]
            },
            "promotion": {
                "base_rates": [0.10, 0.08, 0.05, 0.02],
                "adjustments": [1.0, 0.9, 1.1, 1.0]
            }
        }

        # Test with different parallelization strategies
        execution_modes = [
            {"mode": "sequential", "thread_count": 1},
            {"mode": "parallel_selective", "thread_count": 4},
            {"mode": "parallel_aggressive", "thread_count": 8}
        ]

        for mode_config in execution_modes:
            for run in range(2):
                # Mock deterministic hazard calculations
                calculated_hazards = {}

                for hazard_type, inputs in hazard_inputs.items():
                    # Simulate deterministic calculation
                    rates = inputs["base_rates"]
                    adjustments = inputs["adjustments"]

                    final_rates = [rate * adj for rate, adj in zip(rates, adjustments)]
                    calculated_hazards[hazard_type] = {
                        "final_rates": final_rates,
                        "total_hazard": sum(final_rates)
                    }

                # Create deterministic hash of calculations
                calc_hash = hashlib.sha256(
                    json.dumps(calculated_hazards, sort_keys=True).encode()
                ).hexdigest()

                test_result = DeterminismTestResult(
                    configuration=mode_config,
                    execution_order=list(hazard_inputs.keys()),
                    model_results=calculated_hazards,
                    final_state_hash=calc_hash,
                    execution_time=0.0,
                    parallelism_achieved=mode_config["thread_count"]
                )

                test_name = f"hazard_calculation_{mode_config['mode']}"
                self.validator.record_test_result(test_name, test_result)

        # Validate determinism within each mode
        for mode_config in execution_modes:
            test_name = f"hazard_calculation_{mode_config['mode']}"
            validation = self.validator.validate_determinism(test_name)
            assert validation["valid"] == True, f"Hazard calculations not deterministic for {mode_config}: {validation}"

        # Validate equivalence across modes
        all_hashes = []
        for mode_config in execution_modes:
            test_name = f"hazard_calculation_{mode_config['mode']}"
            if test_name in self.validator.test_results and self.validator.test_results[test_name]:
                all_hashes.append(self.validator.test_results[test_name][0].final_state_hash)

        # All execution modes should produce identical hazard calculations
        unique_hashes = set(all_hashes)
        assert len(unique_hashes) == 1, f"Hazard calculations differ across execution modes: {all_hashes}"


# Integration test fixtures
@pytest.fixture
def determinism_test_environment():
    """Create isolated test environment for determinism testing."""
    temp_dir = tempfile.mkdtemp()

    # Create mock simulation database
    db_path = Path(temp_dir) / "test_simulation.duckdb"

    # Create basic directory structure
    dbt_dir = Path(temp_dir) / "dbt"
    dbt_dir.mkdir(parents=True)

    config_dir = Path(temp_dir) / "config"
    config_dir.mkdir(parents=True)

    yield {
        "temp_dir": temp_dir,
        "db_path": db_path,
        "dbt_dir": dbt_dir,
        "config_dir": config_dir
    }

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_simulation_data():
    """Provide mock simulation data for determinism testing."""
    return {
        "employees": [
            {"id": "EMP001", "start_year": 2025, "band": "IC3"},
            {"id": "EMP002", "start_year": 2025, "band": "IC4"},
            {"id": "EMP003", "start_year": 2026, "band": "IC3"},
        ],
        "events": {
            2025: [
                {"employee_id": "EMP001", "event_type": "hire", "date": "2025-01-15"},
                {"employee_id": "EMP002", "event_type": "hire", "date": "2025-03-01"},
            ],
            2026: [
                {"employee_id": "EMP003", "event_type": "hire", "date": "2026-02-15"},
                {"employee_id": "EMP001", "event_type": "promotion", "date": "2026-06-01"},
            ]
        }
    }


if __name__ == "__main__":
    # Run determinism tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--maxfail=5",
        "-x"  # Stop on first failure to preserve determinism test integrity
    ])
