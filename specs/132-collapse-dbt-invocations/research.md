# Phase 0 Research: Collapse Remaining Per-Year Transformation Invocations

**Feature**: 132-collapse-dbt-invocations
**Date**: 2026-08-02

Every finding below was read out of the current source on `main`, not inferred from the issue text.

---

## Finding 1 — The year-1 INITIALIZATION build is redundant work, not just an extra command

**Decision**: Remove `int_baseline_workforce` from the start-year INITIALIZATION stage. This is Step 1a.

**Evidence**:

- `pipeline/workflow.py:120-123` — at the start year, INITIALIZATION selects exactly `[int_baseline_workforce]`.
- `pipeline/workflow.py:130-146` — at the start year, FOUNDATION *also* selects `int_baseline_workforce`, first in its list.
- `pipeline/year_executor.py:407-433` — `_should_full_refresh_foundation` returns `True` when `year == start_year`, so the FOUNDATION invocation carries `--full-refresh`.

The first build is incremental; the second drops and recreates the table. **The INITIALIZATION build's output is discarded a few seconds later.** The issue characterized this as "selected twice in two adjacent invocations"; it is worse than duplication — it is a build whose result cannot survive.

**Rationale**: This is a deletion, not a regrouping. It cannot change execution order within a command, which is the mechanism by which Tier C broke. It is the lowest-risk 4.2s available.

**Alternatives considered**:
- *Remove `int_baseline_workforce` from FOUNDATION instead, keeping the INITIALIZATION build.* Rejected: that would silently downgrade a full rebuild to an incremental one, violating `FR-005` directly.
- *Merge the two commands.* Rejected: unnecessary. One of them does no useful work; merging preserves waste that deletion removes.

---

## Finding 2 — INITIALIZATION has no validation to lose

**Decision**: Emptying the start-year INITIALIZATION model list carries no observability cost, so `FR-014` is satisfied trivially for Step 1a.

**Evidence**: `pipeline/stage_validator.py:57-83` — `validate_stage` branches only on `FOUNDATION`, `EVENT_GENERATION`, and `STATE_ACCUMULATION`. The `data_freshness_check` rule declared at `workflow.py:180` and `workflow.py:308` is **never dispatched**; no code path consumes it.

**Rationale**: The concern that motivated `FR-014` — that collapsing commands silently drops stage validation — does not apply to this stage. Feature 121's Tier B already relied on the same property when it emptied FOUNDATION for later years (`workflow.py:171-173`).

**Follow-up noted, not actioned**: `data_freshness_check` is dead configuration. Removing it is out of scope here; it belongs in a cleanup issue so this feature's diff stays purely about invocation count.

---

## Finding 3 — The full-rebuild floor is 3, confirming the relaxed count target

**Decision**: The year-1 setup block cannot collapse below three commands. `SC-006`'s target of 14 total stands.

**Evidence** — the six setup commands and why they cannot all merge:

| # | Command | Type | Rebuild | dbt vars |
|---|---|---|---|---|
| 1 | `seed` | seed | — | none |
| 2 | `run --select staging.*` | run | incremental | `_dbt_vars` |
| 3 | `run --select int_effective_parameters --full-refresh` | run | **full** | `+hazard_params_hash` |
| 4 | `build --select dim_*_hazards hazard_cache_metadata --full-refresh` | build | **full** | `+hazard_params_hash` |
| 5 | `run --select int_baseline_workforce` | run | incremental | `_dbt_vars` |
| 6 | `run --select int_baseline_workforce …` (FOUNDATION) | run | **full** | `_dbt_vars` |

Sources: `pipeline_orchestrator.py:711` (seed), `:721` (staging), `hazard_cache_manager.py:403` and `:429`, `year_executor.py:392-401`.

A rebuild flag applies to the whole command, so {2,5} (incremental) cannot merge with {3,4,6} (full). Command 1 is a different resource type. **Floor = seed + one incremental group + one full group = 3.** With Step 1a removing #5 and Step 1b merging #3+#4, the block lands at 4; year 1 totals 6 including the two out-of-scope stage commands, and the five-year run totals 14.

**Alternatives considered**:
- *Fold the seed load into a `dbt build` union with staging.* Would reach 13. Rejected for now: `build` runs tests on seeds and staging models that `run` does not, which changes both runtime and failure modes for a ~4.7s gain. Recorded as an optional Step 1c to evaluate only if Steps 1a/1b underdeliver against `SC-001`.
- *Drop `--full-refresh` from FOUNDATION at start year to enable a wider merge.* Rejected outright: direct `FR-005` violation.

---

## Finding 4 — The hazard-cache pair can merge, but carries a var and a resource-type subtlety

**Decision**: Merge `run --select int_effective_parameters --full-refresh` and `build --select dim_*_hazards hazard_cache_metadata --full-refresh` into a single `build --select int_effective_parameters dim_*_hazards hazard_cache_metadata --full-refresh`. This is Step 1b.

**Evidence**: `hazard_cache_manager.py:395-432`. Both commands are `--full-refresh` and both pass `extra_vars = {"hazard_params_hash": current_hash}`. The models form a clean DAG — each `dim_*_hazards` refs `int_effective_parameters`, and `hazard_cache_metadata` refs the caches — so dbt resolves build order within one selection. Feature 121's Tier A already merged five commands into #4 on exactly this reasoning (`contracts/hazard-cache-batch.md`).

**Two risks to handle in implementation**:

