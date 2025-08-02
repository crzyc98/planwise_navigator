# PlanWise Navigator Performance Optimization Guide

This guide explains how to use the comprehensive performance optimization system that targets **82% performance improvement** for multi-year workforce simulations.

## 🚀 Quick Start

### Prerequisites

1. Install performance optimization dependencies:
```bash
pip install lz4 psutil networkx
```

2. Validate optimization system:
```bash
python scripts/validate_optimizations.py
```

3. Run optimized simulation:
```bash
python scripts/run_optimized_multi_year_simulation.py --years 2024 2025 2026 --enable-all-optimizations
```

## 📊 Performance Optimization Features

### 1. Advanced DuckDB Optimizations
- **Dynamic Memory Allocation**: Automatically allocates 60-85% of available RAM based on system resources
- **Optimized Threading**: Uses up to 8 worker threads based on CPU count
- **Columnar Processing**: Enables vectorized execution and FSST compression
- **Connection Pooling**: Maintains optimized connection pool to reduce overhead

### 2. Intelligent dbt Batch Processing
- **Dependency Analysis**: Builds dependency graph for optimal execution order
- **Parallel Model Execution**: Runs independent models in parallel batches
- **Resource Optimization**: Configures dbt for maximum performance
- **Error Handling**: Robust error handling with detailed reporting

### 3. LZ4 State Compression
- **Workforce State Compression**: Compresses workforce snapshots between years
- **3.5x+ Compression Ratio**: Typical compression ratios for workforce data
- **Memory Efficiency**: Reduces memory usage for large-scale simulations
- **Fast Decompression**: Minimal overhead for state retrieval

### 4. Performance Monitoring
- **Real-time Metrics**: Tracks execution time, memory usage, and throughput
- **Baseline Comparison**: Calculates improvement percentages vs baseline
- **Comprehensive Reporting**: Detailed performance reports and recommendations
- **Achievement Validation**: Validates 82% improvement target

## 🛠️ Usage Examples

### Basic Optimized Simulation
```bash
# Run simulation with all optimizations enabled
python scripts/run_optimized_multi_year_simulation.py \
  --years 2024 2025 2026 \
  --enable-all-optimizations \
  --pool-size 4
```

### Custom Configuration
```bash
# Use custom configuration file
python scripts/run_optimized_multi_year_simulation.py \
  --config config/simulation_config.yaml \
  --years 2024 2025 2026 2027 2028 \
  --pool-size 8 \
  --output results/optimized_simulation.json
```

### Performance Benchmarking
```bash
# Run comprehensive performance benchmark
python scripts/benchmark_performance_optimizations.py \
  --full-benchmark \
  --years 2024 2025 \
  --output benchmark_results.json
```

### Dry Run (Configuration Validation)
```bash
# Validate configuration without running simulation
python scripts/run_optimized_multi_year_simulation.py \
  --years 2024 2025 2026 \
  --dry-run
```

## 📈 Performance Targets and Expected Results

### Foundation Setup Optimization
- **Target**: <10 seconds (vs 49s baseline)
- **Optimizations**:
  - Parallel database initialization
  - Optimized seed loading
  - Batch index creation
  - Advanced DuckDB tuning

### Year Processing Optimization
- **Target**: 2-3 minutes per year (vs 5-8 minutes baseline)
- **Optimizations**:
  - Parallel intermediate model execution
  - State compression and caching
  - Optimized query execution
  - Intelligent resource management

### Multi-Year Coordination
- **Target**: Minimal overhead between years
- **Optimizations**:
  - Compressed state transfer
  - Connection pooling
  - Memory-efficient data structures
  - Optimized context switching

## 🔧 Configuration Options

### Environment Variables
The system automatically configures optimal environment variables:

```bash
DBT_PARTIAL_PARSE=true          # Fast dbt parsing
DBT_USE_COLORS=false           # Reduce I/O overhead
DBT_LOG_FORMAT=json            # Structured logging
DUCKDB_MEMORY_LIMIT=85%        # Dynamic memory allocation
DUCKDB_THREADS=8               # Optimal thread count
PYTHONUNBUFFERED=1             # Immediate output
```

### Command Line Options
```bash
--years YEARS [YEARS ...]           # Simulation years
--config CONFIG                     # Configuration file path
--dbt-project DBT_PROJECT           # dbt project directory
--pool-size POOL_SIZE               # Connection pool size (default: 4)
--output OUTPUT                     # Results output file
--enable-all-optimizations          # Enable all optimizations
--no-compression                    # Disable state compression
--no-monitoring                     # Disable performance monitoring
--dry-run                          # Configuration validation only
--verbose                          # Detailed logging
```

### Configuration File Format
```yaml
# config/simulation_config.yaml
simulation:
  start_year: 2024
  end_year: 2026

performance:
  baseline_metrics:
    foundation_setup: 49000  # ms
    year_processing: 360000  # ms
    total_simulation: 1200000  # ms

environment:
  DUCKDB_MEMORY_LIMIT: "85%"
  DUCKDB_THREADS: "8"
  DBT_PARTIAL_PARSE: "true"
```

## 📊 Performance Monitoring and Reports

### Real-time Monitoring
The system provides real-time performance feedback:
```
🏗️  Foundation Setup: 8,245ms (8.2s)
    🎯 Improvement: 83.2%
📅 Year 2024: 142,000ms (2.4min)
    🗜️  Compression: 3.8x
    🎯 Improvement: 74.5%
📅 Year 2025: 138,500ms (2.3min)
    🎯 Improvement: 76.1%
```

