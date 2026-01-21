# Feature Specification: Remove Polars Event Factory

**Feature Branch**: `024-remove-polars-pipeline`
**Created**: 2026-01-21
**Status**: Draft
**Input**: User description: "Remove Polars event factory system completely. Default to SQL mode in the frontend, disable or remove the Polars option from frontend and CLI, and delete the Polars code which is difficult to maintain. The dbt tests work much better with SQL mode."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Simplified Simulation Experience (Priority: P1)

As a financial analyst using PlanAlign Studio, I want to run workforce simulations without having to choose between SQL and Polars execution modes so that I can focus on my analysis instead of technical implementation details.

**Why this priority**: This is the primary user-facing benefit. Removing the engine selection simplifies the user experience and eliminates confusion about which mode to use. All users will automatically get the more reliable SQL-based execution.

**Independent Test**: Can be fully tested by launching PlanAlign Studio, opening any workspace, and running a simulation. The user should see no engine selection options and simulations should execute using SQL mode with consistent, reliable results.

**Acceptance Scenarios**:

1. **Given** a user opens the Configuration page in PlanAlign Studio, **When** they view the advanced settings, **Then** there is no engine selection dropdown (no "Polars" vs "Pandas" option)
2. **Given** a user starts a simulation from the Studio UI, **When** the simulation executes, **Then** it uses SQL mode exclusively without any fallback warnings or mode-switching messages
3. **Given** a saved workspace with `advanced.engine: 'polars'` in its configuration, **When** loaded and simulated, **Then** the system ignores the legacy setting and uses SQL mode

---

### User Story 2 - Consistent CLI Interface (Priority: P2)

As a DevOps engineer running batch simulations, I want to run the CLI without needing to know about or configure Polars mode so that my automation scripts are simpler and more reliable.

**Why this priority**: CLI users running automated batch jobs need consistent, predictable behavior. Removing Polars options from the CLI eliminates a source of configuration errors and simplifies CI/CD pipelines.

**Independent Test**: Can be fully tested by running `planalign simulate 2025-2027` and `planalign batch` commands. The commands should execute without any `--use-polars-engine` or `--polars-output` options and should not produce deprecation warnings.

**Acceptance Scenarios**:

1. **Given** a user runs `planalign simulate --help`, **When** viewing the available options, **Then** there are no Polars-related flags (`--use-polars-engine`, `--polars-output`)
2. **Given** a user runs `planalign simulate 2025-2027`, **When** the simulation completes, **Then** all events are generated via SQL/dbt models
3. **Given** a user runs a command with a removed flag (e.g., `--use-polars-engine`), **When** the command executes, **Then** an appropriate error indicates the flag is unrecognized

---

### User Story 3 - Improved Test Reliability (Priority: P2)

As a developer maintaining the PlanAlign Engine, I want all simulations to run through SQL/dbt so that dbt tests consistently validate data quality without dual-path complexity.

**Why this priority**: The current dual-path architecture (SQL vs Polars) makes it difficult to maintain test coverage and creates scenarios where Polars mode bypasses dbt tests. SQL-only mode ensures all data flows through dbt's validation framework.

**Independent Test**: Can be fully tested by running `pytest -m fast` and `dbt test --threads 1`. All tests should pass without Polars-related test fixtures or mock configurations.

**Acceptance Scenarios**:

1. **Given** the test suite includes Polars-specific tests, **When** the Polars code is removed, **Then** those tests are also removed or updated to test SQL-only behavior
2. **Given** a simulation runs via any entry point (CLI, Studio, API), **When** events are generated, **Then** all events pass through `fct_yearly_events` and standard dbt tests
3. **Given** an integration test runs a multi-year simulation, **When** the simulation completes, **Then** all data quality validations execute via dbt tests

---

### User Story 4 - Reduced Codebase Complexity (Priority: P3)

As a developer onboarding to the PlanAlign project, I want a single execution path for simulations so that I can understand the codebase faster without learning two parallel implementations.

