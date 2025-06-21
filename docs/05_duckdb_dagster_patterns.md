# DuckDB + Dagster Integration Patterns

**Date**: 2025-06-21  
**Version**: 2.0 (Rebuild Guidelines)  
**Packages**: DuckDB 1.0.0, Dagster 1.10.20, dbt-duckdb 1.9.3

---

## 1. Core Principles

### 1.1 Connection Management
```python
# ✅ CORRECT: Use context manager for connection lifecycle
import duckdb
from contextlib import contextmanager

@contextmanager
def get_duckdb_connection(database_path: str):
    """Safe connection management with automatic cleanup."""
    conn = None
    try:
        conn = duckdb.connect(database_path)
        yield conn
    finally:
        if conn:
            conn.close()
```

### 1.2 Serialization Rules
```python
# ❌ WRONG: Never return DuckDB objects directly
@asset
def bad_asset():
    conn = duckdb.connect("simulation.duckdb")
    relation = conn.sql("SELECT * FROM employees")
    return relation  # This will fail on serialization!

# ✅ CORRECT: Convert to serializable formats
@asset
def good_asset():
    conn = duckdb.connect("simulation.duckdb")
    try:
        result = conn.execute("SELECT * FROM employees").fetchall()
        return result  # List of tuples - serializable
    finally:
        conn.close()
```

---

## 2. Dagster Asset Patterns

### 2.1 Basic Asset with DuckDB
```python
from dagster import asset, AssetExecutionContext
import duckdb
import pandas as pd
from typing import List, Dict, Any

@asset
def workforce_snapshot(context: AssetExecutionContext) -> pd.DataFrame:
    """Generate workforce snapshot with proper connection handling."""
    database_path = "simulation.duckdb"
    
    with get_duckdb_connection(database_path) as conn:
        # Execute query and fetch results
        query = """
        SELECT 
            employee_id,
            level_id,
            current_age,
            current_tenure,
            current_compensation,
            simulation_year
        FROM fct_workforce_snapshot
        WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
        """
        
        # Convert to DataFrame for serialization
        df = conn.execute(query).df()
        
        # Log metrics for monitoring
        context.log.info(f"Generated workforce snapshot with {len(df)} employees")
        
        return df
```

### 2.2 Asset with Configuration Input
```python
from dagster import asset, Config
from pydantic import BaseModel

class SimulationConfig(BaseModel):
    start_year: int = 2025
    growth_rate: float = 0.03
    random_seed: int = 42

@asset
def simulation_parameters(context: AssetExecutionContext, config: SimulationConfig) -> Dict[str, Any]:
    """Store simulation parameters in DuckDB for downstream use."""
    database_path = "simulation.duckdb"
    
    with get_duckdb_connection(database_path) as conn:
        # Create parameters table if not exists
        conn.execute("""
        CREATE TABLE IF NOT EXISTS simulation_parameters (
            parameter_name VARCHAR,
            parameter_value VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Clear existing parameters
        conn.execute("DELETE FROM simulation_parameters")
        
        # Insert new parameters
        params = [
            ("start_year", str(config.start_year)),
            ("growth_rate", str(config.growth_rate)),
            ("random_seed", str(config.random_seed))
        ]
        
        conn.executemany(
            "INSERT INTO simulation_parameters (parameter_name, parameter_value) VALUES (?, ?)",
            params
        )
        
        context.log.info(f"Stored {len(params)} simulation parameters")
        
        # Return serializable config dict
        return config.dict()
```

### 2.3 Asset with Dependencies
```python
@asset(deps=[simulation_parameters])
def baseline_workforce(context: AssetExecutionContext) -> pd.DataFrame:
    """Load baseline workforce data with parameter validation."""
    database_path = "simulation.duckdb"
    
    with get_duckdb_connection(database_path) as conn:
        # Validate parameters exist
        param_count = conn.execute(
            "SELECT COUNT(*) FROM simulation_parameters"
        ).fetchone()[0]
        
        if param_count == 0:
            raise ValueError("Simulation parameters not found. Run simulation_parameters asset first.")
        
        # Load baseline data
        query = """
        SELECT 
            employee_id,
            level_id,
            age,
            tenure,
            compensation,
            hire_date
        FROM stg_census_data
        WHERE active_flag = true
        """
        
        df = conn.execute(query).df()
        
        # Validate data quality
        if df.empty:
            raise ValueError("No active employees found in baseline data")
        
        context.log.info(f"Loaded baseline workforce: {len(df)} employees")
        
        return df
```

---

## 3. Advanced Patterns