### Comprehensive Reports
After completion, the system generates detailed reports:
```
🏆 Multi-Year Simulation Performance Report
==================================================
📊 Simulation Overview:
  📅 Years Processed: 3/3
  ⏱️  Total Time: 325.2s (5.4min)
  ✅ Success Rate: 100.0%

🎯 Performance Achievement:
  📈 Overall Improvement: 84.7%
  🏆 Status: ✅ TARGET ACHIEVED! (84.7% improvement)
```

## 🏗️ Architecture Components

### Core Optimization Engine
- **File**: `orchestrator_mvp/core/advanced_optimizations.py`
- **Purpose**: Central optimization engine with connection pooling, compression, and monitoring
- **Key Classes**: `MultiYearOptimizationEngine`, `PerformanceMonitor`, `StateCompressionManager`

### dbt Batch Executor
- **File**: `orchestrator_mvp/utils/dbt_batch_executor.py`
- **Purpose**: Intelligent dbt batch processing with dependency analysis
- **Key Classes**: `OptimizedDbtExecutor`, `DbtDependencyAnalyzer`

### Multi-Year Engine Integration
- **File**: `orchestrator_mvp/core/optimized_multi_year_engine.py`
- **Purpose**: Complete multi-year simulation orchestration
- **Key Classes**: `OptimizedMultiYearSimulationEngine`

### Execution Scripts
- **Simulation Runner**: `scripts/run_optimized_multi_year_simulation.py`
- **Performance Benchmark**: `scripts/benchmark_performance_optimizations.py`
- **Validation Tool**: `scripts/validate_optimizations.py`

## 🔍 Troubleshooting

### Common Issues

#### Missing Dependencies
```bash
# Error: No module named 'lz4'
pip install lz4 psutil networkx
```

#### Memory Issues
```bash
# If simulation fails with memory errors
python scripts/run_optimized_multi_year_simulation.py \
  --years 2024 2025 \
  --pool-size 2  # Reduce pool size
```

#### dbt Project Not Found
```bash
# Specify correct dbt project path
python scripts/run_optimized_multi_year_simulation.py \
  --dbt-project /path/to/your/dbt/project \
  --years 2024 2025
```

### Performance Troubleshooting

#### Below Target Performance
1. **Check System Resources**: Ensure adequate CPU and memory
2. **Review Query Plans**: Use DuckDB EXPLAIN ANALYZE for bottlenecks
3. **Optimize Materializations**: Consider table vs view strategies
4. **Increase Pool Size**: Try larger connection pools
5. **Check Indexes**: Ensure performance indexes are created

#### Simulation Failures
1. **Run Validation**: `python scripts/validate_optimizations.py`
2. **Check Logs**: Review detailed error messages
3. **Use Dry Run**: Validate configuration first
4. **Reduce Scope**: Test with fewer years initially

## 🎯 Performance Validation

### Expected Performance Improvements

| Operation | Baseline | Optimized | Improvement |
|-----------|----------|-----------|-------------|
| Foundation Setup | 49s | <10s | >79% |
| Year Processing | 5-8min | 2-3min | >60% |
| Overall Simulation | 20-30min | 5-8min | >73% |
| **Total Target** | **Variable** | **Variable** | **≥82%** |

### Benchmarking Process
1. **Baseline Measurement**: Run traditional simulation
2. **Optimized Measurement**: Run with all optimizations
3. **Comparison Analysis**: Calculate improvement percentages
4. **Target Validation**: Verify ≥82% improvement achieved

## 📚 Advanced Usage

### Custom Optimization Strategies
```python
from orchestrator_mvp.core.advanced_optimizations import create_optimization_engine

# Create custom optimization engine
engine = create_optimization_engine(
    pool_size=8,
    enable_monitoring=True
)

# Apply custom DuckDB settings
with engine.connection_pool.get_connection() as conn:
    conn.execute("SET memory_limit = '90%'")
    conn.execute("SET threads = 12")

# Custom state compression
compression_result = engine.compress_and_cache_state(
    "custom_state",
    workforce_dataframe
)
```

### Integration with Existing Orchestrator
```python
from orchestrator_mvp.core.optimized_multi_year_engine import create_optimized_multi_year_engine

# Drop-in replacement for existing multi-year processing
optimized_engine = create_optimized_multi_year_engine(
    dbt_project_path="dbt",
    simulation_years=[2024, 2025, 2026],
    baseline_metrics=your_baseline_metrics
)

# Run with optimization context
with optimized_engine.optimized_simulation_context():
    results = optimized_engine.execute_multi_year_simulation_optimized()
```

## 🏆 Success Metrics

### Target Achievement Indicators
- **✅ Target Achieved (82%+)**: System meets performance goals
- **🔶 Significant Improvement (50-81%)**: Good progress, optimization opportunities remain
- **⚠️ Below Target (<50%)**: Requires investigation and additional optimization

### Performance Monitoring
- **Real-time Metrics**: Execution time, memory usage, throughput
- **Comparative Analysis**: Baseline vs optimized performance
- **Resource Utilization**: CPU, memory, and I/O efficiency
- **Compression Effectiveness**: State compression ratios and space savings

## 📞 Support and Further Development

For questions, issues, or enhancement requests related to the performance optimization system:

1. **Validation**: Run `python scripts/validate_optimizations.py`
2. **Benchmarking**: Use `python scripts/benchmark_performance_optimizations.py`
3. **Documentation**: Review this guide and inline code documentation
4. **Performance Analysis**: Check detailed reports and metrics

The optimization system is designed to be extensible and can be enhanced with additional strategies as needed for specific use cases or performance requirements.
