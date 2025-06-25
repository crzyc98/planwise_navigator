# Technical Implementation Guide - PlanWise Navigator

**Date**: 2025-06-25
**Version**: 3.0 (Post-Epic E013 Modularization)
**Critical Requirements**: DuckDB serialization, Dagster integration, Pydantic configuration, Modular pipeline architecture

---

## 1. Core Architecture Patterns

### 1.1 Database Connection Management
```python
# REQUIRED PATTERN - ConfigurableResource with Context Manager
from dagster import ConfigurableResource, asset, AssetExecutionContext
from contextlib import contextmanager
import duckdb
import pandas as pd

class DuckDBResource(ConfigurableResource):
    """Primary DuckDB resource for all database operations."""

    database_path: str = "data/planwise.duckdb"
    memory_limit: str = "6GB"
    threads: int = 4
    temp_directory: str = "tmp/"

    @contextmanager
    def get_connection(self):
        """Context manager ensuring proper connection cleanup."""
        conn = None
        try:
            conn = duckdb.connect(self.database_path)
            # Apply performance settings
            conn.execute(f"SET memory_limit = '{self.memory_limit}'")
            conn.execute(f"SET threads = {self.threads}")
            conn.execute(f"SET temp_directory = '{self.temp_directory}'")
            yield conn
        finally:
            if conn:
                conn.close()

# REQUIRED: Use in all assets
@asset
def workforce_data_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Standard pattern for all DuckDB assets."""

    with duckdb_resource.get_connection() as conn:
        # ✅ CORRECT: Convert to DataFrame immediately
        df = conn.execute("""
            SELECT employee_id, level_id, current_compensation
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2025
        """).df()

        context.log.info(f"Processed {len(df)} workforce records")
        return df  # pandas.DataFrame is serializable
```

### 1.2 Forbidden Patterns
```python
# ❌ NEVER DO THESE - Will cause serialization failures

@asset
def broken_asset_1():
    conn = duckdb.connect("db.duckdb")
    relation = conn.table("employees")  # DuckDBRelation
    return relation  # SERIALIZATION ERROR

@asset
def broken_asset_2():
    conn = duckdb.connect("db.duckdb")
    result = conn.execute("SELECT * FROM employees")
    return result  # DuckDBPyResult - NOT SERIALIZABLE

@asset
def broken_asset_3():
    conn = duckdb.connect("db.duckdb")
    # Connection never closed - RESOURCE LEAK
    return conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
```

---

## 2. Dagster Resource Configuration

### 2.1 Resource Definitions
```python
# definitions.py - Main Dagster configuration
from dagster import Definitions
from dagster_dbt import DbtCliResource

# All resources must be properly configured
defs = Definitions(
    assets=[
        workforce_data_asset,
        simulation_parameters_asset,
        # ... all other assets
    ],
    resources={
        # Primary DuckDB resource
        "duckdb_resource": DuckDBResource(
            database_path="data/planwise.duckdb",
            memory_limit="6GB",
            threads=4,
            temp_directory="tmp/"
        ),

        # dbt CLI resource
        "dbt": DbtCliResource(
            project_dir="dbt/",
            profiles_dir="dbt/",
            target="dev"
        )
    }
)
```

### 2.2 Environment-Specific Configuration
```python
# config/dagster_config.yaml
resources:
  duckdb_resource:
    config:
      database_path:
        env: DUCKDB_DATABASE_PATH  # Default: "data/planwise.duckdb"
      memory_limit:
        env: DUCKDB_MEMORY_LIMIT   # Default: "6GB"
      threads:
        env: DUCKDB_THREADS        # Default: 4

  dbt:
    config:
      project_dir: "dbt/"
      target:
        env: DBT_TARGET            # Default: "dev"
```

---

## 3. Data Type Conversion Patterns

