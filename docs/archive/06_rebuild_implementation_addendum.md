# Fidelity PlanAlign Engine Rebuild - Implementation Addendum

**Date**: 2025-06-21
**Version**: 2.0 Final Implementation Guide
**Purpose**: Complete technical blueprint for Claude Code implementation

---

## 1. Exact Connection Patterns

### 1.1 Required DuckDBResource Implementation
```python
# orchestrator/resources.py
from dagster import ConfigurableResource
from contextlib import contextmanager
import duckdb
from pydantic import Field
from typing import Generator

class DuckDBResource(ConfigurableResource):
    """Primary DuckDB resource - REQUIRED pattern for ALL database operations."""

    database_path: str = Field(
        default="data/planwise.duckdb",
        description="Path to DuckDB database file"
    )
    memory_limit: str = Field(
        default="6GB",
        description="Memory limit for DuckDB operations"
    )
    threads: int = Field(
        default=4,
        description="Number of threads for parallel processing"
    )
    temp_directory: str = Field(
        default="tmp/",
        description="Temporary directory for DuckDB operations"
    )
    enable_profiling: bool = Field(
        default=False,
        description="Enable query profiling for performance monitoring"
    )

    @contextmanager
    def get_connection(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Context manager ensuring proper connection lifecycle."""
        conn = None
        try:
            # Create connection with configuration
            conn = duckdb.connect(self.database_path)

            # Apply performance settings
            conn.execute(f"SET memory_limit = '{self.memory_limit}'")
            conn.execute(f"SET threads = {self.threads}")
            conn.execute(f"SET temp_directory = '{self.temp_directory}'")

            if self.enable_profiling:
                conn.execute("PRAGMA enable_profiling = 'json'")

            yield conn

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass  # Ignore close errors

# definitions.py - Resource Configuration
from dagster import Definitions
from dagster_dbt import DbtCliResource

defs = Definitions(
    assets=[
        # All assets imported here
    ],
    resources={
        "duckdb_resource": DuckDBResource(
            database_path="data/planwise.duckdb",
            memory_limit="6GB",
            threads=4,
            temp_directory="tmp/",
            enable_profiling=True
        ),
        "dbt": DbtCliResource(
            project_dir="dbt/",
            profiles_dir="dbt/",
            target="dev"
        )
    }
)
```

### 1.2 Standard Asset Connection Pattern
```python
# REQUIRED TEMPLATE - Use for ALL DuckDB assets
from dagster import asset, AssetExecutionContext
import pandas as pd
from typing import Dict, Any, List
from orchestrator.resources import DuckDBResource

@asset
def standard_workforce_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Standard pattern for all DuckDB operations."""

    with duckdb_resource.get_connection() as conn:
        # Step 1: Execute SQL query
        query = """
        SELECT
            employee_id,
            level_id,
            current_compensation,
            simulation_year
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025
        """

        # Step 2: Convert to DataFrame IMMEDIATELY
        df = conn.execute(query).df()

        # Step 3: Validate and log
        if df.empty:
            context.log.warning("Query returned empty results")
            return pd.DataFrame(columns=['employee_id', 'level_id', 'current_compensation', 'simulation_year'])

        # Step 4: Add metadata for debugging
        context.add_output_metadata({
            "row_count": len(df),
            "columns": list(df.columns),
            "query": query,
            "sample_data": df.head(3).to_dict('records')
        })

        context.log.info(f"Processed {len(df)} workforce records")

        # Step 5: Return serializable DataFrame
        return df
```

---

## 2. Code Templates for Common Asset Patterns

