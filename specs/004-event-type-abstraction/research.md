# Research: Event Type Abstraction Layer

**Feature**: 004-event-type-abstraction
**Date**: 2025-12-12

## Research Tasks

### 1. Interface Pattern for Event Generators

**Decision**: Abstract Base Class (ABC) with `@abstractmethod`

**Rationale**: Python's ABC provides:
- Clear contract enforcement at class definition time (not runtime)
- IDE support for detecting missing implementations
- Type checker compatibility (mypy)
- Familiar pattern already used in the codebase (`DbtRunner` inheritance)

**Alternatives Considered**:
- **Protocol (structural typing)**: Rejected - doesn't enforce implementation at definition time; errors occur at call site
- **Duck typing with runtime checks**: Rejected - deferred error detection conflicts with test-first development principle
- **Dataclass with methods**: Rejected - less clear about required vs optional methods

### 2. Registry Pattern for Event Types

**Decision**: Dictionary-based registry with decorator registration

**Rationale**:
- Single import automatically registers all event types
- Decorator pattern (`@register_event_type`) is idiomatic Python
- Allows runtime introspection of available event types
- Supports scenario-specific enable/disable via configuration overlay

**Alternatives Considered**:
- **Explicit registration in __init__.py**: Rejected - requires manual update for each new type
- **Plugin discovery (entry_points)**: Rejected - over-engineering for internal use case
- **Enum-based dispatch**: Rejected - doesn't scale for new types without code modification

### 3. Wrapper Strategy for Existing Events

**Decision**: Thin adapter pattern delegating to existing dbt models via DbtRunner

**Rationale**:
- Preserves byte-identical output (requirement FR-003)
- Zero risk of breaking existing tested logic
- Enables gradual migration - new events use pure interface, existing events use wrappers
- Wrapper overhead is negligible (single method call delegation)

**Alternatives Considered**:
- **In-place refactoring**: Rejected - high risk of breaking determinism; violates clarification decision
- **Parallel implementation**: Rejected - maintenance burden of two code paths

### 4. Hazard Infrastructure Integration

**Decision**: Mixin class providing band lookup, RNG, and selection algorithms

**Rationale**:
- Composition over inheritance allows flexibility
- Existing `PolarsDeterministicRNG` can be extracted and reused
- Band lookups from `config_age_bands.csv` / `config_tenure_bands.csv` already centralized
- Mixin can be used by both SQL and Polars mode implementations

**Alternatives Considered**:
- **Full inheritance hierarchy**: Rejected - inflexible for events that don't need hazard
- **Utility functions**: Rejected - less discoverable, no shared state management
- **Service injection**: Rejected - over-engineering for single-use case

### 5. SQL vs Polars Mode Support

**Decision**: Mode-specific strategy pattern within each generator

**Rationale**:
- Existing `EventGenerationExecutor` already switches on mode
- Generator interface defines `supports_sql()` and `supports_polars()` methods
- Mode selection at execution time, not registration time
- Allows gradual Polars support addition to existing wrappers

**Alternatives Considered**:
- **Separate generator classes per mode**: Rejected - duplication of registration and configuration
- **Mode as constructor parameter**: Rejected - complicates registry pattern

## Integration Points Analysis

### 1. `config/events.py` (972 lines)

**Current State**: Contains Pydantic payload models and factory classes
**Integration**:
- Add `EventRegistry` class (~50 lines)
- Add `EventGenerator` ABC import/re-export
- Preserve existing `SimulationEvent`, payload classes, and factories

### 2. `planalign_orchestrator/pipeline/event_generation_executor.py` (572 lines)

**Current State**: `EventGenerationExecutor` class with `_get_event_generation_models()` returning hardcoded model list
**Integration**:
- Replace hardcoded list with registry lookup
- Add generator iteration with structured logging
- Preserve mode selection logic (SQL vs Polars)

### 3. `planalign_orchestrator/polars_event_factory.py` (150+ lines reviewed)

**Current State**: `PolarsEventGenerator` with hardcoded event type methods
**Integration**:
- Extract RNG to reusable mixin
- Refactor to call generator interface for each event type
- Preserve performance characteristics (vectorized operations)

### 4. dbt Models (`dbt/models/intermediate/events/`)

**Current State**: 10 event SQL models with `tag:EVENT_GENERATION`
**Integration**:
- No modifications to SQL files
- Wrappers call existing models via `DbtRunner.execute_command()`
- Model ordering preserved through generator `execution_order` attribute

## Performance Considerations

### Wrapper Overhead

- Single function call indirection: <1ms per generator
- Registry lookup: O(1) dictionary access
- Total overhead for 5 generators: <5ms (negligible vs 60s target)

### Memory Impact

- Registry: ~1KB (5 generators × 200 bytes metadata)
- Generator instances: Stateless, no additional memory per event
- No impact on 100K+ employee scalability

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Determinism regression | Low | High | Parity tests comparing before/after output |
| Performance regression | Low | Medium | Benchmark tests with ≤66s threshold |
| Interface violations | Medium | Low | ABC enforcement + pytest contract tests |
| Registry conflicts | Low | Low | Unique event_type string validation |

## Conclusion

All research items resolved. No NEEDS CLARIFICATION items remain. Ready for Phase 1 design.
