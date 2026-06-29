# Tasks: Configurable New-Hire Eligibility Rate + Optional Per-Employee Census Eligibility

**Input**: Design documents from `/specs/103-new-hire-eligibility/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the spec's acceptance criteria explicitly require dbt schema tests, a dbt data test (ineligible → zero enrollment events), and isolated multi-year validation; Constitution Principle III mandates test-first.

**Organization**: Tasks grouped by user story (P1→P3) so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1 / US2 / US3 (Setup/Foundational/Polish carry no story label)
- Exact file paths included.

## Path Conventions

Repo root: `/Users/nicholasamaral/Developer/fidelity_planalign`. dbt commands run from `dbt/` with `--threads 1`. Behavioral validation uses an **isolated** `DATABASE_PATH` DB, never the shared `dbt/simulation.duckdb`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare an isolated validation workspace; no production code yet.

- [X] T001 Create an isolated validation workspace at `/tmp/elig/` with a baseline config copy (`cp config/simulation_config.yaml /tmp/elig/base.yaml`) and confirm `planalign health` passes (no DB locks).
- [X] T002 [P] Build a **pre-change baseline** isolated DB for the byte-for-byte regression check (SC-001): `DATABASE_PATH=/tmp/elig/base.duckdb planalign simulate 2025-2027 --config /tmp/elig/base.yaml --database /tmp/elig/base.duckdb`; snapshot row counts/hashes of `fct_yearly_events` and `fct_workforce_snapshot` to `/tmp/elig/baseline_metrics.txt`.

**Checkpoint**: Isolated workspace + frozen baseline ready.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the single resolution model and wire the eligibility gate everywhere. All three stories depend on this. Under defaults this phase is a **no-op** (every employee resolves `is_plan_ineligible_override = FALSE`).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Create `dbt/models/intermediate/int_plan_eligibility_override.sql` skeleton: incremental model (`delete+insert`, `unique_key=['employee_id','simulation_year']`, `pre_hook` delete for `simulation_year`), unioning census employees (`stg_census_data`, `EMP_*`) and current-year new hires (`int_hiring_events`, `NH_*`) for `{{ var('simulation_year') }}`; output columns `employee_id`, `simulation_year`, `is_plan_ineligible_override` (default `FALSE`), `override_source` (default `NULL`). Per data-model.md.
- [X] T004 [P] Wire the gate into `dbt/models/intermediate/int_enrollment_events.sql`: LEFT JOIN `int_plan_eligibility_override` on `(employee_id, simulation_year)` and change the auto-enrollment eligible flag to `is_eligible AND NOT COALESCE(is_plan_ineligible_override, FALSE)`.
- [X] T005 [P] Wire the same gate into `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` (eligible-employees CTE).
- [X] T006 [P] Wire the same gate into `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql`.
- [X] T007 Suppress + annotate in `dbt/models/intermediate/events/int_eligibility_events.sql`: exclude employees with `is_plan_ineligible_override = TRUE` from `DC_PLAN_ELIGIBILITY` emission, and set `reason='ineligible_override'` + `source` in `event_details` for the suppressed audit annotation (FR-009).
- [X] T008 Register `int_plan_eligibility_override` in `dbt/models/intermediate/schema.yml` (description + columns) and verify it sits upstream of the four consumers in the DAG (`dbt ls --select int_plan_eligibility_override+ --threads 1`), confirming it feeds `fct_yearly_events` via the gated models.
- [X] T009 Foundational no-op verification on the isolated DB: `DATABASE_PATH=/tmp/elig/found.duckdb planalign simulate 2025-2027 --database /tmp/elig/found.duckdb` and diff against `/tmp/elig/baseline_metrics.txt` — expect zero differences (proves the plumbing is inert under defaults).

**Checkpoint**: Resolution model + gates in place and provably inert by default. Story work can begin.

---

## Phase 3: User Story 1 - Model a share of new hires as plan-ineligible (Priority: P1) 🎯 MVP

**Goal**: A single analyst dial (`new_hire_ineligible_pct`) deterministically marks a share of each year's new-hire cohort ineligible, suppressing enrollment/contribution/match.

**Independent Test**: Set the dial to 0.10 on an isolated multi-year run; ~10% of each `NH_*` cohort resolves ineligible with zero enrollment events, reproducible across re-runs; dial 0.0 stays byte-for-byte identical to baseline.

### Tests (write first)

- [X] T010 [P] [US1] Add `tests/test_new_hire_eligibility_config.py`: assert `EligibilitySettings.new_hire_ineligible_pct` rejects values outside `[0.0, 1.0]` (FR-011) and that `to_dbt_vars` exports `new_hire_ineligible_pct` (mark `@pytest.mark.fast`).
- [X] T011 [P] [US1] Add dbt data test `dbt/tests/assert_ineligible_no_enrollment.sql`: fail if any employee with `is_plan_ineligible_override = TRUE` has an enrollment/contribution/employer_match event in `fct_yearly_events` (serves US1 & US2; contracts/dbt-event-contract.md).

### Implementation

- [X] T012 [US1] Add `new_hire_ineligible_pct: float = Field(default=0.0, ge=0.0, le=1.0)` to `EligibilitySettings` in `planalign_orchestrator/config/workforce.py`.
- [X] T013 [US1] Export the var in `planalign_orchestrator/config/export.py` `to_dbt_vars`: `dbt_vars["new_hire_ineligible_pct"] = cfg.eligibility.new_hire_ineligible_pct`.
- [X] T014 [US1] Add the documented default to `config/simulation_config.yaml` under `eligibility:` (`new_hire_ineligible_pct: 0.0`).
- [X] T015 [US1] Implement the `NH_*` branch in `dbt/models/intermediate/int_plan_eligibility_override.sql`: `is_plan_ineligible_override = ABS(MOD(HASH(employee_id || '_eligibility_' || simulation_year), 1000000)) / 1000000.0 < {{ var('new_hire_ineligible_pct', 0.0) }}`, `override_source='new_hire_dial'` when true (research.md Decision 3).

### Validation

- [X] T016 [US1] Isolated multi-year run with dial 0.10 (`/tmp/elig/dial.yaml`): `DATABASE_PATH=/tmp/elig/dial.duckdb planalign simulate 2025-2027 ...`; verify per-year `NH_*` ineligible share ≈ 10% (±1pp, SC-002) via the quickstart query, and re-run to confirm identical selection (reproducibility).
- [X] T017 [US1] Run `pytest -m fast tests/test_new_hire_eligibility_config.py` and `cd dbt && DATABASE_PATH=/tmp/elig/dial.duckdb dbt test --select assert_ineligible_no_enrollment int_plan_eligibility_override --threads 1`; confirm dial 0.0 run still matches `/tmp/elig/baseline_metrics.txt` (SC-001).

**Checkpoint**: US1 is a usable MVP — analysts can model an ineligible new-hire share end-to-end.

---

## Phase 4: User Story 2 - Carry explicit eligibility from the census file (Priority: P2)

**Goal**: An optional `eligibility_override` census column marks specific existing employees eligible/ineligible; absent column → everyone eligible (backward compatible).

**Independent Test**: Provide a census with `eligibility_override = FALSE` for some employees; those never enroll/contribute/receive match across all years; a census without the column behaves unchanged.

### Tests (write first)

- [X] T018 [P] [US2] Add `accepted_values` ([true, false], allow NULL) test for `eligibility_override` to `dbt/models/staging/schema.yml` (contracts/census-schema.md).

### Implementation

- [X] T019 [US2] Add the schema-scaffold + lenient coercion for `eligibility_override` in `dbt/models/staging/stg_census_data.sql`, mirroring `auto_escalation_opt_out`: `NULL::BOOLEAN AS eligibility_override` in the WHERE-false branch and `TRY_CAST(eligibility_override AS BOOLEAN) AS eligibility_override` in the data branch (invalid → NULL → eligible, FR-005/FR-012, Decision 5).
- [X] T020 [US2] Surface a non-fatal import warning for raw values that fail to cast, consistent with existing census field warnings (clarify Decision 5); no row/file rejection.
- [X] T021 [US2] Implement the `EMP_*` census branch in `dbt/models/intermediate/int_plan_eligibility_override.sql`: read `eligibility_override` directly from `stg_census_data` (NOT via `int_employee_compensation_by_year`), set `is_plan_ineligible_override = (eligibility_override = FALSE)`, `override_source='census'` (research.md Decision 2, multi-year-correct).

### Validation

- [X] T022 [US2] Build an isolated census fixture carrying `eligibility_override` (some `FALSE`) and run `DATABASE_PATH=/tmp/elig/census.duckdb planalign simulate 2025-2027 ...`; verify zero enrollment/contribution/match leaks for those employees across all years (SC-003 quickstart zero-leak query), and that classification persists into Year 2+ (FR-010).
- [X] T023 [US2] `cd dbt && DATABASE_PATH=/tmp/elig/census.duckdb dbt test --select stg_census_data int_plan_eligibility_override assert_ineligible_no_enrollment --threads 1`; confirm a census without the column still produces an all-eligible, baseline-identical run.

**Checkpoint**: US1 + US2 independently functional.

---

## Phase 5: User Story 3 - Calibrate the new-hire dial to the census-observed rate (Priority: P3)

**Goal**: A `new_hire_eligibility_match_census` toggle makes the effective new-hire ineligible rate track the census-observed ineligible share (ineligible ÷ total census headcount) instead of the literal dial.

**Independent Test**: With the toggle on and a census carrying a known ineligible share, the realized `NH_*` ineligible share tracks that census rate; with no census column it falls back to the dial.

### Tests (write first)

- [X] T024 [P] [US3] Extend `tests/test_new_hire_eligibility_config.py`: assert `new_hire_eligibility_match_census` defaults to `False` and is exported by `to_dbt_vars`.

### Implementation

- [X] T025 [US3] Add `new_hire_eligibility_match_census: bool = Field(default=False)` to `EligibilitySettings` in `planalign_orchestrator/config/workforce.py`.
- [X] T026 [US3] Export the var in `planalign_orchestrator/config/export.py` `to_dbt_vars`.
- [X] T027 [US3] Add the documented default (`new_hire_eligibility_match_census: false`) to `config/simulation_config.yaml`.
- [X] T028 [US3] Implement the effective-rate branch in `dbt/models/intermediate/int_plan_eligibility_override.sql`: when `{{ var('new_hire_eligibility_match_census', false) }}` and the census carries the column, set the new-hire threshold to `COUNT(eligibility_override = FALSE) / COUNT(*)` over all `stg_census_data` rows; else fall back to `new_hire_ineligible_pct`; tag `override_source='census_match'` (research.md Decision 4). Blank/NULL counted as eligible.

### Validation

- [X] T029 [US3] Isolated run with `new_hire_eligibility_match_census: true` against the US2 census fixture; verify the realized `NH_*` ineligible share tracks the census-observed rate (SC-004), and that a census without the column falls back to the dial value.

**Checkpoint**: All three stories functional and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] Optional Python event-layer parity: add `"ineligible_override"` to `EligibilityPayload.reason` and an optional `source` in `config/events/dc_plan.py` (research.md Decision 8); add a fast event-schema test.
- [ ] T031 [P] Studio UI follow-up: add the "% of new hires not yet eligible" slider + "match census eligibility" toggle to the DC-plan card in `planalign_studio/components/`, with helper text estimating ~X employees/year from prior-year hire count (FR-014). Wire through the existing workspace config API export path.
- [X] T032 [P] Update `CHANGELOG.md` and `config/simulation_config.yaml` inline comments documenting the three new inputs and their no-op defaults.
- [X] T033 Final regression gate: re-run the default-config isolated simulation and confirm byte-for-byte parity with `/tmp/elig/baseline_metrics.txt` (SC-001), and run the full fast suite (`pytest -m fast`) — confirm green.

---

## Dependencies & Story Completion Order

- **Setup (T001–T002)** → **Foundational (T003–T009)** must complete before any story.
- **US1 (T010–T017)**: depends only on Foundational. This is the MVP.
- **US2 (T018–T023)**: depends on Foundational. Independent of US1 except both edit `int_plan_eligibility_override.sql` (T015 vs T021) — sequence those two; otherwise parallelizable with US1.
- **US3 (T024–T029)**: depends on Foundational; T028 builds on the model branches (best after T015/T021 exist, since it overrides the new-hire threshold). Census-matching is most meaningful once US2's column exists.
- **Polish (T030–T033)**: after the stories it documents/extends.

**Shared-file note**: T015 (US1), T021 (US2), and T028 (US3) all edit `int_plan_eligibility_override.sql` → NOT parallel; apply in order T015 → T021 → T028.

## Parallel Execution Examples

- **Foundational gate wiring**: T004, T005, T006 touch three different models → run in parallel after T003.
- **US1 tests**: T010 (Python) and T011 (dbt SQL) are different files → parallel.
- **US1 config plumbing**: T012 (`workforce.py`) and T013 (`export.py`) → parallel.
- **Polish**: T030, T031, T032 are independent files → parallel.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: delivers the analyst dial end-to-end with regression safety — the highest-value, most-common sponsor need.
- **Incremental**: add US2 (per-employee census control), then US3 (census calibration). Each is an independently shippable increment behind a no-op default, so partial delivery never changes existing simulation output.
- **Validation discipline**: every behavioral check runs on an isolated `DATABASE_PATH` DB over a full `simulate 2025-2027`, never the shared dev DB (CLAUDE.md §8).
