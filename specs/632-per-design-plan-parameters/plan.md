# Implementation Plan: Per-Design Plan Parameters

**Branch**: `632-per-design-plan-parameters` (planning target; artifacts created on current `main`) | **Date**: 2026-09-01 | **Spec**: [spec.md](spec.md)
**Input**: GitHub issue #632 and the feature specification in `specs/632-per-design-plan-parameters/spec.md`

## Summary

Generalize the existing inline-relation pattern so employees with sticky `plan_design_id` assignments can use different numeric plan terms while sharing one compile-time formula family. Add a strict typed parameter map, export deterministic keyed data, render one scalar and narrow schedule relations, and join them by employee design in every affected calculator and event model. Preserve the current scalar SQL path when keyed configuration is absent. Redesign plan eligibility to resolve waiting days after assignment. Defer vesting explicitly because it is currently request-time analytics rather than a dbt simulation parameter.

## Technical Context

**Language/Version**: Python 3.11; SQL/Jinja compatible with dbt Core 1.8.8 and dbt DuckDB 1.8.1
**Primary Dependencies**: Existing Pydantic v2 configuration, PlanAlign orchestrator, dbt Core, DuckDB 1.0.0, pytest 7.4; no new dependency
**Storage**: Existing scenario-isolated DuckDB outputs; invocation-scoped inline parameter relations only, with no new persisted table or public mart schema
**Testing**: pytest unit/integration tests, dbt singular/schema tests, bidirectional `EXCEPT ALL`, stable ordered row hashes, full isolated 2025–2027 simulations
**Target Platform**: Local macOS/Linux Python CLI and existing PlanAlign pipeline
**Project Type**: Python orchestration/configuration plus dbt transformation pipeline
**Performance Goals**: Preserve 100K+ employee support and single-threaded stability; parameter relations scale with design/tier count rather than employee count; no additional dbt invocation per year
**Constraints**: Same formula family across designs; exact design-set coverage; deterministic output; legacy scalar path unchanged; no shared dev database validation; event-sourced plan-design identity remains authoritative
**Scale/Scope**: Two or more plan designs per run, typically 2–10 designs and small tier/schedule collections, applied across all employee-years

## Constitution Check

*GATE before Phase 0: PASS. Re-checked after Phase 1: PASS.*

- **Event sourcing and immutability — PASS**: no event is mutated; employee design is read from the sticky #631 accumulator and continues into immutable facts.
- **Modular architecture — PASS**: typed configuration stays in `config/plan_design.py`; relation rendering stays in dedicated dbt macros; business models only join and apply resolved parameters. No `int_*` → forbidden `fct_*` dependency is added.
- **Test-first development — PASS**: configuration, macro, model, parity, and multi-year acceptance tests are specified before implementation.
- **Enterprise transparency — PASS**: design id and applied numeric values remain queryable at employee grain; missing/duplicate resolution fails rather than silently falling back.
- **Type-safe configuration — PASS**: Pydantic validates ids, rates, bounds, exact design-set equality, and same-family compatibility before dbt.
- **Performance and scalability — PASS**: inline relations are tiny; joins are keyed; workflow stage count and one-thread default are unchanged.
- **Isolated validation — PASS**: all behavioral verification uses pytest `tmp_path` or explicit `/private/tmp` DuckDB files.

No constitution violation requires a complexity exception.

## Product Lever Decisions

The normative detail is in [contracts/lever-disposition.md](contracts/lever-disposition.md).

**Per-design in Tier 1**:

- match numeric tiers/rates/caps for the globally selected family, including the derived match-max ceiling;
- core flat rate and service-graded schedule;
- auto-enrollment default deferral rate, window days, and scope;
- escalation increment and cap across all event/state/validation consumers;
- plan eligibility waiting days through one authoritative post-assignment relation.

**Global in Tier 1**:

- match/core formula-family selectors, labels, and enablement;
- core points/age/integration formulas and employer-contribution eligibility policy;
- auto-enrollment enablement, hire cutoff, opt-out grace, and behavioral probabilities;
- escalation enablement, effective date, hire cutoff, enrollment requirement, and first delay;
- minimum age, IRS limits, workforce, random, orchestration, and reporting controls.

**Deferred**:

- per-design vesting/forfeiture analytics, because the current API accepts one global request-level schedule and no simulation dbt consumer exists;
- cross-family coexistence (Tier 2).

## Project Structure

