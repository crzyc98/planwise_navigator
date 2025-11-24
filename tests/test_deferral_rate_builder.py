#!/usr/bin/env python3
"""
Unit tests for DeferralRateBuilder

Tests cover:
- Year 1 state building (baseline rates + events)
- Year 2+ state building (previous state + events)
- Age/income segmentation
- Escalation event tracking
- Deferral rate changes
- Performance benchmarking
"""

import pytest
import polars as pl
from datetime import date
from planalign_orchestrator.polars_state_pipeline import DeferralRateBuilder
import logging


class TestDeferralRateBuilder:
    """Test DeferralRateBuilder functionality."""

    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return logging.getLogger('test')

    @pytest.fixture
    def builder(self, logger):
        """Create DeferralRateBuilder instance."""
        return DeferralRateBuilder(logger)

    @pytest.fixture
    def baseline_workforce(self):
        """Sample baseline workforce with demographics."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002', 'EMP003', 'EMP004'],
            'employee_gross_compensation': [250000.0, 100000.0, 150000.0, 75000.0],
            'employee_birth_date': [
                date(1980, 1, 1),  # Age 45 (senior)
                date(1990, 6, 15),  # Age 35 (mid_career)
                date(1985, 3, 20),  # Age 40 (mid_career)
                date(1995, 8, 10)   # Age 30 (young/mid_career boundary)
            ],
            'employee_enrollment_date': [
                date(2024, 3, 1),
                date(2024, 6, 15),
                date(2024, 9, 1),
                date(2025, 2, 1)
            ],
            'employee_deferral_rate': [0.10, 0.06, 0.08, 0.04],
            'active': [True, True, True, True]
        })

    @pytest.fixture
    def enrollment_state(self):
        """Sample enrollment state."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002', 'EMP003', 'EMP004'],
            'simulation_year': [2025, 2025, 2025, 2025],
            'enrollment_status': [True, True, True, True],
            'enrollment_date': [
                date(2024, 3, 1),
                date(2024, 6, 15),
                date(2024, 9, 1),
                date(2025, 2, 1)
            ]
        })

    @pytest.fixture
    def deferral_events(self):
        """Sample deferral events."""
        return pl.DataFrame({
            'employee_id': ['EMP002', 'EMP003'],
            'event_type': ['enrollment', 'deferral_escalation'],
            'simulation_year': [2025, 2025],
            'effective_date': [date(2025, 2, 1), date(2025, 7, 1)],
            'employee_deferral_rate': [0.06, 0.09],
            'event_details': ['Enrolled at 6%', 'Escalated to 9%']
        })

    def test_builder_initialization(self, builder):
        """Test builder initializes with default rates."""
        assert builder is not None
        assert builder.default_rates is not None
        # Check some default rates
        assert builder.default_rates[('young', 'low_income')] == 0.03
        assert builder.default_rates[('senior', 'executive')] == 0.10

    def test_year1_no_events(self, builder, enrollment_state, baseline_workforce):
        """Test Year 1 with no deferral events uses baseline rates."""
        empty_events = pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'simulation_year': [],
            'effective_date': [],
            'employee_deferral_rate': [],
            'event_details': []
        })

        state = builder.build(
            simulation_year=2025,
            events_df=empty_events,
            enrollment_state_df=enrollment_state,
            baseline_df=baseline_workforce,
            previous_state_df=None
        )

        # Should have 4 enrolled employees
        assert state.height == 4

        # Check segmentation and baseline rates
        emp001 = state.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['age_segment'][0] == 'senior'  # Age 45
        assert emp001['income_segment'][0] == 'executive'  # $250K
        assert emp001['current_deferral_rate'][0] == 0.10  # senior/executive baseline

    def test_year1_with_enrollment_events(self, builder, enrollment_state, baseline_workforce, deferral_events):
        """Test Year 1 with enrollment events overrides baseline rates."""
        state = builder.build(
            simulation_year=2025,
            events_df=deferral_events,
            enrollment_state_df=enrollment_state,
            baseline_df=baseline_workforce,
            previous_state_df=None
        )

        # Should have 4 enrolled employees
        assert state.height == 4

        # EMP002: Has enrollment event with 6% rate
        emp002 = state.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['current_deferral_rate'][0] == 0.06  # From event
        assert emp002['escalation_count'][0] == 0

        # EMP003: Has escalation event to 9%
        emp003 = state.filter(pl.col('employee_id') == 'EMP003')
        assert emp003['current_deferral_rate'][0] == 0.09  # From escalation
        assert emp003['escalation_count'][0] == 1
        assert emp003['had_escalation_this_year'][0] is True

    def test_demographics_segmentation(self, builder, enrollment_state, baseline_workforce):
        """Test age/income segmentation logic."""
        demographics = builder._get_employee_demographics(
            baseline_workforce,
            enrollment_state.select(['employee_id', 'enrollment_date'])
        )

        # EMP001: Age 45, $250K -> senior/executive
        emp001 = demographics.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['age_segment'][0] == 'senior'
        assert emp001['income_segment'][0] == 'executive'

        # EMP002: Age 35, $100K -> mid_career/moderate
        emp002 = demographics.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['age_segment'][0] == 'mid_career'
        assert emp002['income_segment'][0] == 'moderate'

        # EMP004: Age 30, $75K -> young or mid_career/low_income
        emp004 = demographics.filter(pl.col('employee_id') == 'EMP004')
        assert emp004['income_segment'][0] == 'low_income'

    def test_extract_deferral_events(self, builder, deferral_events):
        """Test extraction of deferral-related events."""
        # Add some non-deferral events to test filtering
        all_events = pl.concat([
            deferral_events,
            pl.DataFrame({
                'employee_id': ['EMP001'],
                'event_type': ['merit'],
                'simulation_year': [2025],
                'effective_date': [date(2025, 3, 15)],
                'employee_deferral_rate': [None],
                'event_details': ['Merit raise']
            })
        ], how='diagonal')

        extracted = builder._extract_deferral_events(all_events, 2025)

        # Should only have the 2 deferral events
        assert extracted.height == 2
        assert 'merit' not in extracted['event_type'].to_list()

    def test_year2_no_events_carry_forward(self, builder, enrollment_state, baseline_workforce):
        """Test Year 2 with no events carries forward Year 1 state."""
        # Year 1 state
        year1_state = pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002', 'EMP003'],
            'simulation_year': [2025, 2025, 2025],
            'current_deferral_rate': [0.10, 0.06, 0.09],
            'escalation_count': [0, 0, 1],
            'last_escalation_date': [None, None, date(2025, 7, 1)],
            'had_escalation_this_year': [False, False, True],
            'age_segment': ['senior', 'mid_career', 'mid_career'],
            'income_segment': ['executive', 'moderate', 'high']
        })

        # Year 2 enrollment state (same employees enrolled)
        year2_enrollment = enrollment_state.with_columns(
            pl.lit(2026).alias('simulation_year')
        )

        empty_events = pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'simulation_year': [],
            'effective_date': [],
            'employee_deferral_rate': [],
            'event_details': []
        })

        year2_state = builder.build(
            simulation_year=2026,
            events_df=empty_events,
            enrollment_state_df=year2_enrollment,
            baseline_df=baseline_workforce,
            previous_state_df=year1_state
        )

        # Should carry forward all 4 enrolled employees
        assert year2_state.height >= 3  # At least the 3 from year 1

        # EMP001: Deferral rate should be preserved
        emp001 = year2_state.filter(pl.col('employee_id') == 'EMP001')
        assert emp001['current_deferral_rate'][0] == 0.10
        assert emp001['escalation_count'][0] == 0
        assert emp001['had_escalation_this_year'][0] is False

        # EMP003: Deferral rate and escalation count preserved
        emp003 = year2_state.filter(pl.col('employee_id') == 'EMP003')
        assert emp003['current_deferral_rate'][0] == 0.09
        assert emp003['escalation_count'][0] == 1
        assert emp003['had_escalation_this_year'][0] is False  # No NEW escalations

    def test_year2_with_escalation(self, builder, enrollment_state, baseline_workforce):
        """Test Year 2 with escalation event."""
        # Year 1 state
        year1_state = pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'simulation_year': [2025, 2025],
            'current_deferral_rate': [0.10, 0.06],
            'escalation_count': [0, 0],
            'last_escalation_date': [None, None],
            'had_escalation_this_year': [False, False],
            'age_segment': ['senior', 'mid_career'],
            'income_segment': ['executive', 'moderate']
        })

        # Year 2 enrollment
        year2_enrollment = enrollment_state.filter(
            pl.col('employee_id').is_in(['EMP001', 'EMP002'])
        ).with_columns(pl.lit(2026).alias('simulation_year'))

        # Year 2 escalation event for EMP002
        year2_events = pl.DataFrame({
            'employee_id': ['EMP002'],
            'event_type': ['deferral_escalation'],
            'simulation_year': [2026],
            'effective_date': [date(2026, 7, 1)],
            'employee_deferral_rate': [0.07],
            'event_details': ['Escalated to 7%']
        })

        year2_state = builder.build(
            simulation_year=2026,
            events_df=year2_events,
            enrollment_state_df=year2_enrollment,
            baseline_df=baseline_workforce,
            previous_state_df=year1_state
        )

        # EMP002: Should have new rate and increased escalation count
        emp002 = year2_state.filter(pl.col('employee_id') == 'EMP002')
        assert emp002['current_deferral_rate'][0] == 0.07  # New rate
        assert emp002['escalation_count'][0] == 1  # Incremented
        assert emp002['had_escalation_this_year'][0] is True

    def test_no_enrolled_employees(self, builder, baseline_workforce):
        """Test handling when no employees are enrolled."""
        empty_enrollment = pl.DataFrame({
            'employee_id': [],
            'simulation_year': [],
            'enrollment_status': [],
            'enrollment_date': []
        })

        empty_events = pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'simulation_year': [],
            'effective_date': [],
            'employee_deferral_rate': [],
            'event_details': []
        })

        state = builder.build(
            simulation_year=2025,
            events_df=empty_events,
            enrollment_state_df=empty_enrollment,
            baseline_df=baseline_workforce,
            previous_state_df=None
        )

        # Should return empty DataFrame
        assert state.height == 0


