#!/usr/bin/env python3
"""
E068G Polars Bulk Event Factory - Maximum Performance Event Generation

High-performance alternative to SQL-based event generation using Polars
for vectorized operations. Achieves ≤60s total runtime for 5k×5 years.

This module provides:
- PolarsDeterministicRNG: Hash-based RNG matching dbt macro logic
- PolarsEventGenerator: Vectorized event generation for all event types
- EventFactoryConfig: Configuration management
- CLI interface for standalone execution
- Comprehensive logging and performance monitoring

Event generation matches existing SQL logic in dbt models while providing
significant performance improvements through vectorized operations.
"""

import os
import sys
import json
import time
import hashlib
import logging
import argparse
import numpy as np
import polars as pl
import duckdb
from pathlib import Path
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union

# Set Polars to use maximum threads for performance
os.environ.setdefault('POLARS_MAX_THREADS', '16')

# Import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from planalign_orchestrator.config import load_simulation_config, get_database_path

# Module-level logger
logger = logging.getLogger(__name__)


@dataclass
class EventFactoryConfig:
    """Configuration for Polars event factory."""
    start_year: int
    end_year: int
    output_path: Path
    scenario_id: str = "default"
    plan_design_id: str = "default"
    random_seed: int = 12345
    batch_size: int = 10000  # Process employees in batches
    enable_profiling: bool = False
    enable_compression: bool = True
    compression_level: int = 6  # zstd compression level
    max_memory_gb: float = 8.0  # Memory limit

    # Performance optimization settings
    lazy_evaluation: bool = True
    streaming: bool = True
    parallel_io: bool = True

    # Database path (for batch mode scenario isolation)
    database_path: Optional[Path] = None  # If None, uses get_database_path()

    # Compensation settings
    promotion_rate_multiplier: float = 1.0  # Multiplier for base promotion rates (1.0 = seed defaults)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.start_year > self.end_year:
            raise ValueError(f"start_year ({self.start_year}) must be <= end_year ({self.end_year})")

        if self.batch_size < 1:
            raise ValueError(f"batch_size must be > 0, got {self.batch_size}")

        if not isinstance(self.output_path, Path):
            self.output_path = Path(self.output_path)


