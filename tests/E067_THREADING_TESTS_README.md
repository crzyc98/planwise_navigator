# Epic E067 Multi-Threading Test Suite

This comprehensive test suite validates the multi-threading functionality implemented for Epic E067: Multi-Threading PlanAlign Orchestrator. The tests ensure the implementation meets all performance targets and maintains data integrity across different thread configurations.

## Test Categories

### 1. Unit Tests (`test_e067_threading_comprehensive.py`)
**Purpose**: Validate individual threading components in isolation

**Components Tested**:
- `ThreadingSettings` configuration and validation
- `ModelParallelizationSettings` configuration
- `ResourceManagerSettings` configuration
- `DbtRunner` with dynamic threading support
- `ModelDependencyAnalyzer` and model classification
- `ParallelExecutionEngine` with dependency-aware scheduling
- `ResourceManager` with adaptive thread scaling
- `MemoryMonitor` and `CPUMonitor` functionality

**Key Validations**:
- Thread count validation (1-16) with appropriate error messages
- Model classification accuracy (parallel-safe vs sequential vs conditional)
- Dependency analysis correctness
- Thread pool management and cleanup
- Configuration loading consistency

### 2. Integration Tests (`integration/test_e067_threading_determinism.py`)
**Purpose**: Validate end-to-end multi-year simulations across thread configurations

**Test Areas**:
- Configuration loading and validation determinism
- Model execution order consistency
- Random seed consistency across thread counts
- State accumulation determinism (enrollment tracking)
- Event generation consistency
- Parallel vs sequential execution equivalence

**Key Validations**:
- Same input configuration produces identical results across runs
- Different thread counts produce logically equivalent results
- Deterministic execution ordering when required
- Random seed produces consistent results regardless of thread count

### 3. Performance Tests (`performance/test_e067_threading_benchmarks.py`)
**Purpose**: Benchmark performance scaling and validate Epic E067 targets

**Performance Targets Validated**:
- **Baseline**: 10 minutes for 5-year simulation (single-threaded)
- **Target**: 7 minutes for 5-year simulation (4 threads)
- **Maximum**: 5.5 minutes for 5-year simulation (8+ threads)
- **Memory**: <6GB peak usage with 4 threads
- **CPU**: 70-85% utilization across available cores

**Test Areas**:
- Thread count performance scaling (1, 2, 4, 8, 16 threads)
- Memory usage patterns and scaling
- CPU utilization measurement and efficiency
- Resource constraint impact on performance
- Model parallelization effectiveness

### 4. Resource Validation Tests (`test_e067_resource_validation.py`)
**Purpose**: Validate resource management and monitoring

**Components Tested**:
- `MemoryMonitor` functionality and pressure detection
- `CPUMonitor` utilization tracking and recommendations
- `ResourceManager` adaptive scaling under pressure
- Memory limit enforcement and validation
- CPU efficiency across thread counts
- Thread pool resource management

**Key Validations**:
- Memory usage stays within configured limits
- CPU utilization meets target ranges (70-85%)
- Adaptive scaling works under resource pressure
- Resource constraints are properly enforced
- Performance targets are met under resource limits

### 5. Stress Tests (`stress/test_e067_threading_stress.py`)
**Purpose**: Test system behavior under extreme conditions

**Stress Scenarios**:
- Maximum thread count stability (16 threads)
- Memory pressure handling and recovery
- Execution error recovery and cascading failures
- Resource exhaustion scenarios (memory, CPU, file descriptors)
- Concurrent access safety with high concurrency
- Long-running simulation stability

**Key Validations**:
- System remains stable at maximum thread counts
- Graceful degradation under resource pressure
- Error recovery mechanisms work correctly
- No memory leaks during extended execution
- Thread safety under high concurrency

## Running the Tests

### Quick Start
```bash
# Run all fast tests (excludes performance/stress)
python scripts/run_e067_threading_tests.py --quick

# Run specific category
python scripts/run_e067_threading_tests.py --category unit

# Run performance benchmarks
python scripts/run_e067_threading_tests.py --performance --report

# Run stress tests
python scripts/run_e067_threading_tests.py --stress --verbose
```

### Individual Test Files
```bash
# Unit tests
pytest tests/test_e067_threading_comprehensive.py -v

# Performance benchmarks
pytest tests/performance/test_e067_threading_benchmarks.py -v -m performance

# Determinism validation
pytest tests/integration/test_e067_threading_determinism.py -v

# Resource validation
pytest tests/test_e067_resource_validation.py -v

# Stress tests
pytest tests/stress/test_e067_threading_stress.py -v -m stress
```

### Test Markers
Tests are organized using pytest markers:

- `threading`: All threading-related tests
- `performance`: Performance benchmarking tests (may be slow)
- `stress`: Stress tests that push system limits
- `determinism`: Tests that validate deterministic behavior
- `integration`: End-to-end integration tests
- `unit`: Unit tests for individual components
- `slow`: Slow-running tests (skipped by default)
- `resource`: Tests that validate resource usage patterns

