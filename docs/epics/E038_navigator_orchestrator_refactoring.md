# Epic E038: Navigator Orchestrator Refactoring & Modularization

**Status**: 🟡 Planned
**Priority**: High
**Estimated Effort**: 39 Story Points (4 weeks)
**Dependencies**: None
**Epic Owner**: Development Team

---

## 🎯 **Epic Overview**

### **Problem Statement**
The current `run_multi_year.py` orchestrator has grown to 1,012 lines of monolithic code that handles configuration, database management, dbt execution, registry management, pipeline orchestration, reporting, and CLI operations. This creates several critical issues:

- **Maintainability**: Single file with 8+ distinct responsibilities
- **Testability**: Tightly coupled functions difficult to unit test
- **Extensibility**: Adding features requires modifying the monolithic script
- **Code Quality**: Complex interdependencies and repeated patterns
- **Developer Experience**: New team members struggle with the large codebase

### **Solution Approach**
Refactor `run_multi_year.py` into a clean, modular `navigator_orchestrator` package with focused modules following single-responsibility principles. Transform the monolithic architecture into a well-structured, testable, and maintainable orchestration system.

### **Business Value**
- **50% reduction in maintenance effort** through modular design
- **Faster feature development** with clear separation of concerns
- **Improved reliability** through comprehensive testing coverage
- **Better developer onboarding** with focused, understandable modules
- **Enterprise-grade architecture** supporting future scalability

---

## 🔭 **Scope and Non‑Goals**

### **In Scope**
- Modularization of orchestration concerns (config, dbt, registries, pipeline, reporting, validation, CLI).
- Backwards‑compatible public API and CLI for multi‑year runs.
- Event‑sourced alignment: preserve immutable event lineage and reproducibility.

### **Non‑Goals**
- Changing business logic of dbt models or their contracts.
- Altering database schemas or event table immutability.
- Introducing cross‑cutting refactors beyond the orchestrator boundary.

### **Assumptions/Constraints**
- Execution targets DuckDB at `simulation.duckdb`; avoid IDE locks during runs.
- dbt commands run only from `/dbt`; use `{{ ref() }}` and avoid `SELECT *`.
- Network installs are restricted; any new Python deps must be optional or guarded.

## 📋 **Technical Architecture**

### **Proposed Package Structure**
```
navigator_orchestrator/
├── __init__.py          # Public API exports (run_multi_year, run_year)
├── config.py           # YAML loading, validation, dbt variable mapping
├── dbt_runner.py       # dbt command orchestration with error handling
├── registries.py       # enrollment_registry & deferral_escalation_registry
├── pipeline.py         # Year flow orchestration and dependency management
├── reports.py          # Year-end audit reports and multi-year summaries
├── validation.py       # Data quality checks and business rule validation
├── utils.py            # ExecutionMutex, database connections, timing utilities
└── cli.py              # Thin CLI entrypoint with argument parsing
```

### **Module Responsibilities**

| Module | Lines | Responsibilities | Dependencies |
|--------|-------|------------------|--------------|
| `config.py` | ~150 | YAML loading, Pydantic validation, dbt var mapping | `yaml`, `pydantic`, `pathlib` |
| `dbt_runner.py` | ~120 | dbt subprocess execution, command templating, error handling | `subprocess`, `json` |
| `registries.py` | ~200 | Registry creation/updates, SQL generation, state management | Database utilities |
| `pipeline.py` | ~180 | Year orchestration, model sequencing, error recovery | All modules |
| `reports.py` | ~220 | Audit queries, formatted reporting, multi-year analytics | Database utilities |
| `validation.py` | ~100 | Data quality rules, threshold validation, anomaly detection | Database utilities |
| `utils.py` | ~80 | Database connections, mutex, timing, logging utilities | `duckdb`, threading |
| `cli.py` | ~60 | Argument parsing, progress display, environment validation | `click`, `rich` |

### **Architecture Benefits**
- **Focused Responsibilities**: Each module has a single, clear purpose
- **Interface-Driven Design**: Clean APIs between modules
- **Dependency Injection**: Modules receive dependencies, not global state
- **Error Isolation**: Failures contained within module boundaries
- **Testing Strategy**: Each module independently unit testable

