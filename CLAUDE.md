# Fidelity PlanAlign Engine – Claude Code Playbook

Production-ready code for workforce simulation and event sourcing. This playbook captures hard-won lessons and essentials for shipping features.

---

## **Quick Start**

```bash
# Environment
uv venv .venv --python python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Primary workflows
planalign health                              # System check
planalign simulate 2025-2027                  # Multi-year simulation
planalign batch --scenarios baseline high_growth  # Batch processing
planalign studio                              # Launch web UI

# dbt (always from /dbt directory, --threads 1)
cd dbt
dbt build --threads 1 --fail-fast
dbt run --select int_baseline_workforce+ --threads 1

# Database queries
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"
```

---

## **Tech Stack**

| Layer | Technology | Why |
|-------|-----------|-----|
| Storage | DuckDB 1.0.0 | Immutable event store; column-store OLAP |
| Transformation | dbt-core 1.8.8 / dbt-duckdb 1.8.1 | Declarative SQL, testable models |
| Orchestration | planalign_orchestrator | Modular pipeline with staged execution |
| CLI | Typer + Rich | Beautiful terminal UI with progress |
| Web | FastAPI + React/Vite + Tailwind | Modern web-based scenario management |
| Config | Pydantic v2 | Type-safe validation |
| Python | 3.11 | LTS, long support window |

---

## **Event Sourcing Architecture**

Every decision is an immutable event with a UUID, timestamp, and validation.

**Core Event Types:**
- HIRE, TERMINATION, PROMOTION, RAISE
- BENEFIT_ENROLLMENT, DC_PLAN_ELIGIBILITY, DC_PLAN_ENROLLMENT
- DC_PLAN_CONTRIBUTION, DC_PLAN_VESTING, FORFEITURE, HCE_STATUS

**Event Creation (Pydantic v2):**
```python
from planalign_core.events import WorkforceEventFactory
from decimal import Decimal
from datetime import date

hire = WorkforceEventFactory.create_hire_event(
    employee_id="EMP_2025_001",
    scenario_id="baseline_2025",
    plan_design_id="standard_401k",
    hire_date=date(2025, 1, 15),
    department="Engineering",
    job_level=3,
    annual_compensation=Decimal("125000.00")
)
```

**New Event Types:** Implement `EventGenerator` in `planalign_orchestrator/generators/`, register via `@EventRegistry.register("name")`. See `generators/sabbatical.py` for a template.

---

## **Pipeline Stages**

Sequential execution per year via `PipelineOrchestrator`:

1. **INITIALIZATION** – Load seeds and staging data
2. **FOUNDATION** – Build baseline workforce and compensation
3. **EVENT_GENERATION** – Generate hire/termination/promotion events
4. **STATE_ACCUMULATION** – Build accumulators and snapshots
5. **VALIDATION** – Run data quality checks
6. **REPORTING** – Generate audit reports

Entry point: `orchestrator.execute_multi_year_simulation(start_year, end_year)`

---

## **Development Standards**

### Code Quality (Hard Rules)

**Cognitive Complexity ≤ 15:**
- Early returns over nesting. No nesting >3 levels.
- Extract helper functions from loops/conditionals.
- Use dict dispatch over elif chains.
- Named booleans for complex conditions.

**Parameters ≤ 13:**
- Group related params into dataclasses/config objects (e.g., `AutoEnrollmentOptions`).

**Exception Handling:**
- Never bare `except:` or empty `except Exception: pass`.
- Catch specific exceptions; log or re-raise intentionally.

**Dead Code:**
- No commented-out code. No empty blocks (`pass` after `yield`).
- Remove unused imports.

**Type Hints:**
- Return types must match all paths. Use `Union[A, B]` or `A | B` for multiple returns.

### SQL (dbt) Standards

- 2-space indents, UPPERCASE keywords, one clause per line.
- No `SELECT *`. Use `{{ ref() }}` and CTEs for readability.
- Filter heavy models by `{{ var('simulation_year') }}`.
- Join on `(scenario_id, plan_design_id, employee_id, simulation_year)`.
- Use `incremental_strategy='delete+insert'` for incremental models.

**Sanctioned Reads:**
- `int_*` models can read `fct_yearly_events` (published during EVENT_GENERATION, available to STATE_ACCUMULATION).
- `int_*` models can read prior-year `fct_workforce_snapshot`.
- Otherwise: no `int_*` → `fct_*` reads (circular dependency).

