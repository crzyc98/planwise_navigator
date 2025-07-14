# Story S083-02: SCD Performance Optimization

## Story Overview

**Epic**: E027 - Multi-Year Simulation Reliability & Performance
**Points**: 8
**Priority**: High

### Key Improvements (Based on Gemini Analysis)
1. **Use dbt snapshot**: Replace complex hand-rolled SCD logic with dbt's native snapshot materialization
2. **Fix incremental processing**: Ensure proper SCD Type 2 behavior with record updates, not just inserts
3. **Leverage DuckDB optimizations**: Use Parquet partitioning, COPY commands, and optimized data types
4. **Implement hash-based change detection**: More efficient than multi-column comparisons
5. **Add SCD integrity monitoring**: Verify no employees have multiple current records
6. **Memory optimization**: Avoid Pandas for large datasets, use direct SQL transformations

### User Story
**As a** simulation developer
**I want** SCD processing to complete in under 2 minutes
**So that** multi-year simulations run efficiently without blocking

### Problem Statement
The `scd_workforce_state` model takes 19+ minutes to execute on powerful hardware (16 vCPU/64GB Ubuntu 24.04), creating a significant bottleneck in multi-year simulations. This performance issue stems from inefficient SCD Type 2 logic that performs full table rebuilds and lacks proper optimization for incremental processing.

### Root Cause Analysis
1. **Inefficient SCD Logic**: Current implementation uses full table scans with complex window functions
2. **Lack of Incremental Processing**: No mechanism to process only changed employees
3. **Missing Indexing**: No proper indexing strategy for SCD operations
4. **Cartesian Product Risk**: SCD joins can create exponential data growth
5. **Cold Start Amplification**: Empty workforce state forces full table rebuilds

---

## Acceptance Criteria

### Primary Acceptance Criteria
1. **Performance Target**: `scd_workforce_state` execution time reduced from 19+ minutes to <2 minutes
2. **Incremental Processing**: Only process employees with changes since last run
3. **Proper Indexing**: Implement indexing and partitioning strategies for SCD operations
4. **Query Optimization**: Optimize joins and window functions in SCD logic
5. **SLA Monitoring**: Performance monitoring with SLA alerts for long-running operations

### Secondary Acceptance Criteria
1. **Memory Efficiency**: Reduce memory usage during SCD processing
2. **Parallel Processing**: Enable parallel execution where possible
3. **Data Consistency**: Maintain SCD Type 2 accuracy while improving performance
4. **Monitoring**: Comprehensive performance metrics and alerting
5. **Scalability**: Performance improvements scale to larger datasets (100K+ employees)

---

## Technical Specifications

### Current Performance Analysis

#### Current SCD Implementation Issues
```sql
-- PROBLEMATIC: Current scd_workforce_state model
-- Performs full table scan with expensive window functions
CREATE OR REPLACE TABLE scd_workforce_state AS
WITH workforce_history AS (
    SELECT
        employee_id,
        simulation_year,
        annual_salary,
        job_level,
        department,
        employee_status,
        effective_date,
        -- EXPENSIVE: Window function over entire dataset
        LAG(annual_salary) OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as prev_salary,
        LAG(job_level) OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as prev_job_level,
        -- EXPENSIVE: Complex lead calculations
        LEAD(effective_date) OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as next_effective_date
    FROM fct_workforce_snapshot  -- FULL TABLE SCAN
),
scd_changes AS (
    SELECT
        *,
        CASE
            WHEN annual_salary != prev_salary OR job_level != prev_job_level
            THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END as scd_type
    FROM workforce_history
)
SELECT * FROM scd_changes
WHERE scd_type = 'CHANGED'  -- Still processes entire dataset
```

### Proposed Optimized Architecture