### Filter Tests by Marker
```bash
# Run only unit tests
pytest -m "unit and threading" tests/

# Run performance tests only
pytest -m "performance" tests/

# Skip slow tests
pytest -m "not slow" tests/

# Run determinism tests
pytest -m "determinism" tests/
```

## Test Configuration

### Pytest Configuration (`pytest_e067_threading.ini`)
The test suite includes specialized pytest configuration:

- Markers for different test categories
- Timeout settings for long-running tests
- Custom logging configuration
- Environment variables for testing mode
- Output formatting and reporting options

### Environment Variables
The tests use several environment variables:

- `E067_TESTING_MODE=true`: Enables testing mode
- `THREADING_TEST_MODE=enabled`: Enables threading test mode
- `DISABLE_PRODUCTION_SAFETY_CHECKS=true`: Disables production safety checks for testing

## Performance Target Validation

The test suite validates specific performance targets from Epic E067:

### Execution Time Targets
- **1 Thread (Baseline)**: 10 minutes for 5-year simulation
- **4 Threads (Target)**: 7 minutes for 5-year simulation (30% improvement)
- **8+ Threads (Maximum)**: 5.5 minutes for 5-year simulation (45% improvement)

### Resource Usage Targets
- **Memory Usage**: <6GB peak usage with 4 threads
- **CPU Utilization**: 70-85% utilization across available cores
- **Thread Efficiency**: >80% parallelism utilization ratio

### Quality Targets
- **Determinism**: 100% consistent results across runs with same seed
- **Error Rate**: <1% failure rate under normal conditions
- **Recovery Rate**: >95% successful recovery from transient errors

## Test Data and Mocking

The tests use extensive mocking to simulate realistic execution scenarios:

### Mock Components
- `DbtRunner`: Simulates dbt command execution with realistic timing
- `ModelDependencyAnalyzer`: Provides mock dependency analysis
- `ParallelExecutionEngine`: Tests actual parallel execution logic
- System resources (CPU, memory) for controlled testing

### Simulation Data
- Realistic model counts (20-100 models per simulation)
- Multi-year simulation scenarios (2025-2029)
- Various workload complexities (staging, intermediate, marts)
- Different parallelization opportunities per model type

## Troubleshooting

### Common Issues

**Memory-related test failures**:
- Ensure sufficient system memory (>4GB recommended)
- Close other applications during stress tests
- Check if memory limits are appropriate for your system

**CPU-related test failures**:
- CPU utilization tests may vary by system load
- Performance targets may need adjustment for slower systems
- Consider running tests during low system activity

**Threading-related failures**:
- Verify system thread limits: `ulimit -u`
- Check for conflicting processes using threads
- Ensure Python supports threading (should be standard)

**Timeout failures**:
- Increase timeout values for slower systems
- Use `--timeout` option with test runner
- Consider running categories individually

### Debug Options

```bash
# Verbose output
python scripts/run_e067_threading_tests.py --verbose

# Continue on failures (don't stop at first failure)
python scripts/run_e067_threading_tests.py --continue-on-failure

# Increase timeout for slow systems
python scripts/run_e067_threading_tests.py --timeout 1200

# Generate detailed report
python scripts/run_e067_threading_tests.py --report
```

### Log Files
Test execution logs are saved to:
- `tests/logs/e067_threading_tests.log`: Detailed execution log
- `test_reports/e067_*_results.json`: JSON test results per category
- `test_reports/e067_threading_summary_*.txt`: Comprehensive summary reports

## Continuous Integration

The test suite is designed to run in CI environments:

### CI Configuration Example
```yaml
# GitHub Actions example
- name: Run E067 Threading Tests
  run: |
    python scripts/run_e067_threading_tests.py --quick --report

- name: Upload Test Results
  uses: actions/upload-artifact@v3
  with:
    name: e067-test-results
    path: test_reports/
```

### CI Considerations
- Use `--quick` for fast CI runs
- Save test reports as artifacts
- Set appropriate timeouts for CI environment
- Consider system resources in CI (may need different targets)

## Contributing

When adding new threading-related functionality:

1. Add unit tests to `test_e067_threading_comprehensive.py`
2. Add integration tests if cross-component functionality
3. Add performance tests if performance-critical
4. Add stress tests for error conditions
5. Update this README with new test descriptions

### Test Writing Guidelines

- Use descriptive test names that explain what is being validated
- Include docstrings explaining the test purpose and what it validates
- Use appropriate markers (`@pytest.mark.threading`, etc.)
- Mock external dependencies consistently
- Validate both success and failure scenarios
- Include performance measurements where relevant

## Related Documentation

- [Epic E067: Multi-Threading PlanAlign Orchestrator](../docs/epics/E067_multi_threading_planalign_orchestrator.md)
- [Story S067-02: Model-Level Parallelization](../docs/S067-02-Model-Level-Parallelization.md)
- [Threading Configuration Guide](../planalign_orchestrator/README.md#threading-configuration)
- [Performance Benchmarking Guide](../docs/performance/README.md)

---

*Generated for Epic E067 Multi-Threading Implementation - Last Updated: 2025-09-02*