class PolarsDeterministicRNG:
    """
    Deterministic RNG using same hash logic as dbt macros.

    Ensures identical results to SQL-based event generation when using
    the same random seed. Uses MD5 hash for consistency with existing
    dbt macro implementation.
    """

    def __init__(self, random_seed: int = 12345):
        """Initialize RNG with global seed."""
        self.random_seed = random_seed

    def hash_rng(self, employee_id: str, simulation_year: int, event_type: str, salt: str = '') -> float:
        """
        Generate deterministic random number - matches dbt hash_rng macro.

        Creates hash key identical to dbt macro logic:
        CONCAT(random_seed, '|', employee_id, '|', simulation_year, '|', event_type[, '|', salt])

        Args:
            employee_id: Employee identifier
            simulation_year: Year of simulation
            event_type: Type of event (hire, termination, promotion, etc.)
            salt: Additional salt for event-specific randomness

        Returns:
            Uniform random number between 0.0 and 1.0
        """
        # Build hash key exactly matching dbt macro
        hash_key = f"{self.random_seed}|{employee_id}|{simulation_year}|{event_type}"
        if salt:
            hash_key += f"|{salt}"

        # Use MD5 hash like dbt macro, then normalize to [0, 1)
        hash_value = hashlib.md5(hash_key.encode()).hexdigest()
        # Take first 8 characters and convert to integer
        hash_int = int(hash_value[:8], 16)
        # Use same prime normalization as dbt macro
        return (hash_int % 2147483647) / 2147483647.0

    def add_rng_columns_vectorized(self, df: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """
        Add all RNG columns at once using vectorized operations.

        More efficient than map_elements for large datasets. Pre-computes
        all hash values needed for event generation in a single pass.
        """
        # Get unique employee IDs to minimize hash computations
        employee_ids = df['employee_id'].unique().sort()

        # Pre-compute hash values for all employees and event types
        rng_data = []
        event_types = ['hire', 'termination', 'promotion', 'merit', 'enrollment', 'deferral']

        for emp_id in employee_ids:
            emp_rng = {'employee_id': emp_id}
            for event_type in event_types:
                rng_val = self.hash_rng(emp_id, simulation_year, event_type)
                emp_rng[f'u_{event_type}'] = rng_val
            rng_data.append(emp_rng)

        # Create RNG lookup dataframe
        rng_df = pl.DataFrame(rng_data)

        # Join with original dataframe
        return df.join(rng_df, on='employee_id', how='left')


class PolarsEventGenerator:
    """
    High-performance event generation using Polars vectorized operations.

    Generates all workforce events (hire, termination, promotion, merit, enrollment)
    using vectorized operations for maximum performance while maintaining
    identical logic to existing SQL-based event generation.
    """

    def __init__(self, config: EventFactoryConfig):
        """Initialize event generator with configuration."""
        self.config = config
        self.logger = self._setup_logging()
        self.rng = PolarsDeterministicRNG(config.random_seed)

        # Performance monitoring
        self.start_time = time.time()
        self.stats = {
            'total_events_generated': 0,
            'events_by_type': {},
            'events_by_year': {},
            'processing_time_by_year': {},
            'memory_usage_peak_mb': 0.0
        }
        self._workforce_needs_cache: Dict[int, Optional[Dict[str, Any]]] = {}

        # Load baseline workforce and parameters
        self.logger.info("Loading baseline workforce and parameters...")
        self.baseline_workforce = self._load_baseline_workforce()
        self.parameters = self._load_parameters()
        self.logger.info(f"Loaded {len(self.baseline_workforce)} employees and {len(self.parameters)} parameters")

    def _setup_logging(self) -> logging.Logger:
        """Setup logging with appropriate level and formatting."""
        logger = logging.getLogger(__name__)

        # Don't add handlers if already configured
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

        return logger

    def _load_baseline_workforce(self) -> pl.DataFrame:
        """
        Load baseline workforce from dbt seeds or database.

        Tries multiple sources in order of preference:
        1. Parquet files (fastest)
        2. DuckDB simulation database
        3. CSV seeds (fallback)
        """
        # Try Parquet first (fastest)
        parquet_path = Path("data/parquet/stg_census_data.parquet")
        if parquet_path.exists():
            self.logger.info(f"Loading workforce from Parquet: {parquet_path}")
            df = pl.read_parquet(parquet_path)
        else:
            # Try DuckDB database
            try:
                import duckdb
                # Use database_path from config if specified (for batch mode), otherwise default
                db_path = self.config.database_path if self.config.database_path else get_database_path()
                if db_path.exists():
                    self.logger.info(f"Loading workforce from DuckDB: {db_path}")
                    conn = duckdb.connect(str(db_path))
                    # Query baseline workforce for all years
                    query = """
                    SELECT DISTINCT
                        employee_id,
                        employee_ssn,
                        employee_birth_date,
                        employee_hire_date,
                        employee_gross_compensation,
                        employee_annualized_compensation,
                        employee_deferral_rate,
                        current_eligibility_status,
                        employee_enrollment_date,
                        active
                    FROM stg_census_data
                    WHERE active = true
                    """
                    df = pl.from_pandas(conn.execute(query).df())
                    conn.close()
                else:
                    raise FileNotFoundError(f"Database not found: {db_path}")
            except Exception as e:
                self.logger.warning(f"Could not load from database: {e}")
                # Fallback to CSV
                csv_path = Path("dbt/seeds/census_data.csv")
                if csv_path.exists():
                    self.logger.info(f"Loading workforce from CSV: {csv_path}")
                    df = pl.read_csv(csv_path)
                else:
                    raise FileNotFoundError("No workforce data found in any location")

        # Ensure required columns exist and add metadata
        required_cols = ['employee_id', 'employee_gross_compensation']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Ensure required columns exist with appropriate defaults
        required_columns = {
            'employee_hire_date': '2020-01-01',
            'employee_deferral_rate': 0.0,
            'employee_gross_compensation': 50000.0
        }

        for col_name, default_value in required_columns.items():
            if col_name not in df.columns:
                df = df.with_columns(pl.lit(default_value).alias(col_name))

        # Add scenario context and computed fields
        df = df.with_columns([
            pl.lit(self.config.scenario_id).alias('scenario_id'),
            pl.lit(self.config.plan_design_id).alias('plan_design_id'),
            # Ensure salary column exists
            pl.col('employee_gross_compensation').alias('salary'),
            # Add tenure calculation (simplified - compute from hire date)
            pl.when(pl.col('employee_hire_date').is_not_null())
            .then(
                (pl.date(2025, 1, 1) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 365.25
            )
            .otherwise(2.0)
            .alias('tenure_years'),
            # Tenure in months
            pl.when(pl.col('employee_hire_date').is_not_null())
            .then(
                (pl.date(2025, 1, 1) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 30.44
            )
            .otherwise(24.0)
            .alias('tenure_months'),
            # Add level assignment (simplified)
            (pl.col('employee_gross_compensation') / 25000).floor().clip(1, 5).cast(pl.Int32).alias('level_id'),
            # Add performance tier (deterministic based on employee_id)
            pl.when(pl.col('employee_id').str.slice(-1).is_in(['0', '1', '2']))
            .then(pl.lit('high'))
            .when(pl.col('employee_id').str.slice(-1).is_in(['3', '4', '5', '6']))
            .then(pl.lit('average'))
            .otherwise(pl.lit('low'))
            .alias('performance_tier'),
            # Add enrollment status
            (pl.col('employee_deferral_rate').fill_null(0.0) > 0.0).alias('is_enrolled')
        ])

        return df

    def _load_parameters(self) -> Dict[str, Any]:
        """
        Load simulation parameters from comp_levers.csv and defaults.

        Provides fallback defaults for all parameters to ensure
        the simulation can run even with missing configuration.
        """
        parameters = {}

        # Try to load comp_levers.csv
        comp_levers_path = Path("dbt/seeds/comp_levers.csv")
        if comp_levers_path.exists():
            try:
                comp_df = pl.read_csv(comp_levers_path)
                # Convert to lookup dictionary
                for row in comp_df.iter_rows(named=True):
                    key = f"{row['event_type']}_{row['parameter_name']}_level_{row['job_level']}"
                    parameters[key] = row['parameter_value']
                self.logger.info(f"Loaded {len(parameters)} parameters from comp_levers.csv")
            except Exception as e:
                self.logger.warning(f"Could not load comp_levers.csv: {e}")

        # Set default parameters for event generation
        defaults = {
            # Base rates by level (simplified)
            'hire_rate_base': 0.15,
            'termination_rate_base': 0.12,
            'promotion_rate_base': 0.08,
            'merit_rate_base': 0.85,
            'enrollment_rate_base': 0.75,
            'deferral_rate_base': 0.06,
            # Multipliers
            'new_hire_termination_multiplier': 1.5,
            'low_performer_termination_multiplier': 2.0,
            'promotion_salary_increase': 0.15,
            'merit_salary_increase': 0.04,
            'cola_increase': 0.015,
        }

        # Add defaults for any missing parameters
        for key, value in defaults.items():
            if key not in parameters:
                parameters[key] = value

        return parameters

    def _fetch_workforce_needs(self, simulation_year: int) -> Optional[Dict[str, Any]]:
        """Load workforce planning needs for the given year from DuckDB."""
        if simulation_year in self._workforce_needs_cache:
            return self._workforce_needs_cache[simulation_year]

        try:
            import duckdb  # Local import to avoid hard dependency when unused
        except ImportError:
            self.logger.warning(
                "DuckDB not available; Polars hire generation will fall back to heuristics"
            )
            self._workforce_needs_cache[simulation_year] = None
            return None

        # Use database_path from config if specified (for batch mode), otherwise default
        db_path = self.config.database_path if self.config.database_path else get_database_path()
        if not db_path.exists():
            self.logger.warning(
                "Workforce needs unavailable; database %s does not exist", db_path
            )
            self._workforce_needs_cache[simulation_year] = None
            return None

        try:
            with duckdb.connect(str(db_path)) as conn:
                total_row = conn.execute(
                    """
                    SELECT total_hires_needed
                    FROM int_workforce_needs
                    WHERE simulation_year = ?
                      AND scenario_id = ?
                    """,
                    [simulation_year, self.config.scenario_id],
                ).fetchone()

                if not total_row:
                    self.logger.warning(
                        "No workforce needs found for %s; falling back to heuristics",
                        simulation_year,
                    )
                    self._workforce_needs_cache[simulation_year] = None
                    return None

                level_rows = conn.execute(
                    """
                    SELECT level_id, hires_needed, COALESCE(new_hire_avg_compensation, avg_compensation)
                    FROM int_workforce_needs_by_level
                    WHERE simulation_year = ?
                      AND scenario_id = ?
                    ORDER BY level_id
                    """,
                    [simulation_year, self.config.scenario_id],
                ).fetchall()

        except Exception as exc:
            self.logger.warning(
                "Error loading workforce needs for %s: %s", simulation_year, exc
            )
            self._workforce_needs_cache[simulation_year] = None
            return None

        total_value = total_row[0] if total_row and total_row[0] is not None else 0
        total_hires = int(round(total_value))
        if total_hires <= 0:
            self._workforce_needs_cache[simulation_year] = None
            return None

        levels: List[Dict[str, Any]] = []
        for level_id, hires_needed, avg_comp in level_rows:
            hires_val = int(hires_needed or 0)
            if hires_val <= 0:
                continue
            levels.append(
                {
                    'level_id': int(level_id or 1),
                    'hires_needed': hires_val,
                    'avg_comp': float(avg_comp or 60000.0),
                }
            )

        if not levels:
            # Fallback to standard distribution if level breakdown missing
            default_distribution = [
                (1, 0.40),
                (2, 0.30),
                (3, 0.20),
                (4, 0.08),
                (5, 0.02),
            ]
            levels = []
            for level_id, pct in default_distribution:
                hires = max(0, int(round(total_hires * pct)))
                if hires:
                    levels.append(
                        {
                            'level_id': level_id,
                            'hires_needed': hires,
                            'avg_comp': 60000.0 + (level_id - 1) * 10000.0,
                        }
                    )

        # Ensure rounding errors don't lose hires
        assigned = sum(level['hires_needed'] for level in levels)
        remainder = total_hires - assigned
        idx = 0
        while remainder > 0 and levels:
            levels[idx % len(levels)]['hires_needed'] += 1
            remainder -= 1
            idx += 1

        needs = {'total_hires': total_hires, 'levels': levels}
        self._workforce_needs_cache[simulation_year] = needs
        return needs

    @staticmethod
    def _deterministic_new_hire_age(sequence_num: int) -> int:
        """Match SQL pattern for deterministic new hire ages."""
        pattern = [25, 28, 32, 35, 40]
        return pattern[sequence_num % len(pattern)]

    @staticmethod
    def _age_band(age: int) -> str:
        """Return age band string matching workforce snapshot logic."""
        if age < 25:
            return '< 25'
        if age < 35:
            return '25-34'
        if age < 45:
            return '35-44'
        if age < 55:
            return '45-54'
        if age < 65:
            return '55-64'
        return '65+'

    def _build_hire_record(
        self,
        simulation_year: int,
        sequence_num: int,
        level_id: int,
        avg_compensation: float,
    ) -> Dict[str, Any]:
        """Construct a hire event record aligned with SQL event fields."""
        hire_date = date(simulation_year, 1, 1) + timedelta(days=sequence_num % 365)
        age = self._deterministic_new_hire_age(sequence_num)
        compensation = round(avg_compensation * (0.9 + (sequence_num % 10) * 0.02), 2)
        employee_id = f"NH_{simulation_year}_{sequence_num:06d}"
        ssn_offset = max(0, simulation_year - self.config.start_year) * 100000 + sequence_num
        employee_ssn = f"SSN-{900000000 + ssn_offset:09d}"

        return {
            'scenario_id': self.config.scenario_id,
            'plan_design_id': self.config.plan_design_id,
            'employee_id': employee_id,
            'employee_ssn': employee_ssn,
            'event_type': 'hire',
            'event_category': 'hiring',
            'simulation_year': int(simulation_year),
            'event_date': hire_date,
            'effective_date': hire_date,
            'event_details': f"New hire - Level {level_id}",
            'compensation_amount': float(compensation),
            'previous_compensation': None,  # Will be cast to Float64 when creating DataFrame
            'employee_deferral_rate': None,  # Will be cast to Float64 when creating DataFrame
            'prev_employee_deferral_rate': None,  # Will be cast to Float64 when creating DataFrame
            'employee_age': int(age),
            'employee_tenure': 0,
            'level_id': int(level_id),
            'age_band': self._age_band(age),
            'tenure_band': '< 2',
            'event_probability': 1.0,
            'event_payload': json.dumps({'level_id': int(level_id)}),
            'employee_birth_date': hire_date - timedelta(days=age * 365),
        }

    def _generate_hires_from_needs(
        self, needs: Dict[str, Any], simulation_year: int
    ) -> pl.DataFrame:
        """Generate hire events based on workforce planning needs."""
        records: List[Dict[str, Any]] = []
        sequence_num = 0

        for level in needs.get('levels', []):
            level_id = level['level_id']
            hires_needed = level['hires_needed']
            avg_comp = level['avg_comp']
            for _ in range(max(0, hires_needed)):
                sequence_num += 1
                records.append(
                    self._build_hire_record(simulation_year, sequence_num, level_id, avg_comp)
                )

        total_hires = needs.get('total_hires', sequence_num)
        # If rounding trimmed hires, distribute remainder evenly
        while sequence_num < total_hires and records:
            sequence_num += 1
            level = records[(sequence_num - 1) % len(records)]['level_id']
            avg_comp = next(
                (lvl['avg_comp'] for lvl in needs['levels'] if lvl['level_id'] == level),
                records[(sequence_num - 1) % len(records)]['compensation_amount'],
            )
            records.append(
                self._build_hire_record(simulation_year, sequence_num, level, avg_comp)
            )

        if not records:
            return pl.DataFrame()

        df = pl.DataFrame(records)
        # Explicitly cast NULL columns to Float64 to ensure schema compatibility with other event types
        if 'previous_compensation' in df.columns:
            df = df.with_columns(pl.col('previous_compensation').cast(pl.Float64))
        if 'employee_deferral_rate' in df.columns:
            df = df.with_columns(pl.col('employee_deferral_rate').cast(pl.Float64))
        if 'prev_employee_deferral_rate' in df.columns:
            df = df.with_columns(pl.col('prev_employee_deferral_rate').cast(pl.Float64))

        return df

    def _generate_hires_fallback(
        self, cohort: pl.DataFrame, simulation_year: int
    ) -> pl.DataFrame:
        """Fallback hire generation when workforce needs are unavailable."""
        hire_rate = self._get_parameter('HIRE', 'hire_probability', default=0.15)
        estimated_hires = max(0, int(len(cohort) * hire_rate * 0.1))
        if estimated_hires == 0:
            return pl.DataFrame()

        self.logger.warning(
            "Using heuristic hire generation for %s (%s hires)",
            simulation_year,
            estimated_hires,
        )

        records: List[Dict[str, Any]] = []
        for sequence_num in range(1, estimated_hires + 1):
            level_id = 1 + ((sequence_num - 1) % 5)
            avg_comp = 60000.0 + (level_id - 1) * 8000.0
            records.append(
                self._build_hire_record(simulation_year, sequence_num, level_id, avg_comp)
            )

        if not records:
            return pl.DataFrame()

        df = pl.DataFrame(records)
        # Explicitly cast NULL columns to Float64 to ensure schema compatibility
        if 'previous_compensation' in df.columns:
            df = df.with_columns(pl.col('previous_compensation').cast(pl.Float64))
        if 'employee_deferral_rate' in df.columns:
            df = df.with_columns(pl.col('employee_deferral_rate').cast(pl.Float64))
        if 'prev_employee_deferral_rate' in df.columns:
            df = df.with_columns(pl.col('prev_employee_deferral_rate').cast(pl.Float64))

        return df

    def _get_parameter(self, event_type: str, parameter_name: str, level: int = 1, default: float = 0.0) -> float:
        """Get parameter value with fallback to defaults."""
        key = f"{event_type}_{parameter_name}_level_{level}"
        return self.parameters.get(key, self.parameters.get(f"{parameter_name}_base", default))

    def generate_hire_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """
        Generate hire events using vectorized operations.

        Matches logic in int_hiring_events.sql but uses Polars
        for significantly better performance.
        """
        needs = self._fetch_workforce_needs(simulation_year)
        if needs:
            hires_df = self._generate_hires_from_needs(needs, simulation_year)
            if hires_df.height > 0:
                # Include all fields needed by fct_workforce_snapshot and fct_yearly_events
                # These fields are critical for demographic tracking and state accumulation
                return hires_df.select([
                    'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
                    'event_type', 'event_category', 'event_date', 'effective_date',
                    'event_details', 'event_payload',
                    'compensation_amount', 'previous_compensation',
                    'employee_deferral_rate', 'prev_employee_deferral_rate',
                    'employee_age', 'employee_tenure', 'employee_birth_date',
                    'level_id', 'age_band', 'tenure_band',
                    'simulation_year', 'event_probability'
                ])

        fallback_hires = self._generate_hires_fallback(cohort, simulation_year)
        if fallback_hires.height > 0:
            return fallback_hires.select([
                'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
                'event_type', 'event_category', 'event_date', 'effective_date',
                'event_details', 'event_payload',
                'compensation_amount', 'previous_compensation',
                'employee_deferral_rate', 'prev_employee_deferral_rate',
                'employee_age', 'employee_tenure', 'employee_birth_date',
                'level_id', 'age_band', 'tenure_band',
                'simulation_year', 'event_probability'
            ])

        return pl.DataFrame()

    def generate_termination_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """
        Generate experienced employee termination events using exact targets from int_workforce_needs_by_level.

        NOTE: This generates ONLY experienced terminations. New hire terminations are generated separately
        by generate_new_hire_termination_events() to maintain separation of cohorts.
        """
        if cohort.height == 0:
            return pl.DataFrame()

        # Filter to only experienced employees (exclude current year hires)
        # Current year hires will be handled by generate_new_hire_termination_events
        experienced = cohort.filter(
            pl.col('employee_hire_date').is_not_null() &
            (pl.col('employee_hire_date') < pl.date(simulation_year, 1, 1))
        )

        if experienced.height == 0:
            return pl.DataFrame()

        # Query termination targets by level from int_workforce_needs_by_level
        targets_df = None
        using_fallback = False

        try:
            db_path = self.config.database_path if self.config.database_path else get_database_path()
            conn = duckdb.connect(str(db_path), read_only=True)
            termination_targets_query = f"""
                SELECT
                    level_id,
                    expected_terminations
                FROM int_workforce_needs_by_level
                WHERE simulation_year = {simulation_year}
                  AND scenario_id = '{self.config.scenario_id}'
            """
            targets_df = conn.execute(termination_targets_query).pl()
            conn.close()

            if targets_df.height == 0:
                logger.warning(
                    "No termination targets found in int_workforce_needs_by_level for year %s - using fallback calculation",
                    simulation_year
                )
                targets_df = None  # Trigger fallback

        except Exception as exc:
            logger.warning(
                "Could not load termination targets from database for year %s: %s - using fallback calculation",
                simulation_year, exc
            )
            targets_df = None  # Trigger fallback

        # FALLBACK: Calculate targets internally if database query failed
        if targets_df is None:
            using_fallback = True
            termination_rate = self.parameters.get('total_termination_rate', 0.12)

            # Calculate per-level targets based on experienced workforce distribution
            level_counts = experienced.group_by('level_id').agg([
                pl.count().alias('count')
            ])

            targets_df = level_counts.with_columns([
                pl.col('level_id'),
                (pl.col('count') * termination_rate).round().cast(pl.Int64).alias('expected_terminations')
            ])

            logger.info(
                "Year %s: Using fallback termination calculation (%.1f%% rate) - %d total expected",
                simulation_year,
                termination_rate * 100,
                targets_df.select(pl.sum('expected_terminations')).item()
            )
        else:
            logger.info(
                "Year %s: Using database termination targets - %d total expected",
                simulation_year,
                targets_df.select(pl.sum('expected_terminations')).item()
            )

        # Add deterministic random value for selection (matches SQL logic)
        experienced = experienced.with_columns([
            # Deterministic random based on employee_id hash (matches SQL pattern)
            ((pl.col('employee_id').hash() % 10000) / 10000.0).alias('random_value')
        ])

        # Select terminations by level to match exact targets
        selected_terminations = []
        for row in targets_df.iter_rows(named=True):
            level_id = row['level_id']
            target_count = int(row['expected_terminations'])

            if target_count <= 0:
                continue

            # Get employees at this level, ranked by deterministic random
            level_employees = experienced.filter(
                pl.col('level_id') == level_id
            ).sort('random_value')

            # Select exactly target_count employees
            level_terminations = level_employees.head(target_count)
            selected_terminations.append(level_terminations)

        if not selected_terminations:
            return pl.DataFrame()

        # Combine all level terminations
        all_terminations = pl.concat(selected_terminations, how='vertical')

        # Add termination event fields
        terminations = all_terminations.with_columns([
            pl.lit('termination').alias('event_type'),
            pl.lit('termination').alias('event_category'),
            pl.date(simulation_year, 9, 15).alias('event_date'),  # Fall terminations
            pl.date(simulation_year, 9, 15).alias('effective_date'),
            pl.concat_str([
                pl.lit('Termination - voluntary (tenure: '),
                pl.col('tenure_months').cast(pl.Utf8),
                pl.lit(' months)')
            ]).alias('event_details'),
            pl.concat_str([
                pl.lit('{"reason": "voluntary", "level_id": '),
                pl.col('level_id').cast(pl.Utf8),
                pl.lit(', "tenure_months": '),
                pl.col('tenure_months').cast(pl.Utf8),
                pl.lit('}')
            ]).alias('event_payload'),
            pl.lit(simulation_year).cast(pl.Int64).alias('simulation_year'),
            pl.lit(0.12).alias('event_probability'),  # Base experienced termination rate
            # Add demographic fields from cohort
            pl.when(pl.col('employee_ssn').is_not_null())
            .then(pl.col('employee_ssn'))
            .otherwise(pl.lit(None).cast(pl.Utf8))
            .alias('employee_ssn'),
            pl.when(pl.col('employee_birth_date').is_not_null())
            .then(pl.col('employee_birth_date'))
            .otherwise(pl.lit(None).cast(pl.Date))
            .alias('employee_birth_date'),
            pl.col('tenure_years').cast(pl.Int32).alias('employee_tenure'),
            # Add NULL compensation and deferral fields for consistency
            pl.lit(None).cast(pl.Float64).alias('compensation_amount'),
            pl.lit(None).cast(pl.Float64).alias('previous_compensation'),
            pl.lit(None).cast(pl.Float64).alias('employee_deferral_rate'),
            pl.lit(None).cast(pl.Float64).alias('prev_employee_deferral_rate'),
            # Add NULL age fields - will be computed in second pass
            pl.lit(None).cast(pl.Int32).alias('employee_age'),
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            # Compute tenure band
            pl.when(pl.col('tenure_years') < 2).then(pl.lit('< 2'))
            .when(pl.col('tenure_years') < 5).then(pl.lit('2-4'))
            .when(pl.col('tenure_years') < 10).then(pl.lit('5-9'))
            .when(pl.col('tenure_years') < 20).then(pl.lit('10-19'))
            .otherwise(pl.lit('20+'))
            .alias('tenure_band')
        ])

        return terminations.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def generate_promotion_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """Generate promotion events for eligible employees."""
        base_promotion_rate = self._get_parameter('PROMOTION', 'promotion_probability', default=0.08)
        # Apply promotion rate multiplier from config (E082)
        effective_promotion_rate = base_promotion_rate * self.config.promotion_rate_multiplier
        salary_increase = self._get_parameter('PROMOTION', 'promotion_raise', default=0.15)

        promotions = cohort.filter(
            # Basic eligibility criteria
            pl.col('employee_hire_date').is_not_null() &
            (pl.col('tenure_months') >= 12) &  # Minimum 1 year tenure
            (pl.col('level_id') < 5) &  # Can't promote beyond level 5
            # Apply promotion probability (with E082 multiplier applied)
            (pl.col('u_promotion') < effective_promotion_rate)
        ).with_columns([
            pl.lit('promotion').alias('event_type'),
            pl.lit('compensation').alias('event_category'),
            pl.date(simulation_year, 1, 1).alias('event_date'),  # Annual promotions
            pl.date(simulation_year, 1, 1).alias('effective_date'),
            pl.concat_str([
                pl.lit('Promotion from level '),
                pl.col('level_id').cast(pl.Utf8),
                pl.lit(' to '),
                (pl.col('level_id') + 1).cast(pl.Utf8),
                pl.lit(' with '),
                pl.lit(round(salary_increase * 100, 1)).cast(pl.Utf8),
                pl.lit('% increase')
            ]).alias('event_details'),
            pl.concat_str([
                pl.lit('{"old_level": '),
                pl.col('level_id').cast(pl.Utf8),
                pl.lit(', "new_level": '),
                (pl.col('level_id') + 1).cast(pl.Utf8),
                pl.lit(', "new_salary": '),
                (pl.col('salary') * (1 + salary_increase)).round(2).cast(pl.Utf8),
                pl.lit(', "salary_increase_pct": '),
                pl.lit(salary_increase).cast(pl.Utf8),
                pl.lit('}')
            ]).alias('event_payload'),
            pl.lit(simulation_year).cast(pl.Int64).alias('simulation_year'),
            pl.lit(effective_promotion_rate).alias('event_probability'),
            # Add compensation fields
            (pl.col('salary') * (1 + salary_increase)).round(2).alias('compensation_amount'),
            pl.col('salary').alias('previous_compensation'),
            # Add NULL deferral fields
            pl.lit(None).cast(pl.Float64).alias('employee_deferral_rate'),
            pl.lit(None).cast(pl.Float64).alias('prev_employee_deferral_rate'),
            # Add demographic fields from cohort (with NULL fallback)
            pl.col('employee_ssn').alias('employee_ssn'),
            pl.col('employee_birth_date').alias('employee_birth_date'),
            pl.lit(None).cast(pl.Int32).alias('employee_age'),  # Not critical for promotions
            pl.col('tenure_years').cast(pl.Int32).alias('employee_tenure'),
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            pl.lit(None).cast(pl.Utf8).alias('tenure_band')
        ])

        return promotions.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def generate_merit_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """Generate merit increase events for eligible employees."""
        merit_rate = self._get_parameter('RAISE', 'merit_base', default=0.85)
        merit_increase = self._get_parameter('RAISE', 'merit_increase', default=0.04)

        merits = cohort.filter(
            pl.col('employee_hire_date').is_not_null() &
            (pl.col('u_merit') < merit_rate)
        ).with_columns([
            pl.lit('raise').alias('event_type'),
            pl.lit('compensation').alias('event_category'),
            pl.date(simulation_year, 3, 15).alias('event_date'),  # Annual merit cycle
            pl.date(simulation_year, 3, 15).alias('effective_date'),
            pl.concat_str([
                pl.lit('Merit increase: '),
                pl.lit(round(merit_increase * 100, 1)).cast(pl.Utf8),
                pl.lit('% raise')
            ]).alias('event_details'),
            pl.concat_str([
                pl.lit('{"old_salary": '),
                pl.col('salary').round(2).cast(pl.Utf8),
                pl.lit(', "new_salary": '),
                (pl.col('salary') * (1 + merit_increase)).round(2).cast(pl.Utf8),
                pl.lit(', "merit_increase_pct": '),
                pl.lit(merit_increase).cast(pl.Utf8),
                pl.lit(', "merit_type": "annual_merit"}')
            ]).alias('event_payload'),
            pl.lit(simulation_year).cast(pl.Int64).alias('simulation_year'),
            pl.lit(merit_rate).alias('event_probability'),
            # Add compensation fields
            (pl.col('salary') * (1 + merit_increase)).round(2).alias('compensation_amount'),
            pl.col('salary').alias('previous_compensation'),
            # Add NULL fields for consistency
            pl.lit(None).cast(pl.Float64).alias('employee_deferral_rate'),
            pl.lit(None).cast(pl.Float64).alias('prev_employee_deferral_rate'),
            pl.col('employee_ssn').alias('employee_ssn'),
            pl.col('employee_birth_date').alias('employee_birth_date'),
            pl.lit(None).cast(pl.Int32).alias('employee_age'),
            pl.col('tenure_years').cast(pl.Int32).alias('employee_tenure'),
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            pl.lit(None).cast(pl.Utf8).alias('tenure_band')
        ])

        return merits.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def generate_enrollment_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """Generate benefit enrollment events for eligible employees."""
        enrollment_rate = self._get_parameter('ENROLLMENT', 'enrollment_rate', default=0.75)
        base_deferral_rate = self._get_parameter('DEFERRAL', 'base_deferral_rate', default=0.06)

        enrollments = cohort.filter(
            pl.col('employee_hire_date').is_not_null() &
            (pl.col('is_enrolled') == False) &  # Only enroll if not already enrolled
            (pl.col('u_enrollment') < enrollment_rate)
        ).with_columns([
            pl.lit('enrollment').alias('event_type'),
            pl.lit('voluntary_enrollment').alias('event_category'),
            pl.date(simulation_year, 4, 1).alias('event_date'),  # Open enrollment
            pl.date(simulation_year, 4, 1).alias('effective_date'),
            pl.concat_str([
                pl.lit('Enrollment with '),
                pl.lit(round(base_deferral_rate * 100, 1)).cast(pl.Utf8),
                pl.lit('% deferral rate')
            ]).alias('event_details'),
            pl.concat_str([
                pl.lit('{"plan_design_id": "'),
                pl.col('plan_design_id'),
                pl.lit('", "initial_deferral_rate": '),
                pl.lit(base_deferral_rate).cast(pl.Utf8),
                pl.lit(', "eligibility_status": "'),
                pl.col('current_eligibility_status').fill_null('eligible'),
                pl.lit('", "enrollment_type": "new_enrollment"}')
            ]).alias('event_payload'),
            pl.lit(simulation_year).cast(pl.Int64).alias('simulation_year'),
            pl.lit(enrollment_rate).alias('event_probability'),
            # Add NULL compensation fields
            pl.lit(None).cast(pl.Float64).alias('compensation_amount'),
            pl.lit(None).cast(pl.Float64).alias('previous_compensation'),
            # Add deferral rate fields
            pl.lit(base_deferral_rate).cast(pl.Float64).alias('employee_deferral_rate'),
            pl.lit(None).cast(pl.Float64).alias('prev_employee_deferral_rate'),
            # Add demographic fields
            pl.col('employee_ssn').alias('employee_ssn'),
            pl.col('employee_birth_date').alias('employee_birth_date'),
            pl.lit(None).cast(pl.Int32).alias('employee_age'),
            pl.col('tenure_years').cast(pl.Int32).alias('employee_tenure'),
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            pl.lit(None).cast(pl.Utf8).alias('tenure_band')
        ])

        return enrollments.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def generate_deferral_escalation_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """
        Generate automatic deferral rate escalation events.

        Escalates enrolled employees' deferral rates by 1% annually up to a 10% cap.
        Matches logic from int_deferral_rate_escalation_events.sql.
        """
        # Get escalation parameters
        esc_enabled = self._get_parameter('DEFERRAL_ESCALATION', 'enabled', default=True)
        if not esc_enabled:
            return pl.DataFrame()

        esc_rate = self._get_parameter('DEFERRAL_ESCALATION', 'increment', default=0.01)
        esc_cap = self._get_parameter('DEFERRAL_ESCALATION', 'cap', default=0.10)

        # Filter to enrolled employees with current deferral rate below cap
        eligible = cohort.filter(
            pl.col('is_enrolled') &
            (pl.col('employee_deferral_rate').is_not_null()) &
            (pl.col('employee_deferral_rate') < esc_cap)
        )

        if eligible.height == 0:
            return pl.DataFrame()

        # Calculate new deferral rate (capped at max)
        escalations = eligible.with_columns([
            pl.lit('deferral_escalation').alias('event_type'),
            pl.lit('deferral_escalation').alias('event_category'),
            pl.date(simulation_year, 1, 1).alias('event_date'),  # January 1 escalation
            pl.date(simulation_year, 1, 1).alias('effective_date'),
            # New deferral rate = current + increment, capped at max
            pl.when(pl.col('employee_deferral_rate') + esc_rate > esc_cap)
            .then(pl.lit(esc_cap))
            .otherwise(pl.col('employee_deferral_rate') + esc_rate)
            .alias('new_deferral_rate'),
            pl.concat_str([
                pl.lit('Auto-escalation from '),
                (pl.col('employee_deferral_rate') * 100).round(1).cast(pl.Utf8),
                pl.lit('% to '),
                pl.when(pl.col('employee_deferral_rate') + esc_rate > esc_cap)
                .then((pl.lit(esc_cap) * 100).round(1))
                .otherwise((pl.col('employee_deferral_rate') + esc_rate) * 100).round(1).cast(pl.Utf8),
                pl.lit('%')
            ]).alias('event_details'),
            pl.lit(None).cast(pl.Utf8).alias('event_payload'),
            pl.lit(simulation_year).cast(pl.Int64).alias('simulation_year'),
            pl.lit(1.0).alias('event_probability'),  # Automatic, not probabilistic
            # Compensation fields (null for deferral events)
            pl.lit(None).cast(pl.Float64).alias('compensation_amount'),
            pl.lit(None).cast(pl.Float64).alias('previous_compensation'),
            # Store previous deferral rate
            pl.col('employee_deferral_rate').alias('prev_employee_deferral_rate'),
            # Demographic fields
            pl.col('employee_ssn'),
            pl.col('employee_birth_date'),
            pl.lit(None).cast(pl.Int32).alias('employee_age'),
            pl.col('tenure_years').cast(pl.Int32).alias('employee_tenure'),
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            pl.lit(None).cast(pl.Utf8).alias('tenure_band')
        ]).with_columns([
            # Set employee_deferral_rate to new_deferral_rate for consistency
            pl.col('new_deferral_rate').alias('employee_deferral_rate')
        ])

        return escalations.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def generate_enrollment_change_events(self, cohort: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """
        Generate enrollment change events (primarily opt-outs).

        Allows enrolled employees to opt out of the plan.
        Matches logic for enrollment_change events in SQL mode.
        """
        # Get opt-out rate parameter
        optout_rate = self._get_parameter('ENROLLMENT', 'optout_rate', default=0.02)

        # Filter to enrolled employees
        enrolled = cohort.filter(
            pl.col('is_enrolled') &
            (pl.col('u_enrollment') < optout_rate)  # Use enrollment random value for opt-out
        )

        if enrolled.height == 0:
            return pl.DataFrame()

        # Generate opt-out events
        optouts = enrolled.with_columns([
            pl.lit('enrollment_change').alias('event_type'),
            pl.lit('enrollment_change').alias('event_category'),
            pl.date(simulation_year, 6, 30).alias('event_date'),  # Mid-year opt-outs
            pl.date(simulation_year, 6, 30).alias('effective_date'),
            pl.lit('Employee opted out of plan').alias('event_details'),
            pl.lit('{"action": "opt_out"}').alias('event_payload'),
            pl.lit(simulation_year).cast(pl.Int64).alias('simulation_year'),
            pl.lit(optout_rate).alias('event_probability'),
            # Compensation fields (null)
            pl.lit(None).cast(pl.Float64).alias('compensation_amount'),
            pl.lit(None).cast(pl.Float64).alias('previous_compensation'),
            # Deferral rate becomes null after opt-out
            pl.lit(None).cast(pl.Float64).alias('employee_deferral_rate'),
            pl.col('employee_deferral_rate').alias('prev_employee_deferral_rate'),
            # Demographic fields
            pl.col('employee_ssn'),
            pl.col('employee_birth_date'),
            pl.lit(None).cast(pl.Int32).alias('employee_age'),
            pl.col('tenure_years').cast(pl.Int32).alias('employee_tenure'),
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            pl.lit(None).cast(pl.Utf8).alias('tenure_band')
        ])

        return optouts.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def generate_new_hire_termination_events(self, hire_events: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
        """
        Generate termination events for new hires using exact target from int_workforce_needs.

        New hires have elevated termination risk (25% vs 12% for experienced employees).
        This matches the logic in int_new_hire_termination_events.sql.
        """
        if hire_events.height == 0:
            return pl.DataFrame()

        # Query exact new hire termination target from int_workforce_needs
        try:
            db_path = self.config.database_path if self.config.database_path else get_database_path()
            conn = duckdb.connect(str(db_path), read_only=True)
            target_query = f"""
                SELECT expected_new_hire_terminations
                FROM int_workforce_needs
                WHERE simulation_year = {simulation_year}
                  AND scenario_id = '{self.config.scenario_id}'
            """
            result = conn.execute(target_query).fetchone()
            conn.close()

            if not result or result[0] is None:
                logger.warning(
                    "No new hire termination target found in int_workforce_needs for year %s",
                    simulation_year
                )
                return pl.DataFrame()

            target_terminations = int(result[0])

            if target_terminations <= 0:
                logger.info("No new hire terminations needed for year %s", simulation_year)
                return pl.DataFrame()

        except Exception as exc:
            logger.error("Error loading new hire termination target for year %s: %s", simulation_year, exc)
            return pl.DataFrame()

        # Add deterministic random for ranking (matches SQL logic)
        hire_events = hire_events.with_columns([
            ((pl.col('employee_id').hash() % 10000) / 10000.0).alias('random_value')
        ])

        # Rank by deterministic random and select exactly the target number
        ranked_hires = hire_events.sort('random_value')
        selected_terminations = ranked_hires.head(target_terminations)

        # Add termination event fields
        nh_terminations = selected_terminations.with_columns([
            pl.lit('termination').alias('event_type'),
            pl.lit('termination').alias('event_category'),
            # Terminations occur in fall (September 15)
            pl.date(simulation_year, 9, 15).alias('event_date'),
            pl.date(simulation_year, 9, 15).alias('effective_date'),
            pl.concat_str([
                pl.lit('New hire termination - voluntary')
            ]).alias('event_details'),
            pl.concat_str([
                pl.lit('{"reason": "voluntary", "employee_type": "new_hire", "level_id": '),
                pl.col('level_id').cast(pl.Utf8),
                pl.lit('}')
            ]).alias('event_payload'),
            # Termination probability (informational only)
            pl.lit(0.25).alias('event_probability'),
            # Clear compensation fields for terminations
            pl.lit(None).cast(pl.Float64).alias('compensation_amount'),
            pl.lit(None).cast(pl.Float64).alias('previous_compensation'),
            pl.lit(None).cast(pl.Float64).alias('employee_deferral_rate'),
            pl.lit(None).cast(pl.Float64).alias('prev_employee_deferral_rate'),
            # Keep demographic fields from hire event
            pl.lit(None).cast(pl.Utf8).alias('age_band'),
            pl.lit(None).cast(pl.Utf8).alias('tenure_band'),
            pl.lit(0).cast(pl.Int32).alias('employee_tenure')  # Zero tenure for new hires
        ])

        return nh_terminations.select([
            'scenario_id', 'plan_design_id', 'employee_id', 'employee_ssn',
            'event_type', 'event_category', 'event_date', 'effective_date',
            'event_details', 'event_payload',
            'compensation_amount', 'previous_compensation',
            'employee_deferral_rate', 'prev_employee_deferral_rate',
            'employee_age', 'employee_tenure', 'employee_birth_date',
            'level_id', 'age_band', 'tenure_band',
            'simulation_year', 'event_probability'
        ])

    def _get_updated_cohort_for_year(self, simulation_year: int) -> pl.DataFrame:
        """
        Get the appropriate cohort for the given year.

        For year 1: Use baseline workforce
        For year 2+: Load surviving workforce from database (accounts for previous year's hires/terminations)
        """
        if simulation_year == self.config.start_year:
            # Year 1: Use baseline workforce
            self.logger.info(f"Year {simulation_year}: Using baseline workforce ({self.baseline_workforce.height} employees)")
            return self.baseline_workforce.clone()

        # Year 2+: Query database for active workforce after previous year
        try:
            import duckdb
            db_path = self.config.database_path if self.config.database_path else get_database_path()

            if not db_path.exists():
                self.logger.warning(f"Database not found for year {simulation_year}, falling back to baseline")
                return self.baseline_workforce.clone()

            with duckdb.connect(str(db_path)) as conn:
                # Get all active employees from previous year's snapshot
                prev_year = simulation_year - 1
                query = """
                    SELECT
                        employee_id,
                        employee_ssn,
                        employee_birth_date,
                        employee_hire_date,
                        level_id,
                        current_compensation as employee_gross_compensation,
                        current_compensation as employee_annualized_compensation,
                        COALESCE(effective_annual_deferral_rate, 0.0) as employee_deferral_rate,
                        current_eligibility_status,
                        employee_enrollment_date,
                        CASE WHEN employment_status = 'active' THEN true ELSE false END as active
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                      AND employment_status = 'active'
                """
                result = conn.execute(query, [prev_year]).df()

                if len(result) == 0:
                    self.logger.warning(f"No active employees found for previous year {prev_year}, using baseline")
                    return self.baseline_workforce.clone()

                # Convert to Polars and add required fields
                cohort = pl.from_pandas(result)

                # Add computed fields (same as baseline loading)
                cohort = cohort.with_columns([
                    pl.lit(self.config.scenario_id).alias('scenario_id'),
                    pl.lit(self.config.plan_design_id).alias('plan_design_id'),
                    pl.col('employee_gross_compensation').alias('salary'),
                    # Update tenure for new year
                    pl.when(pl.col('employee_hire_date').is_not_null())
                    .then(
                        (pl.date(simulation_year, 1, 1) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 365.25
                    )
                    .otherwise(2.0)
                    .alias('tenure_years'),
                    pl.when(pl.col('employee_hire_date').is_not_null())
                    .then(
                        (pl.date(simulation_year, 1, 1) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 30.44
                    )
                    .otherwise(24.0)
                    .alias('tenure_months'),
                    # level_id is now loaded from fct_workforce_snapshot, no need to recompute
                    pl.col('level_id').cast(pl.Int32).alias('level_id'),
                    pl.when(pl.col('employee_id').str.slice(-1).is_in(['0', '1', '2']))
                    .then(pl.lit('high'))
                    .when(pl.col('employee_id').str.slice(-1).is_in(['3', '4', '5', '6']))
                    .then(pl.lit('average'))
                    .otherwise(pl.lit('low'))
                    .alias('performance_tier'),
                    (pl.col('employee_deferral_rate').fill_null(0.0) > 0.0).alias('is_enrolled')
                ])

                self.logger.info(f"Loaded {len(cohort)} surviving employees from year {prev_year}")
                return cohort

        except Exception as e:
            self.logger.error(f"Error loading previous year workforce: {e}")
            # E078 FIX: Raise exception instead of silently falling back to baseline
            # This was causing duplicate terminations in multi-year simulations
            raise RuntimeError(f"Failed to load workforce from year {prev_year}: {e}") from e

    def generate_year_events(self, simulation_year: int) -> pl.DataFrame:
        """
        Generate all events for a single year using parallel processing.

        Uses vectorized operations for maximum performance while maintaining
        the same event generation logic as SQL-based models.
        """
        year_start_time = time.time()
        self.logger.info(f"Generating events for year {simulation_year}...")

        # Prepare cohort for the year (uses previous year's survivors for year 2+)
        cohort = self._get_updated_cohort_for_year(simulation_year)

        if cohort.height == 0:
            self.logger.warning(f"No employees found for year {simulation_year}")
            return pl.DataFrame()

        # Add all RNG columns at once for efficiency
        self.logger.debug(f"Adding RNG columns for {cohort.height} employees")
        cohort_with_rng = self.rng.add_rng_columns_vectorized(cohort, simulation_year)

        # Generate all event types
        self.logger.info(f"Processing {cohort_with_rng.height} employees for year {simulation_year}")

        event_dfs = []
        event_counts = {}
        hire_events_df = None  # Store hire events for new hire termination generation

        # Generate each event type with timing
        for event_type, generator_method in [
            ('hire', self.generate_hire_events),
            ('termination', self.generate_termination_events),
            ('promotion', self.generate_promotion_events),
            ('raise', self.generate_merit_events),  # Changed from 'merit' to match SQL
            ('enrollment', self.generate_enrollment_events),
            ('deferral_escalation', self.generate_deferral_escalation_events),
            ('enrollment_change', self.generate_enrollment_change_events)
        ]:
            event_start_time = time.time()
            events = generator_method(cohort_with_rng, simulation_year)
            event_duration = time.time() - event_start_time

            if events.height > 0:
                event_dfs.append(events)
                event_counts[event_type] = events.height
                self.logger.info(f"Generated {events.height} {event_type} events in {event_duration:.2f}s")

                # Capture hire events for new hire termination generation
                if event_type == 'hire':
                    hire_events_df = events
            else:
                event_counts[event_type] = 0
                self.logger.debug(f"No {event_type} events generated")

        # Generate new hire terminations (must run after hire events)
        if hire_events_df is not None and hire_events_df.height > 0:
            event_start_time = time.time()
            nh_term_events = self.generate_new_hire_termination_events(hire_events_df, simulation_year)
            event_duration = time.time() - event_start_time

            if nh_term_events.height > 0:
                event_dfs.append(nh_term_events)
                event_counts['new_hire_termination'] = nh_term_events.height
                self.logger.info(f"Generated {nh_term_events.height} new_hire_termination events in {event_duration:.2f}s")
            else:
                event_counts['new_hire_termination'] = 0
                self.logger.debug(f"No new_hire_termination events generated")

        # Combine all events if any were generated
        # Use diagonal_relaxed to handle schema mismatches (NULL vs Float64, Int32 vs Int64, etc.)
        if event_dfs:
            all_events = pl.concat(event_dfs, how='diagonal_relaxed')

            # Add event IDs and audit fields
            all_events = all_events.with_columns([
                # Generate deterministic event IDs using hash
                pl.concat_str([
                    pl.col('scenario_id'),
                    pl.col('plan_design_id'),
                    pl.col('employee_id'),
                    pl.col('simulation_year').cast(pl.Utf8),
                    pl.col('event_type')
                ], separator='|').hash().cast(pl.Utf8).alias('event_id'),

                pl.lit(datetime.now()).alias('created_at'),
                pl.lit('polars_factory').alias('generation_method')
            ])

            # Ensure deterministic ordering
            all_events = all_events.sort(['employee_id', 'event_type', 'event_date'])

            total_events = all_events.height
            year_duration = time.time() - year_start_time

            # Update statistics
            self.stats['total_events_generated'] += total_events
            self.stats['events_by_year'][simulation_year] = total_events
            self.stats['processing_time_by_year'][simulation_year] = year_duration
            for event_type, count in event_counts.items():
                if event_type not in self.stats['events_by_type']:
                    self.stats['events_by_type'][event_type] = 0
                self.stats['events_by_type'][event_type] += count

            self.logger.info(f"Generated {total_events} total events for year {simulation_year} in {year_duration:.2f}s")
            self.logger.info(f"Event breakdown: {event_counts}")

            return all_events
        else:
            self.logger.warning(f"No events generated for year {simulation_year}")
            return pl.DataFrame()

    def generate_multi_year_events(self) -> None:
        """
        Generate events for all years and write to partitioned Parquet files.

        Main entry point for bulk event generation. Processes all years
        sequentially and writes results to partitioned Parquet files
        for optimal dbt integration.
        """
        total_start_time = time.time()
        self.logger.info(f"Starting multi-year event generation ({self.config.start_year}-{self.config.end_year})")
        self.logger.info(f"Configuration: {self.config}")

        # Ensure output directory exists
        self.config.output_path.mkdir(parents=True, exist_ok=True)

        total_events = 0
        successful_years = []
        failed_years = []

        # Process each year
        for year in range(self.config.start_year, self.config.end_year + 1):
            try:
                year_start = time.time()

                year_events = self.generate_year_events(year)

                if year_events.height > 0:
                    # Write year partition
                    year_output_path = self.config.output_path / f"simulation_year={year}"
                    year_output_path.mkdir(exist_ok=True)

                    parquet_file = year_output_path / f"events_{year}.parquet"

                    # Write with compression and optimization
                    write_options = {
                        'compression': 'zstd' if self.config.enable_compression else None,
                        'compression_level': self.config.compression_level,
                        'statistics': True,
                        'row_group_size': min(50000, max(1000, year_events.height // 10))
                    }

                    year_events.write_parquet(parquet_file, **write_options)

                    total_events += year_events.height
                    successful_years.append(year)

                    year_duration = time.time() - year_start
                    self.logger.info(f"Year {year} completed in {year_duration:.1f}s - wrote {year_events.height:,} events")
                else:
                    self.logger.warning(f"No events generated for year {year}")

            except Exception as e:
                failed_years.append(year)
                self.logger.error(f"Failed to generate events for year {year}: {e}", exc_info=True)

        # Final statistics and summary
        total_duration = time.time() - total_start_time

        self.logger.info("="*60)
        self.logger.info("MULTI-YEAR EVENT GENERATION COMPLETE")
        self.logger.info("="*60)
        self.logger.info(f"Total events generated: {total_events:,}")
        self.logger.info(f"Successful years: {len(successful_years)} ({successful_years})")
        if failed_years:
            self.logger.warning(f"Failed years: {len(failed_years)} ({failed_years})")
        self.logger.info(f"Total processing time: {total_duration:.1f}s")
        self.logger.info(f"Average events/second: {total_events / total_duration:.0f}")
        self.logger.info(f"Output directory: {self.config.output_path}")

        # Write comprehensive summary metadata
        summary = {
            'generation_summary': {
                'start_year': self.config.start_year,
                'end_year': self.config.end_year,
                'total_events': total_events,
                'successful_years': successful_years,
                'failed_years': failed_years,
                'total_duration_seconds': total_duration,
                'events_per_second': total_events / total_duration if total_duration > 0 else 0,
                'generated_at': datetime.now().isoformat()
            },
            'configuration': {
                'scenario_id': self.config.scenario_id,
                'plan_design_id': self.config.plan_design_id,
                'random_seed': self.config.random_seed,
                'batch_size': self.config.batch_size,
                'compression_enabled': self.config.enable_compression,
                'max_threads': os.environ.get('POLARS_MAX_THREADS', 'auto')
            },
            'statistics': self.stats,
            'performance_metrics': {
                'target_performance': '≤60s for 5k×5 years',
                'achieved_performance': f"{total_duration:.1f}s for {len(successful_years)} years",
                'performance_ratio': total_duration / 60.0,  # Ratio vs 60s target
                'memory_efficient': total_duration < 300,  # Under 5 minutes is good
                'meets_target': total_duration <= 60 and len(successful_years) >= 3
            }
        }

        summary_path = self.config.output_path / "generation_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        self.logger.info(f"Summary written to: {summary_path}")

        # Performance assessment
        if total_duration <= 60 and len(successful_years) >= 3:
            self.logger.info("✅ PERFORMANCE TARGET MET: ≤60s for multi-year generation")
        else:
            self.logger.warning(f"⚠️  Performance target missed: {total_duration:.1f}s (target: ≤60s)")


def main():
    """CLI entry point for Polars bulk event factory."""
    parser = argparse.ArgumentParser(
        description="Polars Bulk Event Factory - High-Performance Event Generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate events for 2025-2029 with default settings
  python polars_event_factory.py --start 2025 --end 2029 --out /tmp/events

  # High-performance generation with custom seed
  POLARS_MAX_THREADS=16 python polars_event_factory.py --start 2025 --end 2027 \
    --out /mnt/fast/sim_events --seed 54321 --verbose

  # Production run with compression
  python polars_event_factory.py --start 2025 --end 2029 --out ./events \
    --scenario production --plan plan_2025 --enable-compression
        """
    )

    # Required arguments
    parser.add_argument('--start', type=int, required=True,
                       help='Start year for event generation')
    parser.add_argument('--end', type=int, required=True,
                       help='End year for event generation')
    parser.add_argument('--out', type=Path, required=True,
                       help='Output directory for partitioned Parquet files')

    # Optional configuration
    parser.add_argument('--seed', type=int, default=12345,
                       help='Random seed for deterministic generation (default: 12345)')
    parser.add_argument('--scenario', default='default',
                       help='Scenario ID (default: default)')
    parser.add_argument('--plan', default='default',
                       help='Plan design ID (default: default)')

    # Performance options
    parser.add_argument('--batch-size', type=int, default=10000,
                       help='Batch size for processing (default: 10000)')
    parser.add_argument('--enable-compression', action='store_true',
                       help='Enable zstd compression for Parquet files')
    parser.add_argument('--compression-level', type=int, default=6,
                       help='Compression level for zstd (1-22, default: 6)')

    # Debugging and monitoring
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--enable-profiling', action='store_true',
                       help='Enable Polars query profiling')
    parser.add_argument('--max-memory-gb', type=float, default=8.0,
                       help='Maximum memory usage in GB (default: 8.0)')

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers = [logging.StreamHandler()]

    # Add file handler if output directory is specified
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        handlers.append(logging.FileHandler(args.out / 'event_generation.log', mode='w'))

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    logger = logging.getLogger(__name__)

    try:
        # Validate environment
        threads = os.environ.get('POLARS_MAX_THREADS', 'auto')
        logger.info(f"Polars max threads: {threads}")
        logger.info(f"Performance target: ≤60s for 5k×5 years")

        # Create configuration
        config = EventFactoryConfig(
            start_year=args.start,
            end_year=args.end,
            output_path=args.out,
            scenario_id=args.scenario,
            plan_design_id=args.plan,
            random_seed=args.seed,
            batch_size=args.batch_size,
            enable_compression=args.enable_compression,
            compression_level=args.compression_level,
            enable_profiling=args.enable_profiling,
            max_memory_gb=args.max_memory_gb
        )

        logger.info(f"Starting Polars bulk event generation with config: {config}")

        # Generate events
        generator = PolarsEventGenerator(config)
        generator.generate_multi_year_events()

        print(f"\n✅ Event generation complete!")
        print(f"📊 Total events: {generator.stats['total_events_generated']:,}")
        print(f"📁 Output location: {args.out}")
        print(f"⏱️  Total time: {time.time() - generator.start_time:.1f}s")
        print(f"\n🔍 Check generation_summary.json for detailed statistics")

    except Exception as e:
        logger.error(f"Event generation failed: {e}", exc_info=True)
        print(f"\n❌ Event generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