#### 1. dbt Snapshot-Based SCD Implementation
```sql
-- models/snapshots/scd_workforce_state.sql
{% snapshot scd_workforce_state %}
    {{
        config(
            target_schema='snapshots',
            unique_key='employee_id',
            strategy='check',
            check_cols=[
                'annual_salary',
                'job_level',
                'department',
                'employee_status'
            ],
            invalidate_hard_deletes=True
        )
    }}

    WITH workforce_with_hash AS (
        SELECT
            employee_id,
            simulation_year,
            annual_salary,
            job_level,
            department,
            employee_status,
            effective_date,
            -- Hash-based change detection for performance
            {{ dbt_utils.generate_surrogate_key([
                'annual_salary',
                'job_level',
                'department',
                'employee_status'
            ]) }} as change_hash
        FROM {{ ref('fct_workforce_snapshot') }}
        WHERE simulation_year = {{ var('current_year') }}
    )
    SELECT * FROM workforce_with_hash
{% endsnapshot %}
```

#### 2. Optimized Source Data with Partitioning
```sql
-- models/intermediate/int_partitioned_workforce_data.sql
{{ config(
    materialized='table',
    partition_by=['simulation_year'],
    file_format='parquet',
    location_root='data/partitioned_workforce'
) }}

WITH optimized_workforce AS (
    SELECT
        employee_id::VARCHAR(50) as employee_id,  -- Optimize data types
        simulation_year::INTEGER as simulation_year,
        annual_salary::DECIMAL(12,2) as annual_salary,
        job_level::VARCHAR(10) as job_level,
        department::VARCHAR(50) as department,
        employee_status::VARCHAR(20) as employee_status,
        effective_date::DATE as effective_date,
        -- Pre-calculate hash for efficient change detection
        {{ dbt_utils.generate_surrogate_key([
            'annual_salary',
            'job_level',
            'department',
            'employee_status'
        ]) }} as record_hash
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('current_year') }}
)
SELECT * FROM optimized_workforce
```

#### 3. Hash-Based Change Detection
```sql
-- models/intermediate/int_workforce_changes.sql
{{ config(materialized='table') }}

WITH current_workforce AS (
    SELECT * FROM {{ ref('int_partitioned_workforce_data') }}
),
previous_state AS (
    SELECT
        employee_id,
        record_hash as previous_hash,
        dbt_valid_from,
        dbt_valid_to
    FROM {{ ref('scd_workforce_state') }}
    WHERE dbt_valid_to IS NULL  -- Current records only
),
change_detection AS (
    SELECT
        c.employee_id,
        c.simulation_year,
        c.annual_salary,
        c.job_level,
        c.department,
        c.employee_status,
        c.effective_date,
        c.record_hash,
        p.previous_hash,
        CASE
            WHEN p.previous_hash IS NULL THEN 'NEW_EMPLOYEE'
            WHEN c.record_hash != p.previous_hash THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END as change_type
    FROM current_workforce c
    LEFT JOIN previous_state p ON c.employee_id = p.employee_id
)
SELECT * FROM change_detection
WHERE change_type IN ('NEW_EMPLOYEE', 'CHANGED')
```

#### 4. Memory-Efficient Direct SQL Processing
```sql
-- models/marts/scd_workforce_final.sql
{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['dbt_valid_from', 'dbt_valid_to'], 'type': 'btree'},
        {'columns': ['dbt_valid_to'], 'type': 'btree', 'where': 'dbt_valid_to IS NULL'}
    ]
) }}

-- Use COPY for high-performance data loading
{% set copy_sql %}
COPY (
    SELECT
        employee_id,
        simulation_year,
        annual_salary,
        job_level,
        department,
        employee_status,
        effective_date,
        dbt_valid_from,
        dbt_valid_to,
        dbt_scd_id,
        dbt_updated_at
    FROM {{ ref('scd_workforce_state') }}
    WHERE dbt_valid_to IS NULL OR dbt_valid_to > CURRENT_DATE - INTERVAL '1 year'
) TO '{{ var("scd_output_path") }}/scd_workforce_state.parquet'
(FORMAT PARQUET, PARTITION_BY simulation_year, COMPRESSION GZIP)
{% endset %}

-- Return reference to the copied data
SELECT * FROM {{ ref('scd_workforce_state') }}
WHERE dbt_valid_to IS NULL  -- Current records only
```