### **Public API Surface**
```python
# navigator_orchestrator/__init__.py
from pathlib import Path
from typing import Optional, Sequence

class MultiYearReport: ...  # Structured summary object for auditing

def run_year(config_path: Path, year: int, selectors: Optional[Sequence[str]] = None) -> dict: ...

def run_multi_year(
    config_path: Path,
    start_year: int,
    end_year: int,
    selectors: Optional[Sequence[str]] = None,
) -> MultiYearReport: ...
```

### **Configuration Schema (excerpt)**
```yaml
scenario_id: "S001"
plan_design_id: "P2024"
years:
  start: 2021
  end: 2025
dbt:
  target: dev
  threads: 4
  selectors: ["state:modified+"]
validation:
  row_drift_tolerance: 0.005  # 0.5%
  require_pk_uniqueness: true
locks:
  enable_mutex: true
duckdb_path: "simulation.duckdb"
```

### **Event‑Sourcing Alignment**
- Preserve immutable `fct_yearly_events`; no in‑place mutation.
- Maintain unified `SimulationEvent` semantics, carrying `scenario_id` and `plan_design_id` context through every stage.
- Orchestrator must not break event→state lineage used by marts/accumulators; all state must be reproducible from events.
- Reporting modules consume event streams and snapshots without side effects.

---

## ⚡ **Story Breakdown**

### **S038-01: Core Infrastructure Setup** *(5 points)*
**Goal**: Create foundational modules for configuration and utilities
- Create `utils.py` with `ExecutionMutex` and database connection management
- Create `config.py` with Pydantic models and YAML validation
- Migrate core utilities from existing `shared_utils.py` and `run_multi_year.py`
- Add comprehensive unit tests for both modules

**Acceptance Criteria**:
- ✅ `utils.py` provides database connection management and mutex handling
- ✅ `config.py` loads and validates YAML with type-safe Pydantic models
- ✅ 95%+ test coverage for both modules
- ✅ All existing functionality preserved
 - ✅ Configuration includes `scenario_id` and `plan_design_id` and validates presence

### **S038-02: dbt Command Orchestration** *(3 points)*
**Goal**: Extract and enhance dbt command execution logic
- Create `dbt_runner.py` with improved command orchestration
- Add streaming output support for long-running dbt operations
- Implement retry logic and enhanced error handling
- Migrate `run_dbt_command()` functionality with improvements

**Acceptance Criteria**:
- ✅ `DbtRunner` class provides clean interface for dbt operations
- ✅ Support for streaming output and progress reporting
- ✅ Retry logic for transient failures
- ✅ Comprehensive error classification and reporting

### **S038-03: Registry Management System** *(8 points)*
**Goal**: Refactor registry management into dedicated module
- Create `registries.py` with `EnrollmentRegistry` and `DeferralRegistry` classes
- Abstract registry operations with common interface patterns
- Add registry integrity validation and consistency checks
- Migrate all registry functions with enhanced error handling

**Acceptance Criteria**:
- ✅ Registry classes provide type-safe interfaces
- ✅ Automated integrity validation and consistency checking
- ✅ SQL generation abstracted behind clean APIs
- ✅ Cross-year state management properly handled

### **S038-04: Data Quality & Validation Framework** *(3 points)*
**Goal**: Create comprehensive validation and data quality module
- Create `validation.py` with configurable data quality rules
- Extract validation logic from audit functions
- Add business rule validation and anomaly detection
- Implement threshold-based validation with configurable limits

**Acceptance Criteria**:
- ✅ Configurable data quality rules and thresholds
- ✅ Business rule validation with clear error messages
- ✅ Anomaly detection for unusual data patterns
- ✅ Integration with pipeline for automated validation

### **S038-05: Audit & Reporting System** *(5 points)*
**Goal**: Enhance reporting capabilities with modular design
- Create `reports.py` with `YearAuditor` and `MultiYearReporter` classes
- Add configurable report templates and export capabilities
- Enhance multi-year analytics with statistical insights
- Support multiple output formats (console, JSON, CSV)

