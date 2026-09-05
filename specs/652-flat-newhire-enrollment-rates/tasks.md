# Tasks: Explicit New-Hire Enrollment Rates and Deferral Spread

**Input**: Design documents from `/specs/652-flat-newhire-enrollment-rates/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Branch**: `652-flat-newhire-enrollment-rates` | **Tracking Issue**: #652

**Tests**: Test tasks ARE included. Constitution Principle III mandates test-first development (Red-Green-Refactor); this is not optional for this project.

**Organization**: Grouped by user story so each can be implemented and verified independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1-US5, mapping to the user stories in spec.md

## Path Conventions

Existing modular pipeline. dbt models under `dbt/models/`, Python config under `planalign_orchestrator/config/`, Studio under `planalign_studio/components/`, tests under `tests/`.

**Standing rule**: every simulation run in these tasks uses an isolated database via `DATABASE_PATH`. Nothing here may run against `dbt/simulation.duckdb`.

---

## Phase 1: Setup — Capture Baselines

**Purpose**: Every compatibility guarantee in this feature (SC-006, SC-009, SC-012) is a comparison against pre-change behavior. Those baselines must exist before the first line of code changes, or they cannot be reconstructed.

- [X] T001 Create the working directory `var/652/` and a config with both new rates unset, copied from `config/simulation_config.yaml`
- [X] T002 Run the unset-config baseline to `var/652/baseline.duckdb` for 2025-2029 via `DATABASE_PATH=var/652/baseline.duckdb planalign simulate 2025-2029 --config var/652/unset.yaml --database var/652/baseline.duckdb`
- [X] T003 [P] Record new-hire enrollment counts by `participation_status_detail` and year from `var/652/baseline.duckdb` into `var/652/baseline_enrollment.csv` (query in quickstart.md step 2)
- [X] T004 [P] Record per-employee deferral rates from `var/652/baseline.duckdb` into `var/652/baseline_deferral.csv`, for the SC-012 spread-disabled comparison
- [X] T005 [P] Record the per-cell deferral distribution (age segment x income segment x rate) from `var/652/baseline.duckdb` into `var/652/baseline_cells.csv`, establishing the "100% at one rate" figure SC-010 improves on

**Checkpoint**: Baselines captured. Any later claim of "unchanged" is now falsifiable.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The config surface and the removal of the inert multiplier. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests (write first, confirm they fail)

- [X] T006 [P] Add validation tests for `new_hire_opt_out_rate` (accepts 0.0, 1.0 and mid-range; rejects -0.1 and 1.5 with a field-named error) in `tests/unit/orchestrator/test_config_export.py`
- [X] T007 [P] Add export tests asserting `new_hire_opt_out_rate` is omitted from dbt vars when `None` and emitted when `0.0`, mirroring the existing `test_voluntary_enrollment_rate_zero` case, in `tests/unit/orchestrator/test_config_export.py`
- [X] T008 [P] Add a test asserting `voluntary_enrollment_rate`'s description no longer describes a multiplier, guarding against the semantic regression this feature exists to fix, in `tests/unit/orchestrator/test_config_export.py`

### Implementation

- [X] T009 Add the `new_hire_opt_out_rate: Optional[float]` field with `ge=0, le=1` and default `None` to `AutoEnrollmentSettings` in `planalign_orchestrator/config/workforce.py` (alongside `voluntary_enrollment_rate` at line 73)
- [X] T010 Rewrite the `voluntary_enrollment_rate` field description in `planalign_orchestrator/config/workforce.py` to state the flat new-hire meaning and that `None` selects demographic behavior
- [X] T011 Export `new_hire_opt_out_rate` to dbt vars via `_set_if_not_none` in `planalign_orchestrator/config/export.py`, next to the existing `voluntary_enrollment_rate` export at line 193
- [X] T012 Export `new_hire_opt_out_rate` on the Studio `dc_plan` dict path in `planalign_orchestrator/config/export.py`, next to the existing handling at line 432
- [X] T013 Remove the `voluntary_enrollment_rate: 1.0` default from `dbt/dbt_project.yml` line 261 so that `var('voluntary_enrollment_rate', none)` resolves to `none` when unset — this is what makes set/unset expressible in SQL
- [X] T014 [P] Delete the inert `* COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)` term from the probability expression at `dbt/models/intermediate/int_voluntary_enrollment_decision.sql:211`
- [X] T015 [P] Delete the same inert term at `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql:251`
- [X] T016 [P] Delete the same inert term from the year-over-year CTE at `dbt/models/intermediate/int_enrollment_events.sql:549` and `:584`
- [X] T017 Run the unset config to `var/652/phase2.duckdb` and assert new-hire enrollment counts are **byte-identical** to `var/652/baseline_enrollment.csv` — the deletion multiplies by 1.0 and must change nothing; if counts move, stop and re-examine research R1

**Checkpoint**: Config accepts both rates, the multiplier is gone, and behavior is provably unchanged.

---

## Phase 3: User Story 1 — Analyst sets an exact new-hire voluntary enrollment percentage (Priority: P1) 🎯 MVP

**Goal**: Setting the voluntary rate to a value produces that share of eligible new hires enrolling voluntarily.

**Independent Test**: Run with the rate at 0.6 and count eligible new hires with enrollment source `voluntary_enrollment`; the share must be 60% ±2 points in every year.

### Tests (write first, confirm they fail)

- [X] T018 [P] [US1] Create `tests/integration/test_new_hire_enrollment_rates.py` with a test asserting the voluntary share is 60% ±2 points per year against an isolated DB fixture
- [X] T019 [P] [US1] Add a test asserting a rate of 1.0 yields at least 99% voluntary enrollment among eligible new hires (SC-002) in `tests/integration/test_new_hire_enrollment_rates.py`
- [X] T020 [P] [US1] Add a determinism test asserting two runs at the same seed select the identical set of employee IDs, not merely the same count (SC-005), in `tests/integration/test_new_hire_enrollment_rates.py`
- [X] T021 [P] [US1] Add a test asserting no employee has more than one enrollment event per year and that `proactive_voluntary` is absent when the flat rate is set (FR-004), in `tests/integration/test_new_hire_enrollment_rates.py`

### Implementation

- [X] T022 [US1] Add a set/unset Jinja branch to the `deferral_rate_selection` CTE in `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`: when `voluntary_enrollment_rate` is set, hire-year new hires use it as `final_enrollment_probability` directly; continuing employees keep the demographic product in both modes
- [X] T023 [US1] Verify the existing `enrollment_random` draw at `int_voluntary_enrollment_decision.sql:202` is reused unchanged for the flat comparison, so the seed contract and reproducibility guarantee hold
- [X] T024 [US1] Gate `int_proactive_voluntary_enrollment.sql` so it emits no enrollment decision when `voluntary_enrollment_rate` is set, eliminating the second independent draw (research R3); when unset it behaves as today
- [X] T025 [US1] Add `'proactive_voluntary'` to the `enrollment_method` category list at `dbt/models/intermediate/int_enrollment_state_accumulator.sql:58`, fixing the alias gap found in research R4 so proactive enrollments stop relying on a NULL-method fallback
- [X] T026 [US1] Run the P=0.6 config to `var/652/us1.duckdb` and confirm the voluntary share and determinism assertions pass

**Checkpoint**: The voluntary dial does what it says. This alone is a shippable MVP.

---

## Phase 4: User Story 2 — Analyst sets an exact new-hire opt-out percentage (Priority: P1)

**Goal**: The auto-enrolled remainder splits by the stated opt-out rate rather than by demographics.

**Independent Test**: With P=0.6 and Q=0.1, eligible new hires land at ~60% voluntary, ~36% auto-participating, ~4% opted out, ~0% unenrolled.

### Tests (write first, confirm they fail)

- [X] T027 [P] [US2] Add a test asserting the full four-way split at P=0.6, Q=0.1 within 2 points per year (SC-001) in `tests/integration/test_new_hire_enrollment_rates.py`
- [X] T028 [P] [US2] Add a test asserting P=0.0, Q=0.0 yields at least 99% auto-enrolled and participating (SC-003) in `tests/integration/test_new_hire_enrollment_rates.py`
- [X] T029 [P] [US2] Add a test asserting zero eligible new hires **active at year end** are unenrolled (SC-004, measured per decision D2) in `tests/integration/test_new_hire_enrollment_rates.py`

### Implementation

- [X] T030 [US2] Add a set/unset branch to the `opt_out_events` CTE in `dbt/models/intermediate/int_enrollment_events.sql` (lines 340-421): when `new_hire_opt_out_rate` is set, hire-year new hires compare `optout_random` against the flat rate; all other employees keep the demographic product
- [X] T031 [US2] Use the existing `EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year` predicate (already used at line 346) to scope the flat branch to hire-year new hires only, leaving continuing employees on `opt_out_rate_*`
- [X] T032 [US2] Confirm `int_enrollment_events.sql` still compiles under the sqlparse token ceiling that `fct_workforce_snapshot` already trips (plan Risk 5)
- [X] T033 [US2] Run the P=0.6/Q=0.1 config to `var/652/us2.duckdb` and confirm the four-way split assertions pass

**Checkpoint**: Both dials work. The full distribution guarantee from FR-003 holds.

---

## Phase 5: User Story 3 — Analyst reads the control and understands what it does (Priority: P2)

**Goal**: The Studio fields are labeled and defaulted so the unset state is discoverable and the meaning is unambiguous.

**Independent Test**: Open the scenario configuration screen; the voluntary field reads as a new-hire percentage and an opt-out field is present and editable.

### Implementation

- [X] T034 [P] [US3] Add `dcNewHireOptOutRate: string` to the form type in `planalign_studio/components/config/types.ts` (alongside `dcVoluntaryEnrollmentRate` at line 174)
- [X] T035 [US3] Change `dcVoluntaryEnrollmentRate` from `'30'` to `''` and add `dcNewHireOptOutRate: ''` in `planalign_studio/components/config/constants.ts:186` — per decision D1 this is what makes Studio's default match the Python default of unset
- [X] T036 [US3] Relabel the heading and input from "Voluntary Enrollment Rate" to "New Hire Voluntary Enrollment %" and add a "New Hire Opt-Out %" input with 0-100 range validation in `planalign_studio/components/config/DCPlanSection.tsx` (lines 332-352)
- [X] T037 [US3] Add help text on both inputs stating that empty means demographic behavior — the unset state is now meaningful and must be discoverable (FR-016) — in `planalign_studio/components/config/DCPlanSection.tsx`
- [X] T038 [US3] Emit `new_hire_opt_out_rate` when the field is non-empty in `planalign_studio/components/config/buildConfigPayload.ts` (mirroring line 95)
- [X] T039 [US3] Hydrate `dcNewHireOptOutRate` from `cfg.dc_plan?.new_hire_opt_out_rate` in `planalign_studio/components/config/ConfigContext.tsx` (mirroring line 235)
- [X] T040 [P] [US3] Relabel the read-only field and add the opt-out row in `planalign_studio/components/PlanDesignModal.tsx:158`, keeping the existing "Default" rendering for unset values
- [X] T041 [US3] Verify a Studio-created scenario with both fields left empty produces a config with neither key, matching the Python unset path

**Checkpoint**: The dials are legible and default to realistic behavior.

---

## Phase 6: User Story 4 — Continuing-employee behavior is preserved (Priority: P2)

**Goal**: Nothing outside the new-hire population moved.

**Independent Test**: Compare continuing-employee enrollment counts against the Phase 1 baseline.

### Tests

- [X] T042 [P] [US4] Add a test asserting continuing-employee (non-hire-year) enrollment counts match `var/652/baseline_enrollment.csv` when both rates are unset (SC-006, SC-009), in `tests/integration/test_new_hire_enrollment_rates.py`
- [X] T043 [P] [US4] Add a test asserting changing the new-hire voluntary rate leaves continuing-employee enrollment counts unchanged, in `tests/integration/test_new_hire_enrollment_rates.py`

### Implementation

- [X] T044 [US4] Confirm by inspection that the flat branches added in T022 and T030 are gated on hire-year membership and cannot reach continuing employees or the year-over-year conversion path (FR-007)

**Checkpoint**: The blast radius is confirmed to be new hires only.

---

## Phase 7: User Story 5 — Deferral rates look like real elections (Priority: P2)

**Goal**: A demographic cell produces a spread of whole-percent elections at or above its table value, instead of one spike.

**Independent Test**: Run with the spread enabled; no cell holds more than 45% of its members at any single rate, and no member falls below the cell's table value.

### Tests (write first, confirm they fail)

- [X] T045 [P] [US5] Add a test asserting no demographic cell holds more than 45% of members at a single rate when the spread is enabled (SC-010), in `tests/integration/test_deferral_spread.py`
- [X] T046 [P] [US5] Add a test asserting zero employees hold a rate below their cell's table value — the floor property (SC-011, FR-019) — in `tests/integration/test_deferral_spread.py`
- [X] T047 [P] [US5] Add a test asserting the spread-disabled run reproduces `var/652/baseline_deferral.csv` per employee (SC-012), in `tests/integration/test_deferral_spread.py`
- [X] T048 [P] [US5] Add a test asserting the observed lift distribution approximates the 40/30/15/10/5 weights across +0 to +4 (FR-018), in `tests/integration/test_deferral_spread.py`
- [X] T049 [P] [US5] Add a test asserting spread assignment is independent of the match-magnet draw — the two must not correlate (FR-021) — in `tests/integration/test_deferral_spread.py`

### Implementation

- [X] T050 [US5] Add `deferral_spread_max_lift` config (integer percentage points, default `0` = off) to `planalign_orchestrator/config/workforce.py` and export it in `planalign_orchestrator/config/export.py`
- [X] T051 [US5] Create a `deferral_spread` macro in `dbt/macros/deferral_spread.sql` that takes a base rate and an independent random value and returns the base plus a lift of 0-4 whole percentage points using the 40/30/15/10/5 weights, returning the base unchanged when the feature is off
- [X] T052 [US5] Add an independent `spread_random` draw seeded on `employee_id || '-deferral-spread-' || year` in `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` — **must not** reuse `deferral_random` at line 246, which is already consumed by the match-magnet snap (research finding; reuse would correlate the two)
- [X] T053 [US5] Apply the macro between the table lookup and the match-magnet snap in `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`, so match-maximizing behavior still operates on the spread value
- [X] T054 [P] [US5] Apply the same independent draw and macro in `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` (lines 257-358)
- [X] T055 [P] [US5] Apply the same treatment to the year-over-year deferral assignment at `dbt/models/intermediate/int_enrollment_events.sql:514-520`, which is coarser still (4 age buckets, no income dimension) and clusters hardest (FR-023)
- [X] T056 [US5] Run the spread-enabled config to `var/652/us5.duckdb` and confirm the cell-distribution and floor assertions pass

**Checkpoint**: Deferral distributions read as elections rather than lookups.

---

## Phase 8: Raise the Deferral Cap

**Purpose**: Kept separate from Phase 7 on purpose. Per decision D7 this moves numbers **on its own**, independently of the spread, because four table cells are currently clamped. Bundling it would make the spread look responsible for a shift it did not cause.

- [X] T057 Change the `voluntary_max_deferral_rate` default from `0.10` to `0.15` in `dbt/dbt_project.yml` and in the Jinja fallbacks in both voluntary models
- [X] T058 Run the unset-rates, spread-disabled config to `var/652/cap.duckdb` and quantify the isolated effect of the cap change against `var/652/baseline_deferral.csv` — expect movement only in the mature/executive, senior/high, senior/moderate, mature/high and senior/executive cells
- [X] T059 Record the measured cap-only delta (headcount affected, average deferral change, employer match cost change) in `specs/652-flat-newhire-enrollment-rates/cap-change-impact.md` for the changelog

**Checkpoint**: The cap change is quantified in isolation and attributable.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T060 [P] Add dbt schema tests for the new columns on `int_voluntary_enrollment_decision` and `int_proactive_voluntary_enrollment` in `dbt/models/intermediate/schema.yml` (existing entries at lines 1971 and 1987)
- [X] T061 [P] Assert zero employees render as `participating - unknown source` in `fct_workforce_snapshot`, confirming the T025 alias fix (quickstart step 6)
- [X] T062 [P] Update the enrollment documentation to state the new meaning of both rates, the unset-versus-set distinction, and the expected outcome distribution (FR-016)
- [X] T063 [P] Document the deferral spread — the floor semantics, the weights, and that it raises average deferral rates by design (FR-017, D6)
- [X] T064 Add a `CHANGELOG.md` entry covering all three accepted behavior changes: Studio scenarios carrying `0.30` change meaning (D1), average deferral rates rise (D6), and the cap raise moves results independently (D7)
- [X] T065 Run the full acceptance sweep from `quickstart.md` steps 3-5 across all three configurations and record the results
- [X] T066 Run `pytest -m fast` and confirm no regression against the suite's current runtime (issue #648 tracks its existing ~4.5 minute duration; this feature must not make it materially worse)
- [X] T067 Verify the dbt invocation count is unchanged against the 38-command production baseline, since no models were added

---

## Dependencies

```
Phase 1 (Baselines)  ──> Phase 2 (Config + multiplier removal)
                              │
                              ├──> Phase 3 (US1 voluntary)  ──┐
                              │                               ├──> Phase 6 (US4 preserved)
                              ├──> Phase 4 (US2 opt-out) ─────┘
                              │        (US2 verification needs US1 for the full split)
                              │
                              ├──> Phase 5 (US3 Studio)       [independent]
                              │
                              └──> Phase 7 (US5 spread)       [independent]
                                        │
                                        └──> Phase 8 (cap raise)
                                                  │
                                                  └──> Phase 9 (Polish)
