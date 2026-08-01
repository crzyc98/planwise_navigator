---
description: "Task list for 130-promotion-fit-bias"
---

# Tasks: Trustworthy Promotion Rate from a Census Without Job Levels

**Input**: Design documents from `/specs/130-promotion-fit-bias/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED for this feature. FR-013 mandates graded recovery tests, and Constitution III mandates test-first development. Every implementation task below is preceded by its failing test.

**Organization**: Grouped by user story. See "Story independence — an honest note" before planning delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: US1–US4, mapping to spec.md user stories
- All paths are repository-relative from `/Users/nicholasamaral/Developer/fidelity_planalign`

---

## Story independence — an honest note

The template assumes each user story is a viable standalone increment. That holds for US3 and US4 here, but **not for US1 and US2**, and pretending otherwise would produce a bad delivery plan.

US1 (accurate rate) and US2 (know when it can't be trusted) are two halves of one estimator. Shipping US1 alone would publish a mixture-derived promotion rate for *every* level, including levels where the components did not separate — which is a differently-wrong number in place of today's wrong number, and the exact failure the spec calls "wrong-but-confident." The spec says so directly: US2 "must ship with it."

The split below is still real and useful: US1 builds the estimator and produces the separation *statistics*; US2 turns those statistics into *policy* (verdict, exposure gate, default retention, disclosure). US1 is independently testable — recovery to 6% is a meaningful checkpoint. It is just not independently *shippable*.

**MVP = Phase 2 + Phase 3 + Phase 4 (Foundational + US1 + US2).**

---

## Phase 1: Setup

**Purpose**: Establish the baseline this feature is judged against, before anything changes.

- [X] T001 Write and run the bias reproduction script from quickstart.md; record the observed promotion rate on a level-stripped synthetic census. **MEASURED before: 0.0911 (3 snapshots) / 0.1524 (5). After: 0.0590 / 0.0594 against a truth of 0.06.** — the bias compounds with history length. Issue #511's 16.8% is consistent with a longer history, not the 3-snapshot default. Spec updated (SC-001, SC-001a).
- [X] T002 [P] Generate a golden clean-path parameter pack from `main` into `/tmp/pack-main` using a census that retains `level_id`, for the SC-005 parity comparison in T012

**Checkpoint**: The number to beat is recorded, and a byte-comparable pre-change artifact exists.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The grading harness and the shared plumbing every story depends on.

**⚠️ CRITICAL**: T003 blocks everything. Per research.md R-7 the synthetic fixture currently emits raises with **zero variance** (`tests/fixtures/synthetic_census.py:144` gives every non-promoted survivor exactly `merit + cola` and every promoted one exactly `promotion_raise`). Two point masses make a mixture test trivially passable, make `sigma → 0` a division by zero in the separation statistic, and make the US2 inseparable case unconstructible. No test in this feature grades anything until this lands.

- [X] T003 Add `merit_sigma` (default 0.015) and `promotion_sigma` (default 0.04) to `TruthRates` and apply deterministic lognormal jitter to `raise_pct` in `_advance_year` in `tests/fixtures/synthetic_census.py`, drawing from the existing seeded `rng` so the fixture stays reproducible
- [X] T004 [P] Add `TestSyntheticFixture` to `tests/test_parameter_fitting.py` asserting observed raise growth has non-zero standard deviation, that two `generate_history` calls with the same seed produce identical files, and that the existing `test_merit_recovered_per_level` still passes under dispersion
- [X] T005 [P] Add `PromotionBasis` enum, `LevelSeparation` and `PromotionClassification` frozen dataclasses to `planalign_fit/models.py` per data-model.md, and add `promotion_classification: Optional[PromotionClassification] = None` to `FitResult`
- [X] T006 [P] Expose `promotion_compensation.base_increase_pct` (default 0.20) through `planalign_fit/priors.py` for EM initialization, reading it via the existing `Priors.config_value` accessor — no new seed file or loader
- [X] T007 Add a `promotion_weight DOUBLE` column to `_pair_transition_sql` in `planalign_fit/transitions.py` with measured semantics only (`CASE WHEN promoted THEN 1.0 ELSE 0.0 END`), plus a test asserting the `0.0 <= promotion_weight <= 1.0` invariant holds for every row
- [X] T008 [P] Change `hazards.load_cells` in `planalign_fit/hazards.py` to take a weight expression instead of an event predicate (`SUM(promotion_weight)` in place of `SUM(CASE WHEN promoted THEN 1 ELSE 0 END)`); `CellObservation.events` and `ipf.FactorCell.events` are already `float`, so the IPF solver itself needs no change
- [X] T009 [P] Replace the `WHERE continued AND NOT promoted` filter in `observed_merit_by_level` in `planalign_fit/compensation.py` with a promotion-weighted median over all continued employees weighted by `(1 - promotion_weight)`, computed in numpy over per-level arrays, and report effective exposure as `SUM(1 - promotion_weight)` so credibility shrinkage sees the real evidence
- [X] T010 Update the events formatter in `_hazard_section` in `planalign_fit/report.py` to render one decimal place when the count is fractional — `{:,.0f}` would misreport 412.7 expected promotions as an exact tally of 413
- [X] T011 Add `level_coverage_threshold: float = 0.95` and `separation_exposure_gate: float = 0.50` to `FitOptions` in `planalign_fit/runner.py`; the R-3 separation constants deliberately do NOT go here (FR-016)
- [X] T012 Add `TestCleanPathParity` to `tests/test_parameter_fitting.py`. **Note**: the T002 golden was generated with the pre-dispersion fixture, so it is not comparable — the valid parity test is the *same* census fitted by both code versions. Verified via `git stash` of `planalign_fit/`: promotion base, events, age/tenure multipliers, merit, and merit exposure are **byte-for-byte identical**

**Checkpoint**: The harness can grade, the shared types exist, and the weighted plumbing is in place as a verified no-op. User story work can begin.

---

## Phase 3: User Story 1 — Fit a promotion rate from a census with no job-level column (Priority: P1) 🎯 MVP part 1

**Goal**: Replace band-crossing classification with a per-level two-component mixture, so a level-less census yields a promotion rate near the truth instead of ~3x it.

**Independent Test**: Strip `level_id` from the synthetic population and assert the recovered promotion rate is within 1.5pp of 0.06 — the same assertion termination already meets.

### Tests for User Story 1 ⚠️

> Write these FIRST and confirm they FAIL before implementing T017–T022.

- [X] T013 [P] [US1] Create `tests/test_promotion_mixture.py` with EM recovery tests on synthetic numpy arrays drawn from known `mu`, `sigma`, `pi`, asserting the fitted components and mixing weight recover the generating parameters
- [X] T014 [US1] Add determinism tests to `tests/test_promotion_mixture.py`: the same input array fitted twice yields bit-identical results, and results are invariant to input row order
- [X] T015 [US1] Add a prior-escape test to `tests/test_promotion_mixture.py` initializing EM at a merit prior far from the generating truth and asserting recovery anyway — this guards the plan's stated risk that prior anchoring biases the result
- [X] T016 [P] [US1] Add `TestPromotionWithoutLevelId` to `tests/test_parameter_fitting.py`: fit a level-stripped synthetic census and assert the promotion rate is within 1.5pp of truth (SC-001); assert coverage routing selects the estimated path; and add a regression test for the partial-population bug — a census with `level_id` populated for one row must NOT be treated as authoritative (FR-001c)

### Implementation for User Story 1

- [X] T017 [P] [US1] Create `planalign_fit/mixture.py` with `MixtureComponent`, `MixtureFit`, and a deterministic two-component Gaussian EM on `log(1 + growth)` — prior-anchored initialization, `max_iter=200`, `tol=1e-8`, no RNG, a sigma floor to prevent component collapse, and BIC computed for both the two-component and single-component models per research.md R-3/R-4
- [X] T018 [US1] Replace `has_explicit_level: bool` with `level_coverage: float` in `TransitionObservability` in `planalign_fit/transitions.py`, measuring the share of experienced exposure carrying a job level at **both** ends of a transition — this fixes the silent-mixing bug where `transitions.py:202` checks the whole column while `transitions.py:141` coalesces to band derivation per row
- [X] T019 [US1] Create `planalign_fit/promotion.py` with the coverage routing decision (FR-001/FR-001a–d), per-level mixture invocation, and assignment of EM posteriors as `promotion_weight`, applying the forced-zero rules from research.md R-5 (growth <= 0, growth outside the plausible band, top job level) while keeping those rows in exposure
- [X] T020 [US1] Write the estimated-path weights back into the transition table in `planalign_fit/transitions.py` via a `promotion_weights` staging table keyed by `(employee_id, from_year)`, preserving the T007 `[0, 1]` invariant
- [X] T021 [US1] Wire `promotion.classify` into `_run_estimators` in `planalign_fit/runner.py` ahead of `fit_promotion_hazard`, populating `FitResult.promotion_classification`, and **delete** the upper-bound warning at `runner.py:334-341` — it describes behavior that no longer exists (FR-012)
- [X] T022 [US1] Add the "Promotion basis" summary row and the `measured`/`estimated` preamble to `planalign_fit/report.py`, and the corresponding summary row to `_render_summary` in `planalign_cli/commands/fit.py`, per contracts/fit-report.md §1–2 and contracts/cli-fit.md

**Checkpoint**: A level-less census produces an accurate promotion rate. Not yet safe to ship — every level gets a fitted rate whether or not its components separated. That is US2.

---

## Phase 4: User Story 2 — Know when the promotion rate cannot be trusted (Priority: P1) 🎯 MVP part 2

**Goal**: Turn the mixture's separation statistics into policy — per-level verdicts, an exposure gate, and an explicit "not fitted, default retained" outcome.

**Independent Test**: Fit a census whose promotion and ordinary raises genuinely overlap and assert the promotion hazard is reported not fitted, with the configured default retained and the reason stated.

### Tests for User Story 2 ⚠️

- [X] T023 [P] [US2] Add separation-test unit tests to `tests/test_promotion_mixture.py`: well-separated components pass both conditions; overlapping components fail the distance floor; a single-component population fails BIC; a non-converged fit is treated as failed
- [X] T024 [P] [US2] Add an inseparable-population `TruthRates` variant to `tests/fixtures/synthetic_census.py` (small promotion raise, wide merit sigma) so the negative case can be constructed — depends on T003
- [X] T025 [US2] Add `TestPromotionNotFitted` to `tests/test_parameter_fitting.py`: the inseparable census reports basis `not_fitted`, emits no estimated rate (SC-003), lists promotion among unfittable parameters, and retains the prior values in all three promotion seed files
- [X] T026 [US2] Add `TestPartialSeparation` to `tests/test_parameter_fitting.py`: a census where junior levels separate and senior levels do not yields per-level verdicts matching true separability, fitted rates only for separating levels, defaults for the rest, and an overall verdict matching the exposure-coverage rule (SC-003a)
- [X] T027 [P] [US2] Add manifest and provenance contract tests to `tests/test_parameter_fitting.py` per contracts/pack-provenance.md §4: basis recorded in `manifest.json`; a pre-feature manifest without `promotion_basis` loads and defaults to `measured`; a `not_fitted` pack still emits all three promotion seed files; adding manifest fields leaves an otherwise-identical pack's fingerprint unchanged

### Implementation for User Story 2

- [X] T028 [US2] Implement the two-condition separation test in `planalign_fit/promotion.py` as module-level constants unreachable from any CLI or config path (FR-016): BIC must prefer two components, **and** standardized distance `abs(mu2 - mu1) / sigma_pooled >= 2.0`; populate `LevelSeparation` including `reason` for every failing level
- [X] T029 [US2] Implement the per-level fallback in `planalign_fit/promotion.py` — levels that do not separate retain their configured default rate rather than an estimated one (FR-004)
- [X] T030 [US2] Implement the exposure-coverage gate in `planalign_fit/promotion.py`: when separating levels cover less than `separation_exposure_gate` of experienced exposure, set basis `not_fitted` and retain the default throughout (FR-004a); make the boundary comparison deterministic so a value exactly at the threshold does not depend on floating-point noise
- [X] T031 [US2] In `planalign_fit/runner.py`, set `result.promotion = None` on the `not_fitted` path and append an `Unfittable` entry naming the exposure gate and observed share (FR-007) — `all_fitted()` already guards `if hazard is not None`, so no further change is needed there
- [X] T032 [US2] Emit prior-valued promotion seed files on the `not_fitted` path in `planalign_fit/pack.py` so the pack stays valid and runnable (FR-009) — `apply.py:107` builds its overlay by file swap and a missing seed would break it
- [X] T033 [US2] Add `promotion_basis: str` and `thresholds: dict[str, float]` (non-default values only) to `PackManifest` in `planalign_fit/pack.py`; `from_dict` already filters to known fields so older packs load without migration
- [X] T034 [US2] Add `promotion_basis` to `provenance_block` in `planalign_fit/apply.py` (FR-010) — this rides the existing mechanism where `SimulationConfig` retains unknown keys and `to_dbt_vars` ignores them, so it reaches `run_metadata` without perturbing the config fingerprint
- [X] T035 [US2] Add the per-level verdict table, the `not_fitted` handling, and the four conditional data warnings to `planalign_fit/report.py` per contracts/fit-report.md §2 and §4 (FR-004b, FR-006)
- [X] T036 [US2] Add `--level-coverage-threshold` and `--separation-exposure-gate` flags to `planalign_cli/commands/fit.py` with `0 < value <= 1` validation that exits `EXIT_BAD_INPUT` and **never silently clamps**, plus the non-default threshold disclosure in the summary and report (FR-015, FR-017)

**Checkpoint**: MVP complete. The promotion rate is accurate where it can be measured and explicitly absent where it cannot. Ship-ready.

---

## Phase 5: User Story 3 — Merit no longer distorted by promotion misclassification (Priority: P2)

**Goal**: Confirm and disclose that merit is fitted from an undistorted pool on every path.

**Independent Test**: Fit the level-stripped synthetic population and assert the per-level merit rate is within 1pp of truth — an assertion that fails today because over-classification strips the largest ordinary raises from the merit pool.

**Note**: The mechanism landed in Foundational (T009) as a verified no-op on the measured path. This phase is the estimated-path verification and the disclosure that the plumbing alone does not provide.

### Tests for User Story 3 ⚠️

- [X] T037 [P] [US3] Add `TestMeritUndistorted` to `tests/test_parameter_fitting.py`: on a level-stripped census, merit per level recovers within 1pp of truth (SC-002), and both merit and promotion recover in the same fit (US3 scenario 1)
- [X] T038 [P] [US3] Add a merit-on-`not_fitted` test to `tests/test_parameter_fitting.py` asserting merit is still fitted when the promotion hazard is not (FR-008b), and that the report discloses the weighting could not be sharpened

### Implementation for User Story 3

- [X] T039 [US3] Rewrite the merit section description in `_merit_section` in `planalign_fit/report.py` per contracts/fit-report.md §3 — it currently claims merit is fitted over employees "who stayed and were not promoted," which is no longer true on any path
- [X] T040 [US3] Add the FR-008b disclosure sentence to the merit section in `planalign_fit/report.py` for the `not_fitted` path, stating that promotion contamination may remain in the merit pool

**Checkpoint**: Merit is correct and honestly described on all three paths.

---

## Phase 6: User Story 4 — Preserve the job-level column end to end (Priority: P3) ⚠️ PARTIALLY BLOCKED

**Goal**: Ensure a census that carries `level_id` keeps it all the way to the fitter.

**⚠️ Blocked dependency**: FR-011 requires the census anonymizer to preserve `level_id`. **The anonymizer does not exist** — issue #449 is open and unimplemented; the only reference in the codebase is a forward-looking line in `docs/guides/parameter_fitting.md:24`. There is no code to change, so FR-011 cannot be satisfied in this feature. It becomes a constraint recorded against #449 to be honored when the anonymizer is built.

The fitter-side half of this story is actionable and is covered below.

- [X] T041 [P] [US4] Added comment to issue #449 (comment 5151683164) recording the FR-011 constraint: the anonymizer must preserve `level_id` when the source census carries it, because dropping it forces the fitter onto the estimated promotion path — with a pointer to this spec and to the coverage threshold in `planalign_fit/promotion.py`
- [X] T042 [P] [US4] Add a test to `tests/test_parameter_fitting.py` for US4 scenario 3: a census whose `level_id` was dropped or blanked routes to the estimated path and the report attributes the loss of the authoritative route to missing coverage, so the degradation is visible rather than silent

**Checkpoint**: The fitter reports the degradation clearly. FR-011 itself is deferred to #449 and must be called out in the PR.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T043 [P] Add the "Promotion classification" paragraph to `_method_section` in `planalign_fit/report.py` per contracts/fit-report.md §5, rendered on every run so the method is documented whether or not it was used
- [X] T044 [P] Update `docs/guides/parameter_fitting.md` with the three promotion bases, the two adjustable thresholds, and the fact that promotion may now be reported unfittable
- [X] T045 [P] Add the report contract tests from contracts/fit-report.md "Test surface" to `tests/test_parameter_fitting.py`, including the assertion that the string `upper bound` appears in no report on any path (FR-012)
- [X] T046 Verify pack determinism end to end per quickstart.md: two `planalign fit` runs over identical snapshots produce identical fingerprints, with only `fit_date` differing in `manifest.json`
- [~] T047 **PARTIAL** — `apply_pack` verified: fingerprint validates, all three promotion seeds emitted with prior values, effective config carries `param_pack.promotion_basis: not_fitted`. The full multi-year `planalign simulate` was NOT run (multi-minute dbt build); the pack-application path FR-009 depends on is verified, the end-to-end simulation is not
- [X] T048 Confirm `pytest -m fast` still completes in under 10 seconds (Constitution III) — the EM unit tests belong in the fast suite, the 9,000-employee round-trip fits do not
- [X] T049 Run the full `pytest tests/test_parameter_fitting.py tests/test_promotion_mixture.py` suite and record the measured recovery numbers against SC-001 and SC-002; if ±1.5pp / ±1pp prove unreachable, revise the spec's success criteria **with evidence** rather than widening a tolerance silently
- [X] T050 Read `fit_report.md` end to end on all three paths as a human would, per the quickstart checklist — half this feature's requirements are about what the analyst is told, and assertions alone do not verify that it reads well

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: needs T002 for the parity comparison in T012. **Blocks all user stories.** T003 blocks the entire feature.
- **US1 (Phase 3)**: needs Foundational complete
- **US2 (Phase 4)**: needs US1 complete — the separation test consumes `MixtureFit` statistics produced in T017
- **US3 (Phase 5)**: needs US1 complete (real weights on the estimated path); independent of US2
- **US4 (Phase 6)**: needs US1 complete for T042; T041 has no code dependency at all
- **Polish (Phase 7)**: needs all desired stories complete

### Critical path

```text
T003 (fixture dispersion)
  └─> T007 (promotion_weight column)
        └─> T008, T009 (weighted consumers)  [parallel]
              └─> T012 (parity gate)
                    └─> T017 (EM) ─> T019 (routing) ─> T021 (wiring)
                          └─> T028-T030 (separation policy) ─> T031-T036
