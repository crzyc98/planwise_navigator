# Feature Specification: Unified Database Path Resolver

**Feature Branch**: `005-database-path-resolver`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Unify database path resolution logic that is currently duplicated across 3 API services (analytics_service.py, comparison_service.py, simulation_service.py). Preserved behavior: all existing API endpoints find the correct database file, fallback chain (scenario-specific → workspace → project default) works identically. Improved constraints: single DatabasePathResolver service class, all services inject the resolver instead of implementing fallback logic, path resolution is unit-testable in isolation. This enables multi-tenant deployments and proper workspace isolation testing."

## Clarifications

### Session 2025-12-12

- Q: Should the resolver validate workspace_id and scenario_id inputs to prevent path traversal attacks? → A: Yes, resolver validates inputs (rejects path separators, null bytes, relative paths)
- Q: Should the resolver be thread-safe for concurrent FastAPI requests? → A: Stateless resolver with no mutable instance state, thread-safe by design
- Q: How should project_root be determined for the fallback database path? → A: Configurable project_root with fallback to relative path default

## User Scenarios & Testing *(mandatory)*

### User Story 1 - API Developer Injects Resolver (Priority: P1)

As an API developer, I want to inject a DatabasePathResolver into my service instead of implementing fallback logic, so that database path resolution is consistent across all services and I don't duplicate code.

**Why this priority**: This is the core value proposition - eliminating code duplication and ensuring consistent behavior across all API services. Without this, the other stories cannot be implemented.

**Independent Test**: Can be fully tested by creating a new service that injects the resolver and verifying it returns the same database paths as the existing inline implementations.

**Acceptance Scenarios**:

1. **Given** an AnalyticsService with an injected DatabasePathResolver, **When** I request a database path for workspace "ws1" and scenario "sc1", **Then** the resolver returns the same path that the original inline logic would have returned.

2. **Given** a ComparisonService with an injected DatabasePathResolver, **When** I compare scenarios that use different database locations (scenario-specific vs workspace-level), **Then** each scenario's database is correctly resolved through the resolver.

3. **Given** a SimulationService with an injected DatabasePathResolver, **When** I fetch results for a scenario, **Then** the resolver applies the same fallback chain as the original implementation.

---

### User Story 2 - Test Author Validates Path Resolution in Isolation (Priority: P2)

As a test author, I want to unit test database path resolution logic without requiring a real filesystem or workspace storage, so that I can verify fallback behavior quickly and reliably.

**Why this priority**: Testability is a key constraint in the requirements. Being able to test path resolution in isolation enables TDD workflows and catches regressions early.

**Independent Test**: Can be tested by creating a mock WorkspaceStorage, instantiating a DatabasePathResolver, and verifying the fallback chain returns expected paths for various filesystem states.

**Acceptance Scenarios**:

1. **Given** a mock WorkspaceStorage with scenario path "/workspaces/ws1/scenarios/sc1", **When** I resolve a database path and the scenario-level database exists, **Then** the resolver returns "/workspaces/ws1/scenarios/sc1/simulation.duckdb".

2. **Given** a mock WorkspaceStorage where scenario-level database does NOT exist but workspace-level does, **When** I resolve a database path, **Then** the resolver returns the workspace-level path.

3. **Given** a mock WorkspaceStorage where neither scenario nor workspace databases exist, **When** I resolve a database path, **Then** the resolver returns the project default path or None if that also doesn't exist.

---

### User Story 3 - Operator Configures Multi-Tenant Isolation (Priority: P3)

As a platform operator, I want the database resolver to support workspace isolation configuration, so that multi-tenant deployments can prevent cross-workspace data access.

**Why this priority**: Multi-tenant deployment is mentioned as an enabler in the requirements but is a future capability. The resolver should be designed to support this without breaking existing single-tenant behavior.

**Independent Test**: Can be tested by configuring the resolver with isolation mode enabled and verifying it does NOT fall back to project-level databases when workspace-level is missing.

