# Implementation Plan: Run-Cost Profile — Orchestration Overhead vs Computation (Go/No-Go for Compiled Execution)

**Branch**: `116-profile-run-cost` | **Date**: 2026-07-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/116-profile-run-cost/spec.md`

## Summary

Measure where multi-year simulation wall time goes — dbt per-invocation orchestration overhead vs DuckDB SQL execution — across three census sizes (150 / 7,505 / ~60K employees), cross-check the overhead estimate two independent ways, run one direct-execution probe on the EVENT_GENERATION stage, and produce a report with a GO/NO-GO recommendation (criteria confirmed in spec FR-007) that gates roadmap issue #456 (compiled execution mode).

Technical approach: a small profiling harness under `scripts/perf_profile/` reuses the Feature 113 pattern — `create_orchestrator(config, db_path=…, threads=1)` with `setup["census_parquet_path"]` pointing at the size variant and `DATABASE_PATH` pointing at an isolated DuckDB per run. Per-invocation timing comes from wrapping `DbtRunner.execute_command` (timing wrapper, read-only) and snapshotting `dbt/target/run_results.json` after each invocation; per-model execute time comes from those snapshots. The probe executes the already-compiled EVENT_GENERATION SQL from `dbt/target/compiled/` directly via the `duckdb` client against a copied mid-run database and diffs results against the standard path.

## Technical Context

**Language/Version**: Python 3.11 (harness scripts); SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 (measured system, unmodified)
**Primary Dependencies**: `planalign_orchestrator` (`create_orchestrator`, `execute_multi_year_simulation`, `DbtRunner`), `duckdb` Python client, pandas/pyarrow (census scaling) — all already installed
**Storage**: isolated per-run DuckDB files under `var/perf_profile/` (git-ignored); timing samples as JSON/CSV next to them; report in `docs/perf/`
**Testing**: harness self-check = FR-003/FR-004 cross-consistency + regeneration idempotence; no product code changes, so no new product tests
**Target Platform**: macOS dev laptop (decision-grade per spec assumption — decision turns on a ratio)
**Project Type**: analysis/measurement scripts + written report (no product surface)
**Performance Goals**: N/A — this feature measures performance, it does not change it
**Constraints**: shared dev DB `dbt/simulation.duckdb` byte-identical before/after (SC-007); simulation behavior unchanged (FR-009); decomposition residue ≤ 10% (FR-003); ≥ 3 repetitions per size (≥ 2 allowed for the large size, labeled)
**Scale/Scope**: 3 census sizes × 3 repetitions × 3-year horizon ≈ 9 full simulation runs plus one probe; large size ~60K employees (8× dev census, aligned with the constitution's 100K capability requirement)

## Constitution Check

*GATE: evaluated pre-Phase-0 and re-checked post-design — PASS (one justified note).*

| Principle | Status | Notes |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | No writes to any event store except inside throwaway isolated DBs; determinism untouched (FR-009). |
| II. Modular Architecture | PASS | Harness = small single-purpose scripts in `scripts/perf_profile/` (each well under 600 lines); zero product-module changes. |
| III. Test-First Development | PASS (justified) | No product code → no product tests. The harness's correctness check is built into the method: two independent overhead estimates must agree (FR-004 cross-check), the probe must reproduce standard-path results, and SC-006 requires regeneration without manual edits. Unit tests for throwaway measurement scripts would not reduce decision risk. |
| IV. Enterprise Transparency | PASS | The entire deliverable is an audit document: every number traces to a committed script + recorded sample (FR-008). |
| V. Type-Safe Configuration | PASS | Harness run-matrix defined as a small Pydantic model (`ProfileConfig`) reusing `SimulationConfig` loading; no raw config dicts beyond the existing `setup["census_parquet_path"]` pattern. |
| VI. Performance & Scalability | PASS | `--threads 1` kept for all measured runs (measuring the default path is the point); large census (~60K) exercises the 100K-class requirement without changing product behavior. |

## Project Structure

### Documentation (this feature)

```text
specs/116-profile-run-cost/
├── plan.md              # This file
├── research.md          # Phase 0 output — unknowns resolved by direct repo inspection
├── data-model.md        # Phase 1 output — timing sample / profile report / decision record
├── quickstart.md        # Phase 1 output — how to run the harness end-to-end
├── contracts/
│   └── timing-data.md   # Phase 1 output — schema for timing JSON + report tables
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
scripts/perf_profile/            # NEW — measurement harness (analysis-only, no product code)
├── __init__.py
├── profile_config.py            # ProfileConfig (Pydantic): sizes, repetitions, horizon, paths
├── make_large_census.py         # Scale data/census_preprocessed.parquet ~8× → ~60K synthetic census
├── run_matrix.py                # Drive 3 sizes × ≥3 reps via create_orchestrator; emit timing samples
├── dbt_timing.py                # DbtRunner timing wrapper + run_results.json snapshot collector
├── probe_direct_execution.py    # EVENT_GENERATION stage via compiled SQL vs standard path + diff
└── build_report.py              # Aggregate samples → docs/perf/run_cost_profile.md tables

