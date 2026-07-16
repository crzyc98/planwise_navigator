# Test Contract: Exhaustive Route Auth Coverage

This project exposes no external network contract as part of this feature (it adds tests, not endpoints). This document is the "contract" the new `tests/api/test_route_auth_coverage.py` module must satisfy — i.e., the interface between the test and the live FastAPI app.

## Inputs

- The live `FastAPI` instance from `planalign_api.main.create_app()`, built with a configured `PLANALIGN_API_TOKEN` (via the existing `client_factory` fixture pattern from `test_api_auth.py`).
- `app.routes`, iterated and filtered to `starlette.routing.Route` objects with a non-empty `.methods` set.

## Exemption list (public routes)

A named, reviewed constant in the test module, e.g.:

```python
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("/api/health", "GET"),
})
```

FastAPI's own scaffolding routes (`/api/docs`, `/api/redoc`, `/api/openapi.json`, and their `HEAD` variants) are excluded from enumeration entirely (not just marked public) because they are framework-provided, not application endpoints, and are not registered via `app.include_router(...)`.

Adding a new intentionally-public application route requires a one-line addition to `PUBLIC_ROUTES` in the same PR — this is the "documented, explicit exemption mechanism" required by spec.md's edge cases.

## Assertions (per non-public `(path, method)` entry)

1. **No token** → response status is `401`.
2. **Valid token** (`Authorization: Bearer <token>` or `X-API-Token: <token>`) → response status is **not** `401`. (The test does not assert a specific 2xx/4xx business-logic status, since some routes require path parameters or bodies the test does not fabricate — only that the *auth layer* let the request through, distinguished from a 401 that indicates auth blocked it. Routes needing path parameters use a syntactically-valid placeholder, e.g. a UUID-shaped string, so the app can route the request and reach the auth dependency before any business-logic 404/422.)

## Assertion (auth-disabled mode)

3. With no `PLANALIGN_API_TOKEN` configured, a sample of routes (or the full enumerated set, reusing the same list) returns non-401 with no `Authorization` header at all — covering FR-007.

## Failure output contract

On failure, the test MUST report the specific `(path, method)` that failed and which assertion (missing-401 vs. false-401), so a maintainer can immediately see which new/changed route broke the guarantee — consistent with spec.md's SC-001/SC-002 "reviewable diff" requirement.
