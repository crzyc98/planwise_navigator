# Research: Age-Banded Employer Core Contributions

## Decision: Use a plan-owned age schedule, not shared reporting age bands

**Rationale**: The plan-design schedule must represent document-specific boundaries. The existing `config_age_bands.csv` serves reporting and hazard-model grouping and would couple unrelated concerns. `snapshot_flags` already provides annual `current_age` to the core contribution model, so the feature requires neither a new join nor an accumulator.

**Alternatives considered**:

- Reusing reporting age-band seeds — rejected because a reporting-band change could silently reprice plan benefits.
- Deriving age bands from points tiers — rejected because tenure would contaminate an age-only plan design.

## Decision: Preserve decimal configuration rates and convert to macro percentages in both export paths

**Rationale**: Existing direct YAML schedules carry `contribution_rate` as a decimal and Studio payload schedules normalize visible percentages to decimals. Existing core service and points exports convert those decimals to percentage-valued dbt vars, and their macros divide by 100. The new `employer_core_age_schedule` follows this established boundary to avoid a 100× pricing error.

**Alternatives considered**:

- Changing macros to receive decimal rates — rejected because it would change established macro conventions and risk existing modes.
- Letting Studio send visible percentages to the exporter — rejected because it would diverge from other schedule payloads.

## Decision: Add load-time Pydantic validation for the age schedule

**Rationale**: `SimulationConfig` currently permits untyped core and `dc_plan` extras, which allows malformed schedules to reach SQL. A focused core age-tier model and schedule validator gives clear errors before simulation. A nonempty age-banded schedule must start at zero, be contiguous, contain no overlap or reversed finite range, and end in an unbounded tier; an empty schedule remains valid and selects the flat-rate fallback.

**Alternatives considered**:

- UI warnings only — rejected because direct YAML and API-originated config could bypass them.
- SQL compilation/runtime validation — rejected because gaps could silently apply the fallback rate after a costly run starts.

## Decision: Explicitly test both tier bounds in the new macro

**Rationale**: The existing service and points macros infer upper bounds from descending minimums. The age schedule contract includes `min_age` and `max_age`, so the new macro will generate `min_age <= current_age AND (max_age IS NULL OR current_age < max_age)`, sorted by descending lower boundary. This makes `[min, max)` behavior explicit and ensures an exact boundary belongs to the next tier.

**Alternatives considered**:

- Reusing `get_tiered_core_rate` — rejected because it ignores maximum boundaries and cannot detect/configure age-specific fields.

## Decision: Render the resolved core rate once and reuse it

**Rationale**: `int_employer_core_contributions.sql` currently has independent rate-selection chains for amount and audit rate. A single `core_rate_expr` used at both call sites ensures the audit value describes the dollars for all four modes and minimizes regression risk.

**Alternatives considered**:

- Add an age branch to each chain — rejected because the chains can drift again.
- Add a persisted rate table — rejected because it adds storage and lifecycle complexity without providing new business value.

## Decision: Treat `current_age` as the annual rate determination

**Rationale**: `current_age` in `int_workforce_state_accumulator` is the existing point-in-time annual value. The rate is selected once for each employee-year; the compensation basis is still prorated for a mid-year hire, but the rate is not prorated across a birthday.

**Alternatives considered**:

- Birthday-level blended rates — rejected as out of scope and incompatible with the stated administration convention.

## Decision: Reuse the existing 401(a)(4) caveat transport, with generic Studio copy

**Rationale**: `Section401a4ScenarioResult` already carries a risk flag and detail to the Studio. For age-banded mode, set that existing caveat surface even when the numerical result passes, and update the Studio warning language so it accurately covers both service-risk and age-banded review. Ensure the caveat also applies to successful early-return cases (such as no HCE/NHCE), not only normal ratio/general results.

**Alternatives considered**:

- New API fields for age risk — deferred because the feature only needs the existing caveat surface and adding fields would expand the public API.
- A new age-weighted nondiscrimination test — explicitly out of scope; this feature must not claim qualification.
