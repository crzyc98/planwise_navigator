---
description: "Task list for Voluntary-Enrollment Match-Magnet Dial & Ceiling Fidelity"
---

# Tasks: Voluntary-Enrollment Match-Magnet Dial & Match-Ceiling Fidelity

**Input**: Design documents from `/specs/102-match-magnet-dial/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution Principle III (Test-First) is mandatory for this repo. Failing tests precede implementation within each story.

**Organization**: Tasks grouped by user story (US1 → US3, priority order) so each is an independently testable increment.

## Path Conventions

Existing monorepo. dbt models in `dbt/models/`, macros in `dbt/macros/`, defaults in `dbt/dbt_project.yml`; Python config in `planalign_orchestrator/config/`; Studio UI in `planalign_studio/components/config/`; Python tests in `tests/`.

**Validation rule (all stories)**: validate in isolated DBs (`planalign batch … --clean` or `DATABASE_PATH=…`), never the shared `dbt/simulation.duckdb`; run the full multi-year horizon. See `quickstart.md`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding for validation and tests.

- [X] T001 [P] Create the new Python test module skeleton `tests/test_config_export_match_magnet.py` with `pytest` markers (`fast`, `config`) and imports for `SimulationConfig` / export helpers.
- [ ] T002 [P] Add two isolated validation scenarios `scenarios/match_ceiling_6.yaml` and `scenarios/match_ceiling_10.yaml` (no auto-enrollment, stretch/simple match at 50%-on-6% vs 50%-on-10%, identical `random_seed`, voluntary enrollment rate holding ~baseline participation) per `quickstart.md` step 1.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared macros + default vars that all three stories depend on. Replaces the duplicated inline magnet logic in both voluntary models with macro calls, preserving current behavior via defaults (Constitution Principle II).

⚠️ MUST complete before US1/US2/US3 implementation.

- [X] T003 Add `voluntary_max_deferral_rate: 0.10` to the `vars:` block in `dbt/dbt_project.yml` (alongside existing `enrollment_match_magnet_*` at lines ~313-314), with an inline comment describing it as the voluntary deferral cap.
- [X] T004 Create macro `dbt/macros/resolve_match_magnet_ceiling.sql` implementing the contract in `contracts/dbt-vars.md`: dispatch by `employer_match_status` → deferral_based returns the scalar arg; `graded_by_service`/`tenure_graded` call `get_tiered_match_max_deferral(years_of_service_col, employer_match_graded_schedule, default)`; `points_based` calls the points max-deferral macro over `points_match_tiers`; disabled/unknown returns `0`.
- [X] T005 Create macro `dbt/macros/apply_match_magnet.sql` implementing `apply_match_magnet(selected_rate, ceiling, snap_random, enabled, snap_prob, floor, cap)` → snap CASE then `GREATEST(floor, LEAST(cap, snapped))`, per `contracts/dbt-vars.md`.
- [X] T006 Refactor `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` to compute the ceiling via `resolve_match_magnet_ceiling(...)` and produce the final rate via `apply_match_magnet(...)` (cap = `var('voluntary_max_deferral_rate', 0.10)`, floor = `0.01`), removing the inline `match_optimization` CASE and the `GREATEST(0.01, LEAST(0.10, …))` clamp. Preserve audit columns `raw_deferral_rate` / `match_optimized_rate`.
- [X] T007 Apply the identical refactor to `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` (lines ~287-294 snap, ~336 clamp), using the same macros so both paths stay consistent.

**Checkpoint**: Both models compile and, with default vars, reproduce current behavior (no functional change yet — the always-on ceiling fix lands in US1).

---

## Phase 3: User Story 1 — Match ceiling drives voluntary deferral selection (Priority: P1) 🎯 MVP

**Goal**: The deferral rate enrollees snap to tracks the active employer-match ceiling, independent of `deferral_match_response`, across all match modes.

**Independent Test**: Run `match_ceiling_6` vs `match_ceiling_10` in isolated DBs; average voluntary deferral and the 10%+ share are strictly higher in the 10% scenario (`quickstart.md` step 2). Pre-fix they are identical.

### Tests (write first — must fail)

- [X] T008 [P] [US1] In `tests/test_config_export_match_magnet.py`, add a failing test asserting `_export_employer_match_vars(cfg)` includes `employer_match_max_deferral_rate` equal to the active formula's ceiling **when `deferral_match_response` is absent/disabled** (FR-003), for both a simple (max_match_percentage) and tiered/stretch (top-tier `employee_max`) formula.
- [X] T009 [P] [US1] Add a failing test asserting the exported ceiling changes from 0.06 → 0.10 when the active formula's ceiling changes 6% → 10% (FR-002).

### Implementation

- [X] T010 [US1] Extract the formula→ceiling computation (currently `export.py:1188-1212` inside `_export_deferral_match_response_vars`) into a reusable helper and call it from `_export_employer_match_vars` in `planalign_orchestrator/config/export.py`, exporting `employer_match_max_deferral_rate` whenever a match is configured (not gated on DMR).
- [X] T011 [US1] Keep `deferral_match_response_match_max_rate` as a backward-compatible alias in `_export_deferral_match_response_vars` (delegating to the shared helper); confirm `dbt/models/intermediate/events/int_deferral_match_response_events.sql` still resolves it (per research.md open item).
- [X] T012 [US1] Update the `deferral_based` ceiling resolution in both voluntary models / the `resolve_match_magnet_ceiling` call sites to prefer `var('employer_match_max_deferral_rate')` (precedence: new var → legacy DMR var → `max(employee_max over match_tiers)` → hard default), per `contracts/dbt-vars.md` rule 1.
- [X] T013 [US1] Ensure both voluntary models expose `years_of_service`/age-derived service and a points expression so `resolve_match_magnet_ceiling` can resolve per-employee ceilings for `graded_by_service`/`tenure_graded`/`points_based` (clarification B). Add a `match_magnet_ceiling` audit column to both models.

### Validation

- [X] T014 [US1] Run `quickstart.md` step 2 against isolated `match_ceiling_6.duckdb` / `match_ceiling_10.duckdb`; confirm SC-001 (avg deferral higher) and SC-002 (10%+ share higher) in the 10% scenario.
- [ ] T015 [P] [US1] Run `quickstart.md` "Mode coverage" for `graded_by_service`, `tenure_graded`, `points_based`, confirming the per-employee ceiling drives snapping in each mode.

**Checkpoint**: US1 is independently shippable — the correctness bug is fixed using default dial values.

---

## Phase 4: User Story 2 — Analyst can tune the match-magnet dial per scenario (Priority: P2)

**Goal**: Surface the magnet enable toggle and snap fraction in config + Studio UI, carried through scenario copy, defaults preserving current behavior.

**Independent Test**: Change the controls (toggle off; sweep snap fraction) in an isolated scenario and confirm the deferral distribution shifts as expected with no code changes (`quickstart.md` step 3).

### Tests (write first — must fail)

- [X] T016 [P] [US2] Add a failing test in `tests/test_config_export_match_magnet.py` asserting `_export_enrollment_vars(cfg)` emits `enrollment_match_magnet_enabled` and `enrollment_match_magnet_probability` from a YAML `enrollment.match_magnet` block.
- [X] T017 [P] [US2] Add a failing test asserting dc_plan keys `match_magnet_enabled` / `match_magnet_probability` (UI percent → decimal) map to the same dbt vars and take precedence over YAML defaults.

### Implementation (config)

- [X] T018 [US2] Add `MatchMagnetSettings` (fields `enabled`, `snap_probability`) and attach it to `EnrollmentSettings` in `planalign_orchestrator/config/workforce.py` per `contracts/config-schema.md` (bounds `ge/le`).
- [X] T019 [US2] Emit `enrollment_match_magnet_enabled` / `enrollment_match_magnet_probability` from `cfg.enrollment.match_magnet` in `_export_enrollment_vars`, and map the dc_plan keys in `_apply_dc_plan_enrollment_overrides` (`planalign_orchestrator/config/export.py`).
- [X] T020 [P] [US2] Add a commented `enrollment.match_magnet` example block to `config/simulation_config.yaml`.

### Implementation (Studio UI)

- [X] T021 [P] [US2] Add form fields `dcMatchMagnetEnabled` (default true) and `dcMatchMagnetProbability` (default 45) to `planalign_studio/components/config/types.ts` and `constants.ts`.
- [X] T022 [US2] Add the magnet enable toggle + snap-probability % input to `planalign_studio/components/config/DCPlanSection.tsx` (disable the % input when toggle is off).
- [X] T023 [US2] Serialize `match_magnet_enabled` / `match_magnet_probability` (`/100`) into the `dc_plan` payload in `planalign_studio/components/config/buildConfigPayload.ts`.
- [X] T024 [US2] Load existing scenario values for the two fields in `planalign_studio/components/config/ConfigContext.tsx`.
- [X] T025 [US2] Carry the two new fields in `planalign_studio/components/config/CopyScenarioModal.tsx` (FR-005 — mirrors the #326/#327 voluntary-enrollment-rate copy fix).

### Validation

- [ ] T026 [US2] Run `quickstart.md` step 3 (sweep `snap_probability` 0.20/0.45/0.80 and `enabled:false`) in isolated DBs; confirm higher fractions raise the ceiling share/avg deferral and disabled produces no snapping (SC-003, FR-007).

**Checkpoint**: Analysts can steer magnet behavior end-to-end (file + UI + copy).

---

## Phase 5: User Story 3 — Deferral selection can reach the configured ceiling (Priority: P3)

**Goal**: Replace the hard 10% artifact with a per-scenario maximum employee deferral % so ceilings ≥10% populate the 10%+ band.

**Independent Test**: With ceiling 10% and `max_deferral_rate` 0.10, snapped enrollees appear at 10% in the distribution (`quickstart.md` step 4).

### Tests (write first — must fail)

- [X] T027 [P] [US3] Add a failing test in `tests/test_config_export_match_magnet.py` asserting `enrollment.match_magnet.max_deferral_rate` and dc_plan `max_voluntary_deferral_percent` both export `voluntary_max_deferral_rate` (default 0.10, percent→decimal for UI).

### Implementation

- [X] T028 [US3] Add `max_deferral_rate` (default `0.10`, `ge=0.01, le=1.0`) to `MatchMagnetSettings` in `planalign_orchestrator/config/workforce.py`.
- [X] T029 [US3] Export `voluntary_max_deferral_rate` from `cfg.enrollment.match_magnet.max_deferral_rate` and map dc_plan `max_voluntary_deferral_percent` in `planalign_orchestrator/config/export.py` (the SQL clamp already reads this var from Phase 2).
- [X] T030 [P] [US3] Add form field `dcMaxVoluntaryDeferral` (default 10) to `types.ts`/`constants.ts`, a % input in `DCPlanSection.tsx`, payload key `max_voluntary_deferral_percent` (`/100`) in `buildConfigPayload.ts`, loading in `ConfigContext.tsx`, and copy in `CopyScenarioModal.tsx`.

### Validation

- [ ] T031 [US3] Run `quickstart.md` step 4 with a 10% ceiling in an isolated DB; confirm snapped enrollees land at 10% (not capped below). Then set ceiling/`max_deferral_rate` to 12% and confirm rates reach 12%.

**Checkpoint**: High-ceiling designs report correctly in the 10%+ band.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 [P] Add/extend dbt schema tests in `dbt/models/intermediate/schema.yml` for both voluntary models: `selected_deferral_rate`/`proactive_deferral_rate` within `[0.01, voluntary_max_deferral_rate]`, and `match_magnet_ceiling` not-null/non-negative.
- [ ] T033 Run the backward-compatibility regression (`quickstart.md` step 5) in an isolated DB — an existing scenario setting none of the new fields reproduces its pre-change voluntary-deferral distribution exactly (SC-004).
- [ ] T034 [P] Run the reproducibility check (`quickstart.md` step 6): same scenario + seed twice → identical distributions (SC-005, FR-010).
- [ ] T035 [P] Document the match-magnet controls (location, meaning, defaults, interaction with the match ceiling) for analysts — update the DC plan / enrollment section of the relevant docs (FR-012, SC-006).
- [ ] T036 Run `pytest -m "fast and config"` and `cd dbt && dbt build --threads 1 --fail-fast` against an isolated DB to confirm no regressions before PR.

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001–T002 — no dependencies, both [P].
- **Foundational (Phase 2)**: T003–T007 — block all stories. T003/T004/T005 are [P] among themselves; T006/T007 depend on T004+T005 (and T003 for the cap var).
- **US1 (Phase 3)**: depends on Foundational. Delivers the MVP fix. T008/T009 (tests) before T010–T013; T010 before T011/T012; validation T014/T015 last.
- **US2 (Phase 4)**: depends on Foundational; independent of US1 (uses default ceiling) but best sequenced after US1 so the dial tunes a correct ceiling. Tests T016/T017 before T018–T025.
- **US3 (Phase 5)**: depends on Foundational (T003 + T006/T007 clamp). Independent of US1/US2. T027 before T028–T030.
- **Polish (Phase 6)**: after the stories it validates.

### Story independence

- US1 testable with default dial values (no config/UI work).
- US2 testable by toggling/sweeping the dial against any ceiling.
- US3 testable by raising the cap with any ceiling ≥10%.

## Parallel Execution Examples

- **Phase 1**: T001 ∥ T002.
- **Phase 2**: T003 ∥ T004 ∥ T005 (distinct files), then T006 ∥ T007.
- **US1 tests**: T008 ∥ T009. **US1 validation**: T014 then T015 [P].
- **US2**: T016 ∥ T017 (tests); UI T021 [P] then T022–T025; config T018→T019, T020 [P].
- **Polish**: T032 ∥ T034 ∥ T035.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + US1 (T001–T015)**: fixes the correctness defect (match ceiling drives deferral selection in all modes) using existing default dial values. Independently shippable.
- **Increment 2 = US2**: expose the dial for analyst intervention.
- **Increment 3 = US3**: configurable cap to populate the 10%+ band.
- **Finalize = Phase 6**: schema tests, regression/reproducibility/backward-compat, docs.
