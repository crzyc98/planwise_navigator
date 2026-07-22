# Phase 0 Research: Reduce Production-Path dbt Invocations

**Feature**: 121-reduce-dbt-invocations | **Date**: 2026-07-21

This document resolves the open questions from the spec and grounds every planning decision in the actual HEAD codebase and the authoritative feature-120 baseline. There are **no remaining `NEEDS CLARIFICATION` items** — the three spec clarifications (human ship-decision gate, all-mart parity scope, ≤10% RSS) plus this research fully constrain the design.

---

## Decision 1 — Retire "62"; the real HEAD baseline is 38 dbt commands

**Decision**: Adopt **38 dbt commands** (the feature-120 authoritative work-schedule baseline) as the invocation baseline for this feature, and formally retire "62" as a non-invocation number. Phase 0 of implementation re-runs the harness on HEAD to confirm 38 (or record the current value) before any consolidation.

**Rationale**: `specs/120-unify-orchestrator-construction/work-schedule-baseline.md` measured the schedule with the recorder at `DbtRunner.execute_command` (the single choke-point through which every product dbt command passes) on both the reference and Studio configs at 60,040 employees, five years. Both runs issued exactly **38** commands, byte-equivalent order, same semantic signature, shared-dev-DB SHA unchanged. That document explicitly reconciles 38 vs 62: *"the retained Studio log count of 62 … counted log/subprocess-related records with different semantics … not an invocation baseline or an optimization gate."* Independent reverse-engineering of the current code confirms 38:

| Scope | Commands | Source |
|---|---:|---|
| `dbt seed` (once) | 1 | `pipeline_orchestrator._ensure_seeds_loaded` |
| `run --select staging.*` (start year) | 1 | `_run_start_year_setup` |
| `run --select int_effective_parameters --full-refresh` | 1 | `hazard_cache_manager.rebuild_hazard_caches` |
| 4× `build --select dim_*_hazards --full-refresh` + 1× metadata | 5 | `HazardCacheManager.CACHE_MODELS` + `METADATA_MODEL` |
| Per year × 5: INITIALIZATION (1) + FOUNDATION (1) + EVENT_GENERATION (1, tag-based) + STATE_ACCUMULATION (3, split by full-refresh) | 30 | `year_executor` + `event_generation_executor` |
| **Total** | **38** | |

**Alternatives considered**:
- *Take 62 literally and "cut to 32".* Rejected: 62 is not a count of issued commands; targeting it would chase a phantom and could justify unsafe changes to hit an arbitrary number. FR-003 explicitly permits a "stricter evidence-based safe floor" for exactly this situation, and the project's standing practice is to reframe an issue that diverged from current architecture rather than grind on a stale number.
- *Skip re-baselining, trust feature 120's 38.* Rejected as the sole basis: 120's baseline is authoritative and recent, but implementation Phase 0 still re-confirms on this branch's HEAD so the before/after artifacts share one measurement lineage (FR-002, FR-018).

---

## Decision 2 — Published safe floor: target ~20–26 commands; ≤32 is the ceiling, not the goal

**Decision**: The evidence-based safe floor published by this plan is **the cumulative effect of Tiers A+B+C where each is proven output-neutral**, estimated at **~20–26 commands**. The issue's ≤32 is treated as a *ceiling the plan must clear*, not the objective. Invocation count is a **secondary** metric; the **primary** ship gate is the ≥20% warm wall-time improvement (Decision 6).

**Rationale**: Per-tier arithmetic on the real 38 schedule:

| Tier | Change | Δ commands | Running total |
|---|---|---:|---:|
| — | HEAD baseline | — | 38 |
| A | Batch 4 `dim_*_hazards` + metadata into 1 `build`; fold `int_effective_parameters` | −4 to −5 | 33–34 |
| B | Merge per-year INITIALIZATION+FOUNDATION (×5) | −5 | 28–29 |
| C | Collapse per-year STATE_ACCUMULATION 3→1–2 (×5) | −5 to −10 | 19–24 |

**Alternatives considered**: A single "big-bang" rewrite of the schedule was rejected in favor of independently measurable tiers (each tier is one *Consolidation tier* entity, measured and parity-checked on its own), so a regression or a disappointing wall-time delta is attributable to exactly one change.

---

## Decision 3 — Tier A: batch the hazard-cache rebuild (highest-confidence, lowest-risk)

