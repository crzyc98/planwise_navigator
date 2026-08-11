# Tasks: Correct Employer Contribution Eligibility Service Credit

**Input**: Design documents from `/specs/136-eligibility-tenure-offset/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [service-credit contract](contracts/service-credit.md), [quickstart.md](quickstart.md)

**Tests**: Tests are required by the feature specification and constitution. Write and observe each failing regression test before its related SQL correction, and run every behavioral simulation against an isolated DuckDB database.

**Organization**: Shared characterization and eligibility-gate work precede story phases because core and match consume the same determination. User-story phases then cover core costs, match costs, and durable drift detection independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]** marks tasks that can proceed in parallel after their shared prerequisites complete.
- **[US#]** maps a task to the corresponding user story in [spec.md](spec.md).
- Every task names the exact file or files it changes or validates.

## Phase 1: Setup and Pre-Fix Characterization

**Purpose**: Establish deterministic fixtures and preserve the valid opening-year/zero-wait baseline before changing service arithmetic.

- [X] T001 Add deterministic 0-, 1-, 2-, and 3-year core/match wait configuration builders plus an allowed-experienced-termination service-tier case in `tests/fixtures/employer_eligibility_tenure.py` and `tests/fixtures/employer_eligibility_tenure/wait_{0,1,2,3}.yaml`, reusing `tests/fixtures/invariant_census.csv` and asserting every boundary cohort is non-empty.
- [X] T002 Run the unmodified engine with the T001 fixtures in disposable databases and record only synthetic aggregate opening-year outputs for waits 1/2/3 and all-year zero-wait outputs in `tests/fixtures/employer_eligibility_tenure/baseline_characterization.json`.

**Checkpoint**: Synthetic fixtures cover every required boundary, and the behavior that must not change is pinned before implementation.

---

## Phase 2: Foundational Canonical Eligibility Basis

**Purpose**: Make the current-year workforce accumulator the shared core/match eligibility source before story-specific contribution work.

**⚠️ CRITICAL**: Complete this phase before either P1 user story.

- [X] T003 [P] Add a failing, error-severity singular dbt invariant that joins the scoped current build year and rejects any eligibility/workforce service mismatch in `dbt/tests/assert_employer_eligibility_service_matches_workforce.sql`.
- [X] T004 [P] Add a failing, error-severity singular dbt invariant that rejects below-threshold core or enforced-match eligibility while allowing only the corresponding explicit hire-year exception in `dbt/tests/assert_employer_tenure_requirements_enforced.sql`.
- [X] T005 Replace the prior-year `current_tenure + 2` reconstruction with direct current-year accumulator tenure and remove the redundant prior-year self-join without changing hours, status, reason, or exception logic in `dbt/models/intermediate/int_employer_eligibility.sql`.
- [X] T006 Document `current_tenure` as an exact copy of authoritative workforce service and align eligibility-test descriptions with the internal contract in `dbt/models/intermediate/schema.yml`.

**Checkpoint**: Core and configured-match gates use the same current-year service value, and dbt validation fails on any offset or unsupported below-threshold eligibility.

---

## Phase 3: User Story 1 — Multi-Year Core Waiting Periods Produce Distinct Costs (Priority: P1) 🎯 MVP

**Goal**: Correct core eligibility and every service-dependent core rate so 1-, 2-, and 3-year waits remain distinct throughout a five-year projection.

**Independent Test**: Run isolated 2025–2029 scenarios for waits 0, 1, 2, and 3; confirm wait-1 and wait-2 core costs differ every year, wait-3 has fewer contributing employees than wait-2 every year, no below-threshold employee receives core dollars, and opening-year/zero-wait aggregates match the characterization.

### Tests for User Story 1

- [X] T007 [P] [US1] Add failing isolated-database core assertions for annual 1/2 cost separation, strict 2/3 population ordering, no below-threshold awards, non-vacuous cohorts, opening-year characterization, zero-wait parity, and the shared-dev-database hash guard in `tests/integration/test_employer_eligibility_tenure.py`.
- [X] T008 [P] [US1] Strengthen core audit reconciliation for scenario/year scoping and exact termination-date `applied_years_of_service` equality in `dbt/tests/test_audit_trail_core_contributions.sql`.

### Implementation for User Story 1

- [X] T009 [US1] Remove experienced-termination prior-year service reconstruction and select graded/points core rates plus `applied_years_of_service` from current-year accumulator tenure in `dbt/models/intermediate/int_employer_core_contributions.sql`, preserving compensation, proration, caps, and configured termination allowances.
- [X] T010 [US1] Run the core cases in `tests/integration/test_employer_eligibility_tenure.py` and the core invariants in `dbt/tests/{assert_employer_eligibility_service_matches_workforce.sql,assert_employer_tenure_requirements_enforced.sql,test_audit_trail_core_contributions.sql}` against disposable `DATABASE_PATH` databases and correct only failures within the US1 files.

**Checkpoint**: User Story 1 is independently complete: multi-year core costs honor completed service, including termination-date service, while opening-year and zero-wait behavior remain pinned.

---

## Phase 4: User Story 2 — Match Waiting Periods Use the Same Service Basis (Priority: P1)

**Goal**: Enforced match eligibility and every service-dependent match rate use the same authoritative service basis as core.

**Independent Test**: Run an isolated five-year scenario with core and match eligibility enforcement configured identically at two years; confirm neither awards below-threshold employees, both gates identify the same service-qualified employee-years, and an allowed experienced termination is rated using termination-date service.

### Tests for User Story 2

- [X] T011 [P] [US2] Add failing enforced-match assertions for 2-/3-year waits, core/match service-qualified set equality, positive deferral non-vacuity, and allowed-termination service-tier alignment in `tests/integration/test_employer_eligibility_tenure.py`.
- [X] T012 [P] [US2] Tighten the service-match audit from a one-year tolerance to exact equality and scope workforce joins by employee/year/scenario/plan where available in `dbt/tests/test_service_match_boundaries.sql`.

### Implementation for User Story 2

- [X] T013 [US2] Remove experienced-termination prior-year service reconstruction and derive graded, tenure-graded, and points-based match `years_of_service` plus `applied_years_of_service` from current-year accumulator tenure in `dbt/models/intermediate/int_employee_match_calculations.sql`.
- [X] T014 [US2] Run the match cases in `tests/integration/test_employer_eligibility_tenure.py` and exact audit coverage in `dbt/tests/{assert_employer_tenure_requirements_enforced.sql,test_service_match_boundaries.sql}` against disposable `DATABASE_PATH` databases and correct only failures within the US2 files.

**Checkpoint**: User Story 2 is independently testable: enforced match waits and service-dependent match rates reconcile to the same employee-year service used by core.

---

## Phase 5: User Story 3 — Service-Basis Drift Fails Automatically (Priority: P2)

**Goal**: Make any future eligibility or contribution service offset fail fast with bounded, auditable diagnostics.

**Independent Test**: Feed synthetic current-year rows containing a deliberate one-year active-employee offset, a wider termination/reset offset, and below-threshold eligibility into the invariant queries; confirm each violation is returned while exact boundaries and explicit new-hire exceptions pass.

### Tests for User Story 3

- [X] T015 [P] [US3] Add bounded workforce/eligibility equality and requirement-enforcement queries plus fast synthetic tests for exact matches, one-year offsets, termination/reset offsets, exact thresholds, and explicit new-hire exceptions in `tests/invariants/queries.py` and `tests/test_employer_eligibility_invariants.py`.
- [X] T016 [P] [US3] Extend SQL graph-contract tests to reject prior-year service arithmetic/self-joins in eligibility, core, and match consumers while preserving the accumulator-first workflow order in `tests/unit/orchestrator/test_pipeline_graph_contract.py`.

### Implementation for User Story 3

- [X] T017 [US3] Document exact `applied_years_of_service` semantics for core and service-dependent match modes and ensure the singular service tests carry error-severity data-quality tags in `dbt/models/intermediate/schema.yml` and `dbt/tests/{assert_employer_eligibility_service_matches_workforce.sql,assert_employer_tenure_requirements_enforced.sql}`.
- [X] T018 [US3] Run `tests/test_employer_eligibility_invariants.py`, `tests/unit/orchestrator/test_pipeline_graph_contract.py`, and both singular tests under `dbt/tests/` against an isolated final-year database, confirming the deliberate-offset cases fail without modifying `dbt/simulation.duckdb`.

**Checkpoint**: User Story 3 is complete: service drift and unsupported below-threshold eligibility are detected by fast tests, SQL graph contracts, and dbt data checks.

---

## Phase 6: Polish and Cross-Cutting Validation

**Purpose**: Verify the complete feature under repository quality gates and synchronize its runnable validation guide.

- [X] T019 Run the complete isolated validation sequence in `specs/136-eligibility-tenure-offset/quickstart.md`, including the 0/1/2/3 five-year integration matrix, final-year dbt tests with `--threads 1`, and `pytest -m fast`, and resolve only feature-scoped failures.
- [X] T020 Update actual fixture names, commands, expected outcomes, and the no-migration/no-public-contract compatibility note after validation in `specs/136-eligibility-tenure-offset/quickstart.md` and `specs/136-eligibility-tenure-offset/contracts/service-credit.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately; T002 depends on T001 and must finish before production SQL changes.
- **Foundational (Phase 2)**: Depends on T001–T002 and blocks both P1 stories; T003 and T004 can be authored in parallel before T005.
- **US1 (Phase 3)**: Depends on T003–T006; T007 and T008 can run in parallel, then T009 and T010 complete the story.
- **US2 (Phase 4)**: Depends on T003–T006; it is logically independent of core calculation changes, but T011 should follow T007 because both extend the same integration module.
- **US3 (Phase 5)**: Depends on T003–T006; T015 and T016 can proceed alongside the contribution stories, while T017–T018 follow the final consumer behavior.
- **Polish (Phase 6)**: Depends on all selected user stories; T019 precedes T020.