**Acceptance Criteria**:
- ✅ Clean separation between year-specific and multi-year reporting
- ✅ Export capabilities for various formats
- ✅ Enhanced analytics with statistical insights
- ✅ Configurable report templates

### **S038-06: Pipeline Orchestration Engine** *(8 points)*
**Goal**: Create robust pipeline orchestration with dependency management
- Create `pipeline.py` with `YearPipeline` and `DatabaseManager` classes
- Implement dependency resolution and execution ordering
- Add rollback capabilities and checkpointing for failed runs
- Enhance error recovery with detailed failure analysis

**Acceptance Criteria**:
- ✅ Automatic dependency resolution for dbt models
- ✅ Rollback capabilities for failed year simulations
- ✅ Checkpointing support for resuming interrupted runs
- ✅ Detailed error analysis and recovery suggestions
 - ✅ Event lineage preserved; no orphaned or duplicated events

### **S038-07: Enhanced CLI Interface** *(2 points)*
**Goal**: Create modern CLI with rich progress reporting
- Create `cli.py` with `click` argument parsing
- Add progress bars and status reporting with `rich` library
- Implement environment validation and setup checks
- Support configuration overrides via command-line flags

**Acceptance Criteria**:
- ✅ Modern CLI with comprehensive argument parsing
- ✅ Rich progress reporting and status updates
- ✅ Environment validation with helpful error messages
- ✅ Command-line configuration override support

### **S038-08: Integration & Migration** *(5 points)*
**Goal**: Complete integration and ensure backwards compatibility
- Create `__init__.py` with public API exports
- Update existing `run_multi_year.py` to use new modules progressively
- Add comprehensive integration tests
- Create migration guide and documentation

**Acceptance Criteria**:
- ✅ Public API maintains backwards compatibility
- ✅ Existing `run_multi_year.py` acts as thin wrapper
- ✅ Full integration test suite with multi-year scenarios
- ✅ Complete documentation and migration guide

---

## 📊 **Implementation Plan**

### **Phase 1: Foundation (Week 1)**
- **Stories**: S038-01, S038-02
- **Focus**: Core infrastructure and dbt operations
- **Deliverables**: `utils.py`, `config.py`, `dbt_runner.py`
- **Milestone**: Basic orchestration modules functional

### **Phase 2: Data Management (Week 2)**
- **Stories**: S038-03, S038-04
- **Focus**: Registry management and data validation
- **Deliverables**: `registries.py`, `validation.py`
- **Milestone**: State management and quality assurance modules ready

### **Phase 3: Workflow Integration (Week 3)**
- **Stories**: S038-05, S038-06
- **Focus**: Reporting and pipeline orchestration
- **Deliverables**: `reports.py`, `pipeline.py`
- **Milestone**: Complete workflow orchestration system

### **Phase 4: Interface & Deployment (Week 4)**
- **Stories**: S038-07, S038-08
- **Focus**: CLI enhancement and integration
- **Deliverables**: `cli.py`, public API, migration tools
- **Milestone**: Production-ready modular orchestrator

---

## ✅ **Success Criteria**

### **Quantitative Metrics**
- **Code Footprint**: Maintain total LOC within ±10% of 1,012 while reducing per‑function complexity
- **Cyclomatic Complexity**: Reduce average complexity from 15+ to <5 per function
- **Test Coverage**: Achieve 95%+ code coverage across all modules
- **Performance**: Maintain or improve execution time (target: <2% regression)
- **Documentation**: 100% API documentation coverage with examples

### **Qualitative Outcomes**
- **Maintainability**: New features require changes to single modules
- **Testability**: Each module independently unit testable
- **Developer Experience**: New team members productive within 1 day
- **Code Quality**: Pass all linting, type checking, and security scans
- **Reliability**: Zero regression in existing simulation functionality
 - **Event Sourcing**: Event→state lineage remains intact and auditable

### **Business Impact**
- **Development Velocity**: 30% faster feature development cycles
- **Bug Resolution**: 50% reduction in time to diagnose and fix issues
- **Onboarding**: New developers productive 60% faster
- **Technical Debt**: Elimination of architectural technical debt in orchestration layer