### 2.1 Configuration-Driven Asset
```python
from pydantic import BaseModel, Field, validator
from typing import Dict, Any

class SimulationConfig(BaseModel):
    """Validated simulation configuration."""

    start_year: int = Field(..., ge=2020, le=2050)
    end_year: int = Field(..., ge=2020, le=2050)
    target_growth_rate: float = Field(0.03, ge=-0.5, le=0.5)
    total_termination_rate: float = Field(0.12, ge=0.0, le=1.0)
    new_hire_termination_rate: float = Field(0.25, ge=0.0, le=1.0)
    random_seed: int = Field(42, ge=1)
    batch_size: int = Field(10000, ge=1000)

    @validator('end_year')
    def validate_year_range(cls, v, values):
        if 'start_year' in values and v <= values['start_year']:
            raise ValueError('end_year must be after start_year')
        return v

    class Config:
        json_encoders = {
            pd.Timestamp: lambda v: v.isoformat()
        }

@asset
def simulation_config_asset(
    context: AssetExecutionContext,
    config: SimulationConfig,
    duckdb_resource: DuckDBResource
) -> Dict[str, Any]:
    """Store and validate simulation configuration."""

    with duckdb_resource.get_connection() as conn:
        # Store configuration in database
        conn.execute("""
        CREATE TABLE IF NOT EXISTS simulation_config (
            parameter_name VARCHAR,
            parameter_value VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Clear existing config
        conn.execute("DELETE FROM simulation_config")

        # Insert new configuration
        config_items = [
            ("start_year", str(config.start_year)),
            ("end_year", str(config.end_year)),
            ("target_growth_rate", str(config.target_growth_rate)),
            ("total_termination_rate", str(config.total_termination_rate)),
            ("random_seed", str(config.random_seed))
        ]

        conn.executemany(
            "INSERT INTO simulation_config (parameter_name, parameter_value) VALUES (?, ?)",
            config_items
        )

        context.log.info(f"Stored configuration: {config.start_year}-{config.end_year}")

        # Return serializable dictionary
        return config.dict()
```

### 2.2 Data Processing Asset
```python
@asset(deps=[simulation_config_asset])
def baseline_workforce_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Load and validate baseline workforce data."""

    with duckdb_resource.get_connection() as conn:
        # Validate configuration exists
        config_count = conn.execute(
            "SELECT COUNT(*) FROM simulation_config"
        ).fetchone()[0]

        if config_count == 0:
            raise ValueError("Configuration not found - run simulation_config_asset first")

        # Load baseline workforce
        df = conn.execute("""
        SELECT
            employee_id,
            level_id,
            age,
            tenure,
            compensation,
            hire_date::DATE as hire_date
        FROM stg_census_data
        WHERE active_flag = true
        """).df()

        # Data validation
        if df.empty:
            raise ValueError("No active employees in baseline data")

        # Data quality checks
        null_counts = df.isnull().sum()
        if null_counts.any():
            context.log.warning(f"Found null values: {null_counts[null_counts > 0].to_dict()}")

        # Store processed data
        conn.register('baseline_temp', df)
        conn.execute("""
        CREATE OR REPLACE TABLE baseline_workforce AS
        SELECT * FROM baseline_temp
        """)

        context.add_output_metadata({
            "baseline_count": len(df),
            "validation_passed": True,
            "processing_date": pd.Timestamp.now().isoformat()
        })

        return df
```

### 2.3 dbt Integration Asset
```python
from dagster_dbt import DbtCliResource

@asset
def dbt_workforce_models(
    context: AssetExecutionContext,
    dbt: DbtCliResource
) -> Dict[str, Any]:
    """Execute dbt models with proper error handling."""

    # Run dbt models
    dbt_run_result = dbt.cli(
        ["run", "--select", "marts.fct_workforce_snapshot"],
        context=context
    ).wait()

    # Check execution status
    if dbt_run_result.process is None or dbt_run_result.process.returncode != 0:
        context.log.error("dbt run failed")
        raise RuntimeError(f"dbt execution failed with return code: {dbt_run_result.process.returncode}")

    # Run tests
    dbt_test_result = dbt.cli(
        ["test", "--select", "marts.fct_workforce_snapshot"],
        context=context
    ).wait()

    test_success = (
        dbt_test_result.process is not None and
        dbt_test_result.process.returncode == 0
    )

    if not test_success:
        context.log.warning("dbt tests failed - check data quality")

    return {
        "run_success": True,
        "test_success": test_success,
        "execution_time": pd.Timestamp.now().isoformat(),
        "models_executed": ["fct_workforce_snapshot"]
    }

@asset(deps=[dbt_workforce_models])
def post_dbt_analytics(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Analyze dbt outputs - NEVER return dbt objects."""

    with duckdb_resource.get_connection() as conn:
        # Query materialized dbt table
        df = conn.execute("""
        SELECT
            simulation_year,
            level_id,
            COUNT(*) as headcount,
            AVG(current_compensation) as avg_compensation
        FROM fct_workforce_snapshot
        GROUP BY simulation_year, level_id
        ORDER BY simulation_year, level_id
        """).df()

        # Add calculated metrics
        df['compensation_growth'] = df.groupby('level_id')['avg_compensation'].pct_change()

        context.log.info(f"Generated analytics for {len(df)} year-level combinations")

        return df
```

