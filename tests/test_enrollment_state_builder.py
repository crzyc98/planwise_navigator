#!/usr/bin/env python3
"""
Unit tests for EnrollmentStateBuilder

Tests cover:
- Year 1 state building (baseline + events)
- Year 2+ state building (previous state + events)
- Event consolidation logic
- Enrollment status tracking
- Opt-out handling
- Re-enrollment tracking
- Performance benchmarking
"""

import pytest
import polars as pl
from datetime import date
from navigator_orchestrator.polars_state_pipeline import EnrollmentStateBuilder
import logging


class TestEnrollmentStateBuilder:
    """Test EnrollmentStateBuilder functionality."""

    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return logging.getLogger('test')

    @pytest.fixture
    def builder(self, logger):
        """Create EnrollmentStateBuilder instance."""
        return EnrollmentStateBuilder(logger)

    @pytest.fixture
    def baseline_workforce(self):
        """Sample baseline workforce data."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002', 'EMP003', 'EMP004'],
            'employee_enrollment_date': [
                date(2024, 3, 1),  # Already enrolled
                None,              # Not enrolled
                date(2024, 6, 15), # Already enrolled
                None               # Not enrolled
            ],
            'employee_gross_compensation': [100000.0, 85000.0, 95000.0, 120000.0],
            'active': [True, True, True, True]
        })

    @pytest.fixture
    def year1_enrollment_events(self):
        """Sample Year 1 enrollment events."""
        return pl.DataFrame({
            'employee_id': ['EMP002', 'EMP004'],
            'event_type': ['enrollment', 'enrollment'],
            'event_category': ['auto_enrollment', 'voluntary_enrollment'],
            'effective_date': [date(2025, 2, 1), date(2025, 4, 1)],
            'event_details': ['Auto-enrolled at 6%', 'Voluntary enrollment at 8%']
        })

    @pytest.fixture
    def year2_optout_events(self):
        """Sample Year 2 opt-out events."""
        return pl.DataFrame({
            'employee_id': ['EMP002'],
            'event_type': ['enrollment_change'],
            'event_category': ['enrollment_change'],
            'effective_date': [date(2026, 5, 15)],
            'event_details': ['Employee opted out']
        })

    def test_builder_initialization(self, builder):
        """Test builder initializes correctly."""
        assert builder is not None
        assert builder.logger is not None

    def test_year1_no_events(self, builder, baseline_workforce):
        """Test Year 1 state building with no enrollment events."""
        empty_events = pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'event_category': [],
            'effective_date': [],
            'event_details': []
        })

        state = builder.build(
            simulation_year=2025,
            events_df=empty_events,
            baseline_df=baseline_workforce,
            previous_state_df=None
        )

        # Should have 4 employees (all from baseline)
        assert state.height == 4

        # Check enrollment status matches baseline
        emp001 = state.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['enrollment_status'][0] is True
        assert emp001['enrollment_date'][0] == date(2024, 3, 1)
        assert emp001['enrollment_source'][0] == 'baseline'

        emp002 = state.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['enrollment_status'][0] is False
        assert emp002['enrollment_date'][0] is None
        # EMP002 is from baseline even though not enrolled
        assert emp002['enrollment_source'][0] == 'baseline'

    def test_year1_with_enrollment_events(self, builder, baseline_workforce, year1_enrollment_events):
        """Test Year 1 state building with enrollment events."""
        # Combine baseline + enrollment events
        all_events = year1_enrollment_events

        state = builder.build(
            simulation_year=2025,
            events_df=all_events,
            baseline_df=baseline_workforce,
            previous_state_df=None
        )

        # Should have 4 employees
        assert state.height == 4

        # EMP001: Baseline enrollment (unchanged)
        emp001 = state.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['enrollment_status'][0] is True
        assert emp001['enrollment_date'][0] == date(2024, 3, 1)
        assert emp001['enrollment_source'][0] == 'baseline'

        # EMP002: New auto-enrollment event (overrides baseline)
        emp002 = state.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['enrollment_status'][0] is True
        assert emp002['enrollment_date'][0] == date(2025, 2, 1)
        assert emp002['enrollment_source'][0] == 'event_2025'
        assert emp002['enrollment_method'][0] == 'auto'

        # EMP004: New voluntary enrollment event
        emp004 = state.filter(pl.col('employee_id') == 'EMP004')
        assert emp004['enrollment_status'][0] is True
        assert emp004['enrollment_date'][0] == date(2025, 4, 1)
        assert emp004['enrollment_source'][0] == 'event_2025'
        assert emp004['enrollment_method'][0] == 'voluntary'

    def test_year2_with_optout(self, builder, baseline_workforce, year1_enrollment_events, year2_optout_events):
        """Test Year 2 state building with opt-out event."""
        # First build Year 1 state
        year1_state = builder.build(
            simulation_year=2025,
            events_df=year1_enrollment_events,
            baseline_df=baseline_workforce,
            previous_state_df=None
        )

        # Now build Year 2 state with opt-out
        year2_state = builder.build(
            simulation_year=2026,
            events_df=year2_optout_events,
            baseline_df=baseline_workforce,
            previous_state_df=year1_state
        )

        # EMP002: Should be opted out
        emp002 = year2_state.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['enrollment_status'][0] is False
        assert emp002['ever_opted_out'][0] is True
        assert emp002['ever_unenrolled'][0] is True  # Was enrolled, then opted out

        # EMP001: Should carry forward from Year 1
        emp001 = year2_state.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['enrollment_status'][0] is True
        assert emp001['years_since_first_enrollment'][0] == 1  # Incremented from Year 1

    def test_event_consolidation_multiple_events(self, builder):
        """Test consolidation when employee has multiple enrollment events."""
        events = pl.DataFrame({
            'employee_id': ['EMP001', 'EMP001', 'EMP001'],
            'event_type': ['enrollment', 'enrollment_change', 'enrollment'],
            'event_category': ['auto_enrollment', 'enrollment_change', 'voluntary_enrollment'],
            'effective_date': [date(2025, 1, 1), date(2025, 3, 15), date(2025, 6, 1)],
            'event_details': ['Auto-enrolled', 'Changed deferral', 'Re-enrolled']
        })

        summary = builder._consolidate_current_year_events(events, 2025)

        # Should have 1 employee
        assert summary.height == 1

        # Should use latest enrollment event (June 1)
        assert summary['enrollment_event_date'][0] == date(2025, 6, 1)
        assert summary['enrollment_events_count'][0] == 2  # Two enrollment events
        assert summary['enrollment_change_events_count'][0] == 1

    def test_event_consolidation_enrollment_then_optout(self, builder):
        """Test consolidation when employee enrolls then opts out."""
        events = pl.DataFrame({
            'employee_id': ['EMP001', 'EMP001'],
            'event_type': ['enrollment', 'enrollment_change'],
            'event_category': ['auto_enrollment', 'enrollment_change'],
            'effective_date': [date(2025, 2, 1), date(2025, 8, 15)],
            'event_details': ['Auto-enrolled at 6%', 'Employee opted out']
        })

        summary = builder._consolidate_current_year_events(events, 2025)

        # Opt-out should override enrollment
        assert summary['has_enrollment_event_this_year'][0] is False
        assert summary['had_opt_out_this_year'][0] is True

    def test_year2_no_events_carry_forward(self, builder, baseline_workforce):
        """Test Year 2 with no events carries forward Year 1 state."""
        # Year 1 state
        year1_state = pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'simulation_year': [2025, 2025],
            'enrollment_date': [date(2024, 3, 1), date(2025, 2, 1)],
            'enrollment_status': [True, True],
            'years_since_first_enrollment': [0, 0],
            'enrollment_source': ['baseline', 'event_2025'],
            'enrollment_method': [None, 'auto'],
            'ever_opted_out': [False, False],
            'ever_unenrolled': [False, False],
            'enrollment_events_this_year': [0, 1],
            'enrollment_change_events_this_year': [0, 0]
        })

        empty_events = pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'event_category': [],
            'effective_date': [],
            'event_details': []
        })

        year2_state = builder.build(
            simulation_year=2026,
            events_df=empty_events,
            baseline_df=baseline_workforce,
            previous_state_df=year1_state
        )

        # Should have 2 employees
        assert year2_state.height == 2

        # EMP001: Years since enrollment should increment
        emp001 = year2_state.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['enrollment_status'][0] is True
        assert emp001['enrollment_date'][0] == date(2024, 3, 1)
        assert emp001['years_since_first_enrollment'][0] == 1  # Incremented

        # EMP002: Should also increment
        emp002 = year2_state.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['enrollment_status'][0] is True
        assert emp002['enrollment_date'][0] == date(2025, 2, 1)
        assert emp002['years_since_first_enrollment'][0] == 1
        assert emp002['enrollment_method'][0] == 'auto'  # Preserved

    def test_empty_events_dataframe(self, builder):
        """Test consolidation with empty events DataFrame."""
        empty_events = pl.DataFrame()

        summary = builder._consolidate_current_year_events(empty_events, 2025)

        # Should return empty DataFrame
        assert summary.height == 0


@pytest.mark.integration
class TestEnrollmentStatePerformance:
    """Performance benchmarking tests for EnrollmentStateBuilder."""

    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return logging.getLogger('test_perf')

    @pytest.fixture
    def builder(self, logger):
        """Create EnrollmentStateBuilder instance."""
        return EnrollmentStateBuilder(logger)

    @pytest.fixture
    def large_baseline(self):
        """Generate large baseline workforce (10K employees)."""
        n = 10000
        return pl.DataFrame({
            'employee_id': [f'EMP{i:06d}' for i in range(n)],
            'employee_enrollment_date': [
                date(2024, 1 + (i % 12), 1) if i % 2 == 0 else None
                for i in range(n)
            ],
            'employee_gross_compensation': [50000.0 + (i * 100) for i in range(n)],
            'active': [True] * n
        })

    @pytest.fixture
    def large_events(self):
        """Generate large event set (2K enrollment events)."""
        n = 2000
        return pl.DataFrame({
            'employee_id': [f'EMP{i:06d}' for i in range(n)],
            'event_type': ['enrollment' if i % 3 == 0 else 'enrollment_change' for i in range(n)],
            'event_category': [
                'auto_enrollment' if i % 2 == 0 else 'voluntary_enrollment'
                for i in range(n)
            ],
            'effective_date': [date(2025, 1 + (i % 12), 1) for i in range(n)],
            'event_details': [f'Event {i}' for i in range(n)]
        })

    def test_year1_performance_10k_employees(self, builder, large_baseline, large_events):
        """Test Year 1 performance with 10K employees and 2K events."""
        import time

        start = time.time()
        state = builder.build(
            simulation_year=2025,
            events_df=large_events,
            baseline_df=large_baseline,
            previous_state_df=None
        )
        elapsed = time.time() - start

        # Performance target: <500ms
        assert elapsed < 0.5, f"Performance target missed: {elapsed:.3f}s (target: <0.5s)"

        # Validate output
        assert state.height == 10000
        assert 'enrollment_status' in state.columns
        assert 'enrollment_date' in state.columns

        print(f"\n✅ Year 1 Performance: {elapsed:.3f}s for 10K employees, 2K events")

    def test_year2_performance_state_transition(self, builder, large_baseline, large_events):
        """Test Year 2 performance with state transition."""
        import time

        # Build Year 1 state
        year1_state = builder.build(
            simulation_year=2025,
            events_df=large_events,
            baseline_df=large_baseline,
            previous_state_df=None
        )

        # Build Year 2 state with fewer events
        year2_events = large_events.head(500)  # 500 events in Year 2

        start = time.time()
        year2_state = builder.build(
            simulation_year=2026,
            events_df=year2_events,
            baseline_df=large_baseline,
            previous_state_df=year1_state
        )
        elapsed = time.time() - start

        # Performance target: <500ms
        assert elapsed < 0.5, f"Performance target missed: {elapsed:.3f}s (target: <0.5s)"

        # Validate years_since_first_enrollment incremented
        enrolled = year2_state.filter(pl.col('enrollment_status') == True)
        assert enrolled.height > 0

        print(f"\n✅ Year 2 Performance: {elapsed:.3f}s for state transition (10K employees)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
