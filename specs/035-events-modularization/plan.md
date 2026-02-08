# Implementation Plan: Events Module Modularization

**Branch**: `035-events-modularization` | **Date**: 2026-02-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/035-events-modularization/spec.md`

## Summary

Modularize the 1,056-line `config/events.py` into domain-specific submodules (`workforce.py`, `dc_plan.py`, `admin.py`) with shared validators (`validators.py`) and a backward-compatible re-export layer. This reduces merge conflicts, improves navigation, and eliminates 15+ duplicated validator functions.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2.7.4 (existing)
**Storage**: N/A (pure Python refactoring, no database changes)
**Testing**: pytest with existing test infrastructure (256 tests)
**Target Platform**: Linux server (existing deployment)
**Project Type**: Single (Python package refactoring)
**Performance Goals**: No runtime degradation from import indirection
**Constraints**: 100% backward compatibility for `from config.events import *`
**Scale/Scope**: 1,056 lines → 5 modules (~200 lines each)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | PASS | No changes to event storage or behavior |
| II. Modular Architecture | PASS | Splitting 1,056-line file into ~200-line modules (well under 600-line limit) |
| III. Test-First Development | PASS | Will add validator tests; existing tests unchanged |
| IV. Enterprise Transparency | PASS | No changes to logging or audit behavior |
| V. Type-Safe Configuration | PASS | Pydantic v2 models preserved; validators remain type-safe |
| VI. Performance & Scalability | PASS | Import indirection has negligible overhead |

**Gate Result**: PASS - All principles satisfied.

## Project Structure

### Documentation (this feature)

```text
specs/035-events-modularization/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
config/
├── __init__.py          # Existing (unchanged)
├── events.py            # Compatibility layer (re-exports all symbols)
├── events/              # NEW: Package directory
│   ├── __init__.py      # Re-exports from submodules
│   ├── validators.py    # Shared Decimal quantization helpers
│   ├── workforce.py     # HirePayload, PromotionPayload, TerminationPayload, MeritPayload, SabbaticalPayload
│   ├── dc_plan.py       # EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload, AutoEnrollmentWindowPayload, EnrollmentChangePayload
│   ├── admin.py         # ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload
│   └── core.py          # SimulationEvent, EventFactory, WorkforceEventFactory, DCPlanEventFactory, PlanAdministrationEventFactory
├── erisa_compliance.py  # Existing (unchanged)
├── network_config.py    # Existing (unchanged)
└── schema.py            # Existing (unchanged)

tests/
├── unit/
│   ├── events/          # Existing tests (unchanged imports)
│   │   ├── test_simulation_event.py
│   │   ├── test_dc_plan_events.py
│   │   └── test_plan_administration_events.py
│   └── test_validators.py  # NEW: Shared validator tests
└── ...
```

**Structure Decision**: Python allows both `config/events.py` (file) and `config/events/` (package) to coexist. The file takes precedence for imports, serving as the compatibility layer that re-exports from the package.

## Complexity Tracking

> No violations - all modules will be well under 600 lines.

| Module | Estimated Lines | Content |
|--------|-----------------|---------|
| `validators.py` | ~40 | 3 quantization functions |
| `workforce.py` | ~120 | 5 payload classes |
| `dc_plan.py` | ~220 | 6 payload classes |
| `admin.py` | ~100 | 3 payload classes |
| `core.py` | ~400 | SimulationEvent + 4 factory classes |
| `events.py` (compat) | ~60 | Re-exports + `__all__` |

## Implementation Approach

### Phase 1: Validators Module
1. Create `config/events/validators.py` with shared functions
2. Add unit tests for validators
3. Verify existing behavior preserved

### Phase 2: Domain Payloads
1. Create `config/events/workforce.py` (5 payloads)
2. Create `config/events/dc_plan.py` (6 payloads)
3. Create `config/events/admin.py` (3 payloads)
4. Each imports validators and uses shared quantization

### Phase 3: Core Module
1. Create `config/events/core.py` (SimulationEvent + factories)
2. Import all payloads from domain modules
3. Preserve discriminated union in SimulationEvent

### Phase 4: Compatibility Layer
1. Update `config/events.py` to re-export all symbols
2. Preserve identical `__all__` list
3. Run full test suite to verify backward compatibility

### Phase 5: Validation
1. Run all 256+ tests
2. Verify no import changes needed in consumers
3. Verify each module < 300 lines

## Constitution Check (Post-Design Re-check)

*Re-checked after Phase 1 design completion.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | PASS | No changes to SimulationEvent behavior or event storage |
| II. Modular Architecture | PASS | validators.py (~40), workforce.py (~120), dc_plan.py (~220), admin.py (~100), core.py (~400) - all under 600 lines |
| III. Test-First Development | PASS | New test_validators.py covers shared validators; existing 256+ tests unchanged |
| IV. Enterprise Transparency | PASS | No changes to logging, audit trails, or error handling |
| V. Type-Safe Configuration | PASS | All Pydantic models preserved; quantize_amount/rate are type-safe |
| VI. Performance & Scalability | PASS | Import indirection adds ~1ms startup; negligible for batch simulations |

**Post-Design Gate Result**: PASS - Design aligns with all constitutional principles.
