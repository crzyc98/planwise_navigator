# Dagster Asset Patterns for DuckDB Integration

**Date**: 2025-06-21
**Version**: 2.0 (Rebuild Guidelines)
**Focus**: DuckDB serialization and asset definition best practices

---

## 1. Asset Definition Patterns

### 1.1 Core Asset Structure
```python
from dagster import asset, AssetExecutionContext, ConfigurableResource
import pandas as pd
import duckdb
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

@asset
def standard_asset_template(
    context: AssetExecutionContext,
    duckdb_resource: ConfigurableResource
) -> pd.DataFrame:
    """Template for standard DuckDB asset pattern."""

    with duckdb_resource.get_connection() as conn:
        try:
            # 1. Execute SQL query
            query = """
            SELECT
                column1,
                column2,
                COUNT(*) as record_count
            FROM source_table
            GROUP BY column1, column2
            """

            # 2. Convert to serializable format immediately
            result_df = conn.execute(query).df()

            # 3. Log intermediate results
            context.log.info(f"Processed {len(result_df)} records")
            context.add_output_metadata({
                "num_records": len(result_df),
                "columns": list(result_df.columns),
                "preview": result_df.head().to_dict('records')
            })

            # 4. Return serializable object
            return result_df

        except duckdb.Error as e:
            context.log.error(f"DuckDB error in {context.asset_key}: {str(e)}")
            raise
        except Exception as e:
            context.log.error(f"Unexpected error in {context.asset_key}: {str(e)}")
            raise
```

---

## 2. DuckDB Results Serialization Patterns

### 2.1 DataFrame Output (Recommended)
```python
@asset
def dataframe_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Asset returning pandas DataFrame - most common pattern."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        # ✅ CORRECT: Convert to DataFrame immediately
        df = conn.execute("""
            SELECT employee_id, level_id, current_compensation
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2025
        """).df()

        # Validate before returning
        if df.empty:
            context.log.warning("Query returned empty DataFrame")

        context.log.info(f"Returning DataFrame with {len(df)} rows, {len(df.columns)} columns")
        return df

# ❌ WRONG: Never return DuckDB objects
@asset
def broken_asset(context: AssetExecutionContext):
    conn = duckdb.connect("simulation.duckdb")
    relation = conn.sql("SELECT * FROM employees")
    return relation  # DuckDBPyRelation - NOT SERIALIZABLE!
```

### 2.2 Dictionary Output
```python
@asset
def summary_metrics_asset(context: AssetExecutionContext) -> Dict[str, Any]:
    """Asset returning dictionary of metrics."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Get summary statistics
        stats_query = """
        SELECT
            COUNT(*) as total_employees,
            AVG(current_compensation) as avg_compensation,
            MIN(current_age) as min_age,
            MAX(current_age) as max_age
        FROM fct_workforce_snapshot
        WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
        """

        # ✅ CORRECT: Convert to Python primitives
        result = conn.execute(stats_query).fetchone()

        metrics = {
            "total_employees": int(result[0]),
            "avg_compensation": float(result[1]),
            "min_age": int(result[2]),
            "max_age": int(result[3]),
            "calculation_timestamp": pd.Timestamp.now().isoformat()
        }

        context.log.info(f"Generated metrics: {metrics}")
        return metrics
```

### 2.3 List Output
```python
@asset
def employee_list_asset(context: AssetExecutionContext) -> List[Dict[str, Any]]:
    """Asset returning list of records."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        query = """
        SELECT employee_id, level_id, current_compensation
        FROM fct_workforce_snapshot
        WHERE level_id = 5  -- Executive level only
        ORDER BY current_compensation DESC
        """

        # ✅ CORRECT: Convert to list of dictionaries
        df = conn.execute(query).df()
        records = df.to_dict('records')

        context.log.info(f"Returning {len(records)} executive records")
        return records
```

### 2.4 Primitive Output
```python
@asset
def headcount_asset(context: AssetExecutionContext) -> int:
    """Asset returning single primitive value."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        # ✅ CORRECT: Extract primitive value
        headcount = conn.execute("""
            SELECT COUNT(*)
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2025
        """).fetchone()[0]

        context.log.info(f"Current headcount: {headcount}")
        return int(headcount)  # Ensure it's a Python int, not numpy int64
```