**Decision**: In `HazardCacheManager.rebuild_hazard_caches`, replace the loop of 4 single-model `build --select dim_X_hazards --full-refresh` calls + the separate metadata build with **one** `build --select dim_promotion_hazards dim_termination_hazards dim_merit_hazards dim_enrollment_hazards hazard_cache_metadata --full-refresh`. Keep `int_effective_parameters` materialization but fold it into the same rebuild path (either prepend it to the batched selection or reuse the FOUNDATION build); confirm via the DAG that `int_effective_parameters` builds before the `dim_*_hazards` that `ref()` it.

**Rationale**: These calls are already all `--full-refresh`, run once per run (fresh isolated DB → stale caches → single rebuild in year 1; later years' `ensure_hazard_caches_current` finds the hash unchanged and skips), and their only ordering constraint is the `ref()` DAG, which dbt resolves *within* one invocation. There is no cross-invocation transaction boundary and no event-ordering concern. This is the "batch the repeated single-model hazard/setup calls" and "fold `int_effective_parameters`" work items from the issue's Investigation Order, and it is the cleanest win.

**Caveat to verify in Phase 0**: the current code deliberately uses `run` (not `build`) for `int_effective_parameters` "to match how the pipeline builds int_* models — we only need the table to exist, not to run its schema tests here." Folding it into a `build` selection would additionally run its schema tests. Resolution: either (a) keep `int_effective_parameters` as a `run` and batch only the 4 caches + metadata as one `build` (8→4 first-year prep, −4, zero semantic change), or (b) confirm its schema tests pass in this context and use one combined `build` (8→3, −5). Prefer (a) unless (b) is proven test-clean — it preserves current test semantics exactly.

**Alternatives considered**: Batching the hazard rebuild into the FOUNDATION stage selection was rejected — the rebuild must run *before* the workflow stages (it materializes `dim_*_hazards` that EVENT_GENERATION reads) and is gated on cache-hash currency, a concern that does not belong in the per-year stage loop.

---

## Decision 4 — Tier B: merge per-year INITIALIZATION + FOUNDATION into one DAG-ordered selection

**Decision**: Merge the INITIALIZATION and FOUNDATION stage selections into a single `run --select <init models> <foundation models>` per year, since both already execute as one sequential single-selection call each via `_run_parallel_or_single`, and FOUNDATION `ref()`s INITIALIZATION outputs (dbt resolves the order).

**Rationale**: 2 invocations → 1 per year (−5 over five years) with no reordering risk, because dbt orders a multi-model selection by its ref() DAG.

**Guard (must be preserved)**: `_should_full_refresh_foundation` applies `--full-refresh` to the FOUNDATION selection **only on the start year**, and `--full-refresh` applies to the *entire* invocation. Merging would extend that full-refresh to the INITIALIZATION model (`int_baseline_workforce`) on year 1. Phase 0 must verify this is either (a) harmless (baseline workforce is built fresh on year 1 anyway) or (b) handled by keeping year-1 as two calls and merging only years 2–5. Default: merge years 2–5 unconditionally (−4), and merge year 1 only after proving the full-refresh extension is output-neutral. This keeps Tier B strictly output-preserving.

**Alternatives considered**: Using dbt `--select A+` graph operators to auto-pull dependencies was rejected — the stage lists are explicit and curated for determinism; expanding them via graph operators risks pulling unintended nodes.

---

## Decision 5 — Tier C: collapse the STATE_ACCUMULATION full-refresh split (highest risk, gated)

**Decision**: The 3-way split in `_group_models_by_full_refresh` is caused solely by `int_workforce_snapshot_optimized` requiring `--full-refresh` mid-list ("schema compatibility" per `_get_full_refresh_reason`). Attempt to collapse 3→1 (or 3→2) per year **only if** the full-refresh requirement can be removed safely (e.g., the schema issue is resolved so the model is cleanly incremental, or the model is reordered to the head/tail of the selection so a single full-refresh boundary suffices). If neither is provably output-neutral, **do not ship Tier C** and record the floor at the Tier A+B level.

**Rationale**: This is the largest arithmetic win (−5 to −10) but the only tier that touches incremental/full-refresh correctness — precisely the class of change the spec's edge cases forbid rushing ("consolidation would cross a transaction boundary or reorder events → reject"). `int_workforce_snapshot_optimized` is the proration snapshot feeding contributions; a wrong-materialization here silently corrupts comp/contribution bases. Tier C is therefore gated behind a full multi-year parity proof, not just single-year.

**Alternatives considered**: Forcing all STATE_ACCUMULATION models into one `--full-refresh` invocation was rejected outright — full-refreshing the incremental accumulators (`int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`, …) would erase prior-year state and break the temporal-accumulator invariant (year N reads year N−1). The full-refresh split exists to protect exactly this.

---

## Decision 6 — Ship gate: ≥20% warm wall-time, else escalate to the maintainer (no auto-outcome)

**Decision**: After each tier, measure the median-of-three **warm** wall time via `scripts.perf_profile.run_matrix` (`--skip-cold`, ≥3 reps) on both the reference and Studio configs at 60,040 employees, five years, isolated DBs. The cumulative improvement vs the HEAD baseline is the ship gate: ≥20% ships; **<20% is not auto-decided** — present the full before/after artifact set to the maintainer for an explicit ship / no-ship call (recorded in the *Ship decision record*).

**Rationale**: Directly encodes the spec clarification (Session 2026-07-21, Q1) and FR-017. It is genuinely uncertain whether batching moves wall time ≥20%: at 38 commands over ~131s, per-invocation overhead is ~subprocess-launch + project-parse per call; feature 120 already advised that "further run-cost optimization should use per-model execution timing inside this 38-command schedule," implying the remaining time may be dominated by model execution, not launch overhead. The honest design is to measure and let a human decide when the evidence is ambiguous.

**Alternatives considered**: Auto-NO-GO on <20% (rejected — discards guaranteed-safe reductions and removes human judgment the user explicitly wants); auto-ship anything correctness-clean (rejected — removes the evidence guardrail).

---

## Decision 7 — Correctness gate: all-mart, order-insensitive multiset parity

**Decision**: The parity gate compares **every `fct_*` and `dim_*` mart table** between an isolated baseline run and an isolated candidate run using a bidirectional `EXCEPT ALL` (multiset, duplicate-preserving), excluding only documented audit-timestamp fields (`created_at`, `snapshot_created_at`, and `run_metadata`/`run_execution_metadata` rows). Zero differing rows in either direction, for every mart, is required.

**Rationale**: Encodes the spec clarification (Q2 → all `fct_*`/`dim_*` marts) and FR-009/SC-003. `EXCEPT ALL` both directions is the same order-insensitive multiset check feature 120's quickstart already uses (`created_at`/`snapshot_created_at` excluded), so the method is proven in-repo. The dbt `graph`/`ls` output enumerates the mart set so the check can't silently miss a table.

**Alternatives considered**: Comparing only a named core set (rejected per Q2 — could hide a secondary-mart regression); adding `int_*` accumulators to the compare (rejected — over-couples the gate to internal state that may legitimately differ in materialization while the marts remain identical; the marts are the authoritative surface).

---

## Decision 8 — Peak-RSS ceiling and per-tier attribution

**Decision**: Peak RSS ≤ **+10%** vs the HEAD baseline is a hard per-tier gate (any tier exceeding it is reconsidered, not shipped). After each tier, record the four-way split — subprocess launch, dbt command wall, model execution, non-dbt residue — plus CPU and peak RSS, alongside config/census fingerprints and the construction signature, into the before/after artifact.

**Rationale**: Encodes Q3 (≤10%) and FR-015/FR-016/FR-018. Batching more models into one dbt process legitimately raises peak RSS (more of the DAG resident at once); the 10% ceiling catches over-batching. The four-way split is exactly what `scripts.perf_profile` already produces (subprocess launch cost, dbt command wall, per-model execution from `run_results.json`, residue), so attribution needs no new instrumentation.

**Alternatives considered**: No-increase (≤0%) was rejected in clarification as too noise-sensitive on a work laptop; ≤25% rejected as too loose to catch real regressions.

---

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Real invocation baseline on HEAD | 38 commands (feature 120 authoritative; re-confirmed in impl Phase 0). "62" retired. |
| Safe floor (FR-003) | ~20–26 commands (Tiers A+B+C, each output-neutral); ≤32 is the ceiling. |
| Which tables must byte-match | All `fct_*`/`dim_*` marts, bidirectional `EXCEPT ALL`, audit-timestamps exempt. |
| Peak-RSS "material" threshold | +10% over baseline. |
| Sub-20% wall-time outcome | Escalate to maintainer for explicit ship/no-ship; no auto-outcome. |
| Measurement harness | `scripts.perf_profile.run_matrix` / `build_production_report`; `run_execution_metadata` for the ordered schedule + `invocation_count`. |
