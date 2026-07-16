# Tasks: API Contract Tests for FastAPI Routes and WebSocket Auth

**Input**: Design documents from `/specs/115-api-contract-tests/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/route-auth-coverage.md, quickstart.md

**Tests**: This feature's deliverable *is* tests (per plan.md Summary and constitution principle III, this is test infrastructure by construction) — there is no separate "write tests then implement" split. Each user-story phase below writes the actual pytest module(s) for that story directly.

**Organization**: Tasks are grouped by user story (US1–US4, matching spec.md's P1/P1/P2/P3 priorities) to enable independent implementation and verification of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- File paths are exact and relative to repo root

## Path Conventions

Single project, backend-test-only feature. All new/changed files live under `tests/api/` (existing package); no `planalign_api/` production code is touched. Confirmed against plan.md's Project Structure section.

---

## Phase 1: Setup

**Purpose**: Prepare the shared test scaffolding all stories build on

- [X] T001 Create `tests/api/snapshots/` directory (with `.gitkeep` if needed) as the home for the committed OpenAPI baseline referenced by US1

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared fixture extraction that US2 and US4 both need; must land before those phases start

**⚠️ CRITICAL**: US2 and US4 cannot start until T002–T003 are complete. US1 does not depend on this phase and may proceed in parallel.

- [X] T002 Extract the existing `client_factory` fixture out of `tests/api/test_api_auth.py` into a new `tests/api/conftest.py`, preserving its exact behavior (builds `TestClient(create_app())` with per-test `PLANALIGN_API_TOKEN` env var and `APISettings(workspaces_root=tmp_path / "workspaces")`, monkeypatched onto `planalign_api.config.settings`) so it is auto-discovered by every module under `tests/api/` without an explicit import
- [X] T003 Update `tests/api/test_api_auth.py` to remove its local `client_factory` fixture definition (now provided by `tests/api/conftest.py`) and confirm all of its existing tests still pass unchanged

**Checkpoint**: `client_factory` is available to any new test module under `tests/api/` — US2 and US4 can now begin

---

## Phase 3: User Story 1 - Catch breaking API/response-shape changes automatically (Priority: P1) 🎯 MVP

**Goal**: Any unintentional change to a route's path, method, or response shape fails the test suite with a reviewable diff; any new router is automatically included with zero test-code changes.

**Independent Test**: Add/remove a field on any router's Pydantic response model, run `pytest tests/api/test_openapi_contract.py`, and confirm it fails naming the changed path/field; then revert and confirm it passes.

### Implementation for User Story 1

- [X] T004 [P] [US1] Generate the initial committed baseline at `tests/api/snapshots/openapi_schema.json` by running `create_app().openapi()` and serializing it as sorted, indented JSON (per the exact command in `specs/115-api-contract-tests/quickstart.md`)
- [X] T005 [US1] Create `tests/api/test_openapi_contract.py` with `pytestmark = [pytest.mark.fast]` and a test that loads the live `create_app().openapi()` output, deep-compares it to the committed `tests/api/snapshots/openapi_schema.json`, and on mismatch reports the specific added/removed/changed paths and methods (not just "dicts differ") per contracts/route-auth-coverage.md's failure-output expectations and data-model.md's OpenAPI Schema Snapshot entity
- [X] T006 [US1] In the same file, add response-model conformance tests for the cheap, state-free GET endpoints (`/api/health` → `HealthResponse`, `/api/system/status` → `SystemStatus`, `/api/config/defaults` → its declared response model) using `client_factory("shared-secret")`, asserting `ResponseModel.model_validate(response.json())` succeeds per research.md Decision 4
- [X] T007 [US1] Run `pytest tests/api/test_openapi_contract.py -v` and confirm all new tests pass against the freshly generated baseline

**Checkpoint**: User Story 1 is fully functional and independently testable — schema drift and response-model drift are both caught

---

## Phase 4: User Story 2 - Guarantee every route enforces the shared API token (Priority: P1)

**Goal**: Every registered `(path, method)` pair — enumerated from the live route table, not hand-listed — is proven to require the configured API token, and a newly added route is covered automatically.

**Independent Test**: Add a throwaway protected router/endpoint to `planalign_api/main.py`, run `pytest tests/api/test_route_auth_coverage.py` with no test-code changes, confirm it now also covers the new endpoint and passes; then revert the throwaway route (per `specs/115-api-contract-tests/quickstart.md`).

### Implementation for User Story 2

- [X] T008 [US2] Create `tests/api/test_route_auth_coverage.py` with `pytestmark = [pytest.mark.fast]`, a module-level `PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({("/api/health", "GET")})` constant, and a helper that iterates `create_app().routes`, filters to `starlette.routing.Route` instances with a non-empty `.methods`, expands each into `(path, method)` pairs (one per HTTP method on multi-method routes), and excludes FastAPI's own `/api/docs`, `/api/redoc`, `/api/openapi.json` scaffolding routes — per contracts/route-auth-coverage.md
- [X] T009 [US2] In the same file, add a parametrized test (`client_factory("shared-secret")`) asserting every non-`PUBLIC_ROUTES` `(path, method)` entry returns `401` when called with no auth header, substituting a syntactically-valid placeholder (e.g. a UUID-like string) for any path parameters so the route resolves before the auth dependency runs
- [X] T010 [US2] In the same file, add the paired parametrized test asserting every non-`PUBLIC_ROUTES` entry does **not** return `401` when called with a valid `Authorization: Bearer <token>` header, using the same path-parameter substitution as T009
- [X] T011 [US2] In the same file, add a test using `client_factory(None)` (no token configured) asserting the enumerated routes remain reachable (non-`401`) with no auth header at all, covering FR-007's "auth disabled" mode
- [X] T012 [US2] Run `pytest tests/api/test_route_auth_coverage.py -v` and confirm it passes against the current route table, then perform the Independent Test above (add a throwaway route, confirm auto-coverage, revert)

**Checkpoint**: User Stories 1 AND 2 both work independently — schema drift and route-auth coverage are both automated

---

## Phase 5: User Story 3 - Guarantee WebSocket telemetry channels enforce auth (Priority: P2)

**Goal**: Confirm the simulation and batch WebSocket endpoints reject unauthenticated connections and accept authenticated ones, with this behavior under automated test.

**Independent Test**: Run `pytest tests/api/test_api_auth.py -k websocket -v` and confirm reject/accept/wrong-token/no-token-configured are all exercised for both `/ws/simulation/{run_id}` and `/ws/batch/{batch_id}`.

**Note**: Investigation during planning (research.md Decision 1) found this story's three acceptance scenarios are **already fully implemented** in `tests/api/test_api_auth.py` (`test_websocket_requires_configured_token`, `test_websocket_accepts_query_token`, `test_websocket_rejects_wrong_token`, `test_websocket_allows_connections_without_configured_token`, all parametrized over both endpoint paths). This phase is verification, not new implementation.

### Verification for User Story 3

- [X] T013 [US3] Add `pytestmark = [pytest.mark.fast]` to `tests/api/test_api_auth.py` (currently missing — confirmed by grep during planning; without it these tests are not guaranteed to run under `pytest -m fast`, undermining SC-005)
- [X] T014 [US3] Run `pytest tests/api/test_api_auth.py -k websocket -v` and confirm all four existing WebSocket tests pass and map 1:1 onto spec.md's three US3 acceptance scenarios; no new test code needed if so

**Checkpoint**: User Stories 1, 2, AND 3 all independently verified

---

## Phase 6: User Story 4 - Guarantee unsafe network configurations are rejected at startup (Priority: P3)

**Goal**: Confirm the API refuses to start with non-loopback bind + wildcard CORS, and add the two missing explicit positive-path assertions (explicit-CORS-succeeds, loopback-wildcard-succeeds) so all three acceptance scenarios in spec.md are directly asserted, not just implied.

**Independent Test**: Run `pytest tests/api/test_api_auth.py -k cors -v` and confirm all three acceptance scenarios (reject, non-loopback+explicit-succeeds, loopback+wildcard-succeeds) are asserted.

**Note**: research.md Decision 1 found the reject case (`test_non_loopback_wildcard_cors_is_rejected`) already exists; T015 fills the two missing positive-path assertions per research.md Decision 5.

### Implementation for User Story 4

- [X] T015 [US4] Add `test_non_loopback_explicit_cors_succeeds` and `test_loopback_wildcard_cors_succeeds` to `tests/api/test_api_auth.py`, each constructing `APISettings` directly (no `pytest.raises`) and asserting construction succeeds — for `(host="0.0.0.0", cors_origins=["https://studio.example.test"])` and `(host="127.0.0.1", cors_origins=["*"])` respectively — completing spec.md US4's three acceptance scenarios
- [X] T016 [US4] Run `pytest tests/api/test_api_auth.py -k cors -v` and confirm all CORS/startup tests (existing + new) pass

**Checkpoint**: All four user stories independently functional and verified

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Confirm the feature meets its cross-cutting success criteria

- [X] T017 Run `pytest -m fast tests/api/test_openapi_contract.py tests/api/test_route_auth_coverage.py tests/api/test_api_auth.py -v --durations=0` and confirm total runtime is under 30 seconds (SC-005) and every test is in-process (no server subprocess, no database)
- [X] T018 Run the full existing `tests/api/` package (`pytest tests/api/ -v`) to confirm no regressions were introduced by the T002/T003 fixture extraction
- [X] T019 Walk through `specs/115-api-contract-tests/quickstart.md` end-to-end (snapshot regeneration command, new-public-route addition, new-router auto-coverage check) and confirm every step works as written

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001 is independent of T002/T003 but both are quick) — **blocks US2 (Phase 4) and US4 (Phase 6)**, since both touch/rely on `tests/api/conftest.py` and the refactored `test_api_auth.py`
- **US1 (Phase 3)**: Depends only on Setup (T001 for the snapshots directory) — does **not** depend on Foundational, can run fully in parallel with Phase 2
- **US2 (Phase 4)**: Depends on Foundational (T002/T003)
- **US3 (Phase 5)**: Depends on Foundational (T003, since T013 tags the same file T003 modifies) — otherwise independent of US1/US2
- **US4 (Phase 6)**: Depends on Foundational (T002/T003, edits the same file)
- **Polish (Phase 7)**: Depends on all four user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories — fully independent (only needs Phase 1)
- **US2 (P1)**: No dependency on US1/US3/US4's content, only on the Foundational fixture refactor
- **US3 (P2)**: No dependency on US1/US2/US4's content, only on the Foundational refactor (shares a file)
- **US4 (P3)**: No dependency on US1/US2/US3's content, only on the Foundational refactor (shares a file)

### Within Each User Story

- US1: baseline generation (T004) before the diff test that reads it (T005); response-model checks (T006) can follow in the same file; verification run (T007) last
- US2: enumeration helper (T008) before both parametrized auth tests (T009, T010) before the no-token-configured test (T011); verification (T012) last
- US3: marker fix (T013) before verification run (T014)
- US4: new tests (T015) before verification run (T016)

### Parallel Opportunities

- T001 (Setup) and T002–T003 (Foundational) can run in parallel with each other, and with the T004 snapshot generation for US1, since US1 doesn't depend on Foundational
- Once Foundational (Phase 2) completes, US2, US3, and US4 can all proceed in parallel (different concerns, though US3/US4 both touch `test_api_auth.py` — sequence T013 before T015, or coordinate if worked by different people, to avoid an edit conflict on the same file)
- Within US1: T004 and the eventual T005 are sequential (T005 reads T004's output); T006 can be written in parallel with T005 since they're independent test functions in the same new file, but both must exist before T007

---

## Parallel Example: Phase 1–3 kickoff

```bash
# These can be dispatched together at the start of implementation:
Task: "Create tests/api/snapshots/ directory (T001)"
Task: "Extract client_factory fixture into tests/api/conftest.py (T002)"
Task: "Generate initial tests/api/snapshots/openapi_schema.json baseline (T004)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 3: User Story 1 (T004–T007) — this alone delivers the OpenAPI schema-drift safety net, the single highest-value, previously-nonexistent protection called out in the issue
3. **STOP and VALIDATE**: Break a response model on purpose, confirm `test_openapi_contract.py` fails with a useful diff, then revert
4. This is a viable, demoable increment even before US2–US4 land

### Incremental Delivery

1. Setup (T001) → US1 (T004–T007) → demo the schema-drift catch (MVP)
2. Foundational (T002–T003) → US2 (T008–T012) → demo the auto-coverage-on-new-router behavior
3. US3 (T013–T014) → confirm/verify existing WebSocket auth guarantee, now correctly tagged `fast`
4. US4 (T015–T016) → confirm/verify existing CORS/startup guarantee, now with explicit positive-path coverage
5. Polish (T017–T019) → confirm SC-005 timing and no regressions

### Parallel Team Strategy

With two people: one takes US1 (independent of everything) while the other does Foundational then US2; a third person (or either, sequentially) does US3+US4 last since both touch `test_api_auth.py` and benefit from Foundational landing first.

---

## Notes

- No production code (`planalign_api/*`) is modified anywhere in this task list — confirmed against plan.md's Constitution Check (all PASS) and Project Structure (backend read-only)
- [P] is used sparingly here because most tasks within a phase share one target file and are inherently sequential; the meaningful parallelism is *across* Phase 3 (US1) vs. Phase 2 (Foundational)
- Commit after each checkpoint (end of each phase) rather than each task, since several tasks within a phase touch the same file
