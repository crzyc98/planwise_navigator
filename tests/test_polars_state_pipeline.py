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
import logging
from pathlib import Path
from datetime import date, datetime
from planalign_orchestrator.polars_state_pipeline import (
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
    """Test EnrollmentStateBuilder (S076-02)."""

    @pytest.fixture
    def enrollment_builder(self):
        """Create EnrollmentStateBuilder for testing."""
        logger = logging.getLogger(__name__)
        return EnrollmentStateBuilder(logger)

    @pytest.fixture
    def sample_baseline(self):
        """Sample baseline workforce data."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002', 'EMP003'],
            'employee_enrollment_date': [date(2020, 3, 1), None, date(2021, 4, 1)],
            'employee_gross_compensation': [100000.0, 85000.0, 95000.0],
            'employee_birth_date': [date(1990, 1, 1), date(1985, 6, 15), date(1992, 3, 20)]
        })

    @pytest.fixture
    def sample_events(self):
        """Sample enrollment events."""
        return pl.DataFrame({
            'employee_id': ['EMP002', 'EMP003'],
            'event_type': ['enrollment', 'enrollment_change'],
            'simulation_year': [2025, 2025],
            'effective_date': [date(2025, 4, 1), date(2025, 6, 15)],
            'event_details': ['Auto enrollment', 'Opted out'],
            'event_category': ['auto_enrollment', 'opt_out'],
            'employee_deferral_rate': [0.06, 0.0]
        })

    def test_builder_exists(self):
        """Test that builder class exists."""
        assert EnrollmentStateBuilder is not None

    def test_year1_state_building(self, enrollment_builder, sample_baseline, sample_events):
        """Test building Year 1 enrollment state."""
        result = enrollment_builder.build(
            simulation_year=2025,
            events_df=sample_events,
            baseline_df=sample_baseline,
            previous_state_df=None
        )

        assert result is not None
        assert 'employee_id' in result.columns
        assert 'enrollment_status' in result.columns
        assert result.height == 3  # All baseline employees

    def test_handles_empty_events(self, enrollment_builder, sample_baseline):
        """Test handling of empty events DataFrame."""
        empty_events = pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'simulation_year': [],
            'effective_date': [],
            'event_details': [],
            'event_category': [],
            'employee_deferral_rate': []
        }).cast({
            'employee_id': pl.Utf8,
            'effective_date': pl.Date,
            'simulation_year': pl.Int64,
            'employee_deferral_rate': pl.Float64
        })

        result = enrollment_builder.build(
            simulation_year=2025,
            events_df=empty_events,
            baseline_df=sample_baseline,
            previous_state_df=None
        )

        assert result is not None
        assert result.height == 3


class TestDeferralRateBuilder:
    """Test DeferralRateBuilder (S076-02)."""

    @pytest.fixture
    def deferral_builder(self):
        """Create DeferralRateBuilder for testing."""
        logger = logging.getLogger(__name__)
        return DeferralRateBuilder(logger)

    @pytest.fixture
    def sample_enrollment_state(self):
        """Sample enrollment state."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'enrollment_status': [True, True],
            'enrollment_date': [date(2020, 3, 1), date(2025, 4, 1)]
        })

    @pytest.fixture
    def sample_baseline(self):
        """Sample baseline workforce data."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002', 'EMP003'],
            'employee_gross_compensation': [100000.0, 85000.0, 95000.0],
            'employee_birth_date': [date(1990, 1, 1), date(1985, 6, 15), date(1992, 3, 20)]
        })

    @pytest.fixture
    def sample_events(self):
        """Sample deferral events."""
        return pl.DataFrame({
            'employee_id': ['EMP001'],
            'event_type': ['enrollment'],
            'simulation_year': [2025],
            'effective_date': [date(2025, 3, 1)],
            'event_details': ['Enrolled'],
            'event_category': ['auto_enrollment'],
            'employee_deferral_rate': [0.06]
        })

    def test_builder_exists(self):
        """Test that builder class exists."""
        assert DeferralRateBuilder is not None

    def test_year1_deferral_building(
        self, deferral_builder, sample_enrollment_state, sample_baseline, sample_events
    ):
        """Test building Year 1 deferral state."""
        result = deferral_builder.build(
            simulation_year=2025,
            events_df=sample_events,
            enrollment_state_df=sample_enrollment_state,
            baseline_df=sample_baseline,
            previous_state_df=None
        )

        assert result is not None
        assert 'employee_id' in result.columns
        assert 'current_deferral_rate' in result.columns


class TestContributionsCalculator:
    """Test ContributionsCalculator (S076-03)."""

    @pytest.fixture
    def contributions_calculator(self):
        """Create ContributionsCalculator for testing."""
        logger = logging.getLogger(__name__)
        return ContributionsCalculator(logger)

    @pytest.fixture
    def sample_enrollment_state(self):
        """Sample enrollment state."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'enrollment_status': [True, True],
            'enrollment_date': [date(2020, 3, 1), date(2025, 4, 1)]
        })

    @pytest.fixture
    def sample_deferral_state(self):
        """Sample deferral rate state."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'current_deferral_rate': [0.06, 0.04],
            'simulation_year': [2025, 2025]
        })

    @pytest.fixture
    def sample_baseline(self):
        """Sample baseline workforce data."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'employee_gross_compensation': [100000.0, 85000.0],
            'employee_birth_date': [date(1970, 1, 1), date(1995, 6, 15)],  # EMP001 is 55+ for catch-up
            'employee_hire_date': [date(2020, 1, 1), date(2023, 6, 1)]
        })

    @pytest.fixture
    def sample_events(self):
        """Sample events."""
        return pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'simulation_year': [],
            'effective_date': [],
            'compensation_amount': []
        }).cast({
            'employee_id': pl.Utf8,
            'event_type': pl.Utf8,
            'simulation_year': pl.Int64,
            'effective_date': pl.Date,
            'compensation_amount': pl.Float64
        })

    def test_calculator_exists(self):
        """Test that calculator class exists."""
        assert ContributionsCalculator is not None

    def test_contributions_calculation(
        self, contributions_calculator, sample_enrollment_state, sample_deferral_state,
        sample_baseline, sample_events
    ):
        """Test contribution calculations."""
        result = contributions_calculator.calculate(
            simulation_year=2025,
            enrollment_state_df=sample_enrollment_state,
            deferral_state_df=sample_deferral_state,
            baseline_df=sample_baseline,
            events_df=sample_events
        )

        assert result is not None
        assert 'employee_id' in result.columns
        assert 'annual_contribution_amount' in result.columns
        assert 'employer_match_amount' in result.columns

    def test_irs_limit_enforcement(
        self, contributions_calculator, sample_baseline, sample_events
    ):
        """Test IRS limit is enforced."""
        # Employee with high salary and high deferral rate to trigger limit
        enrollment_state = pl.DataFrame({
            'employee_id': ['HIGH_EARNER'],
            'enrollment_status': [True],
            'enrollment_date': [date(2020, 1, 1)]
        })
        deferral_state = pl.DataFrame({
            'employee_id': ['HIGH_EARNER'],
            'current_deferral_rate': [0.50],  # 50% deferral - will hit IRS limit
            'simulation_year': [2025]
        })
        baseline = pl.DataFrame({
            'employee_id': ['HIGH_EARNER'],
            'employee_gross_compensation': [500000.0],  # $500K salary
            'employee_birth_date': [date(1995, 1, 1)],  # Under 50
            'employee_hire_date': [date(2020, 1, 1)]
        })

        result = contributions_calculator.calculate(
            simulation_year=2025,
            enrollment_state_df=enrollment_state,
            deferral_state_df=deferral_state,
            baseline_df=baseline,
            events_df=sample_events
        )

        # IRS limit for 2025 under 50 is $23,500
        assert result.filter(pl.col('employee_id') == 'HIGH_EARNER')['annual_contribution_amount'][0] <= 23500
        assert result.filter(pl.col('employee_id') == 'HIGH_EARNER')['irs_limit_applied'][0] == True

    def test_match_formula_simple(self):
        """Test simple match formula."""
        logger = logging.getLogger(__name__)
        calc = ContributionsCalculator(logger, match_formula='simple_match')
        assert calc.match_formula == 'simple_match'

    def test_match_formula_tiered(self):
        """Test tiered match formula."""
        logger = logging.getLogger(__name__)
        calc = ContributionsCalculator(logger, match_formula='tiered_match')
        assert calc.match_formula == 'tiered_match'


