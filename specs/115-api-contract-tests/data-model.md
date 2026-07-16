# Phase 1 Data Model: API Contract Tests

This feature has no persisted domain data (no DuckDB tables, no event types). The "entities" are test-time constructs used by the new contract-test code. Documented here for traceability back to spec.md's Key Entities section.

## OpenAPI Schema Snapshot

- **Represents**: The committed baseline of `app.openapi()`'s output, checked in at `tests/api/snapshots/openapi_schema.json`.
- **Fields of interest** (from the standard OpenAPI 3.x document `app.openapi()` returns):
  - `paths`: mapping of path → HTTP method → operation (parameters, `responses`, referenced schema)
  - `components.schemas`: the Pydantic-model-derived JSON Schemas referenced by `paths`
- **Validation rule**: A test-time diff between the live `app.openapi()` output and the committed snapshot MUST be empty (deep-equal) for the test to pass.
- **Lifecycle**: Regenerated deliberately (see quickstart.md) as part of the same PR that intentionally changes an endpoint's shape; otherwise static.

## Route Table Entry

- **Represents**: One `(path, http_method)` pair discovered by iterating `app.routes` at test-collection time, restricted to `starlette.routing.Route` instances that expose `methods` (i.e., real HTTP endpoints, not the WebSocket routes or mount points).
- **Fields**:
  - `path: str` — the route's raw path template, e.g. `/api/workspaces/{workspace_id}/scenarios`
  - `method: str` — one of `GET`/`POST`/`PUT`/`PATCH`/`DELETE` (each method on a multi-method route is a distinct entry)
  - `is_public: bool` — derived by membership in the `PUBLIC_ROUTES` exemption constant (see contracts/route-auth-coverage.md), not stored on the route itself
- **Validation rule**: every non-public entry MUST return 401 without a token and MUST NOT return 401 with a valid token, when `PLANALIGN_API_TOKEN` is configured.
- **Lifecycle**: Recomputed fresh on every test run from the live `app` — never cached or committed (unlike the OpenAPI snapshot), which is what gives new routers automatic coverage.

## API Token Configuration State

- **Represents**: Whether `PLANALIGN_API_TOKEN` is set for a given test's `APISettings`/`create_app()` instance, mirroring the existing `client_factory(api_token: str | None)` fixture in `test_api_auth.py`.
- **States**: `configured` (auth enforced) vs. `unconfigured` (auth bypassed, local-dev default) — both states are exercised by both new test files, reusing `client_factory`.

## Bind/CORS Configuration

- **Represents**: The `(host, cors_origins)` pair passed to `APISettings`, evaluated by `validate_network_security` at construction time.
- **States exercised** (existing + new, all in `test_api_auth.py`):
  1. non-loopback host + wildcard CORS → rejected (existing)
  2. non-loopback host + no token → succeeds, logs warning (existing)
  3. non-loopback host + explicit CORS allow-list → succeeds (NEW positive-path assertion)
  4. loopback host + wildcard CORS → succeeds (NEW positive-path assertion)
