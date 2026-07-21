# Fidelity PlanAlign Engine

**An enterprise-grade, on-premises workforce and DC-plan simulation platform with immutable event sourcing — built on DuckDB, dbt, FastAPI, and React.**

Current version: **2.2.0** ("Calibration") — see [CHANGELOG.md](CHANGELOG.md).

## Overview

Fidelity PlanAlign Engine replaces rigid spreadsheet projections with a transparent, reproducible simulation engine — a workforce "time machine" that records every modeled employee lifecycle and retirement-plan event with UUID-stamped precision and enables instant scenario replay and comparison.

Plan sponsors and their advisors use it to estimate the multi-year financial impact of retirement plan design changes — match formulas, auto-enrollment strategies, vesting schedules, eligibility rules — against projected workforce demographics. See [METHODOLOGY.md](METHODOLOGY.md) for the full modeling methodology, assumptions, and limitations.

### Key Features

- **Immutable event sourcing** — every modeled event recorded with UUID, timestamp, and provenance keys (`scenario_id`, `plan_design_id`, `simulation_year`)
- **Multi-year simulation** — sequential year-by-year execution with temporal state accumulators (no circular dependencies)
- **Deterministic reproducibility** — identical inputs + random seed produce identical outputs
- **Modular engines** — compensation, termination, hiring, promotion, DC plan, and plan administration
- **Fast compensation calibration** — comp-only rebuilds that are exact vs. a full simulation, ~3–5× faster (`planalign calibrate`)
- **Scenario isolation** — one DuckDB database per scenario for batch and Studio runs
- **Batch processing** — multi-scenario runs with Excel export, comparison reports, and traceability metadata (git SHA, seed, config)
- **PlanAlign Studio** — web-based scenario management with real-time simulation telemetry
- **Workspace cloud sync** — Git-based workspace synchronization across devices (`planalign sync`)
- **Configurable everything** — age/tenure bands, hazard multipliers, match formulas (including tenure-graded multi-tier), new-hire demographics, IRS limits — all via seeds, YAML, or the Studio UI
- **On-premises only** — zero cloud dependencies; see [SECURITY.md](SECURITY.md)

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Storage** | DuckDB | 1.0.0 | Immutable event store; in-process OLAP engine |
| **Transformation** | dbt-core | 1.8.8 | SQL-based data modeling and testing |
| **Adapter** | dbt-duckdb | 1.8.1 | Stable DuckDB integration |
| **Orchestration** | planalign_orchestrator | 2.2.0 | Staged multi-year pipeline execution |
| **CLI** | planalign (Rich + Typer) | 2.2.0 | Terminal interface with progress tracking |
| **Web Studio** | FastAPI + React/Vite | 2.2.0 | Web-based scenario management |
| **Frontend Styling** | Tailwind CSS | 4.x | Bundled via `@tailwindcss/vite` — never CDN |
| **Configuration** | Pydantic | 2.7.4 | Type-safe parameter management |
| **Git Sync** | GitPython | 3.1.0+ | Workspace cloud synchronization |
| **Python** | CPython | 3.11 / 3.12 | 3.13+ not yet supported (pydantic-core wheels) |

## Architecture

### Event-Sourced Data Flow

```
Raw Census Data → Staging Models → Event Generation → Immutable Event Store → Snapshots → Analytics
                     (stg_*)        (modular engines)   (fct_yearly_events)   (point-in-time)
```

1. **Staging layer** (`stg_*`, 20 models): clean and validate raw census data
2. **Event generation** (`int_*`, 61 models): modular engines create UUID-stamped workforce and DC-plan events
3. **Event store**: audit trail in `fct_yearly_events` (delete+insert by year)
4. **Snapshot layer** (`fct_*`/`dim_*`, 22 mart models): point-in-time workforce states reconstructed from events
5. **Analytics**: scenario comparison, cost projection, and vesting analysis via PlanAlign Studio and batch exports

### Pipeline Stages (per simulation year)

`PipelineOrchestrator` executes six sequential stages per year:

All product, Studio, batch, test, and performance callers construct it through
`planalign_orchestrator.build_orchestrator(ConstructionSpec(...))`. The builder
is the only supported programmatic construction seam; it emits the comparable
construction signature and records the executed dbt work schedule.
**INITIALIZATION → FOUNDATION → EVENT_GENERATION → STATE_ACCUMULATION → VALIDATION → REPORTING**