### 2.4 Batch Processing Asset
```python
@asset
def large_dataset_processor(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    config: SimulationConfig
) -> Dict[str, int]:
    """Process large datasets with memory efficiency."""

    with duckdb_resource.get_connection() as conn:
        # Get total record count
        total_count = conn.execute(
            "SELECT COUNT(*) FROM employees WHERE active_flag = true"
        ).fetchone()[0]

        context.log.info(f"Processing {total_count} records in batches of {config.batch_size}")

        # Initialize results
        processed_count = 0
        level_summaries = {}

        # Process in batches using cursor
        cursor = conn.cursor()
        cursor.execute("""
        SELECT level_id, current_compensation, age, tenure
        FROM employees
        WHERE active_flag = true
        ORDER BY employee_id
        """)

        while True:
            # Fetch batch
            batch = cursor.fetchmany(config.batch_size)
            if not batch:
                break

            # Convert to DataFrame for processing
            batch_df = pd.DataFrame(
                batch,
                columns=['level_id', 'current_compensation', 'age', 'tenure']
            )

            # Process batch
            batch_summary = batch_df.groupby('level_id').agg({
                'current_compensation': ['count', 'mean'],
                'age': 'mean',
                'tenure': 'mean'
            }).round(2)

            # Aggregate results
            for level_id in batch_summary.index:
                if level_id not in level_summaries:
                    level_summaries[level_id] = {
                        'count': 0,
                        'total_compensation': 0,
                        'total_age': 0,
                        'total_tenure': 0
                    }

                level_summaries[level_id]['count'] += int(batch_summary.loc[level_id, ('current_compensation', 'count')])
                level_summaries[level_id]['total_compensation'] += float(batch_summary.loc[level_id, ('current_compensation', 'mean')]) * int(batch_summary.loc[level_id, ('current_compensation', 'count')])
                level_summaries[level_id]['total_age'] += float(batch_summary.loc[level_id, ('age', 'mean')]) * int(batch_summary.loc[level_id, ('current_compensation', 'count')])
                level_summaries[level_id]['total_tenure'] += float(batch_summary.loc[level_id, ('tenure', 'mean')]) * int(batch_summary.loc[level_id, ('current_compensation', 'count')])

            processed_count += len(batch)
            context.log.info(f"Processed batch: {processed_count}/{total_count}")

        cursor.close()

        # Calculate final averages
        final_results = {}
        for level_id, data in level_summaries.items():
            final_results[int(level_id)] = {
                'count': data['count'],
                'avg_compensation': round(data['total_compensation'] / data['count'], 2),
                'avg_age': round(data['total_age'] / data['count'], 1),
                'avg_tenure': round(data['total_tenure'] / data['count'], 1)
            }

        context.add_output_metadata({
            "total_processed": processed_count,
            "levels_analyzed": len(final_results),
            "batch_size": config.batch_size
        })

        return final_results
```

---

## 3. Debugging Guide for Serialization Issues

