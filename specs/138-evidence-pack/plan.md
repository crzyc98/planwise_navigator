# Implementation Plan: Evidence Packs — Cited Driver Decomposition

**Branch**: `138-evidence-pack` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/138-evidence-pack/spec.md`

## Summary

Add a Studio-first, deterministic explanation of why one of the six canonical
headline metrics moved between two years of a resolved scenario result. A
shared evidence-pack domain service will query only the two requested
`fct_workforce_snapshot` partitions through a short-lived read-only DuckDB
connection, apply fixed exact endpoint/cohort decompositions, compute an
always-present residual, and attach re-executable aggregate SQL citations and
run provenance to every figure. The API returns the typed pack and one
canonical self-contained Markdown rendering; Studio displays and downloads it,
while `planalign evidence-pack` uses the same service and renderer for
verification and scripting. No model service, result-store write, sampling,
schema change, or employee-level output is introduced.

## Technical Context

**Language/Version**: Python 3.11; TypeScript 5.8
**Primary Dependencies**: Existing DuckDB 1.0.0, Pydantic 2.7.4, FastAPI, Typer/Rich, React 19, React Router 7, Tailwind CSS 4, and the existing `planalign_ensemble` canonical metric registry; no new dependency
**Storage**: Existing scenario result `simulation.duckdb`, `current_result.json`, archived `run_metadata.json`/`provenance.json`, and append-only in-database `run_metadata`; all access is read-only and no new table or file is persisted in a run archive
**Testing**: pytest 7.4 with synthetic isolated DuckDB fixtures, FastAPI `TestClient`, Typer `CliRunner`, source-level Studio contract tests, TypeScript/Vite production build, and an isolated multi-year simulation fixture
**Target Platform**: Local/on-premises PlanAlign Studio and CLI on supported macOS and Linux workstations
**Project Type**: Shared Python analysis domain with authenticated FastAPI, React Studio, and Typer CLI adapters
**Performance Goals**: Complete a pack against at least 60,000 employee-years within 2 seconds p95; scan only two requested year partitions; show an immediate computing state and never sample
**Constraints**: Aggregate-only output; exact selected-run binding; deterministic fixed-scale arithmetic and ordering; always report residual; suppress unstable shares; short-lived read-only connections; reject missing metrics/years explicitly; lock conflicts return immediately; no writes to `dbt/simulation.duckdb` or any result store
**Scale/Scope**: One resolved scenario run, two (possibly non-adjacent) years, six fixed metrics, 3–4 fixed drivers per metric, and one self-contained Markdown export

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Plan evidence |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | The feature reads the published workforce snapshot and append-only run provenance only. It does not generate, update, delete, or reinterpret immutable events, and citations bind every figure to one resolved run. |
| II. Modular Architecture | PASS | Canonical metric metadata remains with `planalign_ensemble`; decomposition/query/rendering responsibilities live in a focused `planalign_evidence` package; API, Studio, and CLI are thin adapters. No dbt dependency direction changes or circular layer reads are introduced. |
| III. Test-First Development | PASS | Tasks will begin with failing domain tests for every metric and edge condition, followed by API/CLI/UI contracts and an isolated end-to-end test. Fast synthetic DuckDB tests cover most behavior without running dbt. |
| IV. Enterprise Transparency | PASS | Every displayed figure carries exact SQL and result-store identity; packs include run ID/timestamp/seed/fingerprint, trust warnings, explicit undefined reasons, and a residual that is never redistributed. |
| V. Type-Safe Configuration | PASS | Strict Pydantic v2 models validate metric IDs, decimal strings, citations, warnings, and provenance. SQL identifiers come only from a fixed registry; request values are validated and years are integers. No configuration schema changes are needed. |
| VI. Performance & Scalability | PASS | One short-lived read-only connection scans two year partitions and returns aggregate scalars only. No pandas materialization or employee payload crosses the service boundary; the measured target is <2 seconds p95 at 60,000 employee-years. |

**Pre-design gate result**: PASS. No constitutional exception is required.

**Post-Phase-1 re-check**: PASS. The data model contains only aggregate figures
and structural provenance, contracts prohibit result writes and employee-level
outputs, and the quickstart validates behavioral changes only against isolated
temporary databases. No complexity exception is required.

## Project Structure

### Documentation (this feature)

```text
specs/138-evidence-pack/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── evidence-pack-api.yaml
│   ├── evidence-pack-cli.md
│   └── evidence-pack-text.md
└── tasks.md                     # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
planalign_ensemble/
├── models.py                    # MODIFY: public canonical metric identifiers/metadata
└── extract.py                   # MODIFY: reuse public canonical expressions without semantic drift

planalign_evidence/
├── __init__.py                  # NEW: focused public evidence-pack API
├── models.py                    # NEW: strict aggregate-only request/result entities
├── queries.py                   # NEW: allowlisted two-year aggregate citation SQL
├── decompose.py                 # NEW: fixed exact driver formulas and residual/share rules
├── service.py                   # NEW: schema/year validation and read-only pack assembly
└── render.py                    # NEW: deterministic self-contained Markdown renderer