#### 5. MERGE-Based SCD Alternative (if not using dbt snapshot)
```sql
-- models/intermediate/int_scd_merge_processing.sql
{{ config(materialized='table') }}

{% set merge_sql %}
-- Use DuckDB's MERGE for atomic SCD operations
MERGE INTO scd_workforce_state AS target
USING (
    SELECT
        employee_id,
        simulation_year,
        annual_salary,
        job_level,
        department,
        employee_status,
        effective_date,
        record_hash
    FROM {{ ref('int_workforce_changes') }}
    WHERE change_type IN ('NEW_EMPLOYEE', 'CHANGED')
) AS source
ON target.employee_id = source.employee_id
   AND target.is_current_record = true

WHEN MATCHED AND target.record_hash != source.record_hash THEN
    UPDATE SET
        end_date = source.effective_date,
        is_current_record = false,
        updated_at = CURRENT_TIMESTAMP

WHEN NOT MATCHED THEN
    INSERT (
        employee_id,
        simulation_year,
        annual_salary,
        job_level,
        department,
        employee_status,
        effective_date,
        end_date,
        is_current_record,
        record_hash,
        created_at
    )
    VALUES (
        source.employee_id,
        source.simulation_year,
        source.annual_salary,
        source.job_level,
        source.department,
        source.employee_status,
        source.effective_date,
        NULL,
        true,
        source.record_hash,
        CURRENT_TIMESTAMP
    );

-- Insert new current records for updated employees
INSERT INTO scd_workforce_state (
    employee_id,
    simulation_year,
    annual_salary,
    job_level,
    department,
    employee_status,
    effective_date,
    end_date,
    is_current_record,
    record_hash,
    created_at
)
SELECT
    employee_id,
    simulation_year,
    annual_salary,
    job_level,
    department,
    employee_status,
    effective_date,
    NULL as end_date,
    true as is_current_record,
    record_hash,
    CURRENT_TIMESTAMP
FROM {{ ref('int_workforce_changes') }}
WHERE change_type = 'CHANGED';
{% endset %}

-- Execute the merge
{{ run_query(merge_sql) }}

-- Return results for monitoring
SELECT
    change_type,
    COUNT(*) as record_count
FROM {{ ref('int_workforce_changes') }}
GROUP BY change_type
```

#### 3. Performance-Optimized Indexing Strategy
```sql
-- macros/create_scd_indexes.sql
{% macro create_scd_indexes() %}
    -- Create indexes for SCD performance
    CREATE INDEX IF NOT EXISTS idx_scd_workforce_employee_id
        ON {{ ref('scd_workforce_state') }} (employee_id);

    CREATE INDEX IF NOT EXISTS idx_scd_workforce_effective_date
        ON {{ ref('scd_workforce_state') }} (effective_date);

    CREATE INDEX IF NOT EXISTS idx_scd_workforce_current_record
        ON {{ ref('scd_workforce_state') }} (is_current_record)
        WHERE is_current_record = true;

    CREATE INDEX IF NOT EXISTS idx_scd_workforce_composite
        ON {{ ref('scd_workforce_state') }} (employee_id, effective_date, is_current_record);

    -- Analyze table statistics for query optimization
    ANALYZE {{ ref('scd_workforce_state') }};
{% endmacro %}
```

