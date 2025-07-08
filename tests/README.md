# PlanWise Navigator Optimization Testing Framework

This comprehensive testing framework validates all aspects of the PlanWise Navigator optimization system, from individual components to complete user workflows.

## 🎯 Test Coverage Overview

| Test Category | Purpose | Files | Coverage |
|---------------|---------|--------|----------|
| **Unit Tests** | Individual component validation | `test_advanced_optimization_unit.py`, `test_optimization_schemas.py` | 95%+ |
| **Integration Tests** | Cross-component workflows | `test_compensation_workflow_integration.py`, `test_compensation_tuning_integration.py` | 90%+ |
| **Performance Tests** | Speed and memory benchmarking | `test_optimization_performance.py` | Benchmarks |
| **Edge Case Tests** | Boundary and stress conditions | `test_optimization_edge_cases.py` | Edge cases |
| **Error Handling Tests** | Failure mode validation | `test_optimization_error_handling.py` | Error scenarios |
| **End-to-End Tests** | Complete user journeys | `test_end_to_end_optimization.py` | User workflows |

## 🚀 Quick Start

### Run All Tests
```bash
python run_optimization_tests.py --all
```

### Run Specific Categories
```bash
# Core functionality
python run_optimization_tests.py --unit --integration

# Performance validation
python run_optimization_tests.py --performance --report

# Comprehensive validation
python run_optimization_tests.py --e2e --verbose
```

### Quick Development Testing
```bash
python run_optimization_tests.py --quick
```

## 📋 Test Categories Detailed

### 1. Unit Tests (`test_advanced_optimization_unit.py`)

**Purpose**: Validate individual optimization components in isolation.

**Components Tested**:
- `CompensationOptimizer`: Parameter validation, bounds checking, algorithm selection
- `ObjectiveFunctions`: Cost calculations, equity metrics, target achievement
- `SensitivityAnalyzer`: Parameter importance ranking, gradient calculations
- `EvidenceGenerator`: Report generation, data formatting, risk assessment

**Key Test Scenarios**:
```python
# Parameter bounds validation
def test_parameter_bounds_validation():
    # Test valid parameters at boundaries
    # Test invalid parameters outside bounds
    # Test floating point precision issues

# Optimization algorithm selection
def test_optimization_algorithm_selection():
    # Test SLSQP, L-BFGS-B algorithm selection
    # Test fallback mechanisms
    # Test convergence criteria

# Objective function calculations
def test_objective_function_calculations():
    # Test cost objective with various scenarios
    # Test equity objective with compensation distributions
    # Test combined objective weighting
```

### 2. Integration Tests (`test_compensation_workflow_integration.py`)

**Purpose**: Validate complete workflows across components.

**Workflows Tested**:
- UI Parameter Changes → Database Updates → Simulation Execution
- Optimization Engine → Parameter Suggestions → Validation Pipeline
- Advanced Optimization → Compensation Tuning → Results Validation

**Key Integration Scenarios**:
```python
# UI to database parameter flow
def test_ui_to_database_parameter_flow():
    # Simulate UI parameter changes
    # Convert to parameter format
    # Validate and transform to compensation tuning format
    # Verify database state

# Multi-method execution consistency
def test_multi_method_execution_consistency():
    # Direct parameter validation
    # Individual parameter validation
    # Compensation tuning format validation
    # Verify consistency across methods
```

### 3. Performance Tests (`test_optimization_performance.py`)

**Purpose**: Validate system performance characteristics and scalability.

**Performance Areas**:
- Algorithm convergence speed
- Memory usage patterns and leak detection
- Scalability with large datasets
- Caching efficiency
- Database query performance

**Benchmarks**:
```python
PERFORMANCE_BENCHMARKS = {
    "parameter_validation": {"max_time": 0.1, "max_memory": 10},
    "optimization_execution": {"max_time": 5.0, "max_memory": 100},
    "simulation_pipeline": {"max_time": 30.0, "max_memory": 200}
}
```

### 4. Edge Case Tests (`test_optimization_edge_cases.py`)

**Purpose**: Test boundary conditions, extreme scenarios, and data corruption.

