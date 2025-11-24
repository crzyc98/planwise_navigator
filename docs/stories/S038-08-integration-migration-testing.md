# Story S038-08: Integration & Migration Testing

**Epic**: E038 - PlanAlign Orchestrator Refactoring & Modularization
**Story Points**: 5
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: S038-01 through S038-07 (All previous stories)
**Assignee**: Development Team

---

## 🎯 **Goal**

Complete the refactoring by ensuring seamless integration between all modules, comprehensive testing of the complete system, and smooth migration from the monolithic implementation.

## 📋 **User Story**

As a **product owner** of the Fidelity PlanAlign Engine system,
I want **confidence that the refactored orchestrator works correctly and provides all existing functionality**
So that **we can deploy the new modular system without disrupting current workflows**.

## 🛠 **Technical Tasks**

### **Task 1: Complete System Integration**
- Integrate all orchestrator modules into cohesive system
- Create factory/builder pattern for orchestrator initialization
- Implement dependency injection for clean module separation
- Add comprehensive integration testing between all modules

### **Task 2: Migration & Backwards Compatibility**
- Create migration utilities to preserve existing data and configurations
- Implement compatibility layer for existing scripts and workflows
- Add side-by-side validation comparing old vs new implementations
- Create rollback procedures for safe deployment

### **Task 3: Performance & Quality Validation**
- Execute comprehensive performance benchmarking
- Validate all existing functionality is preserved
- Create end-to-end testing with real simulation scenarios
- Document performance improvements and regression analysis

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ All existing functionality preserved with no regressions
- ✅ New modular system produces identical results to monolithic version
- ✅ Backwards compatibility maintained for existing configurations
- ✅ Migration utilities successfully preserve all data and state

### **Performance Requirements**
- ✅ Performance maintained or improved vs existing implementation
- ✅ Memory usage optimized compared to monolithic version
- ✅ Startup time improved or maintained
- ✅ Multi-year simulation performance benchmarked and documented

### **Quality Requirements**
- ✅ 95%+ end-to-end test coverage for complete workflows
- ✅ All integration points tested with real data scenarios
- ✅ Error handling validated across module boundaries
- ✅ Comprehensive regression testing completed

## 🧪 **Testing Strategy**

### **Integration Tests**
```python
# test_full_integration.py
def test_complete_multi_year_workflow_end_to_end()
def test_checkpoint_restart_full_simulation()
def test_error_recovery_across_module_boundaries()
def test_registry_state_consistency_multi_year()
def test_validation_integration_with_all_modules()
def test_reporting_integration_complete_workflow()
```

### **Performance Tests**
```python
# test_performance_benchmarks.py
def test_single_year_simulation_performance()
def test_multi_year_simulation_memory_usage()
def test_large_workforce_scaling_performance()
def test_parallel_execution_performance_gains()
def test_database_operation_optimization()
```

### **Migration Tests**
```python
# test_migration_compatibility.py
def test_existing_config_file_compatibility()
def test_database_state_migration()
def test_checkpoint_format_migration()
def test_backwards_compatibility_layer()
def test_side_by_side_result_validation()
```

## 📊 **Definition of Done**

- [x] All modules integrated into orchestrator via factory/builder
- [x] Migration utilities scaffolded (checkpoints, config compatibility)
- [ ] Backwards compatibility verified with existing workflows
- [ ] Performance benchmarks show maintained or improved metrics
- [ ] End-to-end tests achieve 95%+ coverage
- [ ] Side-by-side validation confirms identical results
- [x] Documentation updated with builder and migration usage
- [ ] Rollback procedures documented and tested

### 🔧 Implementation Progress

- Added `planalign_orchestrator/factory.py` with:
  - `OrchestratorBuilder` (config, db path, dbt threads/executable, rules)
  - `create_orchestrator(config_path, threads, db_path, dbt_executable)` convenience
- Added `planalign_orchestrator/migration.py` with:
  - `MigrationManager` (config compatibility probe, checkpoint directory migration, listing)
  - `MigrationResult` dataclass
- Added tests in `tests/test_factory_migration.py` for builder creation and migration ops.

See also: `docs/MIGRATION_GUIDE_S038.md` for step-by-step migration from the legacy runner to the new orchestrator.

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Core infrastructure must be complete
- **S038-02**: dbt runner must be fully implemented
- **S038-03**: Registry management must be working
- **S038-04**: Validation framework must be integrated
- **S038-05**: Reporting system must be functional
- **S038-06**: Pipeline orchestration must be complete
- **S038-07**: CLI interface must be implemented

### **Downstream Dependencies**
- None - this completes the epic

## 📝 **Implementation Notes**

