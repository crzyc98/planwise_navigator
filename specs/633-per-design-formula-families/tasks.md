# Tasks: Per-Design Contribution Formula Families

**Input**: Design documents from `/specs/633-per-design-formula-families/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Required by the feature specification and Constitution Principle III. All config, relation, parity, audit, compiled-SQL, and guard tests are written and observed failing before formula implementation begins.

**Organization**: Tasks are grouped by user story with a shared red-test foundation. Behavioral validation uses isolated full-horizon databases and never writes to `dbt/simulation.duckdb`. Test inputs come from checked-in builders/files under `tests/fixtures/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and does not depend on incomplete work
- **[Story]**: Maps the task to a user story in `spec.md`
- Every task names the exact file or directory it changes or validates

## Phase 1: Setup (Baselines and Shared Test Inputs)

**Purpose**: Establish reproducible pre-change evidence and deterministic checked-in fixtures.

- [X] T001 Create deterministic single-design, two-design, gap/overlap, audit, and 100k-capacity config/census builders covering all match/core families, integration on/off, and the legacy alias in `tests/fixtures/plan_design_formula_families/config.py`
- [X] T002 [P] Add the fixture package exports and static fixture metadata in `tests/fixtures/plan_design_formula_families/__init__.py`
- [X] T003 Run the pre-change 7.5k and 60k single-family baseline matrix into isolated files under `/tmp/run633/baseline/` and record the main SHA, seed, canonical column set, row hashes, and timings in `specs/633-per-design-formula-families/validation-baselines.md`

---

## Phase 2: Foundational Red Tests and Configuration Contracts

**Purpose**: Establish all release-protecting tests before implementing selectors, relations, dispatch, audit metadata, or guards.

**⚠️ CRITICAL**: T004-T012 must fail for the intended missing behavior before T013 or any user-story implementation begins.

### Red tests

- [X] T004 [P] Add failing fixture-backed unit tests for per-design match/core family literals, run-global inheritance, `tenure_based` normalization, schedule requirements, integration-level validation, and family independence in `tests/unit/config/test_plan_design_formula_families.py`
- [X] T005 [P] Extend the failing exported-variable ownership assertions using the checked-in plan-design fixture payload for age/points core schedules and the empty deferred set in `tests/test_dbt_var_coverage.py`
- [X] T006 [P] Extend the failing relation contract test using inputs rendered from `tests/fixtures/plan_design_formula_families/config.py` for scalar columns, typed empty shapes, age/points schedules, decimal-rate conversion, and design cardinality in `dbt/tests/test_plan_design_parameter_relations.sql`
- [X] T007 [P] Add failing fixture-backed tests for canonical `design_formula_families_json`, normalized aliases, inherited defaults, fingerprint sensitivity, additive schema evolution, and legacy NULL readability in `tests/test_run_metadata.py`
- [X] T008 Add failing small-census canonical-parity cases from `tests/fixtures/plan_design_formula_families/config.py` for every single-design family, integration on/off, ordered hashes, both-direction `EXCEPT ALL`, and the sole `created_at` exclusion in `tests/integration/test_plan_design_formula_families.py`
- [X] T009 Add failing fixture-backed compiled-SQL assertions that single-design runs contain only selected family branches and omit multi-design-only checks in `tests/integration/test_plan_design_formula_families.py`
- [X] T010 [P] Add failing load-time cases for unsupported families, absent schedules, invalid explicit integration levels, and design-specific remediation text using `tests/fixtures/plan_design_formula_families/config.py` in `tests/unit/config/test_plan_design_formula_families.py`
- [X] T011 Add failing fixture-backed match gap/overlap cases requiring correlation ID, year/context, resolution hints, eligibility scoping, computed-zero controls, and no partial publication in `tests/integration/test_plan_design_formula_families.py`
- [X] T012 Add failing fixture-backed core gap/overlap cases requiring the same diagnostic contract, ineligible controls, fallback rejection, and pre-dedup multiplicity detection in `tests/integration/test_plan_design_formula_families.py`

### Foundational implementation