### Python Standards

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date
from decimal import Decimal

class EmployeeEvent(BaseModel):
    employee_id: str = Field(..., min_length=1)
    event_type: Literal["HIRE", "TERMINATION", "PROMOTION", "RAISE"]
    effective_date: date
    annual_compensation: Decimal
```

- Keep functions ≤40 lines. Raise explicit exceptions.
- Use Pydantic v2 for all data models.
- PEP 8, mandatory type hints.

### Naming Conventions

- **dbt models:** `tier_entity_purpose` (e.g., `fct_workforce_snapshot`, `int_termination_events`)
- **Event tables:** `fct_yearly_events` (immutable), `fct_workforce_snapshot` (point-in-time)
- **Python:** `snake_case`, descriptive (e.g., `run_year_simulation`, `audit_year_results`)
- **Config:** `snake_case` in YAML, hierarchical structure

---

## **Critical Patterns**

### Temporal State Accumulators

**Problem:** Year N depends on Year N-1 state + Year N events. Avoid circular dependencies.

**Pattern:**
```sql
WITH prior_year_state AS (
  SELECT * FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
),
current_year_events AS (
  SELECT * FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT
  COALESCE(e.employee_id, p.employee_id) AS employee_id,
  ...
FROM current_year_events e
FULL OUTER JOIN prior_year_state p ON ...
```

Build order: Accumulator → `int_*` models → `fct_yearly_events` → `fct_workforce_snapshot`

### Validate in Isolated Databases

**Rule:** Never validate behavioral changes in the shared dev DB (`dbt/simulation.duckdb`).

**Why:** Running `dbt run`/`build` overwrites shared state. Edge configs (e.g., `auto_enrollment_scope: all_eligible_employees`) only exercise logic in isolation.

**Correct Approach:**
```bash
# Option 1: Isolated scenario database
planalign batch --scenarios my_edge_case --clean

# Option 2: Explicit config + DATABASE_PATH
cp config/simulation_config.yaml /tmp/run/cfg.yaml  # Edit edge config
DATABASE_PATH=/tmp/run/iso.duckdb \
  planalign simulate 2025-2027 --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb

# Run tests against the isolated DB
DATABASE_PATH=/tmp/run/iso.duckdb pytest tests/test_my_feature.py -v
```

### Batch Scenario Processing

```bash
planalign batch                           # All scenarios in scenarios/ dir
planalign batch --scenarios baseline high_growth --clean  # Specific, fresh start
planalign batch --export-format excel     # Excel exports with metadata

# Output: timestamped directory with:
# - Individual .duckdb per scenario (isolated, never touches shared dev DB)
# - Excel exports (workforce snapshots, metrics, events)
# - Metadata (git SHA, seed, config)
# - Comparison reports
```

### Database Locks

**Problem:** "Conflicting lock is held" on simulation.

**Cause:** Active DB connection in IDE (VS Code, DBeaver, Windsurf).

**Solution:** Close all DB connections before running simulations. `planalign health` detects active locks.

### Config Drift Detection

**What it means:** The target DB was last written under a different config/seed. `run_metadata` table stamps effective-config fingerprint + seed at run start. Mismatches warn (never block).

**Audit:**
```bash
duckdb <db> "SELECT run_timestamp, run_type, substr(config_fingerprint,1,12) AS fp, \
  random_seed, start_year, end_year FROM run_metadata ORDER BY run_timestamp DESC"
```

**Remedy:** Use fresh/isolated DB (per the isolated-DB rule), or clean rerun via `setup.clear_tables: true` + `setup.clear_mode: all`.

### SQLParse Token Limit (Auto-Fixed)

**Problem:** Year 2+ fails with "Maximum number of tokens exceeded (10000)".

**Why:** sqlparse 0.5.4+ DoS protection. `fct_workforce_snapshot.sql` compiles to ~13,668 tokens.

**Solution:** Auto-installed on first import of `planalign_orchestrator`. Just run:
```bash
planalign health
# Or: python -c "import planalign_orchestrator"
```

Verify: `python -c "import sqlparse.engine.grouping; print(f'MAX_GROUPING_TOKENS={sqlparse.engine.grouping.MAX_GROUPING_TOKENS}')"` → should print `50000`.

---

## **Testing**

```bash
# Fast unit tests (TDD)
pytest -m fast

# Component-specific
pytest -m "fast and orchestrator"
pytest -m "fast and events"
pytest -m "fast and config"

# Integration tests
pytest -m integration

# Coverage
pytest --cov=planalign_orchestrator --cov=planalign_cli --cov-report=html
```

**Using Fixtures:**
```python
from pathlib import Path
from planalign_orchestrator import ConstructionSpec, build_orchestrator
from tests.fixtures.database import populated_db
from tests.fixtures.config import minimal_config

def test_hire_event_generation(populated_db, minimal_config):
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=minimal_config,
            database=Path("/tmp/test.duckdb"),
            entry_point="invariant_test",
            validation_mode=True,
        )
    ).orchestrator
    result = orchestrator.execute_year(2025)
    assert result.success
