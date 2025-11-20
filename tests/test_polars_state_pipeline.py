#!/usr/bin/env python3
"""
Unit tests for E076 Polars State Accumulation Pipeline

Tests cover:
- StateAccumulatorEngine initialization and configuration
- Event loading from Parquet and DuckDB
- Baseline workforce loading
- State building orchestration
- Performance benchmarking
- Schema validation against dbt output
"""

import pytest
import polars as pl
import duckdb
from pathlib import Path
from datetime import date, datetime
from navigator_orchestrator.polars_state_pipeline import (
    StateAccumulatorEngine,
    StateAccumulatorConfig,
    EnrollmentStateBuilder,
    DeferralRateBuilder,
    ContributionsCalculator,
    SnapshotBuilder
)


class TestStateAccumulatorConfig:
    """Test StateAccumulatorConfig dataclass."""

    def test_valid_config(self):
        """Test creating valid configuration."""
        config = StateAccumulatorConfig(
            simulation_year=2025,
            scenario_id="test_scenario",
            plan_design_id="test_plan"
        )
        assert config.simulation_year == 2025
        assert config.scenario_id == "test_scenario"
        assert config.plan_design_id == "test_plan"
        assert config.enable_validation is True
        assert config.lazy_evaluation is True

    def test_invalid_year(self):
        """Test that invalid simulation year raises error."""
        with pytest.raises(ValueError, match="simulation_year must be >= 2025"):
            StateAccumulatorConfig(simulation_year=2020)


class TestStateAccumulatorEngine:
    """Test StateAccumulatorEngine core functionality."""

    @pytest.fixture
    def minimal_config(self):
        """Minimal configuration for testing."""
        return StateAccumulatorConfig(
            simulation_year=2025,
            scenario_id="baseline",
            plan_design_id="standard_401k"
        )

    @pytest.fixture
    def in_memory_db(self, tmp_path):
        """Create in-memory database with test data."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        # Create test tables
        conn.execute("""
            CREATE TABLE stg_census_data (
                employee_id VARCHAR,
                employee_ssn VARCHAR,
                employee_birth_date DATE,
                employee_hire_date DATE,
                employee_gross_compensation DOUBLE,
                employee_deferral_rate DOUBLE,
                current_eligibility_status VARCHAR,
                employee_enrollment_date DATE,
                active BOOLEAN
            )
        """)

        # Insert test data
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN-001', '1990-01-01', '2020-01-01', 100000.0, 0.06, 'eligible', '2020-03-01', true),
                ('EMP002', 'SSN-002', '1985-06-15', '2019-05-15', 85000.0, 0.04, 'eligible', NULL, true),
                ('EMP003', 'SSN-003', '1992-03-20', '2021-02-10', 95000.0, 0.05, 'eligible', '2021-04-01', true)
        """)

        # Create yearly events table
        conn.execute("""
            CREATE TABLE fct_yearly_events (
                employee_id VARCHAR,
                event_type VARCHAR,
                simulation_year INTEGER,
                scenario_id VARCHAR,
                plan_design_id VARCHAR,
                effective_date DATE,
                event_details VARCHAR,
                event_category VARCHAR,
                compensation_amount DOUBLE,
                employee_deferral_rate DOUBLE
            )
        """)

        conn.close()
        return db_path

    def test_engine_initialization(self, minimal_config, in_memory_db):
        """Test engine initializes correctly."""
        minimal_config.database_path = in_memory_db
        engine = StateAccumulatorEngine(minimal_config)

        assert engine.config.simulation_year == 2025
        assert engine.db_path == in_memory_db
        assert 'total_processing_time' in engine.stats
        assert engine.stats['employees_processed'] == 0

    def test_load_baseline_workforce_year1(self, minimal_config, in_memory_db):
        """Test loading baseline workforce for Year 1."""
        minimal_config.database_path = in_memory_db
        engine = StateAccumulatorEngine(minimal_config)

        baseline_df = engine._load_baseline_workforce()

        assert baseline_df.height == 3  # 3 active employees
        assert 'employee_id' in baseline_df.columns
        assert 'employee_gross_compensation' in baseline_df.columns
        assert engine.stats['employees_processed'] == 3

    def test_load_events_from_duckdb(self, minimal_config, in_memory_db):
        """Test loading events from DuckDB."""
        # Add test events
        conn = duckdb.connect(str(in_memory_db))
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
                ('EMP001', 'hire', 2025, 'baseline', 'standard_401k', '2025-01-15', 'New hire', 'hiring', 100000.0, NULL),
                ('EMP002', 'enrollment', 2025, 'baseline', 'standard_401k', '2025-04-01', 'Enrolled', 'benefits', NULL, 0.06)
        """)
        conn.close()

        minimal_config.database_path = in_memory_db
        engine = StateAccumulatorEngine(minimal_config)

        events_df = engine._load_events()

        assert events_df.height == 2
        assert 'event_type' in events_df.columns
        assert engine.stats['events_processed'] == 2

    def test_build_state_orchestration(self, minimal_config, in_memory_db):
        """Test state building orchestration."""
        minimal_config.database_path = in_memory_db
        engine = StateAccumulatorEngine(minimal_config)

        # Add test events
        conn = duckdb.connect(str(in_memory_db))
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
                ('EMP001', 'merit', 2025, 'baseline', 'standard_401k', '2025-03-15', 'Merit raise', 'compensation', 104000.0, NULL)
        """)
        conn.close()

        state_data = engine.build_state()

        # Verify state data structure
        assert 'events' in state_data
        assert 'baseline' in state_data
        assert state_data['events'].height == 1
        assert state_data['baseline'].height == 3
        assert engine.stats['total_processing_time'] > 0

    def test_load_events_file_not_found(self, minimal_config, tmp_path):
        """Test error handling when database doesn't exist."""
        minimal_config.database_path = tmp_path / "nonexistent.duckdb"
        engine = StateAccumulatorEngine(minimal_config)

        with pytest.raises(FileNotFoundError):
            engine._load_events()