### 3.1 Debug Helper Functions
```python
# orchestrator/debug_helpers.py
from dagster import AssetExecutionContext
import pandas as pd
import pickle
import json
from typing import Any

def debug_serialization(context: AssetExecutionContext, output: Any, asset_name: str):
    """Comprehensive serialization debugging."""

    output_type = type(output).__name__
    context.log.info(f"🔍 Debugging {asset_name} output type: {output_type}")

    # Test pickle serialization (Dagster uses this)
    try:
        pickled = pickle.dumps(output)
        context.log.info(f"✅ Pickle serialization: OK ({len(pickled)} bytes)")
    except Exception as e:
        context.log.error(f"❌ Pickle serialization failed: {str(e)}")
        context.log.error(f"   Type: {type(output)}")
        if hasattr(output, '__dict__'):
            context.log.error(f"   Attributes: {list(output.__dict__.keys())}")

    # Test JSON serialization (metadata)
    try:
        if isinstance(output, pd.DataFrame):
            json_str = output.to_json()
        else:
            json_str = json.dumps(output, default=str)
        context.log.info(f"✅ JSON serialization: OK")
    except Exception as e:
        context.log.error(f"❌ JSON serialization failed: {str(e)}")

    # Type-specific debugging
    if isinstance(output, pd.DataFrame):
        debug_dataframe(context, output)
    elif isinstance(output, dict):
        debug_dict(context, output)
    elif hasattr(output, '__module__') and 'duckdb' in output.__module__:
        context.log.error(f"🚨 FOUND DUCKDB OBJECT: {type(output)} - THIS WILL CAUSE SERIALIZATION ERRORS!")
        context.log.error("   Solution: Convert to DataFrame with .df() or fetchall()")

def debug_dataframe(context: AssetExecutionContext, df: pd.DataFrame):
    """Debug DataFrame serialization issues."""

    context.log.info(f"📊 DataFrame: {df.shape[0]} rows, {df.shape[1]} columns")
    context.log.info(f"   Columns: {list(df.columns)}")

    # Check for problematic data types
    for col in df.columns:
        dtype = df[col].dtype
        context.log.info(f"   {col}: {dtype}")

        if dtype == 'object':
            # Check for non-serializable objects in object columns
            sample_values = df[col].dropna().head(3)
            for i, val in enumerate(sample_values):
                if hasattr(val, '__module__') and 'duckdb' in str(type(val)):
                    context.log.error(f"🚨 Found DuckDB object in column {col}: {type(val)}")

            context.log.info(f"   {col} samples: {sample_values.tolist()}")

    # Check for null values
    null_counts = df.isnull().sum()
    if null_counts.any():
        context.log.info(f"   Null values: {null_counts[null_counts > 0].to_dict()}")

def debug_dict(context: AssetExecutionContext, data: dict):
    """Debug dictionary serialization issues."""

    context.log.info(f"📘 Dictionary: {len(data)} keys")

    for key, value in data.items():
        value_type = type(value).__name__
        context.log.info(f"   {key}: {value_type}")

        # Check for DuckDB objects
        if hasattr(value, '__module__') and 'duckdb' in str(type(value)):
            context.log.error(f"🚨 Found DuckDB object at key '{key}': {type(value)}")

        # Check nested structures
        if isinstance(value, (list, tuple)) and len(value) > 0:
            first_item_type = type(value[0]).__name__
            context.log.info(f"     First item type: {first_item_type}")

# Usage in assets
@asset
def debug_enabled_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Example asset with debugging enabled."""

    with duckdb_resource.get_connection() as conn:
        df = conn.execute("SELECT * FROM employees LIMIT 100").df()

        # Debug the output before returning
        debug_serialization(context, df, "debug_enabled_asset")

        return df
```

### 3.2 Common Serialization Problems & Solutions
```python
# orchestrator/serialization_fixes.py

def fix_duckdb_types(df: pd.DataFrame) -> pd.DataFrame:
    """Fix common DuckDB type issues that cause serialization problems."""

    # Convert numpy types to native Python types
    for col in df.columns:
        if df[col].dtype == 'int64':
            df[col] = df[col].astype('int32')  # Smaller, more compatible
        elif df[col].dtype == 'float64':
            df[col] = df[col].astype('float32')  # Smaller, more compatible
        elif df[col].dtype == 'object':
            # Handle mixed types in object columns
            df[col] = df[col].astype(str)

    # Handle datetime columns
    datetime_cols = df.select_dtypes(include=['datetime64']).columns
    for col in datetime_cols:
        df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')

    # Handle date columns
    date_cols = df.select_dtypes(include=['datetime64[ns]']).columns
    for col in date_cols:
        if df[col].dt.time.eq(pd.Timestamp('00:00:00').time()).all():
            df[col] = df[col].dt.strftime('%Y-%m-%d')

    return df

def validate_output_serializable(output: Any) -> bool:
    """Validate that output is serializable before returning from asset."""

    try:
        # Test pickle serialization
        pickle.dumps(output)
        return True
    except Exception as e:
        print(f"Serialization validation failed: {str(e)}")
        return False

# Example usage in asset
@asset
def serialization_safe_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Asset that ensures serialization safety."""

    with duckdb_resource.get_connection() as conn:
        # Get raw data
        df = conn.execute("""
        SELECT
            employee_id,
            level_id,
            current_compensation,
            hire_date
        FROM employees
        """).df()

        # Fix potential serialization issues
        df = fix_duckdb_types(df)

        # Validate before returning
        if not validate_output_serializable(df):
            context.log.error("Output failed serialization validation")
            debug_serialization(context, df, "serialization_safe_asset")
            raise ValueError("Asset output is not serializable")

        context.log.info(f"✅ Output validated as serializable: {len(df)} records")
        return df
```

---

## 4. Comprehensive Mocking Strategies for Testing

