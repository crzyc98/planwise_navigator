# Feature Specification: SQLParse Token Limit Fix for dbt Subprocess

**Feature Branch**: `011-sqlparse-token-limit-fix`
**Created**: 2026-01-06
**Status**: Draft
**Input**: User description: "Fix Maximum number of tokens exceeded (10000) error caused by sqlparse 0.5.4+ token limit in dbt subprocess"

## Problem Statement

The dbt simulation fails on Year 2 with error "Maximum number of tokens exceeded (10000)" due to:

1. **sqlparse 0.5.4+** introduced a 10,000 token limit for SQL parsing (DoS protection)
2. **fct_workforce_snapshot.sql** has ~1,085 lines with complex Jinja templating that compiles to ~13,668 tokens
3. **Year 2 fails** because the Jinja compiles to MORE SQL than Year 1:
   - Year 1 uses simpler `int_baseline_workforce`
   - Year 2 uses `int_active_employees_prev_year_snapshot` + temporal logic
   - Year 2's compiled SQL pushes past the 10,000 token limit
4. **Existing fix fails**: The fix in `planalign_orchestrator/__init__.py` sets `sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000` but dbt runs as a subprocess with its own Python environment - the sqlparse limit isn't inherited

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Year Simulation Completes Without Token Errors (Priority: P1)

A data analyst runs a multi-year workforce simulation (2025-2027) using the PlanAlign Orchestrator. The simulation should complete all years without encountering sqlparse token limit errors.

**Why this priority**: This is the core business use case. Without this fix, Year 2+ simulations fail entirely, blocking production use.

**Independent Test**: Run `planalign simulate 2025-2027 --verbose` and verify all three years complete successfully.

**Acceptance Scenarios**:

1. **Given** a configured simulation environment, **When** I run `planalign simulate 2025-2027`, **Then** all three years complete without "Maximum number of tokens exceeded" errors
2. **Given** fct_workforce_snapshot.sql with 1,085 lines, **When** dbt compiles the model for Year 2, **Then** the compiled SQL (even with 13,668+ tokens) is parsed successfully
3. **Given** the DbtRunner spawns a subprocess, **When** dbt starts, **Then** sqlparse.engine.grouping.MAX_GROUPING_TOKENS is set to 50000 before any SQL parsing occurs

---

### User Story 2 - Direct dbt Commands Work (Priority: P2)

A developer runs dbt commands directly from the command line (not through the orchestrator). These commands should also work without token limit errors.

**Why this priority**: Developers need to test models during development without going through the full orchestrator.

**Independent Test**: Run `cd dbt && dbt run --select fct_workforce_snapshot --vars '{"simulation_year": 2026}'` and verify it completes.

**Acceptance Scenarios**:

1. **Given** a developer is in the dbt directory, **When** they run `dbt run --select fct_workforce_snapshot --vars '{"simulation_year": 2026}'`, **Then** the command completes without token errors
2. **Given** the sqlparse limit is configured, **When** dbt loads, **Then** the limit is already raised before any model compilation

---

### User Story 3 - Batch Scenario Processing Works (Priority: P2)

A data analyst runs batch scenario processing with multiple scenarios. All scenarios should complete without token limit errors.

**Why this priority**: Batch processing is a critical workflow for scenario comparison.

**Independent Test**: Run `planalign batch --scenarios baseline high_growth` and verify both scenarios complete all years.

**Acceptance Scenarios**:

1. **Given** multiple scenarios configured, **When** I run batch processing, **Then** all scenarios complete without token errors
2. **Given** each scenario spawns separate dbt subprocesses, **When** dbt starts for each scenario, **Then** sqlparse limits are correctly configured for each subprocess

---

### Edge Cases

- **sqlparse API changes**: If sqlparse is upgraded to a version that changes or removes MAX_GROUPING_TOKENS, the configuration MUST fail silently with graceful fallback (continue without patch). Use try/except for ImportError and AttributeError.
- **Existing sitecustomize.py**: Install script MUST append to existing file rather than overwrite, preserving user's customizations while adding sqlparse configuration. Script should check for duplicate configuration before appending.
- **Different venv**: Running dbt in a different virtual environment than planalign_orchestrator is NOT supported. Documentation MUST state that dbt and the orchestrator must use the same virtual environment for the fix to work.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST configure sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000 before any dbt command execution
- **FR-002**: The configuration MUST work for dbt commands spawned as subprocesses by DbtRunner
- **FR-003**: The configuration MUST work for direct dbt commands run from the command line in the dbt directory
- **FR-004**: The configuration MUST be idempotent (safe to apply multiple times)
- **FR-005**: The configuration MUST gracefully handle sqlparse versions that don't have MAX_GROUPING_TOKENS attribute
- **FR-006**: System MUST NOT permanently modify the user's Python environment (e.g., no global site-packages changes)
- **FR-007**: System MUST log when the sqlparse limit is configured (for debugging purposes)

### Non-Functional Requirements

- **NFR-001**: Solution MUST work with Python 3.11+
- **NFR-002**: Solution MUST work with sqlparse 0.5.4+ (the versions with DoS protection)
- **NFR-003**: Solution MUST work with dbt-core 1.8.8+ and dbt-duckdb 1.8.1+
- **NFR-004**: Solution SHOULD have minimal startup overhead (<10ms)

### Key Entities

- **DbtRunner**: The orchestrator component that spawns dbt subprocesses (in `planalign_orchestrator/dbt_runner.py`)
- **sqlparse.engine.grouping**: The sqlparse module containing MAX_GROUPING_TOKENS constant
- **dbt/conftest.py or usercustomize.py**: The hook file that configures sqlparse before dbt loads

## Clarifications

### Session 2026-01-06

- Q: How should the system handle if sitecustomize.py already exists with other customizations? → A: Append to existing file (preserve + add)
- Q: What happens when sqlparse is upgraded to a version that changes the API? → A: Fail silently with graceful fallback (continue without patch)
- Q: What if dbt is installed in a different virtual environment than planalign_orchestrator? → A: Document as unsupported (require same venv)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Multi-year simulation (2025-2027) completes without "Maximum number of tokens exceeded" errors
- **SC-002**: fct_workforce_snapshot.sql compiles successfully for all simulation years (2025, 2026, 2027)
- **SC-003**: Direct dbt commands work without requiring any manual configuration by the user
- **SC-004**: No Python warnings or errors during sqlparse configuration
- **SC-005**: Existing tests continue to pass (no regressions)
