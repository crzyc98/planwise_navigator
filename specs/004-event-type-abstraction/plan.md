# Implementation Plan: Event Type Abstraction Layer

**Branch**: `004-event-type-abstraction` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-event-type-abstraction/spec.md`

## Summary

Create an event type abstraction layer that enables adding new workforce event types by implementing a single interface and registering in one location (`config/events.py`). The implementation wraps existing dbt SQL models with interface adapters to preserve backward compatibility while enabling gradual adoption for new event types. Key deliverables include the `EventGenerator` base interface, `HazardBasedEventGenerator` for hazard-based events, and a centralized `EventRegistry`.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2 (validation), dbt-core 1.8.8 (SQL transforms), Polars 1.0+ (high-performance mode)
**Storage**: DuckDB 1.0.0 (immutable event store at `dbt/simulation.duckdb`)
**Testing**: pytest with fixtures from `tests/fixtures/`, dbt tests for SQL validation
**Target Platform**: Linux server / macOS workstation (on-premises deployment)
**Project Type**: Single project with modular packages
**Performance Goals**: ≤66s for 5k employees × 5 years in Polars mode (10% margin over current 60s target)
**Constraints**: Single-threaded dbt execution by default, <600 lines per module, no circular dependencies
**Scale/Scope**: 100K+ employee records, 5 existing event types to wrap, interface for unlimited new types

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Event Sourcing & Immutability** | ✅ PASS | New events use existing UUID/timestamp pattern; stored in `fct_yearly_events` |
| **II. Modular Architecture** | ✅ PASS | Abstraction adds ~400 lines in new module; no monolith growth |
| **III. Test-First Development** | ✅ PASS | Interface contract tests + parity tests for wrapper validation |
| **IV. Enterprise Transparency** | ✅ PASS | FR-011 requires structured logging with counts, timing, metadata |
| **V. Type-Safe Configuration** | ✅ PASS | Pydantic v2 discriminated unions for all payloads; registry uses typed config |
| **VI. Performance & Scalability** | ✅ PASS | Wrapper pattern adds negligible overhead; Polars mode preserved |

**Gate Status**: PASSED - No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/004-event-type-abstraction/
├── plan.md              # This file
├── research.md          # Phase 0 output - design patterns and integration points
├── data-model.md        # Phase 1 output - entity definitions
├── quickstart.md        # Phase 1 output - developer guide for adding events
├── contracts/           # Phase 1 output - interface contracts
│   └── event_generator.py  # Abstract base class definitions
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
config/
├── events.py            # MODIFY: Add EventRegistry, extend with interface base classes
└── __init__.py          # Export new types

planalign_orchestrator/
├── generators/          # NEW: Event generator implementations
│   ├── __init__.py
│   ├── base.py          # EventGenerator, HazardBasedEventGenerator interfaces
│   ├── hire.py          # HireEventGenerator (wrapper for int_hiring_events.sql)
│   ├── termination.py   # TerminationEventGenerator (wrapper)
│   ├── promotion.py     # PromotionEventGenerator (wrapper)
│   ├── merit.py         # MeritEventGenerator (wrapper)
│   └── enrollment.py    # EnrollmentEventGenerator (wrapper)
├── pipeline/
│   └── event_generation_executor.py  # MODIFY: Use registry for event dispatch
└── polars_event_factory.py           # MODIFY: Integrate with generator interface

tests/
├── unit/
│   └── test_event_generators.py      # NEW: Interface contract tests
├── integration/
│   └── test_event_parity.py          # NEW: Before/after output comparison
└── fixtures/
    └── generators.py                  # NEW: Mock generators for testing
```

**Structure Decision**: Single project structure maintained. New `generators/` package follows existing modular pattern (parallel to `pipeline/`). Each generator wrapper is <200 lines, totaling ~400-500 lines for the complete abstraction layer.

## Complexity Tracking

> No violations - table not required.

## Phase 0: Research Summary

See [research.md](./research.md) for complete findings.

**Key Decisions**:
1. **Interface Pattern**: Abstract Base Class (ABC) with `@abstractmethod` for required methods
2. **Registry Pattern**: Dictionary-based with decorator registration (`@register_event_type`)
3. **Wrapper Strategy**: Thin adapters that call existing dbt models via `DbtRunner`
4. **Hazard Integration**: Mixin class providing band lookup and RNG infrastructure

## Phase 1: Design Artifacts

- [data-model.md](./data-model.md) - Entity and relationship definitions
- [contracts/event_generator.py](./contracts/event_generator.py) - Interface contracts
- [quickstart.md](./quickstart.md) - Developer guide for adding new event types
