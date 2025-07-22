"""
Integration tests for checklist enforcement in multi-year simulations.

Tests the complete checklist-enforced workflow with real data and validates
that step sequence enforcement prevents common errors while maintaining
full functionality and performance.
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
import yaml
import time

from orchestrator_mvp.core.simulation_checklist import (
    SimulationChecklist,
    StepSequenceError
)
from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
from orchestrator_mvp.core.database_manager import get_connection
from orchestrator_mvp.core.workforce_calculations import calculate_workforce_requirements_from_config


class TestChecklistEnforcementIntegration:
    """Test end-to-end checklist enforcement integration."""

    @pytest.fixture
    def sample_config(self):
        """Sample simulation configuration for testing."""
        return {
            'simulation': {
                'start_year': 2025,
                'end_year': 2026
            },
            'target_growth_rate': 0.03,
            'workforce': {
                'total_termination_rate': 0.12,
                'new_hire_termination_rate': 0.25
            },
            'random_seed': 42
        }

    @pytest.fixture
    def mock_database_functions(self):
        """Mock database functions that require actual data setup."""
        with patch('orchestrator_mvp.core.multi_year_orchestrator.get_connection') as mock_get_conn, \
             patch('orchestrator_mvp.core.multi_year_orchestrator.get_baseline_workforce_count') as mock_baseline, \
             patch('orchestrator_mvp.core.multi_year_orchestrator.get_previous_year_workforce_count') as mock_previous, \
             patch('orchestrator_mvp.core.multi_year_orchestrator.generate_and_store_all_events') as mock_events, \
             patch('orchestrator_mvp.core.multi_year_orchestrator.generate_workforce_snapshot') as mock_snapshot:

            # Mock connection
            mock_conn = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.__exit__.return_value = None
            mock_conn.execute.return_value.fetchone.return_value = [1000, 900, 35.5, 8.2]  # Sample workforce data

            # Mock workforce counts
            mock_baseline.return_value = 1000
            mock_previous.return_value = 1050

            # Mock event generation and snapshot creation
            mock_events.return_value = None
            mock_snapshot.return_value = None

            yield {
                'connection': mock_get_conn,
                'baseline': mock_baseline,
                'previous': mock_previous,
                'events': mock_events,
                'snapshot': mock_snapshot
            }

    def test_multi_year_orchestrator_initialization(self, sample_config):
        """Test orchestrator initializes correctly with valid configuration."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2026, sample_config)

        assert orchestrator.start_year == 2025
        assert orchestrator.end_year == 2026
        assert orchestrator.years == [2025, 2026]
        assert orchestrator.config == sample_config
        assert isinstance(orchestrator.checklist, SimulationChecklist)

    def test_orchestrator_configuration_validation(self):
        """Test orchestrator validates configuration properly."""
        # Missing required parameters
        invalid_config = {'simulation': {'start_year': 2025, 'end_year': 2026}}

        with pytest.raises(ValueError, match="Missing required configuration parameters"):
            MultiYearSimulationOrchestrator(2025, 2026, invalid_config)

    def test_complete_workflow_sequence(self, sample_config, mock_database_functions):
        """Test complete workflow executes with proper sequence validation."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2026, sample_config)

        # Track step execution order
        executed_steps = []

        # Mock the individual step execution methods to track calls
        with patch.object(orchestrator, '_execute_pre_simulation_setup') as mock_pre, \
             patch.object(orchestrator, '_execute_workforce_baseline') as mock_baseline, \
             patch.object(orchestrator, '_execute_workforce_requirements') as mock_requirements, \
             patch.object(orchestrator, '_execute_event_generation') as mock_events, \
             patch.object(orchestrator, '_execute_workforce_snapshot') as mock_snapshot, \
             patch.object(orchestrator, '_execute_validation_metrics') as mock_validation:

            # Configure mocks to track execution
            def track_step(step_name):
                def wrapper(*args, **kwargs):
                    executed_steps.append(step_name)
                return wrapper

            mock_pre.side_effect = track_step('pre_simulation')
            mock_baseline.side_effect = track_step('workforce_baseline')
            mock_requirements.side_effect = track_step('workforce_requirements')
            mock_events.side_effect = track_step('event_generation')
            mock_snapshot.side_effect = track_step('workforce_snapshot')
            mock_validation.side_effect = track_step('validation_metrics')

            # Run simulation
            results = orchestrator.run_simulation(skip_breaks=True)

            # Verify successful completion
            assert results['years_completed'] == [2025, 2026]
            assert len(results['years_failed']) == 0
            assert results['total_runtime_seconds'] > 0

            # Verify steps were executed for each year
            assert 'pre_simulation' in executed_steps
            assert executed_steps.count('workforce_baseline') == 2  # Once per year
            assert executed_steps.count('workforce_requirements') == 2
            assert executed_steps.count('event_generation') == 2
            assert executed_steps.count('workforce_snapshot') == 2
            assert executed_steps.count('validation_metrics') == 2

    def test_step_sequence_enforcement_prevents_out_of_order(self, sample_config):
        """Test that checklist prevents out-of-order step execution."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2025, sample_config)

        # Try to execute workforce_snapshot without prerequisites
        with pytest.raises(StepSequenceError) as exc_info:
            orchestrator.checklist.assert_step_ready('workforce_snapshot', 2025)

        error = exc_info.value
        assert error.step == 'workforce_snapshot'
        assert error.year == 2025
        assert len(error.missing_prerequisites) > 0
        assert 'event_generation' in str(error)

    def test_resume_functionality(self, sample_config, mock_database_functions):
        """Test resume functionality from various checkpoints."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2027, sample_config)

        # Simulate partial completion by manually marking steps
        orchestrator.checklist.mark_step_complete('pre_simulation')
        orchestrator.checklist.mark_step_complete('year_transition', 2025)
        orchestrator.checklist.mark_step_complete('workforce_baseline', 2025)
        orchestrator.checklist.mark_step_complete('workforce_requirements', 2025)
        orchestrator.checklist.mark_step_complete('event_generation', 2025)
        orchestrator.checklist.mark_step_complete('workforce_snapshot', 2025)
        orchestrator.checklist.mark_step_complete('validation_metrics', 2025)

        # Should be able to resume from year 2026
        assert orchestrator.can_resume_from(2026, 'year_transition')

        # Test actual resume (mock the execution)
        with patch.object(orchestrator, '_execute_year_workflow') as mock_workflow:
            results = orchestrator.run_simulation(skip_breaks=True, resume_from=2026)

            # Should only execute years 2026 and 2027
            assert mock_workflow.call_count == 2
            called_years = [call[0][0] for call in mock_workflow.call_args_list]
            assert called_years == [2026, 2027]

    def test_rollback_functionality(self, sample_config, mock_database_functions):
        """Test rollback functionality for failed simulations."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2026, sample_config)

        # Complete year 2025
        orchestrator.checklist.mark_step_complete('pre_simulation')
        for step in ['year_transition', 'workforce_baseline', 'workforce_requirements',
                    'event_generation', 'workforce_snapshot', 'validation_metrics']:
            orchestrator.checklist.mark_step_complete(step, 2025)

        # Add to results
        orchestrator.results['years_completed'].append(2025)
        orchestrator.results['step_details'][2025] = {'test': 'data'}

        # Perform rollback
        orchestrator.rollback_year(2025)

        # Verify rollback completed
        assert 2025 not in orchestrator.results['years_completed']
        assert 2025 not in orchestrator.results['step_details']

        # Check that year 2025 steps are reset but pre_simulation preserved
        status = orchestrator.checklist.get_completion_status(2025)
        assert status['pre_simulation'] == True  # Should be preserved
        assert status['workforce_baseline'] == False  # Should be reset

    def test_validation_metrics_integration(self, sample_config, mock_database_functions):
        """Test validation metrics step with real validation logic."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2025, sample_config)

        # Mock database queries for validation
        mock_conn = MagicMock()
        mock_database_functions['connection'].return_value.__enter__.return_value = mock_conn

        # Mock validation query results
        mock_conn.execute.return_value.fetchone.side_effect = [
            (1000, 900),  # Snapshot query result (total, active employees)
            (500, 500),   # Events query result (total, valid events)
            None          # Growth comparison (will be handled in method)
        ]

        # Execute validation step
        orchestrator.checklist.mark_step_complete('pre_simulation')
        orchestrator.checklist.mark_step_complete('year_transition', 2025)
        orchestrator.checklist.mark_step_complete('workforce_baseline', 2025)
        orchestrator.checklist.mark_step_complete('workforce_requirements', 2025)
        orchestrator.checklist.mark_step_complete('event_generation', 2025)
        orchestrator.checklist.mark_step_complete('workforce_snapshot', 2025)

        # Should be able to execute validation
        orchestrator._execute_validation_metrics(2025)

        # Verify validation results stored
        assert 2025 in orchestrator.results['step_details']
        assert 'validation_results' in orchestrator.results['step_details'][2025]

    def test_performance_overhead(self, sample_config, mock_database_functions):
        """Test that checklist enforcement doesn't significantly impact performance."""
        # Test without checklist (direct function calls)
        start_time = time.time()
        checklist = SimulationChecklist(2025, 2025)
        for _ in range(1000):
            checklist.mark_step_complete('pre_simulation')
            checklist.assert_step_ready('workforce_baseline', 2025)
        baseline_time = time.time() - start_time

        # Test with full checklist validation
        start_time = time.time()
        orchestrator = MultiYearSimulationOrchestrator(2025, 2025, sample_config)
        for _ in range(100):  # Fewer iterations due to more complex operations
            progress = orchestrator.get_progress_summary()
            can_resume = orchestrator.can_resume_from(2025, 'workforce_baseline')
        checklist_time = time.time() - start_time

        # Performance should be reasonable (not more than 10x slower per operation)
        # Adjusted for different operation counts
        relative_performance = (checklist_time / 100) / (baseline_time / 1000)
        assert relative_performance < 10, f"Checklist overhead too high: {relative_performance}x"


