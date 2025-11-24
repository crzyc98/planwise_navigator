# Story S031-02: Year Processing Optimization (13 points)

## Story Overview

**As a** simulation engineer
**I want** individual year processing to use batch operations and intelligent parallelization
**So that** each simulation year completes 60% faster than current system

**Epic**: E031 - Optimized Multi-Year Simulation System
**Story Points**: 13
**Priority**: High
**Status**: 🔴 Not Started

## Acceptance Criteria

- [ ] Single year processing improves from 5-8 minutes to 2-3 minutes
- [ ] Batch dbt execution: 5-8 models per command instead of individual runs
- [ ] Parallel execution of independent operations (validation, calculations)
- [ ] Maintains existing 7-step workflow pattern per year
- [ ] Preserves all workforce calculation logic and financial precision
- [ ] DuckDB queries optimized for columnar storage and vectorized operations
- [ ] Memory usage stays under 4GB peak for year processing
- [ ] Sub-second response times for individual event calculations

## Technical Requirements

### Core Implementation
- [ ] Create `YearProcessor` class with optimized batch operations
- [ ] Implement intelligent task dependency management
- [ ] Add concurrent execution using ThreadPoolExecutor where safe
- [ ] Maintain sequential year requirements (year N depends on year N-1)
- [ ] Preserve all existing event generation and workforce snapshot logic

### DuckDB Query Optimization
- [ ] Implement columnar storage optimization for workforce tables
- [ ] Optimize window functions for employee tenure and compensation calculations
- [ ] Use vectorized aggregations for event rollups and financial summaries
- [ ] Implement query result caching for repeated calculations
- [ ] Add indexed access patterns for employee_id and effective_date filters

### dbt Model Performance Enhancement
- [ ] Batch model execution with dependency-aware grouping
- [ ] Parallel execution of independent model groups (staging, intermediate, marts)
- [ ] Resource allocation optimization for memory-intensive models
- [ ] Incremental materialization for large fact tables
- [ ] Query compilation caching to reduce startup overhead

### Analytical Workload Optimization
- [ ] Optimize event generation queries using batch inserts
- [ ] Streamline workforce snapshot calculations with materialized views
- [ ] Enhance financial modeling with pre-computed aggregates
- [ ] Implement efficient time-series analysis for compensation trends
- [ ] Optimize complex joins using DuckDB's hash join algorithms

## Definition of Done

- [ ] YearProcessor class implemented with batch optimization
- [ ] Performance benchmarks show 60% improvement (2-3 minutes vs 5-8 minutes)
- [ ] Maintains identical simulation results as legacy system
- [ ] Concurrent execution working for independent operations
- [ ] All workforce calculation logic preserved
- [ ] Unit tests covering batch operations and parallelization
- [ ] Integration tests validating end-to-end year processing
- [ ] DuckDB query performance monitoring dashboard
- [ ] Memory profiling reports showing <4GB peak usage
- [ ] dbt model execution metrics and optimization recommendations

## Technical Notes

### Performance Baseline
- **Current**: 5-8 minutes per year in orchestrator_mvp
- **Target**: 2-3 minutes per year using batch operations
- **Improvement**: 60% faster year processing
- **Memory Target**: <4GB peak usage per year
- **Query Response**: <1s for individual calculations

### Architecture Considerations
- Batch dbt model execution to reduce startup overhead
- Intelligent parallelization of independent operations
- Preserve sequential dependencies between years
- Maintain all existing financial precision and audit trails

### DuckDB-Specific Optimizations

#### Columnar Storage Advantages
- **Workforce Tables**: Store employee records in columnar format for efficient analytical queries
- **Event Tables**: Optimize event storage with compression for timestamp and categorical columns
- **Financial Data**: Use decimal precision with columnar compression for compensation calculations

#### Query Optimization Techniques
- **Window Functions**: Optimize employee tenure and ranking calculations using DuckDB's vectorized window functions
- **Aggregations**: Use SIMD-accelerated aggregations for payroll summaries and event rollups
- **Joins**: Leverage hash joins for employee-event associations with proper key ordering
- **Filtering**: Push-down predicates for date ranges and employee status filters

#### Memory Management
- **Streaming Operations**: Use streaming aggregations for large workforce datasets
- **Batch Processing**: Process events in 10,000-record batches to control memory usage
- **Result Caching**: Cache intermediate results for repeated calculations within year processing

### dbt Batch Execution Strategy

#### Model Dependency Grouping
```yaml
# Execution Groups for Parallel Processing
Group 1 (Staging - Parallel):
  - stg_census_data
  - stg_compensation_parameters
  - stg_benefit_plans

Group 2 (Intermediate - Parallel):
  - int_baseline_workforce
  - int_effective_parameters
  - int_plan_eligibility

Group 3 (Event Generation - Sequential):
  - int_termination_events
  - int_hiring_events
  - int_promotion_events
  - int_compensation_events

Group 4 (Aggregation - Parallel):
  - int_yearly_event_summary
  - int_workforce_metrics

Group 5 (Final Output - Sequential):
  - fct_yearly_events
  - fct_workforce_snapshot
```

