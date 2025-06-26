# Epic E013: Validation Framework and Success Metrics

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Document Type**: Validation Framework
**Last Updated**: 2024-06-24

## Overview

This document defines the comprehensive validation framework for ensuring the pipeline refactoring achieves its goals while preserving identical simulation behavior. It includes success metrics, testing strategies, validation procedures, and acceptance criteria.

## Validation Objectives

### Primary Objectives
1. **Behavioral Identity**: Ensure refactored pipeline produces mathematically identical results
2. **Performance Preservation**: Maintain or improve execution performance
3. **Code Quality Improvement**: Achieve modularity, maintainability, and testability goals
4. **Operational Continuity**: Preserve all error handling, logging, and monitoring behavior

### Secondary Objectives
1. **Developer Experience**: Improve code readability and maintainability
2. **Testing Coverage**: Achieve comprehensive test coverage for all new components
3. **Documentation Quality**: Provide clear documentation for new modular architecture
4. **Future Extensibility**: Enable easier addition of new simulation features

## Success Metrics

### Code Quality Metrics

#### Quantitative Targets
| Metric | Baseline | Target | Success Criteria |
|--------|----------|--------|------------------|
| **run_multi_year_simulation LOC** | 325 lines | ≤100 lines | 70%+ reduction achieved |
| **Code Duplication** | ~60% overlap | <5% overlap | 90%+ reduction achieved |
| **Test Coverage** | ~80% | ≥95% | Comprehensive coverage |
| **Cyclomatic Complexity** | High (>15) | Medium (<10) | Measurable reduction |
| **Function Length** | >40 lines avg | <40 lines max | Per CLAUDE.md standards |

#### Code Quality Assessment Framework
```python
# Automated code quality checks
def assess_code_quality_improvements():
    """Measure code quality improvements after refactoring."""

    metrics = {
        "lines_of_code": {
            "run_multi_year_simulation": {"before": 325, "after": None, "target": 100},
            "run_year_simulation": {"before": 308, "after": None, "target": 200},
            "total_pipeline": {"before": 633, "after": None, "target": 400}
        },
        "duplication": {
            "event_processing": {"before": "100%", "after": None, "target": "0%"},
            "dbt_commands": {"before": "60%", "after": None, "target": "0%"},
            "error_handling": {"before": "40%", "after": None, "target": "<10%"}
        },
        "function_count": {
            "before": 4, "after": None, "target": 8  # More focused functions
        },
        "test_coverage": {
            "before": 80, "after": None, "target": 95  # Percentage
        }
    }

    return metrics
```

### Performance Metrics

#### Execution Time Targets
| Operation | Baseline | Target | Tolerance |
|-----------|----------|--------|-----------|
| **Single Year Simulation** | X seconds | X seconds | +5% max |
| **Multi-Year Simulation (5 years)** | Y seconds | Y seconds | +5% max |
| **dbt Command Execution** | Z seconds | Z seconds | +2% max |
| **Event Processing** | A seconds | A seconds | +3% max |

#### Memory Usage Targets
| Metric | Baseline | Target | Tolerance |
|--------|----------|--------|-----------|
| **Peak Memory Usage** | M MB | M MB | +10% max |
| **Memory Growth Rate** | G MB/year | G MB/year | +5% max |
| **Connection Pool Size** | C connections | C connections | No increase |

#### Performance Measurement Framework
```python
import time
import psutil
import tracemalloc
from typing import Dict, Any

class PerformanceBenchmark:
    """Framework for measuring simulation performance."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.metrics = {}

    def __enter__(self):
        # Start timing
        self.start_time = time.time()

        # Start memory tracking
        tracemalloc.start()
        self.process = psutil.Process()
        self.start_memory = self.process.memory_info().rss

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Stop timing
        self.end_time = time.time()
        self.execution_time = self.end_time - self.start_time

        # Stop memory tracking
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.end_memory = self.process.memory_info().rss

        self.metrics = {
            "execution_time_seconds": self.execution_time,
            "peak_memory_mb": peak / 1024 / 1024,
            "memory_growth_mb": (self.end_memory - self.start_memory) / 1024 / 1024,
            "test_name": self.test_name
        }

# Usage example
def test_simulation_performance():
    """Benchmark simulation performance."""
    with PerformanceBenchmark("multi_year_simulation") as benchmark:
        result = run_multi_year_simulation(test_config)

    # Validate performance within bounds
    assert benchmark.metrics["execution_time_seconds"] <= baseline_time * 1.05
    assert benchmark.metrics["memory_growth_mb"] <= baseline_memory * 1.10
```

