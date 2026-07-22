# Implementation Plan: Reduce Production-Path dbt Invocations — Batch the Studio Run Schedule

**Branch**: `121-reduce-dbt-invocations` | **Date**: 2026-07-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/121-reduce-dbt-invocations/spec.md`

## Summary

Reduce the fixed per-invocation orchestration cost of the canonical five-year Studio production run by **batching dependency-compatible dbt selections and eliminating redundant single-model calls**, with zero change to simulation outputs, determinism, event ordering, diagnostics, or the isolated-DB rule.

**Critical baseline correction (drives this whole plan).** The issue's premise — "62 dbt invocations, reduce to ≤32" — rests on a number that has since been proven **not to be an invocation count**. Feature 120's authoritative work-schedule baseline (`specs/120-unify-orchestrator-construction/work-schedule-baseline.md`), measured with the recorder installed at `DbtRunner.execute_command` on the canonical construction seam, establishes that the current product path issues **38 dbt commands** for a five-year run over the 60,040-employee Studio census — and that the retained "62" counted log/subprocess records with different semantics, not separately issued commands. The real schedule is `seed + staging + int_effective_parameters + 5 hazard-cache builds` (8 first-year prep) `+ 6 commands × 5 years` (30) `= 38`.

This plan therefore **exercises FR-003's escape hatch** ("planning publishes a stricter, evidence-based safe floor before implementation"): it re-baselines on HEAD (expected 38), retires "62" as a non-baseline, and targets a floor derived from the real 38-command schedule. The concrete, dependency-safe consolidations are:

- **Tier A — hazard-cache batch (highest-confidence win):** the hazard-cache rebuild issues **6 separate single-model `--full-refresh` invocations** (`int_effective_parameters`, then `dim_promotion_hazards` / `dim_termination_hazards` / `dim_merit_hazards` / `dim_enrollment_hazards`, then `hazard_cache_metadata`). Batch the four `dim_*_hazards` + metadata into one `dbt build --select … --full-refresh`, and fold `int_effective_parameters`. First-year prep **8 → ~4**.
- **Tier B — per-year INITIALIZATION+FOUNDATION merge:** both stages already run as a single sequential selection; merge into one DAG-ordered selection. **2 → 1 per year (−5)**. Guarded by the year-1 FOUNDATION full-refresh rule.
- **Tier C — per-year STATE_ACCUMULATION split collapse:** the stage splits into 3 invocations only because `int_workforce_snapshot_optimized` requires `--full-refresh` mid-list. Collapse where the full-refresh requirement can be lifted safely. **3 → 1–2 per year (−5 to −10)**. Highest risk (touches incremental/full-refresh correctness).

Realistic evidence-based floor: **38 → ~20–26**, comfortably under the issue's ≤32. **But the true ship arbiter is the ≥20% warm wall-time gate (FR-017), not the invocation count** — at 38 commands over ~131s (~3.4s/command, much of it real model execution), per-invocation overhead may already be a minority. If cumulative warm improvement falls short of 20%, the plan does **not** auto-ship or auto-abort: it presents the before/after evidence to the maintainer for an explicit ship / no-ship decision (per the clarified human-decision gate).

Approach is **incremental and independently measured**: apply Tier A, then B, then C; after each, measure invocation count, warm wall time (median-of-three), per-component split, and peak RSS against the HEAD baseline, and verify byte-identical outputs across every `fct_*`/`dim_*` mart.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator); SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated `.sql`, unmodified for behavior)
**Primary Dependencies**: `planalign_orchestrator` internals — `DbtRunner.execute_command` (invocation seam + schedule recorder), `PipelineOrchestrator`, `YearExecutor` (`_run_sequential_event_models`, `_group_models_by_full_refresh`, `_run_parallel_or_single`), `WorkflowBuilder.build_year_workflow`, `HazardCacheManager.rebuild_hazard_caches`; measurement via `scripts.perf_profile` (`run_matrix`, `build_production_report`, `dbt_timing`); `run_execution_metadata` / `run_metadata` DuckDB tables
**Storage**: DuckDB. **No schema or behavior change to any `fct_*`/`int_*`/`dim_*` model.** The only intended change is *how many* dbt commands the orchestrator issues and *which models share a command* — never what a model computes. Every behavioral run uses an isolated per-run DB; the shared `dbt/simulation.duckdb` is never built into.
**Testing**: pytest (fast + integration markers, E075 fixtures); the `scripts.perf_profile` harness for wall-time/RSS/invocation measurement; order-insensitive multiset parity (`EXCEPT ALL` both directions) over all marts; existing determinism / multi-year-invariant (Feature 113) / rerun-on-existing-output / failed-stage suites
**Target Platform**: Local macOS / work-laptop; single-threaded dbt (`--threads 1`) is the default and is preserved
**Project Type**: Single project — orchestration engine (Python) driving a dbt/DuckDB pipeline. No frontend/API change.
**Performance Goals**: ≥20% median warm wall-time improvement vs the HEAD baseline (ship gate); invocation count from 38 to a published safe floor (~20–26), ≤32 required; per-tier attribution of subprocess launch vs dbt command wall vs model execution vs residue
**Constraints**: byte-identical outputs across all `fct_*`/`dim_*` marts (audit-timestamp fields exempt); determinism preserved; event ordering + transaction boundaries preserved; model/stage/year failure attribution preserved; peak RSS ≤ +10% vs baseline; no DC-plan/workforce SQL edits unless timing names a specific slow node
**Scale/Scope**: 60,040-employee Studio census, five-year horizon (2025–2029), ~645k events — the exact profiled production workload

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Event Sourcing & Immutability** | ✅ No event schema/content change; determinism preserved (identical seed+config → identical events). Reproducibility is an explicit acceptance gate (FR-010). |
| **II. Modular Architecture** | ✅ Changes are localized to existing seams (`HazardCacheManager`, `YearExecutor`, `WorkflowBuilder`); no new circular deps (staging→intermediate→marts unchanged). No module grows materially; batching *reduces* call-site count. |
| **III. Test-First Development** | ✅ Invocation-count assertions, all-mart parity checks, and failure-attribution tests are written before each consolidation tier (Red-Green). Fast suite stays <10s; parity/perf checks run as integration against isolated DBs. |
| **IV. Enterprise Transparency** | ✅ Model/stage/year failure context and stage/year telemetry are a hard requirement (FR-012); the `run_execution_metadata` ordered schedule keeps every issued command auditable; before/after artifacts recorded (FR-018). |
| **V. Type-Safe Configuration** | ✅ No config surface change; no raw-SQL table-reference concatenation introduced (selections remain `{{ ref() }}`-resolved model names). |
| **VI. Performance & Scalability** | ✅ This *is* a performance feature; single-threaded default preserved; peak RSS bounded ≤ +10% (FR-015); 100k+ record handling unaffected. |

**Gate result: PASS.** No violations; Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/121-reduce-dbt-invocations/
├── plan.md              # This file
├── research.md          # Phase 0: baseline reframing + per-tier decisions
├── data-model.md        # Phase 1: entities (schedule, tier, run-cost artifact, parity, ship record)
├── quickstart.md        # Phase 1: how to baseline, consolidate, measure, gate
├── contracts/           # Phase 1: internal contracts
│   ├── invocation-schedule.md      # recorded schedule + safe-floor definition
│   ├── hazard-cache-batch.md       # batched hazard-cache rebuild contract
│   └── correctness-parity.md       # all-mart multiset parity gate
└── checklists/
    └── requirements.md  # spec quality checklist (already complete)
```