docs/perf/
└── run_cost_profile.md          # THE deliverable — breakdown, size curve, probe, GO/NO-GO

var/perf_profile/                # Git-ignored runtime outputs (isolated DBs, raw samples)
├── samples/*.json               # One timing sample per repetition (contract: timing-data.md)
└── db/*.duckdb                  # Throwaway isolated databases

tests/fixtures/invariant_census.csv   # EXISTING — reused as the tiny (150-employee) census
data/census_preprocessed.parquet      # EXISTING — dev census (7,505 employees)
```

**Structure Decision**: Analysis scripts live in the existing `scripts/` convention (alongside `create_census.py`, `generate_invariant_census.py`) in their own `perf_profile/` subpackage; runtime outputs follow the `var/` git-ignored convention; the report lands in `docs/perf/` as the committed deliverable. No product package (`planalign_orchestrator`, `planalign_core`, `dbt/`) is modified.

## Method Design (what gets measured, and how)

### M1 — Run matrix (FR-002, User Story 2)

For each census size (tiny=150, dev=7,505, large≈60K) × ≥3 repetitions (large may drop to 2, labeled):
`create_orchestrator(config, db_path=<fresh isolated .duckdb>, threads=1)` → `execute_multi_year_simulation(2025, 2027)`, with `setup["census_parquet_path"]` pointing at the size variant. First repetition per size labeled `warm=false` and excluded from headline stats (edge case: warm vs cold). Total wall time recorded around the orchestrator call.

### M2 — Overhead/computation decomposition (FR-003)

`dbt_timing.py` wraps `DbtRunner.execute_command` (composition, not modification: the harness constructs the orchestrator, then wraps its runner instance's method) to record, per invocation: command, selector, wall time, and a post-invocation snapshot of `dbt/target/run_results.json` (which dbt overwrites per invocation — snapshotting after each is mandatory). Then:

- **computation** = Σ model `execute` timings across all snapshots
- **overhead** = Σ (invocation wall − Σ that invocation's model execute time)
- **residue** = total run wall − Σ invocation wall (orchestrator Python, state management)

FR-003 requires computation + overhead + residue ≈ total within 10%.

### M3 — Fixed-cost cross-check (FR-004)

Count invocations per year from the M2 log; measure a minimal invocation (`dbt run --select <trivial staging model>` on a built isolated DB, ≥5 reps) as the fixed per-invocation floor. `invocations × floor` must land in the same order as M2's overhead figure; the report states both and their ratio.

### M4 — Direct-execution probe (FR-005, User Story 3)

On a dev-census run paused after Year-1 FOUNDATION (i.e., copy the isolated DB at that point): execute EVENT_GENERATION for year 2025 (a) via the standard path and (b) by running the stage's compiled SQL from `dbt/target/compiled/` in dependency order through the `duckdb` client with vars pre-substituted (compile once with the run's vars first). Equivalence check: row counts per event type in `fct_yearly_events`-feeding tables + spot-check checksums; record both stage wall times. Divergence is reported as a critical finding regardless of timing (edge case in spec).

### M5 — Report + decision (FR-006/007/010, User Story 1)

`build_report.py` renders all tables from `var/perf_profile/samples/*.json` into `docs/perf/run_cost_profile.md`: decision criteria first (verbatim from FR-007), then breakdowns per size, the overhead-share-vs-size curve, cross-check, probe result, projection with assumptions, environment note, and exactly one recommendation evaluated at the large census. Re-running `build_report.py` regenerates tables byte-stably from the same samples (SC-006).

### Guardrails

- `DATABASE_PATH` always set to a `var/perf_profile/db/` path; harness asserts at startup that the resolved DB path is not `dbt/simulation.duckdb`.
- SHA-256 of `dbt/simulation.duckdb` captured before the campaign and re-verified after (SC-007), automated in `run_matrix.py`.
- Harness never edits product code; the `DbtRunner` wrapper is runtime composition inside the harness process only (FR-009).

## Complexity Tracking

No constitution violations. (Principle III handled via justified note in the Constitution Check table — no product code means no product tests; harness validity is enforced by built-in cross-checks and regeneration idempotence.)