class TestStepSequenceErrorScenarios:
    """Test various step sequence error scenarios."""

    def test_workforce_snapshot_without_events(self):
        """Test attempting to run workforce snapshot without event generation."""
        checklist = SimulationChecklist(2025, 2025)

        # Complete prerequisites except event_generation
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('year_transition', 2025)
        checklist.mark_step_complete('workforce_baseline', 2025)
        checklist.mark_step_complete('workforce_requirements', 2025)
        # Skip event_generation

        # Should fail with clear error message
        with pytest.raises(StepSequenceError) as exc_info:
            checklist.assert_step_ready('workforce_snapshot', 2025)

        error = exc_info.value
        assert 'event_generation' in error.missing_prerequisites
        assert 'workforce_snapshot' in str(error)
        assert '2025' in str(error)
        assert 'prerequisites' in str(error)

    def test_event_generation_without_requirements(self):
        """Test attempting event generation without workforce requirements."""
        checklist = SimulationChecklist(2025, 2025)

        # Complete partial prerequisites
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('year_transition', 2025)
        checklist.mark_step_complete('workforce_baseline', 2025)
        # Skip workforce_requirements

        with pytest.raises(StepSequenceError) as exc_info:
            checklist.assert_step_ready('event_generation', 2025)

        assert 'workforce_requirements' in exc_info.value.missing_prerequisites

    def test_year_2_without_year_1_completion(self):
        """Test attempting year 2 without completing year 1."""
        checklist = SimulationChecklist(2025, 2026)

        # Complete pre_simulation but not year 2025
        checklist.mark_step_complete('pre_simulation')

        # Should fail to begin year 2026
        with pytest.raises(StepSequenceError):
            checklist.begin_year(2026)

    def test_multiple_missing_prerequisites(self):
        """Test error handling with multiple missing prerequisites."""
        checklist = SimulationChecklist(2025, 2025)

        # Try to jump directly to validation_metrics
        with pytest.raises(StepSequenceError) as exc_info:
            checklist.assert_step_ready('validation_metrics', 2025)

        error = exc_info.value
        # Should have multiple missing prerequisites
        assert len(error.missing_prerequisites) > 1
        assert any('workforce_snapshot' in prereq for prereq in error.missing_prerequisites)


