# Feature Specification: Event Type Abstraction Layer

**Feature Branch**: `004-event-type-abstraction`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create an event type abstraction layer that allows adding new workforce event types without copy-paste across 5+ files. Preserved behavior: existing events (HIRE, TERMINATION, PROMOTION, RAISE, ENROLLMENT) work identically with same ordering determinism and audit trails. Improved constraints: base EventGenerator interface with required methods (generate_events, calculate_hazard, validate_event), new event types implement interface and get hazard/generation for free, single registration point in config/events.py. This enables sabbatical events, lateral moves, and custom plan types."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add a New Event Type (Priority: P1)

As a platform developer, I want to add a new workforce event type (e.g., SABBATICAL) by implementing a single interface and registering it in one location, so that I can extend the simulation capabilities without modifying multiple unrelated files.

**Why this priority**: This is the core value proposition of the abstraction layer. If developers cannot easily add new event types, the feature fails its primary purpose.

**Independent Test**: Can be fully tested by creating a new SABBATICAL event type, implementing the interface, and verifying it generates events in the simulation output without modifying existing event logic.

**Acceptance Scenarios**:

1. **Given** the EventGenerator interface exists, **When** a developer creates a new SabbaticalEventGenerator implementing all required methods, **Then** they can register it and the simulation produces SABBATICAL events with proper UUIDs and audit trails.

2. **Given** a new event type is registered, **When** the simulation runs, **Then** the new events appear in fct_yearly_events with correct event_type, ordering, and all required metadata fields.

3. **Given** a developer implements a new event generator, **When** they forget to implement a required method, **Then** the system provides a clear error message indicating which method is missing.

---

### User Story 2 - Preserve Existing Event Behavior (Priority: P1)

As a simulation administrator, I want all existing events (HIRE, TERMINATION, PROMOTION, RAISE, ENROLLMENT) to produce identical results after the abstraction is introduced, so that I can trust the system maintains backward compatibility.

**Why this priority**: Equal to P1 because breaking existing functionality would make the feature unusable. The abstraction must not change simulation outcomes.

**Independent Test**: Can be verified by running identical simulations before and after the refactoring and comparing event outputs row-by-row for deterministic equivalence.

**Acceptance Scenarios**:

1. **Given** a simulation with random_seed=42, **When** run before and after the abstraction refactoring, **Then** both runs produce byte-identical fct_yearly_events output (same UUIDs, dates, amounts, ordering).

2. **Given** existing dbt models use hazard-based event generation, **When** migrated to the new interface, **Then** hazard calculations produce identical probabilities for the same employee/year combinations.

3. **Given** the Polars event factory generates events, **When** updated to use the abstraction, **Then** performance remains within 10% of current benchmarks (allowing ≤66s for 5k employees × 5 years).

---

### User Story 3 - Centralized Event Registration (Priority: P2)

As a platform maintainer, I want all event types registered in a single location (config/events.py), so that I can audit available event types and their configurations without searching multiple files.

**Why this priority**: Reduces maintenance burden but is not blocking for core functionality. System can work without perfect centralization.

**Independent Test**: Can be verified by examining config/events.py and confirming it contains a registry listing all event types with their generator implementations.

**Acceptance Scenarios**:

1. **Given** the event registry in config/events.py, **When** I inspect it, **Then** I see a complete list of all event types with their associated generator classes.

2. **Given** an unregistered event generator, **When** the simulation attempts to use it, **Then** the system raises a clear error indicating the event type must be registered.

3. **Given** the event registry, **When** I want to disable an event type for a specific scenario, **Then** I can configure it without modifying generator code.

---

### User Story 4 - Hazard-Based Event Generation Interface (Priority: P2)

As a simulation developer, I want event generators that use hazard-based probability to inherit standard hazard calculation infrastructure, so that I don't need to re-implement random number generation, band lookups, or selection algorithms for each new event type.

**Why this priority**: Significant productivity gain but not essential for MVP. Developers could manually implement hazard logic if needed.

**Independent Test**: Can be verified by creating a new hazard-based event type (e.g., LATERAL_MOVE) that reuses the base hazard infrastructure and produces correctly distributed events.

**Acceptance Scenarios**:

1. **Given** a HazardBasedEventGenerator base class, **When** I subclass it for LATERAL_MOVE events and provide only a hazard rate lookup, **Then** the base class handles RNG, band assignment, and selection automatically.

2. **Given** an event generator using hazard infrastructure, **When** events are generated, **Then** they use the same deterministic hash-based RNG as existing events for reproducibility.

3. **Given** hazard configuration seeds (e.g., config_lateral_move_hazard.csv), **When** the event generator loads, **Then** it automatically integrates with the age/tenure band system defined in config_age_bands.csv.

---

### User Story 5 - SQL and Polars Generation Parity (Priority: P3)

As a performance engineer, I want new event types to be implementable in both SQL (dbt) and Polars modes with guaranteed parity, so that I can leverage either execution engine without result divergence.