### Documentation (this feature)

```text
specs/632-per-design-plan-parameters/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── config-schema.md
    └── lever-disposition.md
```

### Source and tests

```text
planalign_orchestrator/
├── config/
│   ├── plan_design.py                 # typed parameter map and validators
│   ├── loader.py                      # SimulationConfig field/cross-validation
│   ├── safety.py                      # orchestration config parity
│   ├── __init__.py                    # public config exports
│   └── export.py                      # deterministic keyed dbt export + inventory
└── pipeline/
    └── workflow.py                    # assignment-aware eligibility ordering

dbt/
├── macros/
│   ├── get_plan_design_parameters.sql
│   ├── get_plan_design_match_tiers.sql
│   └── get_plan_design_core_graded_schedule.sql
├── models/intermediate/
│   ├── int_plan_eligibility_determination.sql
│   ├── int_employee_match_calculations.sql
│   ├── int_employer_core_contributions.sql
│   ├── int_deferral_rate_state_accumulator.sql
│   ├── int_enrollment_events.sql
│   ├── int_voluntary_enrollment_decision.sql
│   ├── int_proactive_voluntary_enrollment.sql
│   ├── events/int_eligibility_events.sql
│   ├── events/int_deferral_rate_escalation_events.sql
│   └── events/int_deferral_match_response_events.sql
├── models/staging/stg_census_data.sql  # stop baking design-sensitive wait dates
└── tests/                              # empty/cardinality/expected-parameter checks

tests/
├── fixtures/plan_design_parameters/   # deterministic two-design configs/census
├── integration/test_plan_design_parameters.py
├── unit/orchestrator/test_config_export.py
├── unit/orchestrator/test_config.py
├── test_dbt_var_coverage.py
├── test_workflow_schedule.py
├── unit/test_tier_b_stage_merge.py
└── fixtures/state_pipeline_graph_contract.yaml
```

**Structure Decision**: Extend the current config/export and dbt layers without a new service or persisted relation. Keep schedule expansion in macros, same-family calculations in their existing models, and multi-year acceptance in one dedicated integration suite.

## Implementation Sequence

### Phase A — Red tests and inventory contract

1. Add Pydantic tests for exact assignment/parameter design-set equality, invalid ids, rate bounds, interval ordering/overlap, family-inapplicable schedules, and deterministic ordering.
2. Add export tests proving keyed data is absent in legacy mode, deterministic in keyed mode, and existing scalar outputs remain unchanged.
3. Add a machine-checked lever-disposition registry covering every `to_dbt_vars` output as `per_design`, `global`, or `deferred`, with the normative matrix above as its documentation.
4. Add executable empty-relation dbt tests for scalar, match, and core macros.
5. Add failing isolated integration fixtures for two same-family designs and failing single-entry keyed-versus-scalar parity tests at two census sizes.

**Exit gate**: tests fail for missing typed config, macros, and runtime resolution—not because fixture setup or the shared DB is wrong.

### Phase B — Typed configuration and deterministic export

1. Define focused Pydantic models in `planalign_orchestrator/config/plan_design.py` for match, core, auto-enrollment, escalation, eligibility, and the top-level map.
2. Add `plan_design_parameters` to both `SimulationConfig` and `OrchestrationConfig`; expose the models through `config/__init__.py`.
3. Cross-validate exact key equality against `get_plan_design_set()`. Reject extra or missing definitions and incompatible schedules before execution.
4. Extend `to_dbt_vars` with a single deterministic keyed export only when configured. Continue exporting legacy scalars exactly as today.
5. Confirm run fingerprints/provenance naturally cover the keyed map through `to_dbt_vars`; add a focused metadata/fingerprint regression test.

**Exit gate**: config/export tests pass and legacy golden output is unchanged.

### Phase C — Relation macros and cardinality contracts

1. Implement `get_plan_design_parameters` with explicit `VARCHAR`, `INTEGER`, and `DECIMAL(10,6)` columns.
2. Implement family-aware flattened match schedules with explicit band/tier ordinals and design id.
3. Implement flattened core service bands with explicit ordinals and `[min, max)` bounds.
4. Copy Feature 099's typed `SELECT NULL ... WHERE FALSE` behavior for every empty input.
5. Add dbt tests that assert one scalar row per configured design, unique schedule keys, non-null ids, nonoverlap, and no unknown designs.

**Exit gate**: dbt parse and executable empty/cardinality tests pass in an isolated database.

