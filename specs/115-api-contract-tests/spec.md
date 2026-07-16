# Feature Specification: API Contract Tests for FastAPI Routes and WebSocket Auth

**Feature Branch**: `115-api-contract-tests`
**Created**: 2026-07-16
**Status**: Draft
**Input**: User description: "https://github.com/crzyc98/planwise_navigator/issues/439" — API contract tests for FastAPI routes and WebSocket auth: schema contract tests snapshotting the OpenAPI schema, auth-boundary tests that iterate all routes to assert every route requires the shared API token, WebSocket auth tests for the simulation and batch telemetry sockets rejecting unauthenticated connections, and CORS/startup policy tests rejecting wildcard CORS on non-loopback binds.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catch breaking API/response-shape changes automatically (Priority: P1)

As a maintainer of PlanAlign Studio, when I or a contributor changes a backend endpoint (adds a required field, renames a response key, changes a status code), I want the test suite to fail immediately with a reviewable diff, instead of the frontend silently breaking or a manual endpoint test being the only line of defense.

**Why this priority**: This is the core problem statement in the issue — Studio's API surface has grown organically (workspace config, calibration, comparison, WS telemetry) with only ad-hoc per-endpoint tests, so frontend/backend drift is currently caught by hand. This is the highest-value, most frequently-exercised protection and unblocks safe iteration on every other router.

**Independent Test**: Can be fully tested by adding/removing a field from a router's Pydantic response model, running the fast test suite, and confirming it fails with a diff naming the changed path/field — without needing any other story implemented.

**Acceptance Scenarios**:

1. **Given** the current set of registered API routers, **When** the contract test suite runs, **Then** it captures the full generated OpenAPI schema and compares it against a committed snapshot, failing with a readable diff if paths, methods, or response models changed unexpectedly.
2. **Given** a router's endpoint response is asserted against its declared Pydantic response model, **When** the endpoint is exercised via an in-process test client, **Then** the actual JSON response validates against that model's shape (required fields present, types match).
3. **Given** a new router is added to the FastAPI app after this feature ships, **When** the contract test suite runs, **Then** the new router's routes are automatically included in the OpenAPI snapshot comparison without any test code changes (the snapshot diff surfaces it as a new addition to review).

---

### User Story 2 - Guarantee every route enforces the shared API token (Priority: P1)

