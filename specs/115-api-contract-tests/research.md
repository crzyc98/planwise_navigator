# Phase 0 Research: API Contract Tests

No `[NEEDS CLARIFICATION]` markers remained in the Technical Context after reading the existing codebase, so this phase is a set of design-decision records (not open questions) — captured here so Phase 1 has a rationale trail.

## Decision 1: What already exists vs. what is actually new

**Decision**: Treat this feature as *closing a specific gap*, not building the whole contract-test layer from scratch.

**Rationale**: `tests/api/test_api_auth.py` already exists and covers, with a real `TestClient(create_app())` against the full app:
- HTTP auth-required/allowed round-trip, but only for **one** route (`/api/workspaces`) — `test_protected_router_requires_configured_bearer_token`.
- The "no token configured → open" mode — `test_protected_router_allows_requests_without_configured_token`.
- WebSocket auth reject (1008) / accept / wrong-token / no-token-configured for both `/ws/simulation/{run_id}` and `/ws/batch/{batch_id}` — fully parametrized already (Story 3 requirements FR-008/FR-009 are already satisfied).
- Startup rejection of non-loopback + wildcard CORS, and the security-warning log for non-loopback + no-token — via `planalign_api/config.py::APISettings.validate_network_security` (Story 4 / FR-010, FR-011 already satisfied; FR-011's "explicit allow-list succeeds" and "loopback + wildcard succeeds" cases are implicitly proven by the absence of a raised error in the existing tests, but are not asserted as explicit positive-path tests).
- No OpenAPI schema snapshot test exists anywhere in `tests/`.
- No route enumerated further than the single `/api/workspaces` case — i.e., FR-004/FR-005/FR-006 (exhaustive route-table auth coverage) are **not** implemented.

**Alternatives considered**: Rewrite `test_api_auth.py` wholesale. Rejected — the file's existing tests are correct, already fast, and already prove the WS/CORS stories; duplicating them would violate "match existing patterns" and add churn with no new coverage. Instead, extend the same `client_factory` fixture pattern into two new files for the two genuinely missing concerns.

## Decision 2: How to make the auth-boundary test exhaustive without hand-listing routes

**Decision**: Introspect `app.routes` at test time, filtering to `starlette.routing.Route` instances with a `methods` set (HTTP routes), excluding the built-in doc routes (`/api/docs`, `/api/redoc`, `/api/openapi.json`) and `/api/health` via an explicit, named "public routes" allow-list constant colocated with the test.

**Rationale**: This is exactly the mechanism the issue calls for ("iterate `app.routes` rather than hand-listing endpoints") and is what prevents the #397/#415 failure mode — a new router added later is automatically covered because the test discovers it, not because someone remembered to add a case. `/api/health` is the one endpoint the codebase itself deliberately leaves open (see `main.py` comment: "the system router keeps `/health` public"); the FastAPI-generated doc routes are framework scaffolding, not application data, and are excluded for the same reason `/api/health` is — they carry no business data and are conventionally public.

**Alternatives considered**:
- *Hand-maintained list of protected paths*: rejected — this is precisely the anti-pattern the issue is trying to eliminate.
- *Assert every route requires auth with no exemption list*: rejected — would either force auth onto `/health` (breaking existing, intentional behavior and load-balancer health checks) or force the test to special-case it inline without a named, reviewable exemption (the spec's edge case explicitly calls for a "documented, explicit exemption mechanism").
- *Derive exemptions from a per-route marker/tag instead of a path allow-list*: considered stronger (self-documenting at the route definition) but rejected as a larger change — it would require modifying `main.py`/routers themselves, which the constitution's modular architecture and this feature's read-only-production-code scope discourage. A named constant in the test file is documented in this plan/spec, is trivially reviewable in the same PR that would add a new public route, and requires no production code changes.

## Decision 3: How to snapshot the OpenAPI schema without a new dependency

**Decision**: Commit `app.openapi()`'s JSON output as `tests/api/snapshots/openapi_schema.json` and diff it in a test using a plain `assert actual == json.load(baseline)` with a helper that renders an unwehat-changed/added/removed path-and-method summary on failure. No snapshot-testing library (e.g., syrupy) is added.

**Rationale**: `pyproject.toml` has no snapshot-testing dependency today, and the project's own guidance favors the simplest solution and matching existing patterns — the existing test suite has no precedent for pulling in a snapshot framework. `app.openapi()` already returns a plain dict (FastAPI's cached OpenAPI schema builder); serializing it to committed JSON and comparing is a ~20-line helper, not a new subsystem. An update path is a single regenerate-and-commit script/test-mode flag (see quickstart.md) rather than a new dependency's CLI.

**Alternatives considered**:
- *Add `syrupy`*: rejected — a new dev-dependency for one feature, when a committed JSON file plus a diff helper does the same job with zero new package-management surface.
- *Only compare route paths/methods, not full response models*: rejected — this would satisfy FR-004-style enumeration but not FR-001's "response model changed" requirement; the issue explicitly calls out snapshotting `openapi.json` for this reason.

## Decision 4: How to validate live responses against declared Pydantic response models

**Decision**: For a representative slice of GET endpoints per router (not every endpoint — most POST/DELETE endpoints require request bodies, workspace state, or background jobs that are already covered by each router's dedicated test file, e.g. `test_calibration_api.py`), call the endpoint via `TestClient` with the minimum fixture setup already used by that router's existing tests, and assert `ResponseModel.model_validate(response.json())` succeeds.

**Rationale**: FR-003 asks that "live endpoint responses conform to their declared Pydantic response models." Full end-to-end exercising of every endpoint (including ones needing dbt-built databases) is out of scope for a "fast" in-process suite and duplicates what router-specific tests already do. The OpenAPI snapshot (Decision 3) is the primary drift-detector for the full surface; this decision adds a lighter, second, independent check — parsing real JSON through the real Pydantic model — for endpoints cheap enough to call with no state (health, system status, config defaults), which is where a hand-written OpenAPI schema and the actual runtime model are most likely to silently diverge (e.g., a field marked required in the model but not reflected correctly by FastAPI's schema generation for a `Dict[str, Any]` response).

**Alternatives considered**: Exercise every router's every endpoint with full mocked state to assert response-model conformance for 100% of endpoints. Rejected as scope creep — each router already has a dedicated contract test file (`test_calibration_api.py`, `test_comparison_api.py`, `test_provenance_api.py`, etc.) doing exactly this for its own endpoints; duplicating that here would violate "don't add abstractions beyond what the task requires" and inflate the new suite's runtime.

## Decision 5: Where startup/CORS positive-path assertions belong

**Decision**: Add the two missing explicit positive-path assertions (non-loopback + explicit CORS origins → succeeds; loopback + wildcard CORS → succeeds) as small additions to the existing `tests/api/test_api_auth.py`, next to `test_non_loopback_wildcard_cors_is_rejected`, rather than a new file.

**Rationale**: These are one-line extensions of an existing, correctly-scoped test in the same file about the same `APISettings.validate_network_security` behavior — not a new concern that warrants a new module.

**Alternatives considered**: Fold into the new `test_route_auth_coverage.py` file. Rejected — that file's concern is HTTP route auth enumeration, not settings-level startup validation; keeping them separate matches the "one file, one concern" pattern already established by `test_api_auth.py` itself (which already separates HTTP-auth / WS-auth / CORS-startup concerns internally via distinct test functions).