### Behavioral Identity Metrics

#### Mathematical Validation
| Aspect | Validation Method | Success Criteria |
|--------|------------------|------------------|
| **YearResult Objects** | Field-by-field comparison | 100% identical |
| **Workforce Counts** | Database state comparison | Exact match |
| **Event Counts** | Event table comparison | Exact match |
| **Growth Calculations** | Mathematical verification | <0.0001% variance |
| **Random Number Generation** | Seed-based reproducibility | Identical sequences |

#### Logging and Output Validation
| Aspect | Validation Method | Success Criteria |
|--------|------------------|------------------|
| **Hiring Debug Logs** | Character-level comparison | 100% identical |
| **Error Messages** | Message format validation | Preserved format |
| **Summary Outputs** | Content comparison | Identical information |
| **Performance Logs** | Timing information | Consistent patterns |

## Testing Strategy Framework

### Testing Hierarchy

#### Level 1: Unit Tests (Individual Components)
```python
# Unit test categories and coverage requirements

class UnitTestFramework:
    """Framework for comprehensive unit testing."""

    test_categories = {
        "execute_dbt_command": {
            "basic_execution": ["no_vars", "with_vars", "full_refresh"],
            "error_handling": ["process_none", "non_zero_exit", "stdout_stderr"],
            "edge_cases": ["empty_vars", "special_chars", "long_commands"]
        },
        "clean_duckdb_data": {
            "data_cleaning": ["single_year", "multiple_years", "empty_list"],
            "error_scenarios": ["missing_tables", "connection_errors", "partial_failures"],
            "transaction_safety": ["rollback_on_error", "commit_on_success"]
        },
        "run_dbt_event_models_for_year": {
            "model_execution": ["sequence_order", "variable_passing", "full_refresh"],
            "hiring_debug": ["calculation_accuracy", "logging_format", "edge_cases"],
            "error_propagation": ["model_failures", "debug_errors", "recovery"]
        },
        "run_dbt_snapshot_for_year": {
            "snapshot_types": ["end_of_year", "baseline", "recovery"],
            "validation": ["prerequisites", "record_counts", "completion"],
            "error_handling": ["missing_data", "snapshot_failures", "validation_errors"]
        }
    }

    coverage_requirements = {
        "statement_coverage": 95,  # Percentage of statements executed
        "branch_coverage": 90,     # Percentage of branches taken
        "function_coverage": 100   # Percentage of functions called
    }
```

#### Level 2: Integration Tests (Component Interactions)
```python
class IntegrationTestFramework:
    """Framework for integration testing."""

    test_scenarios = {
        "single_year_simulation": {
            "normal_execution": ["2025", "2026", "2027", "2028", "2029"],
            "error_scenarios": ["invalid_config", "missing_data", "dbt_failures"],
            "performance": ["timing", "memory", "resource_usage"]
        },
        "multi_year_simulation": {
            "year_progressions": ["2025-2027", "2025-2029", "custom_ranges"],
            "dependency_validation": ["year_dependencies", "data_consistency"],
            "error_recovery": ["partial_failures", "continuation", "rollback"]
        },
        "component_interactions": {
            "data_flow": ["cleaning_to_simulation", "events_to_snapshots"],
            "configuration_passing": ["parameter_propagation", "type_safety"],
            "resource_sharing": ["database_connections", "dbt_resources"]
        }
    }
```

