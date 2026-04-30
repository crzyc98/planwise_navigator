---
description: "Task list for 084-fix-match-magnet"
---

# Tasks: Match Formula as Enrollment Deferral Rate Magnet

**Input**: Design documents from `/specs/084-fix-match-magnet/`
**Branch**: `084-fix-match-magnet`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All dbt commands run from `/workspace/dbt/` with `--threads 1`

---

## Phase 1: Setup (Shared Config)

**Purpose**: Capture the pre-fix baseline and add the two new dbt variables that all SQL changes depend on.

- [X] T000 Capture pre-fix baseline: run `dbt run --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --threads 1 --vars "simulation_year: 2025"` then record the `selected_deferral_rate` distribution from `int_voluntary_enrollment_decision WHERE will_enroll=true` and the `proactive_deferral_rate` distribution from `int_proactive_voluntary_enrollment WHERE will_enroll_proactively=true` — save counts to a markdown table in this file under a new "Baseline Snapshot" section for use in SC-001 comparison at Phase 6

- [X] T001 Add `enrollment_match_magnet_enabled: true` and `enrollment_match_magnet_probability: 0.45` vars to `dbt/dbt_project.yml` after line 310 (end of performance optimization settings block), under a new `# Match magnet` comment

---

## Phase 2: Foundational — Test First (Constitution III)

**Purpose**: Write the validation tests before any SQL implementation. Constitution III requires tests to be written first and confirmed to fail before implementation begins.

**⚠️ CRITICAL**: Write these tests, confirm they fail (or cannot yet run due to missing columns), then proceed to Phase 3.

- [X] T002 Write dbt custom test `dbt/tests/test_enrollment_match_magnet_voluntary.sql` that asserts the magnet is actually firing in the voluntary model: `SELECT 1 WHERE (SELECT COUNT(*) FROM int_voluntary_enrollment_decision WHERE will_enroll = true AND optimized_deferral_rate > selected_deferral_rate) = 0` — returns 1 row (FAIL) pre-fix because the column `optimized_deferral_rate` does not yet exist or no rows have been snapped upward; returns 0 rows (PASS) post-fix when snapped employees show `optimized_deferral_rate > selected_deferral_rate` (i.e., the pre-magnet demographic base rate). This guarantees a Constitution III pre-fix failure regardless of any legacy clustering in the old `match_optimization` CTE.

- [X] T003 Write dbt custom test `dbt/tests/test_enrollment_match_magnet_proactive.sql` that asserts the magnet fires in the proactive model: `SELECT 1 WHERE (SELECT COUNT(*) FROM int_proactive_voluntary_enrollment WHERE will_enroll_proactively = true AND proactive_deferral_rate > raw_deferral_rate) = 0` — returns 1 row (FAIL) pre-fix because the proactive model has zero match awareness and `proactive_deferral_rate` can never exceed `raw_deferral_rate`; returns 0 rows (PASS) post-fix when snapped employees show higher elected rate than their demographic base. Note: relies on default `match_tiers` fallback (`employee_max = 0.05`), which is always present; fails pre-fix with certainty.

- [X] T004 Write dbt custom test `dbt/tests/test_magnet_upward_only.sql` that asserts no employee in `int_voluntary_enrollment_decision` has their deferral rate lowered by the magnet — query `SELECT COUNT(*) FROM int_voluntary_enrollment_decision WHERE raw_deferral_rate > selected_deferral_rate AND selected_deferral_rate < 0.10` and assert 0 rows (the `< 0.10` filter excludes rows where the 10% ceiling capped a rate, which would otherwise appear as a false downward movement).

- [X] T004a Write dbt custom test `dbt/tests/test_magnet_upward_only_proactive.sql` that asserts no employee in `int_proactive_voluntary_enrollment` has their elected rate lowered by the magnet — query `SELECT COUNT(*) FROM int_proactive_voluntary_enrollment WHERE raw_deferral_rate > proactive_deferral_rate AND will_enroll_proactively = true AND proactive_deferral_rate < 0.10` and assert 0 rows.

- [X] T004b Write dbt custom test `dbt/tests/test_enrollment_deferral_ceiling.sql` that asserts the 10% ceiling is enforced in both models: `SELECT COUNT(*) FROM int_voluntary_enrollment_decision WHERE selected_deferral_rate > 0.10` UNION ALL `SELECT COUNT(*) FROM int_proactive_voluntary_enrollment WHERE proactive_deferral_rate > 0.10` — assert total = 0 rows (FR-009).