### Modular Engines

- **Compensation**: COLA, merit, and promotion-based adjustments with band-aware math and the E077 deterministic growth solver
- **Termination**: hazard-based turnover with age/tenure multipliers
- **Hiring**: growth-driven recruitment with configurable demographic sampling
- **Promotion**: band-aware advancement with level dampening
- **DC Plan**: eligibility, enrollment (auto/voluntary), deferral escalation, contributions, match, vesting
- **Plan Administration**: forfeitures, HCE determination, IRS limit application

### Seed Configuration Fallback Chain

Seed-based parameters (bands, hazards, IRS limits, match tiers) follow a strict override hierarchy:

1. **Scenario overrides** (`config_overrides`) — highest priority
2. **Workspace base config** (`base_config.yaml`)
3. **Global CSV seeds** (`dbt/seeds/config_*.csv`) — project defaults

## Directory Structure

```
fidelity_planalign/
├── planalign_orchestrator/        # Production orchestration engine
│   ├── pipeline/                  # Modular pipeline (workflow, year_executor,
│   │                              #   state_manager, event_generation_executor,
│   │                              #   hooks, data_cleanup, seed_writer)
│   ├── generators/                # EventGenerator abstraction + registry
│   ├── pipeline_orchestrator.py   # Main coordinator
│   ├── config.py                  # SimulationConfig management (+ get_database_path)
│   ├── dbt_runner.py              # Streaming dbt execution with retry/backoff
│   ├── validation.py              # Rule-based data quality validation
│   └── exceptions.py              # Context-rich error handling + error_catalog.py
├── planalign_cli/                 # `planalign` CLI (Rich + Typer)
├── planalign_api/                 # FastAPI backend for PlanAlign Studio
│   ├── auth.py                    # Optional shared-token auth (PLANALIGN_API_TOKEN)
│   ├── routers/  services/        # Route handlers and business logic
│   └── websocket/                 # Real-time telemetry
├── planalign_studio/              # React/Vite frontend (Tailwind v4, no CDN)
├── planalign_core/                # Shared domain package (Pydantic v2 event model)
├── dbt/                           # dbt project
│   ├── models/staging/            # 20 stg_* models
│   ├── models/intermediate/       # 61 int_* models (events, accumulators)
│   ├── models/marts/              # 22 fct_*/dim_* models
│   ├── seeds/                     # config_*.csv parameter seeds
│   ├── macros/                    # Reusable SQL (band assignment, etc.)
│   └── simulation.duckdb          # Shared dev database (see warning below)
├── config/                        # simulation_config.yaml + templates
├── scenarios/                     # Batch scenario definitions
├── workspaces/                    # Studio workspaces (per-scenario databases)
├── tests/                         # ~2,200 tests with shared fixture library
├── docs/                          # Architecture, data model, guides
├── var/                           # Runtime outputs (git-ignored)
└── data/                          # Raw census inputs (git-ignored)
```

## Getting Started

### Prerequisites

- **Python 3.11 or 3.12** (3.13+ not yet supported — pydantic-core wheels unavailable)
- **Node.js 18+** (for the PlanAlign Studio frontend)
- Employee census data
- On-premises deployment environment

### Installation

**macOS/Linux (uv, recommended):**

```bash
git clone <repository-url> fidelity_planalign
cd fidelity_planalign

uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

**macOS/Linux (pip):**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

**Windows (PowerShell):**

```powershell
winget install --id Python.Python.3.12 -e   # then restart the terminal
git clone <repository-url> fidelity_planalign
cd fidelity_planalign
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -e ".[dev]"
```

**Then, for all platforms:**

```bash
# dbt packages
cd dbt && dbt deps && cd ..

# Frontend dependencies (required for PlanAlign Studio)
cd planalign_studio && npm install && cd ..
```

### Configuration

1. **dbt profile** — `~/.dbt/profiles.yml` (Windows: `%USERPROFILE%\.dbt\profiles.yml`):

```yaml
planalign_engine:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: /absolute/path/to/fidelity_planalign/dbt/simulation.duckdb
      threads: 1