---

## 3. Context Handling Patterns

### 3.1 Standard Context Usage
```python
@asset
def context_aware_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Proper AssetExecutionContext usage."""

    # Access asset metadata
    asset_name = context.asset_key.path[-1]
    run_id = context.run_id

    context.log.info(f"Starting execution of {asset_name} in run {run_id}")

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Log query for debugging
        query = f"""
        SELECT * FROM {asset_name}_source
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """

        context.log.debug(f"Executing query: {query}")

        df = conn.execute(query).df()

        # Add execution metadata
        context.add_output_metadata({
            "execution_time": pd.Timestamp.now().isoformat(),
            "query": query,
            "row_count": len(df),
            "columns": list(df.columns)
        })

        return df
```

### 3.2 Resource-Based Context
```python
from dagster import ConfigurableResource
from pydantic import Field

class DuckDBResource(ConfigurableResource):
    database_path: str = Field(description="Path to DuckDB database")
    memory_limit: str = Field(default="2GB", description="Memory limit")

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = duckdb.connect(self.database_path)
            conn.execute(f"SET memory_limit = '{self.memory_limit}'")
            yield conn
        finally:
            if conn:
                conn.close()

@asset
def resource_based_asset(
    context: AssetExecutionContext,
    duckdb_resource: DuckDBResource
) -> pd.DataFrame:
    """Asset using ConfigurableResource."""

    with duckdb_resource.get_connection() as conn:
        df = conn.execute("SELECT * FROM employees LIMIT 1000").df()

        context.log.info(f"Loaded {len(df)} employees using resource")
        context.add_output_metadata({
            "database_path": duckdb_resource.database_path,
            "memory_limit": duckdb_resource.memory_limit
        })

        return df
```

### 3.3 Configuration-Driven Assets
```python
from dagster import Config
from pydantic import BaseModel

class SimulationConfig(BaseModel):
    start_year: int = 2025
    end_year: int = 2030
    growth_rate: float = 0.03

@asset
def config_driven_asset(
    context: AssetExecutionContext,
    config: SimulationConfig
) -> Dict[str, Any]:
    """Asset with configuration input."""

    context.log.info(f"Running simulation from {config.start_year} to {config.end_year}")

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Use config in query
        query = f"""
        SELECT
            simulation_year,
            COUNT(*) as headcount
        FROM fct_workforce_snapshot
        WHERE simulation_year BETWEEN {config.start_year} AND {config.end_year}
        GROUP BY simulation_year
        ORDER BY simulation_year
        """

        df = conn.execute(query).df()

        # Return config + results
        return {
            "config": config.dict(),
            "results": df.to_dict('records'),
            "years_processed": len(df)
        }
```

---

## 4. Error Handling Patterns

### 4.1 Comprehensive Error Handling
```python
@asset
def robust_error_handling_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Asset with comprehensive error handling."""

    try:
        with get_duckdb_connection("simulation.duckdb") as conn:
            # Validate prerequisites
            table_exists = conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'employees'
            """).fetchone()[0]

            if table_exists == 0:
                raise ValueError("Required table 'employees' does not exist")

            # Execute main query
            query = """
            SELECT employee_id, level_id, current_compensation
            FROM employees
            WHERE active_flag = true
            """

            df = conn.execute(query).df()

            # Validate results
            if df.empty:
                context.log.warning("No active employees found")
                return pd.DataFrame(columns=['employee_id', 'level_id', 'current_compensation'])

            # Check data quality
            null_compensation = df['current_compensation'].isnull().sum()
            if null_compensation > 0:
                context.log.warning(f"Found {null_compensation} employees with null compensation")

            context.log.info(f"Successfully processed {len(df)} employees")
            return df

    except duckdb.CatalogException as e:
        context.log.error(f"Database schema error: {str(e)}")
        context.log.error("Check that all required tables exist and have correct schema")
        raise

    except duckdb.ConversionException as e:
        context.log.error(f"Data conversion error: {str(e)}")
        context.log.error("Check data types and formats in source tables")
        raise

    except duckdb.Error as e:
        context.log.error(f"DuckDB error: {str(e)}")
        context.log.error(f"Query that failed: {query if 'query' in locals() else 'Unknown'}")
        raise

    except Exception as e:
        context.log.error(f"Unexpected error in asset {context.asset_key}: {str(e)}")
        context.log.error(f"Asset execution context: {context}")
        raise
```

