# Feature Specification: Property-Based Event Factory Contracts

**Feature Branch**: `437-property-based-event-factories`
**Created**: 2026-08-12
**Status**: Draft
**Input**: User description: "Add Hypothesis property tests over the core workforce, DC plan, and plan-administration event factories to cover round trips, Decimal precision, date boundaries and ordering, invalid-input rejection, and stable JSON serialization."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trust Valid Event Construction (Priority: P1)

As a simulation developer, I want broad generated coverage of valid event-factory inputs so that I can change event models without silently breaking the audit trail.

**Why this priority**: The event factories create the typed records at the foundation of auditability. A valid event that cannot round-trip or changes its values is an immediate integrity defect.

**Independent Test**: Run the property test module and verify that generated valid inputs for every in-scope factory produce a `SimulationEvent` whose native dump validates back to an equal event.

**Acceptance Scenarios**:

1. **Given** generated valid inputs for an in-scope event factory, **When** the event is dumped with `model_dump()` and rebuilt with `SimulationEvent.model_validate()`, **Then** the rebuilt event equals the original event, including its UUID, timestamp, context, effective date, payload subtype, and payload values.
2. **Given** valid identifiers containing non-ASCII characters, **When** a factory creates an event, **Then** the identifiers remain Unicode strings and their non-whitespace content is preserved through the round trip.
3. **Given** leading or trailing whitespace around a non-empty top-level identifier, **When** a factory creates an event, **Then** the existing normalization behavior remains stable through the round trip.

---

### User Story 2 - Protect Numeric and Temporal Boundaries (Priority: P1)

As an audit consumer, I want monetary amounts, rates, and event dates to retain their defined types, scales, bounds, and ordering so that event payloads remain exact and temporally credible.

**Why this priority**: Float coercion, uncontrolled scale, or incorrect dates can corrupt downstream balances and employee histories while still producing syntactically valid records.

**Independent Test**: Run the Decimal and date property groups and verify generated boundary values remain `Decimal`, normalize to the documented scale, stay within allowed bounds, and map to the intended effective dates.

**Acceptance Scenarios**:

1. **Given** valid monetary inputs, including values at supported precision boundaries, **When** an event is created, **Then** every monetary payload value is a `Decimal` normalized to six fractional digits and is never a `float`.
2. **Given** valid rate inputs at and between zero and one, **When** an event is created, **Then** every rate payload value is a `Decimal` normalized to four fractional digits and remains within the inclusive range `[0, 1]`.
3. **Given** a generated simulation year and valid dates for an event, **When** a factory creates the event, **Then** the event effective date is the factory's designated payload date and lies within that generated year.
4. **Given** a generated employee lifecycle containing both hire and termination events, **When** both factories create the events, **Then** the hire date is no later than the termination effective date.

---

### User Story 3 - Reject Malformed Inputs and Freeze Serialization (Priority: P1)

As a maintainer of the DuckDB ingestion boundary, I want malformed factory inputs rejected consistently and JSON payload shapes pinned so that invalid or contract-breaking events cannot enter the audit trail unnoticed.

**Why this priority**: Silent construction from invalid values and unreviewed serialization changes both undermine the event store's role as an immutable contract.

**Independent Test**: Run the rejection and JSON contract property groups and verify invalid generated inputs raise `pydantic.ValidationError`, while valid JSON-mode dumps match the documented keys and JSON-compatible types for each in-scope event.

**Acceptance Scenarios**:

1. **Given** negative or otherwise disallowed compensation and amount values, **When** the relevant factory is called, **Then** construction raises `ValidationError`.
2. **Given** a rate below zero or above one, **When** the relevant factory is called, **Then** construction raises `ValidationError`.
3. **Given** an empty or whitespace-only employee identifier, **When** any in-scope factory is called, **Then** construction raises `ValidationError`.
4. **Given** a valid in-scope event, **When** it is dumped in JSON mode, **Then** the top-level and payload keys exactly match the documented contract and every value has the documented JSON-compatible type.
5. **Given** a JSON-mode dump, **When** it is encoded with the standard JSON encoder and validated back into `SimulationEvent`, **Then** encoding succeeds and the reconstructed event equals the original event.

### Edge Cases