- [X] T013 Add `family` and `match_template` to `MatchParameterSet`, add age/points band models plus family/integration fields to `CoreParameterSet`, and retain explicit Pydantic constraints in `planalign_orchestrator/config/plan_design.py`
- [X] T014 Replace run-global schedule validation with per-design match/core validation and actionable design/field diagnostics in `planalign_orchestrator/config/loader.py`
- [X] T015 Export the new per-design family, schedule, template, and integration values while preserving legacy run-global defaults in `planalign_orchestrator/config/export.py`
- [X] T016 Expand populated and empty scalar relations with stable typed match/core family, template, and integration columns in `dbt/macros/get_plan_design_parameters.sql`
- [X] T017 [P] Implement the half-open design-keyed age schedule relation with exactly-once percentage-to-decimal conversion in `dbt/macros/get_plan_design_core_age_schedule.sql`
- [X] T018 [P] Implement the half-open design-keyed points schedule relation with exactly-once percentage-to-decimal conversion in `dbt/macros/get_plan_design_core_points_schedule.sql`
- [X] T019 Reclassify age/points schedules as per-design, preserve the three-way disposition API with an empty `DBT_VAR_DEFERRED`, and make T004-T006 green in `planalign_orchestrator/config/export.py`

**Checkpoint**: Shared contracts are green; parity, audit, and guard tests remain red only for unimplemented story behavior.

---

## Phase 3: User Story 1 - Grandfathered Contribution Formulas by Hire Cohort (Priority: P1) 🎯 Feature MVP

**Goal**: Employees on different sticky designs receive match and core contributions from their own independently selected families and integration settings.

**Independent Test**: Run a 2025-2029 isolated two-design scenario with legacy `deferral_based`/`flat` and new-hire `tenure_graded`/`age_banded`; verify at least ten employees per design, downstream outputs, sticky assignment, and canonical audit metadata.

### Implementation for User Story 1

- [X] T020 [P] [US1] Extract byte-preserving match-family SQL emitters for all four supported families into `dbt/macros/match_family_arms/`
- [X] T021 [US1] Replace the run-global match branch with a union of referenced family arms, join by design/family, and drive caps and identifiers per row in `dbt/models/intermediate/int_employee_match_calculations.sql`
- [X] T022 [US1] Resolve match-magnet ceilings from each assigned design's family and schedule in `dbt/macros/resolve_match_magnet_ceiling.sql`
- [X] T023 [P] [US1] Replace the compile-time family literal with per-design resolution in `dbt/models/intermediate/events/int_deferral_match_response_events.sql`
- [X] T024 [P] [US1] Route voluntary-enrollment match-magnet decisions through the assigned design's family in `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`
- [X] T025 [P] [US1] Route proactive voluntary-enrollment match-magnet decisions through the assigned design's family in `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql`
- [X] T026 [P] [US1] Extract byte-preserving rate emitters for all four supported core families into `dbt/macros/core_family_rates/`
- [X] T027 [US1] Dispatch core rates and permitted-disparity settings by design, read banded families from design-keyed relations, and preserve integration output columns in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T028 [US1] Add and populate canonical nullable `design_formula_families_json` through additive append-only schema evolution per `specs/633-per-design-formula-families/contracts/audit-metadata.md` in `planalign_orchestrator/run_metadata.py`
- [X] T029 [US1] Run the focused multi-family test in `/tmp/run633/us1/` and record ten-per-design calculations, downstream tie-outs, sticky assignment, and audit-map evidence in `specs/633-per-design-formula-families/validation-baselines.md`

**Checkpoint**: A configuration-only two-design run produces correct match, core, integration, enrollment-response, and audit results.

---

## Phase 4: User Story 2 - Existing Single-Design Runs Are Unchanged (Priority: P1)

**Goal**: Preserve legacy configuration behavior, canonical deterministic results, and normal-path performance.

**Independent Test**: Compare main and branch full-horizon outputs across every family at 7.5k and 60k using the fixed canonical column set; confirm zero differences, equal hashes, and runtime within 5% at 60k.