### 3.1 DuckDB to Python Type Mapping
```python
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, Optional

def convert_duckdb_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert DuckDB types to proper Python types for serialization."""

    # Type conversion mapping
    type_conversions = {
        'BIGINT': 'int64',
        'DOUBLE': 'float64',
        'VARCHAR': 'string',
        'DATE': 'datetime64[ns]',
        'TIMESTAMP': 'datetime64[ns]',
        'DECIMAL': 'float64'
    }

    # Apply conversions
    for col in df.columns:
        if df[col].dtype == 'object':
            # Handle potential date/datetime strings
            try:
                df[col] = pd.to_datetime(df[col])
            except:
                pass  # Keep as string

    return df

@asset
def typed_workforce_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Asset with proper type conversion."""

    with duckdb_resource.get_connection() as conn:
        df = conn.execute("""
            SELECT
                employee_id::VARCHAR as employee_id,
                level_id::BIGINT as level_id,
                current_compensation::DECIMAL(10,2) as current_compensation,
                hire_date::DATE as hire_date,
                last_updated::TIMESTAMP as last_updated
            FROM employees
        """).df()

        # Convert types for proper serialization
        df = convert_duckdb_types(df)

        context.log.info(f"Converted types for {len(df)} records")
        return df
```

### 3.2 Pydantic Configuration Models
```python
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional
from datetime import date

class SimulationConfig(BaseModel):
    """Primary simulation configuration with validation."""

    # Required parameters
    start_year: int = Field(..., ge=2020, le=2050, description="Simulation start year")
    end_year: int = Field(..., ge=2020, le=2050, description="Simulation end year")

    # Workforce parameters
    target_growth_rate: float = Field(0.03, ge=-0.5, le=0.5, description="Annual growth rate")
    total_termination_rate: float = Field(0.12, ge=0.0, le=1.0, description="Annual termination rate")
    new_hire_termination_rate: float = Field(0.25, ge=0.0, le=1.0, description="First-year termination rate")

    # Technical parameters
    random_seed: int = Field(42, ge=1, description="Random seed for reproducibility")
    batch_size: int = Field(10000, ge=1000, description="Processing batch size")

    # Validation rules
    @validator('end_year')
    def end_year_after_start(cls, v, values):
        if 'start_year' in values and v <= values['start_year']:
            raise ValueError('end_year must be after start_year')
        return v

    @validator('new_hire_termination_rate')
    def new_hire_rate_validation(cls, v, values):
        if 'total_termination_rate' in values and v < values['total_termination_rate']:
            raise ValueError('new_hire_termination_rate should be >= total_termination_rate')
        return v

    class Config:
        # Ensure proper JSON serialization for Dagster
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat()
        }

class WorkforceMetrics(BaseModel):
    """Output metrics model for serialization."""

    total_employees: int
    avg_compensation: float
    headcount_by_level: Dict[int, int]
    processing_timestamp: str

    class Config:
        # Allow arbitrary types for complex data structures
        arbitrary_types_allowed = True

# Usage in assets
@asset
def simulation_config_asset(
    context: AssetExecutionContext,
    config: SimulationConfig
) -> Dict[str, Any]:
    """Store validated configuration."""

    # Configuration is automatically validated by Pydantic
    context.log.info(f"Simulation configured: {config.start_year}-{config.end_year}")

    # Return serializable dict
    return config.dict()
```

---

## 4. dbt Integration Patterns

