# Data Model: Event Type Abstraction Layer

**Feature**: 004-event-type-abstraction
**Date**: 2025-12-12

## Entity Definitions

### EventGenerator (Abstract Base)

The core interface that all event generators must implement.

| Attribute | Type | Description |
|-----------|------|-------------|
| `event_type` | `str` | Unique identifier (e.g., "hire", "termination") |
| `execution_order` | `int` | Determines processing sequence (lower = earlier) |
| `requires_hazard` | `bool` | Whether generator uses hazard probability tables |
| `supports_sql` | `bool` | Whether SQL/dbt mode is supported |
| `supports_polars` | `bool` | Whether Polars mode is supported |

**Required Methods**:
- `generate_events(context: EventContext) -> List[SimulationEvent]`
- `validate_event(event: SimulationEvent) -> ValidationResult`

**Optional Methods**:
- `calculate_hazard(employee: Employee, year: int) -> float` (required if `requires_hazard=True`)

### HazardBasedEventGenerator (Mixin)

Provides infrastructure for hazard-probability-based event generation.

| Attribute | Type | Description |
|-----------|------|-------------|
| `hazard_table_name` | `str` | Name of hazard config seed (e.g., "config_promotion_hazard") |
| `rng_salt` | `str` | Additional salt for deterministic RNG |

**Provided Methods**:
- `get_hazard_rate(age_band: str, tenure_band: str, level: int) -> float`
- `get_random_value(employee_id: str, year: int) -> float`
- `assign_age_band(age: float) -> str`
- `assign_tenure_band(tenure: float) -> str`
- `select_by_hazard(workforce: DataFrame, year: int) -> DataFrame`

### EventRegistry

Centralized registration and lookup for all event generators.

| Attribute | Type | Description |
|-----------|------|-------------|
| `_generators` | `Dict[str, Type[EventGenerator]]` | Map of event_type to generator class |
| `_instances` | `Dict[str, EventGenerator]` | Cached generator instances |
| `_disabled` | `Set[str]` | Event types disabled for current scenario |

**Methods**:
- `register(event_type: str) -> Callable` (decorator)
- `get(event_type: str) -> EventGenerator`
- `list_all() -> List[str]`
- `list_enabled(scenario_id: str) -> List[str]`
- `disable(event_type: str, scenario_id: str) -> None`
- `enable(event_type: str, scenario_id: str) -> None`

### EventContext

Runtime context passed to event generators.

| Attribute | Type | Description |
|-----------|------|-------------|
| `simulation_year` | `int` | Current simulation year |
| `scenario_id` | `str` | Active scenario identifier |
| `plan_design_id` | `str` | Plan design configuration |
| `random_seed` | `int` | Global random seed for reproducibility |
| `dbt_runner` | `DbtRunner` | For SQL mode execution |
| `db_manager` | `DatabaseConnectionManager` | For direct queries |
| `config` | `SimulationConfig` | Full simulation configuration |

### ValidationResult

Result of event validation.

| Attribute | Type | Description |
|-----------|------|-------------|
| `is_valid` | `bool` | Whether event passed validation |
| `errors` | `List[str]` | List of validation error messages |
| `warnings` | `List[str]` | List of validation warnings |

### GeneratorMetrics

Structured logging output for observability (FR-011).

| Attribute | Type | Description |
|-----------|------|-------------|
| `event_type` | `str` | Generator event type |
| `event_count` | `int` | Number of events generated |
| `execution_time_ms` | `float` | Generation time in milliseconds |
| `mode` | `str` | "sql" or "polars" |
| `year` | `int` | Simulation year |
| `scenario_id` | `str` | Scenario identifier |

## Entity Relationships

```
EventRegistry
    │
    ├── has many ──► EventGenerator (registered generators)
    │                    │
    │                    ├── is-a ──► HireEventGenerator
    │                    ├── is-a ──► TerminationEventGenerator
    │                    ├── is-a ──► PromotionEventGenerator (uses HazardMixin)
    │                    ├── is-a ──► MeritEventGenerator (uses HazardMixin)
    │                    └── is-a ──► EnrollmentEventGenerator
    │
    └── provides ──► EventContext (runtime context)
                         │
                         └── uses ──► DbtRunner, DatabaseConnectionManager
```

## State Transitions

### Generator Lifecycle

```
REGISTERED ──► INITIALIZED ──► GENERATING ──► COMPLETED
     │              │               │             │
     │              │               │             └── metrics emitted
     │              │               └── events validated
     │              └── context injected
     └── decorator registration
```

### Event Validation States

```
CREATED ──► VALIDATING ──► VALID ──► STORED
                │
                └── INVALID ──► ERROR (with messages)
```

## Validation Rules

### EventGenerator Registration
- `event_type` must be unique across registry
- `event_type` must match pattern `[a-z][a-z0-9_]*`
- `execution_order` must be positive integer
- At least one of `supports_sql` or `supports_polars` must be True

### Event Validation (via `validate_event`)
- `event_id` must be valid UUID
- `employee_id` must be non-empty string
- `effective_date` must be within simulation year
- `scenario_id` must match context
- `plan_design_id` must match context
- Payload must pass Pydantic validation

## Existing Entities (Unchanged)

The following entities from `config/events.py` remain unchanged:

- `SimulationEvent` - Core event model with discriminated union payload
- `HirePayload`, `TerminationPayload`, `PromotionPayload`, `MeritPayload`, `EnrollmentPayload` - Event-specific payloads
- `WorkforceEventFactory`, `DCPlanEventFactory`, `PlanAdministrationEventFactory` - Existing factory classes (retained for backward compatibility)

## Index of Execution Orders

| Event Type | execution_order | Notes |
|------------|-----------------|-------|
| termination | 10 | Must run first (affects workforce counts) |
| hire | 20 | Backfills for terminations |
| new_hire_termination | 25 | Subset of hires that terminate same year |
| promotion | 30 | Uses hazard tables |
| merit | 40 | Uses hazard tables |
| enrollment | 50 | Depends on workforce state |
| deferral_escalation | 60 | Post-enrollment adjustments |
