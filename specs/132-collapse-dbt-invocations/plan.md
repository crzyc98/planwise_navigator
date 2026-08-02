# Implementation Plan: Collapse Remaining Per-Year Transformation Invocations

**Branch**: `132-collapse-dbt-invocations` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/132-collapse-dbt-invocations/spec.md`

## Summary

A five-year 60k run issues 20 dbt commands and has a historical median of 102.7s across 18 prior runs; this feature's fresh baseline is 103.576s. The issue's 91.5s headline is unreproducible and internally inconsistent. This plan removes commands without changing what any of them compute.

Phase 0 research found that the year-1 block is not merely inefficient — **one of its eight commands is pure waste**. `int_baseline_workforce` is built incrementally by the INITIALIZATION stage and then immediately **`--full-refresh`ed by FOUNDATION**, discarding the first build entirely. Deleting it is a removal, not a regrouping, and the stage it belongs to has no validation attached (`validate_stage` ignores `INITIALIZATION`). Historical cohorts value the removed command at ~1.5–1.75s, while the deletion is worthwhile independently because it removes provably discarded work.

The remaining reductions are two genuine merges — the hazard-cache pair, and the later-year setup command folded into event generation — each gated by the all-marts 60k parity check.

| Step | Change | Commands | Est. |
|---|---|---|---|
| 1a | Drop redundant year-1 `int_baseline_workforce` build | 20 → 19 | ~1.5–1.75s |
| 1b | Merge hazard-cache `run` + `build` into one `build` | 19 → 18 | ~1.5–1.75s |
| 2 | Fold later-year setup into event generation (4 years) | 18 → 14 | ~6–7s; stop candidate |

## Technical Context

**Language/Version**: Python 3.11 (orchestrator only). SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 — **no model file is modified by this feature**.
**Primary Dependencies**: `planalign_orchestrator` internals — `WorkflowBuilder.build_year_workflow` (`pipeline/workflow.py`), `YearExecutor._run_parallel_or_single` / `_should_full_refresh_foundation` (`pipeline/year_executor.py`), `HazardCacheManager.rebuild_hazard_caches`, `PipelineOrchestrator._run_start_year_setup`, `DbtRunner.execute_command` (schedule recorder), `StageValidator`. Measurement via `scripts/perf_profile` (`make_large_census`, `run_matrix`, `dbt_timing`).
**Storage**: DuckDB. Isolated per-run databases under `var/`; the shared `dbt/simulation.duckdb` is never built into.
**Testing**: pytest (`fast` / `integration` markers) for schedule-shape assertions in CI; the 60k all-marts parity gate is a **local pre-merge script** producing a committed artifact (per clarification Q4).
**Target Platform**: macOS / Linux developer laptop, single-threaded dbt (`--threads 1`).
**Project Type**: Internal orchestration library + CLI. No external interface changes.
**Performance Goals**: Story 1 ≥3s reduction; Story 2 ≥6s further reduction if attempted. Per-step, median of three. Bars are derived from observed 38 → 30 and 30 → 20 command-count cohorts.
**Constraints**: `FR-005` — a full rebuild must never be silently downgraded, and rebuild flags apply per command. `FR-006`–`FR-013` — all-marts bidirectional parity at 60k over five years, plus a determinism re-run, run locally with committed evidence.
**Scale/Scope**: 60,040 employees × 5 years. Three source files expected to change; zero dbt models.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| **I. Event Sourcing & Immutability** | No event semantics, schema, or seed determinism change. Reproducibility-given-seed is enforced positively by `FR-011`'s determinism re-run, which is stronger than the status quo. | ✅ Pass |
| **II. Modular Architecture** | Changes confined to three existing modules; no new module, no module growth, no layer inversion. Step 1a *removes* code. | ✅ Pass |
| **III. Test-First Development** | Schedule-shape tests (command count per year, rebuild-flag preservation) are written before each change and run in the fast suite. The 60k parity gate cannot run in CI (multiple ~103s runs), which is a partial tension — see Complexity Tracking. | ⚠️ Justified |
| **IV. Enterprise Transparency** | `FR-014`–`FR-016` explicitly preserve per-stage validation, telemetry, and failure attribution across merges. `run_execution_metadata` already records the finalized schedule. | ✅ Pass |
| **V. Type-Safe Configuration** | No configuration surface touched; no new Pydantic models. | ✅ Pass |
| **VI. Performance & Scalability** | This is performance work with a measured target. `--threads 1` is unchanged; merging commands does not raise peak memory (dbt builds nodes serially within a selection). | ✅ Pass |

**Post-Phase-1 re-check**: No new violations. The design added no modules, no dependencies, and no configuration. Step 1a reduces total code.

## Project Structure

### Documentation (this feature)

```text
specs/132-collapse-dbt-invocations/
├── plan.md              # This file
├── spec.md              # Feature specification (clarified 2026-08-02)
├── research.md          # Phase 0 — invocation-by-invocation findings
├── data-model.md        # Phase 1 — command schedule + parity result entities
├── quickstart.md        # Phase 1 — how to run the gate and the measurement
├── contracts/
│   ├── command-schedule.md    # The invariant shape of the schedule, per step
│   └── parity-gate.md         # The all-marts 60k gate, adapted from Feature 121
├── checklists/
│   └── requirements.md  # Spec quality checklist (passing)
└── evidence/            # Committed parity + timing artifacts (FR-013)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── pipeline/
│   ├── workflow.py             # CHANGED — start-year stage composition (steps 1a, 2)
│   ├── year_executor.py        # CHANGED — rebuild-flag resolution (step 2 guard)
│   └── stage_validator.py      # unchanged (read during research; no INITIALIZATION rule)
├── hazard_cache_manager.py     # CHANGED — merge the run+build pair (step 1b)
└── pipeline_orchestrator.py    # possibly CHANGED — start-year setup ordering