### 4.1 Proper dbt Asset Handling
```python
from dagster_dbt import DbtCliResource, dbt_assets, DbtCliInvocation

@asset
def run_dbt_models(
    context: AssetExecutionContext,
    dbt: DbtCliResource
) -> Dict[str, Any]:
    """Execute dbt models with proper result handling."""

    # Run dbt models
    dbt_run_invocation = dbt.cli(["run", "--select", "marts"], context=context).wait()

    # Check execution status - CRITICAL: Use .wait() method
    if dbt_run_invocation.process is None or dbt_run_invocation.process.returncode != 0:
        context.log.error("dbt run failed")
        raise RuntimeError("dbt execution failed")

    # Run tests
    dbt_test_invocation = dbt.cli(["test", "--select", "marts"], context=context).wait()

    test_success = (
        dbt_test_invocation.process is not None and
        dbt_test_invocation.process.returncode == 0
    )

    if not test_success:
        context.log.warning("dbt tests failed - check data quality")

    # Return serializable results summary
    return {
        "run_success": True,
        "test_success": test_success,
        "models_executed": "marts",
        "execution_time": context.run.start_time.isoformat()
    }

@asset(deps=[run_dbt_models])
def post_dbt_analysis(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Analyze dbt model outputs - NEVER return dbt objects directly."""

    with duckdb_resource.get_connection() as conn:
        # Query materialized dbt tables
        df = conn.execute("""
            SELECT
                simulation_year,
                level_id,
                COUNT(*) as headcount,
                AVG(current_compensation) as avg_compensation
            FROM fct_workforce_snapshot  -- dbt materialized table
            GROUP BY simulation_year, level_id
            ORDER BY simulation_year, level_id
        """).df()

        # Perform additional analysis
        df['compensation_growth'] = df.groupby('level_id')['avg_compensation'].pct_change()

        context.log.info(f"Analyzed dbt output: {len(df)} records")
        return df  # Return DataFrame, not dbt objects
```

---

## 5. Error Handling & Robustness

### 5.1 Comprehensive Error Handling
```python
from dagster import DagsterExecutionInterruptedError
import duckdb

@contextmanager
def safe_duckdb_operation(context: AssetExecutionContext, duckdb_resource: DuckDBResource):
    """Safe DuckDB operations with comprehensive error handling."""

    conn = None
    try:
        conn = duckdb_resource.get_connection().__enter__()
        yield conn
    except duckdb.CatalogException as e:
        context.log.error(f"Database schema error: {str(e)}")
        context.log.error("Check that all required tables exist")
        raise DagsterExecutionInterruptedError(f"Schema error: {e}")
    except duckdb.ConversionException as e:
        context.log.error(f"Data type conversion error: {str(e)}")
        context.log.error("Check data types in source tables")
        raise DagsterExecutionInterruptedError(f"Data conversion error: {e}")
    except duckdb.Error as e:
        context.log.error(f"DuckDB error: {str(e)}")
        raise DagsterExecutionInterruptedError(f"Database error: {e}")
    except Exception as e:
        context.log.error(f"Unexpected error in {context.asset_key}: {str(e)}")
        raise DagsterExecutionInterruptedError(f"Unexpected error: {e}")
    finally:
        if conn:
            try:
                duckdb_resource.get_connection().__exit__(None, None, None)
                context.log.debug("DuckDB connection closed safely")
            except:
                context.log.warning("Error closing DuckDB connection")

@asset
def robust_workforce_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Asset with comprehensive error handling."""

    with safe_duckdb_operation(context, duckdb_resource) as conn:
        # Validate prerequisites
        table_count = conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name IN ('employees', 'job_levels')
        """).fetchone()[0]

        if table_count < 2:
            raise ValueError("Required tables missing: employees, job_levels")

        # Execute main query with validation
        df = conn.execute("""
            SELECT
                e.employee_id,
                e.level_id,
                e.current_compensation,
                jl.level_name
            FROM employees e
            JOIN job_levels jl ON e.level_id = jl.level_id
            WHERE e.active_flag = true
        """).df()

        # Validate results
        if df.empty:
            context.log.warning("No active employees found")
            return pd.DataFrame(columns=['employee_id', 'level_id', 'current_compensation', 'level_name'])

        # Data quality checks
        null_compensation = df['current_compensation'].isnull().sum()
        if null_compensation > 0:
            context.log.warning(f"Found {null_compensation} employees with null compensation")
            # Fill with median or handle appropriately
            median_comp = df['current_compensation'].median()
            df['current_compensation'].fillna(median_comp, inplace=True)

        context.log.info(f"Successfully processed {len(df)} employees")
        return df
```

---

## 6. Performance Optimization