class TestSnapshotBuilder:
    """Test SnapshotBuilder (S076-04)."""

    @pytest.fixture
    def snapshot_builder(self):
        """Create SnapshotBuilder for testing."""
        logger = logging.getLogger(__name__)
        return SnapshotBuilder(logger)

    @pytest.fixture
    def sample_baseline(self):
        """Sample baseline workforce data."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'employee_ssn': ['SSN001', 'SSN002'],
            'employee_birth_date': [date(1990, 1, 1), date(1985, 6, 15)],
            'employee_hire_date': [date(2020, 1, 1), date(2019, 5, 15)],
            'employee_gross_compensation': [100000.0, 85000.0],
            'employee_deferral_rate': [0.06, 0.04],
            'employee_enrollment_date': [date(2020, 3, 1), None],
            'active': [True, True]
        })

    @pytest.fixture
    def sample_events(self):
        """Sample events."""
        return pl.DataFrame({
            'employee_id': [],
            'event_type': [],
            'simulation_year': [],
            'effective_date': [],
            'event_details': [],
            'compensation_amount': [],
            'employee_age': [],
            'level_id': []
        }).cast({
            'employee_id': pl.Utf8,
            'event_type': pl.Utf8,
            'simulation_year': pl.Int64,
            'effective_date': pl.Date,
            'event_details': pl.Utf8,
            'compensation_amount': pl.Float64,
            'employee_age': pl.Int64,
            'level_id': pl.Int64
        })

    @pytest.fixture
    def sample_enrollment_state(self):
        """Sample enrollment state."""
        return pl.DataFrame({
            'employee_id': ['EMP001', 'EMP002'],
            'enrollment_date': [date(2020, 3, 1), None],
            'enrollment_status': [True, False],
            'enrollment_method': ['voluntary', None],
            'ever_opted_out': [False, False]
        })

    @pytest.fixture
    def sample_deferral_state(self):
        """Sample deferral state."""
        return pl.DataFrame({
            'employee_id': ['EMP001'],
            'current_deferral_rate': [0.06],
            'escalation_count': [0],
            'had_escalation_this_year': [False]
        })

    @pytest.fixture
    def sample_contributions(self):
        """Sample contributions."""
        return pl.DataFrame({
            'employee_id': ['EMP001'],
            'annual_contribution_amount': [6000.0],
            'prorated_annual_compensation': [100000.0],
            'employer_match_amount': [1500.0],
            'irs_limit_applied': [False],
            'contribution_quality_flag': ['NORMAL']
        })

    def test_builder_exists(self):
        """Test that builder class exists."""
        assert SnapshotBuilder is not None

    def test_snapshot_building(
        self, snapshot_builder, sample_baseline, sample_events,
        sample_enrollment_state, sample_deferral_state, sample_contributions
    ):
        """Test building workforce snapshot."""
        result = snapshot_builder.build(
            simulation_year=2025,
            baseline_df=sample_baseline,
            events_df=sample_events,
            enrollment_state_df=sample_enrollment_state,
            deferral_state_df=sample_deferral_state,
            contributions_df=sample_contributions
        )

        assert result is not None
        assert 'employee_id' in result.columns
        assert 'employment_status' in result.columns
        assert 'detailed_status_code' in result.columns
        assert 'age_band' in result.columns
        assert 'tenure_band' in result.columns
        assert result.height == 2  # Both baseline employees

    def test_age_band_calculation(self, snapshot_builder, sample_baseline, sample_events,
                                   sample_enrollment_state, sample_deferral_state, sample_contributions):
        """Test age band calculation."""
        result = snapshot_builder.build(
            simulation_year=2025,
            baseline_df=sample_baseline,
            events_df=sample_events,
            enrollment_state_df=sample_enrollment_state,
            deferral_state_df=sample_deferral_state,
            contributions_df=sample_contributions
        )

        # EMP001 born 1990 should be 35 in 2025 -> 35-44 band
        emp001_band = result.filter(pl.col('employee_id') == 'EMP001')['age_band'][0]
        assert emp001_band == '35-44'

    def test_status_classification(self, snapshot_builder, sample_baseline,
                                    sample_enrollment_state, sample_deferral_state, sample_contributions):
        """Test detailed status code classification."""
        # Create events with a termination
        events_with_termination = pl.DataFrame({
            'employee_id': ['EMP002'],
            'event_type': ['termination'],
            'simulation_year': [2025],
            'effective_date': [date(2025, 6, 30)],
            'event_details': ['Voluntary resignation'],
            'compensation_amount': [None],
            'employee_age': [None],
            'level_id': [None]
        }).cast({
            'compensation_amount': pl.Float64,
            'employee_age': pl.Int64,
            'level_id': pl.Int64
        })

        result = snapshot_builder.build(
            simulation_year=2025,
            baseline_df=sample_baseline,
            events_df=events_with_termination,
            enrollment_state_df=sample_enrollment_state,
            deferral_state_df=sample_deferral_state,
            contributions_df=sample_contributions
        )

        # EMP001 should be continuous_active, EMP002 should be experienced_termination
        emp001_status = result.filter(pl.col('employee_id') == 'EMP001')['detailed_status_code'][0]
        emp002_status = result.filter(pl.col('employee_id') == 'EMP002')['detailed_status_code'][0]

        assert emp001_status == 'continuous_active'
        assert emp002_status == 'experienced_termination'


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


@pytest.mark.integration
class TestYearExecutorPolarsIntegration:
    """Test E076 Polars state accumulation integration with YearExecutor."""

    @pytest.fixture
    def mock_config_with_polars(self):
        """Create a mock SimulationConfig with Polars state accumulation enabled."""
        from unittest.mock import MagicMock

        config = MagicMock()
        config.simulation.start_year = 2025
        config.simulation.end_year = 2025

        # Enable Polars state accumulation
        polars_settings = MagicMock()
        polars_settings.state_accumulation_enabled = True
        polars_settings.state_accumulation_fallback_on_error = True
        polars_settings.state_accumulation_validate_results = False
        polars_settings.output_path = "data/parquet/events"

        config.get_polars_settings.return_value = polars_settings
        config.is_polars_mode_enabled.return_value = True
        config.is_polars_state_accumulation_enabled.return_value = True
        config.get_polars_state_accumulation_settings.return_value = {
            "enabled": True,
            "fallback_on_error": True,
            "validate_results": False
        }

        return config

    @pytest.fixture
    def mock_config_without_polars(self):
        """Create a mock SimulationConfig with Polars state accumulation disabled."""
        from unittest.mock import MagicMock

        config = MagicMock()
        config.simulation.start_year = 2025
        config.simulation.end_year = 2025

        # Disable Polars state accumulation
        polars_settings = MagicMock()
        polars_settings.state_accumulation_enabled = False
        polars_settings.state_accumulation_fallback_on_error = True

        config.get_polars_settings.return_value = polars_settings
        config.is_polars_mode_enabled.return_value = False
        config.is_polars_state_accumulation_enabled.return_value = False
        config.get_polars_state_accumulation_settings.return_value = {
            "enabled": False,
            "fallback_on_error": True,
            "validate_results": False
        }

        return config

    def test_should_use_polars_when_enabled(self, mock_config_with_polars):
        """Test that Polars state accumulation is used when enabled."""
        from unittest.mock import MagicMock
        from planalign_orchestrator.pipeline.year_executor import (
            YearExecutor,
            POLARS_STATE_PIPELINE_AVAILABLE
        )

        if not POLARS_STATE_PIPELINE_AVAILABLE:
            pytest.skip("Polars state pipeline not available")

        # Create mock dependencies
        dbt_runner = MagicMock()
        db_manager = MagicMock()

        executor = YearExecutor(
            config=mock_config_with_polars,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline", "plan_design_id": "standard_401k"},
            dbt_threads=1,
            verbose=True
        )

        # Test the check method
        assert executor._should_use_polars_state_accumulation() is True

    def test_should_not_use_polars_when_disabled(self, mock_config_without_polars):
        """Test that dbt is used when Polars state accumulation is disabled."""
        from unittest.mock import MagicMock
        from planalign_orchestrator.pipeline.year_executor import YearExecutor

        # Create mock dependencies
        dbt_runner = MagicMock()
        db_manager = MagicMock()

        executor = YearExecutor(
            config=mock_config_without_polars,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            verbose=False
        )

        # Test the check method
        assert executor._should_use_polars_state_accumulation() is False

    def test_fallback_to_dbt_on_polars_error(self, mock_config_with_polars, tmp_path):
        """Test that execution falls back to dbt when Polars fails."""
        from unittest.mock import MagicMock, patch
        from planalign_orchestrator.pipeline.year_executor import (
            YearExecutor,
            POLARS_STATE_PIPELINE_AVAILABLE
        )
        from planalign_orchestrator.pipeline.workflow import StageDefinition, WorkflowStage

        if not POLARS_STATE_PIPELINE_AVAILABLE:
            pytest.skip("Polars state pipeline not available")

        # Create mock dependencies
        dbt_runner = MagicMock()
        dbt_result = MagicMock()
        dbt_result.success = True
        dbt_result.return_code = 0
        dbt_runner.execute_command.return_value = dbt_result

        db_manager = MagicMock()

        executor = YearExecutor(
            config=mock_config_with_polars,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline", "plan_design_id": "standard_401k"},
            dbt_threads=1,
            verbose=True
        )

        # Create STATE_ACCUMULATION stage definition
        stage = StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=["int_enrollment_state_accumulator", "fct_workforce_snapshot"],
            validation_rules=[]
        )

        # Mock StateAccumulatorEngine to raise an error
        with patch('planalign_orchestrator.pipeline.year_executor.StateAccumulatorEngine') as mock_engine_class:
            mock_engine_class.side_effect = Exception("Simulated Polars failure")

            # Execute should fall back to dbt
            result = executor.execute_workflow_stage(stage, year=2025)

            # Verify fallback occurred - dbt_runner should have been called
            assert result["success"] is True
            assert dbt_runner.execute_command.called

    def test_config_settings_propagation(self):
        """Test that config settings properly enable/disable state accumulation."""
        from planalign_orchestrator.config import PolarsEventSettings

        # Test default (disabled)
        settings = PolarsEventSettings()
        assert settings.state_accumulation_enabled is False
        assert settings.state_accumulation_fallback_on_error is True
        assert settings.state_accumulation_validate_results is False

        # Test enabled
        settings_enabled = PolarsEventSettings(state_accumulation_enabled=True)
        assert settings_enabled.state_accumulation_enabled is True
