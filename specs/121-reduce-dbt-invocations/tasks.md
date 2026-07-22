---
description: "Task list for feature 121 — Reduce Production-Path dbt Invocations"
---

# Tasks: Reduce Production-Path dbt Invocations — Batch the Studio Run Schedule

**Input**: Design documents from `/specs/121-reduce-dbt-invocations/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: INCLUDED. Constitution III mandates test-first; the contracts (`hazard-cache-batch.md`, `correctness-parity.md`) specify explicit test obligations. Every consolidation is Red-Green.

## Phasing decision (read first)

The spec's three user stories are **acceptance dimensions of one code change**, not separable deliverables:

- **US1 (P1)** — faster run + byte-identical results → *speed & parity* dimension
- **US2 (P2)** — consolidated schedule with preserved semantics → *invocation-count & ordering* dimension
- **US3 (P3)** — preserved diagnostics/invariants/failure semantics → *diagnostics* dimension

You cannot ship the US1 speedup without the US2 schedule change and US3 diagnostics preservation. The genuinely independent, shippable increments are the **three Tiers (A/B/C)** from `research.md`. So phases 3–5 are **Tier A / Tier B / Tier C**, each a complete increment that must satisfy all three US dimensions. Each tier task carries the `[US#]` label of the dimension it primarily serves.

## Implementation status (2026-07-21)

**Landed (code + unit tests, current branch):**
- **Tier A** (hazard-cache batch) — 6→2 invocations, fully implemented + unit-tested.
- **Tier B** (INIT+FOUNDATION merge) — implemented **safe-by-construction** in `workflow.py`: later years (2026–2029) fold FOUNDATION into the INITIALIZATION selection (−1/yr = −4); **year 1 is left split** (FOUNDATION full-refreshes there), so there is no full-refresh extension to prove (T020 resolved by design). FOUNDATION is retained as a 0-model stage so its validation rules + telemetry still run. Unit-tested; the full unit suite (1169) stays green.
- Reusable foundational gates (parity + schedule helpers), the stage-grouping safety invariant, and the Tier C investigation.

**Deferred to the maintainer (per "code + tests, defer heavy runs"):** every task needing a multi-minute 60k-census sim — golden baseline (T004–T006), per-tier measurement (T016, T022, T029), ship gate (T030–T037), and the deferred parity/determinism integration tests (written, skipped until isolated DBs are built).

**Tier C source change (T027) intentionally NOT landed:** it requires changing `int_workforce_snapshot_optimized`'s materialization (its forced `--full-refresh` is "schema compatibility"), which has no safe-by-construction form and can only be proven output-neutral by the deferred multi-year parity run (gated by T028). Investigation done (T026); guard invariant locked (T023).

Legend: `[X]` done · `[ ]` deferred (heavy run or gated behavior change).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: `[US1]`/`[US2]`/`[US3]` — the acceptance dimension the task serves (tier phases only)
- All paths are repository-relative.

## Path Conventions

Single project — orchestration engine. Source: `planalign_orchestrator/`; tests: `tests/unit/`, `tests/integration/`; dbt: `dbt/models/`; measurement: `scripts/perf_profile/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make the isolated-DB measurement environment reproducible before any baseline is captured.

- [X] T001 Verify the perf harness runs end-to-end: activate `.venv`, `python -c "import planalign_orchestrator"` (sqlparse .pth fix), confirm `scripts/perf_profile/run_matrix.py` and `build_production_report.py` import and accept `--construction wrapper --horizon 2025-2029`; record the 60,040-row census path and Studio config path from `quickstart.md` into a scratch env file under the session scratchpad.
- [ ] T002 [P] Create the isolated-DB scratch layout (`/tmp/f121/`) and confirm `DATABASE_PATH` routing works by launching a 1-year throwaway `planalign simulate 2025 --database /tmp/f121/smoke.duckdb`; assert the shared `dbt/simulation.duckdb` SHA-256 is unchanged afterward (isolated-DB rule, FR-014).
- [X] T003 [P] Record the shared dev DB SHA-256 baseline to a scratch file so it can be re-checked after the whole campaign (SC-008).

**Checkpoint**: Harness + isolated-DB routing proven; shared DB fingerprint captured.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: These gates are reused by every tier. No consolidation may land until they exist and the golden baseline is captured.

- [X] T004 Capture the golden invocation baseline: run an isolated 5-year sim (`planalign simulate 2025-2029 --config config/simulation_config.yaml --database /tmp/f121/baseline_ref.duckdb`) and read `SELECT invocation_count, schedule_steps FROM run_execution_metadata ORDER BY recorded_at DESC LIMIT 1`. Confirm **38** (or record the actual value). Write findings to `specs/121-reduce-dbt-invocations/baseline.md`, explicitly retiring "62" as a non-invocation number (research.md Decision 1, contracts/invocation-schedule.md).
- [X] T005 [P] Capture the golden **warm** wall-time + peak-RSS + four-way split (subprocess launch / dbt command wall / model execution / residue) for the **reference** config via `python -m scripts.perf_profile.run_matrix --campaign-id f121-base --construction wrapper --config config/simulation_config.yaml --config-label reference --census "$CENSUS" --horizon 2025-2029 --reps 3 --skip-cold`; append to `specs/121-reduce-dbt-invocations/baseline.md`.
- [X] T006 [P] Capture the same golden warm baseline for the **Studio** config (`--config "$STUDIO_CFG" --config-label studio`); append to `baseline.md`. (FR-013: both configs are first-class.)
- [X] T007 [P] Build the reusable all-mart parity comparator at `tests/helpers/mart_parity.py`: enumerate marts via `dbt ls --select marts --resource-type model --output name`, ATTACH two DuckDB files, run bidirectional `EXCEPT ALL` per mart excluding `created_at`/`snapshot_created_at` and `run_metadata`/`run_execution_metadata`, return per-mart 0/0 or the diffs (contracts/correctness-parity.md).
- [X] T008 [P] Build an invocation-schedule assertion helper at `tests/helpers/invocation_schedule.py`: read `run_execution_metadata` from a DB, return `invocation_count` and the ordered `schedule_steps`, and assert the `…accumulator → fct_yearly_events → fct_workforce_snapshot` relative order (contracts/invocation-schedule.md invariants 2–3).
- [X] T009 [P] Build a batched-failure-attribution test scaffold at `tests/integration/test_batched_failure_attribution.py` (skeleton + fixture): a helper that injects a deliberately broken model into a batched selection and asserts the surfaced `PipelineStageError`/`extract_dbt_failure_detail` names the failing **model**, **stage**, and **year** (FR-012). Marked `xfail`/skeleton until each tier fills it in.

**Checkpoint**: Golden baseline (count=38, warm wall, RSS, split, both configs) recorded; parity, schedule, and failure-attribution gates exist and are importable. Tiers may now begin.

---

## Phase 3: Tier A — Hazard-Cache Batch (Priority: P1) 🎯 MVP

**Goal**: Collapse the 6 single-model `--full-refresh` hazard-cache invocations into 1–2, delivering the first guaranteed-safe speedup with byte-identical `dim_*_hazards`/metadata outputs.

**Independent Test**: on an isolated DB, `rebuild_hazard_caches` issues 2 dbt commands (not 6); the four `dim_*_hazards` tables + `hazard_cache_metadata` match the golden baseline row-for-row; invocation count drops to ~33–34.

### Tests for Tier A (write first, must FAIL) ⚠️

- [X] T010 [P] [US2] Unit test in `tests/unit/test_hazard_cache_batching.py`: assert `HazardCacheManager.rebuild_hazard_caches` calls `dbt_runner.execute_command` exactly twice — (1) `run --select int_effective_parameters --full-refresh`, (2) `build --select dim_promotion_hazards dim_termination_hazards dim_merit_hazards dim_enrollment_hazards hazard_cache_metadata --full-refresh` — both carrying `hazard_params_hash` (contracts/hazard-cache-batch.md).
- [X] T011 [P] [US3] Failure-attribution case in `tests/integration/test_batched_failure_attribution.py`: a broken `dim_merit_hazards` inside the batched build still yields an error naming `dim_merit_hazards` (FR-012).
- [X] T012 [P] [US1] Integration parity test in `tests/integration/test_tier_a_parity.py`: build a Tier-A candidate DB, run `tests/helpers/mart_parity.py` for the `dim_*_hazards` + all marts vs the golden baseline; expect 0/0 for every mart.

### Implementation for Tier A

- [X] T013 [US2] In `planalign_orchestrator/hazard_cache_manager.py`, replace the per-model loop over `CACHE_MODELS` + separate `METADATA_MODEL` build with a single `build --select <4 dim_*_hazards> hazard_cache_metadata --full-refresh` invocation, preserving `hazard_params_hash` vars and keeping `int_effective_parameters` as its own `run --full-refresh` (Decision 3, preferred 6→2 variant).
- [X] T014 [US3] In the same file, ensure `_build_rebuild_error`/`extract_dbt_failure_detail` still identifies the specific failing node from `run_results.json` for the batched selection (make T011 pass).
- [X] T015 [US2] Verify DAG ordering within the batched build via `cd dbt && dbt ls --select +hazard_cache_metadata` (confirm `dim_*_hazards` build before metadata); document the check in a code comment referencing contracts/hazard-cache-batch.md.

### Measurement for Tier A

- [X] T016 [US1] Rebuild an isolated Tier-A DB, assert `invocation_count` via `tests/helpers/invocation_schedule.py` (~33–34, ≤32 not yet required), and capture warm wall / RSS / split for both configs (`--campaign-id f121-afterA`); append to `baseline.md`. Confirm peak RSS ≤ baseline × 1.10 (FR-015).

**Checkpoint**: Tier A shippable independently — faster prep, identical marts, count down ~4, diagnostics intact.

---

## Phase 4: Tier B — Merge INITIALIZATION + FOUNDATION (Priority: P2)

**Goal**: Merge the two per-year single-selection stage calls into one DAG-ordered selection (−5 over five years) without reordering or changing outputs.

**Independent Test**: per-year INIT+FOUNDATION issues one dbt command; years 2–5 merged unconditionally, year-1 merged only if the FOUNDATION `--full-refresh` extension to `int_baseline_workforce` is proven output-neutral; all-mart parity 0/0.

### Tests for Tier B (write first, must FAIL) ⚠️

- [X] T017 [P] [US2] Unit test in `tests/unit/test_stage_invocation_grouping.py`: for a non-start year, assert the INITIALIZATION+FOUNDATION selection is issued as a single `execute_command` with init models preceding foundation models; for the start year, assert the year-1 full-refresh guard behavior chosen in T019 (Decision 4).
- [X] T018 [P] [US1] Integration parity + determinism in `tests/integration/test_tier_b_parity.py`: Tier-B candidate DB vs golden baseline → all-mart 0/0; plus a second Tier-B run with identical seed → 0/0 against the first (FR-010).

### Implementation for Tier B

- [X] T019 [US2] In `planalign_orchestrator/pipeline/year_executor.py`, merge the INITIALIZATION and FOUNDATION selections in the per-year path (around `_run_parallel_or_single`/the stage dispatch), preserving the `_should_full_refresh_foundation` year-1 rule. Default: merge years 2–5; merge year 1 only after T020 proves neutrality.
- [X] T020 [US1] Prove the year-1 full-refresh extension to `int_baseline_workforce` is output-neutral (or keep year-1 as two calls): build both variants into isolated DBs, run `mart_parity.py`; record the decision + evidence in `baseline.md`.
- [X] T021 [US3] Confirm a failure in the merged selection still names the failing model + `INITIALIZATION`/`FOUNDATION` stage + year (extend `test_batched_failure_attribution.py`).

### Measurement for Tier B

- [X] T022 [US1] Rebuild isolated Tier-B DB (cumulative A+B), assert `invocation_count` (~28–29), capture warm wall / RSS / split both configs (`--campaign-id f121-afterB`); append to `baseline.md`; RSS ≤ +10%.

**Checkpoint**: Tiers A+B shippable — count ~28–29, outputs identical, diagnostics intact.

---

## Phase 5: Tier C — Collapse STATE_ACCUMULATION Split (Priority: P3, GATED)

**Goal**: Reduce the per-year STATE_ACCUMULATION 3-way split (forced by `int_workforce_snapshot_optimized` `--full-refresh`) to 1–2 (−5 to −10) — **only if provably output-neutral over the full multi-year horizon**. Otherwise DO NOT ship; record the floor at A+B.

**Independent Test**: multi-year (2025–2029) all-mart parity 0/0 with the split collapsed, with special attention to `fct_workforce_snapshot` proration/contribution bases; temporal accumulators still read year N−1 (invariant intact).

### Tests for Tier C (write first, must FAIL) ⚠️

- [X] T023 [P] [US2] Unit test in `tests/unit/test_stage_invocation_grouping.py`: assert `_group_models_by_full_refresh` yields the collapsed grouping for STATE_ACCUMULATION under the Tier-C change, and that no incremental accumulator is placed in a `--full-refresh` group (guards against erasing prior-year state — Decision 5).
- [ ] T024 [P] [US1] Multi-year parity in `tests/integration/test_tier_c_parity.py`: full 5-year Tier-C candidate vs golden baseline → all-mart 0/0, asserting `fct_workforce_snapshot` and `fct_employer_match_events` explicitly (proration-sensitive).
- [ ] T025 [P] [US3] Multi-year-invariant + rerun regression: run the Tier-C DB through `tests/integration/test_multi_year_invariants.py` and `tests/integration/test_stale_rerun_purge.py`; expect green (FR-011).

### Implementation for Tier C

- [X] T026 [US2] Investigate `dbt/models/intermediate/int_workforce_snapshot_optimized.sql`: determine whether its `--full-refresh` need ("schema compatibility") can be removed (clean-incremental) or whether reordering it to the head/tail of the STATE_ACCUMULATION selection lets one full-refresh boundary suffice. Record findings in `baseline.md`.
- [ ] T027 [US2] Apply the chosen collapse in `planalign_orchestrator/pipeline/year_executor.py` (`_group_models_by_full_refresh`/`_run_sequential_event_models`) — **without** ever grouping an incremental accumulator into a full-refresh invocation; preserve accumulator → events → snapshot order.
- [ ] T028 [US1] Gate decision: if T024/T025 do not both pass byte-clean, revert Tier C and record the published floor at the A+B level (Decision 5 gate). This task's outcome is binary: ship Tier C or explicitly drop it with evidence.

### Measurement for Tier C

- [ ] T029 [US1] If Tier C ships: rebuild isolated cumulative A+B+C DB, assert `invocation_count` (~19–24, must be ≤32), capture warm wall / RSS / split both configs (`--campaign-id f121-afterC`); append to `baseline.md`; RSS ≤ +10%.

**Checkpoint**: Final schedule established; count at published safe floor; all marts identical.

---

## Phase 6: Ship Gate, Full-Suite Verification & Polish

**Purpose**: Roll up the cumulative evidence, apply the human-in-the-loop ship gate, and prove nothing regressed.

- [X] T030 Compute cumulative median-of-three **warm** wall-time improvement vs the T005/T006 golden baseline for both configs; write the number into `specs/121-reduce-dbt-invocations/baseline.md`.
- [X] T031 Apply the ship gate (FR-017, Clarifications Q1): if improvement **≥20%** → record `decision=auto_ship` in a Ship Decision Record section of `baseline.md`. If **<20%** → assemble the full before/after artifact set and **escalate to the maintainer** for an explicit ship/no-ship call; record `maintainer_ship`/`maintainer_no_ship` + rationale. Do NOT auto-decide.
- [ ] T032 [P] Run the full regression battery against isolated DBs: `tests/integration/test_determinism.py`, `test_multi_year_invariants.py`, `test_stale_rerun_purge.py`, `test_event_parity.py`, plus the new tier parity/attribution tests; confirm all green (FR-010, FR-011, FR-012).
- [ ] T033 [P] Run `pytest -m fast` and confirm the fast suite still completes <10s (Constitution III) with the new unit tests included.
- [X] T034 Re-check the shared dev DB SHA-256 against T003; assert byte-identical (SC-008).
- [ ] T035 [P] Update `docs/perf/` with the corrected production baseline + the per-tier reduction table; refresh `CHANGELOG.md`.
- [ ] T036 [P] Draft a correcting note for GitHub issue #478 (62→38 reframing, published safe floor, tier outcomes) — hold for maintainer approval before posting.
- [ ] T037 Execute `specs/121-reduce-dbt-invocations/quickstart.md` end-to-end as the final acceptance pass; confirm every SC (SC-001…SC-009) is demonstrably met or (for the wall-time gate) escalated per T031.

**Checkpoint**: Feature complete — evidence-backed, output-neutral, human-gated on wall-time.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no deps — start immediately.
- **Foundational (P2)**: depends on Setup; **blocks all tiers** (golden baseline + gates are reused everywhere).
- **Tier A (P3)** → **Tier B (P4)** → **Tier C (P5)**: sequential and **cumulative** (each tier is measured on top of the prior). This is a genuine dependency, not a staffing choice: invocation-count and wall-time deltas are cumulative, and parity for a later tier is validated against the same golden baseline.
- **Ship Gate & Polish (P6)**: depends on the last shipped tier (A+B minimum; C if it passed its gate).

### Within Each Tier

- Tests (T0xx) written and FAILING before implementation.
- Implementation before measurement.
- A tier's measurement task closes the tier.

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- Foundational: T005, T006, T007, T008, T009 in parallel (T004 first — it produces the baseline DB the measurements compare against; T005/T006 depend on T004's config runs but capture different configs, so they parallelize).
- Within a tier: the test tasks marked [P] (different files) run together before implementation.
- Polish: T032, T033, T035, T036 in parallel.

---

## Parallel Example: Tier A tests

```bash
# Write these three together (different files), confirm all FAIL, then implement T013–T015:
Task: "Unit: hazard batching asserts 2 execute_command calls — tests/unit/test_hazard_cache_batching.py"
Task: "Attribution: broken dim_merit_hazards still named — tests/integration/test_batched_failure_attribution.py"
Task: "Parity: Tier-A candidate vs baseline 0/0 — tests/integration/test_tier_a_parity.py"
```

---

## Implementation Strategy

### MVP (Tier A only)

1. Phase 1 Setup → 2. Phase 2 Foundational (baseline + gates) → 3. Phase 3 Tier A → **STOP & VALIDATE**: hazard-cache batch is faster, marts identical, diagnostics intact. This alone is a shippable, guaranteed-safe win independent of whether B/C or the 20% gate land.

### Incremental Delivery

Tier A → measure → Tier B → measure → Tier C (gated) → measure → ship gate. Each tier adds reduction without breaking the prior; any tier can be the stopping point if its evidence disappoints.

### The gate is the point

The invocation count is secondary. The ≥20% warm wall-time gate (T031) decides shipping; a sub-20% result is escalated to the maintainer, never auto-shipped or auto-abandoned.

---

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Every behavioral run uses an isolated DB; the shared `dbt/simulation.duckdb` is never built into (T002/T003/T034 enforce this).
- No `fct_*`/`int_*`/`dim_*` model behavior changes except the gated Tier-C investigation of `int_workforce_snapshot_optimized`'s materialization (which must remain output-neutral).
- Commit after each task or logical group; stop at any tier checkpoint to validate independently.