- Monetary and rate values at zero where allowed, the smallest supported positive unit, maximum configured scale, and values immediately outside allowed bounds.
- Decimal values with trailing zeros, more precision than the normalized workforce compensation fields accept, and values that would expose accidental binary-float conversion.
- Leap-day and first/last-day-of-year effective dates.
- Same-day hire and termination, which is valid because the lifecycle invariant is non-strict (`hire_date <= termination_date`).
- Empty strings, whitespace-only strings, non-ASCII identifiers, combining characters, and identifier text with surrounding whitespace.
- Optional fields represented as `None`/JSON `null`, including `plan_id`, `correlation_id`, and `prior_year_hce`.
- Empty vesting balance mappings and all supported vesting source keys; generated balances must remain non-float Decimals.
- Generated invalid values must reach the public factory methods rather than testing payload classes alone.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The test suite MUST use Hypothesis to generate valid and invalid inputs for the public event factory methods.
- **FR-002**: Initial coverage MUST include `create_hire_event`, `create_termination_event`, `create_promotion_event`, `create_merit_event` (the codebase's raise-equivalent factory), `create_enrollment_event`, `create_contribution_event`, `create_vesting_event`, `create_forfeiture_event`, and `create_hce_status_event`.
- **FR-003**: Every in-scope factory MUST have a generated-valid round-trip property proving `model_dump()` followed by `SimulationEvent.model_validate()` yields an event equal to the original.
- **FR-004**: Decimal properties MUST prove that native model values remain `Decimal`, monetary values use six fractional digits, rates use four fractional digits, and no tested Decimal field becomes a `float`; vesting source-balance values are scale-checked without introducing a new sign constraint.
- **FR-005**: Rate generators and assertions MUST cover the inclusive valid bounds `[0, 1]` and invalid values outside that range for every in-scope rate-bearing event.
- **FR-006**: Date properties MUST cover the first and last day of a generated simulation year, leap-day where applicable, factory-specific effective-date mapping, and generated hire/termination lifecycle ordering.
- **FR-007**: Rejection properties MUST call public factories and assert `pydantic.ValidationError` for invalid compensation or amount values, invalid rates, and empty or whitespace-only employee identifiers.
- **FR-008**: Serialization properties MUST use `model_dump(mode="json")`, assert exact top-level and per-payload key sets, assert JSON-compatible value types, and prove standard JSON encoding plus model revalidation succeeds.
- **FR-009**: Serialization assertions MUST codify UUIDs, dates, datetimes, and Decimals as JSON strings; booleans as JSON booleans; integers as JSON numbers; optional missing values as JSON `null`; and nested payloads/mappings as JSON objects.
- **FR-010**: Property tests MUST be located under `tests/unit/events/` so repository marker automation marks them `unit`, `fast`, and `events`.
- **FR-011**: Each property MUST run no more than 100 generated examples by default, avoid database or network I/O, and fit the existing fast TDD loop.
- **FR-012**: Hypothesis MUST be declared as a development dependency, not a production runtime dependency, consistently across `pyproject.toml`, requirements files, and the lockfile.
- **FR-013**: Existing example-based event tests MUST remain in place for readable examples and targeted regression messages; property tests supplement rather than replace them.
- **FR-014**: Workforce compensation validation MUST reject positive inputs that quantize to `0.000000`, preventing creation of hire, promotion, or merit events that cannot pass their own dump/revalidation contract; the fix MUST be shared, minimal, and accompanied by a focused regression example.

### Key Entities

- **SimulationEvent**: The Pydantic v2 event envelope containing audit identity fields, scenario context, an effective date, and a discriminated payload; immutability is an event-store usage policy rather than a frozen-model guarantee.
- **Event Factory Case**: Test metadata describing one public factory, its valid-input strategy, expected payload subtype, source system, designated effective-date field, Decimal fields, and serialization key contract.
- **Generated Event Input**: A valid or deliberately invalid argument set supplied to a public factory.
- **Serialization Contract**: Exact JSON-mode top-level and payload keys plus the JSON-compatible type expected for each field.
- **Employee Lifecycle Pair**: Generated hire and termination inputs for the same employee and simulation year with non-decreasing effective dates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All nine initial factory methods pass generated-valid round-trip coverage with up to 100 examples per property and no flaky failures across repeated local runs.
- **SC-002**: Tests detect replacement of any covered `Decimal` with a `float`, a scale change from six monetary/four rate places, acceptance of a covered rate outside `[0, 1]`, or acceptance of workforce compensation that normalizes to zero.
- **SC-003**: Tests detect any addition, removal, rename, or JSON type change in the covered event envelope or payload contracts.
- **SC-004**: Invalid generated compensation, amount, rate, and employee-ID inputs consistently raise `ValidationError` through the public factories.
- **SC-005**: The new property test module is collected by `pytest -m "fast and events"` and completes within the repository's fast-test budget without database access.
- **SC-006**: Installing the project without development extras no longer installs Hypothesis, while installing `.[dev]` provides the version resolved in the project lockfile.
- **SC-007**: Hire, promotion, and merit events created from accepted compensation inputs always survive native and JSON dump/revalidation; sub-quantum positive compensation raises `ValidationError` at construction.

## Assumptions

- The issue's term "raise" refers to the existing merit factory and payload (`create_merit_event` / `MeritPayload`); no new event type is introduced.
- "Within the simulation year" is a generated test-context property because the factory APIs do not accept a simulation-year argument; this feature does not add one.
- Hire-to-termination ordering is verified over a generated pair of factory calls because a termination factory call does not receive `hire_date`; this feature does not introduce cross-event state into individual payload validation.
- Native `model_dump()` is the exact Python round-trip contract, while `model_dump(mode="json")` is the guarded JSON/audit-ingestion contract; this feature does not assert a direct factory-to-DuckDB adapter.
- The initial scope excludes eligibility, auto-enrollment-window, enrollment-change, compliance, and sabbatical events; their later adoption can reuse the strategy and contract helpers created here.