### 4.2 Graceful Degradation
```python
@asset
def fault_tolerant_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Asset with graceful degradation on partial failures."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Primary data source
        try:
            primary_df = conn.execute("""
                SELECT employee_id, level_id, current_compensation
                FROM current_employees
                WHERE active_flag = true
            """).df()

            context.log.info(f"Loaded {len(primary_df)} records from primary source")

        except duckdb.Error as e:
            context.log.warning(f"Primary source failed: {str(e)}, falling back to backup")

            # Fallback to backup source
            try:
                primary_df = conn.execute("""
                    SELECT employee_id, level_id, current_compensation
                    FROM employee_backup
                    WHERE status = 'ACTIVE'
                """).df()

                context.log.info(f"Loaded {len(primary_df)} records from backup source")

            except duckdb.Error as backup_error:
                context.log.error(f"Both primary and backup sources failed")
                context.log.error(f"Primary error: {str(e)}")
                context.log.error(f"Backup error: {str(backup_error)}")

                # Return empty DataFrame with correct schema
                return pd.DataFrame(columns=['employee_id', 'level_id', 'current_compensation'])

        # Enrich data if possible
        try:
            enriched_df = conn.execute("""
                SELECT
                    p.employee_id,
                    p.level_id,
                    p.current_compensation,
                    jl.level_name
                FROM primary_df p
                LEFT JOIN job_levels jl ON p.level_id = jl.level_id
            """).df()

            context.log.info("Successfully enriched data with job levels")
            return enriched_df

        except duckdb.Error as enrich_error:
            context.log.warning(f"Data enrichment failed: {str(enrich_error)}")
            context.log.warning("Returning primary data without enrichment")
            return primary_df
```

### 4.3 Retry Logic
```python
import time
from functools import wraps

def retry_on_duckdb_error(max_retries: int = 3, delay: float = 1.0):
    """Decorator for retrying DuckDB operations."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except duckdb.Error as e:
                    if attempt == max_retries - 1:
                        raise

                    # Get context if available
                    context = next((arg for arg in args
                                  if isinstance(arg, AssetExecutionContext)), None)

                    if context:
                        context.log.warning(
                            f"Attempt {attempt + 1} failed: {str(e)}. "
                            f"Retrying in {delay} seconds..."
                        )

                    time.sleep(delay * (2 ** attempt))  # Exponential backoff

            return None
        return wrapper
    return decorator

@asset
def retry_enabled_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Asset with automatic retry on DuckDB errors."""

    @retry_on_duckdb_error(max_retries=3, delay=1.0)
    def execute_query():
        with get_duckdb_connection("simulation.duckdb") as conn:
            return conn.execute("""
                SELECT * FROM potentially_locked_table
                WHERE processing_date = CURRENT_DATE
            """).df()

    df = execute_query()
    context.log.info(f"Successfully executed query with {len(df)} results")
    return df
```

---

## 5. Asset Dependency Patterns

### 5.1 Simple Dependencies
```python
@asset
def source_data(context: AssetExecutionContext) -> pd.DataFrame:
    """Source data asset."""
    with get_duckdb_connection("simulation.duckdb") as conn:
        df = conn.execute("SELECT * FROM raw_employees").df()
        context.log.info(f"Loaded {len(df)} source records")
        return df

@asset(deps=[source_data])
def processed_data(context: AssetExecutionContext, source_data: pd.DataFrame) -> pd.DataFrame:
    """Asset that depends on source_data."""

    # Process the input DataFrame
    processed_df = source_data.copy()
    processed_df['processed_at'] = pd.Timestamp.now()

    # Store results in DuckDB
    with get_duckdb_connection("simulation.duckdb") as conn:
        conn.register('processed_temp', processed_df)
        conn.execute("""
            CREATE OR REPLACE TABLE processed_employees AS
            SELECT * FROM processed_temp
        """)

    context.log.info(f"Processed {len(processed_df)} records")
    return processed_df
```