### 4.1 DuckDB Resource Mocking
```python
# tests/conftest.py
import pytest
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
from orchestrator.resources import DuckDBResource

@pytest.fixture
def mock_duckdb_resource():
    """Mock DuckDBResource for unit testing."""

    # Create mock resource
    mock_resource = Mock(spec=DuckDBResource)

    # Create mock connection
    mock_conn = MagicMock()

    # Setup context manager behavior
    mock_context = MagicMock()
    mock_context.__enter__ = Mock(return_value=mock_conn)
    mock_context.__exit__ = Mock(return_value=None)
    mock_resource.get_connection.return_value = mock_context

    return mock_resource, mock_conn

@pytest.fixture
def sample_employee_data():
    """Sample employee data for testing."""

    return pd.DataFrame({
        'employee_id': ['E001', 'E002', 'E003', 'E004'],
        'level_id': [1, 2, 1, 3],
        'current_compensation': [50000, 75000, 52000, 95000],
        'age': [25, 30, 28, 35],
        'tenure': [2, 5, 3, 8],
        'active_flag': [True, True, True, False]
    })

@pytest.fixture
def mock_duckdb_execute():
    """Mock DuckDB execute method with realistic return patterns."""

    def _mock_execute(query: str, sample_data: pd.DataFrame):
        mock_result = Mock()

        # Simulate different query patterns
        if "COUNT(*)" in query:
            mock_result.fetchone.return_value = (len(sample_data),)
            return mock_result
        elif "SELECT" in query and "employees" in query:
            mock_result.df.return_value = sample_data
            return mock_result
        else:
            mock_result.df.return_value = pd.DataFrame()
            return mock_result

    return _mock_execute
```

### 4.2 Asset Testing Patterns
```python
# tests/test_assets.py
import pytest
from dagster import build_asset_context, materialize
from unittest.mock import Mock, patch
import pandas as pd

def test_baseline_workforce_asset(mock_duckdb_resource, sample_employee_data):
    """Test baseline workforce asset with mocked database."""

    mock_resource, mock_conn = mock_duckdb_resource

    # Setup mock query responses
    def mock_execute(query):
        mock_result = Mock()
        if "COUNT(*)" in query:
            mock_result.fetchone.return_value = (5,)  # Config exists
        else:
            mock_result.df.return_value = sample_employee_data[sample_employee_data['active_flag']]
        return mock_result

    mock_conn.execute = mock_execute
    mock_conn.register = Mock()

    # Import and test asset
    from orchestrator.assets import baseline_workforce_asset

    context = build_asset_context()
    result = baseline_workforce_asset(context, mock_resource)

    # Validate results
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 3  # Only active employees
    assert 'employee_id' in result.columns

    # Verify database interactions
    mock_conn.execute.assert_called()
    mock_conn.register.assert_called_once()

def test_simulation_config_asset():
    """Test configuration asset with validation."""

    from orchestrator.assets import simulation_config_asset, SimulationConfig

    # Valid configuration
    config = SimulationConfig(
        start_year=2025,
        end_year=2030,
        target_growth_rate=0.03
    )

    # Mock resource
    mock_resource = Mock()
    mock_conn = Mock()
    mock_resource.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_resource.get_connection.return_value.__exit__ = Mock(return_value=None)

    context = build_asset_context()
    result = simulation_config_asset(context, config, mock_resource)

    # Validate results
    assert isinstance(result, dict)
    assert result['start_year'] == 2025
    assert result['end_year'] == 2030

    # Verify database operations
    mock_conn.execute.assert_called()
    mock_conn.executemany.assert_called_once()

def test_serialization_compliance():
    """Test that all common output types are serializable."""

    import pickle

    # Test cases
    test_outputs = [
        pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']}),
        {'key': 'value', 'count': 42, 'rate': 0.15},
        [{'id': 1, 'name': 'test'}, {'id': 2, 'name': 'test2'}],
        42,
        'string_value',
        [1, 2, 3, 4, 5]
    ]

    for output in test_outputs:
        try:
            pickled = pickle.dumps(output)
            assert len(pickled) > 0
        except Exception as e:
            pytest.fail(f"Serialization failed for {type(output)}: {str(e)}")
```