#### 6. Simplified Dagster Asset with dbt Snapshot
```python
# orchestrator/assets/scd_workforce_processing.py
from dagster import asset, AssetExecutionContext, AssetIn
from orchestrator.resources import DuckDBResource, DbtResource
from orchestrator.utils.scd_performance_monitor import SCDPerformanceMonitor
import pandas as pd
from typing import Dict, Any

@asset(
    ins={"workforce_data": AssetIn("int_partitioned_workforce_data")},
    description="Process SCD workforce state using dbt snapshot"
)
def scd_workforce_state_processed(
    context: AssetExecutionContext,
    duckdb: DuckDBResource,
    dbt: DbtResource,
    workforce_data: pd.DataFrame
) -> Dict[str, Any]:
    """Process SCD workforce state using dbt snapshot for optimal performance"""

    # Initialize performance monitoring
    monitor = SCDPerformanceMonitor(context, duckdb)
    monitor.start_monitoring()

    try:
        # Phase 1: Run dbt snapshot (handles all SCD logic)
        context.log.info("Starting dbt snapshot processing")
        snapshot_results = dbt.run(["snapshot"], full_refresh=False)

        if not snapshot_results.success:
            raise Exception(f"dbt snapshot failed: {snapshot_results.results}")

        monitor.record_phase_completion("dbt_snapshot", len(workforce_data))

        # Phase 2: Data quality validation
        with duckdb.get_connection() as conn:
            # Check for SCD integrity violations
            integrity_check = conn.execute("""
                SELECT
                    employee_id,
                    COUNT(*) as current_record_count
                FROM scd_workforce_state
                WHERE dbt_valid_to IS NULL
                GROUP BY employee_id
                HAVING COUNT(*) > 1
            """).df()

            if len(integrity_check) > 0:
                context.log.error(f"SCD integrity violation: {len(integrity_check)} employees have multiple current records")
                raise Exception("SCD integrity check failed")

            # Get processing metrics
            processing_metrics = conn.execute("""
                SELECT
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN dbt_valid_to IS NULL THEN 1 END) as current_records,
                    COUNT(DISTINCT employee_id) as unique_employees,
                    MAX(dbt_updated_at) as last_updated
                FROM scd_workforce_state
            """).fetchone()

        monitor.record_phase_completion("data_quality_validation", processing_metrics[0])

        # Check SLA compliance
        monitor.check_sla_compliance(sla_threshold_seconds=120)

        context.log.info(f"SCD processing completed successfully: {processing_metrics[0]} total records, {processing_metrics[1]} current records")

        return {
            "total_records": processing_metrics[0],
            "current_records": processing_metrics[1],
            "unique_employees": processing_metrics[2],
            "last_updated": processing_metrics[3],
            "processing_time": monitor.get_total_duration()
        }

    except Exception as e:
        monitor.check_sla_compliance(sla_threshold_seconds=120)
        raise e

@asset(
    deps=["scd_workforce_state_processed"],
    description="Optimize SCD table with indexes and statistics"
)
def scd_workforce_state_optimized(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> None:
    """Optimize SCD table with proper indexes and statistics"""

    with duckdb.get_connection() as conn:
        # Create optimized indexes
        optimization_queries = [
            "CREATE INDEX IF NOT EXISTS idx_scd_employee_id ON scd_workforce_state (employee_id)",
            "CREATE INDEX IF NOT EXISTS idx_scd_valid_from ON scd_workforce_state (dbt_valid_from)",
            "CREATE INDEX IF NOT EXISTS idx_scd_valid_to ON scd_workforce_state (dbt_valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_scd_current_records ON scd_workforce_state (dbt_valid_to) WHERE dbt_valid_to IS NULL",
            "CREATE INDEX IF NOT EXISTS idx_scd_composite ON scd_workforce_state (employee_id, dbt_valid_from, dbt_valid_to)",
            "ANALYZE scd_workforce_state"
        ]

        for query in optimization_queries:
            try:
                conn.execute(query)
                context.log.info(f"Executed optimization: {query}")
            except Exception as e:
                context.log.warning(f"Optimization query failed: {query}, Error: {e}")

        # Collect performance statistics
        stats = conn.execute("""
            SELECT
                table_name,
                estimated_size,
                column_count,
                row_count
            FROM duckdb_tables()
            WHERE table_name = 'scd_workforce_state'
        """).fetchone()

        context.log.info(f"Table optimization completed: {stats[3]} rows, {stats[1]} estimated size")

@asset(
    deps=["scd_workforce_state_optimized"],
    description="Export optimized SCD data to Parquet"
)
def scd_workforce_state_exported(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> str:
    """Export SCD data to partitioned Parquet for downstream consumption"""

    output_path = context.run.run_config.get("scd_output_path", "data/scd_workforce_state")

    with duckdb.get_connection() as conn:
        # Export to partitioned Parquet using COPY
        export_query = f"""
            COPY (
                SELECT
                    employee_id,
                    simulation_year,
                    annual_salary,
                    job_level,
                    department,
                    employee_status,
                    effective_date,
                    dbt_valid_from,
                    dbt_valid_to,
                    dbt_scd_id,
                    dbt_updated_at
                FROM scd_workforce_state
                WHERE dbt_valid_to IS NULL OR dbt_valid_to > CURRENT_DATE - INTERVAL '2 years'
            ) TO '{output_path}'
            (FORMAT PARQUET, PARTITION_BY simulation_year, COMPRESSION GZIP, OVERWRITE_OR_IGNORE true)
        """

        conn.execute(export_query)

        # Verify export
        file_count = conn.execute(f"""
            SELECT COUNT(*) FROM glob('{output_path}/**/*.parquet')
        """).fetchone()[0]

        context.log.info(f"Exported SCD data to {output_path}: {file_count} Parquet files")

        return output_path
```

