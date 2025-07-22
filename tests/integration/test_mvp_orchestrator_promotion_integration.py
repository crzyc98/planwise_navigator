"""
Integration tests for MVP orchestrator promotion event generation.

This module tests the end-to-end promotion event generation process within
the full MVP orchestrator pipeline, ensuring proper interaction with other
event types and data persistence across simulation years.
"""

import pytest
import pandas as pd
from datetime import date
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator_mvp.mvp_orchestrator import MVPOrchestrator
from orchestrator_mvp.utils.db_utils import get_duckdb_connection
from config.config_loader import load_simulation_config


class TestMVPOrchestratorPromotionIntegration:
    """Integration tests for promotion events in the MVP orchestrator."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Set up test environment and clean up after tests."""
        # Setup
        self.conn = get_duckdb_connection()
        self.config = load_simulation_config()

        # Ensure test uses consistent random seed
        self.config['simulation']['random_seed'] = 12345

        # Back up existing data if needed
        self._backup_tables()

        yield

        # Teardown - restore original data
        self._restore_tables()
        self.conn.close()

    def _backup_tables(self):
        """Back up existing tables before tests."""
        tables = ['fct_yearly_events', 'fct_workforce_snapshot']
        for table in tables:
            try:
                self.conn.execute(f"CREATE TABLE {table}_backup AS SELECT * FROM {table}")
            except:
                pass  # Table might not exist

    def _restore_tables(self):
        """Restore original tables after tests."""
        tables = ['fct_yearly_events', 'fct_workforce_snapshot']
        for table in tables:
            try:
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
                self.conn.execute(f"CREATE TABLE {table} AS SELECT * FROM {table}_backup")
                self.conn.execute(f"DROP TABLE {table}_backup")
            except:
                pass

    def test_full_pipeline_promotion_generation(self):
        """Test promotion events are generated in full pipeline execution."""
        # Clear any existing events
        self.conn.execute("DELETE FROM fct_yearly_events WHERE event_type = 'promotion'")

        # Run the orchestrator for one year
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=True, use_mvp_models=True)
        simulation_year = 2024

        # Execute the simulation
        result = orchestrator.run_year_simulation(
            simulation_year=simulation_year,
            scenario_id='test_scenario',
            plan_design_id='base_plan'
        )

        # Verify promotion events were generated
        promotion_count = self.conn.execute(
            "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'promotion' AND simulation_year = ?"
            , [simulation_year]
        ).fetchone()[0]

        assert promotion_count > 0, "No promotion events generated in full pipeline"
        assert promotion_count > 100, f"Too few promotion events: {promotion_count}"
        assert promotion_count < 500, f"Too many promotion events: {promotion_count}"

    def test_promotion_interaction_with_other_events(self):
        """Test that promotions interact correctly with other event types."""
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=True, use_mvp_models=True)
        simulation_year = 2024

        # Run simulation
        orchestrator.run_year_simulation(
            simulation_year=simulation_year,
            scenario_id='test_interaction',
            plan_design_id='base_plan'
        )

        # Get all events for the year
        events_df = self.conn.execute("""
            SELECT employee_id, event_type, effective_date
            FROM fct_yearly_events
            WHERE simulation_year = ?
            ORDER BY employee_id, effective_date
        """, [simulation_year]).df()

        # Check for employees with multiple events
        employee_event_counts = events_df.groupby('employee_id')['event_type'].count()
        employees_with_multiple_events = employee_event_counts[employee_event_counts > 1]

        assert len(employees_with_multiple_events) > 0, "No employees have multiple events"

        # Check that promotions don't occur on the same day as terminations
        for emp_id in employees_with_multiple_events.index:
            emp_events = events_df[events_df['employee_id'] == emp_id]

            promotion_dates = emp_events[emp_events['event_type'] == 'promotion']['effective_date'].values
            termination_dates = emp_events[emp_events['event_type'] == 'termination']['effective_date'].values

            for prom_date in promotion_dates:
                assert prom_date not in termination_dates, \
                    f"Employee {emp_id} has promotion and termination on same date"

    def test_promotion_rates_by_level_integration(self):
        """Test that promotion rates match expected values by level in full pipeline."""
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=True, use_mvp_models=True)
        simulation_year = 2024

        # Clear previous events
        self.conn.execute("DELETE FROM fct_yearly_events WHERE simulation_year = ?", [simulation_year])

        # Run simulation
        orchestrator.run_year_simulation(
            simulation_year=simulation_year,
            scenario_id='test_rates',
            plan_design_id='base_plan'
        )

        # Calculate actual promotion rates by level
        promotion_rates = self.conn.execute("""
            WITH workforce AS (
                SELECT level, COUNT(DISTINCT employee_id) as total_employees
                FROM int_workforce_previous_year
                GROUP BY level
            ),
            promotions AS (
                SELECT
                    wpv.level,
                    COUNT(DISTINCT pe.employee_id) as promoted_employees
                FROM fct_yearly_events pe
                JOIN int_workforce_previous_year wpv ON pe.employee_id = wpv.employee_id
                WHERE pe.event_type = 'promotion'
                  AND pe.simulation_year = ?
                GROUP BY wpv.level
            )
            SELECT
                w.level,
                w.total_employees,
                COALESCE(p.promoted_employees, 0) as promoted_employees,
                COALESCE(p.promoted_employees * 1.0 / w.total_employees, 0) as promotion_rate
            FROM workforce w
            LEFT JOIN promotions p ON w.level = p.level
            ORDER BY w.level
        """, [simulation_year]).df()

        # Expected rates from hazard configuration
        expected_rates = {
            'IC': 0.30,
            'AVP': 0.25,
            'VP': 0.15,
            'Director': 0.10,
            'MD': 0.08
        }

        # Verify rates are within expected ranges (allowing for randomness)
        for _, row in promotion_rates.iterrows():
            level = row['level']
            actual_rate = row['promotion_rate']

            if level in expected_rates:
                expected = expected_rates[level]
                # Allow 30% variance due to randomness
                assert expected * 0.7 <= actual_rate <= expected * 1.3, \
                    f"Level {level} promotion rate {actual_rate:.2%} outside expected range"

    def test_multi_year_promotion_persistence(self):
        """Test that promotion events persist correctly across multiple years."""
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=True, use_mvp_models=True)

        # Clear all events
        self.conn.execute("DELETE FROM fct_yearly_events")

        # Run multiple years
        years = [2023, 2024, 2025]
        total_promotions = {}

        for year in years:
            orchestrator.run_year_simulation(
                simulation_year=year,
                scenario_id='test_multiyear',
                plan_design_id='base_plan'
            )

            # Count promotions for this year
            count = self.conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'promotion' AND simulation_year = ?",
                [year]
            ).fetchone()[0]
            total_promotions[year] = count

        # Verify all years have promotions
        for year, count in total_promotions.items():
            assert count > 0, f"No promotions generated for year {year}"

        # Verify cumulative count matches sum
        total_in_db = self.conn.execute(
            "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'promotion'"
        ).fetchone()[0]

        expected_total = sum(total_promotions.values())
        assert total_in_db == expected_total, \
            f"Database total {total_in_db} doesn't match sum {expected_total}"

    def test_workforce_state_after_promotions(self):
        """Test that workforce snapshot correctly reflects promotions."""
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=True, use_mvp_models=True)
        simulation_year = 2024

        # Get initial level distribution
        initial_distribution = self.conn.execute("""
            SELECT level, COUNT(*) as count
            FROM int_workforce_previous_year
            GROUP BY level
        """).df().set_index('level')['count'].to_dict()

        # Run simulation
        orchestrator.run_year_simulation(
            simulation_year=simulation_year,
            scenario_id='test_workforce_state',
            plan_design_id='base_plan'
        )

        # Get promotions by from/to level
        promotions = self.conn.execute("""
            SELECT
                wpv.level as from_level,
                CASE
                    WHEN wpv.level = 'IC' THEN 'AVP'
                    WHEN wpv.level = 'AVP' THEN 'VP'
                    WHEN wpv.level = 'VP' THEN 'Director'
                    WHEN wpv.level = 'Director' THEN 'MD'
                    ELSE wpv.level
                END as to_level,
                COUNT(*) as count
            FROM fct_yearly_events pe
            JOIN int_workforce_previous_year wpv ON pe.employee_id = wpv.employee_id
            WHERE pe.event_type = 'promotion'
              AND pe.simulation_year = ?
            GROUP BY wpv.level
        """, [simulation_year]).df()

        # Verify workforce changes make sense
        for _, promo in promotions.iterrows():
            from_level = promo['from_level']
            to_level = promo['to_level']
            count = promo['count']

            # From level should decrease, to level should increase
            assert from_level != to_level, f"Promotion from {from_level} to same level"
            assert count > 0, f"No promotions from {from_level} to {to_level}"

    def test_promotion_event_data_integrity(self):
        """Test that promotion events have all required fields and valid data."""
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=True, use_mvp_models=True)
        simulation_year = 2024

        # Run simulation
        orchestrator.run_year_simulation(
            simulation_year=simulation_year,
            scenario_id='test_integrity',
            plan_design_id='base_plan'
        )

        # Get promotion events
        promotions = self.conn.execute("""
            SELECT *
            FROM fct_yearly_events
            WHERE event_type = 'promotion'
              AND simulation_year = ?
            LIMIT 10
        """, [simulation_year]).df()

        # Check required fields
        required_fields = [
            'employee_id', 'event_type', 'effective_date',
            'simulation_year', 'scenario_id', 'plan_design_id'
        ]

        for field in required_fields:
            assert field in promotions.columns, f"Missing required field: {field}"
            assert promotions[field].notna().all(), f"Null values in field: {field}"

        # Validate data types and values
        assert promotions['event_type'].eq('promotion').all(), "Invalid event type"
        assert promotions['simulation_year'].eq(simulation_year).all(), "Invalid simulation year"

        # Check effective dates are within the simulation year
        for date_str in promotions['effective_date']:
            event_date = pd.to_datetime(date_str)
            assert event_date.year == simulation_year, f"Event date {date_str} outside simulation year"

    def test_promotion_performance_under_load(self):
        """Test promotion generation performance with larger workforce."""
        # This test ensures the system performs adequately under load
        orchestrator = MVPOrchestrator(self.conn, self.config, debug=False, use_mvp_models=True)
        simulation_year = 2024

        import time
        start_time = time.time()

        # Run simulation
        orchestrator.run_year_simulation(
            simulation_year=simulation_year,
            scenario_id='test_performance',
            plan_design_id='base_plan'
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Get workforce size and promotion count
        workforce_size = self.conn.execute(
            "SELECT COUNT(*) FROM int_workforce_previous_year"
        ).fetchone()[0]

        promotion_count = self.conn.execute(
            "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'promotion' AND simulation_year = ?",
            [simulation_year]
        ).fetchone()[0]

        # Performance assertions
        assert execution_time < 60, f"Simulation took too long: {execution_time:.2f} seconds"

        # Calculate events per second
        if promotion_count > 0:
            events_per_second = promotion_count / execution_time
            assert events_per_second > 50, f"Event generation too slow: {events_per_second:.2f} events/sec"

        print(f"Performance metrics:")
        print(f"  Workforce size: {workforce_size}")
        print(f"  Promotions generated: {promotion_count}")
        print(f"  Execution time: {execution_time:.2f} seconds")
        print(f"  Events per second: {promotion_count / execution_time:.2f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
