# Implementation Plan: Studio Two-Scenario Diff View

**Branch**: `110-scenario-diff-view` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/110-scenario-diff-view/spec.md`

## Summary

Add a focused, read-only A-vs-B Studio view that pairs annual workforce/DC-plan metrics with the effective configuration differences and run provenance that explain them. Extend the existing comparison response with active-employee average compensation, add a small configuration-diff service and endpoint that reuse `WorkspaceStorage.get_merged_config()` and read `run_metadata` through read-only scenario connections, then render the two typed responses in a new Studio route with entry points from the scenario list and existing two-scenario comparison.

## Technical Context

**Language/Version**: Python >=3.11; TypeScript 5.8; SQL compatible with DuckDB 1.0.0
**Primary Dependencies**: FastAPI, Pydantic v2, DuckDB; React 19, React Router 7, Recharts 3.5, Tailwind CSS 4, Lucide React
**Storage**: Existing workspace `base_config.yaml` and scenario overrides plus existing scenario-isolated DuckDB outputs and append-only `run_metadata`; no new tables or persisted fields
**Testing**: pytest 7.4 with temporary DuckDB fixtures and FastAPI `TestClient`; TypeScript/Vite production build for frontend type and bundle validation
**Target Platform**: PlanAlign Studio on local/on-prem macOS and Linux workstations
**Project Type**: Web application with Python API backend and React frontend
**Performance Goals**: Complete a valid two-scenario diff request within the constitution's <2-second p95 dashboard target for 100K-employee scenario outputs; keep chart interaction responsive across normal 1-20 year simulations
**Constraints**: Strictly read-only scenario access; exactly two completed scenarios from one workspace; missing legacy provenance degrades gracefully; existing comparison clients remain compatible; no client-side metric re-aggregation; no network or new dependencies
**Scale/Scope**: Two scenario databases, up to 20 annual points per metric, five headline metric panels, one effective-config delta list; localized API models/router/service/tests plus one Studio view, route, client types, and two entry points

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Plan evidence |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | The feature reads existing snapshots, events, effective configuration, and append-only provenance. It creates no events and performs no scenario-database writes. |
| II. Modular Architecture | PASS | `ComparisonService` receives only the additive average-compensation metric. Configuration diff and provenance live in a separate focused service so the existing 667-line comparison service does not grow a second responsibility. No dbt dependency direction changes. |
| III. Test-First Development | PASS | Backend model/service/router tests are written first against temporary isolated databases; frontend compilation and focused component behavior are validated before the end-to-end scenario check. |
| IV. Enterprise Transparency | PASS | The design surfaces effective setting changes, actual run timestamps, fingerprints, seeds, and mixed-generation/current-config drift warnings next to outcomes. |
| V. Type-Safe Configuration | PASS | Effective configuration uses the existing validated merge path, API responses are Pydantic models, and frontend payloads use explicit TypeScript types with no `any` in the new contracts. |
| VI. Performance & Scalability | PASS | Each of two databases is opened read-only for bounded aggregate/provenance queries; responses contain annual aggregates rather than employee rows and target <2 seconds p95. |

**Pre-design gate result**: PASS. No constitutional exception is required.

**Post-Phase-1 re-check**: PASS. The contracts introduce no persistence or reverse dependencies, the config-diff service remains separate, and the quickstart requires isolated databases.

## Project Structure

### Documentation (this feature)

```text
specs/110-scenario-diff-view/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── comparison-api.yaml
└── tasks.md             # Phase 2 output (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   ├── comparison.py              # MODIFY: avg compensation + config-diff/provenance response models
│   └── __init__.py                # MODIFY: export new models
├── routers/
│   └── comparison.py              # MODIFY: two-scenario config-diff endpoint and validation
├── services/
│   ├── comparison_service.py      # MODIFY: query/wire avg_compensation only
│   ├── config_diff_service.py     # NEW: effective-config diff + read-only provenance
│   └── database_path_resolver.py  # REUSE: locate isolated scenario DBs
└── storage/
    └── workspace_storage.py       # REUSE unchanged: exact effective-config merge semantics

planalign_studio/
├── App.tsx                        # MODIFY: /analytics/diff route
├── constants.ts                   # MODIFY: shared two-scenario colors if needed
├── services/
│   └── api.ts                     # MODIFY: fully typed comparison/config-diff contracts + client
└── components/
    ├── ScenarioDiff.tsx           # NEW: header, warnings, config delta table, metric panels
    ├── ScenariosPage.tsx          # MODIFY: Diff A vs B action for exactly two completed selections
    └── ScenarioComparison.tsx     # MODIFY: focused-diff link for exactly two scenarios

tests/
├── test_comparison_dc_plan.py     # MODIFY: active-only avg compensation and delta fixture tests
├── test_config_diff_service.py    # NEW: merge, nested/list deltas, exclusions, provenance, no-write tests
└── test_comparison_api.py         # NEW: response contract and 400/404 validation tests
```

**Structure Decision**: Preserve the existing web application split. The mature multi-scenario `ComparisonService` remains the source for metrics and receives one additive field only. A new `ConfigDiffService` owns the distinct configuration/provenance responsibility and reuses storage and database-path abstractions already used by Studio. The frontend adds one focused page without refactoring the existing N-scenario dashboard, which is explicitly out of scope.

## Complexity Tracking

No constitution violations; table intentionally empty.