#### 7. Enhanced Performance Monitoring with SCD Integrity
```python
# orchestrator/utils/scd_performance_monitor.py
from typing import Dict, Any, Optional
import time
from datetime import datetime, timedelta
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource

class SCDPerformanceMonitor:
    """Monitor SCD processing performance with SLA tracking and integrity checks"""

    def __init__(self, context: AssetExecutionContext, duckdb: DuckDBResource):
        self.context = context
        self.duckdb = duckdb
        self.start_time = None
        self.metrics = {}
        self.phase_start_times = {}

    def start_monitoring(self):
        """Start performance monitoring"""
        self.start_time = time.time()
        self.context.log.info("Starting SCD performance monitoring")

    def record_phase_completion(self, phase_name: str, record_count: int):
        """Record completion of SCD processing phase with enhanced metrics"""
        if self.start_time is None:
            return

        current_time = time.time()
        phase_duration = current_time - self.phase_start_times.get(phase_name, current_time)
        total_duration = current_time - self.start_time

        self.metrics[phase_name] = {
            "duration_seconds": phase_duration,
            "record_count": record_count,
            "records_per_second": record_count / phase_duration if phase_duration > 0 else 0,
            "total_duration_seconds": total_duration
        }

        self.context.log.info(
            f"SCD Phase '{phase_name}' completed: "
            f"{record_count} records in {phase_duration:.2f}s "
            f"({self.metrics[phase_name]['records_per_second']:.0f} records/sec)"
        )

        # Record detailed metrics
        self._record_detailed_metrics(phase_name, record_count, phase_duration)

    def start_phase(self, phase_name: str):
        """Start timing a specific phase"""
        self.phase_start_times[phase_name] = time.time()

    def get_total_duration(self) -> float:
        """Get total processing duration"""
        if self.start_time is None:
            return 0
        return time.time() - self.start_time

    def check_scd_integrity(self) -> Dict[str, Any]:
        """Check SCD Type 2 integrity and data quality"""
        integrity_results = {
            "multiple_current_records": 0,
            "orphaned_records": 0,
            "overlapping_periods": 0,
            "null_key_violations": 0,
            "change_data_capture_anomalies": 0
        }

        with self.duckdb.get_connection() as conn:
            # Check for multiple current records per employee
            multiple_current = conn.execute("""
                SELECT COUNT(*)
                FROM (
                    SELECT employee_id
                    FROM scd_workforce_state
                    WHERE dbt_valid_to IS NULL
                    GROUP BY employee_id
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            integrity_results["multiple_current_records"] = multiple_current

            # Check for NULL key violations
            null_keys = conn.execute("""
                SELECT COUNT(*)
                FROM scd_workforce_state
                WHERE employee_id IS NULL OR dbt_valid_from IS NULL
            """).fetchone()[0]
            integrity_results["null_key_violations"] = null_keys

            # Check for overlapping periods
            overlapping = conn.execute("""
                SELECT COUNT(*)
                FROM scd_workforce_state s1
                JOIN scd_workforce_state s2 ON s1.employee_id = s2.employee_id
                WHERE s1.dbt_scd_id != s2.dbt_scd_id
                  AND s1.dbt_valid_from < COALESCE(s2.dbt_valid_to, '9999-12-31')
                  AND COALESCE(s1.dbt_valid_to, '9999-12-31') > s2.dbt_valid_from
            """).fetchone()[0]
            integrity_results["overlapping_periods"] = overlapping

            # Check for change data capture anomalies
            change_anomalies = conn.execute("""
                SELECT COUNT(*)
                FROM (
                    SELECT employee_id, COUNT(*) as change_count
                    FROM scd_workforce_state
                    WHERE dbt_valid_from >= CURRENT_DATE - INTERVAL '1 day'
                    GROUP BY employee_id
                    HAVING COUNT(*) > 10  -- More than 10 changes in one day is suspicious
                )
            """).fetchone()[0]
            integrity_results["change_data_capture_anomalies"] = change_anomalies

        # Log integrity check results
        total_violations = sum(integrity_results.values())
        if total_violations > 0:
            self.context.log.warning(f"SCD integrity violations found: {integrity_results}")
        else:
            self.context.log.info("SCD integrity check passed")

        return integrity_results

    def check_sla_compliance(self, sla_threshold_seconds: int = 120):
        """Check SLA compliance and alert if exceeded"""
        if self.start_time is None:
            return

        total_duration = time.time() - self.start_time

        if total_duration > sla_threshold_seconds:
            self.context.log.warning(
                f"SCD processing exceeded SLA: {total_duration:.2f}s > {sla_threshold_seconds}s"
            )

            # Record SLA breach
            self._record_sla_breach(total_duration, sla_threshold_seconds)

        # Record performance metrics
        self._record_performance_metrics(total_duration)

        # Check integrity
        integrity_results = self.check_scd_integrity()

        # Alert on integrity violations
        if sum(integrity_results.values()) > 0:
            self.context.log.error("SCD integrity violations detected - review required")

    def _record_detailed_metrics(self, phase_name: str, record_count: int, duration: float):
        """Record detailed phase metrics"""
        with self.duckdb.get_connection() as conn:
            conn.execute("""
                INSERT INTO mon_scd_phase_metrics (
                    phase_name,
                    metric_timestamp,
                    duration_seconds,
                    record_count,
                    records_per_second,
                    simulation_year
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                phase_name,
                datetime.now(),
                duration,
                record_count,
                record_count / duration if duration > 0 else 0,
                self.context.run.run_config.get("simulation_year", 2024)
            ])

    def _record_sla_breach(self, actual_duration: float, sla_threshold: int):
        """Record SLA breach in monitoring table"""
        with self.duckdb.get_connection() as conn:
            conn.execute("""
                INSERT INTO mon_sla_breaches (
                    component_name,
                    breach_timestamp,
                    actual_duration_seconds,
                    sla_threshold_seconds,
                    breach_severity
                )
                VALUES (?, ?, ?, ?, ?)
            """, [
                "scd_workforce_state",
                datetime.now(),
                actual_duration,
                sla_threshold,
                "HIGH" if actual_duration > sla_threshold * 2 else "MEDIUM"
            ])

    def _record_performance_metrics(self, total_duration: float):
        """Record performance metrics for trending"""
        with self.duckdb.get_connection() as conn:
            conn.execute("""
                INSERT INTO mon_performance_metrics (
                    component_name,
                    metric_timestamp,
                    execution_time_seconds,
                    total_records_processed,
                    performance_category
                )
                VALUES (?, ?, ?, ?, ?)
            """, [
                "scd_workforce_state",
                datetime.now(),
                total_duration,
                sum(m["record_count"] for m in self.metrics.values()),
                "EXCELLENT" if total_duration < 60 else "GOOD" if total_duration < 120 else "POOR"
            ])
```