#### Level 3: End-to-End Tests (Complete Pipeline)
```python
class EndToEndTestFramework:
    """Framework for end-to-end validation."""

    validation_scenarios = {
        "behavioral_identity": {
            "identical_results": ["same_config_same_results", "reproducibility"],
            "mathematical_accuracy": ["growth_calculations", "event_counts"],
            "state_consistency": ["database_state", "intermediate_results"]
        },
        "operational_continuity": {
            "error_handling": ["error_propagation", "recovery_mechanisms"],
            "logging_preservation": ["format_consistency", "information_completeness"],
            "monitoring_compatibility": ["metrics_consistency", "alerting_triggers"]
        },
        "performance_validation": {
            "execution_time": ["regression_detection", "scalability"],
            "resource_usage": ["memory_efficiency", "connection_management"],
            "throughput": ["large_simulations", "concurrent_execution"]
        }
    }
```

## Validation Procedures

### Pre-Implementation Validation
1. **Baseline Establishment**
   - [ ] Capture current simulation results for standard test cases
   - [ ] Document current performance metrics
   - [ ] Record current logging output patterns
   - [ ] Establish current code quality metrics

2. **Test Environment Setup**
   - [ ] Create isolated test database
   - [ ] Set up performance monitoring tools
   - [ ] Configure logging capture mechanisms
   - [ ] Prepare test data sets

### Implementation Phase Validation
1. **Incremental Testing**
   - [ ] Test each modular component as implemented
   - [ ] Validate integration points progressively
   - [ ] Monitor performance impact incrementally
   - [ ] Compare partial results with baseline

2. **Continuous Validation**
   - [ ] Run automated test suite on each change
   - [ ] Monitor performance trends
   - [ ] Track code quality metrics
   - [ ] Validate behavioral consistency

### Post-Implementation Validation
1. **Comprehensive Comparison**
   - [ ] Run full simulation suite before/after
   - [ ] Compare all outputs mathematically
   - [ ] Validate performance within tolerance
   - [ ] Confirm operational behavior

2. **Acceptance Testing**
   - [ ] Stakeholder review of results
   - [ ] Performance acceptance validation
   - [ ] Documentation completeness check
   - [ ] Migration readiness assessment

## Behavioral Identity Validation

### Mathematical Validation Framework
```python
import numpy as np
from typing import List, Dict, Any

class BehaviorValidation:
    """Framework for validating behavioral identity."""

    @staticmethod
    def compare_year_results(original: YearResult, refactored: YearResult) -> Dict[str, bool]:
        """Compare YearResult objects for mathematical identity."""
        comparison = {
            "year_match": original.year == refactored.year,
            "success_match": original.success == refactored.success,
            "active_employees_match": original.active_employees == refactored.active_employees,
            "total_terminations_match": original.total_terminations == refactored.total_terminations,
            "experienced_terminations_match": original.experienced_terminations == refactored.experienced_terminations,
            "new_hire_terminations_match": original.new_hire_terminations == refactored.new_hire_terminations,
            "total_hires_match": original.total_hires == refactored.total_hires,
            "growth_rate_match": abs(original.growth_rate - refactored.growth_rate) < 1e-10,
            "validation_passed_match": original.validation_passed == refactored.validation_passed
        }

        return comparison

    @staticmethod
    def validate_database_state(year: int, original_db: str, refactored_db: str) -> Dict[str, bool]:
        """Compare database state between implementations."""
        validation = {}

        # Compare workforce snapshots
        original_workforce = get_workforce_snapshot(original_db, year)
        refactored_workforce = get_workforce_snapshot(refactored_db, year)
        validation["workforce_identical"] = original_workforce.equals(refactored_workforce)

        # Compare event counts
        original_events = get_event_counts(original_db, year)
        refactored_events = get_event_counts(refactored_db, year)
        validation["events_identical"] = original_events == refactored_events

        return validation

    @staticmethod
    def validate_hiring_calculations(year: int, config: Dict[str, Any]) -> Dict[str, bool]:
        """Validate hiring calculation mathematical accuracy."""
        # Extract configuration
        workforce_count = get_workforce_count(year)
        target_growth_rate = config["target_growth_rate"]
        total_termination_rate = config["total_termination_rate"]
        new_hire_termination_rate = config["new_hire_termination_rate"]

        # Calculate expected values
        import math
        expected_experienced_terms = math.ceil(workforce_count * total_termination_rate)
        expected_growth_amount = workforce_count * target_growth_rate
        expected_total_hires = math.ceil(
            (expected_experienced_terms + expected_growth_amount) /
            (1 - new_hire_termination_rate)
        )
        expected_new_hire_terms = round(expected_total_hires * new_hire_termination_rate)

        # Get actual values from simulation
        actual_results = get_simulation_results(year)

        return {
            "experienced_terminations_correct": (
                actual_results["experienced_terminations"] == expected_experienced_terms
            ),
            "total_hires_correct": (
                actual_results["total_hires"] == expected_total_hires
            ),
            "new_hire_terminations_correct": (
                actual_results["new_hire_terminations"] == expected_new_hire_terms
            ),
            "growth_rate_within_tolerance": (
                abs(actual_results["growth_rate"] - target_growth_rate) < 0.002
            )
        }
```