**Why this priority**: Important for production use but deferred since MVP can launch with single-mode support.

**Independent Test**: Can be verified by generating events for a new type in both SQL and Polars modes and confirming identical output.

**Acceptance Scenarios**:

1. **Given** a new event type with both SQL and Polars implementations, **When** both are run with identical inputs, **Then** they produce the same events (allowing for expected hash-collision tolerance of <0.01%).

2. **Given** the abstraction layer, **When** registering a new event type, **Then** I can specify whether it supports SQL-only, Polars-only, or both modes.

---

### Edge Cases

- What happens when two event generators produce conflicting events for the same employee on the same date?
  - Events are recorded in generation order with sequence numbers; conflict resolution follows existing precedence rules (TERMINATION supersedes other events).

- How does the system handle event generators that fail mid-simulation?
  - Failed generators raise specific exceptions; the pipeline checkpointing system can recover from the last successful stage.

- What happens if a custom event type requires fields not in the standard SimulationEvent payload?
  - The Pydantic discriminated union pattern allows new payload types; developers add a new payload class to config/events.py.

- How are event generators ordered when multiple types could affect the same employee?
  - Explicit ordering configuration in the registry; existing order (termination → hire → promotion → merit → enrollment) is preserved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a base EventGenerator interface with required methods: `generate_events()`, `validate_event()`, and optional `calculate_hazard()` for hazard-based generators.

- **FR-002**: System MUST maintain a single event type registry in config/events.py that maps event type names to their generator implementations.

- **FR-003**: System MUST preserve byte-identical output for existing event types (HIRE, TERMINATION, PROMOTION, MERIT, ENROLLMENT) when using the same random seed.

- **FR-004**: System MUST support the existing Pydantic v2 discriminated union pattern for event payloads, allowing new payload types to be registered.

- **FR-005**: System MUST integrate new event types with the pipeline orchestrator's staged workflow (EVENT_GENERATION stage).

- **FR-006**: System MUST support event generators that use hazard tables with age/tenure band lookups from centralized seed configuration.

- **FR-007**: System MUST provide clear error messages when:
  - A required interface method is not implemented
  - An unregistered event type is referenced
  - Event validation fails

- **FR-008**: System MUST preserve event ordering determinism across simulation runs with the same configuration.

- **FR-009**: New event types MUST produce events with all required audit fields: event_id (UUID), created_at, scenario_id, plan_design_id, source_system, correlation_id.

- **FR-010**: System MUST support enabling/disabling specific event types per scenario without code changes.

- **FR-011**: System MUST emit structured logs for event generation including: event type, event count, execution time, and generator metadata (supports filtering and production incident analysis).

### Key Entities

- **EventGenerator**: Base interface defining required methods for event generation. Attributes include event_type, requires_hazard, execution_order.

- **HazardBasedEventGenerator**: Extended interface for generators using hazard probability tables. Provides standard band lookup and selection algorithms.

- **EventRegistry**: Centralized mapping of event type names to generator classes, with configuration for ordering and mode support.

- **EventPayload**: Pydantic model representing event-specific data. Each event type has a corresponding payload class with validation rules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can add a new event type by creating a single generator class and one registry entry, without modifying existing event generator files (verified by code review showing ≤3 files changed for new event type).

- **SC-002**: Simulation results remain identical for existing event types (100% row-level match comparing before/after outputs with same seed).

- **SC-003**: New event types integrate with existing data quality tests and audit trail requirements (new events pass all dq_* validation models).

- **SC-004**: Time to implement a new event type reduces from current baseline (developer survey shows 50%+ reduction in lines of code touched).

- **SC-005**: System maintains performance within acceptable bounds (Polars mode achieves ≤66s for 5k employees × 5 years, allowing 10% degradation margin).

- **SC-006**: Error messages for interface violations are actionable (developers resolve 90% of implementation errors without documentation lookup).

## Constraints & Tradeoffs

- **Migration Strategy**: Wrap existing dbt SQL models with interface adapters rather than refactoring them in-place. This preserves tested behavior while enabling gradual adoption of the new interface pattern for future event types.
- **Backward Compatibility Priority**: Existing event generation logic remains untouched; the abstraction layer delegates to current implementations.

## Assumptions

- The existing Pydantic v2 discriminated union pattern is flexible enough to accommodate new event payload types without schema migration.
- Event ordering within a year is deterministic based on generation order, not effective_date (matching current behavior).
- New event types will follow similar patterns to existing workforce events (employee-centric, date-bounded, scenario-isolated).
- The dbt incremental model pattern with delete+insert strategy will work for new event types without modification.
- Hazard-based generators will use the same age/tenure band definitions as existing promotions and terminations.

## Clarifications

### Session 2025-12-12

- Q: Should the abstraction layer wrap existing dbt SQL models or migrate them in-place? → A: Wrap existing models - keep current dbt SQL files, add interface wrappers that delegate to them.
- Q: What level of logging/observability should the abstraction layer provide? → A: Structured logging - log event generation summaries per type with counts, timing, and generator metadata.