**Edge Case Categories**:
- **Boundary Values**: Min/max parameters, floating point precision
- **Data Corruption**: Malformed inputs, missing data, inconsistent states
- **Extreme Scenarios**: Zero budgets, massive growth, workforce reduction
- **Concurrent Access**: Race conditions, resource contention

**Example Edge Cases**:
```python
# Extreme parameter values
extreme_params = {
    "merit_rate_level_1": 0.08,  # Near maximum
    "merit_rate_level_5": 0.02,  # Near minimum
    "cola_rate": 0.0,            # Zero COLA
}

# Floating point precision
precision_params = {
    "merit_rate_level_1": 0.1 + 0.2 - 0.3,  # Floating point edge case
    "cola_rate": 1.0 / 3.0 * 3.0 - 1.0     # Should be 0 but...
}
```

### 5. Error Handling Tests (`test_optimization_error_handling.py`)

**Purpose**: Validate error handling and recovery mechanisms.

**Error Scenarios**:
- **Database Errors**: Connection failures, query errors, lock conflicts
- **Optimization Failures**: Non-convergence, numerical issues
- **Input Validation**: Invalid parameters, malformed data
- **System Resources**: Memory exhaustion, timeout conditions

**Recovery Mechanisms**:
```python
# Graceful degradation
def test_graceful_degradation():
    # Test fallback when features fail
    # Verify basic functionality remains
    # Check error message quality

# Retry logic
def test_database_connection_retry_logic():
    # Simulate intermittent failures
    # Test retry mechanisms
    # Verify eventual success
```

### 6. End-to-End Tests (`test_end_to_end_optimization.py`)

**Purpose**: Validate complete user journeys and business scenarios.

**User Journey Scenarios**:
- **Cost Optimization**: Minimize costs while maintaining competitiveness
- **Equity Focus**: Improve compensation equity across job levels
- **Balanced Approach**: Balance cost, equity, and target achievement
- **Aggressive Growth**: Support business growth with competitive compensation
- **Budget Constrained**: Optimize within strict budget constraints

**Complete Workflow Validation**:
```python
# Business scenario end-to-end
@pytest.mark.parametrize("scenario", business_scenarios)
def test_business_scenario_end_to_end(scenario):
    # 1. Parameter validation
    # 2. Optimization execution
    # 3. Simulation execution
    # 4. Evidence generation
    # 5. Result validation
    # 6. Business outcome verification
```

## 🔧 Test Configuration

### Pytest Configuration (`conftest.py`)

**Test Markers**:
- `@pytest.mark.unit`: Unit tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.performance`: Performance tests
- `@pytest.mark.e2e`: End-to-end tests
- `@pytest.mark.edge_case`: Edge case tests
- `@pytest.mark.error_handling`: Error handling tests

**Shared Fixtures**:
```python
@pytest.fixture
def mock_duckdb_resource():
    """Provide mock DuckDB resource for testing."""

@pytest.fixture
def sample_workforce_data():
    """Generate sample workforce data for testing."""

@pytest.fixture
def performance_tracker():
    """Provide performance tracking utility."""
```

### Environment Setup

**Required Dependencies**:
```bash
pip install pytest pytest-mock pytest-cov memory_profiler psutil
```

**Environment Variables**:
```bash
export DAGSTER_HOME=~/dagster_home_planwise
export PYTHONPATH=/Users/nicholasamaral/planwise_navigator
```

## 📊 Running Tests

### Test Runner Options

```bash
# Basic test categories
python run_optimization_tests.py --unit          # Unit tests only
python run_optimization_tests.py --integration   # Integration tests only
python run_optimization_tests.py --performance   # Performance tests only
python run_optimization_tests.py --e2e          # End-to-end tests only

# Combined categories
python run_optimization_tests.py --quick        # Unit + integration (development)
python run_optimization_tests.py --all          # All test categories

# Execution options
python run_optimization_tests.py --verbose      # Detailed output
python run_optimization_tests.py --coverage     # Coverage report
python run_optimization_tests.py --parallel     # Parallel execution
python run_optimization_tests.py --report       # Generate JSON report
```

### Direct Pytest Execution

```bash
# Run specific test file
pytest tests/test_advanced_optimization_unit.py -v

# Run specific test method
pytest tests/test_optimization_schemas.py::TestParameterSchema::test_parameter_validation -v

