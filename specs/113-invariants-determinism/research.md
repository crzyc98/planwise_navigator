# Phase 0 Research: Multi-Year Invariant Suite + Determinism Test

All Technical Context unknowns resolved. Decisions below were verified against the repository (paths and behaviors inspected on branch `113-invariants-determinism`).

## R1. How to drive a full multi-year simulation from a test

**Decision**: Use the programmatic entry point — `load_simulation_config(<fixture yaml>)` → `create_orchestrator(config)` → `execute_multi_year_simulation(start_year=2025, end_year=2027)` — inside a session-scoped pytest fixture, with `DATABASE_PATH` set to a per-session tmp file.

**Rationale**: This is the documented programmatic path (dbt/CLAUDE.md "Multi-Year Simulation"); `dbt/profiles.yml`, `get_database_path()`, and the existing integration fixtures all honor `DATABASE_PATH`, giving isolation for free. A session-scoped fixture runs the (expensive) simulation once, and all invariant tests read it — keeping runtime inside SC-002.

**Alternatives considered**: (a) Shelling out to `planalign simulate` — heavier, harder to capture failures as Python exceptions, and FR-014 needs to distinguish simulation failure from invariant violation, which is natural with an in-process exception. (b) `planalign batch` — designed for scenario sets, adds directory/Excel machinery the suite doesn't need.

## R2. Reference census: format and delivery

**Decision**: Check in `tests/fixtures/invariant_census.csv` (~150 employees, deterministic content), generated once by a kept-for-provenance script (`scripts/generate_invariant_census.py`, fixed numpy seed). A session fixture converts CSV → parquet in the tmp dir (pandas/pyarrow, already dependencies) and passes `census_parquet_path` as a dbt var, exactly how `stg_census_data.sql` ingests census data (`read_parquet('{{ var("census_parquet_path") }}')`).

**Rationale**: The pipeline requires parquet (`config/simulation_config.yaml: census_parquet_path`), but committed parquet is binary and unreviewable; CSV is diffable and stable. The existing generators (`scripts/generate_fresh_census.py`) produce 5,000–7,500 employees and use a CSPRNG for some fields — unsuitable for a stable checked-in fixture, hence a dedicated small deterministic generator. Column set must match the `stg_census_data.sql` schema scaffold (employee_id, ssn, birth/hire/termination dates, gross/capped compensation, active, deferral rate, contribution columns, eligibility_entry_date, scheduled_hours_per_week, auto_escalation_opt_out, eligibility_override, …) — validated by the existing `tests/test_census_schema.py` conventions.

**Census design constraints** (from FR-001): every configured age band (0-25…65+) and tenure band (0-2…20+) populated; all job levels present; a mix of enrolled-at-census (with deferral rates) and never-enrolled employees; a few pre-hire-cutoff and post-cutoff hires so auto-enrollment scoping is exercised; at least one terminated-in-census employee.

