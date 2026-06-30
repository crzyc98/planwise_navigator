# Implementation Plan: Optimize fct_workforce_snapshot Eligibility Branch

**Branch**: `104-snapshot-eligibility-perf` | **Date**: 2026-06-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/104-snapshot-eligibility-perf/spec.md` (GitHub issue [#365](https://github.com/crzyc98/planwise_navigator/issues/365))

## Summary

Replace the correlated subquery in the subsequent-years (year 2+) eligibility branch of `dbt/models/marts/fct_workforce_snapshot.sql` with a single-pass window-function formulation, collapsing the model's double read of `fct_yearly_events` in that CTE down to one. The change is strictly behavior-preserving: output must be byte-identical to `main`.

**Decisive finding from Phase 0** (see [research.md](./research.md)): the `events` eligibility CTE filters on `JSON_EXTRACT_STRING(event_details, '$.determination_type') = 'initial'`, but **no model or Python layer in the codebase emits a `determination_type` key** into eligibility `event_details`. The predicate is therefore `NULL = 'initial'` (falsy) for every row, so the CTE returns **zero rows in every configuration** and the downstream `COALESCE(events.*, baseline.*)` always falls through to baseline. This makes the byte-identical guarantee trivially satisfiable (the correlated subquery's result is empty today) **provided the rewrite preserves the `determination_type` predicate verbatim**. The dead-code nature of the whole events-eligibility join is documented and deferred to a separate issue — it is a business-rules decision and is out of scope here.

## Technical Context

**Language/Version**: SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated `.sql`); Python 3.11 orchestrator drives the build
**Primary Dependencies**: DuckDB 1.0.0 engine; `fct_yearly_events` (incremental, on-disk); `int_baseline_workforce`, `int_enrollment_state_accumulator`, `int_active_employees_prev_year_snapshot` (referenced, unchanged)
**Storage**: DuckDB; the single mutated artifact is `dbt/models/marts/fct_workforce_snapshot.sql` → table `fct_workforce_snapshot`
**Testing**: baseline-vs-rewrite snapshot diff across a multi-year `planalign simulate` run in isolated DBs; existing dbt schema tests on `fct_workforce_snapshot`; `pytest -m fast`
**Target Platform**: macOS dev / Ubuntu analytics server; single-threaded dbt (`--threads 1`)
**Project Type**: dbt analytical model (internal transformation; no external API surface)
**Performance Goals**: no wall-clock regression on the `fct_workforce_snapshot` stage; collapse 2 reads of `fct_yearly_events` in the eligibility CTE to 1; remove the per-employee correlated re-scan
**Constraints**: byte-identical output (FR-002/SC-001); change confined to the year-2+ eligibility branch (FR-004); validate in isolated DB, never the shared dev DB (FR-008)
**Scale/Scope**: ~8k–11k events/year, multi-year (2025–2027+); single model file, one CTE rewrite (~20 lines)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | Read-only against `fct_yearly_events`; no event mutation; reproducibility preserved (same seed → byte-identical output). |
| II. Modular Architecture | ✅ Pass | Single model, single CTE; layering respected — `fct_workforce_snapshot` is a mart reading `fct_yearly_events` (sanctioned exception), no new cross-layer dependency. |
| III. Test-First Development | ✅ Pass | Validation harness (baseline snapshot capture) is authored before the rewrite; the diff is the red/green gate. dbt schema tests must stay green. |
| IV. Enterprise Transparency | ✅ Pass | Dead-predicate finding documented in research.md and deferred to a tracked follow-up issue rather than silently changed. |
| V. Type-Safe Configuration | ✅ Pass | No config change; uses `{{ ref() }}` (no raw string table refs); no Pydantic surface touched. |
| VI. Performance & Scalability | ✅ Pass | Single-threaded default unchanged; goal is fewer scans, no regression; no new memory pressure (window over a year-filtered eligibility set). |

**dbt workflow gates**: ✅ run from `/dbt`, `--threads 1`; ✅ heavy-model year filtering preserved; ✅ no new circular dependency (mart→`fct_yearly_events` is the sanctioned exception). **No violations — Complexity Tracking not required.**

## Project Structure

### Documentation (this feature)

```text
specs/104-snapshot-eligibility-perf/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 — decorrelation approach + dead-predicate finding
├── data-model.md        # Phase 1 — eligibility resolution semantics & columns
├── quickstart.md        # Phase 1 — baseline-vs-rewrite validation harness
├── contracts/
│   └── fct_workforce_snapshot.contract.md  # Output contract (columns + invariants)
└── checklists/
    └── requirements.md  # Spec quality checklist (complete)
```

### Source Code (repository root)

```text
dbt/
└── models/
    └── marts/
        └── fct_workforce_snapshot.sql   # ONLY file changed — CTE `employee_eligibility`,
                                         # subsequent-years branch, lines ~457–476

dbt/models/intermediate/events/int_eligibility_events.sql   # READ-ONLY (confirms no determination_type emitted)
```

**Structure Decision**: Single-file dbt model change. No Python, no config, no seed, no schema, no downstream-model changes. The only edit is the `events` subquery inside the `employee_eligibility` CTE's `{% else %}` (subsequent-years) branch.

## Phase 0 — Research

See [research.md](./research.md). Resolves: (1) the faithful decorrelation technique preserving the exact `MAX(simulation_year)`-over-all-eligibility-events semantics; (2) the `determination_type` dead-predicate discovery and why it makes the rewrite safe; (3) why issue #365's "use `current_year_events`" suggestion does **not** apply to the L466 read (cross-year by design) and why the year-1 L412 read is out of scope.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md): the eligibility-resolution semantics, the columns produced by the `events` subquery, and the precedence (`events` → `baseline`) that must be preserved.
- [contracts/fct_workforce_snapshot.contract.md](./contracts/fct_workforce_snapshot.contract.md): the model output contract — column set unchanged, row grain unchanged, zero-diff invariant.
- [quickstart.md](./quickstart.md): the isolated-DB baseline-vs-rewrite validation harness (capture on `main`, rewrite, re-run, diff; multi-year; includes an edge config).

## Complexity Tracking

No constitution violations. Table intentionally omitted.