```

2. **Simulation parameters** — `config/simulation_config.yaml`:

```yaml
start_year: 2025
end_year: 2029
target_growth_rate: 0.03
total_termination_rate: 0.12
new_hire_termination_rate: 0.25
random_seed: 42
```

3. **Verify the installation**:

```bash
planalign --version
planalign health          # system readiness check
planalign validate        # configuration validation
cd dbt && dbt debug       # database connection check
```

## Running the Platform

### CLI (primary interface)

```bash
planalign health                                  # Quick system diagnostic
planalign status --detailed                       # Full system status
planalign simulate 2025-2027                      # Multi-year simulation
planalign simulate 2025 --dry-run                 # Preview execution plan
planalign simulate 2025 --verbose                 # Detailed logging
planalign calibrate 2025-2029 --database iso.duckdb   # Fast comp-only calibration
planalign batch --scenarios baseline high_growth  # Batch scenarios with isolation
planalign batch --export-format excel --clean     # Excel export with metadata
planalign analyze                                 # Results analysis in the terminal
planalign validate                                # Validate configuration
planalign studio                                  # Launch web interface

# Workspace cloud sync (Git-based)
planalign sync init git@github.com:user/planalign-workspaces.git
planalign sync push -m "Added Q4 projections"
planalign sync pull
planalign sync status
```

### PlanAlign Studio (web interface)

```bash
planalign studio                        # API + frontend, opens browser
planalign studio --api-port 8001 --frontend-port 3000
planalign studio --api-only             # API backend only
planalign studio --frontend-only       # Frontend only
planalign studio --no-browser --verbose
```

- **API** (FastAPI): http://localhost:8000 — REST + WebSocket telemetry; docs at `/api/docs`
- **Frontend** (React/Vite): http://localhost:5173 — scenario management, real-time progress, comparison tools, calibration panel

The API binds to `127.0.0.1` by default. For any non-loopback deployment, set `PLANALIGN_API_TOKEN` and explicit CORS origins — see [SECURITY.md](SECURITY.md).

### Fast Compensation Calibration

`planalign calibrate` rebuilds only the compensation/workforce dbt subgraph per year, skipping the entire DC-plan stack. Per-year average compensation and YoY growth are **exact** versus a full simulation (~3–5× faster).

```bash
planalign calibrate 2025-2029 --database iso.duckdb --target-growth 0.035
planalign calibrate 2025-2029 --cola 0.025 --merit 0.04 --database iso.duckdb
planalign calibrate 2025-2029 --interactive --database iso.duckdb
```

The target database must have had one prior full build. With no `--database`, an isolated `dbt/calibration/calibration_*.duckdb` is created — the shared dev DB is never touched.

### dbt Directly (development)

```bash
cd dbt   # always run dbt from the dbt/ directory, always --threads 1

dbt build --threads 1 --fail-fast
dbt run --select tag:foundation --vars '{simulation_year: 2025}' --threads 1
dbt run --select tag:EVENT_GENERATION --vars '{simulation_year: 2025}' --threads 1
dbt test --select tag:data_quality --threads 1
dbt docs generate && dbt docs serve
```

> **⚠️ Shared dev database warning:** `dbt/simulation.duckdb` is the shared dev database. Never validate behavioral changes by running `dbt run`/`dbt build` into it — use an isolated database instead:
>
> ```bash
> # Preferred: isolated per-scenario databases
> planalign batch --scenarios my_edge_case --clean
>
> # Or: one-off isolated run
> DATABASE_PATH=/tmp/run/iso.duckdb \
>   planalign simulate 2025-2027 --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb
>
> # Point tests at the isolated DB (get_database_path() honors DATABASE_PATH)
> DATABASE_PATH=/tmp/run/iso.duckdb pytest tests/test_my_feature.py -v
> ```

## Development

### Testing

The suite contains **~2,200 tests** organized with auto-applied markers and a shared fixture library (`tests/fixtures/`).

```bash
pytest -m fast                          # Fast unit tests — TDD loop
pytest -m "fast and orchestrator"       # Component-scoped
pytest -m integration                   # Integration tests (database, dbt)
pytest -m e2e                           # End-to-end workflow tests
pytest tests/                           # Everything
```

**Fixtures:**

```python
from tests.fixtures import (
    in_memory_db,        # Clean DuckDB, <0.01s setup
    populated_test_db,   # Pre-loaded employees + events
    minimal_config,      # Lightweight config for unit tests
    mock_dbt_runner,     # Successful dbt execution mock
    sample_employees,    # Test employee records
)