1. **The extra var must survive the merge.** `hazard_params_hash` is not in the workflow's `_dbt_vars`. If the merged command is issued through a path that supplies only `_dbt_vars`, the caches rebuild against a wrong or missing hash — a silent correctness failure the parity gate *would* catch, but only after a full 60k run. The merged call must keep passing `extra_vars` explicitly.
2. **`run` → `build` promotes int_effective_parameters' schema tests.** The existing code comments at `hazard_cache_manager.py:399-400` state the choice of `run` was deliberate — "we only need the table to exist, not to run its schema tests here." Merging into `build` newly executes those tests. This is arguably an improvement, but it is a behavior change: a pre-existing test failure would now fail the run. Implementation must first confirm those tests pass at 60k, and the step must be reverted if they are flaky.

**Alternatives considered**:
- *Merge as `run` instead of `build`.* Rejected: the four `dim_*_hazards` models plus metadata are currently built with `build` for their tests; downgrading to `run` would drop existing test coverage, trading correctness for speed.

---

## Finding 5 — Step 2 must union into a tag selection, not a model list

**Decision**: For years after the start year, fold the merged INITIALIZATION+FOUNDATION models into the event-generation selection, producing `run --select tag:EVENT_GENERATION <foundation models>`.

**Evidence**:
- `stage_execution_strategies.py:26-43` — `execute_tagged_stage` issues `run --select tag:EVENT_GENERATION`. This is the product path and matches the command the issue measured.
- `year_executor.py:308-331` — STATE_ACCUMULATION instead issues an explicit model list.
- `workflow.py:171-173` — Tier B already folded FOUNDATION into INITIALIZATION for later years by list concatenation, and both are non-full-refresh after the start year (`_should_full_refresh_foundation` is start-year-only). The same safety argument extends to this merge.

**Rationale**: dbt unions selectors, so adding model names alongside a tag selector is well-defined. Neither side carries a rebuild flag after the start year, so `FR-005` is not engaged.

**The specific risk**: `workflow.py:191` carries the comment *"Match working runner ordering exactly for determinism"* over the event-generation model list. That ordering is already **not** enforced — the models go into one dbt selection where order comes from the `ref()` DAG, not the list. But the comment signals that someone believed order mattered here, and this is precisely the stage where Tier C's ordering assumption broke. Step 2 is therefore the highest-risk change in the feature and must not be attempted before Step 1 is measured and merged.

**Alternatives considered**:
- *Merge event generation and state accumulation instead.* Rejected by `FR-004` — both already amortize startup well (~2.9–3.7s wall for ~2.3–2.9s SQL), so there is little to win and real ordering risk.

---

## Finding 6 — The 60k reference census is generated, and both sides of a gate must share it

**Decision**: Generate the census once per gate and reuse the identical file for baseline, candidate, and both determinism runs.

**Evidence**: The repository's largest census is 7,505 rows (`data/census_preprocessed.parquet`; the `_5k` and `_7k` variants are also 7,505). `scripts/perf_profile/make_large_census.py` scales by a factor — 7,505 × 8 = 60,040, the spec's reference figure. It asserts row count and id uniqueness after scaling (`make_large_census.py:97-102`).

**Rationale**: If the census were regenerated between the two sides of a comparison and the generation is not perfectly deterministic, parity would fail for reasons unrelated to the change — or worse, mask a real difference.

---

## Finding 7 — Prior guidance about per-year hazard-cache rebuilds is obsolete

**Decision**: Do not budget for hazard-cache rebuilds in years 2–5.

**Evidence**: The measured schedule shows the hazard-cache commands only in year 1, and the issue's baseline is explicitly stated as "after #516/#518". The earlier behavior — the cache-currency check querying the global database and therefore rebuilding caches every year on isolated-DB runs — was fixed by #516.

**Consequence**: Any note, memory, or plan that still treats per-year hazard rebuilds as ~22% of wall time is stale and must not be used to size this work.

---

## Resolved unknowns

| Spec open item | Resolution |
|---|---|
| How to collapse year-1 setup while honoring `FR-005` | Findings 1–4: delete the redundant build, merge the two full-refresh hazard commands, leave the incremental and seed groups alone. Floor of 3 confirmed. |
| Whether the parity harness is new or reuses Feature 121's | Reuse. `specs/121-reduce-dbt-invocations/contracts/correctness-parity.md` already defines the all-marts bidirectional `EXCEPT ALL` comparison and determinism re-run; this feature adds only the 60k-scale and five-year-horizon requirements. |
| Whether `SC-006`'s target of 14 can tighten | Only via optional Step 1c (seed+staging union, → 13), which trades new test execution for ~4.7s. Deferred unless Step 1 underdelivers. |

## Finding 8 — Historical command-count cohorts supersede the issue estimate

**Decision**: Use 102.7s as the historical 20-command baseline and derive bars
from observed command-removal campaigns: 3s for Story 1 and 6s for Story 2.

**Evidence**: Accepted 60,040-row campaigns under `var/perf_profile/` record
medians of 131.935s at 38 commands, 120.202s at 30 commands, and 102.720s at
20 commands. Those transitions value a removed command at 1.46–1.75s. The
fresh Feature 132 baseline measured 103.576s at 20 commands, confirming the
historical cohort. No recorded 20-command run approaches 91.5s; the fastest is
97.138s. The issue's named components also sum to 87.0s, not 91.5s.

**Consequence**: `dbt invocation wall − summed model execution` is retained as
a diagnostic residual, not interpreted as wholly removable startup. It includes
parse, adapter, and catalog work that can remain after commands are combined.