---

## 🚨 **Risk Assessment**

### **Technical Risks**

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|-------------------|
| **Regression in existing functionality** | Medium | High | Comprehensive integration tests, gradual migration |
| **Performance degradation** | Low | Medium | Benchmark existing performance, profile new implementation |
| **Complex interdependencies** | Medium | Medium | Clear interface design, dependency injection patterns |
| **Migration complexity** | Low | Medium | Maintain backwards compatibility, phased rollout |
| **Event lineage breakage** | Low | High | Enforce immutable events, lineage tests, snapshot diffing |

### **Business Risks**

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|-------------------|
| **Extended development timeline** | Medium | Medium | Aggressive testing, early feedback loops |
| **Team capacity constraints** | Low | Medium | Clear story breakdown, parallel development |
| **Stakeholder resistance** | Low | Low | Demonstrate clear benefits, maintain existing interfaces |

### **Risk Mitigation Plan**
- **Comprehensive Testing**: Unit, integration, and regression test suites
- **Backwards Compatibility**: Existing scripts continue working during transition
- **Gradual Migration**: Progressive adoption with fallback mechanisms
- **Performance Monitoring**: Continuous benchmarking throughout development
- **Stakeholder Communication**: Regular demos and progress updates
 - **Lineage Verification**: Add tests that reconstruct state from events and compare snapshots

---

## 🔗 **Dependencies**

### **External Dependencies**
- **Python Libraries**: `pydantic`, `click`, `rich` (optional; CLI/UX enhancements only)
- **Existing Systems**: Maintain compatibility with current dbt models and database schema
- **Development Tools**: pytest, black, mypy for quality assurance

### **Internal Dependencies**
- **dbt Models**: No changes required to existing dbt project structure
- **Configuration**: Maintain compatibility with existing `simulation_config.yaml` format
- **Database Schema**: No changes to existing table structures or relationships
 - **Event Tables**: `fct_yearly_events` remains immutable; `fct_workforce_snapshot` is point‑in‑time

### **Timeline Dependencies**
- **No blocking dependencies**: All work can proceed in parallel
- **Integration dependencies**: Stories S038-06 and S038-08 depend on completion of prior stories
- **Testing dependencies**: Integration tests require completion of all module implementations

---

## 🧪 **Testing Strategy**

### **Unit Testing**
```
tests/unit/
├── test_config.py          # Configuration loading and validation
├── test_dbt_runner.py      # dbt command execution and error handling
├── test_registries.py      # Registry creation, updates, integrity checks
├── test_pipeline.py        # Year execution flow and error recovery
├── test_reports.py         # Report generation, formatting, export
├── test_validation.py      # Data quality rules and business validation
├── test_utils.py           # Database connections, mutex, timing utilities
└── test_cli.py             # Command-line interface and argument parsing
```

### **Integration Testing**
```
tests/integration/
├── test_single_year_flow.py      # Complete year execution end-to-end
├── test_multi_year_flow.py       # Multi-year coordination and state management
├── test_error_recovery.py        # Failure scenarios and recovery mechanisms
├── test_backwards_compatibility.py # Existing interface compatibility
└── test_performance_regression.py  # Performance benchmarking and validation
```

### **Test Data & Fixtures**
- **Synthetic Configuration**: Test configurations for various scenarios
- **Mock dbt Responses**: Simulated dbt command outputs for testing
- **Database Fixtures**: Sample workforce data for validation testing
- **Performance Baselines**: Current execution time benchmarks

### **Testing Tools**
- **pytest**: Primary testing framework with fixtures and parameterization
- **pytest-mock**: Mocking external dependencies and system interactions
- **pytest-benchmark**: Performance testing and regression detection
- **pytest-cov**: Code coverage reporting and enforcement
- **factory_boy**: Test data generation and fixtures

### **Data Quality Gates (dbt alignment)**
- Row count drift from raw→staged ≤ 0.5%.
- Primary‑key uniqueness on every model.
- Distribution drift checks maintain expected p‑values (see CLAUDE.md).
- Enforce contracts; avoid `SELECT *`; use CTEs and `{{ ref() }}`.

