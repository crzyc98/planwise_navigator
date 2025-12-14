# Feature Specification: Self-Healing dbt Initialization

**Feature Branch**: `006-self-healing-dbt-init`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Add self-healing dbt initialization that detects missing tables and triggers dbt build automatically on first simulation in new workspaces"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First Simulation in New Workspace (Priority: P1)

As a user creating a new workspace for the first time, I want the simulation to automatically initialize all required database tables so that I don't encounter "table does not exist" errors and can run my first simulation successfully.

**Why this priority**: This is the core problem being solved. New users should have a seamless first-run experience without needing to manually run database setup commands.

**Independent Test**: Can be fully tested by creating a new workspace with no existing database and starting a simulation. The system should automatically detect missing tables and initialize them before proceeding.

**Acceptance Scenarios**:

1. **Given** a new workspace with no database file, **When** the user starts their first simulation, **Then** the system creates the database and initializes all require tables automatically.

2. **Given** a new workspace with an empty database (no tables), **When** the user starts their first simulation, **Then** the system detects missing tables and runs the initialization process before continuing.

3. **Given** a workspace with some but not all required tables, **When** the user starts a simulation, **Then** the system identifies the missing tables and creates only those that are missing.

---

### User Story 2 - Progress Feedback During Initialization (Priority: P2)

As a user waiting for first-time initialization, I want to see clear progress feedback so that I understand what the system is doing and approximately how long it will take.

**Why this priority**: Without feedback, users may think the system is frozen or broken during the potentially lengthy initialization process.

**Independent Test**: Can be tested by observing the UI/CLI output during first-time initialization and verifying progress messages appear.

**Acceptance Scenarios**:

1. **Given** a new workspace requiring initialization, **When** the system begins auto-initialization, **Then** the user sees a message indicating initialization has started.

2. **Given** initialization is in progress, **When** each major step completes, **Then** the user sees progress updates (e.g., "Loading seed data...", "Building foundation models...").

3. **Given** initialization completes successfully, **When** the simulation is ready to proceed, **Then** the user sees a completion message before the simulation continues.

---

### User Story 3 - Graceful Error Recovery (Priority: P3)

As a user whose initialization fails partway through, I want the system to provide clear error messages and allow me to retry so that I can resolve the issue and complete my simulation.

**Why this priority**: Error recovery ensures users aren't stuck in a broken state and can take corrective action.

**Independent Test**: Can be tested by simulating an initialization failure (e.g., corrupt seed file) and verifying the error message is actionable.

**Acceptance Scenarios**:

1. **Given** initialization fails due to a recoverable error, **When** the error is displayed, **Then** the user sees a clear message explaining what went wrong and how to fix it.

2. **Given** a previous initialization attempt failed, **When** the user retries the simulation, **Then** the system attempts initialization again from the beginning (clean retry).

3. **Given** initialization fails due to missing configuration, **When** the error is displayed, **Then** the user is directed to the specific configuration that needs attention.

---

### Edge Cases

- What happens when the database file exists but is corrupted?
  - The system should detect corruption and offer to recreate the database
- What happens when initialization is interrupted (user cancels or system crash)?
  - The system should detect incomplete initialization and restart from a clean state on next attempt
- What happens when disk space is insufficient for initialization?
  - The system should check available space before starting and provide a clear error if insufficient
- What happens when required seed/configuration files are missing?
  - The system should report which files are missing and where they should be located
- What happens when the user runs multiple simulations concurrently during initialization?
  - The system should prevent concurrent initializations to avoid database conflicts

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect when required database tables are missing before starting a simulation
- **FR-002**: System MUST automatically trigger database initialization when missing tables are detected
- **FR-003**: System MUST load seed data (configuration tables) as part of initialization
- **FR-004**: System MUST build foundation models that create required tables after seed data is loaded
- **FR-005**: System MUST provide progress feedback during the initialization process
- **FR-006**: System MUST complete initialization before proceeding with the simulation
- **FR-007**: System MUST handle initialization failures gracefully with actionable error messages
- **FR-008**: System MUST prevent concurrent initialization attempts to avoid database conflicts
- **FR-009**: System MUST verify initialization completed successfully before marking it as done
- **FR-010**: System MUST support retry of failed initializations without leaving the database in a corrupt state

### Non-Functional Requirements

- **NFR-001**: System MUST use structured logging with step timing (start/complete timestamps) for all initialization steps
- **NFR-002**: Log entries MUST include step name, duration, and success/failure status
- **NFR-003**: Logs MUST be compatible with existing `planalign` CLI logging patterns
- **NFR-004**: Initialization MUST complete within 60 seconds for standard workspace configurations (per SC-003)

### Key Entities

- **InitializationState**: Represents the current state of database initialization (not_started, in_progress, completed, failed)
- **RequiredTable**: A table that must exist for simulations to run successfully. Required tables include:
  - Seed tables: config_age_bands, config_tenure_bands, and other configuration seeds
  - Foundation models: int_baseline_workforce, int_employee_compensation_by_year, int_employee_benefits
- **InitializationStep**: A discrete step in the initialization process (seed loading, foundation model building, validation)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of first-time simulations in new workspaces complete successfully without manual intervention
- **SC-002**: Users receive progress feedback within 2 seconds of initialization starting
- **SC-003**: Initialization completes within 60 seconds for standard workspace configurations
- **SC-004**: Error messages during failed initialization include specific remediation steps in 100% of cases
- **SC-005**: Zero "table does not exist" errors reported after this feature is deployed
- **SC-006**: Failed initializations can be retried without requiring manual database cleanup

## Clarifications

### Session 2025-12-12

- Q: What is the required list of tables that must exist for initialization to be considered complete? → A: Seed tables + foundation models (int_baseline_workforce, int_employee_compensation_by_year, int_employee_benefits)
- Q: Should initialization block the simulation entirely until complete, or allow partial simulation? → A: Block completely - simulation cannot proceed until all tables exist
- Q: How should initialization events be logged for debugging and support? → A: Structured logging with step timing (start/complete timestamps per step)

## Constraints & Tradeoffs

- **Blocking Initialization**: Simulation is completely blocked until all required tables exist. This ensures data integrity and prevents confusing partial results, at the cost of requiring users to wait for full initialization before any simulation output.
- **Rejected Alternative**: Partial simulation with degraded functionality was considered but rejected to maintain data consistency and avoid user confusion.

## Assumptions

- The list of required tables is known and stable: seed tables (config_age_bands, config_tenure_bands, etc.) plus foundation models (int_baseline_workforce, int_employee_compensation_by_year, int_employee_benefits)
- Seed data files are present in the expected location for all workspaces
- The database build process is idempotent (can be safely re-run)
- Users have sufficient disk space for database creation (minimum 100MB)
- Single-threaded initialization is acceptable for first-run performance
