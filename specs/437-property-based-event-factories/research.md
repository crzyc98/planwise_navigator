# Research: Property-Based Event Factory Contracts

**Feature**: 437-property-based-event-factories
**Date**: 2026-08-12

## Decision 1: Test the public factory surface named by the issue

**Decision**: Cover exactly nine initial methods: workforce hire, termination, promotion, and merit; DC-plan enrollment, contribution, and vesting; and administration forfeiture and HCE status. Treat the issue's “raise” terminology as the repository's existing merit factory.

**Rationale**: These methods are the audit-critical starting scope requested by issue 437. Calling factories instead of payload constructors verifies argument mapping, fixed `source_system` values, effective-date selection, discriminated payload construction, and envelope validation together.

**Alternatives considered**:

- Cover all fourteen payload types immediately: rejected because the issue says to start with the CLAUDE.md core list, and broadening would dilute the first contract suite.
- Test payload models only: rejected because it would miss factory mapping defects and top-level identifier validation.

## Decision 2: Use typed factory-case metadata plus specialized strategies

**Decision**: Define reusable Hypothesis strategies and a typed case descriptor in `tests/fixtures/event_factory_strategies.py`. Use the descriptor for common round-trip, effective-date, source-system, and serialization properties; use focused strategies for Decimal fields, invalid categories, and lifecycle pairs.

**Rationale**: A single generic strategy for every behavior would obscure field-specific boundaries, while nine copy-pasted test classes would be difficult to audit. Metadata makes coverage completeness explicit and focused strategies produce useful minimal counterexamples.

**Alternatives considered**:

- One monolithic `@given` test selecting any factory: rejected because 100 examples would not guarantee balanced exercise of all factories and failures would be less local.
- Fully separate properties and argument builders per factory: rejected because the envelope and JSON assertions would be duplicated nine times.

## Decision 3: Generate Decimals directly and assert normalized scale

**Decision**: Use `hypothesis.strategies.decimals` with finite values, bounded magnitude, and explicit `places` for valid domains. Assert native values are exactly `Decimal`, never `float`, and have the documented exponent (`-6` for amounts, `-4` for rates). Include exact zero/one rate boundaries, the smallest accepted positive amount, nested vesting values, and separate invalid strategies. Use exact type checks for booleans and integers because `bool` subclasses `int`.

**Rationale**: Building Decimals from floats can introduce binary artifacts before Pydantic sees the input. Direct Decimal generation tests the actual exact-arithmetic contract and lets Hypothesis shrink toward meaningful numeric boundaries.

The existing schema has two behaviors that tests must not conflate:

- Workforce compensation fields accept positive Decimals and normalize them through `quantize_amount`.
- Fields declaring `decimal_places` constrain acceptable input scale before/alongside normalization. Generated-valid values must respect that input contract, while explicit over-scale examples/properties can pin rejection where it is part of the current schema.
- Vesting `source_balances_vested` values are quantized but currently have no sign constraint. This feature pins their Decimal type and scale without silently adding a non-negative business rule.

**Alternatives considered**:

- Generate Python floats and convert them to Decimal: rejected because it tests float conversion artifacts rather than Decimal discipline.
- Assert numeric equality only: rejected because `Decimal("1.000000") == Decimal("1")` does not protect the scale contract.

## Decision 4: Reject workforce compensation that quantizes to zero

**Decision**: Add a shared positive-amount quantization validator and use it for hire, promotion, and merit compensation. It must quantize to six places and raise a Pydantic-wrapped `ValueError` when the normalized result is not positive. Preserve a minimized example regression for the half-even boundary and property-test sub-quantum positive inputs.

**Rationale**: Current field ordering checks `gt=0` before the after-validator quantizes. For example, `Decimal("0.0000001")` constructs an event whose compensation is `Decimal("0.000000")`; dumping and revalidating that event then fails `gt=0`. The factory has therefore produced an event outside its own schema. Rejecting at initial construction restores closure under serialization without changing stored precision.

**Alternatives considered**:

- Restrict the generated-valid strategy to six-place inputs and leave the defect: rejected because malformed Decimal precision is a named issue-437 edge case and the failure is already reproduced.
- Raise the stored precision or preserve arbitrary input scale: rejected because the six-place `(18,6)` contract is established by the shared validators and serialization contract.
- Add three independent checks in workforce payloads: rejected in favor of a small shared validator that keeps the rule consistent.

## Decision 5: Model temporal context in composite strategies

**Decision**: Generate a simulation year and derive dates from that year's first and last day. Build composite lifecycle inputs that produce a hire date and a termination date with `hire_date <= termination_date`, including same-day events and leap years. Assert each factory maps its designated payload date to `SimulationEvent.effective_date`.

**Rationale**: `SimulationEvent` and the factories do not accept `simulation_year`, and the termination factory does not accept `hire_date`. The honest property is therefore about mapping valid contextual inputs, not cross-record validation that the API cannot perform.

No additional date ordering is inferred: the current schemas do not enforce final-pay, contribution/pay-period, or vesting service-date relationships.