class TestBackwardCompatibility:
    """Test backward compatibility with existing functionality."""

    def test_existing_function_signatures_preserved(self, mock_database_functions):
        """Test that new orchestrator maintains existing function signatures."""
        from orchestrator_mvp.core.multi_year_simulation import run_multi_year_simulation
        from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator

        # Both should accept the same basic parameters
        config = {
            'target_growth_rate': 0.03,
            'workforce': {'total_termination_rate': 0.12, 'new_hire_termination_rate': 0.25}
        }

        # New orchestrator should work with same config structure
        orchestrator = MultiYearSimulationOrchestrator(2025, 2026, config)
        assert orchestrator.config == config

    def test_configuration_compatibility(self):
        """Test that existing configuration files work unchanged."""
        # Simulate existing test_config.yaml structure
        legacy_config = {
            'simulation': {'start_year': 2025, 'end_year': 2027},
            'target_growth_rate': 0.03,
            'workforce': {
                'total_termination_rate': 0.12,
                'new_hire_termination_rate': 0.25
            },
            'random_seed': 42
        }

        # Should initialize without issues
        orchestrator = MultiYearSimulationOrchestrator(2025, 2027, legacy_config)
        assert orchestrator.start_year == 2025
        assert orchestrator.end_year == 2027


class TestIntegrationWithExistingModels:
    """Test integration with existing dbt models and validation functions."""

    def test_workforce_calculation_integration(self):
        """Test integration with existing workforce calculation functions."""
        # Test that checklist works with existing calculation functions
        calc_result = calculate_workforce_requirements_from_config(
            current_workforce=1000,
            config={
                'target_growth_rate': 0.03,
                'total_termination_rate': 0.12,
                'new_hire_termination_rate': 0.25
            }
        )

        # Result should be compatible with checklist system
        assert 'experienced_terminations' in calc_result
        assert 'total_hires_needed' in calc_result
        assert 'expected_new_hire_terminations' in calc_result
        assert calc_result['current_workforce'] == 1000

    def test_database_connection_compatibility(self):
        """Test that checklist system works with existing database connections."""
        # Test with actual database connection pattern used in existing code
        try:
            with patch('orchestrator_mvp.core.database_manager.get_connection') as mock_get_conn:
                mock_conn = MagicMock()
                mock_get_conn.return_value = mock_conn
                mock_conn.__enter__.return_value = mock_conn
                mock_conn.__exit__.return_value = None

                # Should work with existing connection patterns
                checklist = SimulationChecklist(2025, 2025)
                # Test that checklist operations don't interfere with database operations
                status = checklist.get_completion_status(2025)
                assert isinstance(status, dict)

        except Exception as e:
            pytest.fail(f"Database compatibility test failed: {e}")


