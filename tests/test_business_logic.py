#!/usr/bin/env python3
"""
Business Logic Tests

Validate business rules and metrics make sense.
Part of Epic E047: Production Testing & Validation Framework.
"""

from __future__ import annotations

import pytest
import duckdb
import argparse
from navigator_orchestrator.cli import cmd_run


class TestBusinessLogic:
    """Validate business rules and metrics make sense"""

    def test_deterministic_simulation(self):
        """Same seed produces identical results"""

        # Create test arguments for deterministic runs
        def create_test_args(seed: int):
            return argparse.Namespace(
                config=None,
                database=None,
                threads=4,
                dry_run=False,
                verbose=False,
                years="2025-2025",
                seed=seed,
                force_clear=True,  # Ensure clean slate
                resume_from=None
            )

        # Run simulation twice with same seed
        seed = 42
        args1 = create_test_args(seed)
        args2 = create_test_args(seed)

        # Execute first run
        result1 = cmd_run(args1)
        assert result1 == 0, "First simulation run failed"

        # Capture results from first run
        with duckdb.connect("simulation.duckdb") as conn:
            workforce_count_1 = conn.execute("""
                SELECT COUNT(*) FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()[0]

            total_compensation_1 = conn.execute("""
                SELECT SUM(total_compensation) FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()[0]

            total_contributions_1 = conn.execute("""
                SELECT SUM(annual_contribution_amount) FROM int_employee_contributions
                WHERE simulation_year = 2025
            """).fetchone()[0]

            hire_events_1 = conn.execute("""
                SELECT COUNT(*) FROM fct_yearly_events
                WHERE event_type = 'hire' AND simulation_year = 2025
            """).fetchone()[0]

        # Execute second run
        result2 = cmd_run(args2)
        assert result2 == 0, "Second simulation run failed"

        # Capture results from second run
        with duckdb.connect("simulation.duckdb") as conn:
            workforce_count_2 = conn.execute("""
                SELECT COUNT(*) FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()[0]

            total_compensation_2 = conn.execute("""
                SELECT SUM(total_compensation) FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()[0]

            total_contributions_2 = conn.execute("""
                SELECT SUM(annual_contribution_amount) FROM int_employee_contributions
                WHERE simulation_year = 2025
            """).fetchone()[0]

            hire_events_2 = conn.execute("""
                SELECT COUNT(*) FROM fct_yearly_events
                WHERE event_type = 'hire' AND simulation_year = 2025
            """).fetchone()[0]

        # Verify deterministic results
        assert workforce_count_1 == workforce_count_2, f"Workforce count mismatch: {workforce_count_1} vs {workforce_count_2}"
        assert abs((total_compensation_1 or 0) - (total_compensation_2 or 0)) < 0.01, f"Total compensation mismatch: {total_compensation_1} vs {total_compensation_2}"
        assert abs((total_contributions_1 or 0) - (total_contributions_2 or 0)) < 0.01, f"Total contributions mismatch: {total_contributions_1} vs {total_contributions_2}"
        assert hire_events_1 == hire_events_2, f"Hire events mismatch: {hire_events_1} vs {hire_events_2}"

    def test_growth_targets_achieved(self):
        """Verify configured growth rates are approximately achieved"""

        # Run a 2-year simulation to test growth
        args = argparse.Namespace(
            config=None,
            database=None,
            threads=4,
            dry_run=False,
            verbose=False,
            years="2025-2026",
            seed=42,
            force_clear=True,
            resume_from=None
        )

        result = cmd_run(args)
        assert result == 0, "Multi-year simulation failed"

        with duckdb.connect("simulation.duckdb") as conn:
            # Get workforce counts by year
            growth_data = conn.execute("""
                SELECT
                    simulation_year,
                    COUNT(*) as workforce_count
                FROM fct_workforce_snapshot
                WHERE employment_status = 'active'
                GROUP BY simulation_year
                ORDER BY simulation_year
            """).fetchall()

            if len(growth_data) >= 2:
                year_2025_count = growth_data[0][1]
                year_2026_count = growth_data[1][1]

                if year_2025_count > 0:
                    growth_achieved = (year_2026_count - year_2025_count) / year_2025_count

                    # Allow reasonable growth range (-5% to +15%)
                    assert -0.05 <= growth_achieved <= 0.15, f"Growth rate {growth_achieved:.2%} outside reasonable range"

    def test_compensation_reasonableness(self):
        """Verify compensation values are reasonable"""
        with duckdb.connect("simulation.duckdb") as conn:
            comp_stats = conn.execute("""
                SELECT
                    MIN(total_compensation) as min_comp,
                    MAX(total_compensation) as max_comp,
                    AVG(total_compensation) as avg_comp,
                    STDDEV(total_compensation) as stddev_comp,
                    COUNT(*) as total_count
                FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()

            if comp_stats and comp_stats[4] > 0:  # If we have data
                min_comp, max_comp, avg_comp, stddev_comp, total_count = comp_stats

                # Sanity checks for compensation
                assert min_comp >= 25000, f"Minimum compensation too low: ${min_comp:,.2f}"
                assert max_comp <= 750000, f"Maximum compensation too high: ${max_comp:,.2f}"
                assert 40000 <= avg_comp <= 150000, f"Average compensation unreasonable: ${avg_comp:,.2f}"

                # Check distribution is reasonable (not all same salary)
                if stddev_comp:
                    cv = stddev_comp / avg_comp  # Coefficient of variation
                    assert 0.1 <= cv <= 1.0, f"Compensation distribution too {('narrow' if cv < 0.1 else 'wide')}: CV = {cv:.2f}"

    def test_contribution_rates_realistic(self):
        """Verify contribution rates within expected ranges"""
        with duckdb.connect("simulation.duckdb") as conn:
            deferral_data = conn.execute("""
                SELECT
                    ec.annual_contribution_amount / ws.total_compensation as deferral_rate,
                    COUNT(*) as employee_count
                FROM int_employee_contributions ec
                JOIN fct_workforce_snapshot ws
                    ON ec.employee_id = ws.employee_id
                    AND ec.simulation_year = ws.simulation_year
                WHERE ws.total_compensation > 0
                AND ws.employment_status = 'active'
                AND ec.simulation_year = 2025
                GROUP BY ec.annual_contribution_amount / ws.total_compensation
                ORDER BY deferral_rate
            """).fetchall()

            for rate, count in deferral_data:
                assert 0 <= rate <= 0.5, f"Unrealistic deferral rate: {rate:.2%} for {count} employees"

            # Check average deferral rate is reasonable
            avg_deferral = conn.execute("""
                SELECT AVG(ec.annual_contribution_amount / ws.total_compensation) as avg_deferral
                FROM int_employee_contributions ec
                JOIN fct_workforce_snapshot ws
                    ON ec.employee_id = ws.employee_id
                    AND ec.simulation_year = ws.simulation_year
                WHERE ws.total_compensation > 0
                AND ws.employment_status = 'active'
                AND ec.simulation_year = 2025
            """).fetchone()[0]

            if avg_deferral:
                assert 0.02 <= avg_deferral <= 0.20, f"Average deferral rate unrealistic: {avg_deferral:.2%}"

    def test_event_distribution_logic(self):
        """Verify events are distributed reasonably throughout the year"""
        with duckdb.connect("simulation.duckdb") as conn:
            # Test monthly distribution of events
            monthly_events = conn.execute("""
                SELECT
                    EXTRACT(MONTH FROM effective_date) as month,
                    COUNT(*) as event_count
                FROM fct_yearly_events
                WHERE simulation_year = 2025
                GROUP BY EXTRACT(MONTH FROM effective_date)
                ORDER BY month
            """).fetchall()

            if monthly_events:
                total_events = sum(count for _, count in monthly_events)

                # Check no month has more than 50% of all events (avoid unrealistic clustering)
                for month, count in monthly_events:
                    month_pct = count / total_events
                    assert month_pct <= 0.5, f"Month {month} has {month_pct:.2%} of events - too concentrated"

    def test_hire_termination_balance(self):
        """Verify hire/termination balance makes sense"""
        with duckdb.connect("simulation.duckdb") as conn:
            event_balance = conn.execute("""
                SELECT
                    SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) as hires,
                    SUM(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) as terminations
                FROM fct_yearly_events
                WHERE simulation_year = 2025
            """).fetchone()

            if event_balance:
                hires, terminations = event_balance

                # In growth scenarios, hires should generally exceed terminations
                # Allow some flexibility for different scenarios
                if hires > 0 and terminations > 0:
                    hire_term_ratio = hires / terminations
                    assert 0.3 <= hire_term_ratio <= 5.0, f"Hire/termination ratio unrealistic: {hire_term_ratio:.2f}"

    def test_promotion_progression_logic(self):
        """Verify promotions follow logical progression patterns"""
        with duckdb.connect("simulation.duckdb") as conn:
            # Check that promoted employees exist in workforce
            orphaned_promotions = conn.execute("""
                SELECT COUNT(*) FROM fct_yearly_events ye
                WHERE ye.event_type = 'promotion'
                AND ye.simulation_year = 2025
                AND ye.employee_id NOT IN (
                    SELECT employee_id FROM fct_workforce_snapshot
                    WHERE simulation_year = 2025
                )
            """).fetchone()[0]

            assert orphaned_promotions == 0, f"Found {orphaned_promotions} promotions for non-existent employees"

            # Check promotion events have reasonable compensation increases
            promotion_raises = conn.execute("""
                SELECT
                    ye.employee_id,
                    ye.new_compensation,
                    ye.previous_compensation,
                    (ye.new_compensation - ye.previous_compensation) / ye.previous_compensation as raise_pct
                FROM fct_yearly_events ye
                WHERE ye.event_type = 'promotion'
                AND ye.simulation_year = 2025
                AND ye.previous_compensation > 0
            """).fetchall()

            for emp_id, new_comp, prev_comp, raise_pct in promotion_raises:
                # Promotions should result in meaningful raise (2% to 50%)
                assert 0.02 <= raise_pct <= 0.50, f"Employee {emp_id} promotion raise {raise_pct:.2%} outside reasonable range"

    def test_merit_increase_logic(self):
        """Verify merit increases follow business logic"""
        with duckdb.connect("simulation.duckdb") as conn:
            merit_raises = conn.execute("""
                SELECT
                    ye.employee_id,
                    ye.new_compensation,
                    ye.previous_compensation,
                    (ye.new_compensation - ye.previous_compensation) / ye.previous_compensation as raise_pct
                FROM fct_yearly_events ye
                WHERE ye.event_type = 'RAISE'
                AND ye.simulation_year = 2025
                AND ye.previous_compensation > 0
            """).fetchall()

            for emp_id, new_comp, prev_comp, raise_pct in merit_raises:
                # Merit raises should be reasonable (0% to 15%)
                assert 0.0 <= raise_pct <= 0.15, f"Employee {emp_id} merit raise {raise_pct:.2%} outside reasonable range"

    def test_workforce_demographic_consistency(self):
        """Verify workforce demographics are consistent"""
        with duckdb.connect("simulation.duckdb") as conn:
            # Check age distribution is reasonable
            age_stats = conn.execute("""
                SELECT
                    MIN(current_age) as min_age,
                    MAX(current_age) as max_age,
                    AVG(current_age) as avg_age
                FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()

            if age_stats and age_stats[0] is not None:
                min_age, max_age, avg_age = age_stats

                assert 18 <= min_age <= 25, f"Minimum age unrealistic: {min_age}"
                assert 60 <= max_age <= 80, f"Maximum age unrealistic: {max_age}"
                assert 35 <= avg_age <= 50, f"Average age unrealistic: {avg_age}"

            # Check tenure distribution
            tenure_stats = conn.execute("""
                SELECT
                    MIN(current_tenure) as min_tenure,
                    MAX(current_tenure) as max_tenure,
                    AVG(current_tenure) as avg_tenure
                FROM fct_workforce_snapshot
                WHERE simulation_year = 2025 AND employment_status = 'active'
            """).fetchone()

            if tenure_stats and tenure_stats[0] is not None:
                min_tenure, max_tenure, avg_tenure = tenure_stats

                assert 0 <= min_tenure <= 2, f"Minimum tenure unrealistic: {min_tenure}"
                assert max_tenure <= 45, f"Maximum tenure unrealistic: {max_tenure}"
                assert 2 <= avg_tenure <= 20, f"Average tenure unrealistic: {avg_tenure}"