### 5.2 Multi-Asset Dependencies
```python
@asset
def employee_data(context: AssetExecutionContext) -> pd.DataFrame:
    """Employee master data."""
    with get_duckdb_connection("simulation.duckdb") as conn:
        return conn.execute("SELECT * FROM employees").df()

@asset
def compensation_data(context: AssetExecutionContext) -> pd.DataFrame:
    """Compensation data."""
    with get_duckdb_connection("simulation.duckdb") as conn:
        return conn.execute("SELECT * FROM compensation").df()

@asset(deps=[employee_data, compensation_data])
def enriched_employee_data(
    context: AssetExecutionContext,
    employee_data: pd.DataFrame,
    compensation_data: pd.DataFrame
) -> pd.DataFrame:
    """Enriched employee data combining multiple sources."""

    # Merge DataFrames
    merged_df = employee_data.merge(
        compensation_data,
        on='employee_id',
        how='left'
    )

    # Store result
    with get_duckdb_connection("simulation.duckdb") as conn:
        conn.register('enriched_temp', merged_df)
        conn.execute("""
            CREATE OR REPLACE TABLE enriched_employees AS
            SELECT * FROM enriched_temp
        """)

    context.log.info(f"Created enriched dataset with {len(merged_df)} records")
    return merged_df
```

### 5.3 Conditional Dependencies
```python
@asset
def conditional_processing_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Asset with conditional processing based on data availability."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Check if optional enhancement data exists
        enhancement_available = conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'enhancement_data'
        """).fetchone()[0] > 0

        if enhancement_available:
            context.log.info("Enhancement data available, using enriched query")
            query = """
            SELECT
                e.employee_id,
                e.level_id,
                e.current_compensation,
                en.enhancement_factor
            FROM employees e
            LEFT JOIN enhancement_data en ON e.employee_id = en.employee_id
            """
        else:
            context.log.info("Enhancement data not available, using basic query")
            query = """
            SELECT
                employee_id,
                level_id,
                current_compensation,
                1.0 as enhancement_factor
            FROM employees
            """

        df = conn.execute(query).df()

        context.add_output_metadata({
            "enhancement_used": enhancement_available,
            "record_count": len(df)
        })

        return df
```

---

## 6. Performance Optimization Patterns

### 6.1 Lazy Loading
```python
@asset
def lazy_loading_asset(context: AssetExecutionContext) -> Dict[str, Any]:
    """Asset using lazy loading for large datasets."""

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Get metadata first
        metadata_query = """
        SELECT
            COUNT(*) as total_records,
            MIN(created_date) as earliest_date,
            MAX(created_date) as latest_date
        FROM large_table
        """

        metadata = conn.execute(metadata_query).fetchone()

        context.log.info(f"Dataset contains {metadata[0]} records from {metadata[1]} to {metadata[2]}")

        # Only load recent data
        recent_data_query = """
        SELECT * FROM large_table
        WHERE created_date >= CURRENT_DATE - INTERVAL '30 days'
        """

        recent_df = conn.execute(recent_data_query).df()

        return {
            "metadata": {
                "total_records": int(metadata[0]),
                "earliest_date": str(metadata[1]),
                "latest_date": str(metadata[2])
            },
            "recent_data": recent_df.to_dict('records'),
            "recent_count": len(recent_df)
        }
```

### 6.2 Batch Processing
```python
@asset
def batch_processing_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Asset processing large datasets in batches."""

    batch_size = 50000
    all_results = []

    with get_duckdb_connection("simulation.duckdb") as conn:
        # Get total count
        total_count = conn.execute("SELECT COUNT(*) FROM large_employees_table").fetchone()[0]

        context.log.info(f"Processing {total_count} records in batches of {batch_size}")

        # Process in batches
        for offset in range(0, total_count, batch_size):
            batch_query = f"""
            SELECT
                employee_id,
                level_id,
                current_compensation,
                -- Add complex calculations here
                current_compensation * 1.1 as projected_compensation
            FROM large_employees_table
            ORDER BY employee_id
            LIMIT {batch_size} OFFSET {offset}
            """

            batch_df = conn.execute(batch_query).df()

            # Process batch (your business logic here)
            processed_batch = batch_df.copy()
            processed_batch['batch_number'] = offset // batch_size + 1
            processed_batch['processed_at'] = pd.Timestamp.now()

            all_results.append(processed_batch)

            context.log.info(f"Processed batch {offset // batch_size + 1}: {len(batch_df)} records")

        # Combine all batches
        final_df = pd.concat(all_results, ignore_index=True)

        context.add_output_metadata({
            "total_batches": len(all_results),
            "final_record_count": len(final_df)
        })

        return final_df
```