### **dbt Execution Policy**
- Run dbt from `/dbt` only; use `--select` to scope runs where possible.
- Support deferral/partial parsing when configured; surface clear errors.
- Stream logs for long‑running tasks; persist structured logs for audit.

---

## 🔄 **Migration Path**

### **Backwards Compatibility Strategy**
1. **Phase 1**: New modules coexist with existing `run_multi_year.py`
2. **Phase 2**: Existing script progressively delegates to new modules
3. **Phase 3**: Existing script becomes thin wrapper around new package
4. **Phase 4**: Full transition with deprecation warnings for old patterns

### **Migration Phases**

#### **Phase 1: Parallel Development** *(Weeks 1-2)*
- New modules developed alongside existing code
- No changes to existing `run_multi_year.py` interface
- Integration testing validates equivalent functionality

#### **Phase 2: Progressive Integration** *(Week 3)*
- Update `run_multi_year.py` to use new modules internally
- Maintain exact same CLI interface and behavior
- Add feature flags to switch between old and new implementations

#### **Phase 3: Interface Transition** *(Week 4)*
- Introduce new `navigator_orchestrator` CLI interface
- Add deprecation warnings to old patterns
- Provide migration guide for users

#### **Phase 4: Full Adoption** *(Future)*
- Remove old implementation after user transition period
- Archive legacy code with clear migration path documentation
- Monitor usage patterns and provide support for remaining users

### **Rollback Strategy**
- **Feature flags** allow instant rollback to previous implementation
- **Configuration compatibility** ensures no data migration required
- **Database schema unchanged** prevents any data loss scenarios
- **Performance monitoring** enables early detection of regressions
 - **Operational toggle** to disable new CLI features without affecting core runs

---

## 📚 **Documentation Plan**

### **Developer Documentation**
- **API Reference**: Comprehensive docstrings with examples for all public interfaces
- **Architecture Guide**: Module interactions, dependency flow, and design decisions
- **Contributing Guide**: Development setup, testing procedures, code standards
- **Migration Guide**: Step-by-step transition from existing `run_multi_year.py`

### **User Documentation**
- **CLI Reference**: Updated command-line interface documentation
- **Configuration Guide**: Enhanced configuration options and validation
- **Troubleshooting**: Common issues and resolution procedures
- **Examples**: Real-world usage scenarios and best practices

### **Technical Specifications**
- **Module Interfaces**: Formal API specifications for each module
- **Error Handling**: Exception hierarchy and error recovery procedures
- **Performance Characteristics**: Benchmarks and scaling considerations
- **Security Considerations**: Data handling and access control patterns
 - **Provenance/Logging**: Structured, timestamped logs (JSON) with `scenario_id` and `plan_design_id` on every record

---

## 🎉 **Expected Outcomes**

### **Immediate Benefits**
- **Clean Architecture**: Well-structured, maintainable orchestration system
- **Enhanced Testing**: Comprehensive test coverage enabling confident development
- **Improved Developer Experience**: Clear module boundaries and focused responsibilities
- **Better Error Handling**: Detailed error reporting and recovery guidance

### **Long-term Impact**
- **Faster Feature Development**: Modular design enables parallel development
- **Reduced Maintenance Burden**: Clear separation of concerns reduces debugging time
- **Enhanced Reliability**: Comprehensive testing and validation reduces production issues
- **Team Scalability**: Multiple developers can work on different modules simultaneously

### **Technical Excellence**
- **Enterprise-Grade Architecture**: Production-ready orchestration system
- **Comprehensive Monitoring**: Detailed execution metrics and performance insights
- **Extensible Design**: Foundation for future enhancements and capabilities
- **Industry Best Practices**: Modern Python development standards and patterns

---

**Epic E038 represents a critical investment in the long-term maintainability and scalability of the PlanWise Navigator orchestration system. By transforming the monolithic `run_multi_year.py` into a well-architected, modular package, we establish a foundation for sustainable development and operational excellence.**