### Validation for User Story 2

- [X] T030 [US2] Run all eight 7.5k branch scenarios into `/tmp/run633/branch/7500/` and record canonical zero-difference/hash comparisons for both intermediate contribution models and both downstream facts in `specs/633-per-design-formula-families/validation-baselines.md`
- [X] T031 [US2] Run all eight 60k branch scenarios into `/tmp/run633/branch/60000/` and record the same canonical comparisons in `specs/633-per-design-formula-families/validation-baselines.md`
- [X] T032 [US2] Compare 60k timings against `/tmp/run633/baseline/`, investigate variance above 5%, and document mitigation or the passing result in `specs/633-per-design-formula-families/validation-baselines.md`
- [X] T033 [US2] Run a saved pre-feature configuration unchanged through a full isolated horizon under `/tmp/run633/legacy/` and record config, result, and normal-path assertions in `specs/633-per-design-formula-families/validation-baselines.md`

**Checkpoint**: Legacy and single-design paths are canonically equal, compile only selected families, and meet the runtime boundary.

---

## Phase 5: User Story 3 - Formula Resolution Failures Abort Loudly (Priority: P1)

**Goal**: Stop before publication whenever an eligible employee resolves to zero or multiple formulas, with correlation, execution context, and remediation guidance.

**Independent Test**: Execute isolated multi-year match-gap, match-overlap, core-gap, and core-overlap scenarios; each fails before publication and identifies correlation ID, employee, design, year, side, family, observed value/count, and schedule correction.

**Pre-written tests**: T010-T012 establish the red behavior before dispatch implementation.

### Implementation for User Story 3

- [X] T034 [US3] Add an exactly-one-match-arm guard whose failure carries invocation/stage correlation, employee/design/year/family context, arm count/value, and schedule remediation hint in `dbt/models/intermediate/int_employee_match_calculations.sql`
- [X] T035 [P] [US3] Add the fixture-backed second-net assertion for match resolution and employee/design/year grain in `dbt/tests/data_quality/test_match_formula_arm_coverage.sql`
- [X] T036 [US3] Add core rate provenance and pre-dedup multiplicity guards with the full diagnostic contract and eligibility scoping in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T037 [P] [US3] Add the fixture-backed second-net assertion for core gaps, overlaps, fallback use, and employee/design/year grain in `dbt/tests/data_quality/test_core_rate_band_resolution.sql`
- [X] T038 [US3] Audit every deduplication, aggregation, and uniqueness key in all five in-scope models and record compliance or corrections in `specs/633-per-design-formula-families/key-audit.md`
- [X] T039 [US3] Run all four negative scenarios under `/tmp/run633/guards/` and record failure stage, diagnostics, and absence of downstream publication in `specs/633-per-design-formula-families/validation-baselines.md`

**Checkpoint**: No eligible employee can silently lose, duplicate, or fall back, and every in-scope key carries plan design.

---

## Phase 6: Polish and Constitution Gates

**Purpose**: Close documentation, schema, coverage, performance, and full-suite requirements.

