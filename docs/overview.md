# Platform Overview

## What it is

Fidelity PlanAlign Engine is an on-premises workforce-simulation platform. It projects
a workforce forward year by year — hires, terminations, promotions, raises — together
with the full DC-plan (401(k)) lifecycle: eligibility, enrollment, deferrals, employer
match, vesting, and compliance events. Every simulated decision is recorded as an
immutable event, so any result can be audited and any scenario reproduced exactly from
its random seed.

Typical uses:

- **Headcount and compensation planning** — project growth, turnover, and comp spend
  under a target growth rate, with an algebraic solver that hits headcount targets
  deterministically (E077).
- **DC-plan design** — compare match formulas (including tenure-graded multi-tier
  match), auto-enrollment designs, and eligibility rules across scenarios.
- **Calibration** — tune COLA/merit levers against a compensation-growth target
  (`planalign calibrate`) ~3–5× faster than a full simulation, with exact results.

## Interfaces

| Interface | Entry point | Audience |
|-----------|-------------|----------|
| **CLI** (`planalign`) | Rich + Typer terminal app | Analysts, day-to-day runs |
| **PlanAlign Studio** | `planalign studio` — FastAPI backend (:8000) + React/Vite frontend (:5173) | Scenario management via web UI |
| **Python API** | `build_orchestrator(ConstructionSpec(...))` | Programmatic / test use through the canonical seam |

CLI commands: `simulate`, `calibrate`, `batch`, `analyze`, `validate`, `status`,
`health`, `studio`, `sync`.

## Technology stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Storage / engine | DuckDB 1.0.0 | Column-store OLAP; one `.duckdb` file per scenario |
| Transformation | dbt-core 1.8.8 + dbt-duckdb 1.8.1 | ~156 SQL models (38 staging, 108 intermediate, 10 marts) |
| Orchestration | `planalign_orchestrator` (Python 3.11) | Staged multi-year pipeline |
| Domain model | `planalign_core` (Pydantic v2) | Event payloads, config schema, constants |
| API | FastAPI (`planalign_api`) | REST + WebSocket telemetry |
| Frontend | React/Vite + Tailwind CSS v4 (`planalign_studio`) | Bundled locally; no CDNs |
| Packaging | uv | Editable install via `uv pip install -e ".[dev]"` |

## Key properties

- **Immutability** — events in `fct_yearly_events` are append-only, UUID-stamped.
- **Reproducibility** — identical config + seed ⇒ identical results, across platforms.
- **Auditability** — workforce state at any point reconstructs from the event stream;
  batch exports embed git SHA, seed, and configuration metadata.
- **Isolation** — scenarios run in separate database files; the shared dev database
  (`dbt/simulation.duckdb`) is never used to validate behavioral changes
  (see [development.md](development.md)).

Current version: see `_version.py` (v2.1.0 "Studio & Compliance" at the time of writing).