### Logging Validation Framework
```python
import re
from typing import List, Tuple

class LoggingValidation:
    """Framework for validating logging output consistency."""

    @staticmethod
    def compare_hiring_debug_logs(original_logs: List[str], refactored_logs: List[str]) -> bool:
        """Compare hiring debug logs character-by-character."""

        # Extract hiring debug sections
        original_debug = LoggingValidation._extract_hiring_debug(original_logs)
        refactored_debug = LoggingValidation._extract_hiring_debug(refactored_logs)

        if len(original_debug) != len(refactored_debug):
            return False

        for orig_line, refact_line in zip(original_debug, refactored_debug):
            if orig_line.strip() != refact_line.strip():
                return False

        return True

    @staticmethod
    def _extract_hiring_debug(logs: List[str]) -> List[str]:
        """Extract hiring calculation debug lines from logs."""
        debug_lines = []
        in_debug_section = False

        for line in logs:
            if "🔍 HIRING CALCULATION DEBUG:" in line:
                in_debug_section = True
                debug_lines.append(line)
            elif in_debug_section and line.strip().startswith("📊"):
                debug_lines.append(line)
            elif in_debug_section and line.strip().startswith("🎯"):
                debug_lines.append(line)
            elif in_debug_section and not line.strip().startswith(("📊", "🎯")):
                in_debug_section = False

        return debug_lines

    @staticmethod
    def validate_error_message_formats(original_errors: List[str], refactored_errors: List[str]) -> bool:
        """Validate that error message formats are preserved."""

        # Define expected error patterns
        patterns = [
            r"Failed to run .+ for .+\. Exit code: \d+",
            r"Simulation failed for year \d+:",
            r"Year \d+ validation failed:",
            r"No baseline workforce data found"
        ]

        for pattern in patterns:
            original_matches = [re.search(pattern, error) for error in original_errors]
            refactored_matches = [re.search(pattern, error) for error in refactored_errors]

            if len(original_matches) != len(refactored_matches):
                return False

        return True
```

## Acceptance Criteria Framework

### Epic-Level Acceptance Criteria
```python
class EpicAcceptanceCriteria:
    """Framework for validating epic-level acceptance criteria."""

    @staticmethod
    def validate_code_quality_improvements() -> Dict[str, bool]:
        """Validate code quality improvement targets."""
        return {
            "multi_year_loc_reduced": get_loc_count("run_multi_year_simulation") <= 100,
            "code_duplication_eliminated": get_duplication_percentage() < 5,
            "test_coverage_achieved": get_test_coverage() >= 95,
            "function_length_compliant": max(get_function_lengths()) <= 40,
            "cyclomatic_complexity_reduced": max(get_complexity_scores()) <= 10
        }

    @staticmethod
    def validate_behavioral_preservation() -> Dict[str, bool]:
        """Validate that all behavior is preserved."""
        return {
            "simulation_results_identical": compare_all_simulation_results(),
            "error_handling_preserved": validate_error_scenarios(),
            "logging_output_preserved": compare_all_logging_output(),
            "performance_within_tolerance": validate_performance_metrics(),
            "database_state_identical": compare_database_states()
        }

    @staticmethod
    def validate_testing_completeness() -> Dict[str, bool]:
        """Validate testing completeness requirements."""
        return {
            "unit_tests_comprehensive": validate_unit_test_coverage(),
            "integration_tests_complete": validate_integration_scenarios(),
            "end_to_end_tests_passing": validate_e2e_test_results(),
            "performance_tests_within_bounds": validate_performance_tests(),
            "documentation_complete": validate_documentation_completeness()
        }
```

