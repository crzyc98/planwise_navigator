# Implementation Plan: Run Provenance Report

**Branch**: `111-run-provenance-report` | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/111-run-provenance-report/spec.md`

## Summary

Add an execution-time, PII-safe provenance manifest to every Studio-archived run, keyed by the same authoritative run ID used by the API, database stamp, telemetry, and archive. Capture software/source state, effective inputs and fingerprints, completed-year event/reconciliation aggregates, and exact validation results while the simulation runs; finalize partial evidence honestly on failure or cancellation. A shared strictly read-only service will resolve one exact run archive, assemble a typed report with field-level unavailable findings, canonicalize and SHA-256 digest the evidence, and render matching JSON and Markdown for a new CLI command and authenticated Studio API endpoint without touching current configuration, files, databases, or run history.

## Technical Context

**Language/Version**: Python >=3.11
**Primary Dependencies**: Existing FastAPI, Pydantic v2, Typer, Rich, DuckDB 1.0.0, PyYAML, and Python standard-library `hashlib`/`json`/`zipfile`/`subprocess`; no new dependency
**Storage**: Existing `workspaces/<workspace>/scenarios/<scenario>/runs/<run_id>/` archives plus one versioned `provenance.json` sidecar created during execution; existing append-only DuckDB `run_metadata` reuses its schema with the authoritative run ID; no public mart or new database table
**Testing**: pytest 7.4 with `tmp_path` archive fixtures, Typer `CliRunner`, FastAPI `TestClient`, isolated DuckDB fixtures, and one full isolated multi-year Studio simulation
**Target Platform**: On-premises/local PlanAlign CLI and Studio API on supported macOS and Linux workstations
**Project Type**: Shared Python reporting service with CLI and authenticated web-service adapters
**Performance Goals**: Generate both representations for a normal retained run in under 2 seconds at p95; remain independent of employee population size by reading bounded aggregate evidence; keep typical two-file output under 5 MB
**Constraints**: Report generation strictly read-only; exact run-ID binding; no current-state fallback; deterministic cross-channel SHA-256; no employee-level PII or physical paths; preserve failed/cancelled/partial evidence; no shared `dbt/simulation.duckdb` validation; no network or new packages
**Scale/Scope**: One selected run; typical 1-20 simulation years, repository-defined event types and validation rules, tens to low hundreds of seed files, and a small retained-run scan (default three runs per scenario)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Plan evidence |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | The feature does not modify workforce events. It captures aggregate counts from `fct_yearly_events` at completed-year boundaries and never updates/deletes events; report reads only terminal run archives. |
| II. Modular Architecture | PASS | Capture, strict archive location, canonicalization, rendering, and transport adapters have separate focused modules. Existing `run_metadata`, pipeline, telemetry, and simulation service receive localized wiring only; no dbt layer dependency changes or circular imports. |
| III. Test-First Development | PASS | Tasks will begin with fast model/digest/disposition/PII tests, then archive/CLI/API contract tests, followed by an isolated full multi-year integration test and failure/cancellation cases. |
| IV. Enterprise Transparency | PASS | The design binds exact execution identity, source/input fingerprints, effective assumptions, aggregate outcomes, validation results, unavailable findings, disposition, and deterministic digest into one artifact. |
| V. Type-Safe Configuration | PASS | The exact merged `SimulationConfig` remains the execution source; Pydantic v2 models validate the manifest and report. Configuration fingerprints reuse `compute_config_fingerprint()` and report-safe redaction is explicit and tested. |
| VI. Performance & Scalability | PASS | Report generation reads bounded JSON aggregates, not employee rows, and performs no simulation/dbt work. Execution-time aggregate queries are grouped by year/type and support the existing 100K+ workforce target; API target remains <2 seconds p95. |

**Pre-design gate result**: PASS. No constitutional exception is required.

**Post-Phase-1 re-check**: PASS. The data model contains aggregate evidence only, contracts prohibit current-state fallback and archive writes, source responsibilities remain separated, and the quickstart validates behavioral changes exclusively in temporary isolated workspaces/databases.

## Project Structure

### Documentation (this feature)

```text
specs/111-run-provenance-report/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   ├── provenance-api.yaml
│   ├── provenance-cli.md
│   └── report-schema.md
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── run_metadata.py                     # MODIFY: accept propagated authoritative run ID
├── validation.py                       # MODIFY: deterministic safe validation disposition/count contract
├── pipeline_orchestrator.py            # MODIFY: execute/capture registered rules in VALIDATION stage
└── pipeline/
    └── telemetry_emitter.py             # MODIFY: emit validation + completed-year reconciliation aggregates

planalign_api/
├── main.py                              # MODIFY: register authenticated global run provenance router
├── models/
│   ├── provenance.py                    # NEW: Pydantic manifest/report/digest/sign-off models
│   └── __init__.py                      # MODIFY: export public provenance models
├── routers/
│   └── provenance.py                    # NEW: GET JSON envelope or two-file ZIP by run ID
└── services/
    ├── simulation/
    │   ├── service.py                   # MODIFY: create/finalize recorder; propagate run context
    │   ├── run_archiver.py              # MODIFY: preserve authoritative metadata and artifact binding
    │   └── output_parser.py             # REUSE: pass structured records without employee payloads
    └── provenance/
        ├── __init__.py                  # NEW: focused public service exports
        ├── capture.py                   # NEW: input/source fingerprints + atomic manifest recorder
        ├── locator.py                   # NEW: strict read-only global run resolver/consistent-view checks
        ├── report.py                    # NEW: manifest/legacy evidence assembly + disposition
        └── render.py                    # NEW: canonical payload, SHA-256, JSON + Markdown renderers

planalign_cli/
├── main.py                              # MODIFY: register flat `provenance` command
└── commands/
    └── provenance.py                    # NEW: read-only archive report adapter/output handling

tests/
├── fixtures/
│   └── run_provenance.py                # NEW: complete/legacy/failed/partial archive builders
├── unit/
│   ├── test_provenance_models.py        # NEW: schema/disposition/PII rules
│   ├── test_provenance_digest.py        # NEW: canonicalization/tamper/sign-off tests
│   ├── test_provenance_capture.py       # NEW: source/input fingerprints + incremental finalization
│   ├── test_provenance_report.py        # NEW: strict lookup, legacy gaps, render parity/no-write
│   └── cli/
│       └── test_provenance_command.py   # NEW: CLI contract and exit behavior
├── api/
│   └── test_provenance_api.py           # NEW: auth, envelope/ZIP/ETag/errors/parity
└── integration/
    └── test_run_provenance_report.py    # NEW: isolated multi-year + failed/cancelled capture
```

**Structure Decision**: Preserve the existing orchestrator/API/CLI split. The orchestrator remains responsible for contemporaneous validation and safe aggregate telemetry; the API simulation service owns the Studio archive lifecycle and execution-time manifest; a small provenance service package owns strict read-only location, report assembly, canonicalization, and rendering; CLI and API are thin adapters over that same service. This avoids growing the already large simulation router/service with a second reporting responsibility and prevents duplicate digest logic.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations; table intentionally empty.
