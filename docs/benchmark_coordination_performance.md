# Multi-Year Coordination Performance Benchmark Suite

This document describes the comprehensive performance benchmarking suite for Story S031-04 Multi-Year Coordination optimization, designed to validate the 65% coordination overhead reduction target.

## Overview

The benchmark suite provides comprehensive performance analysis for all coordination components:

- **CrossYearCostAttributor** - Cost attribution across simulation years
- **IntelligentCacheManager** - Multi-tier caching system
- **CoordinationOptimizer** - Performance optimization coordination
- **ResourceOptimizer** - Memory and I/O optimization

## Key Features

### Comprehensive Performance Profiling
- Baseline vs optimized performance comparison
- Component-level isolation testing for bottleneck identification
- Statistical analysis with multiple measurement runs
- Memory usage and throughput analysis
- Real-time performance monitoring

### Multiple Test Scenarios
- **Small**: 1,000 employees, 2 years, minimal events (quick validation)
- **Medium**: 10,000 employees, 3 years, standard events (typical workload)
- **Large**: 50,000 employees, 5 years, heavy events (stress testing)

### Detailed Reporting
- Performance grade calculation (A+ to D scale)
- Component-by-component analysis
- System resource utilization
- Optimization recommendations
- JSON output for programmatic analysis

### Target Validation
- Validates 65% coordination overhead reduction target
- Performance regression detection
- Historical comparison capabilities
- Pass/fail criteria for CI/CD integration

## Usage

### Quick Validation Test

First, run the validation test to ensure everything works:

```bash
python scripts/test_benchmark_coordination.py
```

### Basic Usage

Run a single scenario benchmark:

```bash
# Small scenario (quick test)
python scripts/benchmark_multi_year_coordination.py --scenario small

# Medium scenario (typical workload)
python scripts/benchmark_multi_year_coordination.py --scenario medium --verbose

# Large scenario (stress test)
python scripts/benchmark_multi_year_coordination.py --scenario large
```

### Comprehensive Testing

Run all scenarios with detailed reporting:

```bash
# Run all scenarios and generate comprehensive report
python scripts/benchmark_multi_year_coordination.py --all-scenarios --generate-report

# Save results to specific directory
python scripts/benchmark_multi_year_coordination.py --all-scenarios --generate-report --output-dir ./performance_results

# Save JSON results for analysis
python scripts/benchmark_multi_year_coordination.py --all-scenarios --output results.json
```

### Advanced Options

```bash
# Verbose logging for debugging
python scripts/benchmark_multi_year_coordination.py --scenario medium --verbose

# Custom output location
python scripts/benchmark_multi_year_coordination.py --all-scenarios --output-dir ./custom_results --generate-report
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--scenario {small,medium,large}` | Run benchmark for specific scenario |
| `--all-scenarios` | Run benchmarks for all scenarios |
| `--verbose, -v` | Enable verbose logging |
| `--output PATH` | Output file for JSON results |
| `--generate-report` | Generate detailed text report |
| `--output-dir PATH` | Output directory for reports (default: ./benchmark_results) |

## Understanding Results

### Performance Grades

- **A+ (≥75% reduction)**: Exceeds target significantly
- **A (≥65% reduction)**: Meets target exactly
- **B+ (≥50% reduction)**: Good improvement, close to target
- **B (≥35% reduction)**: Moderate improvement
- **C (≥20% reduction)**: Some improvement
- **D (<20% reduction)**: Minimal improvement

### Key Metrics

1. **Coordination Overhead Reduction**: Primary target metric (goal: ≥65%)
2. **Total Time Improvement**: Overall performance improvement
3. **Component Performance**: Individual component contributions
4. **Memory Efficiency**: Memory usage optimization
5. **Throughput**: Operations per second improvement

### Sample Output

```
EXECUTIVE SUMMARY
----------------------------------------
Test Date: 2025-01-15 14:30:22 UTC
Scenarios Tested: small, medium, large
Overall Performance Grade: A
Average Overhead Reduction: 67.8%
Target Achieved (65% reduction): ✅ YES
Performance Regression Detected: ✅ NO

SMALL SCENARIO
  Workforce Size: 1,000 employees
  Simulation Years: 2 years (2024-2025)
  Total Events: 6,000
  Coordination Overhead: 1.234s → 0.402s
  Overhead Reduction: 67.4%
  Target Achieved: ✅ YES
```

## Test Scenarios Details

### Small Scenario
- **Purpose**: Quick validation and development testing
- **Workforce**: 1,000 employees
- **Duration**: 2 years (2024-2025)
- **Events**: 3 per employee per year (6,000 total)
- **Expected Runtime**: 5-10 seconds
- **Use Case**: CI/CD validation, quick iteration testing

### Medium Scenario
- **Purpose**: Typical production workload simulation
- **Workforce**: 10,000 employees
- **Duration**: 3 years (2024-2026)
- **Events**: 5 per employee per year (150,000 total)
- **Expected Runtime**: 30-60 seconds
- **Use Case**: Performance validation, optimization tuning

