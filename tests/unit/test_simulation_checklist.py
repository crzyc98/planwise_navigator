"""
Unit tests for the SimulationChecklist class.

Tests step sequencing enforcement, state management, and error handling
to ensure proper workflow validation for multi-year simulations.
"""

import pytest
from datetime import datetime

from orchestrator_mvp.core.simulation_checklist import (
    SimulationChecklist,
    StepSequenceError,
    SimulationStep,
    StepStatus
)


class TestSimulationChecklistInitialization:
    """Test checklist initialization and basic functionality."""

    def test_init_single_year(self):
        """Test initialization for single year simulation."""
        checklist = SimulationChecklist(2025, 2025)

        assert checklist.start_year == 2025
        assert checklist.end_year == 2025
        assert checklist.years == [2025]

        # Check that all steps are initialized as incomplete
        status = checklist.get_completion_status(2025)
        assert status['pre_simulation'] == False
        assert status['year_transition'] == False
        assert status['workforce_baseline'] == False
        assert status['workforce_requirements'] == False
        assert status['event_generation'] == False
        assert status['workforce_snapshot'] == False
        assert status['validation_metrics'] == False

    def test_init_multi_year(self):
        """Test initialization for multi-year simulation."""
        checklist = SimulationChecklist(2025, 2029)

        assert checklist.start_year == 2025
        assert checklist.end_year == 2029
        assert checklist.years == [2025, 2026, 2027, 2028, 2029]

        # Check that pre_simulation is year-independent
        status = checklist.get_completion_status()
        assert 'pre_simulation' in status

        # Check that each year has all steps
        for year in [2025, 2026, 2027, 2028, 2029]:
            year_status = checklist.get_completion_status(year)
            assert all(step in year_status for step in [
                'pre_simulation', 'year_transition', 'workforce_baseline',
                'workforce_requirements', 'event_generation', 'workforce_snapshot',
                'validation_metrics'
            ])


class TestStepCompletion:
    """Test step completion marking and tracking."""

    def test_mark_pre_simulation_complete(self):
        """Test marking pre-simulation step as complete."""
        checklist = SimulationChecklist(2025, 2025)

        # Initially incomplete
        assert checklist.get_completion_status(2025)['pre_simulation'] == False

        # Mark complete
        checklist.mark_step_complete('pre_simulation')

        # Verify completion
        assert checklist.get_completion_status(2025)['pre_simulation'] == True

    def test_mark_year_specific_step_complete(self):
        """Test marking year-specific steps as complete."""
        checklist = SimulationChecklist(2025, 2026)

        # Mark workforce_baseline complete for year 2025
        checklist.mark_step_complete('workforce_baseline', 2025)

        # Check year 2025 status
        status_2025 = checklist.get_completion_status(2025)
        assert status_2025['workforce_baseline'] == True

        # Check year 2026 status (should still be incomplete)
        status_2026 = checklist.get_completion_status(2026)
        assert status_2026['workforce_baseline'] == False

    def test_invalid_step_name(self):
        """Test error handling for invalid step names."""
        checklist = SimulationChecklist(2025, 2025)

        with pytest.raises(ValueError, match="Unknown step"):
            checklist.mark_step_complete('invalid_step', 2025)

    def test_invalid_year(self):
        """Test error handling for invalid years."""
        checklist = SimulationChecklist(2025, 2026)

        with pytest.raises(ValueError, match="outside simulation range"):
            checklist.mark_step_complete('workforce_baseline', 2027)


class TestStepSequenceValidation:
    """Test step dependency validation and error handling."""

    def test_pre_simulation_always_ready(self):
        """Test that pre_simulation step is always ready."""
        checklist = SimulationChecklist(2025, 2025)

        # Should not raise exception
        checklist.assert_step_ready('pre_simulation')

    def test_workforce_baseline_requires_pre_simulation(self):
        """Test that workforce_baseline requires pre_simulation."""
        checklist = SimulationChecklist(2025, 2025)

        # Should raise StepSequenceError
        with pytest.raises(StepSequenceError) as exc_info:
            checklist.assert_step_ready('workforce_baseline', 2025)

        error = exc_info.value
        assert error.step == 'workforce_baseline'
        assert error.year == 2025
        assert 'pre_simulation' in error.missing_prerequisites
        assert 'pre_simulation' in str(error)

    def test_workforce_requirements_chain(self):
        """Test workforce_requirements prerequisite chain."""
        checklist = SimulationChecklist(2025, 2025)

        # Mark pre_simulation complete
        checklist.mark_step_complete('pre_simulation')

        # workforce_requirements should still fail without workforce_baseline
        with pytest.raises(StepSequenceError) as exc_info:
            checklist.assert_step_ready('workforce_requirements', 2025)

        assert 'workforce_baseline' in exc_info.value.missing_prerequisites

        # Mark workforce_baseline complete
        checklist.mark_step_complete('workforce_baseline', 2025)

        # Now workforce_requirements should be ready
        checklist.assert_step_ready('workforce_requirements', 2025)  # Should not raise

    def test_complete_step_chain(self):
        """Test completing the entire step chain."""
        checklist = SimulationChecklist(2025, 2025)

        # Complete all steps in order
        checklist.mark_step_complete('pre_simulation')
        checklist.assert_step_ready('workforce_baseline', 2025)
        checklist.mark_step_complete('workforce_baseline', 2025)

        checklist.assert_step_ready('workforce_requirements', 2025)
        checklist.mark_step_complete('workforce_requirements', 2025)

        checklist.assert_step_ready('event_generation', 2025)
        checklist.mark_step_complete('event_generation', 2025)

        checklist.assert_step_ready('workforce_snapshot', 2025)
        checklist.mark_step_complete('workforce_snapshot', 2025)

        checklist.assert_step_ready('validation_metrics', 2025)
        checklist.mark_step_complete('validation_metrics', 2025)

        # Verify all complete
        status = checklist.get_completion_status(2025)
        assert all(status.values())


