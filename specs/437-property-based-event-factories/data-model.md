# Data Model: Property-Based Event Factory Contracts

**Feature**: 437-property-based-event-factories
**Date**: 2026-08-12

This feature adds test-domain models and contracts only. It does not add a persisted table, alter `SimulationEvent`, or change a public payload schema.

## Existing Domain Entities Under Test

### SimulationEvent

| Field | Native type | JSON-mode type | Rule |
|---|---|---|---|
| `event_id` | `UUID` | string | Generated UUID is preserved by round trip. |
| `employee_id` | `str` | string | Non-empty after trimming; Unicode is allowed. |
| `effective_date` | `date` | ISO date string | Equals the factory-designated payload date. |
| `created_at` | timezone-aware `datetime` | ISO datetime string | Generated value is preserved by round trip. |
| `scenario_id` | `str` | string | Non-empty after trimming. |
| `plan_design_id` | `str` | string | Non-empty after trimming. |
| `source_system` | `str` | string | Fixed by each public factory. |
| `payload` | discriminated Pydantic payload | object | `event_type` selects the exact payload subtype. |
| `correlation_id` | `str | None` | string or null | Factory-created events currently default to null. |

### Numeric Value Families

| Family | Fields in initial scope | Valid domain | Normalized scale |
|---|---|---|---|
| Monetary amount | hire compensation; promotion compensation; merit compensation; contribution amount/YTD; forfeiture amount; HCE YTD/annualized/threshold | Positive or non-negative as declared by each payload | 6 fractional digits |
| Vesting source balance | values in `source_balances_vested` | Sign currently unconstrained; this feature pins type and scale only | 6 fractional digits |
| Rate/percentage | merit percentage; enrollment pre-tax/Roth/after-tax rates; vesting percentage; forfeiture vested percentage | Inclusive `[0, 1]` | 4 fractional digits |

All native values remain `Decimal`. JSON mode represents them as decimal strings, never JSON floating-point numbers.

## New Test-Domain Entities

### EventFactoryCase

A typed immutable descriptor used by shared properties.

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Stable test ID such as `hire` or `hce_status`. |
| `factory` | callable | Public factory method invoked by the property. |
| `arguments` | Hypothesis strategy | Generates a valid keyword-argument mapping. |
| `payload_type` | Pydantic model type | Expected discriminated payload subtype. |
| `event_type` | `str` | Expected payload discriminator value. |
| `source_system` | `str` | Expected fixed envelope source. |
| `effective_date_argument` | `str` | Argument whose value must become the envelope effective date. |
| `payload_keys` | `frozenset[str]` | Exact JSON-mode payload key set. |
| `json_field_types` | mapping | Expected JSON-compatible type family for each payload field. |

### GeneratedEventInput

| Attribute | Type | Validation rule |
|---|---|---|
| `simulation_year` | `int` | Bounded to Python-supported representative simulation years. |
| `arguments` | `dict[str, object]` | Matches one factory signature and uses valid literal choices. |
| `expected_effective_date` | `date` | Lies between January 1 and December 31 of `simulation_year`. |

### InvalidEventInput

| Attribute | Type | Categories |
|---|---|---|
| `case` | `EventFactoryCase` | Factory to call. |
| `arguments` | `dict[str, object]` | Otherwise-valid argument mapping with one invalid field. |
| `invalid_field` | `str` | Employee ID, amount/compensation, or rate. |
| `invalid_category` | enum-like string | Empty, whitespace-only, negative, zero-when-positive-required, below-zero rate, above-one rate, or over-scale where constrained. |

The invalid input is sent through the factory and must transition only to `ValidationError`; it must never produce a `SimulationEvent`. This includes workforce compensation that is positive before normalization but rounds to zero at six places.

### EmployeeLifecyclePair

| Attribute | Type | Rule |
|---|---|---|
| `employee_id` | `str` | Same valid identifier for both events. |
| `simulation_year` | `int` | Shared generated year. |
| `hire_arguments` | mapping | Produces a hire in the shared year. |
| `termination_arguments` | mapping | Produces a termination in the shared year. |
| `hire_date` | `date` | `<= termination_date`. |
| `termination_date` | `date` | `>= hire_date`. |

## Relationships

```text
EventFactoryCase
  ├── generates ──> GeneratedEventInput
  ├── invokes ────> public event factory
  ├── expects ────> SimulationEvent + exact payload subtype
  └── defines ────> SerializationContract

EmployeeLifecyclePair
  ├── invokes ────> WorkforceEventFactory.create_hire_event
  └── invokes ────> WorkforceEventFactory.create_termination_event

InvalidEventInput
  └── invokes public factory ──> ValidationError
```

## Test-State Transitions

### Valid event

```text
generated arguments
  -> factory validation
  -> SimulationEvent
  -> native model_dump
  -> model_validate
  -> equal SimulationEvent
```

### JSON contract

```text
SimulationEvent
  -> model_dump(mode="json")
  -> exact key/type assertions
  -> json.dumps
  -> model_validate
  -> equal SimulationEvent
```

### Invalid event

```text
otherwise-valid arguments + one invalid value
  -> public factory
  -> pydantic.ValidationError
```

## Validation Rules

- Valid strategies construct values directly inside the declared field bounds; they do not use filtering to discard mostly-invalid examples.
- Decimal strategies exclude NaN/infinity and bound magnitude so quantization cannot leak `decimal.InvalidOperation` outside Pydantic's validation boundary.
- Monetary and rate assertions check both `isinstance(value, Decimal)` and the Decimal exponent, because numeric equality alone does not preserve scale.
- Nested vesting balances are checked value-by-value.
- Workforce compensation is valid only when its six-place normalized value remains positive; sub-quantum positives are rejected during initial construction.
- The event's payload type and discriminator must agree with its case descriptor.
- The event effective date must equal its designated factory input and fall within the generated year.
- Top-level key order is not contractual; exact key membership and value types are contractual.
- JSON encoding text formatting and object key order are not contractual.
- No generated test entity is persisted.