### Large Scenario
- **Purpose**: Stress testing and scalability validation
- **Workforce**: 50,000 employees
- **Duration**: 5 years (2024-2028)
- **Events**: 8 per employee per year (2,000,000 total)
- **Expected Runtime**: 3-5 minutes
- **Use Case**: Scalability testing, worst-case performance

## Component Analysis

### CrossYearCostAttributor
- **Focus**: Cost attribution accuracy and performance
- **Optimizations**: Vectorized calculations, batch processing
- **Metrics**: Attributions per second, memory efficiency
- **Target**: 20% of total overhead reduction

### IntelligentCacheManager
- **Focus**: Cache hit rates and access times
- **Optimizations**: Multi-tier caching, intelligent promotion
- **Metrics**: Hit rate, access time, memory usage
- **Target**: 30% of total overhead reduction

### CoordinationOptimizer
- **Focus**: Overall coordination efficiency
- **Optimizations**: Parallel processing, resource management
- **Metrics**: Optimization effectiveness, resource utilization
- **Target**: 25% of total overhead reduction

### ResourceOptimizer
- **Focus**: Memory and I/O efficiency
- **Optimizations**: Streaming, compression, chunking
- **Metrics**: Memory savings, I/O reduction
- **Target**: 20% of total overhead reduction, plus enablement

## Integration with CI/CD

The benchmark suite is designed for CI/CD integration:

### Exit Codes
- **0**: All targets achieved successfully
- **1**: Performance targets not met or errors occurred
- **130**: Interrupted by user (Ctrl+C)

### JSON Output Format
```json
{
  "test_timestamp": "2025-01-15T14:30:22.123456",
  "overall_target_achieved": true,
  "average_overhead_reduction_percent": 67.8,
  "performance_grade": "A",
  "integration_results": {
    "small": {
      "coordination_overhead_reduction_percent": 67.4,
      "target_achieved": true,
      "component_results": { ... }
    }
  }
}
```

### GitHub Actions Integration
```yaml
- name: Run Performance Benchmark
  run: |
    python scripts/benchmark_multi_year_coordination.py --all-scenarios --output benchmark_results.json

- name: Check Performance Targets
  run: |
    if ! python -c "import json; data=json.load(open('benchmark_results.json')); exit(0 if data['overall_target_achieved'] else 1)"; then
      echo "Performance targets not met"
      exit 1
    fi
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure you're running from project root
   cd /path/to/planwise_navigator
   python scripts/benchmark_multi_year_coordination.py --scenario small
   ```

2. **Memory Issues on Large Scenarios**
   ```bash
   # Check available memory first
   python -c "import psutil; print(f'Available: {psutil.virtual_memory().available/1024**3:.1f}GB')"

   # Run smaller scenario if memory is limited
   python scripts/benchmark_multi_year_coordination.py --scenario medium
   ```

3. **Slow Performance**
   ```bash
   # Run with verbose logging to identify bottlenecks
   python scripts/benchmark_multi_year_coordination.py --scenario small --verbose
   ```

### Performance Expectations

| Scenario | Expected Time | Memory Usage | Target Reduction |
|----------|---------------|--------------|------------------|
| Small    | 5-10 seconds  | < 1GB        | ≥ 60%           |
| Medium   | 30-60 seconds | 2-4GB        | ≥ 65%           |
| Large    | 3-5 minutes   | 6-12GB       | ≥ 70%           |

### System Requirements

- **Minimum**: 4GB RAM, 2 CPU cores
- **Recommended**: 16GB RAM, 4+ CPU cores
- **Large scenarios**: 32GB RAM, 8+ CPU cores

## Extending the Benchmark

### Adding New Components

1. Create benchmark method in `CoordinationBenchmark` class:
   ```python
   def benchmark_new_component(self, scenario, enable_optimization=True):
       # Implementation here
       return ComponentBenchmarkResult(...)
   ```

2. Add to component benchmarks dictionary:
   ```python
   component_benchmarks['new_component'] = self.benchmark_new_component
   ```

### Adding New Scenarios

1. Add to scenarios dictionary in `__init__`:
   ```python
   self.scenarios['extra_large'] = BenchmarkScenario(
       name='extra_large',
       workforce_size=100000,
       simulation_years=[2024, 2025, 2026, 2027, 2028, 2029],
       events_per_employee_per_year=10,
       description='Extra large scenario for extreme testing'
   )
   ```

### Custom Metrics

Extend `ComponentBenchmarkResult` and `IntegrationBenchmarkResult` dataclasses to include additional metrics specific to your use case.

## Best Practices

1. **Run validation test first** to ensure environment is correct
2. **Start with small scenarios** for development and debugging
3. **Use verbose logging** when investigating performance issues
4. **Save results** for historical comparison and trend analysis
5. **Run on consistent hardware** for reliable benchmarking
6. **Monitor system resources** during large scenario testing
7. **Integrate with CI/CD** for continuous performance monitoring

## Support and Troubleshooting

For issues with the benchmark suite:

1. Check the validation test output
2. Review logs with `--verbose` flag
3. Verify system resources meet requirements
4. Check for recent changes that might affect performance
5. Compare results with historical baselines

The benchmark suite is designed to be self-contained and should work with the existing PlanWise Navigator codebase without additional dependencies.
