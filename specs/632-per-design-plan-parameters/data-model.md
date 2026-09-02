# Data Model: Per-Design Plan Parameters

## 1. PlanDesignParametersMap

Invocation-scoped configuration mapping each assignable design id to one complete Tier 1 parameter set.

**Fields**

- `design_id: str` — the map key; unique and nonblank.
- `match: MatchParameterSet`
- `employer_core: CoreParameterSet`
- `auto_enrollment: AutoEnrollmentParameterSet`
- `deferral_escalation: EscalationParameterSet`
- `eligibility: EligibilityParameterSet`

**Relationships and rules**

- Its key set equals `PlanDesignAssignmentSettings.design_set()` exactly.
- It is optional only as a whole. Absence means legacy scalar mode; presence means strict keyed mode.
- It does not contain formula-family selectors.
- Serialization is deterministic by sorted design id and schedule ordinal.

## 2. MatchParameterSet

Numeric inputs for the one globally selected match family.

**Fields**

- `cap_percent: Decimal` in `[0, 1]`.
- `tiers: list[MatchTier]` for deferral-based match.
- `graded_schedule`, `tenure_graded_bands`, or `points_tiers` as the typed schedule matching the global family; other family schedules are empty.

**MatchTier fields**

- `employee_min: Decimal`
- `employee_max: Decimal`
- `match_rate: Decimal`
- implicit list order normalized to `tier_ordinal`

**Rules**

- Intervals use `[employee_min, employee_max)` semantics.
- Bounds are ordered and nonoverlapping within a design/band.
- The derived match-maximizing deferral ceiling comes from the same design schedule.

## 3. CoreParameterSet

Numeric inputs for flat or service-graded core contributions.

**Fields**

- `contribution_rate: Decimal` in `[0, 1]`.
- `graded_schedule: list[CoreServiceBand]`.

**CoreServiceBand fields**

- `min_years: int >= 0`
- `max_years: int | None`
- `rate: Decimal` in `[0, 1]`
- implicit list order normalized to `band_ordinal`

**Rules**

- Bands use `[min_years, max_years)` semantics.
- Bands are ordered and nonoverlapping.
- The schedule is populated only when the global core family is service-graded.

## 4. AutoEnrollmentParameterSet

**Fields**

- `default_deferral_rate: Decimal` in `[0, 1]`
- `window_days: int >= 0`
- `scope: Literal['all_eligible_employees', 'new_hires_only']`

**Rules**

- The global auto-enrollment enable flag, assignment cutoff, opt-out grace, and behavioral probabilities remain outside this entity.
- Event dates and default rates are resolved after employee design assignment.

## 5. EscalationParameterSet

**Fields**

- `increment: Decimal` in `[0, 1]`
- `cap: Decimal` in `[0, 1]`

**Rules**

- `increment <= cap`.
- The global enable flag, effective date, hire cutoff, enrollment requirement, and first delay remain outside this entity.
- Event generation, state accumulation, match response, and data-quality checks read the same design values.

## 6. EligibilityParameterSet

**Fields**

- `waiting_period_days: int >= 0`

**Rules**

- This is the only keyed representation of the three existing waiting-day aliases.
- The authoritative eligibility date equals `employee_hire_date + waiting_period_days` for the assigned design, subject to existing calendar semantics.
- All plan-eligibility events, enrollment decisions, and snapshot audit fields use this result.

## 7. Runtime Scalar Parameter Relation

An ephemeral inline relation produced by `get_plan_design_parameters`.

**Grain**: one row per `plan_design_id`.

**Key**: `plan_design_id`.

**Cardinality contract**

- keyed mode: exactly one row for every assigned design;
- empty macro input: zero rows with the full typed schema;
- legacy mode: consumer does not invoke the keyed relation path.

## 8. Runtime Schedule Relations

Inline relations produced by schedule macros.

**Grains**

- match: one row per `(plan_design_id, family, band_ordinal, tier_ordinal)`;
- core: one row per `(plan_design_id, band_ordinal)`.

**Rules**

- All employee joins include `plan_design_id`.
- Every employee resolves no more than one service band and the intended tier set.
- Empty inputs return zero rows with typed schemas.

## 9. Assignment-Aware Plan Eligibility

An employee/year relation built after `int_plan_design_assignment_accumulator`.

**Grain**: `(scenario_id, plan_design_id, employee_id, simulation_year)`.

**Fields**

- canonical employee/design/year identifiers;
- `employee_hire_date`;
- `waiting_period_days`;
- `eligibility_date`;
- existing minimum-age/override results and audit reason fields.

**Relationships**

- many employee eligibility rows join one scalar parameter row by `plan_design_id`;
- enrollment and eligibility event models consume this relation;
- the workforce snapshot carries its resolved audit fields.

## State and mode transitions

There is no parameter state transition over time in Tier 1: a run has one immutable parameter map, and an employee's sticky design assignment selects the same parameter set in every year. Configuration mode is exclusive:

1. `plan_design_parameters` absent → legacy scalar mode;
2. `plan_design_parameters` present and valid → strict keyed mode;
3. partial/mismatched keyed map → configuration validation error before dbt.