class TestMultiYearValidation:
    """Test validation across multiple simulation years."""

    def test_begin_year_first_year(self):
        """Test beginning the first simulation year."""
        checklist = SimulationChecklist(2025, 2027)

        # Should not raise for first year
        checklist.begin_year(2025)

    def test_begin_year_subsequent_year_incomplete(self):
        """Test beginning subsequent year when previous year incomplete."""
        checklist = SimulationChecklist(2025, 2027)

        # Try to begin 2026 without completing 2025
        with pytest.raises(StepSequenceError):
            checklist.begin_year(2026)

    def test_begin_year_subsequent_year_complete(self):
        """Test beginning subsequent year when previous year complete."""
        checklist = SimulationChecklist(2025, 2027)

        # Complete all steps for 2025
        self._complete_year(checklist, 2025)

        # Should now be able to begin 2026
        checklist.begin_year(2026)

    def test_year_transition_validation(self):
        """Test year_transition step validation."""
        checklist = SimulationChecklist(2025, 2027)

        # Complete pre_simulation
        checklist.mark_step_complete('pre_simulation')

        # year_transition should be ready for 2025 (first year)
        checklist.assert_step_ready('year_transition', 2025)

        # But not for 2026 until 2025 is complete
        with pytest.raises(StepSequenceError):
            checklist.assert_step_ready('year_transition', 2026)

    def _complete_year(self, checklist: SimulationChecklist, year: int):
        """Helper to complete all steps for a year."""
        if not checklist._state['pre_simulation'].completed:
            checklist.mark_step_complete('pre_simulation')

        steps = ['year_transition', 'workforce_baseline', 'workforce_requirements',
                'event_generation', 'workforce_snapshot', 'validation_metrics']

        for step in steps:
            checklist.mark_step_complete(step, year)


class TestUtilityMethods:
    """Test utility methods and helper functions."""

    def test_get_next_step(self):
        """Test getting the next step to complete."""
        checklist = SimulationChecklist(2025, 2025)

        # First step should be pre_simulation
        next_step = checklist.get_next_step(2025)
        assert next_step == 'pre_simulation'

        # After completing pre_simulation
        checklist.mark_step_complete('pre_simulation')
        next_step = checklist.get_next_step(2025)
        assert next_step == 'year_transition'

        # After completing year_transition
        checklist.mark_step_complete('year_transition', 2025)
        next_step = checklist.get_next_step(2025)
        assert next_step == 'workforce_baseline'

    def test_can_resume_from(self):
        """Test resume capability checking."""
        checklist = SimulationChecklist(2025, 2025)

        # Cannot resume from workforce_requirements without prerequisites
        assert not checklist.can_resume_from(2025, 'workforce_requirements')

        # Complete prerequisites
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('year_transition', 2025)
        checklist.mark_step_complete('workforce_baseline', 2025)

        # Now can resume from workforce_requirements
        assert checklist.can_resume_from(2025, 'workforce_requirements')

    def test_reset_year(self):
        """Test resetting a year's completion state."""
        checklist = SimulationChecklist(2025, 2026)

        # Complete some steps for 2025
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('workforce_baseline', 2025)
        checklist.mark_step_complete('workforce_requirements', 2025)

        # Reset year 2025
        checklist.reset_year(2025)

        # Year 2025 steps should be reset, but pre_simulation preserved
        status = checklist.get_completion_status(2025)
        assert status['pre_simulation'] == True  # Year-independent, not reset
        assert status['workforce_baseline'] == False
        assert status['workforce_requirements'] == False

    def test_get_progress_summary(self):
        """Test progress summary generation."""
        checklist = SimulationChecklist(2025, 2026)

        # Complete some steps
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('workforce_baseline', 2025)

        summary = checklist.get_progress_summary()

        # Should contain progress indicators
        assert '✓' in summary  # Completed steps
        assert '○' in summary  # Incomplete steps
        assert 'Pre-simulation setup' in summary
        assert 'Year 2025' in summary
        assert 'Year 2026' in summary


