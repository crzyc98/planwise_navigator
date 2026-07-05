# Architecture

## Package layout

```
planalign_core/          Shared domain package: event payloads (Pydantic v2),
                         simulation config schema, constants, network config
planalign_orchestrator/  Simulation engine: pipeline stages, dbt runner,
                         event generators, validation, error handling
planalign_cli/           Rich/Typer terminal interface (planalign command)
planalign_api/           FastAPI backend for Studio (REST + WebSocket)
planalign_studio/        React/Vite + Tailwind v4 frontend
dbt/                     dbt project: staging → intermediate → marts
config/                  YAML configuration only (simulation_config.yaml)
var/                     Runtime outputs (git-ignored): artifacts, reports,
                         logs, outputs, backups
workspaces/              Studio workspace storage (planalign_api settings)
```

Dependency direction: `planalign_cli` and `planalign_api` sit on top of
`planalign_orchestrator`, which (like everything else) imports domain types from
`planalign_core`. Nothing imports from the CLI or API layers.

## Event sourcing

The system of record is `fct_yearly_events`: an append-only table of UUID-stamped,
typed events. Workforce state (`fct_workforce_snapshot`) is a point-in-time
projection derived from events, never edited in place.

Principles:

- **Immutability** — events are written once per (scenario, plan design, year).
- **Reproducibility** — same config + random seed ⇒ byte-identical event stream.
- **Type safety** — every payload is a Pydantic v2 model in `planalign_core.events`
  (see [data-model.md](data-model.md)).

New event types implement the `EventGenerator` ABC in
`planalign_orchestrator/generators/` and register via
`@EventRegistry.register("name")`; `generators/sabbatical.py` is the minimal example.

## Pipeline

`PipelineOrchestrator.execute_multi_year_simulation(start_year, end_year)` runs each
year through the stages defined in `planalign_orchestrator/pipeline/workflow.py`:

1. **INITIALIZATION** — load seeds and staging data
2. **FOUNDATION** — baseline workforce and compensation
3. **EVENT_GENERATION** — hire / termination / promotion / merit / enrollment events
4. **STATE_ACCUMULATION** — accumulators, `fct_yearly_events`, snapshots
5. **VALIDATION** — data-quality checks (dbt tests)
6. **REPORTING** — audit reports and run summaries
7. **CLEANUP** — post-run cleanup

Pipeline modules (`planalign_orchestrator/pipeline/`): `workflow.py` (stage
definitions), `state_manager.py`, `year_executor.py`,
`event_generation_executor.py`, `hooks.py`, `data_cleanup.py`.

## dbt layers

~156 models in three tiers, built with `--threads 1`:

| Tier | Prefix | Count | Role |
|------|--------|-------|------|
| Staging | `stg_*` | 38 | Clean raw/seed data |
| Intermediate | `int_*` | 108 | Business logic, event generation, accumulators |
| Marts | `fct_*`, `dim_*` | 10 | Final outputs |

Heavy models filter by `{{ var('simulation_year') }}` and use incremental
materialization with `incremental_strategy='delete+insert'`.

**Circular-dependency rule:** `int_*` models must not read `fct_*` tables, with two
sanctioned exceptions — `fct_yearly_events` (built first in STATE_ACCUMULATION) and
prior-year reads of `fct_workforce_snapshot`.

## Temporal state accumulators

Cross-year state (enrollment, deferral rates) uses the accumulator pattern: Year N
reads Year N−1 rows from `{{ this }}` plus Year N events, producing state without
circular refs. Examples: `int_enrollment_state_accumulator`,
`int_deferral_rate_state_accumulator`.

Build order within a year:
accumulators → `int_*` events → `fct_yearly_events` → `fct_workforce_snapshot`.

## Error handling

`planalign_orchestrator/exceptions.py` defines a `NavigatorError` hierarchy
(`DatabaseError`, `ConfigurationError`, `PipelineError`, `DbtError`,
`ResourceError`, `StateError`) carrying execution context (stage, model,
correlation ID) and resolution hints; `error_catalog.py` pattern-matches known
failures.

## Databases

- `dbt/simulation.duckdb` — shared dev database; fine for reads, never for
  validating changes.
- One isolated `.duckdb` per scenario for batch runs and Studio simulations.
- `get_database_path()` (from `planalign_orchestrator.config`) resolves the active
  database and honors the `DATABASE_PATH` environment variable.