**Acceptance Scenarios**:

1. **Given** a DatabasePathResolver configured for multi-tenant mode, **When** I resolve a path and neither scenario nor workspace databases exist, **Then** the resolver returns None instead of falling back to project default.

2. **Given** a DatabasePathResolver configured for single-tenant mode (default), **When** I resolve a path and only project default exists, **Then** the resolver returns the project default path with a warning.

---

### Edge Cases

- What happens when the workspace_id is invalid or the workspace path doesn't exist?
  - The resolver returns None and logs a warning
- What happens when multiple DuckDB files exist at different levels (scenario + workspace + project)?
  - The resolver returns the most specific (scenario-level) per the fallback chain
- What happens when the database file exists but is locked or corrupted?
  - Path resolution succeeds (file exists); connection errors are handled by the calling service
- What happens when the project root cannot be determined?
  - The resolver raises a ConfigurationError at instantiation, not during resolution
- What happens when workspace_id or scenario_id contains path traversal characters (e.g., "../", null bytes)?
  - The resolver rejects the input immediately and returns None with a logged security warning

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a single DatabasePathResolver class that encapsulates all database path resolution logic
- **FR-002**: System MUST maintain the existing fallback chain: scenario-specific → workspace → project default
- **FR-003**: System MUST allow services to receive the resolver via dependency injection (constructor parameter)
- **FR-004**: System MUST support isolation modes: "single-tenant" (fallback to project default allowed) and "multi-tenant" (no project fallback)
- **FR-005**: System MUST log a warning when falling back to project-level database in single-tenant mode
- **FR-006**: System MUST return the resolved path along with metadata indicating which level it was found at (scenario, workspace, or project)
- **FR-007**: All three existing services (AnalyticsService, ComparisonService, SimulationService) MUST be refactored to use the new resolver
- **FR-008**: System MUST maintain backward compatibility - all existing API endpoints must continue to work identically
- **FR-009**: System MUST validate workspace_id and scenario_id inputs, rejecting path separators, null bytes, and relative path components to prevent path traversal attacks
- **FR-010**: System MUST implement the resolver as stateless (no mutable instance state) to ensure thread-safety for concurrent FastAPI request handling
- **FR-011**: System MUST accept an optional project_root parameter at construction, falling back to the existing relative path detection if not provided

### Key Entities

- **DatabasePathResolver**: Stateless service class responsible for resolving database paths given workspace and scenario identifiers. Contains fallback logic and isolation mode configuration (immutable after construction). Thread-safe by design.
- **ResolvedDatabasePath**: Value object containing the resolved path and metadata (source level, warnings). Attributes: path (Path or None), source ("scenario" | "workspace" | "project" | None), warning (optional message).
- **WorkspaceStorage**: Existing storage abstraction that provides workspace and scenario path helpers. The resolver depends on this for path construction.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All database path resolution logic exists in exactly one location (DatabasePathResolver class)
- **SC-002**: Zero code duplication - grep for the fallback pattern yields only the resolver implementation
- **SC-003**: Unit tests for path resolution execute in under 100ms without filesystem I/O
- **SC-004**: All existing API integration tests pass without modification (backward compatibility)
- **SC-005**: The resolver is used by all three services: AnalyticsService, ComparisonService, SimulationService
- **SC-006**: Code coverage for DatabasePathResolver is at least 95%

## Assumptions

- The existing `WorkspaceStorage` class will remain the source of truth for workspace and scenario path construction
- The database filename remains `simulation.duckdb` across all levels
- The project root path can be explicitly configured at resolver construction; if not provided, it defaults to the existing pattern (`Path(__file__).parent.parent.parent` relative to API services)
- Services will adopt constructor injection; no changes to FastAPI dependency injection patterns are required beyond passing the resolver
- Multi-tenant mode is a configuration option but not required for initial implementation to work