### DuckDB-Specific Optimizations

#### Enhanced Query Optimization Settings
```sql
-- Optimize DuckDB settings for SCD processing
SET threads = 16;  -- Use all available cores
SET memory_limit = '32GB';  -- Increase memory limit
SET temp_directory = '/tmp/duckdb_scd';  -- Use fast temp storage

-- Enable parallel processing
SET enable_parallel_join = true;
SET enable_parallel_sort = true;
SET enable_parallel_aggregate = true;

-- Optimize for analytical workloads
SET enable_optimizer = true;
SET enable_profiling = true;
SET enable_progress_bar = true;

-- Additional DuckDB optimizations
SET preserve_insertion_order = false;  -- Allow reordering for performance
SET checkpoint_threshold = '1GB';  -- Reduce checkpoint frequency
SET wal_autocheckpoint = 10000;  -- Optimize WAL checkpointing
SET enable_http_metadata_cache = true;  -- Cache remote metadata
SET enable_object_cache = true;  -- Enable object caching
```

#### Parquet Optimization Strategy
```sql
-- Optimize data layout for query performance
CREATE TABLE scd_workforce_state_optimized (
    employee_id VARCHAR(50),
    simulation_year INTEGER,
    annual_salary DECIMAL(12,2),
    job_level VARCHAR(10),
    department VARCHAR(50),
    employee_status VARCHAR(20),
    effective_date DATE,
    end_date DATE,
    is_current_record BOOLEAN,
    record_hash BIGINT,
    created_at TIMESTAMP
)
USING PARQUET
PARTITIONED BY (simulation_year, department)
TBLPROPERTIES (
    'parquet.compression' = 'GZIP',
    'parquet.block.size' = '134217728',  -- 128MB blocks
    'parquet.page.size' = '1048576'      -- 1MB pages
);

-- Use COPY for high-performance bulk loading
COPY scd_workforce_state_optimized
FROM 'data/scd_workforce_state/*.parquet'
WITH (FORMAT PARQUET, PARTITION_DETECTION true);
```

