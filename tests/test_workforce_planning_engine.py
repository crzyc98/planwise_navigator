"""Tests for E077 Polars Workforce Planning Engine."""

from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from navigator_orchestrator.workforce_planning_engine import (
    WorkforcePlanningEngine,
    WorkforceNeeds
)


@pytest.fixture
def sample_workforce():
    """Sample 100-employee workforce for testing."""
    return pl.DataFrame({
        'employee_id': [f'EMP_{i:04d}' for i in range(100)],
        'employee_ssn': [f'SSN-{100000000 + i:09d}' for i in range(100)],
        'level_id': [1] * 40 + [2] * 30 + [3] * 20 + [4] * 8 + [5] * 2,
        'employee_compensation': [75000.0] * 40 + [95000.0] * 30 + [125000.0] * 20 + [175000.0] * 8 + [250000.0] * 2,
        'current_age': [30] * 100,
        'current_tenure': [3.0] * 100,
    })


class TestAlgebraicSolver:
    """Test ADR E077-A single-rounding algebraic solver."""

    def test_positive_growth_exact_reconciliation(self):
        """Positive growth with exact balance (error = 0)."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=7000,
            growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.25'),
            nh_term_rate=Decimal('0.40')
        )

        # Validate exact balance
        assert needs.reconciliation_error == 0
        assert needs.target_ending_workforce == 7210
        assert needs.total_hires_needed == 3267
        assert needs.expected_experienced_terminations == 1750
        assert needs.implied_new_hire_terminations == 1307

        # Verify equation: start + hires - exp_terms - nh_terms = ending
        calculated_ending = (
            7000 + needs.total_hires_needed
            - needs.expected_experienced_terminations
            - needs.implied_new_hire_terminations
        )
        assert calculated_ending == needs.target_ending_workforce

    def test_zero_growth(self):
        """Zero growth scenario."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=7000,
            growth_rate=Decimal('0.00'),
            exp_term_rate=Decimal('0.12'),
            nh_term_rate=Decimal('0.25')
        )

        assert needs.reconciliation_error == 0
        assert needs.target_ending_workforce == 7000

    def test_negative_growth_rif(self):
        """RIF scenario with negative growth."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=7000,
            growth_rate=Decimal('-0.10'),
            exp_term_rate=Decimal('0.12'),
            nh_term_rate=Decimal('0.40')
        )

        assert needs.total_hires_needed == 0
        assert needs.implied_new_hire_terminations == 0
        assert needs.target_ending_workforce == 6300
        assert needs.reconciliation_error == 0

    def test_feasibility_guard_nh_term_rate(self):
        """Guard 1: NH term rate must be <99%."""
        engine = WorkforcePlanningEngine()

        with pytest.raises(ValueError, match="must be <99%"):
            engine.calculate_exact_needs(
                starting_workforce=7000,
                growth_rate=Decimal('0.03'),
                exp_term_rate=Decimal('0.25'),
                nh_term_rate=Decimal('0.99')
            )

    def test_feasibility_guard_hire_ratio(self):
        """Guard 3: Hires cannot exceed 50% of starting workforce."""
        engine = WorkforcePlanningEngine()

        with pytest.raises(ValueError, match="exceeds 50%"):
            engine.calculate_exact_needs(
                starting_workforce=1000,
                growth_rate=Decimal('0.60'),  # Requires >50% hiring
                exp_term_rate=Decimal('0.05'),
                nh_term_rate=Decimal('0.10')
            )


class TestLargestRemainderMethod:
    """Test ADR E077-B largest-remainder quota allocation."""

    def test_exact_reconciliation(self):
        """Sum of level quotas must equal total quota exactly."""
        engine = WorkforcePlanningEngine()

        quotas = engine.allocate_level_quotas(
            total_quota=3267,
            level_populations={1: 2800, 2: 2100, 3: 1400, 4: 560, 5: 140}
        )

        assert sum(quotas.values()) == 3267

    def test_empty_level_exclusion(self):
        """Edge Case 2: Empty levels receive 0 quota."""
        engine = WorkforcePlanningEngine()

        quotas = engine.allocate_level_quotas(
            total_quota=450,
            level_populations={1: 1000, 2: 500, 3: 200, 4: 50, 5: 0}
        )

        assert quotas.get(5, 0) == 0
        assert sum(quotas.values()) == 450

    def test_quota_exceeds_population(self):
        """Edge Case 1: Level with fewer employees than quota gets capped."""
        engine = WorkforcePlanningEngine()

        quotas = engine.allocate_level_quotas(
            total_quota=450,
            level_populations={1: 1000, 2: 500, 3: 200, 4: 50, 5: 3}
        )

        assert quotas[5] <= 3  # Capped at population
        assert sum(quotas.values()) == 450


class TestDeterministicSelection:
    """Test ADR E077-C deterministic hash-based selection."""

    def test_determinism_same_seed(self, sample_workforce):
        """Same seed produces identical results."""
        engine1 = WorkforcePlanningEngine(random_seed=42)
        engine2 = WorkforcePlanningEngine(random_seed=42)

        needs = WorkforceNeeds(
            starting_workforce=100,
            target_ending_workforce=103,
            total_hires_needed=10,
            expected_experienced_terminations=7,
            implied_new_hire_terminations=0,
            reconciliation_error=0,
            nh_term_rate_check='PASS',
            growth_bounds_check='PASS',
            hire_ratio_check='PASS',
            implied_nh_terms_check='PASS'
        )

        cohorts1 = engine1.generate_cohorts(sample_workforce, needs, 2025)
        cohorts2 = engine2.generate_cohorts(sample_workforce, needs, 2025)

        # Same employees terminated
        assert set(cohorts1['experienced_terminations']['employee_id']) == \
               set(cohorts2['experienced_terminations']['employee_id'])

    def test_different_seeds_different_results(self, sample_workforce):
        """Different seeds produce different selections."""
        engine1 = WorkforcePlanningEngine(random_seed=42)
        engine2 = WorkforcePlanningEngine(random_seed=1337)

        needs = WorkforceNeeds(
            starting_workforce=100,
            target_ending_workforce=103,
            total_hires_needed=10,
            expected_experienced_terminations=7,
            implied_new_hire_terminations=0,
            reconciliation_error=0,
            nh_term_rate_check='PASS',
            growth_bounds_check='PASS',
            hire_ratio_check='PASS',
            implied_nh_terms_check='PASS'
        )

        cohorts1 = engine1.generate_cohorts(sample_workforce, needs, 2025)
        cohorts2 = engine2.generate_cohorts(sample_workforce, needs, 2025)

        # Different employee selection
        assert set(cohorts1['experienced_terminations']['employee_id']) != \
               set(cohorts2['experienced_terminations']['employee_id'])

        # But same counts (deterministic quota allocation)
        assert cohorts1['experienced_terminations'].height == \
               cohorts2['experienced_terminations'].height

    def test_exact_ending_workforce(self, sample_workforce):
        """Ending workforce must equal target exactly."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=100,
            growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.15'),
            nh_term_rate=Decimal('0.25')
        )

        cohorts = engine.generate_cohorts(sample_workforce, needs, 2025)

        ending_workforce = (
            cohorts['continuous_active'].height +
            cohorts['new_hires_active'].height
        )

        assert ending_workforce == needs.target_ending_workforce
        assert ending_workforce == 103  # 100 * 1.03 rounded