### Story-Level Acceptance Criteria
Each user story includes specific, measurable acceptance criteria:

#### S013-01: dbt Command Utility
- [ ] execute_dbt_command function implemented with all parameter combinations
- [ ] 15+ repetitive dbt command blocks replaced
- [ ] Unit tests cover all scenarios (>95% coverage)
- [ ] Integration test shows identical behavior

#### S013-02: Data Cleaning Separation
- [ ] clean_duckdb_data operation extracts embedded logic
- [ ] Multi-year simulation uses new operation
- [ ] Transaction safety implemented and tested
- [ ] Performance impact neutral or positive

#### S013-03: Event Processing Modularization
- [ ] run_dbt_event_models_for_year operation implemented
- [ ] Hiring debug logic preserved character-for-character
- [ ] Code duplication eliminated between single/multi-year
- [ ] Mathematical accuracy validated

#### S013-04: Snapshot Management
- [ ] run_dbt_snapshot_for_year operation implemented
- [ ] All snapshot types supported (baseline, end-of-year, recovery)
- [ ] Validation and error handling comprehensive
- [ ] Integration points updated

#### S013-05: Single-Year Refactoring
- [ ] run_year_simulation refactored to use new components
- [ ] 40%+ code reduction achieved
- [ ] All repetitive patterns eliminated
- [ ] Behavior identical to original

#### S013-06: Multi-Year Orchestration
- [ ] run_multi_year_simulation transformed to pure orchestrator
- [ ] 85%+ code reduction achieved (275+ lines eliminated)
- [ ] All duplicated logic removed
- [ ] End-to-end behavior identical

#### S013-07: Validation & Testing
- [ ] Comprehensive test suite implemented (>95% coverage)
- [ ] Behavioral identity validated mathematically
- [ ] Performance regression within tolerance
- [ ] All acceptance criteria automated

#### S013-08: Documentation & Cleanup
- [ ] Architecture documentation updated
- [ ] Developer guide created
- [ ] Migration guide completed
- [ ] Code cleanup finished

## Continuous Monitoring Framework

### Automated Validation Pipeline
```python
class ContinuousValidation:
    """Framework for ongoing validation during and after implementation."""

    def run_validation_suite(self) -> Dict[str, Any]:
        """Run complete validation suite."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "code_quality": self.validate_code_quality(),
            "behavioral_identity": self.validate_behavior(),
            "performance": self.validate_performance(),
            "testing": self.validate_testing(),
            "documentation": self.validate_documentation()
        }

        # Generate summary report
        results["summary"] = self.generate_summary(results)

        return results

    def generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of validation results."""
        total_checks = sum(len(section) for section in results.values() if isinstance(section, dict))
        passed_checks = sum(
            sum(1 for v in section.values() if v is True)
            for section in results.values()
            if isinstance(section, dict)
        )

        return {
            "overall_success_rate": passed_checks / total_checks,
            "epic_ready_for_completion": passed_checks / total_checks >= 0.95,
            "recommendations": self.generate_recommendations(results)
        }
```

---

**Implementation Notes**: This validation framework provides comprehensive coverage for ensuring the refactoring achieves all Epic goals while maintaining operational integrity. Use this framework throughout the implementation to ensure continuous validation and early detection of any deviations from requirements.
