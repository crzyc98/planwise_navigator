# Implementation Plan: Studio Workflows for Parameter Fit and Backtest

**Branch**: `588-studio-fit-backtest` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/588-studio-fit-backtest/spec.md`

## Summary

This feature exposes the CLI-only `planalign fit` and `planalign backtest` workflows in Studio. The analyst team uses Studio exclusively.

- **Uploads**: a workspace-scoped, immutable history set, validated by the fitter itself.
- **Jobs**: run as cancellable CLI subprocesses that report structured progress. Job records persist on disk per workspace, with bounded retention.
- **Results**: surfaced from the pack, a new additive `diagnostics.json`, and the scorecard.
- **Apply**: a pack becomes a *new* scenario after a fingerprint-verified review handshake. Pack seeds are layered into Studio runs, and the promotion hazard is translated into editable config.

Delivered as three slices: backend jobs, then apply, then the Studio UI.

## Technical Context

**Language/Version**: Python 3.11; TypeScript 5.8 / React 19 (Studio)
**Primary Dependencies**: FastAPI, Pydantic v2, `planalign_fit`, `planalign_backtest`, Typer CLI, React Router 7, Tailwind 4, lucide-react
**Storage**: Workspace filesystem (JSON records, pack directories). Per-seed isolated DuckDBs for backtest scratch. No shared-DB access.
**Testing**: pytest (`fast` marker for API and unit tests; one slow end-to-end backtest), vitest for pure UI helpers, the OpenAPI snapshot contract test
**Target Platform**: Local Studio (macOS/Linux; Windows-tolerant process termination)
**Project Type**: Web application (FastAPI backend + React SPA) over Python packages
**Performance Goals**: Launch responds in under 2 s; cancel takes effect in under 10 s; preview hashes 5 × ~50 MB files in a few seconds
**Constraints**: Never touch `dbt/simulation.duckdb`; single-threaded dbt (`threads=1`, already enforced by backtest); modules ≤ ~600 lines; functions ≤ 40 lines; cognitive complexity ≤ 15
**Scale/Scope**: ≤ 20 retained jobs per workspace; ≤ 1 concurrent backtest per workspace; 2–5 snapshots per set

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Event sourcing & immutability | ✅ | No event-store changes. Backtest seeds run in isolated DBs. Packs are immutable evidence; apply creates a new scenario. |
| II. Modular architecture | ✅ | New `planalign_api/services/param_fit/` package, split into history, jobs, runner, results and apply modules, each under 600 lines. The router only wires HTTP. |
| III. Test-first | ✅ | Tests are written before each slice's implementation (tasks.md orders them first). Fast-marked tests use small synthetic histories and a stub subprocess. One slow end-to-end test is not fast-marked. |
| IV. Enterprise transparency | ✅ | Every job records its inputs, hashes, moved settings and errors. Pack-derived scenarios carry full provenance, and `run_metadata` records the pack identity. |
| V. Type-safe configuration | ✅ | Pydantic v2 request and response models with bounds that mirror CLI validation. |
| VI. Performance & scalability | ✅ | Subprocesses keep the API responsive. Single-threaded dbt. At most one backtest per workspace. |

Post-design re-check: ✅ no violations; the Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/588-studio-fit-backtest/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/api.md  contracts/progress-protocol.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
planalign_fit/
├── diagnostics.py        # NEW build_diagnostics(run) -> dict
├── progress.py           # NEW env-gated PLANALIGN_FIT_PROGRESS| emitter
├── pack.py               # write_pack(..., diagnostics=None) → diagnostics.json
├── apply.py              # apply_pack(..., seeds_root=None)
└── runner.py             # progress stages
planalign_backtest/runner.py   # progress events; seeds_root passthrough; expose fit run
planalign_cli/commands/
├── fit.py                # write diagnostics.json
├── backtest.py           # write fit_report.md + diagnostics.json; simulation_failed event
└── gc.py                 # sweep workspaces/*/param_fits/*/work
planalign_api/
├── config.py             # param_fit_max_jobs_per_workspace
├── models/param_fit.py   # NEW API models
├── routers/param_fits.py # NEW routes (history, jobs, reports, apply)
├── main.py               # register router
└── services/
    ├── param_fit/        # NEW
    │   ├── __init__.py
    │   ├── history.py    # upload/list/preview/delete history sets
    │   ├── jobs.py       # JobStore: job.json persistence, reconciliation, retention
    │   ├── runner.py     # subprocess launch, progress parsing, cancel, exit-code mapping
    │   ├── results.py    # read pack/diagnostics/scorecard; staleness
    │   └── apply.py      # apply preview + create pack-derived scenario
    └── simulation/
        ├── run_execution.py  # write_seeds(..., pack_seeds_dir=None)
        └── service.py        # pass scenario param_pack/seeds
planalign_studio/
├── App.tsx  components/Layout.tsx     # route + nav
├── services/api.ts  services/api.generated.ts
└── components/paramFit/
    ├── ParamFitPage.tsx  HistoryStep.tsx  ConfigureStep.tsx  JobList.tsx
    ├── JobProgress.tsx  FitResults.tsx  BacktestScorecard.tsx  ApplyPackModal.tsx
    └── paramFitHelpers.ts  paramFitHelpers.test.ts
tests/
├── test_parameter_fitting.py           # + diagnostics/fingerprint-invariance tests
├── test_fit_progress.py                # NEW progress protocol
├── api/test_param_fit_history.py       # NEW
├── api/test_param_fit_jobs.py          # NEW (stub subprocess: success/failure/cancel/interrupted/retention)
├── api/test_param_fit_apply.py         # NEW (apply, stale, acks, name collision, source preserved)
├── api/test_param_fit_backtest_e2e.py  # NEW slow real fit+backtest via the API service
└── unit/simulation/test_simulation_service.py  # + pack seed layering
```

**Structure Decision**: This is a web-application layout on top of the existing packages. Fit and backtest logic stays in `planalign_fit` and `planalign_backtest`. The API adds one service package and one router. Studio adds one component folder.

## Delivery slices (one commit each on this branch)

1. **Backend jobs**: diagnostics.json, the progress protocol, `seeds_root`, history, jobs, the runner, results, retention, gc, routes (without apply), and the OpenAPI snapshot.
2. **Apply**: pack seed layering in Studio runs, the apply preview and apply, and staleness enforcement.
3. **Studio UI**: the page, API client, generated types, nav, and vitest helpers.

## Complexity Tracking

None.