```

**Story independence**:

- **US1** is fully independent once Phase 2 lands. It is the MVP.
- **US2** is implementable independently, but its headline assertion (the four-way split) needs US1 present to be meaningful. Its own opt-out share is testable alone.
- **US3** touches only Studio files and can proceed in parallel with any backend story.
- **US4** is a verification story with one inspection task; it depends on US1 and US2 being present.
- **US5** touches deferral-rate assignment, which no other story modifies. Fully parallel to US1-US4.

## Parallel Execution Opportunities

- **Phase 1**: T003, T004, T005 all read the same finished database and write separate files.
- **Phase 2**: T006-T008 (tests, same file — write together, they are one edit); T014, T015, T016 touch three different SQL files.
- **Phase 3**: T018-T021 are all in one new test file; write as a unit.
- **Phase 5**: T034 and T040 touch different files from the rest of the Studio work.
- **Phase 7**: T054 and T055 apply the same macro to two different models.
- **Phase 9**: T060-T063 are four independent files.
- **Across phases**: US3 (Studio) and US5 (spread) can run concurrently with US1/US2 by different workstreams, since their file sets are disjoint.

## Implementation Strategy

**MVP**: Phases 1, 2, and 3. That delivers the dial that actually caused the issue — set 60%, get 60% — and is independently shippable.

**Increment 2**: Phase 4, completing the four-way distribution guarantee, plus Phase 6 to confirm nothing else moved.

**Increment 3**: Phase 5, making the controls legible in Studio.

**Increment 4**: Phases 7 and 8, the deferral realism work, which is orthogonal to everything above and carries its own accepted behavior changes.

**Stop conditions**: T017 failing means the research premise about the inert multiplier is wrong — stop and re-derive rather than patching forward. T058 showing movement outside the five expected cells means the cap change has a wider blast radius than analysis predicted.