#### Resource Allocation
- **Memory per Model**: Allocate 1-2GB per model for large transformations
- **Thread Pool**: Use 3-4 threads for parallel model execution
- **Connection Pool**: Maintain 2 DuckDB connections per thread to avoid contention

#### Performance Monitoring
- **Model Timing**: Track execution time for each model group
- **Memory Usage**: Monitor peak memory consumption per model
- **Query Plans**: Analyze DuckDB query execution plans for optimization opportunities

### Analytical Workload Optimization

#### Event Generation Performance
```sql
-- Optimized batch event insertion
INSERT INTO fct_yearly_events
SELECT
    gen_random_uuid() as event_id,
    employee_id,
    event_type,
    effective_date,
    event_payload
FROM (
    -- Use VALUES clause for batch processing
    SELECT * FROM generate_events_batch(10000)
) events;
```

#### Snapshot Calculation Optimization
```sql
-- Materialized view for workforce snapshots
CREATE OR REPLACE VIEW workforce_snapshot_mv AS
SELECT
    simulation_year,
    employee_id,
    -- Use window functions for running totals
    SUM(salary_amount) OVER (
        PARTITION BY employee_id
        ORDER BY effective_date
        ROWS UNBOUNDED PRECEDING
    ) as cumulative_compensation
FROM workforce_events
WHERE event_type IN ('HIRE', 'PROMOTION', 'RAISE');
```

#### Financial Modeling Enhancements
- **Pre-computed Aggregates**: Create summary tables for common financial calculations
- **Incremental Updates**: Use dbt incremental models for large financial datasets
- **Vectorized Calculations**: Leverage DuckDB's SIMD operations for compensation formulas

### Performance Monitoring Framework

#### Real-time Metrics
- **Query Execution Time**: Track individual model execution times
- **Memory Usage**: Monitor peak and average memory consumption
- **CPU Utilization**: Track parallel execution efficiency
- **I/O Performance**: Monitor disk read/write patterns

#### Bottleneck Identification
```python
# Performance monitoring integration
class YearProcessorProfiler:
    def __init__(self):
        self.metrics = {
            'model_timings': {},
            'memory_usage': {},
            'query_plans': {},
            'bottlenecks': []
        }

    def profile_model_execution(self, model_name: str, execution_time: float):
        self.metrics['model_timings'][model_name] = execution_time
        if execution_time > 30:  # Flag slow models
            self.metrics['bottlenecks'].append(f"{model_name}: {execution_time}s")
```

#### Performance Dashboard
- **Year Processing Timeline**: Visual timeline of model execution
- **Resource Usage Charts**: Memory and CPU utilization over time
- **Bottleneck Alerts**: Automated alerts for performance degradation
- **Optimization Recommendations**: AI-generated suggestions for query improvements

### Resource Management Strategy

#### Memory Optimization
- **Streaming Processing**: Process large datasets in chunks to avoid memory overflow
- **Garbage Collection**: Explicit cleanup of intermediate results
- **Connection Pooling**: Reuse database connections to reduce overhead

#### CPU Optimization
- **Thread Pool Management**: Optimize thread count based on available cores
- **Task Scheduling**: Intelligent scheduling of CPU-intensive operations
- **Vectorization**: Leverage DuckDB's SIMD capabilities for mathematical operations

#### Storage Optimization
- **Compression**: Use DuckDB's built-in compression for large tables
- **Partitioning**: Partition tables by simulation_year for efficient access
- **Indexing**: Create indexes on frequently queried columns (employee_id, effective_date)

## Testing Strategy

### Performance Testing
- [ ] Unit tests for YearProcessor class
- [ ] Performance benchmarks comparing year processing times
- [ ] Concurrent execution tests
- [ ] Data integrity tests ensuring identical results
- [ ] Error handling tests for batch operations
- [ ] Memory usage profiling tests
- [ ] DuckDB query performance regression tests
- [ ] dbt model execution time benchmarks

### Load Testing
- [ ] Large workforce simulation (100K+ employees)
- [ ] Multi-year performance under sustained load
- [ ] Memory stress testing with peak usage monitoring
- [ ] Concurrent year processing validation

### Optimization Validation
- [ ] DuckDB query plan analysis
- [ ] Columnar storage efficiency tests
- [ ] Vectorized operation performance validation
- [ ] Cache hit rate optimization tests

## Dependencies

- ✅ orchestrator_dbt optimization system (completed)
- ✅ Existing workforce calculation logic
- ✅ Database schema compatibility

## Implementation Examples