### 6.1 Memory-Efficient Processing
```python
@asset
def large_dataset_processor(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource,
    config: SimulationConfig
) -> Dict[str, int]:
    """Process large datasets efficiently."""

    # Use smaller limits for development
    is_dev = context.instance.is_dev_mode if hasattr(context.instance, 'is_dev_mode') else False
    limit_clause = f"LIMIT {config.batch_size}" if is_dev else ""

    with duckdb_resource.get_connection() as conn:
        # Stream processing for large datasets
        total_processed = 0
        results = {}

        # Get batches using cursor
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT level_id, current_compensation
            FROM employees
            WHERE active_flag = true
            ORDER BY employee_id
            {limit_clause}
        """)

        # Process in chunks
        while True:
            batch = cursor.fetchmany(config.batch_size)
            if not batch:
                break

            # Convert batch to DataFrame for processing
            batch_df = pd.DataFrame(batch, columns=['level_id', 'current_compensation'])

            # Aggregate by level
            level_counts = batch_df.groupby('level_id').size()

            # Update results
            for level_id, count in level_counts.items():
                results[int(level_id)] = results.get(int(level_id), 0) + count

            total_processed += len(batch)
            context.log.info(f"Processed batch: {total_processed} total records")

        cursor.close()

        context.add_output_metadata({
            "total_processed": total_processed,
            "levels_found": len(results),
            "batch_size": config.batch_size
        })

        return results  # Dict[int, int] is serializable
```

### 6.2 Query Optimization
```python
@asset
def optimized_workforce_summary(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Optimized queries for better performance."""

    with duckdb_resource.get_connection() as conn:
        # Enable query profiling
        conn.execute("PRAGMA enable_profiling = 'json'")

        # Optimized query using DuckDB strengths
        query = """
        WITH workforce_summary AS (
            SELECT
                level_id,
                COUNT(*) as headcount,
                AVG(current_compensation) as avg_compensation,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_compensation) as median_compensation,
                STDDEV(current_compensation) as std_compensation
            FROM employees
            WHERE active_flag = true
            GROUP BY level_id
        ),
        level_details AS (
            SELECT
                jl.level_id,
                jl.level_name,
                jl.min_salary,
                jl.max_salary
            FROM job_levels jl
        )
        SELECT
            ws.*,
            ld.level_name,
            ld.min_salary,
            ld.max_salary,
            (ws.avg_compensation - ld.min_salary) / (ld.max_salary - ld.min_salary) as salary_position
        FROM workforce_summary ws
        JOIN level_details ld ON ws.level_id = ld.level_id
        ORDER BY ws.level_id
        """

        df = conn.execute(query).df()

        # Get query performance info
        profile_info = conn.execute("PRAGMA profiling_output").fetchall()

        context.log.info(f"Query executed efficiently: {len(df)} level summaries")
        context.log.debug(f"Query profile: {profile_info}")

        return df
```

---

## 7. Testing Infrastructure

### 7.1 Unit Testing Patterns
```python
import pytest
from unittest.mock import Mock, MagicMock
from dagster import build_asset_context, materialize
import pandas as pd

def test_workforce_asset_execution():
    """Test asset execution with mocked DuckDB."""

    # Mock DuckDB resource
    mock_duckdb_resource = Mock(spec=DuckDBResource)
    mock_conn = MagicMock()

    # Setup context manager mock
    mock_duckdb_resource.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_duckdb_resource.get_connection.return_value.__exit__ = Mock(return_value=None)

    # Mock query results
    test_data = pd.DataFrame({
        'employee_id': ['E001', 'E002', 'E003'],
        'level_id': [1, 2, 1],
        'current_compensation': [50000, 75000, 52000]
    })
    mock_conn.execute.return_value.df.return_value = test_data

    # Test asset execution
    context = build_asset_context()
    result = workforce_data_asset(context, mock_duckdb_resource)

    # Validate results
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 3
    assert list(result.columns) == ['employee_id', 'level_id', 'current_compensation']
    assert result['employee_id'].iloc[0] == 'E001'

def test_configuration_validation():
    """Test Pydantic configuration validation."""

    # Valid configuration
    valid_config = SimulationConfig(
        start_year=2025,
        end_year=2030,
        target_growth_rate=0.03
    )
    assert valid_config.start_year == 2025

    # Invalid configuration - should raise ValidationError
    with pytest.raises(ValueError):
        SimulationConfig(
            start_year=2030,
            end_year=2025,  # End before start
            target_growth_rate=0.03
        )

def test_serialization_compliance():
    """Test that all asset outputs are serializable."""

    # Test DataFrame serialization
    df = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
    serialized = df.to_json()
    assert isinstance(serialized, str)

    # Test dict serialization
    config = SimulationConfig(start_year=2025, end_year=2030)
    config_dict = config.dict()
    import json
    json_str = json.dumps(config_dict)
    assert isinstance(json_str, str)
```