### 4.3 Integration Testing with Real Database
```python
# tests/test_integration.py
import pytest
import os
import tempfile
from dagster import materialize
from orchestrator.resources import DuckDBResource
from orchestrator.assets import SimulationConfig

@pytest.fixture
def temp_database():
    """Create temporary database for integration testing."""

    with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
        db_path = f.name

    # Create test resource
    test_resource = DuckDBResource(
        database_path=db_path,
        memory_limit="1GB",
        threads=2
    )

    # Setup test schema
    with test_resource.get_connection() as conn:
        conn.execute("""
        CREATE TABLE employees (
            employee_id VARCHAR,
            level_id INTEGER,
            current_compensation DECIMAL,
            age INTEGER,
            tenure INTEGER,
            active_flag BOOLEAN,
            hire_date DATE
        )
        """)

        conn.execute("""
        INSERT INTO employees VALUES
        ('E001', 1, 50000, 25, 2, true, '2023-01-01'),
        ('E002', 2, 75000, 30, 5, true, '2020-06-15'),
        ('E003', 1, 52000, 28, 3, true, '2022-03-10'),
        ('E004', 3, 95000, 35, 8, false, '2017-09-20')
        """)

        conn.execute("""
        CREATE TABLE job_levels (
            level_id INTEGER,
            level_name VARCHAR,
            min_salary DECIMAL,
            max_salary DECIMAL
        )
        """)

        conn.execute("""
        INSERT INTO job_levels VALUES
        (1, 'Junior', 40000, 60000),
        (2, 'Senior', 60000, 90000),
        (3, 'Principal', 80000, 120000)
        """)

    yield test_resource

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass

def test_full_pipeline_integration(temp_database):
    """Test complete pipeline with real database."""

    # Import assets
    from orchestrator.assets import (
        simulation_config_asset,
        baseline_workforce_asset
    )

    # Test configuration
    config = SimulationConfig(
        start_year=2025,
        end_year=2027,
        target_growth_rate=0.03
    )

    # Execute pipeline
    result = materialize(
        [simulation_config_asset, baseline_workforce_asset],
        resources={"duckdb_resource": temp_database},
        run_config={
            "ops": {
                "simulation_config_asset": {
                    "config": config.dict()
                }
            }
        }
    )

    # Validate pipeline success
    assert result.success

    # Validate individual outputs
    config_output = result.output_for_node("simulation_config_asset")
    assert config_output['start_year'] == 2025

    workforce_output = result.output_for_node("baseline_workforce_asset")
    assert len(workforce_output) == 3  # Only active employees
    assert list(workforce_output.columns) == ['employee_id', 'level_id', 'age', 'tenure', 'compensation', 'hire_date']

def test_error_handling_integration(temp_database):
    """Test error handling with real database."""

    from orchestrator.assets import baseline_workforce_asset
    from dagster import build_asset_context

    # Drop the employees table to trigger error
    with temp_database.get_connection() as conn:
        conn.execute("DROP TABLE employees")

    context = build_asset_context()

    # Should raise appropriate error
    with pytest.raises(Exception) as exc_info:
        baseline_workforce_asset(context, temp_database)

    assert "employees" in str(exc_info.value).lower()
```

### 4.4 Performance Testing Framework
```python
# tests/test_performance.py
import pytest
import time
import pandas as pd
from dagster import build_asset_context
from unittest.mock import Mock

def test_large_dataset_processing_performance():
    """Test performance with large dataset simulation."""

    # Create large sample dataset
    large_data = pd.DataFrame({
        'employee_id': [f'E{i:06d}' for i in range(50000)],
        'level_id': [i % 5 + 1 for i in range(50000)],
        'current_compensation': [50000 + (i % 10000) for i in range(50000)],
        'age': [25 + (i % 40) for i in range(50000)],
        'active_flag': [True] * 50000
    })

    # Mock resource with large dataset
    mock_resource = Mock()
    mock_conn = Mock()
    mock_resource.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_resource.get_connection.return_value.__exit__ = Mock(return_value=None)

    # Simulate batch processing
    batch_size = 10000
    def mock_fetchmany(size):
        if not hasattr(mock_fetchmany, 'offset'):
            mock_fetchmany.offset = 0

        start = mock_fetchmany.offset
        end = min(start + size, len(large_data))

        if start >= len(large_data):
            return []

        batch = large_data.iloc[start:end].values.tolist()
        mock_fetchmany.offset = end
        return batch

    mock_cursor = Mock()
    mock_cursor.fetchmany = mock_fetchmany
    mock_conn.cursor.return_value = mock_cursor

    # Import and test asset
    from orchestrator.assets import large_dataset_processor, SimulationConfig

    config = SimulationConfig(batch_size=batch_size)
    context = build_asset_context()

    # Measure execution time
    start_time = time.time()
    result = large_dataset_processor(context, mock_resource, config)
    execution_time = time.time() - start_time

    # Performance assertions
    assert execution_time < 10.0  # Should complete in under 10 seconds
    assert isinstance(result, dict)
    assert len(result) > 0  # Should have processed some levels

    print(f"Processed 50K records in {execution_time:.2f} seconds")

@pytest.mark.parametrize("batch_size", [1000, 5000, 10000, 25000])
def test_batch_size_optimization(batch_size):
    """Test different batch sizes for optimal performance."""

    # Create test data
    test_data = pd.DataFrame({
        'level_id': [i % 3 + 1 for i in range(batch_size * 3)],
        'current_compensation': [50000 + i for i in range(batch_size * 3)]
    })

    # Mock processing
    start_time = time.time()

    # Simulate batch processing
    processed_count = 0
    for i in range(0, len(test_data), batch_size):
        batch = test_data.iloc[i:i+batch_size]
        processed_count += len(batch)
        # Simulate processing time
        time.sleep(0.001)  # 1ms per batch

    processing_time = time.time() - start_time

    # Record performance metrics
    print(f"Batch size {batch_size}: {processing_time:.3f}s for {processed_count} records")

    assert processed_count == len(test_data)
    assert processing_time < 1.0  # Should be fast for test data
```