class TestErrorHandling:
    """Test error scenarios and edge cases."""

    def test_invalid_year_range(self):
        """Test invalid year ranges."""
        with pytest.raises(ValueError):
            # End year before start year
            SimulationChecklist(2026, 2025)

    def test_assert_step_ready_invalid_step(self):
        """Test assert_step_ready with invalid step name."""
        checklist = SimulationChecklist(2025, 2025)

        with pytest.raises(ValueError, match="Unknown step"):
            checklist.assert_step_ready('invalid_step', 2025)

    def test_begin_year_invalid_year(self):
        """Test begin_year with year outside range."""
        checklist = SimulationChecklist(2025, 2027)

        with pytest.raises(ValueError, match="outside simulation range"):
            checklist.begin_year(2028)

    def test_reset_year_invalid_year(self):
        """Test reset_year with year outside range."""
        checklist = SimulationChecklist(2025, 2027)

        with pytest.raises(ValueError, match="outside simulation range"):
            checklist.reset_year(2028)

    def test_step_sequence_error_details(self):
        """Test StepSequenceError provides useful details."""
        checklist = SimulationChecklist(2025, 2025)

        try:
            checklist.assert_step_ready('workforce_snapshot', 2025)
        except StepSequenceError as e:
            assert e.step == 'workforce_snapshot'
            assert e.year == 2025
            assert len(e.missing_prerequisites) > 0
            assert 'workforce_snapshot' in str(e)
            assert '2025' in str(e)
            assert 'prerequisites' in str(e)
        else:
            pytest.fail("Expected StepSequenceError")


class TestStateManagement:
    """Test internal state management and consistency."""

    def test_state_key_generation(self):
        """Test internal state key generation."""
        checklist = SimulationChecklist(2025, 2025)

        # Pre-simulation should have simple key
        key = checklist._get_state_key('pre_simulation')
        assert key == 'pre_simulation'

        # Year-specific steps should have year prefix
        key = checklist._get_state_key('workforce_baseline', 2025)
        assert key == '2025.workforce_baseline'

    def test_state_key_year_required(self):
        """Test that year is required for year-specific steps."""
        checklist = SimulationChecklist(2025, 2025)

        with pytest.raises(ValueError, match="Year required"):
            checklist._get_state_key('workforce_baseline')

    def test_state_persistence_across_operations(self):
        """Test that state persists correctly across operations."""
        checklist = SimulationChecklist(2025, 2026)

        # Complete several steps
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('workforce_baseline', 2025)
        checklist.mark_step_complete('workforce_requirements', 2025)

        # Verify state persists after other operations
        checklist.get_next_step(2025)
        checklist.get_progress_summary()
        checklist.can_resume_from(2025, 'event_generation')

        # State should be unchanged
        status = checklist.get_completion_status(2025)
        assert status['pre_simulation'] == True
        assert status['workforce_baseline'] == True
        assert status['workforce_requirements'] == True
        assert status['event_generation'] == False


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_complete_single_year_simulation(self):
        """Test complete single-year simulation workflow."""
        checklist = SimulationChecklist(2025, 2025)

        # Execute complete workflow
        steps = [
            ('pre_simulation', None),
            ('year_transition', 2025),
            ('workforce_baseline', 2025),
            ('workforce_requirements', 2025),
            ('event_generation', 2025),
            ('workforce_snapshot', 2025),
            ('validation_metrics', 2025)
        ]

        for step_name, year in steps:
            # Verify step is ready
            checklist.assert_step_ready(step_name, year)

            # Complete step
            checklist.mark_step_complete(step_name, year)

        # Verify all complete
        status = checklist.get_completion_status(2025)
        assert all(status.values())

        # Verify next step is None (complete)
        assert checklist.get_next_step(2025) is None

    def test_multi_year_simulation_workflow(self):
        """Test multi-year simulation workflow."""
        checklist = SimulationChecklist(2025, 2027)

        # Complete pre-simulation
        checklist.mark_step_complete('pre_simulation')

        # Complete each year
        for year in [2025, 2026, 2027]:
            checklist.begin_year(year)

            year_steps = ['year_transition', 'workforce_baseline', 'workforce_requirements',
                         'event_generation', 'workforce_snapshot', 'validation_metrics']

            for step in year_steps:
                checklist.assert_step_ready(step, year)
                checklist.mark_step_complete(step, year)

        # Verify all years complete
        for year in [2025, 2026, 2027]:
            assert checklist.get_next_step(year) is None

    def test_interrupted_simulation_resume(self):
        """Test resuming from interrupted simulation."""
        checklist = SimulationChecklist(2025, 2027)

        # Simulate partial completion of 2025
        checklist.mark_step_complete('pre_simulation')
        checklist.mark_step_complete('year_transition', 2025)
        checklist.mark_step_complete('workforce_baseline', 2025)
        checklist.mark_step_complete('workforce_requirements', 2025)
        # Stop at event_generation (simulate interruption)

        # Verify can resume from event_generation
        assert checklist.can_resume_from(2025, 'event_generation')

        # Complete remaining steps
        checklist.mark_step_complete('event_generation', 2025)
        checklist.mark_step_complete('workforce_snapshot', 2025)
        checklist.mark_step_complete('validation_metrics', 2025)

        # Should now be able to proceed to 2026
        checklist.begin_year(2026)
        assert checklist.can_resume_from(2026, 'year_transition')