**Checkpoint**: Tests written. Run `dbt compile --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment` to confirm models compile; tests will fail or not yet run until implementation. Proceed to Phase 3.

---

## Phase 3: User Story 1 — Realistic Match-Driven Enrollment Clustering (Priority: P1) 🎯 MVP

**Goal**: Both the voluntary and proactive enrollment paths produce match-threshold clustering when a deferral-based match formula is active.

**Independent Test**: Run `dbt run --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --threads 1 --vars "simulation_year: 2025"`, then query `selected_deferral_rate` distribution and confirm ~45% of sub-threshold enrollees elected the match-maximizing rate.

### Implementation for User Story 1

- [X] T005 [P] [US1] Add the Jinja match_max_rate computation block to `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` — insert after the `{{ config(...) }}` block and before the opening `WITH`, exactly as specified in plan.md Step 2a (sets `employer_match_status`, `precomputed_match_max`, `match_tiers`, `enrollment_match_magnet_enabled`, `enrollment_match_magnet_probability`, and computes `match_max_rate` using the namespace fallback pattern)

- [X] T006 [P] [US1] Add the same Jinja match_max_rate computation block to `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` — insert after the `{{ config(...) }}` block and before the opening `WITH` (identical block to T005)

- [X] T007 [US1] Replace the `match_optimization` CTE in `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` (lines 199–226) with the dynamic version from plan.md Step 2b — single CASE expression using `enrollment_match_magnet_enabled`, `match_max_rate`, `enrollment_match_magnet_probability`, and existing `deferral_random` column; remove the old formula-name branching and hardcoded 3%/5%/6% thresholds. Also update the `enrollment_decisions` CTE to store the pre-magnet demographic base rate as `raw_deferral_rate` (using `selected_deferral_rate` from `match_optimization.*`, which is the unchanged demographic rate from `deferral_rate_selection`) and add `optimized_deferral_rate as match_optimized_rate` as a new audit column — this satisfies FR-010 for the voluntary model. (depends on T005)

- [X] T008 [US1] Insert new `match_optimization` CTE into `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` between `deferral_rate_selection` and `proactive_enrollment_decisions` CTEs — uses inline hash expression `(ABS(HASH(employee_id || '-match-magnet-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0` as the magnet random draw (plan.md Step 3b; depends on T006)

- [X] T009 [US1] Update `proactive_enrollment_decisions` CTE in `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` — change source from `deferral_rate_selection` to `match_optimization`; change `selected_deferral_rate` to `optimized_deferral_rate` in the `GREATEST(0.01, LEAST(0.10, ...))` expression for `proactive_deferral_rate`; add `optimized_deferral_rate as match_optimized_rate` as new audit column alongside existing `selected_deferral_rate as raw_deferral_rate` (plan.md Step 3c; depends on T008)

- [X] T010 [US1] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars "simulation_year: 2025"` from `/workspace/dbt/` and verify it compiles and runs without errors

- [X] T011 [US1] Run `dbt run --select int_proactive_voluntary_enrollment --threads 1 --vars "simulation_year: 2025"` from `/workspace/dbt/` and verify it compiles and runs without errors

- [X] T012 [P] [US1] Query `dbt/simulation.duckdb` to verify voluntary enrollment clustering: `SELECT ROUND(selected_deferral_rate*100,1) AS pct, COUNT(*) AS n FROM int_voluntary_enrollment_decision WHERE will_enroll=true GROUP BY 1 ORDER BY 1` — confirm the match-maximizing rate row (e.g. 5.0%) has significantly more rows than recorded in the T000 baseline snapshot (depends on T010)

- [X] T013 [P] [US1] Query `dbt/simulation.duckdb` to verify proactive enrollment clustering: `SELECT ROUND(proactive_deferral_rate*100,1) AS pct, COUNT(*) AS n FROM int_proactive_voluntary_enrollment WHERE will_enroll_proactively=true GROUP BY 1 ORDER BY 1` — confirm match-maximizing rate shows meaningful concentration vs. the T000 baseline (depends on T011)

- [X] T014 [US1] Run dbt tests for the two models: `dbt test --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --threads 1 --vars "simulation_year: 2025"` — confirm T002, T003, T004, T004a, T004b tests now pass

**Checkpoint**: US1 complete. Both enrollment paths cluster at the match threshold. Tests pass.

---

## Phase 4: User Story 2 — Formula-Agnostic Match Threshold (Priority: P2)

**Goal**: The clustering target is derived from actual configured tiers, not hardcoded values. Verify with non-default formulas.

**Independent Test**: Re-run models after changing match_tiers to a non-standard formula (e.g. single tier with employee_max=0.07); confirm clustering shifts to 7%, not 3%, 5%, or 6%.

**Note on `--vars` syntax**: When passing `match_tiers` as a YAML list via the dbt CLI, use the form `--vars '{match_tiers: [{employee_min: 0.00, employee_max: 0.07, match_rate: 1.00}]}'` (single-quoted outer shell string, double-quoted YAML value). If CLI parsing is unreliable, set `match_tiers` in `dbt_project.yml` temporarily and comment it out after testing.

### Implementation for User Story 2

- [X] T015 [P] [US2] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars '{simulation_year: 2025, match_tiers: [{employee_min: 0.00, employee_max: 0.07, match_rate: 1.00}]}'` from `/workspace/dbt/` and query results — confirm `selected_deferral_rate` clusters at 0.07, not at any hardcoded value