### Optimized YearProcessor Class
```python
class OptimizedYearProcessor:
    def __init__(self, duckdb_connection, thread_pool_size=4):
        self.conn = duckdb_connection
        self.thread_pool = ThreadPoolExecutor(max_workers=thread_pool_size)
        self.profiler = YearProcessorProfiler()

    async def process_year_optimized(self, year: int) -> Dict[str, Any]:
        """Process a simulation year with batch operations and parallelization."""
        start_time = time.time()

        # Step 1: Batch staging models (parallel)
        staging_tasks = [
            self._run_model_batch(['stg_census_data', 'stg_compensation_parameters']),
            self._run_model_batch(['stg_benefit_plans', 'stg_market_data'])
        ]
        await asyncio.gather(*staging_tasks)

        # Step 2: Intermediate models (dependency-aware batching)
        intermediate_results = await self._run_intermediate_batch(year)

        # Step 3: Event generation (sequential but optimized)
        events = await self._generate_events_batch(year, intermediate_results)

        # Step 4: Final aggregations (parallel)
        final_tasks = [
            self._create_workforce_snapshot(year, events),
            self._calculate_financial_summary(year, events)
        ]
        snapshot, financial = await asyncio.gather(*final_tasks)

        total_time = time.time() - start_time
        self.profiler.record_year_processing_time(year, total_time)

        return {
            'year': year,
            'processing_time': total_time,
            'workforce_snapshot': snapshot,
            'financial_summary': financial
        }

    def _run_model_batch(self, models: List[str]) -> Future:
        """Execute multiple dbt models in a single command."""
        model_selector = ' '.join([f'--select {model}' for model in models])
        command = f"dbt run {model_selector} --threads 4"
        return self.thread_pool.submit(self._execute_dbt_streaming, command)
```

### DuckDB Query Optimization Examples
```sql
-- Optimized event aggregation with columnar operations
CREATE OR REPLACE TABLE yearly_event_summary AS
SELECT
    simulation_year,
    event_type,
    COUNT(*) as event_count,
    -- Use vectorized aggregations
    APPROX_COUNT_DISTINCT(employee_id) as affected_employees,
    -- Leverage columnar compression for financial data
    SUM(CAST(event_payload->>'$.amount' AS DECIMAL(15,2))) as total_amount
FROM fct_yearly_events
WHERE simulation_year = $1
GROUP BY ALL  -- DuckDB's efficient GROUP BY ALL
ORDER BY event_type;

-- Optimized workforce snapshot with window functions
CREATE OR REPLACE TABLE workforce_snapshot_optimized AS
SELECT
    employee_id,
    simulation_year,
    -- Use DuckDB's fast window functions
    LAST_VALUE(salary) OVER (
        PARTITION BY employee_id
        ORDER BY effective_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) as current_salary,
    -- Vectorized calculations
    ARRAY_AGG(event_type ORDER BY effective_date) as event_history
FROM workforce_events_mv
WHERE simulation_year <= $1
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY employee_id
    ORDER BY effective_date DESC
) = 1;
```

### dbt Batch Execution Configuration
```yaml
# profiles.yml optimization
planalign_engine:
  target: prod
  outputs:
    prod:
      type: duckdb
      path: './simulation.duckdb'
      # Optimize for analytical workloads
      config:
        memory_limit: '4GB'
        threads: 4
        # Enable vectorized execution
        enable_optimizer: true
        # Use columnar storage
        default_table_format: 'parquet'
        # Optimize for aggregations
        enable_pushdown: true

# dbt_project.yml optimization
models:
  planalign_engine:
    staging:
      +materialized: view
      +pre-hook: "SET memory_limit='1GB'"
    intermediate:
      +materialized: table
      +pre-hook: "SET threads=2"
    marts:
      +materialized: table
      +post-hook: "ANALYZE {{ this }}"
      +pre-hook: "SET memory_limit='2GB'"
```

### Performance Monitoring Integration
```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(list)

    def measure_execution_time(self, operation_name: str):
        """Decorator for measuring execution time."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration = time.perf_counter() - start
                    self.metrics[operation_name].append(duration)
                    if duration > 30:  # Alert on slow operations
                        logging.warning(f"Slow operation {operation_name}: {duration:.2f}s")
            return wrapper
        return decorator

    def get_performance_report(self) -> Dict[str, Dict[str, float]]:
        """Generate performance statistics."""
        report = {}
        for operation, timings in self.metrics.items():
            report[operation] = {
                'avg_time': np.mean(timings),
                'max_time': max(timings),
                'min_time': min(timings),
                'p95_time': np.percentile(timings, 95)
            }
        return report
```

## Risks & Mitigation

- **Risk**: Concurrent execution introduces race conditions
  - **Mitigation**: Careful dependency analysis and sequential safeguards
  - **Detection**: Automated data integrity checks after parallel operations
- **Risk**: Batch operations fail more frequently
  - **Mitigation**: Individual fallback execution for failed batches
  - **Recovery**: Automatic retry with exponential backoff
- **Risk**: Performance targets not achieved
  - **Mitigation**: Progressive optimization with benchmarking
  - **Monitoring**: Real-time performance dashboard with alerts
- **Risk**: Memory usage exceeds available resources
  - **Mitigation**: Streaming processing and memory profiling
  - **Safeguards**: Circuit breakers for memory-intensive operations
- **Risk**: DuckDB query optimization introduces incorrect results
  - **Mitigation**: Comprehensive regression testing with golden datasets
  - **Validation**: Bit-level comparison of optimized vs original results