### User Story Dependencies

- **US1 (P1)**: Uses the canonical gate established in Phase 2 and has no dependency on match calculation changes.
- **US2 (P1)**: Uses the canonical gate established in Phase 2 and can be verified without core rate changes when configured-match assertions are run alone.
- **US3 (P2)**: Uses the shared invariants from Phase 2; its fast mutation and graph checks are independently executable, while final documentation covers both contribution consumers.

### Dependency Graph

```text
Setup ──> Canonical eligibility foundation ──┬──> US1 core correction ──┐
                                            ├──> US2 match correction ─┼──> Polish
                                            └──> US3 drift prevention ─┘
```

### Parallel Opportunities

- T003 and T004 target independent singular dbt test files.
- T007 and T008 target the Python integration suite and core dbt audit test independently.
- T011 and T012 target the Python integration suite and match dbt audit test independently after T007 establishes the shared harness.
- T015 and T016 target independent fast-invariant and graph-contract files.
- After Phase 2, core SQL work, match SQL work, and fast drift-prevention work can proceed concurrently if edits to the shared integration test and `schema.yml` are coordinated.

## Parallel Execution Examples

### User Story 1

```text
Task: T007 — Isolated multi-year core waiting-period integration assertions
Task: T008 — Exact core service-audit dbt test
```