---

## 5. Deployment Validation Script

```python
# scripts/validate_deployment.py
#!/usr/bin/env python3
"""
Comprehensive deployment validation for Fidelity PlanAlign Engine.
Run this before deploying to catch serialization and configuration issues.
"""

import sys
import os
import traceback
import pandas as pd
import pickle
import json
from typing import List, Dict, Any
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def validate_serialization_compliance() -> List[str]:
    """Test serialization of common data types."""

    issues = []

    test_cases = [
        ("DataFrame", pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})),
        ("Dictionary", {'key': 'value', 'number': 42, 'float': 3.14}),
        ("List of dicts", [{'id': 1, 'name': 'test'}, {'id': 2, 'name': 'test2'}]),
        ("Integer", 42),
        ("String", "test_string"),
        ("List", [1, 2, 3, 4, 5]),
        ("Nested dict", {'data': {'metrics': [1, 2, 3]}, 'timestamp': '2025-01-01'})
    ]

    for name, obj in test_cases:
        try:
            # Test pickle (Dagster internal)
            pickle.dumps(obj)

            # Test JSON (metadata)
            if hasattr(obj, 'to_json'):
                obj.to_json()
            else:
                json.dumps(obj, default=str)

            print(f"✅ {name}: Serialization OK")

        except Exception as e:
            issues.append(f"❌ {name}: {str(e)}")

    return issues

def validate_duckdb_patterns() -> List[str]:
    """Validate DuckDB connection patterns."""

    issues = []

    try:
        import duckdb

        # Test basic connection
        conn = duckdb.connect(":memory:")
        result = conn.execute("SELECT 1 as test").fetchone()

        if result[0] != 1:
            issues.append("Basic DuckDB query failed")

        conn.close()
        print("✅ DuckDB basic connection: OK")

        # Test context manager pattern
        with duckdb.connect(":memory:") as test_conn:
            df = test_conn.execute("SELECT 1 as col1, 'test' as col2").df()

            # Test serialization of DuckDB DataFrame
            pickle.dumps(df)

        print("✅ DuckDB context manager: OK")
        print("✅ DuckDB DataFrame serialization: OK")

    except Exception as e:
        issues.append(f"DuckDB validation failed: {str(e)}")

    return issues

def validate_pydantic_models() -> List[str]:
    """Validate Pydantic configuration models."""

    issues = []

    try:
        from orchestrator.assets import SimulationConfig

        # Test valid configuration
        config = SimulationConfig(
            start_year=2025,
            end_year=2030,
            target_growth_rate=0.03
        )

        # Test serialization
        config_dict = config.dict()
        json.dumps(config_dict)
        pickle.dumps(config_dict)

        print("✅ Pydantic model validation: OK")
        print("✅ Pydantic serialization: OK")

        # Test invalid configuration
        try:
            invalid_config = SimulationConfig(
                start_year=2030,
                end_year=2025,  # Invalid: end before start
                target_growth_rate=0.03
            )
            issues.append("Pydantic validation failed to catch invalid config")
        except ValueError:
            print("✅ Pydantic validation catches errors: OK")

    except Exception as e:
        issues.append(f"Pydantic model validation failed: {str(e)}")

    return issues

def validate_asset_imports() -> List[str]:
    """Validate that all assets can be imported."""

    issues = []

    try:
        # Test asset imports
        from orchestrator.assets import (
            simulation_config_asset,
            baseline_workforce_asset,
            dbt_workforce_models,
            post_dbt_analytics
        )

        print("✅ Asset imports: OK")

        # Test resource import
        from orchestrator.resources import DuckDBResource

        print("✅ Resource imports: OK")

    except Exception as e:
        issues.append(f"Import validation failed: {str(e)}")
        issues.append(f"Traceback: {traceback.format_exc()}")

    return issues

def validate_dagster_definitions() -> List[str]:
    """Validate Dagster definitions."""

    issues = []

    try:
        from definitions import defs

        # Check that definitions object exists
        if not hasattr(defs, 'assets'):
            issues.append("Definitions missing assets")

        if not hasattr(defs, 'resources'):
            issues.append("Definitions missing resources")

        # Check required resources
        required_resources = ['duckdb_resource', 'dbt']
        for resource in required_resources:
            if resource not in defs.resources:
                issues.append(f"Missing required resource: {resource}")

        print("✅ Dagster definitions: OK")

    except Exception as e:
        issues.append(f"Dagster definitions validation failed: {str(e)}")

    return issues

def validate_file_structure() -> List[str]:
    """Validate required file structure."""

    issues = []

    required_files = [
        "definitions.py",
        "requirements.txt",
        "orchestrator/__init__.py",
        "orchestrator/assets.py",
        "orchestrator/resources.py",
        "dbt/dbt_project.yml",
        "dbt/profiles.yml"
    ]

    for file_path in required_files:
        full_path = project_root / file_path
        if not full_path.exists():
            issues.append(f"Missing required file: {file_path}")
        else:
            print(f"✅ File exists: {file_path}")

    return issues

def run_all_validations() -> bool:
    """Run all deployment validations."""

    print("🔍 Running Fidelity PlanAlign Engine deployment validation...")
    print("=" * 60)

    all_issues = []

    # File structure validation
    print("\n📁 Validating file structure...")
    file_issues = validate_file_structure()
    all_issues.extend(file_issues)

    # Import validation
    print("\n📦 Validating imports...")
    import_issues = validate_asset_imports()
    all_issues.extend(import_issues)

    # Serialization validation
    print("\n🔄 Validating serialization...")
    serialization_issues = validate_serialization_compliance()
    all_issues.extend(serialization_issues)

    # DuckDB validation
    print("\n🦆 Validating DuckDB patterns...")
    duckdb_issues = validate_duckdb_patterns()
    all_issues.extend(duckdb_issues)

    # Pydantic validation
    print("\n⚙️ Validating Pydantic models...")
    pydantic_issues = validate_pydantic_models()
    all_issues.extend(pydantic_issues)

    # Dagster validation
    print("\n🏗️ Validating Dagster definitions...")
    dagster_issues = validate_dagster_definitions()
    all_issues.extend(dagster_issues)

    # Final report
    print("\n" + "=" * 60)

    if all_issues:
        print("❌ DEPLOYMENT VALIDATION FAILED")
        print("\nIssues found:")
        for issue in all_issues:
            print(f"  • {issue}")
        return False
    else:
        print("✅ ALL DEPLOYMENT VALIDATIONS PASSED!")
        print("\n🚀 Ready for deployment!")
        return True

if __name__ == "__main__":
    success = run_all_validations()
    sys.exit(0 if success else 1)
```