scripts/perf_profile/           # unchanged — reused for measurement
├── make_large_census.py        # generates the 60,040 reference census (8× scale)
├── run_matrix.py
└── dbt_timing.py

scripts/
└── parity_gate.py              # NEW — all-marts bidirectional comparison driver

tests/
├── test_workflow_schedule.py   # NEW (fast) — command count + rebuild-flag assertions
└── integration/
    └── test_stage_attribution.py  # NEW — failure still names year + stage after merges

dbt/                            # UNCHANGED — no model, seed, or macro is modified
```

**Structure Decision**: Existing single-project layout. The feature is a behavior-preserving change to orchestration only; the one new source file is the parity-gate driver, which lives with the other operational scripts rather than in the package, because it is a development gate and not product code.

## Phase 0: Research

See [research.md](./research.md). Resolved every open question from the spec; no `NEEDS CLARIFICATION` remains.

Headline findings:

1. **The year-1 INITIALIZATION build is redundant** (`workflow.py:120-123` builds `int_baseline_workforce`; `workflow.py:130-146` rebuilds it, and `_should_full_refresh_foundation` returns `True` at start year). The first build's output is discarded.
2. **`INITIALIZATION` has no validation.** `StageValidator.validate_stage` branches only on `FOUNDATION`, `EVENT_GENERATION`, and `STATE_ACCUMULATION`; the declared `data_freshness_check` rule is never dispatched. Removing the stage's models has no observability cost.
3. **The full-rebuild floor is 3, not 2**, confirming `SC-006`'s relaxed target of 14: the year-1 block contains a seed load, one full-refresh group, and one incremental group that cannot legally merge.
4. **Event generation selects by tag, state accumulation selects by model list** (`stage_execution_strategies.py:26-43` vs `year_executor.py:308-331`). Step 2 must union foundation models into a tag selection, which is the shape Tier B already proved.
5. **The hazard-cache pair passes an extra dbt var** (`hazard_params_hash`) that the workflow's vars do not carry — a merge must preserve it or the caches silently rebuild against the wrong hash.

## Phase 1: Design & Contracts

- [data-model.md](./data-model.md) — the command schedule, reference workload, parity result, and step record, with the invariants each must satisfy.
- [contracts/command-schedule.md](./contracts/command-schedule.md) — the exact expected schedule before and after each step; this is what the fast tests assert against.
- [contracts/parity-gate.md](./contracts/parity-gate.md) — the all-marts gate, inherited from Feature 121 and extended with the 60k-scale and five-year-horizon requirements.
- [quickstart.md](./quickstart.md) — generating the census, running a gate, reading the result.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Constitution III — the primary correctness gate does not run in CI | The gate requires multiple full 60k runs at ~103s each plus census generation and database builds. CI is sharded on measured durations with a coverage ratchet; adding a multi-minute memory-heavy job would distort shard balance for every unrelated PR, to guard a change that ships twice. | *Gate in CI permanently*: cost is borne by every PR forever for a two-PR feature. *Gate at 7.5k in CI*: the spec explicitly classifies 7.5k parity as non-evidence — Tier C passed at 7.5k and broke at 60k — so a green CI check would actively mislead. **Mitigation**: the cheap half of the testing *is* in CI — schedule-shape and rebuild-flag assertions run in the fast suite, so a regrouping that changes command structure cannot land unnoticed. Only the expensive row-level comparison is local, and `FR-013` requires its full output be committed as a reviewable artifact rather than asserted. |