### 3.1 Batch Processing with Chunking
```python
@asset
def process_large_simulation(context: AssetExecutionContext) -> Dict[str, int]:
    """Process large datasets in chunks to manage memory."""
    database_path = "simulation.duckdb"
    chunk_size = 10000
    total_processed = 0
    
    with get_duckdb_connection(database_path) as conn:
        # Get total count
        total_count = conn.execute(
            "SELECT COUNT(*) FROM employees"
        ).fetchone()[0]
        
        # Process in chunks
        for offset in range(0, total_count, chunk_size):
            chunk_query = f"""
            SELECT * FROM employees
            LIMIT {chunk_size} OFFSET {offset}
            """
            
            chunk_df = conn.execute(chunk_query).df()
            
            # Process chunk (your business logic here)
            processed_chunk = process_employee_chunk(chunk_df)
            
            # Write results back to DuckDB
            conn.register('processed_chunk', processed_chunk)
            conn.execute("""
            INSERT INTO processed_employees 
            SELECT * FROM processed_chunk
            """)
            
            total_processed += len(processed_chunk)
            context.log.info(f"Processed chunk: {offset}-{offset + len(chunk_df)}")
    
    return {"total_processed": total_processed}
```

### 3.2 Asset with Custom IOManager
```python
from dagster import IOManager, io_manager
from typing import Any

class DuckDBIOManager(IOManager):
    """Custom IOManager for DuckDB table persistence."""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
    
    def handle_output(self, context, obj: pd.DataFrame) -> None:
        """Store DataFrame as DuckDB table."""
        table_name = context.asset_key.path[-1]  # Use asset name as table name
        
        with get_duckdb_connection(self.database_path) as conn:
            # Register DataFrame and create table
            conn.register('temp_df', obj)
            conn.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS 
            SELECT * FROM temp_df
            """)
            
            context.log.info(f"Stored {len(obj)} rows in table {table_name}")
    
    def load_input(self, context) -> pd.DataFrame:
        """Load DataFrame from DuckDB table."""
        table_name = context.asset_key.path[-1]
        
        with get_duckdb_connection(self.database_path) as conn:
            df = conn.execute(f"SELECT * FROM {table_name}").df()
            context.log.info(f"Loaded {len(df)} rows from table {table_name}")
            return df

@io_manager
def duckdb_io_manager():
    return DuckDBIOManager("simulation.duckdb")
```

### 3.3 Asset with Error Handling
```python
@asset
def robust_simulation_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Robust asset with comprehensive error handling."""
    database_path = "simulation.duckdb"
    
    try:
        with get_duckdb_connection(database_path) as conn:
            # Validate database state
            tables = conn.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'main'
            """).fetchall()
            
            required_tables = ['employees', 'job_levels', 'hazard_tables']
            existing_tables = [t[0] for t in tables]
            
            missing_tables = set(required_tables) - set(existing_tables)
            if missing_tables:
                raise ValueError(f"Missing required tables: {missing_tables}")
            
            # Execute main query with timeout
            query = """
            SELECT 
                e.employee_id,
                e.level_id,
                jl.level_name,
                e.current_compensation
            FROM employees e
            JOIN job_levels jl ON e.level_id = jl.level_id
            WHERE e.active_flag = true
            """
            
            df = conn.execute(query).df()
            
            # Validate results
            if df.empty:
                context.log.warning("Query returned no results")
                return pd.DataFrame()
            
            # Check for data quality issues
            null_compensation = df['current_compensation'].isnull().sum()
            if null_compensation > 0:
                context.log.warning(f"Found {null_compensation} employees with null compensation")
            
            context.log.info(f"Successfully processed {len(df)} employees")
            return df
            
    except duckdb.Error as e:
        context.log.error(f"DuckDB error: {str(e)}")
        raise
    except Exception as e:
        context.log.error(f"Unexpected error: {str(e)}")
        raise
```

---

## 4. dbt Integration Patterns

### 4.1 dbt Asset Execution
```python
from dagster_dbt import DbtCliResource, dbt_assets

@dbt_assets(manifest=dbt_manifest_path)
def dbt_simulation_models(context: AssetExecutionContext, dbt: DbtCliResource):
    """Execute dbt models with proper connection handling."""
    
    # Run dbt with explicit connection management
    dbt_run_invocation = dbt.cli(["run", "--select", "marts"], context=context).wait()
    
    # Check execution status
    if dbt_run_invocation.process is None or dbt_run_invocation.process.returncode != 0:
        raise RuntimeError("dbt run failed")
    
    # Run tests
    dbt_test_invocation = dbt.cli(["test", "--select", "marts"], context=context).wait()
    
    if dbt_test_invocation.process is None or dbt_test_invocation.process.returncode != 0:
        context.log.warning("dbt tests failed - check data quality")
    
    return dbt_run_invocation
```