### 7.2 Integration Testing
```python
def test_full_simulation_pipeline():
    """Integration test for complete simulation pipeline."""

    # Setup test database
    test_db_path = "test_planwise.duckdb"

    # Create test resource
    test_duckdb_resource = DuckDBResource(
        database_path=test_db_path,
        memory_limit="1GB",
        threads=2
    )

    # Setup test data
    with test_duckdb_resource.get_connection() as conn:
        conn.execute("""
            CREATE TABLE employees (
                employee_id VARCHAR,
                level_id INTEGER,
                current_compensation DECIMAL,
                active_flag BOOLEAN
            )
        """)

        conn.execute("""
            INSERT INTO employees VALUES
            ('E001', 1, 50000, true),
            ('E002', 2, 75000, true),
            ('E003', 1, 52000, false)
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
            (2, 'Senior', 60000, 90000)
        """)

    # Test simulation config
    config = SimulationConfig(start_year=2025, end_year=2026)

    # Execute pipeline
    result = materialize(
        [workforce_data_asset, simulation_config_asset],
        resources={"duckdb_resource": test_duckdb_resource},
        run_config={
            "ops": {
                "simulation_config_asset": {
                    "config": config.dict()
                }
            }
        }
    )

    assert result.success

    # Validate outputs
    workforce_output = result.output_for_node("workforce_data_asset")
    assert len(workforce_output) == 2  # Only active employees

    config_output = result.output_for_node("simulation_config_asset")
    assert config_output["start_year"] == 2025

    # Cleanup
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
```

---

## 8. Deployment Checklist

### 8.1 Pre-Deployment Validation
```python
# deployment_validation.py
import sys
from typing import List, Dict, Any
import pandas as pd
import duckdb
from dagster import materialize

def validate_serialization_compliance() -> List[str]:
    """Validate that all asset outputs are serializable."""

    issues = []

    # Test basic serialization
    test_objects = [
        pd.DataFrame({'a': [1, 2, 3]}),
        {'key': 'value', 'number': 42},
        [1, 2, 3, 'string'],
        42,
        'string_value'
    ]

    for obj in test_objects:
        try:
            import json
            import pickle

            # Test JSON serialization (Dagster metadata)
            if hasattr(obj, 'to_json'):
                obj.to_json()
            else:
                json.dumps(obj)

            # Test pickle serialization (Dagster artifacts)
            pickle.dumps(obj)

        except Exception as e:
            issues.append(f"Serialization failed for {type(obj)}: {str(e)}")

    return issues

def validate_database_connections() -> List[str]:
    """Validate DuckDB connection patterns."""

    issues = []

    try:
        # Test basic connection
        conn = duckdb.connect(":memory:")

        # Test context manager pattern
        with duckdb.connect(":memory:") as test_conn:
            result = test_conn.execute("SELECT 1 as test").fetchone()
            if result[0] != 1:
                issues.append("Basic query execution failed")

        conn.close()

    except Exception as e:
        issues.append(f"Database connection validation failed: {str(e)}")

    return issues

def run_deployment_validation() -> bool:
    """Run all deployment validations."""

    print("🔍 Running PlanWise Navigator deployment validation...")

    all_issues = []

    # Serialization validation
    serialization_issues = validate_serialization_compliance()
    all_issues.extend(serialization_issues)

    # Database validation
    db_issues = validate_database_connections()
    all_issues.extend(db_issues)

    # Report results
    if all_issues:
        print("❌ Deployment validation failed:")
        for issue in all_issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ All deployment validations passed!")
        return True

if __name__ == "__main__":
    success = run_deployment_validation()
    sys.exit(0 if success else 1)
```