# Run with markers
pytest -m "unit and not slow" -v
pytest -m "performance" --tb=short
pytest -m "e2e" -s --tb=long

# Run with coverage
pytest --cov=streamlit_dashboard --cov=orchestrator.optimization --cov-report=html
```

## 🎯 Test Development Guidelines

### Writing Unit Tests

```python
class TestNewComponent:
    """Test new optimization component."""

    def setup_method(self):
        """Setup for each test method."""
        self.component = NewComponent()
        self.mock_data = generate_test_data()

    def test_component_functionality(self):
        """Test core component functionality."""
        # Arrange
        input_data = self.mock_data

        # Act
        result = self.component.process(input_data)

        # Assert
        assert result.is_valid
        assert result.meets_business_requirements()

    def test_component_error_handling(self):
        """Test component error handling."""
        with pytest.raises(ValueError, match="Expected error message"):
            self.component.process(invalid_data)
```

### Writing Integration Tests

```python
@pytest.mark.integration
def test_component_integration():
    """Test integration between components."""

    # Setup test environment
    env = TestEnvironment()

    # Execute workflow
    result = env.execute_workflow(parameters)

    # Validate end-to-end behavior
    assert result.success
    assert result.meets_integration_requirements()
```

### Writing Performance Tests

```python
@pytest.mark.performance
def test_component_performance(performance_tracker):
    """Test component performance characteristics."""

    performance_tracker.start()

    # Execute performance-critical code
    result = execute_performance_test()

    metrics = performance_tracker.stop()

    # Assert performance requirements
    performance_tracker.assert_performance(
        max_time=5.0,
        max_memory=100.0
    )
```

## 📈 Test Results and Reporting

### Test Report Structure

```json
{
  "timestamp": 1699123456.789,
  "execution_time": 45.67,
  "results": {
    "unit": true,
    "integration": true,
    "performance": true,
    "edge_case": true,
    "error_handling": true,
    "e2e": true
  },
  "summary": {
    "total_categories": 6,
    "passed_categories": 6,
    "overall_success": true
  }
}
```

### Coverage Report

Coverage reports are generated in HTML format when using `--coverage` option:
- **Target Coverage**: 95%+ for unit tests, 90%+ for integration tests
- **Coverage Areas**: All optimization components, parameter schemas, workflows

### Performance Benchmarks

Performance tests validate against established benchmarks:
- **Parameter Validation**: < 100ms, < 10MB memory
- **Optimization Execution**: < 5s, < 100MB memory
- **End-to-End Workflows**: < 30s, < 200MB memory

## 🔍 Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=/Users/nicholasamaral/planwise_navigator

# Or use relative imports in test files
sys.path.insert(0, str(Path(__file__).parent.parent))
```

**Database Connection Issues**:
```python
# Use mock database for testing
@pytest.fixture
def mock_duckdb():
    mock_resource = Mock()
    # Setup mock responses
    return mock_resource
```

**Performance Test Failures**:
```bash
# Run performance tests in isolation
pytest tests/test_optimization_performance.py -v -s

# Check system resources
htop  # Monitor CPU/memory during tests
```

### Debug Mode

```bash
# Run with debug output
pytest tests/ -v -s --tb=long --capture=no

# Run single test with maximum output
pytest tests/test_file.py::test_method -vvv -s --tb=long
```

## 🤝 Contributing to Tests

### Adding New Tests

1. **Identify Test Category**: Unit, integration, performance, etc.
2. **Create Test File**: Follow naming convention `test_*.py`
3. **Use Fixtures**: Leverage shared fixtures from `conftest.py`
4. **Add Markers**: Use appropriate pytest markers
5. **Update Runner**: Add new test files to `run_optimization_tests.py`

### Test Review Checklist

- [ ] Tests are well-documented and named clearly
- [ ] Appropriate test markers are used
- [ ] Mock objects are used properly to isolate units
- [ ] Performance tests have reasonable benchmarks
- [ ] Error scenarios are covered comprehensively
- [ ] Tests are deterministic and repeatable

## 📚 References

- [pytest Documentation](https://docs.pytest.org/)
- [PlanWise Navigator Architecture](../CLAUDE.md)
- [Optimization Components](../orchestrator/optimization/)
- [Parameter Schemas](../streamlit_dashboard/optimization_schemas.py)