### User Story 2

```text
Task: T011 — Enforced-match and core/match qualification integration assertions
Task: T012 — Exact match service-audit dbt test
```

### User Story 3

```text
Task: T015 — Bounded invariant queries and deliberate-offset fast tests
Task: T016 — SQL consumer graph-contract guards
```

## Implementation Strategy

### MVP First

1. Complete Setup and the canonical eligibility foundation.
2. Complete User Story 1 and validate its 0/1/2/3 isolated core scenarios.
3. Stop and verify the analyst-visible core cost defect is corrected without opening-year or zero-wait drift.
4. Treat User Story 2 as required before a complete P1 release because match shares the same defect.

### Incremental Delivery

1. Preserve pre-fix compatibility baselines and establish failing shared invariants.
2. Correct the shared eligibility service basis.
3. Deliver and validate core waiting-period behavior (US1 MVP).
4. Deliver and validate configured match behavior and rate alignment (US2 complete P1 scope).
5. Add mutation pins, graph guards, documentation, and the complete isolated validation sequence (US3 and polish).

## Notes

- Keep saved scenario results immutable; only reruns receive corrected values.
- Do not add configuration, API, Studio, event, or public mart fields.
- Do not change adjacent points-based age arithmetic, reporting tenure bands, enrollment behavior, contribution formulas, proration, vesting, or default match compatibility mode.
- Do not add this feature to the already capped seven-case edge-config matrix.
- Run dbt only from `dbt/`, always with `--threads 1`, and never use `dbt/simulation.duckdb` for behavioral validation.