**Alternatives considered**:

- Add `simulation_year` or `hire_date` parameters to factories: rejected as an unrequested public API and event contract change.
- Claim that an individual termination event can reject pre-hire dates: rejected because the required prior event state is unavailable at construction time.

## Decision 6: Pin native and JSON serialization as distinct contracts

**Decision**: Use `model_dump()` for the Python round trip and `model_dump(mode="json")` for the wire contract. Native dumps must retain UUID/date/datetime/Decimal objects. JSON-mode dumps must have exact envelope and per-payload key sets, encode via `json.dumps`, represent UUIDs/dates/datetimes/Decimals as strings, and validate back to an equal event.

**Rationale**: The two modes serve different consumers. Native equality protects Pydantic reconstruction; JSON-mode key/type checks catch schema drift relevant to serialized ingestion. A representative current event confirms Pydantic 2.7.4 emits Decimal values as strings and UTC datetimes as ISO-8601 strings.

**Alternatives considered**:

- Snapshot entire JSON strings: rejected because generated UUIDs and timestamps make snapshots noisy, and ordering/text formatting is not the semantic contract.
- Check only that `json.dumps` succeeds: rejected because renamed keys or string-to-number changes could still encode successfully.

## Decision 7: Require validation exceptions at the factory boundary

**Decision**: Invalid properties call public factories and assert `pydantic.ValidationError`. Do not assert complete error messages.

**Rationale**: This proves malformed events are not constructed silently while avoiding coupling to Pydantic's version-specific wording. Existing models already reject the issue's exemplar inputs; the property suite broadens the domain around those examples.

**Alternatives considered**:

- Assert `ValueError`: rejected because callers rely on Pydantic's aggregated `ValidationError` boundary.
- Match full error strings: rejected because message wording is not the ingestion contract and is brittle across compatible Pydantic updates.

## Decision 8: Keep Hypothesis bounded and local

**Decision**: Apply explicit module-local settings with `max_examples=100`, `deadline=None`, and deterministic generation; retain normal shrinking phases and do not suppress health checks preemptively. Use constructive composite strategies rather than rejection-heavy filters. Parameterize over the nine factory descriptors and draw each descriptor's strategy so every factory receives a named 100-example run. Keep all tests pure and place the property module under `tests/unit/events/` so marker automation applies `unit`, `fast`, and `events`.

**Rationale**: One hundred examples matches the issue's CI cap while still exploring boundaries and shrinking failures. Pydantic construction is CPU-only; disabling per-example deadlines avoids machine-speed flakiness without permitting unbounded example counts.

**Alternatives considered**:

- Register a global Hypothesis profile: rejected because it could change existing high-example property tests such as IRS 402(g) coverage.
- Depend on Hypothesis defaults: rejected because default settings may change and would not encode the CI budget requested by the issue.
- Select a factory from one `one_of` strategy: rejected because 100 examples would be distributed unevenly and would not guarantee full exercise of each factory.

## Decision 9: Move Hypothesis out of runtime dependencies

**Decision**: Remove `hypothesis>=6.0.0` from `[project].dependencies` and `requirements.txt`; add it to `[project.optional-dependencies].dev` and `requirements-dev.txt`; refresh `uv.lock` while preserving the currently resolved version where possible.

**Rationale**: Hypothesis is used only by tests. The repository currently installs it in production despite the issue explicitly requiring a dev extra. Both packaging paths must agree.

**Alternatives considered**:

- Add a second copy to the dev extra but retain runtime declarations: rejected because runtime installations would still include a testing-only package.
- Pin exactly 6.155.1 in source metadata: rejected because the repository currently uses a compatible lower bound and the lockfile already provides reproducibility.

## Baseline Findings

- Existing event unit suite: 68 tests pass in 1.02 seconds before implementation.
- Existing tests include one example round trip for DC plan events and one for administration events, but no generated factory-wide contract.
- Unicode top-level identifiers are accepted and surrounding whitespace is trimmed by `SimulationEvent` validators.
- A representative JSON-mode hire event uses strings for UUID/date/datetime/Decimal values, JSON booleans for booleans, JSON numbers for integers, and `null` for optional `None` values.
- No database fixture or isolated DuckDB run is needed because the proposed tests construct and serialize Pydantic models only.
- The repository-wide `fast` suite is documented by current CI as roughly four minutes for about 2,180 tests, despite the constitution retaining a historical `<10s` target. This inherited drift is not caused by issue 437; implementation must measure targeted incremental runtime and keep each new property capped at 100 examples.
- `uv.lock` currently records project version 2.2.0 while `pyproject.toml` declares 2.4.0. A normal `uv lock` refresh may correct that pre-existing metadata as well as moving Hypothesis into the `dev` extra; the lockfile must not be hand-edited selectively.

## Clarifications Resolved

No `NEEDS CLARIFICATION` items remain. Scope, raise/merit terminology, simulation-year semantics, lifecycle ordering, serialization mode, dependency placement, and performance settings are resolved above.