@pytest.mark.fast
@pytest.mark.unit
def test_my_feature(in_memory_db, sample_employees):
    ...
```

### Coverage

`pytest-cov` writes Cobertura XML to `coverage.xml`. Stack `--cov` flags to select packages:

```bash
pytest tests/ \
  --cov=planalign_orchestrator \
  --cov=planalign_cli \
  --cov=planalign_api \
  --cov=planalign_core \
  --cov-report=xml \
  --cov-report=term
```

Configuration lives in the `[tool.coverage.*]` sections of `pyproject.toml`.

### Continuous Integration

GitHub Actions workflows (`.github/workflows/`) run linting (ruff, mypy), the Python test suite, dbt compilation checks, and performance/production validation. Before pushing:

```bash
ruff check planalign_orchestrator/ planalign_cli/ planalign_api/ planalign_core/
mypy planalign_orchestrator/ planalign_cli/ planalign_core/ --ignore-missing-imports
pytest -m fast
cd dbt && dbt compile
```

### Contribution Standards

- **Python**: PEP 8, mandatory type hints, functions under ~40 lines, explicit exceptions, Pydantic v2 for config/models, cognitive complexity ≤ 15
- **SQL (dbt)**: 2-space indents, uppercase keywords, CTEs, `{{ ref() }}`, no `SELECT *`; models named `tier_entity_purpose`
- **Event sourcing**: immutable events with UUIDs; `int_*` models never read `fct_*` tables (sanctioned exceptions: `fct_yearly_events` and prior-year `fct_workforce_snapshot`)
- **State management**: temporal accumulators (Year N reads Year N−1 state + Year N events)
- **Testing**: schema + custom tests for every dbt model; pytest coverage for all new Python code

## Key Data Models

| Model | Purpose |
|-------|---------|
| `stg_census_data` | Cleaned employee master data with schema validation |
| `fct_yearly_events` | Immutable event store (UUID, timestamp, provenance keys) |
| `fct_workforce_snapshot` | Point-in-time workforce state as of Dec 31 each year |
| `fct_employer_match_events` | Per-employee annual match calculations |
| `fct_compensation_growth` | YoY comp analysis (current / continuous / incumbent methodologies) |
| `int_enrollment_state_accumulator` | Temporal enrollment state across years |
| `int_deferral_rate_state_accumulator` | Temporal deferral rate state across years |

## Performance Characteristics

- **Scale**: 100K+ employee records without memory errors
- **Runtime**: 5-year simulation in < 5 minutes for 10K employees
- **Memory**: < 8GB RAM peak during simulation
- **Storage**: ~1GB per 50,000 employees per simulation year
- **Stability**: single-threaded dbt execution (`--threads 1`) recommended on work laptops

## Deployment

- **On-premises only** — no cloud data transfer; Studio and API default to loopback binding
- **Production**: on-premises Linux server, persistent DuckDB with backups, systemd/supervisor process management, cron-driven `planalign batch` automation
- **Security posture**: see [SECURITY.md](SECURITY.md) for the API auth boundary, network defaults, data handling, and vulnerability reporting

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | Activate the venv: `source .venv/bin/activate` |
| `Conflicting lock is held` | Close IDE/DBeaver database connections; `planalign health` detects locks |
| Duplicate enrollment events | Use the temporal accumulator models; never create `int_*` → `fct_*` circular reads |
| `Maximum number of tokens exceeded (10000)` on Year 2+ | Auto-fixed on first `import planalign_orchestrator` (installs a sqlparse `.pth` override) |
| Confusing query results from `dbt/simulation.duckdb` | The shared dev DB may be half-built; validate in an isolated database instead |
| Database path confusion | `python -c "from planalign_orchestrator.config import get_database_path; print(get_database_path())"` |

For diagnostics: `planalign health`, `planalign status --detailed`, `planalign validate`, `dbt debug`, and `--verbose` on any command.

## Further Reading

- [METHODOLOGY.md](METHODOLOGY.md) — modeling methodology, assumptions, and limitations
- [SECURITY.md](SECURITY.md) — security policy and deployment hardening
- [CHANGELOG.md](CHANGELOG.md) — version history
- [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) — AI-assistant playbooks
- `docs/` — architecture, data model, development guides
- [dbt Documentation](https://docs.getdbt.com/) · [DuckDB Documentation](https://duckdb.org/docs/)