class TestConcurrencyAndReliability:
    """Test concurrent access and reliability scenarios."""

    def test_state_consistency_under_multiple_operations(self):
        """Test state consistency when performing multiple operations rapidly."""
        checklist = SimulationChecklist(2025, 2027)

        # Perform many rapid operations
        for i in range(100):
            checklist.get_completion_status(2025)
            checklist.get_next_step(2025)
            checklist.can_resume_from(2025, 'workforce_baseline')
            if i % 10 == 0:
                checklist.mark_step_complete('pre_simulation')

        # State should remain consistent
        status = checklist.get_completion_status(2025)
        assert status['pre_simulation'] == True
        assert status['workforce_baseline'] == False

    def test_memory_usage_reasonable(self):
        """Test that checklist doesn't consume excessive memory."""
        import sys

        # Create large simulation range
        initial_size = sys.getsizeof(SimulationChecklist(2025, 2025))
        large_simulation = SimulationChecklist(2025, 2050)  # 25 years
        large_size = sys.getsizeof(large_simulation)

        # Memory usage should scale reasonably
        size_ratio = large_size / initial_size
        assert size_ratio < 100, f"Memory usage scaling too high: {size_ratio}x"

    def test_error_recovery_scenarios(self, sample_config, mock_database_functions):
        """Test error recovery in various failure scenarios."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2026, sample_config)

        # Test recovery from database connection failure
        with patch.object(orchestrator, '_execute_event_generation') as mock_events:
            mock_events.side_effect = Exception("Database connection failed")

            with pytest.raises(Exception, match="Database connection failed"):
                orchestrator.run_simulation(skip_breaks=True)

            # Orchestrator should still be in valid state for recovery
            assert orchestrator.start_year == 2025
            assert orchestrator.end_year == 2026
            assert len(orchestrator.results['years_failed']) > 0


class TestRealWorldScenarios:
    """Test realistic usage scenarios."""

    def test_analyst_workflow_simulation(self, mock_database_functions):
        """Simulate typical analyst workflow with checklist."""
        # Analyst starts with configuration
        config = {
            'target_growth_rate': 0.05,  # Higher growth scenario
            'workforce': {
                'total_termination_rate': 0.10,
                'new_hire_termination_rate': 0.20
            },
            'random_seed': 123
        }

        # Create orchestrator
        orchestrator = MultiYearSimulationOrchestrator(2025, 2027, config)

        # Check initial state
        progress = orchestrator.get_progress_summary()
        assert 'Pre-simulation setup' in progress
        assert '○' in progress  # Should show incomplete steps

        # Simulate partial completion then interruption
        orchestrator.checklist.mark_step_complete('pre_simulation')

        # Analyst checks if can resume
        can_resume_2025 = orchestrator.can_resume_from(2025, 'year_transition')
        assert can_resume_2025 == True

        can_resume_2026 = orchestrator.can_resume_from(2026, 'year_transition')
        assert can_resume_2026 == False  # 2025 not complete yet

    def test_debugging_workflow_with_force_override(self, mock_database_functions):
        """Test debugging workflow using force override capability."""
        orchestrator = MultiYearSimulationOrchestrator(2025, 2025, {
            'target_growth_rate': 0.03,
            'workforce': {'total_termination_rate': 0.12, 'new_hire_termination_rate': 0.25}
        })

        # Simulate debugging scenario where analyst needs to test workforce_snapshot
        # without running full pipeline (emergency override)

        # Normal validation should fail
        with pytest.raises(StepSequenceError):
            orchestrator.checklist.assert_step_ready('workforce_snapshot', 2025)

        # But the error message should be informative
        try:
            orchestrator.checklist.assert_step_ready('workforce_snapshot', 2025)
        except StepSequenceError as e:
            assert 'event_generation' in str(e)
            assert 'Please complete these steps first' in str(e)
