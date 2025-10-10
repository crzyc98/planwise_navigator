"""
E077: End-to-end integration tests for Polars cohort generation engine.

Tests the complete workflow:
1. Polars engine generates cohorts
2. Cohorts written to Parquet
3. dbt loads Parquet files
4. Validation gates (A, B, C) pass
5. Exact reconciliation verified (error = 0)
"""

from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from navigator_orchestrator.workforce_planning_engine import WorkforcePlanningEngine
from navigator_orchestrator.polars_integration import PolarsIntegrationManager
from navigator_orchestrator.config import SimulationConfig, load_simulation_config


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary directory for Polars output."""
    cohort_dir = tmp_path / "polars_cohorts"
    cohort_dir.mkdir()
    return cohort_dir


@pytest.fixture
def test_config(temp_output_dir):
    """Test configuration with Polars cohort engine enabled."""
    # Create minimal config
    config = SimulationConfig(
        simulation={
            'start_year': 2025,
            'end_year': 2025,
            'random_seed': 42,
            'target_growth_rate': 0.03
        },
        compensation={
            'cola_rate': 0.025,
            'merit_budget': 0.03
        },
        workforce={
            'total_termination_rate': 0.25,
            'new_hire_termination_rate': 0.40
        },
        optimization={
            'level': 'high',
            'event_generation': {
                'mode': 'polars',
                'polars': {
                    'enabled': True,
                    'use_cohort_engine': True,
                    'cohort_output_dir': str(temp_output_dir)
                }
            }
        }
    )
    return config


@pytest.fixture
def sample_workforce_100():
    """100-employee workforce for testing."""
    return pl.DataFrame({
        'employee_id': [f'EMP_{i:04d}' for i in range(100)],
        'employee_ssn': [f'SSN-{100000000 + i:09d}' for i in range(100)],
        'level_id': [1] * 40 + [2] * 30 + [3] * 20 + [4] * 8 + [5] * 2,
        'employee_compensation': [75000.0] * 40 + [95000.0] * 30 + [125000.0] * 20 + [175000.0] * 8 + [250000.0] * 2,
        'current_age': [30] * 100,
        'current_tenure': [3.0] * 100,
    })


class TestE077Integration:
    """Integration tests for E077 Polars cohort generation."""

    def test_cohort_generation_exact_reconciliation(self, sample_workforce_100):
        """Test that cohort generation achieves exact reconciliation (error = 0)."""
        engine = WorkforcePlanningEngine(random_seed=42)

        # Calculate exact needs
        needs = engine.calculate_exact_needs(
            starting_workforce=100,
            growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.15'),
            nh_term_rate=Decimal('0.25')
        )

        # Verify exact reconciliation
        assert needs.reconciliation_error == 0

        # Generate cohorts
        cohorts = engine.generate_cohorts(sample_workforce_100, needs, 2025)

        # Verify cohort counts
        assert 'continuous_active' in cohorts
        assert 'experienced_terminations' in cohorts
        assert 'new_hires_active' in cohorts
        assert 'new_hires_terminated' in cohorts

        # Verify exact ending workforce
        ending_count = (
            cohorts['continuous_active'].height +
            cohorts['new_hires_active'].height
        )
        assert ending_count == needs.target_ending_workforce == 103

    def test_parquet_atomic_write(self, sample_workforce_100, temp_output_dir):
        """Test atomic Parquet write with manifest."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=100,
            growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.15'),
            nh_term_rate=Decimal('0.25')
        )

        cohorts = engine.generate_cohorts(sample_workforce_100, needs, 2025)

        # Write atomically
        output_path = engine.write_cohorts_atomically(
            cohorts,
            temp_output_dir,
            2025,
            "test_scenario"
        )

        # Verify directory structure
        assert output_path.exists()
        assert (output_path / 'continuous_active.parquet').exists()
        assert (output_path / 'experienced_terminations.parquet').exists()
        assert (output_path / 'new_hires_active.parquet').exists()
        assert (output_path / 'new_hires_terminated.parquet').exists()
        assert (output_path / 'manifest.json').exists()

        # Verify manifest contents
        import json
        manifest = json.loads((output_path / 'manifest.json').read_text())
        assert manifest['scenario_id'] == 'test_scenario'
        assert manifest['simulation_year'] == 2025
        assert manifest['random_seed'] == 42
        assert 'continuous_active' in manifest['cohorts']

    def test_deterministic_reproducibility(self, sample_workforce_100):
        """Test that same seed produces identical cohorts."""
        engine1 = WorkforcePlanningEngine(random_seed=42)
        engine2 = WorkforcePlanningEngine(random_seed=42)

        needs = engine1.calculate_exact_needs(
            starting_workforce=100,
            growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.15'),
            nh_term_rate=Decimal('0.25')
        )

        cohorts1 = engine1.generate_cohorts(sample_workforce_100, needs, 2025)
        cohorts2 = engine2.generate_cohorts(sample_workforce_100, needs, 2025)

        # Verify identical terminations
        terms1 = set(cohorts1['experienced_terminations']['employee_id'])
        terms2 = set(cohorts2['experienced_terminations']['employee_id'])
        assert terms1 == terms2

        # Verify identical new hire IDs
        nh1 = cohorts1['new_hires_active']['employee_id'].to_list()
        nh2 = cohorts2['new_hires_active']['employee_id'].to_list()
        assert nh1 == nh2

    def test_validation_gates_pass(self, sample_workforce_100):
        """Test that all three validation gates (A, B, C) pass."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=100,
            growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.15'),
            nh_term_rate=Decimal('0.25')
        )

        # Gate A: Workforce needs exact reconciliation
        assert needs.reconciliation_error == 0
        assert needs.nh_term_rate_check == 'PASS'
        assert needs.growth_bounds_check == 'PASS'

        # Gate B: Level quota allocation sums exactly
        level_pops = {1: 40, 2: 30, 3: 20, 4: 8, 5: 2}
        term_quotas = engine.allocate_level_quotas(
            needs.expected_experienced_terminations,
            level_pops
        )
        assert sum(term_quotas.values()) == needs.expected_experienced_terminations

        hire_quotas = engine.allocate_level_quotas(
            needs.total_hires_needed,
            level_pops
        )
        assert sum(hire_quotas.values()) == needs.total_hires_needed

        # Gate C: Actual ending workforce equals target
        cohorts = engine.generate_cohorts(sample_workforce_100, needs, 2025)
        ending_count = (
            cohorts['continuous_active'].height +
            cohorts['new_hires_active'].height
        )
        assert ending_count == needs.target_ending_workforce

    @pytest.mark.parametrize("growth_rate,exp_term_rate,nh_term_rate", [
        (Decimal('0.03'), Decimal('0.25'), Decimal('0.40')),  # Positive growth
        (Decimal('0.00'), Decimal('0.12'), Decimal('0.25')),  # Zero growth
        (Decimal('-0.10'), Decimal('0.12'), Decimal('0.40')),  # RIF scenario
        (Decimal('0.10'), Decimal('0.08'), Decimal('0.20')),  # High growth
    ])
    def test_growth_scenarios(
        self,
        sample_workforce_100,
        growth_rate,
        exp_term_rate,
        nh_term_rate
    ):
        """Test exact reconciliation across various growth scenarios."""
        engine = WorkforcePlanningEngine(random_seed=42)

        needs = engine.calculate_exact_needs(
            starting_workforce=100,
            growth_rate=growth_rate,
            exp_term_rate=exp_term_rate,
            nh_term_rate=nh_term_rate
        )

        # Verify exact reconciliation
        assert needs.reconciliation_error == 0

        # Generate cohorts
        cohorts = engine.generate_cohorts(sample_workforce_100, needs, 2025)

        # Verify balance equation
        calculated_ending = (
            100 +
            needs.total_hires_needed -
            needs.expected_experienced_terminations -
            needs.implied_new_hire_terminations
        )
        assert calculated_ending == needs.target_ending_workforce

        # Verify actual ending equals target
        ending_count = (
            cohorts['continuous_active'].height +
            cohorts['new_hires_active'].height
        )
        assert ending_count == needs.target_ending_workforce