As a maintainer, when the shared API token is configured, I want a test to assert that literally every registered HTTP route rejects requests without a valid token — including any route added after this feature ships — so the exact failure mode behind prior incidents (#397/#415) cannot recur silently on a new endpoint.

**Why this priority**: Equal priority to User Story 1 — this is an explicit security regression guard called out in the issue and tied to real prior incidents. Iterating `app.routes` (rather than hand-listing endpoints) is the specific mechanism that makes the guarantee durable as the API grows.

**Independent Test**: Can be fully tested by adding a new router with a new endpoint and confirming the existing auth-boundary test (with no changes to its own code) automatically exercises and enforces the 401-without-token requirement on that new endpoint.

**Acceptance Scenarios**:

1. **Given** `PLANALIGN_API_TOKEN` is configured, **When** any registered HTTP route is called without an `Authorization`/`X-API-Token` header, **Then** the response is `401 Unauthorized`.
2. **Given** `PLANALIGN_API_TOKEN` is configured, **When** any registered HTTP route is called with the correct token, **Then** the request proceeds past the auth check (no 401).
3. **Given** the app's route table is introspected at test time rather than hand-listed, **When** a new router/endpoint is added to the codebase, **Then** the auth-boundary test covers it automatically on the next test run with zero test-code changes.

---

### User Story 3 - Guarantee WebSocket telemetry channels enforce auth (Priority: P2)

As a maintainer, I want the real-time simulation and batch progress WebSocket channels to reject unauthenticated connection attempts and accept authenticated ones, with an automated test guarding this behavior, so the WebSocket-specific fix from #415 cannot silently regress.

**Why this priority**: Narrower in scope than the full-route HTTP auth guard (Story 2) — it covers two specific WebSocket endpoints rather than the whole route table — but it closes a documented prior incident and a different auth code path (query-param token vs. header token) that Story 2's mechanism does not cover.

**Independent Test**: Can be fully tested by attempting to open each WebSocket endpoint without a token (expect close with policy-violation code) and with a valid token (expect the connection to be accepted), independent of the HTTP contract tests.

**Acceptance Scenarios**:

1. **Given** `PLANALIGN_API_TOKEN` is configured, **When** a client opens the simulation-progress WebSocket without a valid token, **Then** the server closes the connection with the policy-violation close code before accepting it.
2. **Given** `PLANALIGN_API_TOKEN` is configured, **When** a client opens the batch-progress WebSocket without a valid token, **Then** the server closes the connection with the policy-violation close code before accepting it.
3. **Given** `PLANALIGN_API_TOKEN` is configured, **When** a client opens either WebSocket with a valid token, **Then** the connection is accepted and the server does not close it for auth reasons.

---

### User Story 4 - Guarantee unsafe network configurations are rejected at startup (Priority: P3)

As a maintainer, I want an automated test confirming the API refuses to start when it is configured to bind to a non-loopback address with wildcard CORS enabled, so a misconfiguration can't silently expose an unauthenticated, cross-origin-open API surface in a non-local deployment.

**Why this priority**: Lowest priority of the four — it's a startup-time configuration guard (per SECURITY.md) rather than a per-request behavior, and misconfiguration of bind address/CORS together is a narrower, less frequently touched scenario than the per-route/per-connection concerns above.

**Independent Test**: Can be fully tested by constructing the app/settings with a non-loopback bind address and wildcard CORS origins and confirming startup raises a configuration error, independent of the other stories.

**Acceptance Scenarios**:

1. **Given** the API is configured to bind to a non-loopback address, **When** CORS origins are also configured as wildcard (`*`), **Then** application startup fails with a clear configuration error and the server does not start.
2. **Given** the API is configured to bind to a non-loopback address, **When** CORS origins are configured as an explicit allow-list (not wildcard), **Then** application startup succeeds.
3. **Given** the API is configured to bind to the loopback address (the default), **When** CORS origins are wildcard, **Then** application startup succeeds (the wildcard restriction only applies to non-loopback binds).

### Edge Cases

- What happens when `PLANALIGN_API_TOKEN` is not set at all (the current local-dev default)? The auth-boundary and WebSocket auth tests must also cover this "auth disabled" mode, asserting routes and sockets remain reachable without a token, so the test suite doesn't force auth to always be on.
- How does the OpenAPI snapshot test handle a legitimate, intentional API change (e.g., a new field added deliberately)? The workflow must make updating the committed snapshot a deliberate, reviewable action (part of the same PR that changes the API), not an automatic pass-through.
- How is a route that legitimately has no auth requirement (e.g., a health check) distinguished from a route that is missing auth by mistake? The route-iteration test needs a documented, explicit exemption mechanism for intentionally public routes, rather than silently skipping failures.
- What happens if a router is registered but exposes zero routes, or a route supports multiple HTTP methods? The route-iteration test must enumerate at the (path, method) level, not just the router/path level, so no method on a multi-method route is missed.
- How does a WebSocket auth test distinguish "connection rejected for auth" from "connection rejected for an unrelated server error"? The test must assert on the specific policy-violation close code, not merely "connection closed."

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The test suite MUST generate the application's full OpenAPI schema and compare it against a committed snapshot, failing with a diff identifying which paths, methods, or response models changed.
- **FR-002**: The test suite MUST provide a documented, explicit process for updating the committed OpenAPI snapshot when an API change is intentional, so legitimate changes are not blocked but are always reviewed as part of the diff.
- **FR-003**: The test suite MUST validate, for each router under test, that live endpoint responses conform to their declared Pydantic response models (required fields present, correct types).
- **FR-004**: The test suite MUST enumerate every registered (path, HTTP method) pair on the running application by introspecting the route table at test time, not by a hand-maintained list of endpoints.
- **FR-005**: The test suite MUST assert that every enumerated (path, method) pair returns `401 Unauthorized` when called without a valid API token, while `PLANALIGN_API_TOKEN` is configured — except for pairs explicitly and visibly marked as intentionally public.
- **FR-006**: The test suite MUST assert that every enumerated (path, method) pair succeeds past the auth check when called with a valid API token, while `PLANALIGN_API_TOKEN` is configured.
- **FR-007**: The test suite MUST assert that, when `PLANALIGN_API_TOKEN` is not configured, routes remain reachable without a token (covering the local-dev "auth disabled" default).
- **FR-008**: The test suite MUST assert that the simulation-progress WebSocket endpoint rejects connections lacking a valid token, closing with the policy-violation close code, and accepts connections presenting a valid token.
- **FR-009**: The test suite MUST assert that the batch-progress WebSocket endpoint rejects connections lacking a valid token, closing with the policy-violation close code, and accepts connections presenting a valid token.
- **FR-010**: The test suite MUST assert that application startup fails with a clear configuration error when the API is configured for a non-loopback bind address together with wildcard CORS origins.
- **FR-011**: The test suite MUST assert that application startup succeeds for a non-loopback bind address when CORS origins are an explicit allow-list, and for a loopback bind address regardless of CORS configuration.
- **FR-012**: All new tests introduced by this feature MUST run in-process (no external server process, no live network calls) and MUST be tagged so they run within the project's existing fast test workflow.

### Key Entities

- **OpenAPI Schema Snapshot**: The committed, versioned representation of the API's generated schema (paths, methods, response models) used as the baseline for detecting unintentional contract drift.
- **Route Table Entry**: A (path, HTTP method, router) tuple introspected from the running application, used to drive exhaustive per-route auth assertions; may carry an explicit "intentionally public" exemption flag.
- **API Token Configuration State**: Whether a shared API token is configured for the running instance; determines expected auth behavior (enforced vs. disabled) across both HTTP and WebSocket tests.
- **Bind/CORS Configuration**: The combination of network bind address (loopback vs. non-loopback) and CORS origin policy (explicit allow-list vs. wildcard) evaluated at startup to determine whether the configuration is safe to run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An unintentional breaking change to any API response shape (added/removed/retyped field, changed path or method) is caught by the test suite before merge, with zero manual endpoint-by-endpoint testing required.
- **SC-002**: 100% of registered HTTP routes are covered by the auth-boundary test at any point in time, including routes added after this feature ships, with no test-code update required to gain coverage of a new route.
- **SC-003**: Both real-time telemetry WebSocket channels are verified to reject unauthenticated connection attempts, closing the exact gap behind the prior incident referenced in the issue.
- **SC-004**: An unsafe non-loopback-bind-plus-wildcard-CORS configuration is caught at startup by an automated test, with zero reliance on a human remembering to check SECURITY.md manually.
- **SC-005**: The full new contract test suite completes in under 30 seconds and runs entirely in-process, so it can be part of the routine fast test loop rather than a separate slow/manual pass.