### **Orchestrator Factory Pattern**
```python
from typing import Optional, Dict, Any
from pathlib import Path

class OrchestratorBuilder:
    """Builder pattern for creating fully configured orchestrator instances."""

    def __init__(self):
        self.config: Optional[SimulationConfig] = None
        self.db_manager: Optional[DatabaseConnectionManager] = None
        self.custom_validators: List[ValidationRule] = []
        self.custom_reporters: List[ReportTemplate] = []

    def with_config(self, config_path: Path) -> 'OrchestratorBuilder':
        """Load configuration from file."""
        config_loader = ConfigurationLoader()
        self.config = config_loader.load_configuration(config_path)
        return self

    def with_database(self, db_path: Optional[Path] = None) -> 'OrchestratorBuilder':
        """Configure database connection."""
        self.db_manager = DatabaseConnectionManager(db_path or Path("simulation.duckdb"))
        return self

    def with_custom_validator(self, validator: ValidationRule) -> 'OrchestratorBuilder':
        """Add custom validation rule."""
        self.custom_validators.append(validator)
        return self

    def build(self) -> PipelineOrchestrator:
        """Build complete orchestrator instance."""
        if not self.config:
            raise ValueError("Configuration must be provided")

        if not self.db_manager:
            self.db_manager = DatabaseConnectionManager()

        # Create all components with dependency injection
        dbt_runner = DbtRunner(
            working_dir=Path("dbt"),
            threads=self.config.dbt.threads
        )

        registry_manager = RegistryManager(self.db_manager)

        validator = setup_default_validators(self.config.validation)
        for custom_validator in self.custom_validators:
            validator.register_rule(custom_validator)

        reporter = MultiYearReporter(self.db_manager)
        for custom_template in self.custom_reporters:
            reporter.register_template(custom_template)

        return PipelineOrchestrator(
            config=self.config,
            db_manager=self.db_manager,
            dbt_runner=dbt_runner,
            registry_manager=registry_manager,
            validator=validator,
            reporter=reporter
        )

# Convenience factory functions
def create_orchestrator(config_path: Path) -> PipelineOrchestrator:
    """Create standard orchestrator with default configuration."""
    return (OrchestratorBuilder()
            .with_config(config_path)
            .with_database()
            .build())

def create_custom_orchestrator(
    config_path: Path,
    db_path: Path,
    custom_validators: List[ValidationRule] = None,
    custom_reporters: List[ReportTemplate] = None
) -> PipelineOrchestrator:
    """Create orchestrator with custom components."""
    builder = (OrchestratorBuilder()
               .with_config(config_path)
               .with_database(db_path))

    for validator in (custom_validators or []):
        builder.with_custom_validator(validator)

    return builder.build()
```

## 📘 **Usage Examples**

```python
from planalign_orchestrator.factory import create_orchestrator

orchestrator = create_orchestrator(
    "config/simulation_config.yaml",
    threads=8,
    db_path="simulation.duckdb",
)
summary = orchestrator.execute_multi_year_simulation()

from planalign_orchestrator.migration import MigrationManager
mm = MigrationManager()
compat = mm.validate_config_compatibility("config/simulation_config.yaml")
print("Identifiers present:", compat["has_identifiers"])
mm.migrate_checkpoints()  # ensure checkpoint dir is ready
print(mm.list_checkpoints())
```

### **Migration and Compatibility Layer**
```python
class MigrationManager:
    """Manages migration from monolithic to modular orchestrator."""

    def __init__(self, old_db_path: Path, new_db_path: Path):
        self.old_db_path = old_db_path
        self.new_db_path = new_db_path

    def migrate_database_schema(self) -> MigrationResult:
        """Migrate database schema to new format if needed."""

        migration_steps = [
            self._add_scenario_id_columns,
            self._add_plan_design_id_columns,
            self._create_checkpoint_tables,
            self._create_registry_metadata_tables
        ]

        results = []
        for step in migration_steps:
            try:
                result = step()
                results.append(result)
            except Exception as e:
                return MigrationResult(
                    success=False,
                    error=f"Migration step failed: {e}",
                    completed_steps=results
                )

        return MigrationResult(success=True, completed_steps=results)

    def validate_migration(self, test_years: List[int]) -> ValidationResult:
        """Validate migration by comparing results between implementations."""

        # Run same simulation with both implementations
        old_orchestrator = self._create_legacy_orchestrator()
        new_orchestrator = self._create_modular_orchestrator()

        validation_results = []

        for year in test_years:
            old_result = old_orchestrator.run_single_year(year)
            new_result = new_orchestrator.execute_year_workflow(year)

            comparison = self._compare_simulation_results(old_result, new_result)
            validation_results.append(comparison)

        return ValidationResult(
            is_valid=all(r.matches for r in validation_results),
            details=validation_results
        )

class CompatibilityLayer:
    """Provides backwards compatibility for existing scripts."""

    def __init__(self, orchestrator: PipelineOrchestrator):
        self.orchestrator = orchestrator

    def run_multi_year_simulation(
        self,
        start_year: int,
        end_year: int,
        config_path: Optional[str] = None,
        **legacy_kwargs
    ) -> Dict[str, Any]:
        """Legacy interface that maps to new orchestrator methods."""

        # Convert legacy arguments to new format
        if config_path:
            self.orchestrator.config = load_legacy_config(config_path)

        # Map legacy kwargs to new configuration
        if 'target_growth_rate' in legacy_kwargs:
            self.orchestrator.config.simulation.target_growth_rate = legacy_kwargs['target_growth_rate']

        # Execute with new orchestrator
        result = self.orchestrator.execute_multi_year_simulation(start_year, end_year)

        # Convert result to legacy format
        return self._convert_to_legacy_format(result)

    def _convert_to_legacy_format(self, result: MultiYearSummary) -> Dict[str, Any]:
        """Convert new result format to legacy dictionary format."""
        return {
            'years_completed': list(range(result.start_year, result.end_year + 1)),
            'total_workforce_growth': result.growth_analysis['total_growth_pct'],
            'final_workforce_size': result.workforce_progression[-1].total_employees,
            'participation_rate': result.participation_trends[-1],
            'execution_time': (result.generated_at - result.start_time).total_seconds()
        }
```