### 4.2 Hybrid dbt + Python Asset
```python
@asset(deps=[dbt_simulation_models])
def post_dbt_analysis(context: AssetExecutionContext) -> pd.DataFrame:
    """Perform Python analysis on dbt model outputs."""
    database_path = "simulation.duckdb"
    
    with get_duckdb_connection(database_path) as conn:
        # Query dbt model output
        query = """
        SELECT 
            simulation_year,
            level_id,
            COUNT(*) as headcount,
            AVG(current_compensation) as avg_compensation
        FROM fct_workforce_snapshot
        GROUP BY simulation_year, level_id
        ORDER BY simulation_year, level_id
        """
        
        df = conn.execute(query).df()
        
        # Perform Python analysis
        df['compensation_growth'] = df.groupby('level_id')['avg_compensation'].pct_change()
        df['headcount_growth'] = df.groupby('level_id')['headcount'].pct_change()
        
        context.log.info(f"Calculated growth metrics for {len(df)} level-year combinations")
        
        return df
```

---

## 5. Resource Configuration

### 5.1 Dagster Resources
```python
from dagster import resource, ConfigurableResource
from pydantic import Field

class DuckDBResource(ConfigurableResource):
    """DuckDB connection resource with configuration."""
    
    database_path: str = Field(description="Path to DuckDB database file")
    memory_limit: str = Field(default="2GB", description="Memory limit for DuckDB")
    threads: int = Field(default=4, description="Number of threads for DuckDB")
    
    def get_connection(self):
        """Get configured DuckDB connection."""
        conn = duckdb.connect(self.database_path)
        
        # Apply configuration
        conn.execute(f"SET memory_limit = '{self.memory_limit}'")
        conn.execute(f"SET threads = {self.threads}")
        
        return conn
    
    @contextmanager
    def get_connection_context(self):
        """Get connection with automatic cleanup."""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                conn.close()

# Resource configuration
@resource
def duckdb_resource():
    return DuckDBResource(
        database_path="simulation.duckdb",
        memory_limit="4GB",
        threads=8
    )
```

### 5.2 Usage with Resources
```python
@asset
def resource_based_asset(context: AssetExecutionContext, duckdb: DuckDBResource) -> pd.DataFrame:
    """Asset using DuckDB resource."""
    
    with duckdb.get_connection_context() as conn:
        df = conn.execute("SELECT * FROM employees LIMIT 1000").df()
        context.log.info(f"Loaded {len(df)} employees using resource")
        return df
```

---

## 6. Testing Patterns

### 6.1 Asset Testing
```python
import pytest
from dagster import materialize

def test_workforce_snapshot_asset():
    """Test workforce snapshot asset execution."""
    
    # Setup test database
    test_db = "test_simulation.duckdb"
    
    with get_duckdb_connection(test_db) as conn:
        # Create test data
        conn.execute("""
        CREATE TABLE fct_workforce_snapshot (
            employee_id VARCHAR,
            level_id INTEGER,
            current_age INTEGER,
            simulation_year INTEGER
        )
        """)
        
        conn.execute("""
        INSERT INTO fct_workforce_snapshot VALUES
        ('E001', 1, 25, 2025),
        ('E002', 2, 30, 2025)
        """)
    
    # Test asset execution
    result = materialize([workforce_snapshot])
    assert result.success
    
    # Validate output
    output_df = result.output_for_node("workforce_snapshot")
    assert len(output_df) == 2
    assert output_df['simulation_year'].iloc[0] == 2025
```

### 6.2 Integration Testing
```python
def test_full_simulation_pipeline():
    """Test complete simulation pipeline."""
    
    # Setup test configuration
    config = SimulationConfig(
        start_year=2025,
        growth_rate=0.03,
        random_seed=42
    )
    
    # Execute pipeline
    result = materialize([
        simulation_parameters,
        baseline_workforce,
        workforce_snapshot
    ], run_config={"ops": {"simulation_parameters": {"config": config}}})
    
    assert result.success
    
    # Validate pipeline outputs
    assert result.output_for_node("simulation_parameters")["start_year"] == 2025
    assert len(result.output_for_node("baseline_workforce")) > 0
    assert len(result.output_for_node("workforce_snapshot")) > 0
```

---

## 7. Common Pitfalls & Solutions

### 7.1 Serialization Issues
```python
# ❌ PROBLEM: Returning DuckDB objects
@asset
def problematic_asset():
    conn = duckdb.connect("db.duckdb")
    return conn.sql("SELECT * FROM table")  # DuckDBPyRelation not serializable

# ✅ SOLUTION: Convert to serializable format
@asset
def fixed_asset():
    conn = duckdb.connect("db.duckdb")
    try:
        return conn.execute("SELECT * FROM table").df()  # pandas.DataFrame is serializable
    finally:
        conn.close()
```

