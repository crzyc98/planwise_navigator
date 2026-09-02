# Feature Specification: Per-Design Plan Parameters

**Feature Branch**: `632-per-design-plan-parameters`
**Created**: 2026-09-01
**Status**: Draft
**Input**: GitHub issue [#632](https://github.com/crzyc98/planwise_navigator/issues/632), a Tier 1 sub-issue of #571; depends on completed issue #631.

## Problem Statement

The pipeline can now assign each employee a sticky `plan_design_id`, but plan parameters are still exported as run-global dbt scalar variables. Employees assigned to two designs therefore cannot receive different match, core, enrollment, escalation, eligibility, or vesting terms within the same simulation, even when both designs use the same formula family.

The common grandfathering case is parameter-only variation: for example, existing employees receive 100% on the first 3% deferred while new hires receive 50% on the first 6%. The formula shape remains the same, but its rates, tiers, caps, or schedules differ by assigned design.

## Scope

**In scope**

- A typed collection of parameter sets keyed by `plan_design_id`, consistent with the design set established by `plan_design_assignment`.
- Runtime SQL relations keyed by `plan_design_id` for parameter-level variation in:
  - employer match rates, tiers, and caps;
  - employer core rate and service-graded schedule;
  - auto-enrollment default deferral rate, window, and scope;
  - deferral escalation increment and cap;
  - plan eligibility waiting days; and
  - vesting-schedule disposition, with the current request-time analytics architecture documented and deferred rather than misrepresented as a dbt conversion.
- Explicit documentation of every converted lever and every deliberately global dbt variable.
- Preservation of legacy scalar exports and byte-identical results for single-design configurations.
- Defensive, schema-valid empty relations when a relation or nested schedule has no configured rows.
- Isolated, multi-year validation for a same-family two-design configuration and edge cases.

**Out of scope**

- Different formula families in the same run. Formula selectors such as `employer_match_status`, core formula mode, and vesting formula type remain run-global compile-time choices for Tier 1.
- New plan-design assignment rule types or changes to sticky assignment semantics from #631.
- New public marts, API endpoints, or Studio controls for authoring multiple design parameter sets.
- Converting all dbt variables wholesale; simulation, workforce, stochastic, regulatory, orchestration, and reporting controls remain global unless explicitly listed above.
- Per-design vesting/forfeiture analytics. Vesting is not currently a simulation dbt variable: the API accepts one request-level schedule and applies it globally. Supporting simultaneous schedules requires a separate service/API contract change.
- Retroactive modification of saved results; affected scenarios must be rerun.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Two designs use different match parameters (Priority: P1)

An analyst assigns legacy employees to one design and new hires to another. Both designs use the same match formula family, but their tier rates and caps differ. Each employee must receive the amount specified by the employee's assigned design.

**Independent Test**: Run a small deterministic census with one employee on each design, equal compensation and deferral rates, and hand-calculate both match amounts.

**Acceptance Scenarios**:

1. **Given** both designs use deferral-based tiered match, legacy is 100% on 3%, and new-hire is 50% on 6%, **When** employees defer at least 6%, **Then** each employee's match equals the hand-calculated amount for their assigned design.
2. **Given** two designs have different match caps, **When** the uncapped formula exceeds one design's cap but not the other's, **Then** cap application is evaluated independently by design.
3. **Given** an employee's sticky design assignment persists across years, **When** the simulation advances, **Then** the employee continues using the same design's parameters.

### User Story 2 — Other plan levers vary by design (Priority: P1)

An analyst uses the same formula family for both designs but varies core contributions, auto-enrollment, escalation, and eligibility terms. Every simulation-time employee decision must resolve parameters from the employee's assigned design; request-time vesting analytics remain deferred.

**Independent Test**: Use a deterministic edge census containing employees on both sides of each boundary and verify the affected events, state, and contribution amounts by design.

**Acceptance Scenarios**:

1. **Given** different flat or service-graded core parameters, **When** core contributions are calculated, **Then** each amount uses the assigned design's rate or schedule.
2. **Given** different auto-enrollment default rates, windows, or scopes, **When** otherwise-equivalent employees become eligible, **Then** enrollment events and initial deferral rates reflect their assigned designs.
3. **Given** different escalation increments or caps, **When** enrolled employees reach an escalation date, **Then** the new rates respect the assigned design's increment and cap.
4. **Given** different eligibility waiting days, **When** employees cross only one design's boundary, **Then** eligibility is determined independently by design.

### User Story 3 — Existing single-design behavior is unchanged (Priority: P1)

An existing user runs any legacy single-design scenario without the new parameter collection. The pipeline must behave exactly as it did before this feature.

**Independent Test**: Run pre-change and post-change code against identical isolated databases at two census sizes and compare canonical tables with `EXCEPT ALL` in both directions plus deterministic row hashes after excluding documented wall-clock metadata. Raw DuckDB file bytes are not stable because models write timestamps.

**Acceptance Scenarios**:

1. **Given** a legacy single-design configuration, **When** the same seeded multi-year simulation runs before and after the change, **Then** canonical outputs have zero row differences in both directions and serialized deterministic artifacts are byte-identical.
2. **Given** no per-design parameters are configured, **When** dbt compiles, **Then** existing scalar defaults and precedence remain unchanged.

### User Story 4 — Configuration failures are explicit and SQL remains valid (Priority: P2)

A developer or analyst supplies incomplete or inconsistent multi-design parameter configuration. Invalid configuration should fail before simulation, while empty optional relations should compile to a schema-valid zero-row relation rather than invalid SQL.

**Independent Test**: Validate Pydantic rejection cases and compile each empty relation macro directly or through its consuming model.

**Acceptance Scenarios**:

1. **Given** a configured design parameter id that is not in the assignment design set, or an assigned design without a required parameter set, **When** configuration is loaded, **Then** validation fails with the mismatched ids.
2. **Given** an optional nested tier or schedule list is empty, **When** its SQL relation is rendered, **Then** it has the documented columns and zero rows.
3. **Given** duplicate parameter sets or duplicate/overlapping schedule keys for one design, **When** configuration is loaded, **Then** validation fails before dbt execution.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Configuration MUST represent plan parameter sets as a deterministic collection keyed by unique, nonblank `plan_design_id` values.
- **FR-002**: In a multi-design configuration, the parameter design set MUST equal the design set produced by `plan_design_assignment`; missing and extra ids MUST be rejected before execution.
- **FR-003**: Formula-family selectors MUST remain global in Tier 1, and configuration MUST reject parameter sets that imply incompatible formula families within one run.
- **FR-004**: The exporter MUST preserve existing scalar dbt variables for legacy single-design configurations and MUST additionally export deterministic keyed parameter data only when multi-design parameters are configured.
- **FR-005**: Match calculations MUST resolve rates, tiers, and caps by the employee's `plan_design_id` before calculating or capping the amount.
- **FR-006**: Core calculations MUST resolve flat rates and service-graded schedules by the employee's `plan_design_id` while keeping the selected core formula family global.
- **FR-007**: Auto-enrollment decisions MUST resolve default deferral rate, enrollment window, and scope by `plan_design_id` at the point each decision or event is created.
- **FR-008**: Deferral escalation decisions and state accumulation MUST resolve increment and cap by `plan_design_id` in every simulation year.
- **FR-009**: Plan eligibility MUST resolve waiting days by `plan_design_id` from one authoritative relation used by all eligibility consumers; legacy aliases MUST NOT diverge.
- **FR-010**: The lever disposition MUST record vesting as deferred because no simulation dbt variable or employee-level vesting calculation currently exists; a follow-up MUST define how request-level vesting and forfeiture analytics resolve schedules by `plan_design_id`.
- **FR-011**: Every keyed parameter or nested schedule relation MUST expose explicit typed columns and render a schema-valid zero-row result when no rows are configured.
- **FR-012**: Employee-level joins to parameter relations MUST include `plan_design_id` and the existing scenario/year/employee keys where applicable, and MUST yield exactly one applicable parameter row or schedule band for each decision.
- **FR-013**: The implementation MUST document a complete lever disposition matrix: per-design now, global by Tier 1 boundary, or deferred, with rationale and consuming models.
- **FR-014**: Legacy single-design runs MUST produce byte-identical deterministic row content, excluding documented wall-clock metadata, demonstrated by bidirectional `EXCEPT ALL` and stable row hashes at two census sizes across a full multi-year simulation.
- **FR-015**: A two-design same-family run MUST produce independently verifiable per-employee amounts and decisions, including at least one hand tie-out per design.
- **FR-016**: Behavioral validation MUST use fresh isolated DuckDB databases and include non-default edge configurations for enrollment scope/window, low escalation caps, and eligibility boundaries.
- **FR-017**: Existing event-sourcing, deterministic UUID, config fingerprint, run-metadata design-set, and incremental grain contracts MUST remain valid.

### Key Entities

- **Plan design assignment**: The sticky per-employee design identity created by #631 and carried through events, accumulators, and snapshots.
- **Plan design parameter set**: One validated parameter record for a design id, containing same-family lever values and nested schedules.
- **Keyed parameter relation**: A dbt-rendered, typed SQL row set with one scalar row per design and separate flattened rows for repeated tiers or schedule bands.
- **Lever disposition matrix**: The auditable inventory that records whether each exported dbt variable is per-design, global, or deferred and why.

## Success Criteria *(mandatory)*

- **SC-001**: Legacy single-design comparisons show `EXCEPT ALL` counts of 0/0 for canonical event, state, contribution, and snapshot relations at two census sizes, with byte-identical deterministic artifacts.
- **SC-002**: In the 100%-on-3% versus 50%-on-6% scenario, at least one employee per design ties exactly to a hand calculation at cent precision.
- **SC-003**: Every employee-year in the two-design test resolves exactly one parameter row for every enabled lever; zero missing or duplicate resolutions are reported.
- **SC-004**: Empty relation tests compile successfully and return the expected column schema with zero rows for 100% of keyed relation macros.
- **SC-005**: Multi-year edge scenarios demonstrate independent behavior for both designs at enrollment, escalation, and eligibility boundaries without cross-design leakage; vesting remains the documented deferred follow-up.
- **SC-006**: The lever disposition matrix accounts for all 138 currently exported dbt vars and explicitly classifies the 89 identified as plan-design-scoped.

## Assumptions

- Issue #631 is the authoritative source of per-employee sticky `plan_design_id` and is already merged.
- Tier 1 supports multiple numeric or schedule parameter sets only when all designs share the same compile-time formula family for a lever.
- Single-design compatibility has priority over eliminating duplicate scalar/keyed config representations; removing legacy scalar exports is a later breaking change.
- Regulatory limits, workforce behavior, random seeds, simulation dates, orchestration controls, and reporting controls are run-global.
- Studio authoring and public API schema changes are deferred; YAML/Pydantic configuration and dbt execution are sufficient for this engine feature.