- [X] T040 [P] Document scalar columns, schedule relations, output grains, audit field, and data tests in `dbt/models/intermediate/schema.yml`
- [X] T041 [P] Synchronize operator-facing examples and canonical validation commands in `specs/633-per-design-formula-families/quickstart.md`
- [ ] T042 Time the complete `pytest -m fast -q` suite, require completion under 10 seconds, and record command, elapsed time, and result in `specs/633-per-design-formula-families/validation-baselines.md` (MEASURED AND RECORDED: 2,675 passed in 246.41s; the under-10-second gate is NOT MET and remains open)
- [X] T043 Run the full plan-design integration suite against isolated fixture databases and record its result in `specs/633-per-design-formula-families/validation-baselines.md`
- [X] T044 Run relation, match-coverage, and core-resolution dbt tests from `dbt/` with `--threads 1` against an isolated fixture database and record the result in `specs/633-per-design-formula-families/validation-baselines.md`
- [X] T045 Measure Python/core-module and dbt schema/custom-test coverage against the constitution's 95%/90% targets and record any justified gap in `specs/633-per-design-formula-families/validation-baselines.md`
- [X] T046 Run the complete acceptance procedure and verify every criterion and constitution gate in `specs/633-per-design-formula-families/quickstart.md` (found and fixed an ineligible permitted-disparity regression in the integration-enabled core path; see `validation-baselines.md`)
- [X] T047 Run the default single-threaded 100k full-horizon scenario into `/tmp/run633/capacity_100k.duckdb` and record peak memory plus no-memory-error completion in `specs/633-per-design-formula-families/validation-baselines.md`

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup**: T003 finishes before implementation.
- **Foundation**: T004-T012 are the mandatory red-test gate; T013-T019 then make shared contracts green.
- **US1**: Depends on the complete foundation and implements the feature MVP.
- **US2**: Protective tests T008-T009 are red before US1; full-scale validation depends on US1.
- **US3**: Tests T010-T012 are red before US1; guard implementation depends on US1 dispatch.
- **Polish**: Depends on all story checkpoints.

### User Story Dependency Graph

```text
Setup -> all red tests -> shared config/relations -> US1 dispatch and audit
                                                 |-> US2 parity/performance validation
                                                 `-> US3 guards and negative validation

US1 + US2 + US3 -> documentation, full suites, coverage, and 100k capacity
```

### Parallel Opportunities

- T001 and T002 can proceed together.
- T004-T007 and T010 touch independent test files; T008-T009 then share the integration file sequentially.
- T017 and T018 can proceed together after the payload shape is fixed.
- T020, T026, and T028 touch independent match/core/audit files.
- T023-T025 touch separate production models after T022 settles the resolver contract.
- T035 and T037 touch independent singular tests after failure contracts are fixed.
- T040 and T041 can proceed together after behavior stabilizes.

---

## Parallel Example: User Story 1

```text
Task T020: Extract the four match-family emitters.
Task T026: Extract the four core-family rate emitters.
Task T028: Implement canonical audit metadata.
```

After T022 establishes the resolver contract:

```text
Task T023: Update deferral match response.
Task T024: Update voluntary enrollment.
Task T025: Update proactive voluntary enrollment.
```

---

## Implementation Strategy

### Feature MVP

1. Complete Phase 1 and preserve baseline evidence.
2. Complete every red test in T004-T012 before implementation.
3. Complete shared contracts T013-T019.
4. Complete US1 through T029 and validate independently.
5. Treat the plan's match-only boundary as a possible PR review split, not full-feature completion.

### Incremental Delivery

1. **Red guardrails**: Config, relation, canonical parity, audit, compiled-SQL, and negative tests.
2. **Foundation**: Typed selectors, validation, export taxonomy, and schedules.
3. **US1**: Match/core dispatch, enrollment consistency, integration, and auditability.
4. **US2**: Full-scale parity and performance evidence.
5. **US3**: Pre-publication guards and cross-model key audit.
6. **Constitution gates**: Complete suites, coverage, and 100k capacity.

### Validation Discipline

- Activate `.venv` before Python, pytest, dbt, or CLI commands.
- Run dbt only from `dbt/` and always with `--threads 1`.
- Source test data from `tests/fixtures/`; use one isolated DuckDB file per scenario and branch.
- Run full multi-year simulations for behavioral acceptance; focused unit/compile/relation tests are earlier gates.
- Compare identical seeds/configs across the fixed canonical column set; exclude only `created_at`.
- Preserve `scenario_id`, `plan_design_id`, `employee_id`, and `simulation_year` in every relevant key.

## Notes

- All three stories are P1 because correctness, default-path parity, and loud failure are co-equal release gates.
- `[P]` marks only tasks that do not edit the same file or depend on incomplete behavior.
- `fct_employer_match_events` and `fct_workforce_snapshot` retain schemas and are validation targets.
- `int_employer_eligibility` and `int_plan_eligibility_override` remain out of scope.
- No new public mart, dependency, or configuration mechanism is introduced.