### 7.2 Connection Leaks
```python
# ❌ PROBLEM: Connections not closed
@asset
def leaky_asset():
    conn = duckdb.connect("db.duckdb")
    return conn.execute("SELECT * FROM table").fetchall()  # Connection never closed

# ✅ SOLUTION: Use context manager
@asset
def safe_asset():
    with get_duckdb_connection("db.duckdb") as conn:
        return conn.execute("SELECT * FROM table").fetchall()
```

### 7.3 Schema Evolution
```python
@asset
def schema_safe_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Handle schema changes gracefully."""
    
    with get_duckdb_connection("simulation.duckdb") as conn:
        # Check if new column exists
        try:
            conn.execute("SELECT new_column FROM employees LIMIT 1")
            has_new_column = True
        except duckdb.CatalogException:
            has_new_column = False
            context.log.info("New column not found, using legacy schema")
        
        # Adapt query based on schema
        if has_new_column:
            query = "SELECT employee_id, level_id, new_column FROM employees"
        else:
            query = "SELECT employee_id, level_id, NULL as new_column FROM employees"
        
        return conn.execute(query).df()
```

---

## 8. Performance Optimization

### 8.1 Query Optimization
```python
@asset
def optimized_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Optimized DuckDB queries for performance."""
    
    with get_duckdb_connection("simulation.duckdb") as conn:
        # Use columnar advantages
        query = """
        SELECT 
            level_id,
            COUNT(*) as headcount,
            AVG(current_compensation) as avg_comp,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_compensation) as median_comp
        FROM employees
        WHERE active_flag = true
        GROUP BY level_id
        ORDER BY level_id
        """
        
        # Enable query profiling
        conn.execute("PRAGMA enable_profiling")
        
        df = conn.execute(query).df()
        
        # Get query statistics
        profile = conn.execute("PRAGMA profiling_output").fetchall()
        context.log.info(f"Query executed in {profile}")
        
        return df
```

### 8.2 Memory Management
```python
@asset
def memory_efficient_asset(context: AssetExecutionContext) -> pd.DataFrame:
    """Process large datasets with memory efficiency."""
    
    with get_duckdb_connection("simulation.duckdb") as conn:
        # Configure memory settings
        conn.execute("SET memory_limit = '2GB'")
        conn.execute("SET max_memory = '2GB'")
        
        # Use streaming for large results
        query = """
        SELECT * FROM large_table
        WHERE processing_date >= '2025-01-01'
        """
        
        # Process in streaming fashion
        cursor = conn.cursor()
        cursor.execute(query)
        
        # Fetch in batches
        batch_size = 50000
        all_results = []
        
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            
            # Process batch
            batch_df = pd.DataFrame(batch, columns=[desc[0] for desc in cursor.description])
            processed_batch = process_batch(batch_df)
            all_results.append(processed_batch)
            
            context.log.info(f"Processed batch of {len(batch)} rows")
        
        # Combine results
        final_df = pd.concat(all_results, ignore_index=True)
        
        return final_df
```

---

## 9. Monitoring & Observability

### 9.1 Asset Checks
```python
from dagster import asset_check, AssetCheckResult

@asset_check(asset=workforce_snapshot)
def check_workforce_data_quality(context: AssetExecutionContext) -> AssetCheckResult:
    """Validate workforce snapshot data quality."""
    
    with get_duckdb_connection("simulation.duckdb") as conn:
        # Check for null values
        null_check = conn.execute("""
        SELECT COUNT(*) as null_count
        FROM fct_workforce_snapshot
        WHERE employee_id IS NULL OR level_id IS NULL
        """).fetchone()[0]
        
        # Check for duplicate employees
        duplicate_check = conn.execute("""
        SELECT COUNT(*) - COUNT(DISTINCT employee_id) as duplicate_count
        FROM fct_workforce_snapshot
        WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
        """).fetchone()[0]
        
        # Check compensation ranges
        comp_check = conn.execute("""
        SELECT 
            MIN(current_compensation) as min_comp,
            MAX(current_compensation) as max_comp
        FROM fct_workforce_snapshot
        """).fetchone()
        
        # Validate results
        issues = []
        if null_check > 0:
            issues.append(f"Found {null_check} rows with null critical fields")
        
        if duplicate_check > 0:
            issues.append(f"Found {duplicate_check} duplicate employees")
        
        if comp_check[0] < 0 or comp_check[1] > 1000000:
            issues.append(f"Compensation out of range: {comp_check[0]} - {comp_check[1]}")
        
        if issues:
            return AssetCheckResult(
                success=False,
                description=f"Data quality issues found: {'; '.join(issues)}"
            )
        else:
            return AssetCheckResult(
                success=True, 
                description="All data quality checks passed"
            )
```

---

This comprehensive guide provides battle-tested patterns for integrating DuckDB with Dagster assets while avoiding common serialization and connection management pitfalls. Use these patterns as templates for your PlanWise Navigator rebuild.