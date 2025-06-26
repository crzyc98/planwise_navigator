# Epic E013: Dagster Simulation Pipeline Modularization

**Status**: Planning
**Priority**: High
**Epic Owner**: Technical Lead
**Start Date**: 2024-06-24
**Target Completion**: Q3 2024

## Executive Summary

The current Dagster simulation pipeline contains a monolithic `run_multi_year_simulation` operation of 325+ lines that handles multiple responsibilities including data cleaning, orchestration, dbt command execution, validation, and logging. This creates maintenance burden, code duplication, and testing challenges that impact development velocity and code quality.

This epic will refactor the pipeline into modular, single-responsibility components while preserving identical business logic and simulation sequence as defined in Epic 11.5.

## Business Justification

### Current Pain Points
- **Maintenance Overhead**: Logic changes require updates in multiple locations due to 60% code duplication between single-year and multi-year operations
- **Development Velocity**: Large, complex functions slow down feature development and bug fixes
- **Testing Difficulty**: Monolithic structure makes unit testing and isolation challenging
- **Code Quality**: Repetitive dbt command patterns (15+ identical blocks) violate DRY principles
- **Risk Management**: Large functions increase risk of introducing bugs during modifications

### Business Value
- **Reduced Development Time**: Modular components enable faster feature development and maintenance
- **Improved Code Quality**: Single-responsibility functions with standardized patterns
- **Enhanced Reliability**: Smaller, focused functions are easier to test and validate
- **Team Productivity**: Cleaner codebase improves developer experience and onboarding
- **Technical Debt Reduction**: Eliminates architectural debt that could compound over time

### Success Metrics
- **Code Reduction**: 60% reduction in run_multi_year_simulation function size (325 → ~50 lines)
- **Duplication Elimination**: Remove 100% of duplicated logic between single/multi-year operations
- **Testing Coverage**: Achieve >95% unit test coverage on new modular components
- **Performance**: Maintain identical simulation execution time and results
- **Maintainability**: Reduce average time to implement new features by 30%

## Technical Scope

### In Scope
1. **Modularization of run_multi_year_simulation operation**
   - Extract data cleaning logic into dedicated operation
   - Create reusable dbt command executor utility
   - Separate event processing into focused operations
   - Transform main operation into pure orchestrator

2. **Refactoring of run_year_simulation operation**
   - Integrate with new utility functions
   - Eliminate code duplication
   - Maintain existing validation logic

3. **Standardization of dbt command execution**
   - Create centralized dbt command utility
   - Standardize error handling and logging
   - Implement consistent --vars and --full-refresh handling

4. **Testing and validation framework**
   - Unit tests for all new modular components
   - Integration tests to verify identical behavior
   - Performance benchmarking

### Out of Scope
- Changes to simulation business logic or Epic 11.5 sequence
- Modifications to dbt models or database schema
- User interface or dashboard changes
- Configuration structure changes

### Dependencies
- No external dependencies identified
- Internal dependency on existing dbt models and database structure
- Requires coordination with any concurrent Epic 11.5 simulation changes

## Architecture Overview

### Current State
```
run_multi_year_simulation (325 lines)
├── Data cleaning (embedded)
├── Year loop orchestration
├── dbt command execution (15+ repetitive blocks)
├── Event processing logic (duplicated from single-year)
├── Validation and error handling
└── Summary logging
```

### Target State
```
run_multi_year_simulation (~50 lines)
├── clean_duckdb_data_op()
├── For each year:
│   └── run_year_simulation_op() (refactored)
│       ├── execute_dbt_command() utility
│       ├── run_dbt_event_models_for_year_op()
│       ├── run_dbt_snapshot_for_year_op()
│       └── validate_year_results()
└── Summary logging
```

## User Stories

| Story ID | Title | Priority | Estimate | Status |
|----------|-------|----------|----------|---------|
| S013-01 | dbt Command Utility Creation | High | 3 pts | Not Started |
| S013-02 | Data Cleaning Operation Extraction | High | 2 pts | Not Started |
| S013-03 | Event Processing Modularization | High | 5 pts | Not Started |
| S013-04 | Snapshot Management Operation | Medium | 3 pts | Not Started |
| S013-05 | Single-Year Operation Refactoring | High | 4 pts | Not Started |
| S013-06 | Multi-Year Orchestration Transformation | High | 4 pts | Not Started |
| S013-07 | Validation and Testing Implementation | High | 5 pts | Not Started |
| S013-08 | Documentation and Cleanup | Medium | 2 pts | Not Started |

**Total Estimate**: 28 story points

## Risk Assessment

### Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Behavior changes during refactoring | Medium | High | Comprehensive integration testing with before/after comparison |
| Performance regression | Low | Medium | Benchmarking and profiling during development |
| Complex state dependencies | Medium | Medium | Careful analysis of year-to-year dependencies |

### Business Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Delayed delivery impacting other initiatives | Low | High | Phased delivery approach with incremental validation |
| Resource allocation conflicts | Medium | Medium | Clear sprint planning and stakeholder communication |

## Acceptance Criteria

### Epic-Level Acceptance Criteria
1. **Functional Preservation**
   - All existing simulation tests pass without modification
   - Identical simulation results for same input parameters
   - All existing error handling behavior preserved

2. **Code Quality Improvements**
   - run_multi_year_simulation reduced to <100 lines
   - Zero code duplication between single/multi-year operations
   - All new functions <40 lines per PlanWise coding standards

3. **Testing Coverage**
   - >95% unit test coverage on new modular components
   - Integration tests validate end-to-end simulation pipeline
   - Performance benchmarks show no regression

4. **Documentation**
   - Updated docstrings for all modified functions
   - Architecture documentation reflects new modular structure
   - Migration guide for future developers

## Definition of Done

- [ ] All user stories completed with acceptance criteria met
- [ ] Code review approved by technical lead
- [ ] All existing tests pass
- [ ] New unit and integration tests implemented and passing
- [ ] Performance benchmarking completed with no regressions
- [ ] Documentation updated and reviewed
- [ ] Epic acceptance criteria validated
- [ ] Deployment to development environment successful
- [ ] Stakeholder sign-off obtained

## Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Analysis & Design | 1 week | Technical specification, detailed story breakdown |
| Core Utilities Development | 2 weeks | dbt command utility, data cleaning operation |
| Modularization Implementation | 3 weeks | Event processing ops, single-year refactoring |
| Integration & Testing | 2 weeks | Multi-year transformation, comprehensive testing |
| Documentation & Cleanup | 1 week | Final documentation, code cleanup |

**Total Duration**: 9 weeks

## Communication Plan

- **Weekly Progress Updates**: Technical lead provides status to stakeholders
- **Milestone Reviews**: Architecture review at 25%, 50%, and 75% completion
- **Final Presentation**: Demo of refactored pipeline and benefits achieved

---

*This epic aligns with PlanWise Navigator's technical excellence initiatives and supports the long-term maintainability of the workforce simulation platform.*