planalign_api/
├── main.py                      # MODIFY: register protected scenario evidence route/run headers
├── models/
│   └── evidence_pack.py         # NEW: API envelope or re-export of shared models
├── routers/
│   ├── __init__.py              # MODIFY: export router
│   └── evidence_pack.py         # NEW: validate request and map domain errors
└── services/
    └── evidence_pack_service.py # NEW: resolve selected result and assemble trust/provenance

planalign_cli/
├── main.py                      # MODIFY: register flat `evidence-pack` command
└── commands/
    └── evidence_pack.py         # NEW: scenario-path resolver/stdout or atomic Markdown output

planalign_studio/
├── App.tsx                      # MODIFY: register evidence-pack view if deep-linking is used
├── services/
│   └── api.ts                   # MODIFY: typed authenticated request and Blob download
└── components/
    ├── SimulationDetail.tsx     # MODIFY: completed-result Evidence Pack action/panel entry
    └── EvidencePackPanel.tsx    # NEW: selectors, warnings, drivers, citations, export

tests/
├── fixtures/
│   └── evidence_pack.py         # NEW: isolated canonical snapshot/provenance fixtures
├── test_evidence_pack_service.py # NEW: all formulas, citations, privacy, no-write behavior
├── api/
│   ├── test_evidence_pack_api.py # NEW: auth/contract/error/run-header behavior
│   └── snapshots/openapi_schema.json # MODIFY: reviewed API contract snapshot
├── unit/
│   ├── test_evidence_pack_studio_contract.py # NEW: dependency-free UI source contract
│   └── cli/test_evidence_pack_command.py      # NEW: parity and exit behavior
├── integration/
│   └── test_evidence_pack.py    # NEW: isolated multi-year cross-surface/citation verification
└── performance/
    └── test_evidence_pack_performance.py # NEW: 60k employee-year interactive budget
```

**Structure Decision**: Keep metric vocabulary in the existing ensemble domain,
because feature 138 explicitly inherits those definitions. Put deterministic
query/decomposition/rendering logic in a small shared `planalign_evidence`
package so neither API nor CLI owns business rules. The API service alone
resolves workspace/scenario current-result and archive trust context; the CLI
resolves the supplied scenario path. Both bind a concrete run before querying
and then call the same read-only builder and renderer. Studio remains a thin
presentation/export client.

## Design Decisions

### Selected-result binding

Studio requests a pack by workspace and scenario. The backend resolves
`current_result.json` once, validates the completed result, records its run ID,
database path, and relative result-store locator, and uses that immutable target
for the entire request. The response contains that run ID, so display and
download are one payload and cannot cross a later pointer update. The CLI takes
the scenario path required by the specification, resolves its current result,
and permits the established legacy `scenario/simulation.duckdb` fallback with
an explicit provenance warning.

### Fixed driver registry

All drivers are fixed and ordered by canonical metric:

| Metric | Drivers |
|---|---|
| Active headcount | New active records; removed active records; retained became active; retained ceased active |
| Total compensation | Entered population compensation; left population compensation; retained compensation and proration |
| Employer match cost | Entered population cost; left population cost; retained compensation exposure; retained effective match payout rate |
| Total employer plan cost | Entered population cost; left population cost; retained compensation exposure; retained effective plan payout rate |
| Participation rate | Retained participation behavior; entered population participation; left population participation; population reweighting |
| Average deferral rate | Retained deferral behavior; entered population deferral; left population deferral; population reweighting |

The cost factor split is the symmetric midpoint/Shapley identity over retained
compensation and realized payout rate. Ratio decompositions use symmetric
numerator/denominator attribution and explicitly report entering/leaving
populations. Details and undefined cases are normative in
[data-model.md](./data-model.md).

### Citation and numeric contract

Each pack contains one deterministic, literalized, aggregate-only SQL query and
each figure cites the query plus its unique result column and run-relative
result-store locator. Re-executing the query reproduces all cited scalars. SQL
may use `employee_id` internally to form cohorts but never selects an employee
identifier or employee-level value. Aggregate inputs are cast to fixed-scale
decimal; API/export numbers use canonical decimal strings; display formatting
does not change cited values.

## Validation Strategy

1. Fast domain tests first: synthetic two-year tables prove each fixed formula,
   non-adjacent spans, exact reconciliation, explicit zero residual, undefined
   denominators, share suppression, missing-column/year errors, deterministic
   ordering, and aggregate-only serialization.
2. Citation/no-write tests: independently re-execute every cited result column;
   compare database size/mtime/table list before and after; simulate a lock and
   assert immediate conflict behavior.
3. Adapter contracts: API auth/status/OpenAPI/run headers; CLI scenario-path
   resolution/exit codes/stdout; assert both canonical text and figures match.
4. Studio validation: source-level UI contract plus `npm run build` because the
   frontend has no test runner.
5. Behavioral validation: run or reuse a full multi-year simulation only in an
   isolated `tmp_path`/`DATABASE_PATH` database, then follow quickstart checks.
6. Performance: measure all six metrics over at least 60,000 employee-years and
   require p95 <= 2 seconds without sampling.

## Complexity Tracking

No constitution violations; table intentionally omitted.