---

## 6. Implementation Checklist

### Pre-Development Setup
- [ ] Create virtual environment with `requirements.txt`
- [ ] Setup project directory structure
- [ ] Initialize git repository
- [ ] Create `.gitignore` for data files and cache

### Phase 1: Foundation
- [ ] Implement `DuckDBResource` with exact pattern
- [ ] Create `SimulationConfig` Pydantic model
- [ ] Setup basic asset templates
- [ ] Implement debugging helpers
- [ ] Create deployment validation script
- [ ] Setup testing framework with mocks

### Phase 2: Core Assets
- [ ] Build `simulation_config_asset`
- [ ] Build `baseline_workforce_asset`
- [ ] Build `dbt_workforce_models`
- [ ] Build `post_dbt_analytics`
- [ ] Add comprehensive error handling
- [ ] Add asset checks and validation

### Phase 3: Testing & Validation
- [ ] Unit tests with mocked DuckDB
- [ ] Integration tests with real database
- [ ] Performance tests with large datasets
- [ ] Serialization compliance validation
- [ ] End-to-end pipeline testing

### Phase 4: Production Ready
- [ ] All assets pass deployment validation
- [ ] Performance benchmarks met
- [ ] Error handling tested
- [ ] Documentation complete
- [ ] Ready for deployment

This implementation addendum provides the complete technical blueprint for rebuilding Fidelity PlanAlign Engine with bulletproof DuckDB integration, comprehensive testing, and proper serialization handling.