**Alternatives considered**: committed parquet (binary, no review); runtime generation inside the fixture without a checked-in file (results drift when the generator changes — violates FR-001's stability requirement).

## R3. Fixed representative configuration

**Decision**: `tests/fixtures/invariant_config.yaml`, derived from `config/simulation_config.yaml` with: 3-year horizon 2025–2027; pinned `random_seed`; auto-enrollment **on** (with a hire-date cutoff that splits the census); auto-escalation **on** with a low cap (so the cap binds during the horizon — FR-008 needs the cap exercised); a multi-tier match; positive `target_growth_rate` (so hiring + terminations both occur — FR-007). Loaded through the normal Pydantic config path.

**Rationale**: One config that makes every invariant family non-vacuous. Broader config coverage is explicitly deferred to the edge-config matrix (#438) per the spec's Assumptions.

**Alternatives considered**: reusing `config/simulation_config.yaml` directly — rejected: it can drift for unrelated reasons and its horizon/levers aren't chosen to make the invariants bite (e.g., a high escalation cap would leave FR-008's cap clause untested).

## R4. Invariant implementation shape

**Decision**: A small registry in `tests/invariants/catalog.py`: each invariant is a dataclass `(name, description, guarded_issue, violation_sql)` where `violation_sql` returns *violating rows* (empty result = pass). A parametrized pytest test executes each against the built DB and, on failure, renders the invariant name, guarded issue, and up to 20 violating rows (FR-011 diagnostics). Empty event sets pass vacuously by construction (edge case: zero promotions in a year).

**Rationale**: SQL-native checks match the engine (the state lives in DuckDB); a registry makes each failure individually reported (not one mega-test), keeps modules tiny (Constitution II), and lets future features (#438, #441) reuse the catalog. Prior art in-repo: `tests/conservation_employee_state_by_year.sql` and `tests/test_deterministic_behavior.sql` show SQL-check precedent; this feature supersedes them with an executed, CI-enforced form.

**Alternatives considered**: dbt tests inside the dbt project — rejected: they'd run during the simulation build (wrong phase; FR-014 requires checks only against a *fully built* DB) and can't express the double-run determinism comparison at all.

## R5. Determinism comparison mechanics

**Decision**: Run the identical config+seed twice into `run_a.duckdb` / `run_b.duckdb` (two session fixtures sharing one census parquet). Compare in DuckDB by `ATTACH`ing both files read-only and computing symmetric `EXCEPT` over the non-exempt column projection of `fct_yearly_events` and `fct_workforce_snapshot`; canonical ordering is irrelevant to set-difference, but result sampling orders by (simulation_year, employee_id, event_type/event_sequence) for readable diffs. Row-count equality is asserted first (EXCEPT alone can't catch exact duplicate multiplicity) — count check + set difference together give row-for-row equality given the event-uniqueness invariant.

**Exempt-field starting list** (FR-010, each justified in contracts/):
- `created_at` on `fct_yearly_events` — populated with `CURRENT_TIMESTAMP` at build time (verified at `dbt/models/marts/fct_yearly_events.sql:430`); wall-clock, not simulation state.
- `snapshot_created_at`/equivalent bookkeeping timestamps on `fct_workforce_snapshot` (verify exact column name during implementation).
- The `run_metadata` table (feature 109) is excluded from comparison entirely — it records run timestamps by design.

`event_id` is **not** expected on the exempt list: the mart derives it via `COALESCE(event_id, MD5(scenario|plan|employee|year|type))` and upstream randomness is seeded hash-based (`get_random_value(employee_id, year, random_seed)`), so ids should reproduce. If the double-run reveals a genuinely random id source, that is a product bug to fix (or, at worst, an exemption with written justification per FR-010) — decided by evidence during implementation, not assumed.

**Alternatives considered**: whole-table hash comparison (`md5(string_agg(...))`) — fast but useless diagnostics (FR-011 requires row samples); pandas frame comparison — pulls full tables through Python memory for no benefit over in-engine EXCEPT.

## R6. CI integration

**Decision**: New job `multi-year-invariants` in `.github/workflows/ci.yml` (same setup steps as existing jobs: checkout, Python 3.11, uv, cached deps): runs `pytest -m multi_year_invariants -v`, uploads the tmp `.duckdb` files with `actions/upload-artifact` on failure (`if: failure()`), and is added to the PR-blocking set from day one (spec assumption: no advisory phase). The pytest marker `multi_year_invariants` is registered in `pyproject.toml`; tests are also marked `integration` so existing selection conventions keep working. Fixtures write DBs under `tmp_path_factory` but the fixture copies failure DBs to a stable `var/test-artifacts/` path for the upload step.

**Rationale**: Matches the two existing workflow files' structure (ubuntu-latest, uv, Python 3.11); a separate job gives the suite its own timing budget (SC-002's 15-min CI bound) and its own required-check line, without slowing the fast-test job.

**Alternatives considered**: folding into the existing test job — rejected: mixes a ~10-min simulation into the fast feedback path and makes artifact upload conditions murkier.

## R7. Validating the suite itself (seeded defects)

**Decision**: SC-001/SC-005 are verified during rollout by temporary defect branches: (a) revert the #418 fix commit (`7f42aa24`) — enrollment-preservation invariant must fail; (b) revert the #419 fix (`cf5e57e5`) — continuity/stale-state invariants must fail; (c) inject an unseeded random draw into one event model — determinism must fail naming the table. These are performed once, recorded in the PR description with the failing output, and not kept as permanent tests (permanently maintaining intentionally-broken branches is not worth the upkeep; the invariants themselves are the permanent artifact).

**Rationale**: Proves the red step of test-first development (Constitution III) for a feature whose deliverable *is* tests.

**Alternatives considered**: permanent mutation-testing harness — heavyweight; revisit only if the suite ever passes a real regression through.