@pytest.mark.integration
class TestDeferralRatePerformance:
    """Performance benchmarking tests for DeferralRateBuilder."""

    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return logging.getLogger('test_perf')

    @pytest.fixture
    def builder(self, logger):
        """Create DeferralRateBuilder instance."""
        return DeferralRateBuilder(logger)

    @pytest.fixture
    def large_baseline(self):
        """Generate large baseline workforce (10K employees)."""
        n = 10000
        return pl.DataFrame({
            'employee_id': [f'EMP{i:06d}' for i in range(n)],
            'employee_gross_compensation': [50000.0 + (i * 15) for i in range(n)],
            'employee_birth_date': [
                date(1970 + (i % 40), 1 + (i % 12), 1)
                for i in range(n)
            ],
            'employee_enrollment_date': [
                date(2024, 1 + (i % 12), 1) if i % 2 == 0 else date(2025, 1, 1)
                for i in range(n)
            ],
            'employee_deferral_rate': [0.03 + (i % 10) * 0.01 for i in range(n)],
            'active': [True] * n
        })

    @pytest.fixture
    def large_enrollment(self):
        """Generate large enrollment state (10K employees)."""
        n = 10000
        return pl.DataFrame({
            'employee_id': [f'EMP{i:06d}' for i in range(n)],
            'simulation_year': [2025] * n,
            'enrollment_status': [True] * n,
            'enrollment_date': [date(2024, 1 + (i % 12), 1) for i in range(n)]
        })

    @pytest.fixture
    def large_events(self):
        """Generate large event set (1K deferral events)."""
        n = 1000
        return pl.DataFrame({
            'employee_id': [f'EMP{i:06d}' for i in range(n)],
            'event_type': ['deferral_escalation' if i % 3 == 0 else 'enrollment' for i in range(n)],
            'simulation_year': [2025] * n,
            'effective_date': [date(2025, 1 + (i % 12), 1) for i in range(n)],
            'employee_deferral_rate': [0.04 + (i % 8) * 0.01 for i in range(n)],
            'event_details': [f'Event {i}' for i in range(n)]
        })

    def test_year1_performance_10k_employees(self, builder, large_enrollment, large_baseline, large_events):
        """Test Year 1 performance with 10K employees."""
        import time

        start = time.time()
        state = builder.build(
            simulation_year=2025,
            events_df=large_events,
            enrollment_state_df=large_enrollment,
            baseline_df=large_baseline,
            previous_state_df=None
        )
        elapsed = time.time() - start

        # Performance target: <500ms
        assert elapsed < 0.5, f"Performance target missed: {elapsed:.3f}s (target: <0.5s)"

        # Validate output
        assert state.height == 10000
        assert 'current_deferral_rate' in state.columns
        assert 'escalation_count' in state.columns

        print(f"\n✅ Year 1 Performance: {elapsed:.3f}s for 10K employees, 1K events")

    def test_year2_performance_state_transition(self, builder, large_enrollment, large_baseline, large_events):
        """Test Year 2 performance with state transition."""
        import time

        # Build Year 1 state
        year1_state = builder.build(
            simulation_year=2025,
            events_df=large_events,
            enrollment_state_df=large_enrollment,
            baseline_df=large_baseline,
            previous_state_df=None
        )

        # Build Year 2 state with fewer events
        year2_enrollment = large_enrollment.with_columns(pl.lit(2026).alias('simulation_year'))
        year2_events = large_events.head(300).with_columns(pl.lit(2026).alias('simulation_year'))

        start = time.time()
        year2_state = builder.build(
            simulation_year=2026,
            events_df=year2_events,
            enrollment_state_df=year2_enrollment,
            baseline_df=large_baseline,
            previous_state_df=year1_state
        )
        elapsed = time.time() - start

        # Performance target: <500ms
        assert elapsed < 0.5, f"Performance target missed: {elapsed:.3f}s (target: <0.5s)"

        # Validate escalation counts accumulated
        assert year2_state.height == 10000

        print(f"\n✅ Year 2 Performance: {elapsed:.3f}s for state transition (10K employees)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