```

T003 is the single most blocking task in the feature and the one most likely to be skipped as "just a test fixture."

### Within each story

- Tests are written and confirmed failing before the implementation they cover
- Types before the modules that use them (T005 before T017/T019)
- Pure numerics before domain integration (T017 before T019)
- Domain integration before surfaces (T019/T021 before T022)

---

## Parallel Opportunities

### Phase 2 (Foundational)

```bash
# After T003 lands, these touch different files:
Task: "T004 fixture assertions in tests/test_parameter_fitting.py"
Task: "T005 new types in planalign_fit/models.py"
Task: "T006 base_increase_pct in planalign_fit/priors.py"

# After T007 lands:
Task: "T008 weighted load_cells in planalign_fit/hazards.py"
Task: "T009 weighted merit median in planalign_fit/compensation.py"
```

### Phase 3 (US1)

```bash
# Test authoring across two different files:
Task: "T013 EM unit tests in tests/test_promotion_mixture.py"
Task: "T016 round-trip tests in tests/test_parameter_fitting.py"
```

T014 and T015 are **not** parallel with T013 — same file. T017 is the only implementation task in US1 that parallelizes with anything, since T018–T022 form a dependency chain.

### Phase 7 (Polish)

T043, T044, T045 touch three different files and run in parallel. T046–T050 are verification and run last, in order.

---

## Implementation Strategy

### MVP (Phases 1, 2, 3, 4)

1. Setup — record the baseline (T001, T002)
2. Foundational — **T003 first**, then plumbing; T012 is the gate that proves the clean path did not move
3. US1 — the estimator; checkpoint at "6% recovered instead of 16.8%"
4. US2 — the policy; checkpoint at "inseparable census reports not fitted"
5. **STOP and VALIDATE**: run quickstart.md verification in full, especially determinism (T046) and clean-path parity (T012)

Do not ship after Phase 3. See "Story independence" above.

### Incremental delivery after MVP

- US3 (Phase 5) — merit verification and disclosure; two tests and two report edits
- US4 (Phase 6) — one issue comment and one test; FR-011 deferred to #449
- Polish (Phase 7) — documentation, method disclosure, end-to-end verification

### Suggested commit boundaries

- T003–T004: "Give the synthetic census realistic raise dispersion"
- T005–T012: "Thread a promotion weight through the fitter (no behavior change)"
- T013–T022: "Estimate promotions from the raise distribution when level_id is absent"
- T023–T036: "Report promotion as unfittable when raises do not separate"
- T037–T042, T043–T050: "Merit disclosure", "Docs and verification"

---

## Notes

- The fitter never opens a simulation database — `fit_parameter_pack` uses in-memory DuckDB (`runner.py:66`). Only T047 runs a simulation, and it uses an isolated `--database` path per CLAUDE.md §8.
- No dbt model, SQL file under `dbt/`, or `.duckdb` file is touched by this feature. If a change starts reaching into `dbt/`, it has left the plan.
- The separation-test constants must stay unreachable from the CLI, config, and environment (FR-016). If a task tempts you to make them configurable, that is the abuse the requirement exists to prevent.
- Verify each test fails before implementing against it — particularly T016, which passes today for the wrong reason if `level_id` stripping is not actually applied.
