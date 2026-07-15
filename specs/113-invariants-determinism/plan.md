# Implementation Plan: Multi-Year Invariant Suite + Determinism Test

**Branch**: `113-invariants-determinism` | **Date**: 2026-07-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/113-invariants-determinism/spec.md`

## Summary

Add a merge-blocking safety net for cross-year simulation correctness: a pytest-driven suite that runs one real 3-year simulation (via `create_orchestrator(...).execute_multi_year_simulation`) on a small checked-in reference census into an isolated `DATABASE_PATH` DuckDB, then evaluates six named invariant families as read-only SQL checks; plus a determinism check that executes the identical config+seed a second time into a second isolated DB and diffs `fct_yearly_events` and `fct_workforce_snapshot` row-for-row (canonical ordering, documented exempt fields). Both run in one new CI job on every PR, uploading the isolated `.duckdb` files as artifacts on failure. Guards the #418 (census enrollment persistence) and #419 (stale rerun state) regression classes structurally.

## Technical Context

**Language/Version**: Python 3.11 (pytest harness, invariant runner); SQL via DuckDB 1.0.0 (invariant queries, diff queries); simulation itself via dbt-core 1.8.8 / dbt-duckdb 1.8.1 driven by `planalign_orchestrator`
**Primary Dependencies**: `planalign_orchestrator` (`create_orchestrator`, `execute_multi_year_simulation`, `load_simulation_config`), `duckdb` Python client, pytest + existing markers/fixture library (E075), pandas/pyarrow (CSV→parquet census conversion, already dependencies)
**Storage**: Two per-run isolated DuckDB files under pytest `tmp_path_factory` (never `dbt/simulation.duckdb`); reference census checked in as CSV, converted to parquet at session setup and passed via the `census_parquet_path` dbt var
**Testing**: pytest markers `integration` + new `multi_year_invariants`; CI job in `.github/workflows/ci.yml` (ubuntu-latest, uv), `actions/upload-artifact` for failure DBs
**Target Platform**: macOS dev laptops + ubuntu-latest CI (same-machine determinism only, per spec)
**Project Type**: Test infrastructure within existing monorepo (no product-code changes expected; any nondeterminism found is fixed as a product bug under this feature)
**Performance Goals**: Full suite (2 simulations of 3 years on ~150 employees + checks) <10 min locally, <15 min in CI (SC-002)
**Constraints**: Zero reads/writes to shared dev DB (SC-004); `--threads 1` dbt convention; suite must be parallel-safe across concurrent CI runs (per-run tmp dirs)
**Scale/Scope**: ~150-employee census spanning all age/tenure bands and job levels; 3 simulation years (2025–2027); 6 invariant families ≈ 10–14 individual checks; 2 tables diffed for determinism

## Constitution Check

*GATE: evaluated against Constitution v1.0.0 — PASS (pre-Phase-0 and re-checked post-Phase-1).*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | **Directly served**: the determinism check enforces "reproducible given the same seed and configuration" (currently an untested claim); invariants enforce event/state coherence. No events are mutated. |
| II. Modular Architecture | Invariant checks live in a small module set under `tests/invariants/` (catalog + runner + comparisons), each well under 600 lines; no cross-layer reads introduced — checks are read-only SQL against a built DB. |
| III. Test-First Development | The feature *is* tests. Seeded-defect validation (SC-001, SC-005) is the red step: each invariant is proven to fail on its target defect before being trusted green. |
| IV. Enterprise Transparency | FR-011 diagnostics (named invariant, offending employee/year rows) align with the <5-min-diagnosis goal; failure DBs preserved as CI artifacts. |
| V. Type-Safe Configuration | The suite's fixed config is a normal Pydantic-validated `simulation_config.yaml` derivative loaded via `load_simulation_config`; no raw config dicts. |
| VI. Performance & Scalability | Tiny census + `--threads 1`; suite is `integration`-marked so the <10s fast suite is untouched. |

**Development Workflow compliance**: uses `tests/fixtures/` conventions (E075), `DATABASE_PATH` isolation exactly as `dbt/profiles.yml` and existing fixtures honor it, dbt invoked only via the orchestrator (which runs from `/dbt` with `--threads 1`).

No violations → Complexity Tracking table omitted.

## Project Structure

### Documentation (this feature)

```text
specs/113-invariants-determinism/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── invariant-catalog.md   # Named invariants: definition, SQL contract, guarded regression
│   └── ci-interface.md        # CI job, markers, commands, artifact contract
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
tests/
├── fixtures/
│   ├── invariant_census.csv          # NEW: ~150-employee reference census (checked in, reviewable)
│   ├── invariant_config.yaml         # NEW: fixed representative config (AE on, escalation+cap, multi-tier match, seed pinned)
│   └── invariant_simulation.py       # NEW: session-scoped fixtures — CSV→parquet, run sim once (and twice for determinism) into tmp DBs
├── invariants/
│   ├── __init__.py                   # NEW
│   ├── catalog.py                    # NEW: Invariant dataclass + registry (name, SQL, description, guarded issue)
│   ├── queries.py                    # NEW: the invariant SQL (violation-returning queries)
│   └── comparison.py                 # NEW: determinism diff (canonical ordering, exempt-field list, bounded row samples)
└── integration/
    ├── test_multi_year_invariants.py # NEW: one test per invariant family, parametrized from catalog
    └── test_determinism.py           # NEW: double-run comparison tests (events, snapshot)

scripts/
└── generate_invariant_census.py      # NEW: deterministic one-time generator that produced the checked-in CSV (kept for regeneration provenance)

.github/workflows/
└── ci.yml                            # MODIFIED: new `multi-year-invariants` job (PR-blocking, artifact upload on failure)

pyproject.toml                        # MODIFIED: register `multi_year_invariants` pytest marker
```

**Structure Decision**: Extend the existing E075 test layout — fixtures in `tests/fixtures/`, full-simulation tests in `tests/integration/`, with the invariant definitions isolated in a new `tests/invariants/` package so the catalog is reusable (the planned edge-config matrix #438 and ensemble work #441 can import the same checks). No production package is modified unless the determinism check exposes a real nondeterminism bug, which would be fixed in place and covered by this suite.
