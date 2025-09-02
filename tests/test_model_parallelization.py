#!/usr/bin/env python3
"""
Comprehensive tests for Story S067-02: Model-Level Parallelization

Tests the sophisticated model-level parallelization system including:
- Model classification accuracy
- Dependency analysis correctness
- Parallel execution safety
- Thread pool management
- Resource monitoring
- Deterministic results
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Set

# Import the components we're testing
from navigator_orchestrator.model_execution_types import (
    ModelClassifier, ModelExecutionType, ModelClassification
)
from navigator_orchestrator.model_dependency_analyzer import (
    ModelDependencyAnalyzer, DependencyGraph, ParallelizationOpportunity
)
from navigator_orchestrator.parallel_execution_engine import (
    ParallelExecutionEngine, ExecutionContext, ExecutionResult
)
from navigator_orchestrator.dbt_runner import DbtRunner, DbtResult


class TestModelClassifier:
    """Test the model classification system."""

    def setup_method(self):
        self.classifier = ModelClassifier()

    def test_parallel_safe_classification(self):
        """Test that parallel-safe models are classified correctly."""

        # Test hazard calculation models
        hazard_model = self.classifier.classify_model("int_hazard_termination")
        assert hazard_model.execution_type == ModelExecutionType.PARALLEL_SAFE
        assert "hazard_calculation" in hazard_model.tags
        assert hazard_model.threads_safe == True
        assert hazard_model.parallel_group == "hazard_calculations"

        # Test staging models
        staging_model = self.classifier.classify_model("stg_census_data")
        assert staging_model.execution_type == ModelExecutionType.PARALLEL_SAFE
        assert "staging" in staging_model.tags

        # Test independent business logic
        params_model = self.classifier.classify_model("int_effective_parameters")
        assert params_model.execution_type == ModelExecutionType.PARALLEL_SAFE
        assert "independent_logic" in params_model.tags

    def test_sequential_classification(self):
        """Test that sequential models are classified correctly."""

        # Test state accumulator models
        accumulator_model = self.classifier.classify_model("int_enrollment_state_accumulator")
        assert accumulator_model.execution_type == ModelExecutionType.SEQUENTIAL
        assert "state_accumulator" in accumulator_model.tags
        assert accumulator_model.threads_safe == False

        # Test fact tables that depend on ordering
        facts_model = self.classifier.classify_model("fct_yearly_events")
        assert facts_model.execution_type == ModelExecutionType.SEQUENTIAL
        assert "sequential_required" in facts_model.tags

    def test_conditional_classification(self):
        """Test that conditional models are classified correctly."""

        # Test event generation models
        events_model = self.classifier.classify_model("int_termination_events")
        assert events_model.execution_type == ModelExecutionType.CONDITIONAL
        assert "event_generation" in events_model.tags

        # Test complex contribution models
        contrib_model = self.classifier.classify_model("int_employee_contributions")
        assert contrib_model.execution_type == ModelExecutionType.CONDITIONAL

    def test_unknown_model_classification(self):
        """Test classification of unknown models."""

        unknown_model = self.classifier.classify_model("unknown_test_model")
        assert unknown_model.execution_type == ModelExecutionType.CONDITIONAL
        assert "unknown" in unknown_model.tags
        assert "conservative classification" in unknown_model.reason

    def test_parallel_groups(self):
        """Test parallel group functionality."""

        models = [
            "int_hazard_termination",
            "int_hazard_promotion",
            "int_hazard_merit",
            "stg_census_data",
            "stg_comp_levers"
        ]

        groups = self.classifier.get_parallel_groups(models)

        # Should have hazard_calculations and staging groups
        assert "hazard_calculations" in groups
        assert "staging" in groups

        # Check group contents
        hazard_group = groups["hazard_calculations"]
        assert len(hazard_group) == 3
        assert all("hazard" in model for model in hazard_group)

        staging_group = groups["staging"]
        assert len(staging_group) == 2
        assert all(model.startswith("stg_") for model in staging_group)

    def test_can_run_in_parallel(self):
        """Test parallel compatibility checking."""

        # Two parallel-safe models should be compatible
        assert self.classifier.can_run_in_parallel(
            "int_hazard_termination", "int_hazard_promotion"
        ) == True

        # Sequential model cannot run with anything
        assert self.classifier.can_run_in_parallel(
            "int_enrollment_state_accumulator", "int_hazard_termination"
        ) == False

        # Conditional models should be conservative
        assert self.classifier.can_run_in_parallel(
            "int_termination_events", "int_hiring_events"
        ) == False


class TestDependencyGraph:
    """Test the dependency graph data structure."""

    def setup_method(self):
        self.graph = DependencyGraph()

    def test_add_dependency(self):
        """Test adding dependencies to the graph."""

        self.graph.add_dependency("model_a", "model_b")
        self.graph.add_dependency("model_a", "model_c")

        deps = self.graph.get_dependencies("model_a")
        assert deps == {"model_b", "model_c"}

        dependents = self.graph.get_dependents("model_b")
        assert dependents == {"model_a"}

    def test_transitive_dependencies(self):
        """Test transitive dependency calculation."""

        # Create chain: A -> B -> C -> D
        self.graph.add_dependency("model_a", "model_b")
        self.graph.add_dependency("model_b", "model_c")
        self.graph.add_dependency("model_c", "model_d")

        transitive = self.graph.get_transitive_dependencies("model_a")
        assert transitive == {"model_b", "model_c", "model_d"}

    def test_topological_sort(self):
        """Test topological sorting of models."""

        # Create DAG: D <- C <- A, B -> C
        self.graph.add_dependency("model_a", "model_c")
        self.graph.add_dependency("model_b", "model_c")
        self.graph.add_dependency("model_c", "model_d")

        models = ["model_a", "model_b", "model_c", "model_d"]
        sorted_models = self.graph.topological_sort(models)

        # D should come first, C before A and B
        assert sorted_models.index("model_d") < sorted_models.index("model_c")
        assert sorted_models.index("model_c") < sorted_models.index("model_a")
        assert sorted_models.index("model_c") < sorted_models.index("model_b")

    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies."""

        # Create circular dependency: A -> B -> A
        self.graph.add_dependency("model_a", "model_b")
        self.graph.add_dependency("model_b", "model_a")

        models = ["model_a", "model_b"]

        with pytest.raises(ValueError, match="Circular dependency detected"):
            self.graph.topological_sort(models)