### Source Code (repository root)

No new source directories. The change touches existing orchestrator seams only:

```text
planalign_orchestrator/
├── hazard_cache_manager.py         # Tier A: batch the 4 dim_*_hazards + metadata (+ fold int_effective_parameters) into 1–2 invocations
├── pipeline/
│   ├── workflow.py                 # Tier B/C: stage model lists (grouping hints; no model-content change)
│   └── year_executor.py            # Tier B: merge INIT+FOUNDATION selection; Tier C: relax STATE_ACCUMULATION full-refresh split (_group_models_by_full_refresh / _run_parallel_or_single)
└── dbt_runner.py                   # unchanged behavior; already hosts the execute_command recorder seam

scripts/perf_profile/               # measurement only (unchanged product behavior)
└── run_matrix.py / build_production_report.py / dbt_timing.py

tests/
├── unit/                           # invocation-count + full-refresh-grouping assertions (fast)
└── integration/                    # all-mart parity, determinism, RSS, failure-attribution against isolated DBs
```

**Structure Decision**: Single-project orchestration engine. The feature is a surgical consolidation of dbt invocation call-sites inside three existing modules plus test/measurement additions; it introduces no new packages, services, or model files, consistent with Constitution II (modular, no new abstraction where an existing seam suffices).

## Complexity Tracking

> No Constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