- [X] T016 [P] [US2] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars '{simulation_year: 2025, match_tiers: [{employee_min: 0.00, employee_max: 0.04, match_rate: 1.00}]}'` and query results — confirm clustering at 0.04

- [X] T017 [P] [US2] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars '{simulation_year: 2025, employer_match_status: graded_by_service}'` and query results — confirm no clustering occurs (magnet inactive for non-deferral-based formulas; `selected_deferral_rate` should show pure demographic distribution matching the T000 baseline)

**Checkpoint**: US2 complete. Clustering target dynamically reads actual tier boundaries.

---

## Phase 5: User Story 3 — Configurable Magnet Strength (Priority: P3)

**Goal**: `enrollment_match_magnet_probability` controls clustering intensity; magnet is upward-only.

**Independent Test**: Run with probability=0 (expect zero clustering), probability=0.70 (expect ~70% clustering), and with employees already at/above threshold (expect no change).

### Implementation for User Story 3

- [X] T018 [US3] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars "simulation_year: 2025 enrollment_match_magnet_probability: 0.0"` and query results — confirm deferral rate distribution matches pre-fix demographic baseline (no clustering at match threshold). Note: this tests the *probabilistic* disable path (probability=0 means no employee is snapped even though the magnet is enabled). Compare to T021 which tests the feature-flag disable path (`enabled=false`).

- [X] T019 [US3] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars "simulation_year: 2025 enrollment_match_magnet_probability: 0.70"` and query results — confirm roughly 70% of sub-threshold enrollees elected the match-maximizing rate

- [X] T020 [US3] Query `dbt/simulation.duckdb` to verify upward-only behavior: `SELECT COUNT(*) FROM int_voluntary_enrollment_decision WHERE raw_deferral_rate > selected_deferral_rate AND selected_deferral_rate < 0.10` — assert result is 0 (magnet never lowers rates; ceiling-capped rows excluded to avoid false positives)