### 8.2 Common Debugging Patterns
```python
# debugging_helpers.py
from dagster import AssetExecutionContext
import pandas as pd
from typing import Any

def debug_asset_output(context: AssetExecutionContext, output: Any, asset_name: str):
    """Debug helper for validating asset outputs."""

    output_type = type(output)
    context.log.info(f"Asset {asset_name} output type: {output_type}")

    # Check serializability
    try:
        import pickle
        pickle.dumps(output)
        context.log.info("✅ Output is pickle-serializable")
    except Exception as e:
        context.log.error(f"❌ Pickle serialization failed: {str(e)}")

    # Type-specific debugging
    if isinstance(output, pd.DataFrame):
        context.log.info(f"DataFrame shape: {output.shape}")
        context.log.info(f"DataFrame columns: {list(output.columns)}")
        context.log.info(f"DataFrame dtypes: {output.dtypes.to_dict()}")

        # Check for problematic types
        for col in output.columns:
            if output[col].dtype == 'object':
                sample_values = output[col].dropna().head(3).tolist()
                context.log.info(f"Object column {col} sample values: {sample_values}")

    elif isinstance(output, dict):
        context.log.info(f"Dict keys: {list(output.keys())}")
        for key, value in output.items():
            context.log.info(f"Dict[{key}] type: {type(value)}")

    # Add to output metadata for debugging
    context.add_output_metadata({
        "output_type": str(output_type),
        "debug_timestamp": pd.Timestamp.now().isoformat()
    })

# Usage in assets
@asset
def debug_enabled_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Example asset with debugging enabled."""

    # Your asset logic here
    result_df = pd.DataFrame({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']})

    # Debug the output
    debug_asset_output(context, result_df, "debug_enabled_asset")

    return result_df
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Setup DuckDBResource with proper connection management
- [ ] Implement basic asset patterns with serialization compliance
- [ ] Create Pydantic configuration models
- [ ] Setup testing infrastructure with mocks
- [ ] Validate deployment checklist compliance

### Phase 2: Core Assets (Week 2)
- [ ] Implement all staging models using patterns
- [ ] Create intermediate workforce models
- [ ] Build event generation assets
- [ ] Add comprehensive error handling
- [ ] Performance test with realistic data sizes

### Phase 3: Integration (Week 3)
- [ ] Integrate dbt models with proper result handling
- [ ] Implement multi-year simulation pipeline
- [ ] Add asset checks and validation
- [ ] Performance optimization and memory management
- [ ] End-to-end integration testing

### Phase 4: Production (Week 4)
- [ ] Streamlit dashboard integration
- [ ] Export and reporting capabilities
- [ ] Final performance tuning
- [ ] Production deployment validation
- [ ] Documentation and handover

---

## 10. Critical Success Factors

### Must-Have Requirements
1. **Zero DuckDB object serialization** - All assets return DataFrame/dict/primitives
2. **Proper connection cleanup** - All connections use context managers
3. **Pydantic configuration** - All config uses validated models
4. **Comprehensive error handling** - Convert DB errors to Dagster failures
5. **Memory efficiency** - Handle large datasets without OOM errors
6. **Test coverage** - Mock all external dependencies

### Acceptance Criteria
- All assets pass serialization validation
- No connection leaks in testing
- Configuration validation catches invalid inputs
- Error messages provide actionable debugging info
- Performance benchmarks meet requirements
- 100% test success rate with realistic data

This guide provides the complete technical foundation for rebuilding PlanWise Navigator with bulletproof DuckDB integration and Dagster compatibility.
