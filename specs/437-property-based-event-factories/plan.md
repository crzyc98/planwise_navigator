# Implementation Plan: Property-Based Event Factory Contracts

**Branch**: `437-property-based-event-factories` | **Date**: 2026-08-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/437-property-based-event-factories/spec.md`

## Summary

Add bounded Hypothesis properties around the nine audit-critical public factory methods named in issue 437. Shared strategies and factory metadata will generate valid, boundary, and invalid inputs; properties will pin native Pydantic round trips, Decimal type/scale discipline, effective-date mapping and contextual lifecycle ordering, `ValidationError` rejection, and exact JSON-mode keys/types. A property-oriented probe already exposed one closure defect: positive workforce compensation can quantize to zero and produce an event that fails its own revalidation. The implementation therefore includes a minimal shared positive-amount quantizer for hire, promotion, and merit compensation, plus a focused regression. Hypothesis moves from production dependencies to the `dev` extra with requirements and lock metadata refreshed consistently.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic 2.7.4; Hypothesis 6.155.1 currently resolved from `hypothesis>=6.0.0` (development only after implementation)
**Storage**: N/A
**Testing**: pytest 7.4.0 with Hypothesis; repository `unit`, `fast`, and `events` marker automation
**Target Platform**: Local developer environments and Linux CI supported by the existing Python package
**Project Type**: Python domain package with a unit-test suite
**Performance Goals**: At most 100 generated examples per property; measure and minimize incremental runtime in the targeted event suite
**Constraints**: No network or database I/O; no float-based input generation; exact event key/type compatibility; preserve example tests; retain default Hypothesis shrinking; avoid global settings that affect existing 5,000–10,000-example properties
**Scale/Scope**: Nine public factory methods across three factories; one shared Decimal validator correction; two new test-support modules; four dependency metadata files

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

| Principle | Pre-design gate | Post-design evidence |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | Round-trip and wire-contract properties protect UUIDs, timestamps, context, payloads, and values without mutating event-store data. The model is not described as technically frozen; immutability remains the event-store policy. |
| II. Modular Architecture | PASS | Reusable strategies/case metadata live in test fixtures, assertions live in event unit tests, and the positive amount rule is one shared validator rather than three divergent checks. |
| III. Test-First Development | PASS with inherited performance drift noted | The failing sub-quantum case is captured before the validator fix; all properties are auto-marked `unit`/`fast`/`events` and capped at 100. Current CI documents the full fast suite at about four minutes, so implementation measures bounded incremental cost instead of claiming the historical `<10s` gate already holds. |
| IV. Enterprise Transparency | PASS | Exact JSON keys and types make audit-boundary changes explicit and reviewable. |
| V. Type-Safe Configuration | PASS | Tests exercise public Pydantic v2 factories, require malformed values to surface as `ValidationError`, and ensure accepted normalized values remain schema-valid. |
| VI. Performance & Scalability | PASS | Pure in-memory model construction, constructive strategies, bounded examples, and no runtime use of Hypothesis keep production and CI impact controlled. |

No feature-introduced constitution violation requires a complexity exception. The pre-existing fast-suite duration divergence is documented and measured, not expanded into this issue's scope.

## Project Structure

### Documentation (this feature)

```text
specs/437-property-based-event-factories/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── event-serialization.md
```

### Source Code (repository root)

```text
planalign_core/events/
├── core.py                         # Existing public factories/envelope
├── workforce.py                    # Apply shared positive-amount quantizer to hire/promotion/merit compensation
├── dc_plan.py                      # Existing DC-plan payload validation (unchanged unless a property proves otherwise)
├── admin.py                        # Existing administration payload validation (unchanged unless a property proves otherwise)
└── validators.py                   # Add shared six-place positive-amount quantizer

tests/
├── fixtures/
│   └── event_factory_strategies.py # Shared Hypothesis strategies and factory-case metadata
└── unit/events/
    ├── test_simulation_event.py    # Existing examples retained
    ├── test_dc_plan_events.py      # Existing examples retained
    ├── test_plan_administration_events.py # Existing examples retained
    └── test_event_factory_properties.py   # New validity, Decimal, date, rejection, and serialization properties

pyproject.toml                      # Move Hypothesis from runtime dependencies into the dev extra
requirements.txt                   # Remove Hypothesis from runtime requirements
requirements-dev.txt               # Add Hypothesis to development requirements
uv.lock                            # Refresh project/dependency metadata through uv, not manual edits
```

**Structure Decision**: Centralize generated inputs and exact contracts in one reusable test-fixture module. The property module consumes typed per-factory metadata so every one of the nine factories receives its own generated run while common envelope assertions stay deduplicated. Production changes remain limited to the already-reproduced workforce compensation closure defect.

## Implementation Sequence

1. Preserve the minimized sub-quantum workforce compensation counterexample as a failing example test: a positive value that half-even quantization turns into `0.000000` must raise `ValidationError` during initial hire, promotion, and merit construction.
2. Add a shared positive-amount quantization helper in `planalign_core/events/validators.py` and apply it to all three workforce compensation validators. Quantize to six places, reject a normalized value `<= 0`, and keep the exception inside Pydantic's `ValidationError` boundary.
3. Reclassify Hypothesis in `pyproject.toml`, `requirements.txt`, and `requirements-dev.txt`, then run `uv lock` rather than hand-editing the lockfile. Review the expected pre-existing editable-project version refresh from 2.2.0 to 2.4.0 as part of the lock diff.
4. Add `tests/fixtures/event_factory_strategies.py` with bounded readable Unicode identifiers, exact finite Decimals, simulation-year dates, lifecycle pairs, and one typed descriptor per in-scope factory. Avoid `.filter()` and rejection-heavy `assume()`; exclude extreme Decimal magnitudes that could leak `decimal.InvalidOperation`.
5. Add validity/mapping properties parameterized by factory descriptor, drawing each descriptor's strategy independently so every factory receives up to 100 examples. Compare complete `SimulationEvent` equality after native dump/revalidation and assert payload subtype, source system, and effective-date mapping.
6. Add Decimal properties by schema family: six-place amounts, four-place rates, nested vesting balance scale without adding a sign rule, inclusive rate boundaries, accepted overprecision behavior where supported, constrained over-scale rejection, exact `Decimal` output types, and no float conversion.
7. Add temporal properties for January 1, December 31, leap day, and generated hire/termination pairs. Do not infer unimplemented final-pay, pay-period/contribution, or vesting service-date ordering rules.
8. Add invalid-input properties through public factories for negative/zero-when-positive amounts, sub-quantum workforce compensation, out-of-range rates, and empty/whitespace-only employee IDs; require `pydantic.ValidationError` without matching version-specific messages.
9. Add JSON-mode contract properties using [contracts/event-serialization.md](contracts/event-serialization.md): exact envelope/payload key sets, exact primitive types (`type(value) is bool/int` where relevant), standard JSON encode/decode, and `SimulationEvent.model_validate` equality. Do not exclude defaults or `None` fields.
10. Run the targeted property module with Hypothesis statistics, the full event unit selection, the repository fast suite for incremental timing, focused Ruff/Black checks, dependency-placement searches, and `uv lock --check`. No isolated DuckDB run is required unless implementation unexpectedly expands beyond Pydantic event behavior.

## Complexity Tracking

No feature-introduced constitution violations or additional architectural complexity are planned.