#### Memory-Efficient Processing
```sql
-- Process SCD in memory-efficient chunks
CREATE OR REPLACE MACRO process_scd_chunk(start_employee_id, end_employee_id) AS (
    WITH employee_chunk AS (
        SELECT employee_id
        FROM fct_workforce_snapshot
        WHERE employee_id BETWEEN start_employee_id AND end_employee_id
        AND simulation_year = ?
    ),
    chunk_scd AS (
        SELECT
            employee_id,
            simulation_year,
            annual_salary,
            job_level,
            effective_date,
            LAG(annual_salary) OVER (
                PARTITION BY employee_id
                ORDER BY effective_date
            ) as prev_salary
        FROM fct_workforce_snapshot
        WHERE employee_id IN (SELECT employee_id FROM employee_chunk)
    )
    SELECT * FROM chunk_scd
    WHERE annual_salary != prev_salary OR prev_salary IS NULL
);
```

---

## Implementation Plan

### Phase 1: Analysis and Baseline (2 days)
1. Analyze current SCD query execution plans
2. Identify specific performance bottlenecks
3. Establish baseline performance metrics
4. Create performance monitoring framework

### Phase 2: Incremental Processing (3 days)
1. Implement change detection logic
2. Create optimized SCD processing model
3. Add incremental materialization support
4. Test with subset of employees

### Phase 3: Parallel Processing (2 days)
1. Implement parallel batch processing
2. Add Dagster partitioning support
3. Optimize DuckDB settings for parallel execution
4. Test scalability with large datasets