class TestModelDependencyAnalyzer:
    """Test the dependency analysis system."""

    def setup_method(self):
        # Create temporary dbt project directory
        self.temp_dir = tempfile.mkdtemp()
        self.dbt_dir = Path(self.temp_dir) / "dbt"
        self.dbt_dir.mkdir(parents=True)

        # Create mock manifest.json
        self.create_mock_manifest()

        self.analyzer = ModelDependencyAnalyzer(self.dbt_dir)

    def create_mock_manifest(self):
        """Create a mock dbt manifest for testing."""

        manifest = {
            "nodes": {
                "model.test.int_hazard_termination": {
                    "name": "int_hazard_termination",
                    "depends_on": {
                        "nodes": ["model.test.stg_config_termination_hazard_base"]
                    }
                },
                "model.test.stg_config_termination_hazard_base": {
                    "name": "stg_config_termination_hazard_base",
                    "depends_on": {"nodes": []}
                },
                "model.test.int_enrollment_state_accumulator": {
                    "name": "int_enrollment_state_accumulator",
                    "depends_on": {
                        "nodes": ["model.test.fct_yearly_events"]
                    }
                },
                "model.test.fct_yearly_events": {
                    "name": "fct_yearly_events",
                    "depends_on": {
                        "nodes": ["model.test.int_termination_events"]
                    }
                },
                "model.test.int_termination_events": {
                    "name": "int_termination_events",
                    "depends_on": {
                        "nodes": ["model.test.int_hazard_termination"]
                    }
                }
            }
        }

        target_dir = self.dbt_dir / "target"
        target_dir.mkdir(exist_ok=True)

        with open(target_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

    def test_analyze_dependencies(self):
        """Test dependency analysis from manifest."""

        with patch.object(self.analyzer, '_load_dbt_manifest'):
            self.analyzer._manifest_cache = self.get_mock_manifest()
            dependency_graph = self.analyzer.analyze_dependencies()

            # Check that dependencies are loaded correctly
            hazard_deps = dependency_graph.get_dependencies("int_hazard_termination")
            assert "stg_config_termination_hazard_base" in hazard_deps

            events_deps = dependency_graph.get_dependencies("fct_yearly_events")
            assert "int_termination_events" in events_deps

    def get_mock_manifest(self):
        """Get mock manifest data."""
        return {
            "nodes": {
                "model.test.int_hazard_termination": {
                    "name": "int_hazard_termination",
                    "depends_on": {
                        "nodes": ["model.test.stg_config_termination_hazard_base"]
                    }
                },
                "model.test.stg_config_termination_hazard_base": {
                    "name": "stg_config_termination_hazard_base",
                    "depends_on": {"nodes": []}
                }
            }
        }

    def test_identify_parallelization_opportunities(self):
        """Test identification of parallelization opportunities."""

        with patch.object(self.analyzer, 'analyze_dependencies'):
            # Mock dependency graph
            self.analyzer.dependency_graph = DependencyGraph()

            stage_models = [
                "int_hazard_termination",
                "int_hazard_promotion",
                "int_hazard_merit",
                "stg_census_data"
            ]

            opportunities = self.analyzer.identify_parallelization_opportunities(
                stage_models, max_parallelism=4
            )

            # Should find opportunities for hazard calculations
            assert len(opportunities) > 0
            hazard_opportunity = next(
                (op for op in opportunities if op.execution_group == "hazard_calculations"),
                None
            )
            assert hazard_opportunity is not None
            assert len(hazard_opportunity.parallel_models) >= 2

    def test_execution_plan_creation(self):
        """Test execution plan creation."""

        with patch.object(self.analyzer, 'analyze_dependencies'):
            self.analyzer.dependency_graph = DependencyGraph()

            stage_models = [
                "int_hazard_termination",
                "int_enrollment_state_accumulator",
                "stg_census_data"
            ]

            plan = self.analyzer.create_execution_plan(stage_models, max_parallelism=2)

            # Should have both parallel and sequential phases
            assert "execution_phases" in plan
            phases = plan["execution_phases"]

            # Check that we have appropriate phases
            phase_types = [phase["type"] for phase in phases]
            assert "parallel" in phase_types or "sequential" in phase_types

    def test_execution_safety_validation(self):
        """Test execution safety validation."""

        with patch.object(self.analyzer, 'analyze_dependencies'):
            self.analyzer.dependency_graph = DependencyGraph()

            # Test safe parallel models
            safe_models = ["int_hazard_termination", "int_hazard_promotion"]
            safety = self.analyzer.validate_execution_safety(safe_models)

            assert safety["safe"] == True
            assert len(safety["issues"]) == 0

            # Test unsafe combination (add dependency)
            self.analyzer.dependency_graph.add_dependency("int_hazard_promotion", "int_hazard_termination")

            unsafe_safety = self.analyzer.validate_execution_safety(safe_models)
            assert unsafe_safety["safe"] == False
            assert len(unsafe_safety["issues"]) > 0


class TestParallelExecutionEngine:
    """Test the parallel execution engine."""

    def setup_method(self):
        # Mock components
        self.mock_dbt_runner = Mock(spec=DbtRunner)
        self.mock_dependency_analyzer = Mock(spec=ModelDependencyAnalyzer)

        # Create engine
        self.engine = ParallelExecutionEngine(
            dbt_runner=self.mock_dbt_runner,
            dependency_analyzer=self.mock_dependency_analyzer,
            max_workers=2,
            resource_monitoring=False,  # Disable for testing
            verbose=False
        )

    def test_sequential_fallback(self):
        """Test fallback to sequential execution."""

        models = ["model_a", "model_b"]
        context = ExecutionContext(
            simulation_year=2025,
            dbt_vars={},
            stage_name="test",
            execution_id="test123"
        )

        # Mock successful execution
        mock_result = DbtResult(
            success=True,
            stdout="Success",
            stderr="",
            execution_time=1.0,
            return_code=0,
            command=["run", "--select", "model_a"]
        )

        self.mock_dbt_runner.execute_command.return_value = mock_result

        result = self.engine._execute_sequential_fallback(models, context)

        assert result.success == True
        assert len(result.model_results) == 2
        assert result.parallelism_achieved == 1

    def test_parallel_phase_execution(self):
        """Test parallel phase execution."""

        phase = {
            "type": "parallel",
            "models": ["int_hazard_termination", "int_hazard_promotion"],
            "group": "hazard_calculations",
            "estimated_speedup": 2.0,
            "safety_level": "high"
        }

        context = ExecutionContext(
            simulation_year=2025,
            dbt_vars={},
            stage_name="test",
            execution_id="test123"
        )

        # Mock validation to pass
        self.mock_dependency_analyzer.validate_execution_safety.return_value = {
            "safe": True,
            "issues": [],
            "warnings": []
        }

        # Mock successful dbt execution
        mock_result = DbtResult(
            success=True,
            stdout="Success",
            stderr="",
            execution_time=1.0,
            return_code=0,
            command=["run"]
        )
        self.mock_dbt_runner.execute_command.return_value = mock_result

        result = self.engine._execute_parallel_phase(phase, context)

        assert result.success == True
        assert len(result.model_results) == 2
        assert result.parallelism_achieved == 2

    def test_resource_monitoring(self):
        """Test resource monitoring during execution."""

        # Enable resource monitoring
        engine_with_monitoring = ParallelExecutionEngine(
            dbt_runner=self.mock_dbt_runner,
            dependency_analyzer=self.mock_dependency_analyzer,
            max_workers=2,
            resource_monitoring=True,
            memory_limit_mb=1000.0,  # Low limit to trigger pressure
            verbose=False
        )

        # Mock high memory usage
        with patch('psutil.virtual_memory') as mock_memory:
            mock_memory.return_value.used = 2000 * 1024 * 1024  # 2GB in bytes

            resources = engine_with_monitoring.resource_monitor.check_resources()
            assert resources["memory_pressure"] == True

    def test_deterministic_execution(self):
        """Test that deterministic execution produces consistent ordering."""

        # Create engine with deterministic execution enabled
        engine = ParallelExecutionEngine(
            dbt_runner=self.mock_dbt_runner,
            dependency_analyzer=self.mock_dependency_analyzer,
            max_workers=2,
            deterministic_execution=True,
            resource_monitoring=False,
            verbose=False
        )

        models = ["model_z", "model_a", "model_b"]

        # Mock validation
        self.mock_dependency_analyzer.validate_execution_safety.return_value = {
            "safe": True, "issues": [], "warnings": []
        }

        # Mock successful execution
        mock_result = DbtResult(
            success=True, stdout="", stderr="", execution_time=1.0,
            return_code=0, command=[]
        )
        self.mock_dbt_runner.execute_command.return_value = mock_result

        phase = {
            "type": "parallel",
            "models": models,
            "group": "test",
            "estimated_speedup": 1.5,
            "safety_level": "high"
        }

        context = ExecutionContext(2025, {}, "test", "test123")
        result = engine._execute_parallel_phase(phase, context)

        # Models should be sorted for deterministic execution
        called_models = [
            call[0][1] for call in self.mock_dbt_runner.execute_command.call_args_list
        ]
        assert called_models == sorted(models)

    def test_parallelization_statistics(self):
        """Test parallelization statistics generation."""

        # Mock dependency graph with known models
        mock_graph = Mock()
        mock_graph.nodes = {
            "int_hazard_termination": set(),
            "int_enrollment_state_accumulator": set(),
            "int_employee_contributions": set()
        }

        self.mock_dependency_analyzer.dependency_graph = mock_graph

        stats = self.engine.get_parallelization_statistics()

        assert "total_models" in stats
        assert "parallel_safe" in stats
        assert "sequential_required" in stats
        assert "conditional" in stats
        assert "parallelization_ratio" in stats
        assert "max_theoretical_speedup" in stats

    def test_stage_validation(self):
        """Test stage-level parallelization validation."""

        stage_models = ["int_hazard_termination", "int_hazard_promotion"]

        # Mock opportunities
        mock_opportunity = ParallelizationOpportunity(
            parallel_models=stage_models,
            execution_group="hazard_calculations",
            estimated_speedup=2.0,
            resource_requirements={"memory_mb": 512, "cpu_threads": 2},
            safety_level="high"
        )

        self.mock_dependency_analyzer.identify_parallelization_opportunities.return_value = [
            mock_opportunity
        ]

        validation = self.engine.validate_stage_parallelization(stage_models)

        assert validation["stage_models"] == 2
        assert validation["parallelizable_models"] == 2
        assert validation["estimated_speedup"] == 2.0
        assert "high" in validation["safety_breakdown"]


class TestIntegration:
    """Integration tests for the complete parallelization system."""

    def test_end_to_end_classification_and_execution(self):
        """Test full workflow from classification to execution."""

        # This would be a more comprehensive test that exercises
        # the entire pipeline, but requires actual dbt environment
        # For now, we test the component integration

        classifier = ModelClassifier()

        # Test that classifications are consistent
        hazard_model = classifier.classify_model("int_hazard_termination")
        assert hazard_model.execution_type == ModelExecutionType.PARALLEL_SAFE

        # Test that parallel groups work
        models = ["int_hazard_termination", "int_hazard_promotion"]
        groups = classifier.get_parallel_groups(models)
        assert "hazard_calculations" in groups

        # Test compatibility checking
        compatible = classifier.can_run_in_parallel(
            "int_hazard_termination", "int_hazard_promotion"
        )
        assert compatible == True


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_missing_dependencies_handling(self):
        """Test handling when parallelization components are missing."""

        # Mock missing components
        with patch('navigator_orchestrator.dbt_runner.PARALLEL_EXECUTION_AVAILABLE', False):
            from navigator_orchestrator.dbt_runner import DbtRunner

            runner = DbtRunner(
                enable_model_parallelization=True,
                verbose=False
            )

            # Should gracefully fall back to sequential execution
            info = runner.get_parallelization_info()
            assert info["available"] == False
            assert "not initialized" in info["reason"]

    def test_configuration_validation(self):
        """Test configuration validation and error handling."""

        # Test invalid worker count
        with pytest.raises(ValueError):
            ParallelExecutionEngine(
                dbt_runner=Mock(),
                dependency_analyzer=Mock(),
                max_workers=0,  # Invalid
                verbose=False
            )

    def test_execution_failure_handling(self):
        """Test handling of execution failures."""

        mock_dbt_runner = Mock(spec=DbtRunner)
        mock_dependency_analyzer = Mock(spec=ModelDependencyAnalyzer)

        engine = ParallelExecutionEngine(
            dbt_runner=mock_dbt_runner,
            dependency_analyzer=mock_dependency_analyzer,
            max_workers=2,
            resource_monitoring=False,
            verbose=False
        )

        # Mock failed execution
        mock_result = DbtResult(
            success=False,
            stdout="",
            stderr="Error occurred",
            execution_time=1.0,
            return_code=1,
            command=["run", "--select", "model_a"]
        )

        mock_dbt_runner.execute_command.return_value = mock_result

        models = ["model_a"]
        context = ExecutionContext(2025, {}, "test", "test123")

        result = engine._execute_sequential_fallback(models, context)

        assert result.success == False
        assert len(result.errors) > 0


# Test configuration and fixtures
@pytest.fixture
def sample_models():
    """Sample models for testing."""
    return [
        "int_hazard_termination",
        "int_hazard_promotion",
        "int_enrollment_state_accumulator",
        "stg_census_data",
        "int_employee_contributions",
        "fct_yearly_events"
    ]


@pytest.fixture
def mock_dbt_runner():
    """Mock DbtRunner for testing."""
    runner = Mock(spec=DbtRunner)
    runner.execute_command.return_value = DbtResult(
        success=True,
        stdout="Success",
        stderr="",
        execution_time=1.0,
        return_code=0,
        command=["run"]
    )
    return runner


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