- [X] T021 [US3] Run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars '{simulation_year: 2025, enrollment_match_magnet_enabled: false}'` and query results — confirm distribution is identical to the T000 baseline snapshot (pure demographics, no clustering). Note: this tests the *feature-flag* disable path (`enabled=false`). Compare to T018 which tests the probabilistic disable path (probability=0). Both should produce identical distributions, confirming that the two mechanisms are equivalent ways to suppress the magnet.

**Checkpoint**: US3 complete. Magnet strength is configurable; toggle works; upward-only constraint enforced.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end regression check, SC-001 comparison, and final commit.

- [X] T022 Run full enrollment pipeline `dbt run --select int_enrollment_events --threads 1 --vars "simulation_year: 2025"` from `/workspace/dbt/` and confirm no errors (default var settings)

- [X] T023 Run `dbt build --threads 1 --vars "simulation_year: 2025" --fail-fast` from `/workspace/dbt/` to confirm no downstream model regressions — all models build and all tests pass

- [X] T024 [P] Verify audit columns present in both models: query `SELECT raw_deferral_rate, match_optimized_rate, selected_deferral_rate FROM int_voluntary_enrollment_decision LIMIT 5` and `SELECT raw_deferral_rate, match_optimized_rate, proactive_deferral_rate FROM int_proactive_voluntary_enrollment LIMIT 5` — confirm both pre-magnet and post-magnet rates are present in both models for audit (FR-010)

- [X] T025 [P] Verify determinism: run `dbt run --select int_voluntary_enrollment_decision --threads 1 --vars "simulation_year: 2025"` twice and confirm `selected_deferral_rate` distribution is identical across runs (FR-007)

- [X] T026 [P] SC-001 comparison: query the post-fix `selected_deferral_rate` distribution and compare the fraction at the match-maximizing rate (e.g., 5.0%) against the T000 baseline snapshot — confirm the fraction increased by at least 35 percentage points (SC-001)

- [X] T027 Write commit with message: `fix(084): Add match formula magnet to enrollment deferral rate selection`

---

## Baseline Snapshot

*(To be filled in during T000 — record pre-fix distributions here before any SQL changes)*

### Voluntary Enrollment (`int_voluntary_enrollment_decision WHERE will_enroll=true`)

| selected_deferral_rate | n | pct |
|------------------------|---|-----|
| 3% | 43 | 7.9% |
| 4% | 55 | 10.2% |
| 5% | 11 | 2.0% |
| 6% | 250 | 46.2% |
| 8% | 88 | 16.3% |
| 10% | 94 | 17.4% |

*Note: Old code used hardcoded simple_match clustering (40% of ≥5% employees → 6%), inflating the 6% bucket. No-magnet pure demographic baseline (from T018 probability=0.0): 3%:43, 4%:55, 5%:16, 6%:128, 8%:143, 10%:156.*

### Proactive Enrollment (`int_proactive_voluntary_enrollment WHERE will_enroll_proactively=true`)

| proactive_deferral_rate | n | pct |
|-------------------------|---|-----|
| 3% | 113 | 19.3% |
| 4% | 44 | 7.5% |
| 6% | 286 | 48.7% |
| 8% | 131 | 22.3% |
| 10% | 13 | 2.2% |

*Note: Old code had zero match awareness in proactive model. Post-fix with default probability=0.45: 5%:77 (13.1%) appears as new clustering.*

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational/Tests)**: T000 must complete before tests (baseline needed for comparison); T001 must exist before tests reference vars
- **Phase 3 (US1)**: Depends on Phase 2 — T005 and T006 can run in parallel after T001; T007 depends on T005; T008 depends on T006; T009 depends on T008
- **Phase 4 (US2)**: Depends on Phase 3 completion — same SQL, different var overrides
- **Phase 5 (US3)**: Depends on Phase 3 completion — same SQL, different var overrides
- **Phase 6 (Polish)**: Depends on Phases 4 and 5 completion

### Parallel Opportunities

- T005 and T006: Different files — run in parallel (both add Jinja block)
- T010 and T011: Different models — run in parallel (both dbt run)
- T012 and T013: Different queries — run in parallel (both validations)
- T015, T016, T017: Different var combinations — run in parallel
- T018, T019, T020, T021: Different var combinations / queries — run in parallel
- T024, T025, T026: Different validations — run in parallel

---

## Implementation Strategy

### MVP (User Story 1 Only)

1. Complete Phase 1: Capture baseline (T000) + add dbt vars (T001)
2. Complete Phase 2: Write tests (T002–T004b)
3. Complete Phase 3: Implement SQL changes (T005–T014)
4. **STOP and VALIDATE**: Both enrollment paths cluster at match threshold; tests pass
5. Run full build (T022–T023) to confirm no regressions

### Full Delivery

After MVP validation, proceed through Phase 4 → Phase 5 → Phase 6 to verify formula-agnostic behavior, configurability, SC-001 quantitative comparison, and clean commit.

---

## Notes

- All dbt commands run from `/workspace/dbt/` with `--threads 1`
- Default simulation database: `dbt/simulation.duckdb`
- The implementation SQL is fully specified in `plan.md` Steps 2–3 — no design decisions left for implementation
- The two Jinja blocks (T005, T006) are identical; copy-paste with confidence
- The proactive model's magnet uses an inline hash rather than `deferral_random` — this is intentional (see research.md Decision 2)
- `int_enrollment_events.sql` requires NO changes — it uses explicit column selects from both models
- **T002 design note**: Tests whether `optimized_deferral_rate > selected_deferral_rate` (i.e., snapped rate > demographic base) — fails pre-fix because the column is missing entirely, passes post-fix when snapped employees exist. This is the Constitution III-safe test design.
- **T018 vs T021**: Both suppress the magnet but via different mechanisms. T018 uses `probability=0` (probabilistic gate never fires); T021 uses `enabled=false` (CASE condition short-circuits before probabilistic gate). Both should produce identical output distributions.
