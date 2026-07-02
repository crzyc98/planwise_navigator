# Implementation Plan: Fast Compensation Calibration Mode

**Branch**: `105-comp-calibration` | **Date**: 2026-06-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/105-comp-calibration/spec.md`

## Summary

Add a `planalign calibrate <start>-<end>` CLI command (plus a Studio calibration panel) that rebuilds **only** the compensation/workforce dbt subgraph per simulation year against an **isolated database**, reusing the existing E077 deterministic solver, mid-year proration, band-aware merit/COLA/promotion logic, and the S051 `fct_compensation_growth` mart **verbatim**, while skipping the entire DC-plan / enrollment / vesting / contribution / match stack. Because the comp metrics are produced by the identical validated SQL, they are **exact** vs. a full simulation — the speedup (~3–5×) comes purely from building fewer models, not from approximation.

**Technical approach**: Introduce a *calibration workflow variant* of `WorkflowBuilder.build_year_workflow` that drops DC models from the EVENT_GENERATION and STATE_ACCUMULATION stages while keeping `fct_yearly_events` and `fct_workforce_snapshot` in the build set. The snapshot/event-stream `ref()`s to DC models resolve against **stale-but-present** DC tables (Design 1, see research.md), which never feed the comp columns. A fail-fast prerequisite guard verifies those DC tables exist before the run. A thin `CalibrationRunner` orchestrates per-year partial builds and reads `fct_compensation_growth` for the per-year delta table; the CLI and a new `/api/calibration` router/Studio panel are thin presentation layers over it.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator/CLI/API); SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1; TypeScript/React (Studio)
**Primary Dependencies**: Typer + Rich (CLI), Pydantic v2 (config), FastAPI (API), React/Vite + Tailwind (Studio), DuckDB 1.0.0
**Storage**: DuckDB. No new tables — calibration reuses `fct_yearly_events`, `fct_workforce_snapshot`, `fct_compensation_growth`. Default target is an isolated `<calibration>.duckdb`, never the shared `dbt/simulation.duckdb`.
**Testing**: pytest (`-m fast` unit, `-m integration`); dbt tests; isolated-DB integration per CLAUDE.md
**Target Platform**: macOS/Linux work-laptop CLI + local Studio web app
**Project Type**: Web (CLI + orchestrator backend + FastAPI + React frontend) — existing structure, no new top-level projects
**Performance Goals**: 5-year calibrate run ~3–5× faster than the ~11-min full sim (target ~2–4 min); comp metrics bit-for-bit exact
**Constraints**: `--threads 1` default (work-laptop stability); must never mutate the shared dev DB on a default run; fail fast (<seconds) when DC prerequisite tables are absent
**Scale/Scope**: 100K+ employee records; ~17-model comp subgraph rebuilt per year; one calibration run at a time (no automated sweep)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | Calibration **reads** `fct_yearly_events`/snapshot produced by the same immutable-event SQL; it does not invent a parallel event model. It generates no new event types and writes only to an isolated DB. Stale DC events are left untouched (immutable), never edited. |
| II. Modular Architecture | ✅ PASS | New code is a focused `CalibrationRunner` + a calibration `WorkflowBuilder` variant + thin CLI command and API router. Each stays well under the ~600-line / 6–8-method guidance. No new circular deps (still staging→intermediate→marts; comp subgraph is a strict subset of the existing DAG). |
| III. Test-First Development | ✅ PASS | Plan mandates fast unit tests for the workflow-variant model selection + prerequisite guard, and an integration test asserting exactness vs. a full-sim baseline DB (written before wiring the CLI). |
| IV. Enterprise Transparency | ✅ PASS | Calibration runs reuse existing audit logging; the prerequisite guard emits a contextual, actionable error (correlation with the standard error catalog). Per-year deltas are explicit and reproducible given seed+config. |
| V. Type-Safe Configuration | ✅ PASS | Reuses existing `CompensationSettings` Pydantic models and `to_dbt_vars()`. No raw SQL string concatenation; dbt `{{ ref() }}` only. New API payloads are Pydantic models. |
| VI. Performance & Scalability | ✅ PASS | The whole point is fewer models → faster; `--threads 1` stays default. No regression to existing paths (additive). |

**Result**: PASS — no violations, Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/105-comp-calibration/
├── plan.md              # This file
├── research.md          # Phase 0 output — design decisions (Design 1 vs 2, model set, exactness proof)
├── data-model.md        # Phase 1 output — entities (Calibration Run, Param Set, Per-Year Result)
├── quickstart.md        # Phase 1 output — how to run + verify exactness
├── contracts/
│   ├── cli-calibrate.md         # CLI command contract (args, output table, exit codes)
│   └── api-calibration.md       # FastAPI calibration endpoints + payloads
└── checklists/
    └── requirements.md  # (from /speckit.specify)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── calibration_runner.py            # NEW: CalibrationRunner — per-year comp-only build + result assembly
├── pipeline/
│   └── workflow.py                  # MODIFIED: add build_calibration_year_workflow() variant (comp-only stages)
├── pipeline_orchestrator.py         # REUSED: update_compensation_parameters() for interactive re-tune
├── scenario_batch_runner.py         # REFERENCE: isolated-DB pattern to mirror for default calibration DB
└── config/
    ├── simulation.py                # REUSED: CompensationSettings (cola_rate, merit_budget, ...)
    └── export.py                    # REUSED: to_dbt_vars()

planalign_cli/
├── commands/
│   └── calibrate.py                 # NEW: run_calibration() + --interactive loop (mirrors simulate.py)
└── main.py                          # MODIFIED: register @app.command("calibrate")

planalign_api/
├── routers/
│   └── calibration.py               # NEW: POST /api/calibration/run, result models
└── main.py                          # MODIFIED: include calibration router

planalign_studio/
└── components/
    └── CalibrationPanel.tsx         # NEW: sliders (target growth, COLA, merit, new-hire mix) + per-year charts

dbt/                                 # NO new models for Design 1 (stale-but-present)
                                     # Design 2 (lean snapshot) deferred — see research.md

tests/
├── test_calibration_workflow.py     # NEW (fast): comp-only model set excludes DC; guard logic
├── test_calibration_runner.py       # NEW (fast): result assembly, year-range parsing, isolated-DB default
└── test_calibration_exactness.py    # NEW (integration): comp columns == full sim under same + edge config
```

**Structure Decision**: Reuse the existing web/CLI/orchestrator layout — no new top-level projects. The feature is additive: one new orchestrator module (`CalibrationRunner`), one new workflow-builder method, thin CLI/API/Studio presentation layers, and three test modules. dbt models are unchanged under the chosen Design 1.

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.