### Phase 4: Monitoring and Validation (1 day)
1. Deploy performance monitoring
2. Add SLA alerting
3. Validate data consistency
4. Document optimization techniques

---

## Testing Strategy

### Performance Testing
```python
# tests/performance/test_scd_performance.py
import pytest
import time
from tests.fixtures import large_workforce_dataset

@pytest.mark.performance
def test_scd_processing_performance(duckdb_resource, large_workforce_dataset):
    """Test SCD processing meets performance requirements"""

    start_time = time.time()

    # Execute SCD processing
    result = process_scd_workforce_state(duckdb_resource, simulation_year=2024)

    execution_time = time.time() - start_time

    # Assert performance requirements
    assert execution_time < 120, f"SCD processing took {execution_time:.2f}s, expected <120s"
    assert len(result) > 0, "SCD processing produced no results"

    # Validate data consistency
    assert result['is_current_record'].sum() > 0, "No current records found"

@pytest.mark.performance
def test_scd_memory_usage(duckdb_resource, large_workforce_dataset):
    """Test SCD processing memory efficiency"""

    import psutil
    process = psutil.Process()

    memory_before = process.memory_info().rss / 1024 / 1024  # MB

    # Execute SCD processing
    result = process_scd_workforce_state(duckdb_resource, simulation_year=2024)

    memory_after = process.memory_info().rss / 1024 / 1024  # MB
    memory_used = memory_after - memory_before

    # Assert memory requirements
    assert memory_used < 4096, f"SCD processing used {memory_used:.2f}MB, expected <4096MB"
```

### Data Consistency Testing
```python
# tests/integration/test_scd_data_consistency.py
def test_scd_data_consistency(duckdb_resource):
    """Test SCD processing maintains data consistency"""

    # Execute SCD processing
    result = process_scd_workforce_state(duckdb_resource, simulation_year=2024)

    # Validate SCD Type 2 properties
    assert result.groupby('employee_id')['is_current_record'].sum().max() == 1, \
        "Multiple current records found for same employee"

    # Validate date ranges
    overlapping_records = result.groupby('employee_id').apply(
        lambda x: x.sort_values('effective_date').apply(
            lambda row: row['effective_date'] < row['end_date'], axis=1
        ).all()
    )
    assert overlapping_records.all(), "Overlapping date ranges found"
```

---

## Performance Requirements

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Execution Time | 19+ minutes | <2 minutes | Wall clock time for complete SCD processing |
| Memory Usage | Unknown | <4GB | Peak memory consumption during processing |
| Records/Second | ~87 | >1000 | Processing throughput |
| SLA Compliance | 0% | 95% | Percentage of runs completing within SLA |
| Data Consistency | 100% | 100% | SCD Type 2 validation checks |

---

## Risk Assessment

### High Risk
- **Data consistency**: Optimizations may introduce SCD Type 2 violations
- **Complex dependencies**: Changes may affect downstream models

### Medium Risk
- **Memory constraints**: Large datasets may exceed available memory
- **Parallel processing**: Race conditions in concurrent execution

### Mitigation Strategies
- Comprehensive data validation testing
- Gradual rollout with monitoring
- Memory profiling and optimization
- Thorough testing of parallel execution scenarios

---

## Definition of Done

### Performance Requirements
- [ ] SCD processing completes in <2 minutes on target hardware
- [ ] Memory usage stays below 4GB during processing
- [ ] Processing throughput exceeds 1000 records/second
- [ ] 95% of runs complete within SLA threshold

### Technical Requirements
- [ ] Incremental processing implemented and tested
- [ ] Parallel batch processing functional
- [ ] Performance monitoring with SLA alerting operational
- [ ] DuckDB optimization settings applied
- [ ] Comprehensive indexing strategy deployed

### Quality Requirements
- [ ] Data consistency validation passes 100%
- [ ] Performance tests meet all benchmarks
- [ ] Memory usage profiling completed
- [ ] Documentation includes optimization techniques
- [ ] Rollback plan prepared for production deployment