### **End-to-End Testing Framework**
```python
class EndToEndTestSuite:
    """Comprehensive end-to-end testing for complete orchestrator."""

    def __init__(self, test_data_path: Path, expected_results_path: Path):
        self.test_data_path = test_data_path
        self.expected_results_path = expected_results_path

    def run_comprehensive_tests(self) -> TestSuiteResult:
        """Execute complete test suite with various scenarios."""

        test_scenarios = [
            self._test_basic_single_year_simulation,
            self._test_multi_year_progression,
            self._test_checkpoint_restart_functionality,
            self._test_error_recovery_scenarios,
            self._test_large_workforce_performance,
            self._test_configuration_validation,
            self._test_registry_consistency,
            self._test_data_quality_validation
        ]

        results = []
        for test_scenario in test_scenarios:
            try:
                result = test_scenario()
                results.append(result)
            except Exception as e:
                results.append(TestResult(
                    name=test_scenario.__name__,
                    passed=False,
                    error=str(e)
                ))

        return TestSuiteResult(
            tests_run=len(results),
            tests_passed=sum(1 for r in results if r.passed),
            results=results
        )

    def _test_multi_year_progression(self) -> TestResult:
        """Test complete multi-year workflow with data validation."""

        orchestrator = create_orchestrator(self.test_data_path / "test_config.yaml")

        # Execute 3-year simulation
        result = orchestrator.execute_multi_year_simulation(2025, 2027)

        # Validate key metrics
        assertions = [
            result.start_year == 2025,
            result.end_year == 2027,
            len(result.workforce_progression) == 3,
            result.growth_analysis['compound_annual_growth_rate'] > 0,
            all(wp.total_employees > 0 for wp in result.workforce_progression)
        ]

        return TestResult(
            name="multi_year_progression",
            passed=all(assertions),
            details={
                'simulation_years': len(result.workforce_progression),
                'final_workforce': result.workforce_progression[-1].total_employees,
                'cagr': result.growth_analysis['compound_annual_growth_rate']
            }
        )
```

### **Performance Benchmarking**
```python
class PerformanceBenchmark:
    """Performance benchmarking for orchestrator components."""

    def run_performance_suite(self) -> BenchmarkResults:
        """Execute comprehensive performance benchmarks."""

        benchmarks = {
            'single_year_execution': self._benchmark_single_year,
            'multi_year_execution': self._benchmark_multi_year,
            'registry_operations': self._benchmark_registry_performance,
            'validation_performance': self._benchmark_validation,
            'database_operations': self._benchmark_database_performance
        }

        results = {}
        for name, benchmark_func in benchmarks.items():
            print(f"Running benchmark: {name}")
            results[name] = benchmark_func()

        return BenchmarkResults(results)

    def _benchmark_single_year(self) -> PerformanceMetrics:
        """Benchmark single year simulation performance."""

        orchestrator = create_orchestrator(Path("test_config.yaml"))

        start_time = time.time()
        initial_memory = psutil.Process().memory_info().rss

        # Execute single year
        orchestrator.execute_year_workflow(2025)

        execution_time = time.time() - start_time
        peak_memory = psutil.Process().memory_info().rss
        memory_delta = peak_memory - initial_memory

        return PerformanceMetrics(
            execution_time_seconds=execution_time,
            memory_usage_mb=memory_delta / (1024 * 1024),
            database_operations=orchestrator.get_db_operation_count()
        )

    def compare_with_baseline(
        self,
        current_results: BenchmarkResults,
        baseline_results: BenchmarkResults
    ) -> PerformanceComparison:
        """Compare current performance with baseline."""

        comparisons = {}
        for metric_name in current_results.results:
            current = current_results.results[metric_name]
            baseline = baseline_results.results[metric_name]

            time_improvement = (baseline.execution_time_seconds - current.execution_time_seconds) / baseline.execution_time_seconds
            memory_improvement = (baseline.memory_usage_mb - current.memory_usage_mb) / baseline.memory_usage_mb

            comparisons[metric_name] = {
                'time_improvement_pct': time_improvement * 100,
                'memory_improvement_pct': memory_improvement * 100,
                'performance_regression': time_improvement < -0.05,  # 5% regression threshold
                'memory_regression': memory_improvement < -0.10     # 10% memory regression threshold
            }

        return PerformanceComparison(comparisons)
```

---

**This story completes the epic by ensuring all modules work together seamlessly, migration is smooth, and the refactored system meets all performance and functionality requirements.**