```

---

## **Database Access Pattern**

**Always use `get_database_path()`** — it honors the `DATABASE_PATH` env var:

```python
from planalign_orchestrator.config import get_database_path
import duckdb

conn = duckdb.connect(str(get_database_path()))
result = conn.execute(
    "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?",
    [year]
).fetchall()
conn.close()
```

---

## **Troubleshooting**

### ModuleNotFoundError
**Cause:** Using system packages instead of venv.
**Fix:** Activate venv: `source .venv/bin/activate`

### dbt Errors
**Always run from `/dbt` directory with `--threads 1`:**
```bash
cd dbt
dbt run --select int_baseline_workforce --vars "simulation_year: 2025" --threads 1
```

### Circular Dependencies in Enrollment
**Problem:** Duplicate events or missing dates.
**Solution:** Use `int_enrollment_state_accumulator` with proper temporal tracking (see Critical Patterns).

### Virtual Environment Issues
**Recreate and reinstall:**
```bash
rm -rf .venv
uv venv .venv --python python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
planalign health  # Trigger sqlparse auto-fix
```

---

## **Key Learnings**

1. **Config Dominates Event Counts:** Identical code + census can swing `fct_yearly_events` by 142k on different configs. Don't compare across configs.

2. **One DB Per Scenario:** Every workflow isolates one `.duckdb` per scenario. Prefer warnings over schema migrations for cross-scenario concerns.

3. **Hazard Cache Gotcha:** Cache-currency check queries the global DB, so caches rebuild every year on isolated-DB runs (~22% of wall time).

4. **dbt Invocation Baseline:** Production baseline is 38 dbt commands (not 62). Feature 121 optimized to 30 commands, byte-identical, 9.4% faster.

5. **CI is Green:** No Sonar/Codecov/Docker steps. Coverage gate: 60% ratchet-up-only.

---

## **Versioning**

Current version: **2.4.0** (unreleased; v2.2.0 "Calibration" is last tagged release).

Managed in `_version.py` and `pyproject.toml`. See `/docs/VERSIONING_GUIDE.md` for the full process and `/CHANGELOG.md` for history.

---

## **Resources**

- **Architecture Guides:** `/docs/guides/` (parallel_scenario_fanout.md, parameter_fitting.md, backtesting.md, seed_ensembles.md, net_employer_cost.md)
- **Performance:** `/docs/perf/` (profiling reports, timings)
- **Security:** `SECURITY.md` (API token auth, CORS policy, non-loopback deployments)

## Active Technologies
- Python 3.11; dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated SQL) + DuckDB 1.0.0, Pydantic v2, `planalign_orchestrator` pipeline (633-per-design-formula-families)
- DuckDB event store; `int_employee_match_calculations` (table), `fct_employer_match_events`, (633-per-design-formula-families)
- DuckDB event store; `int_employee_match_calculations`, `int_employer_core_contributions`, `fct_employer_match_events`, `fct_workforce_snapshot` (633-per-design-formula-families)
- Python 3.11; dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated SQL); TypeScript/React for Studio + DuckDB 1.0.0, Pydantic v2, `planalign_orchestrator` pipeline (652-flat-newhire-enrollment-rates)
- DuckDB event store — `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`, `int_enrollment_events`, `int_enrollment_state_accumulator`, `fct_yearly_events`, `fct_workforce_snapshot` (652-flat-newhire-enrollment-rates)

## Recent Changes
- 633-per-design-formula-families: Added Python 3.11; dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated SQL) + DuckDB 1.0.0, Pydantic v2, `planalign_orchestrator` pipeline