class TestEnrollmentStateBuilder:
    """Test EnrollmentStateBuilder (placeholder for S076-02)."""

    def test_builder_exists(self):
        """Test that builder class exists."""
        assert EnrollmentStateBuilder is not None
        # TODO: Add tests when S076-02 is implemented


class TestDeferralRateBuilder:
    """Test DeferralRateBuilder (placeholder for S076-02)."""

    def test_builder_exists(self):
        """Test that builder class exists."""
        assert DeferralRateBuilder is not None
        # TODO: Add tests when S076-02 is implemented


class TestContributionsCalculator:
    """Test ContributionsCalculator (placeholder for S076-03)."""

    def test_calculator_exists(self):
        """Test that calculator class exists."""
        assert ContributionsCalculator is not None
        # TODO: Add tests when S076-03 is implemented


class TestSnapshotBuilder:
    """Test SnapshotBuilder (placeholder for S076-04)."""

    def test_builder_exists(self):
        """Test that builder class exists."""
        assert SnapshotBuilder is not None
        # TODO: Add tests when S076-04 is implemented


@pytest.mark.integration
class TestStateAccumulatorPerformance:
    """Performance benchmarking tests."""

    @pytest.fixture
    def large_dataset(self, tmp_path):
        """Create larger dataset for performance testing."""
        db_path = tmp_path / "perf_test.duckdb"
        conn = duckdb.connect(str(db_path))

        # Create tables
        conn.execute("""
            CREATE TABLE stg_census_data (
                employee_id VARCHAR,
                employee_ssn VARCHAR,
                employee_birth_date DATE,
                employee_hire_date DATE,
                employee_gross_compensation DOUBLE,
                employee_deferral_rate DOUBLE,
                current_eligibility_status VARCHAR,
                employee_enrollment_date DATE,
                active BOOLEAN
            )
        """)

        conn.execute("""
            CREATE TABLE fct_yearly_events (
                employee_id VARCHAR,
                event_type VARCHAR,
                simulation_year INTEGER,
                scenario_id VARCHAR,
                plan_design_id VARCHAR,
                effective_date DATE,
                event_details VARCHAR,
                event_category VARCHAR,
                compensation_amount DOUBLE,
                employee_deferral_rate DOUBLE
            )
        """)

        # Generate 1000 employees
        employees = []
        for i in range(1000):
            emp_id = f"EMP{i:06d}"
            employees.append((
                emp_id,
                f"SSN-{i:09d}",
                date(1980 + (i % 20), 1 + (i % 12), 1),
                date(2020 + (i % 5), 1, 1),
                50000.0 + (i * 100),
                0.04 + (i % 10) * 0.01,
                'eligible',
                date(2020 + (i % 5), 3, 1) if i % 2 == 0 else None,
                True
            ))

        conn.executemany(
            "INSERT INTO stg_census_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            employees
        )

        # Generate 500 events
        events = []
        for i in range(500):
            emp_id = f"EMP{i:06d}"
            events.append((
                emp_id,
                ['merit', 'promotion', 'enrollment'][i % 3],
                2025,
                'baseline',
                'standard_401k',
                date(2025, 3, 15),
                f"Event {i}",
                'compensation' if i % 3 < 2 else 'benefits',
                50000.0 + (i * 100) if i % 3 < 2 else None,
                0.06 if i % 3 == 2 else None
            ))

        conn.executemany(
            "INSERT INTO fct_yearly_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            events
        )

        conn.close()
        return db_path

    def test_performance_1k_employees(self, large_dataset):
        """Test performance with 1000 employees."""
        config = StateAccumulatorConfig(
            simulation_year=2025,
            scenario_id='baseline',  # Match test data
            plan_design_id='standard_401k',  # Match test data
            database_path=large_dataset,
            enable_profiling=True
        )

        engine = StateAccumulatorEngine(config)
        state_data = engine.build_state()

        # Performance targets from E076 spec
        assert engine.stats['total_processing_time'] < 5.0  # <5s target
        assert engine.stats['employees_processed'] == 1000
        assert engine.stats['events_processed'] == 500

        print(f"\n✅ Performance Test: {engine.stats['total_processing_time']:.2f}s for 1K employees")


@pytest.mark.integration
class TestSchemaValidation:
    """Test schema compatibility with dbt output."""

    def test_events_schema_matches_dbt(self, tmp_path):
        """Test that events schema matches fct_yearly_events."""
        # TODO: Implement schema validation in S076-05
        pass

    def test_snapshot_schema_matches_dbt(self, tmp_path):
        """Test that snapshot schema matches fct_workforce_snapshot."""
        # TODO: Implement schema validation in S076-05
        pass