### Phase D — Assignment-aware eligibility boundary

1. Remove design-sensitive waiting-day derivation from `stg_census_data`; retain raw hire data and any global/non-design fields.
2. Rework `int_plan_eligibility_determination` to join `int_plan_design_assignment_accumulator` and the keyed scalar relation, and emit `(scenario_id, plan_design_id, employee_id, simulation_year)` plus the resolved wait/date audit fields.
3. Move the authoritative eligibility calculation from start-year FOUNDATION to EVENT_GENERATION immediately after assignment and before `int_eligibility_events` and enrollment models. Preserve later-year build semantics.
4. Route census and new-hire logic in `int_eligibility_events` through that single relation; remove its independent scalar wait calculation.
5. Update voluntary/proactive enrollment and snapshot consumers so all wait dates come from the authoritative relation.
6. Update workflow schedule tests, calibration expectations if applicable, execution-type metadata, schema docs, and the pipeline graph fixture.

**Exit gate**: one eligibility date/wait value exists per employee/design/year; boundary tests pass for 0/30/90-day designs and the pipeline graph remains acyclic.

### Phase E — Convert behavior and contribution consumers

1. **Enrollment**: join assignments and scalar parameters in `int_enrollment_events`; use design default rate/window/scope. Carry full identifiers through voluntary/proactive models and harden joins.
2. **Escalation**: use design increment/cap in event generation, `int_deferral_rate_state_accumulator`, match-response events, and data-quality validation. Leave global timing/enablement branches intact.
3. **Match**: replace unkeyed tier cross joins and scalar cap with design-keyed relations inside the already selected global family branch. Derive the match-max ceiling from the same design schedule for all match-magnet consumers.
4. **Core**: join design scalar rate and the service-graded schedule selected by the global family; leave points/age/integration modes on their documented global path.
5. Harden touched employee joins with scenario/design/employee/year keys wherever both relations expose them.
6. Update schema descriptions and refactor dbt data-quality tests that currently calculate expected values from one global scalar.

**Exit gate**: every enabled lever resolves exactly one scalar parameter row and the intended schedule rows, with no row fan-out or missing design.

### Phase F — Isolated acceptance and compatibility

1. Run the `same_family_match_core` fixture over 2025–2027. Hand-tie one $80,000/4%-deferral employee per design to $2,400 versus $1,600; verify caps, core amounts, match events, and snapshots.
2. Run `enrollment_eligibility_escalation` over 2025–2027 with different scopes/windows/defaults, low caps, and waiting-day boundaries. Assert event populations, dates, increments, caps, and sticky selection per design.
3. Run scalar legacy versus keyed single-design parity at census sizes 40 and 149. Use bidirectional `EXCEPT ALL` and stable hashes across all deterministic mart columns, excluding only documented wall-clock metadata.
4. Run the dedicated scalar-versus-keyed 40- and 149-row parity fixtures over 2025–2027; this compares the two configuration paths directly without mutating or stashing the working tree.
5. Run targeted Ruff/Black, `pytest -m fast`, dbt parse/schema/singular tests, and the dedicated integration suite.

**Hard release gates**:

- semantic parity is `0/0` at both census sizes;
- every assigned employee resolves exactly one design parameter set;
- both hand calculations tie to the cent independently;
- all behavioral databases are isolated and multi-year;
- lever disposition documentation and machine inventory agree;
- no claim is made that vesting is supported per design.

## Risk Controls

- **Row fan-out**: assert resolution cardinality before aggregates and include design id in joins/grouping.
- **Numeric drift**: use explicit decimal types and verify rounding against independent `Decimal` calculations.
- **Hidden partial conversion**: inventory every consumer of converted vars, especially match ceiling and escalation cap.
- **Legacy regression**: retain the unmodified Jinja scalar path when keyed config is absent.
- **Pipeline cycle**: place eligibility after assignment but before eligibility/enrollment events; verify the manifest graph and authoritative stage selection.
- **Fingerprint drift**: export no keyed var in legacy mode; keyed mode intentionally fingerprints the full design map.
- **Empty schedules**: distinguish schema-valid macro emptiness from valid business configuration; Pydantic rejects an empty schedule when the selected family requires rows.
- **Vesting overclaim**: track the separate API/service follow-up and keep it out of Tier 1 completion language.

## Complexity Tracking

No constitution violations or new architectural layers are required.
