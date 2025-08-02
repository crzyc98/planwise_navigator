# orchestrator_dbt API Reference

**Version:** 1.0.0
**Package:** `orchestrator_dbt`
**Performance Target:** 82% improvement over legacy MVP

A comprehensive API reference for the optimized orchestrator_dbt package, providing production-ready multi-year workforce simulation capabilities with enhanced performance monitoring and error handling.

## Table of Contents

- [Quick Start](#quick-start)
- [CLI Interface](#cli-interface)
- [Core Functions](#core-functions)
- [Configuration Management](#configuration-management)
- [Performance Monitoring](#performance-monitoring)
- [Error Handling](#error-handling)
- [Integration Patterns](#integration-patterns)
- [Examples](#examples)

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m orchestrator_dbt.run_multi_year --help
```

### Basic Usage

```python
import asyncio
from orchestrator_dbt.run_multi_year import (
    run_foundation_benchmark,
    run_enhanced_multi_year_simulation,
    OptimizationLevel
)

# Foundation setup benchmark
async def quick_start():
    result = await run_foundation_benchmark(
        optimization_level=OptimizationLevel.HIGH,
        benchmark_mode=True
    )
    print(f"Foundation setup: {result['execution_time']:.2f}s")

asyncio.run(quick_start())
```

## CLI Interface

### Command Line Usage

The primary CLI entry point provides comprehensive simulation and benchmarking capabilities:

```bash
python -m orchestrator_dbt.run_multi_year [OPTIONS]
```

### CLI Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--start-year` | int | - | Start year for simulation (required for simulation modes) |
| `--end-year` | int | - | End year for simulation (required for simulation modes) |
| `--optimization` | choice | `high` | Optimization level: `high`, `medium`, `low`, `fallback` |
| `--max-workers` | int | 4 | Maximum concurrent workers |
| `--batch-size` | int | 1000 | Batch size for processing |
| `--enable-compression` | flag | False | Enable state compression for memory efficiency |
| `--fail-fast` | flag | False | Stop on first year failure |
| `--performance-mode` | flag | False | Enable detailed performance monitoring |
| `--foundation-only` | flag | False | Run foundation setup only |
| `--compare-mvp` | flag | False | Compare performance with MVP orchestrator |
| `--test-config` | flag | False | Test configuration compatibility |
| `--benchmark` | flag | False | Run in comprehensive benchmark mode |
| `--config` | str | None | Path to configuration file (YAML) |
| `--log-file` | str | None | Path to log file |
| `--verbose` | flag | False | Enable verbose logging |
| `--structured-logs` | flag | False | Use structured logging format |

### CLI Examples

```bash
# Basic multi-year simulation
python -m orchestrator_dbt.run_multi_year --start-year 2025 --end-year 2029

# High-performance simulation
python -m orchestrator_dbt.run_multi_year \
    --start-year 2025 --end-year 2029 \
    --optimization high \
    --max-workers 8 \
    --batch-size 2000 \
    --enable-compression \
    --performance-mode

# Foundation setup benchmark
python -m orchestrator_dbt.run_multi_year \
    --foundation-only \
    --benchmark \
    --verbose

# Performance comparison with MVP
python -m orchestrator_dbt.run_multi_year \
    --start-year 2025 --end-year 2027 \
    --compare-mvp \
    --benchmark

# Configuration compatibility test
python -m orchestrator_dbt.run_multi_year \
    --test-config \
    --config /path/to/simulation_config.yaml
```

## Core Functions

### run_foundation_benchmark()

Executes foundation setup with comprehensive performance benchmarking.

```python
async def run_foundation_benchmark(
    optimization_level: OptimizationLevel,
    config_path: Optional[str] = None,
    benchmark_mode: bool = False
) -> Dict[str, Any]
```

**Parameters:**
- `optimization_level` (OptimizationLevel): Optimization level for execution
- `config_path` (Optional[str]): Path to configuration file
- `benchmark_mode` (bool): Enable detailed benchmarking

**Returns:**
- `Dict[str, Any]`: Benchmark results with performance metrics

**Example:**
```python
result = await run_foundation_benchmark(
    optimization_level=OptimizationLevel.HIGH,
    config_path="config/simulation_config.yaml",
    benchmark_mode=True
)

print(f"Success: {result['success']}")
print(f"Execution time: {result['execution_time']:.2f}s")
print(f"Target met (<10s): {result['target_met']}")
print(f"Performance improvement: {result['performance_improvement']:.1%}")
```

**Performance Targets:**
- Execution time: < 10 seconds
- Performance improvement: > 82% vs legacy
- Memory efficiency: > 70%

### run_enhanced_multi_year_simulation()

Executes complete multi-year simulation with enhanced monitoring.

```python
async def run_enhanced_multi_year_simulation(
    start_year: int,
    end_year: int,
    optimization_level: OptimizationLevel,
    max_workers: int,
    batch_size: int,
    enable_compression: bool,
    fail_fast: bool,
    performance_mode: bool = False,
    config_path: Optional[str] = None
) -> Dict[str, Any]
```

**Parameters:**
- `start_year` (int): Starting year for simulation
- `end_year` (int): Ending year for simulation
- `optimization_level` (OptimizationLevel): Optimization configuration
- `max_workers` (int): Maximum concurrent workers
- `batch_size` (int): Processing batch size
- `enable_compression` (bool): Enable state compression
- `fail_fast` (bool): Stop on first failure
- `performance_mode` (bool): Enable detailed performance monitoring
- `config_path` (Optional[str]): Path to configuration file

**Returns:**
- `Dict[str, Any]`: Simulation results with performance metrics

**Example:**
```python
result = await run_enhanced_multi_year_simulation(
    start_year=2025,
    end_year=2029,
    optimization_level=OptimizationLevel.HIGH,
    max_workers=8,
    batch_size=2000,
    enable_compression=True,
    fail_fast=False,
    performance_mode=True,
    config_path="config/simulation_config.yaml"
)

print(f"Simulation ID: {result['simulation_id']}")
print(f"Completed years: {result['completed_years']}")
print(f"Success rate: {result['success_rate']:.1%}")
print(f"Total time: {result['total_execution_time']:.2f}s")
```

### run_comprehensive_performance_comparison()

Executes performance comparison with MVP orchestrator for regression testing.

```python
async def run_comprehensive_performance_comparison(
    start_year: int,
    end_year: int,
    config_path: Optional[str] = None,
    benchmark_mode: bool = False
) -> Dict[str, Any]
```

**Parameters:**
- `start_year` (int): Starting year for comparison
- `end_year` (int): Ending year for comparison
- `config_path` (Optional[str]): Path to configuration file
- `benchmark_mode` (bool): Enable detailed benchmark reporting

**Returns:**
- `Dict[str, Any]`: Comparison results with performance metrics

**Example:**
```python
result = await run_comprehensive_performance_comparison(
    start_year=2025,
    end_year=2027,
    config_path="config/simulation_config.yaml",
    benchmark_mode=True
)

print(f"MVP available: {result['mvp_available']}")
print(f"Performance improvement: {result['improvement']:.1%}")
print(f"Target met (82%): {result['target_met']}")
print(f"Regression test: {'PASSED' if result['regression_test_passed'] else 'FAILED'}")
```

## Configuration Management

### load_and_validate_config()

Loads and validates simulation configuration with comprehensive error checking.

```python
def load_and_validate_config(config_path: Optional[str] = None) -> Dict[str, Any]
```

**Parameters:**
- `config_path` (Optional[str]): Path to YAML configuration file

**Returns:**
- `Dict[str, Any]`: Validated configuration dictionary

**Configuration Schema:**

```yaml
simulation:
  start_year: 2025        # Required: int
  end_year: 2029          # Required: int
  target_growth_rate: 0.03 # Required: float (0.0-1.0)

workforce:
  total_termination_rate: 0.12      # Required: float (0.0-1.0)
  new_hire_termination_rate: 0.25   # Optional: float (0.0-1.0)

eligibility:
  waiting_period_days: 365          # Optional: int

enrollment:
  auto_enrollment:
    hire_date_cutoff: "2024-01-01"  # Optional: date string
    scope: "new_hires_only"         # Optional: string

compensation:
  cola_rate: 0.025                  # Optional: float
  merit_pool: 0.03                  # Optional: float

random_seed: 42                     # Required: int
```

### validate_configuration()

Validates configuration structure and value ranges.

```python
def validate_configuration(config: Dict[str, Any]) -> Tuple[bool, List[str]]
```

**Parameters:**
- `config` (Dict[str, Any]): Configuration dictionary to validate

**Returns:**
- `Tuple[bool, List[str]]`: (is_valid, list_of_errors)

**Validation Rules:**
- Required sections: `simulation`, `workforce`, `random_seed`
- Year range: `end_year > start_year`
- Rate values: All rates must be between 0.0 and 1.0
- Large year ranges (>10 years) generate warnings

### test_configuration_compatibility()

Tests configuration compatibility with both new and legacy systems.

```python
def test_configuration_compatibility(config_path: Optional[str] = None) -> Dict[str, Any]
```

**Parameters:**
- `config_path` (Optional[str]): Path to configuration file

**Returns:**
- `Dict[str, Any]`: Compatibility test results

**Example:**
```python
result = test_configuration_compatibility("config/simulation_config.yaml")

print(f"Configuration valid: {result['config_valid']}")
print(f"New system compatible: {result['new_system_compatible']}")
print(f"Legacy compatible: {result['legacy_compatible']}")

if result['issues']:
    print("Issues found:")
    for issue in result['issues']:
        print(f"  - {issue}")

if result['recommendations']:
    print("Recommendations:")
    for rec in result['recommendations']:
        print(f"  - {rec}")
```

## Performance Monitoring

### PerformanceMonitor

Real-time performance monitoring and reporting class.

```python
class PerformanceMonitor:
    def __init__(self):
        """Initialize performance monitor."""

    def start(self) -> None:
        """Start performance monitoring."""

    def checkpoint(self, name: str) -> float:
        """Record a performance checkpoint."""

    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
```

**Usage Example:**
```python
monitor = PerformanceMonitor()
monitor.start()

# Perform operations
operation_1()
monitor.checkpoint("operation_1_complete")

operation_2()
monitor.checkpoint("operation_2_complete")

# Get performance summary
summary = monitor.get_summary()
print(f"Total time: {summary['total_time']:.2f}s")
print(f"Peak memory: {summary['peak_memory_mb']:.1f}MB")
print(f"Memory efficiency: {summary['memory_efficiency']:.1%}")
```

**Performance Metrics:**
- `total_time`: Total execution time in seconds
- `peak_memory_mb`: Peak memory usage in MB
- `avg_memory_mb`: Average memory usage in MB
- `memory_efficiency`: Memory efficiency ratio (0.0-1.0)
- `checkpoints`: Detailed timing for each checkpoint

### OptimizationLevel

Enumeration for optimization levels.

```python
class OptimizationLevel(Enum):
    HIGH = "high"           # Maximum performance optimization
    MEDIUM = "medium"       # Balanced performance and stability
    LOW = "low"             # Conservative optimization
    FALLBACK = "fallback"   # Minimal optimization for compatibility
```

**Optimization Level Impact:**

| Level | Performance | Memory Usage | Stability | Use Case |
|-------|-------------|--------------|-----------|----------|
| HIGH | Maximum | Optimized | Good | Production workloads |
| MEDIUM | Balanced | Moderate | Excellent | Development/testing |
| LOW | Conservative | Higher | Maximum | Debugging/troubleshooting |
| FALLBACK | Minimal | Highest | Maximum | Compatibility issues |

## Error Handling

### error_context()

Context manager for enhanced error handling with troubleshooting guidance.

```python
@contextmanager
def error_context(operation: str, troubleshooting_guide: str = ""):
    """Enhanced error handling with troubleshooting guidance."""
```

**Usage Example:**
```python
troubleshooting = """
Foundation setup troubleshooting:
1. Check database connectivity
2. Verify memory availability
3. Ensure configuration is valid
"""

with error_context("Foundation setup", troubleshooting):
    result = await run_foundation_benchmark(OptimizationLevel.HIGH)
```

**Automatic Troubleshooting:**
- **Database errors**: Connection, permissions, disk space guidance
- **Memory errors**: Batch size, compression, worker reduction suggestions
- **Dependency errors**: Sequential execution, data validation recommendations

### Exception Types

Common exceptions and their meanings:

```python
# Configuration errors
ValueError("Invalid configuration: missing required field")

# Performance errors
RuntimeError("Foundation setup exceeded 10 second target")

# Resource errors
MemoryError("Insufficient memory for batch processing")

# Dependency errors
RuntimeError("Sequential year execution validation failed")
```

## Integration Patterns

### Programmatic Integration

```python
import asyncio
from orchestrator_dbt.run_multi_year import *

class WorkforceSimulationService:
    """Service class for workforce simulation integration."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.monitor = PerformanceMonitor()

    async def run_simulation(self, start_year: int, end_year: int) -> dict:
        """Run complete simulation workflow."""
        self.monitor.start()

        # Foundation setup
        foundation_result = await run_foundation_benchmark(
            optimization_level=OptimizationLevel.HIGH,
            config_path=self.config_path,
            benchmark_mode=True
        )

        if not foundation_result['success']:
            raise RuntimeError("Foundation setup failed")

        # Multi-year simulation
        simulation_result = await run_enhanced_multi_year_simulation(
            start_year=start_year,
            end_year=end_year,
            optimization_level=OptimizationLevel.HIGH,
            max_workers=8,
            batch_size=2000,
            enable_compression=True,
            fail_fast=False,
            performance_mode=True,
            config_path=self.config_path
        )

        return {
            'foundation': foundation_result,
            'simulation': simulation_result,
            'performance': self.monitor.get_summary()
        }
```

### API Integration

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Workforce Simulation API")

class SimulationRequest(BaseModel):
    start_year: int
    end_year: int
    optimization_level: str = "high"
    config_path: str = "config/simulation_config.yaml"

@app.post("/api/v1/simulation/run")
async def run_simulation(request: SimulationRequest):
    """API endpoint for running simulations."""
    try:
        optimization = OptimizationLevel(request.optimization_level)

        result = await run_enhanced_multi_year_simulation(
            start_year=request.start_year,
            end_year=request.end_year,
            optimization_level=optimization,
            max_workers=4,
            batch_size=1000,
            enable_compression=True,
            fail_fast=False,
            performance_mode=True,
            config_path=request.config_path
        )

        return {"status": "success", "data": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Batch Processing Integration

```python
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

class BatchSimulationProcessor:
    """Batch processing for multiple simulation scenarios."""

    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent

    async def process_scenarios(self, scenarios: List[Dict]) -> List[Dict]:
        """Process multiple scenarios concurrently."""

        async def run_scenario(scenario):
            return await run_enhanced_multi_year_simulation(
                start_year=scenario['start_year'],
                end_year=scenario['end_year'],
                optimization_level=OptimizationLevel.HIGH,
                max_workers=2,  # Reduced for concurrent processing
                batch_size=1000,
                enable_compression=True,
                fail_fast=True,
                performance_mode=False,
                config_path=scenario.get('config_path')
            )

        # Process scenarios with controlled concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def bounded_scenario(scenario):
            async with semaphore:
                return await run_scenario(scenario)

        tasks = [bounded_scenario(scenario) for scenario in scenarios]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return results
```

## Examples

### Complete Workflow Example

```python
import asyncio
import logging
from pathlib import Path

async def complete_workflow_example():
    """Complete workflow demonstrating all major features."""

    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    config_path = "config/simulation_config.yaml"

    try:
        # 1. Configuration validation
        logger.info("🔧 Validating configuration...")
        config = load_and_validate_config(config_path)
        logger.info("✅ Configuration valid")

        # 2. Foundation benchmark
        logger.info("🚀 Running foundation benchmark...")
        foundation_result = await run_foundation_benchmark(
            optimization_level=OptimizationLevel.HIGH,
            config_path=config_path,
            benchmark_mode=True
        )

        if foundation_result['target_met']:
            logger.info(f"✅ Foundation setup: {foundation_result['execution_time']:.2f}s")
        else:
            logger.warning(f"⚠️  Foundation setup: {foundation_result['execution_time']:.2f}s (above target)")

        # 3. Multi-year simulation
        logger.info("🎯 Running multi-year simulation...")
        simulation_result = await run_enhanced_multi_year_simulation(
            start_year=config['simulation']['start_year'],
            end_year=config['simulation']['end_year'],
            optimization_level=OptimizationLevel.HIGH,
            max_workers=8,
            batch_size=2000,
            enable_compression=True,
            fail_fast=False,
            performance_mode=True,
            config_path=config_path
        )

        if simulation_result['success']:
            logger.info(f"✅ Simulation completed: {simulation_result['simulation_id']}")
            logger.info(f"   Years: {simulation_result['completed_years']}")
            logger.info(f"   Time: {simulation_result['total_execution_time']:.2f}s")
            logger.info(f"   Success rate: {simulation_result['success_rate']:.1%}")
        else:
            logger.error(f"❌ Simulation failed")
            logger.error(f"   Completed: {simulation_result['completed_years']}")
            logger.error(f"   Failed: {simulation_result['failed_years']}")

        # 4. Performance comparison (if MVP available)
        logger.info("📊 Running performance comparison...")
        comparison_result = await run_comprehensive_performance_comparison(
            start_year=config['simulation']['start_year'],
            end_year=min(config['simulation']['start_year'] + 2, config['simulation']['end_year']),
            config_path=config_path,
            benchmark_mode=True
        )

        if comparison_result['target_met']:
            logger.info(f"✅ Performance target met: {comparison_result['improvement']:.1%} improvement")
        else:
            logger.warning(f"⚠️  Performance target missed: {comparison_result['improvement']:.1%} improvement")

        return {
            'foundation': foundation_result,
            'simulation': simulation_result,
            'comparison': comparison_result
        }

    except Exception as e:
        logger.error(f"💥 Workflow failed: {e}")
        raise

# Run the complete workflow
if __name__ == "__main__":
    result = asyncio.run(complete_workflow_example())
```

### Performance Optimization Example

```python
async def performance_optimization_example():
    """Example demonstrating performance optimization strategies."""

    # Test different optimization configurations
    configurations = [
        {
            'name': 'Conservative',
            'optimization': OptimizationLevel.LOW,
            'workers': 2,
            'batch_size': 500,
            'compression': False
        },
        {
            'name': 'Balanced',
            'optimization': OptimizationLevel.MEDIUM,
            'workers': 4,
            'batch_size': 1000,
            'compression': True
        },
        {
            'name': 'High Performance',
            'optimization': OptimizationLevel.HIGH,
            'workers': 8,
            'batch_size': 2000,
            'compression': True
        }
    ]

    results = []

    for config in configurations:
        print(f"🧪 Testing {config['name']} configuration...")

        result = await run_enhanced_multi_year_simulation(
            start_year=2025,
            end_year=2027,
            optimization_level=config['optimization'],
            max_workers=config['workers'],
            batch_size=config['batch_size'],
            enable_compression=config['compression'],
            fail_fast=False,
            performance_mode=True
        )

        results.append({
            'name': config['name'],
            'success': result['success'],
            'time': result.get('total_execution_time', 0),
            'rate': result.get('performance_metrics', {}).get('records_per_second', 0)
        })

        print(f"   Time: {result.get('total_execution_time', 0):.2f}s")
        print(f"   Rate: {result.get('performance_metrics', {}).get('records_per_second', 0):.0f} records/sec")

    # Find optimal configuration
    successful_results = [r for r in results if r['success']]
    if successful_results:
        optimal = min(successful_results, key=lambda x: x['time'])
        print(f"\\n🏆 Optimal configuration: {optimal['name']}")
        print(f"   Time: {optimal['time']:.2f}s")
        print(f"   Rate: {optimal['rate']:.0f} records/sec")

    return results
```

## Support and Troubleshooting

### Common Issues

1. **Foundation setup > 10 seconds**
   - Reduce batch size
   - Check system resources
   - Use lower optimization level

2. **Memory errors during simulation**
   - Enable compression (`--enable-compression`)
   - Reduce max workers
   - Reduce batch size

3. **Configuration validation failures**
   - Check required fields
   - Verify value ranges (0.0-1.0 for rates)
   - Ensure year range is valid

4. **Performance regression test failures**
   - Verify MVP orchestrator is available
   - Check system performance baseline
   - Review configuration compatibility

### Performance Tuning Guidelines

- **CPU-bound workloads**: Increase `max_workers` up to CPU cores
- **Memory-constrained**: Enable compression, reduce batch size
- **I/O-bound**: Increase batch size, moderate worker count
- **Debugging**: Use `OptimizationLevel.LOW` with `verbose` logging

### Monitoring and Observability

Enable comprehensive monitoring with:
```bash
python -m orchestrator_dbt.run_multi_year \
    --performance-mode \
    --verbose \
    --structured-logs \
    --log-file simulation.log
```

For production deployments, integrate with your monitoring stack using the performance metrics returned by all API functions.

---

**For additional support, consult the troubleshooting guide and migration documentation.**