**Why this priority**: Reducing codebase size by ~7,300 lines improves maintainability and lowers the barrier for new developers. This is a long-term benefit that compounds over time.

**Independent Test**: Can be validated by reviewing the codebase after removal to confirm no Polars event factory, state pipeline, or integration code remains.

**Acceptance Scenarios**:

1. **Given** the Polars removal is complete, **When** searching the codebase for "polars_event_factory" or "polars_state_pipeline", **Then** no implementation files are found
2. **Given** the codebase is analyzed, **When** counting lines of code, **Then** approximately 4,400+ lines of Polars implementation code are removed
3. **Given** the `requirements.txt` or `pyproject.toml` is reviewed, **When** checking dependencies, **Then** `polars` can be made an optional dependency (not required for core functionality)

---

### Edge Cases

- **Legacy workspace with Polars configuration**: The system ignores the legacy `advanced.engine: 'polars'` setting and uses SQL mode. No error is raised to maintain backward compatibility with existing workspaces.
- **External script with removed CLI flags**: The CLI returns an error indicating the flag is unrecognized, prompting users to update their scripts.
- **Existing Parquet output files**: Files in `data/parquet/` from previous Polars runs remain but are no longer read or written by the system. Documentation should note that these are legacy artifacts.
- **Polars library still installed**: The presence of the `polars` Python library has no effect; the system never attempts to use it for event generation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST execute all event generation using SQL/dbt models exclusively
- **FR-002**: System MUST NOT provide any user-facing option to select Polars execution mode
- **FR-003**: CLI MUST NOT include `--use-polars-engine` or `--polars-output` options
- **FR-004**: PlanAlign Studio MUST NOT display engine selection in the configuration UI
- **FR-005**: API MUST NOT accept or process `advanced.engine` configuration for Polars mode
- **FR-006**: System MUST gracefully handle legacy workspace configurations that reference Polars mode by ignoring them
- **FR-007**: System MUST remove all Polars event factory implementation files (`polars_event_factory.py`, `polars_state_pipeline.py`, `polars_integration.py`)
- **FR-008**: System MUST remove Polars-specific configuration classes and settings from the config module
- **FR-009**: System MUST simplify pipeline executors by removing hybrid SQL/Polars branching logic
- **FR-010**: Test suite MUST be updated to remove Polars-specific test files and fixtures

### Key Entities

- **EventGenerationExecutor**: Pipeline component that executes event generation - will be simplified to SQL-only execution
- **SimulationConfig**: Configuration model for simulations - will have `advanced.engine` field removed or deprecated
- **Workspace**: User workspace that may contain legacy Polars configuration - will ignore Polars settings silently

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Codebase reduces by approximately 4,400+ lines of Polars implementation code (measured by line count diff)
- **SC-002**: All existing dbt tests pass after removal (no test regressions)
- **SC-003**: Multi-year simulations (2025-2030) complete successfully using SQL-only mode
- **SC-004**: New developers can understand the event generation flow by reading a single code path instead of two
- **SC-005**: Studio configuration page loads without engine selection options
- **SC-006**: CLI help text shows no Polars-related options
- **SC-007**: Existing workspaces with Polars configuration load and run without errors

## Assumptions

- The SQL/dbt mode provides equivalent functionality to Polars mode for all supported event types (hire, termination, promotion, merit, enrollment)
- Performance of SQL mode is acceptable for the target use case (simulations with <10,000 employees over 5-10 years)
- No external systems depend on the Polars-specific Parquet output format
- Users have not built custom integrations that rely on the `--use-polars-engine` CLI flag

## Out of Scope

- Optimizing SQL mode performance to match Polars mode speed (current SQL mode performance is acceptable)
- Removing the `polars` Python library from the project (it may be used for other purposes)
- Migrating existing Parquet files to DuckDB format
- Creating a migration utility for legacy workspace configurations (silent ignore is sufficient)
