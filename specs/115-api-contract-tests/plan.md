# Implementation Plan: API Contract Tests for FastAPI Routes and WebSocket Auth

**Branch**: `115-api-contract-tests` | **Date**: 2026-07-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/115-api-contract-tests/spec.md`

## Summary

Add an in-process, fast-tagged contract-test layer over the existing `planalign_api` FastAPI app: (1) a committed OpenAPI schema snapshot diffed on every run to catch unintentional path/response-shape drift, (2) an exhaustive auth-boundary test that iterates `app.routes` (not a hand list) so every current and future HTTP route is proven to require `PLANALIGN_API_TOKEN` when configured, (3) WebSocket auth coverage for `/ws/simulation/{run_id}` and `/ws/batch/{batch_id}`, and (4) startup-config tests for the non-loopback + wildcard-CORS rejection. Investigation found (2)–(4) are *already substantially implemented* in `tests/api/test_api_auth.py` and `planalign_api/config.py`/`auth.py`; the real gap this feature closes is the exhaustive route-iteration guarantee (today only one protected route, `/api/workspaces`, is exercised) and the OpenAPI snapshot layer (does not exist at all).

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, Starlette `TestClient` (httpx-based), Pydantic v2, pytest
**Storage**: N/A (no database involved; tests exercise the FastAPI app in-process)
**Testing**: pytest, existing `tests/api/` package, `fast` marker (`pytest -m fast`, target <10s for the fast suite per constitution)
**Target Platform**: Linux/macOS dev and CI runners (same as rest of test suite)
**Project Type**: Web application (existing `planalign_api` backend + `planalign_studio` frontend); this feature touches backend tests only
**Performance Goals**: New contract test suite completes in <30s (SC-005), in-process only, no live network/server
**Constraints**: No new runtime dependency unless clearly justified (existing stack has no snapshot-testing library — see research.md for the decision to use a plain committed JSON snapshot instead of adding one); must not require a running server or a database
**Scale/Scope**: ~18 registered routers (`planalign_api/main.py`) exposing on the order of 60–80 (path, method) pairs at the time of writing; 2 WebSocket endpoints; scope is the `planalign_api` app only (no `planalign_studio` frontend changes)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Event Sourcing & Immutability** — N/A. This feature adds tests only; it touches no event-sourced tables or simulation state. PASS (not applicable).
- **II. Modular Architecture** — New test modules are added under the existing `tests/api/` package, one file per concern (schema snapshot, route-auth coverage), following the project's existing one-file-per-concern test layout. No production module is touched. PASS.
- **III. Test-First Development** — This entire feature *is* test infrastructure; by construction it is test-first. Tests are tagged `fast` to fit the existing TDD loop. PASS.
- **IV. Enterprise Transparency** — The OpenAPI snapshot diff and route-coverage assertions produce a reviewable, named failure (which path/method), consistent with the transparency principle. PASS.
- **V. Type-Safe Configuration** — Tests validate live responses against existing Pydantic response models (already declared on routers); no new untyped config surface is introduced. PASS.
- **VI. Performance & Scalability** — Tests are in-process, single-threaded, no dbt/DuckDB build involved; well within the <10s fast-suite budget in aggregate with the rest of `-m fast`. PASS.

No violations. Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/115-api-contract-tests/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output (test-contract descriptions, not network contracts)
│   └── route-auth-coverage.md
└── tasks.md              # Phase 2 output (/speckit.tasks command — not created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_api/
├── main.py                          # create_app(); existing, read-only for this feature
├── auth.py                          # require_api_token / require_websocket_api_token; existing, read-only
├── config.py                        # APISettings, validate_network_security; existing, read-only
└── routers/                         # existing routers; read-only for this feature

tests/api/
├── test_api_auth.py                 # EXISTING — single-route auth smoke test, WS auth, CORS startup test (kept as-is)
├── test_openapi_contract.py          # NEW — OpenAPI schema snapshot diff + response-model shape checks
├── test_route_auth_coverage.py       # NEW — exhaustive (path, method) auth-boundary iteration over app.routes
└── snapshots/
    └── openapi_schema.json           # NEW — committed OpenAPI snapshot baseline
```

**Structure Decision**: Existing web-application layout (`planalign_api` backend, `planalign_studio` frontend) is unchanged. This feature is backend-test-only and lives entirely under `tests/api/`, alongside the existing `test_api_auth.py` and `test_provenance_api.py` it builds on. No frontend files are touched. New test files are added rather than folding everything into `test_api_auth.py`, keeping each file under one concern (schema contract vs. route-auth coverage) per the modular-architecture principle.

## Complexity Tracking

*No violations — table omitted.*