---

## 7. Testing Patterns

### 7.1 Asset Testing
```python
import pytest
from dagster import materialize

def test_asset_execution():
    """Test basic asset execution."""

    # Setup test data
    test_db = "test_simulation.duckdb"

    with get_duckdb_connection(test_db) as conn:
        conn.execute("""
            CREATE TABLE employees (
                employee_id VARCHAR,
                level_id INTEGER,
                current_compensation DECIMAL
            )
        """)

        conn.execute("""
            INSERT INTO employees VALUES
            ('E001', 1, 50000),
            ('E002', 2, 75000)
        """)

    # Create test asset
    @asset
    def test_employee_asset():
        with get_duckdb_connection(test_db) as conn:
            return conn.execute("SELECT * FROM employees").df()

    # Execute and validate
    result = materialize([test_employee_asset])
    assert result.success

    output_df = result.output_for_node("test_employee_asset")
    assert len(output_df) == 2
    assert list(output_df.columns) == ['employee_id', 'level_id', 'current_compensation']
```

### 7.2 Serialization Testing
```python
def test_asset_serialization():
    """Test that asset outputs are properly serializable."""

    @asset
    def serializable_asset():
        with get_duckdb_connection("test.duckdb") as conn:
            # This should work - returns DataFrame
            return conn.execute("SELECT 1 as test_col").df()

    @asset
    def non_serializable_asset():
        conn = duckdb.connect("test.duckdb")
        # This should fail - returns DuckDBPyRelation
        return conn.sql("SELECT 1 as test_col")

    # Test serializable asset
    result = materialize([serializable_asset])
    assert result.success

    # Test non-serializable asset (should fail)
    with pytest.raises(Exception):
        materialize([non_serializable_asset])
```

---

## 8. Best Practices Checklist

### ✅ Do's
- **Always** convert DuckDB results to DataFrame/dict/list before returning
- **Always** use context managers for connection handling
- **Always** log intermediate results with context.log.info()
- **Always** add output metadata for debugging
- **Always** handle DuckDB-specific exceptions
- **Always** validate data before processing
- **Always** use AssetExecutionContext consistently

### ❌ Don'ts
- **Never** return DuckDBPyRelation objects from assets
- **Never** leave connections open without try/finally
- **Never** ignore empty result sets without logging
- **Never** use bare except clauses
- **Never** hardcode database paths in assets
- **Never** assume tables exist without validation
- **Never** mix OpExecutionContext and AssetExecutionContext

---

## 9. Quick Reference Templates

### Basic Asset Template
```python
@asset
def my_asset(context: AssetExecutionContext) -> pd.DataFrame:
    with get_duckdb_connection("simulation.duckdb") as conn:
        df = conn.execute("SELECT * FROM my_table").df()
        context.log.info(f"Processed {len(df)} records")
        return df
```

### Config-Driven Asset Template
```python
@asset
def my_config_asset(context: AssetExecutionContext, config: MyConfig) -> Dict[str, Any]:
    with get_duckdb_connection("simulation.duckdb") as conn:
        result = conn.execute(f"SELECT COUNT(*) FROM table WHERE year = {config.year}").fetchone()[0]
        return {"count": int(result), "config": config.dict()}
```

### Resource-Based Asset Template
```python
@asset
def my_resource_asset(context: AssetExecutionContext, duckdb_resource: DuckDBResource) -> pd.DataFrame:
    with duckdb_resource.get_connection() as conn:
        df = conn.execute("SELECT * FROM my_table").df()
        return df
```

Use these patterns as your foundation for all Fidelity PlanAlign Engine assets to ensure consistent, serializable, and maintainable code.
