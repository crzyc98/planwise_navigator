# Tasks: Evidence Packs — Cited Driver Decomposition

**Input**: Design documents from `/specs/138-evidence-pack/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [API contract](contracts/evidence-pack-api.yaml), [CLI contract](contracts/evidence-pack-cli.md), [text contract](contracts/evidence-pack-text.md), [quickstart.md](quickstart.md)

**Tests**: Tests are required by the feature specification and project constitution. Write and observe each failing test before its related implementation. Behavioral validation must use disposable isolated DuckDB files; evidence-pack reads must never modify `dbt/simulation.duckdb` or a scenario result.

**Organization**: Shared canonical-metric, typed-model, fixture, and read-only target work precedes the story phases. User Story 1 delivers the visible cited decomposition, User Story 2 completes the equal-priority honesty/trust gate, User Story 3 adds portable text export, and User Story 4 adds CLI verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]** marks tasks that can proceed in parallel after their shared prerequisites complete because they edit different files.
- **[US#]** maps a task to the corresponding user story in [spec.md](spec.md).
- Every task names the exact file or files it changes or validates.

## Phase 1: Setup and Deterministic Fixtures

**Purpose**: Establish one reusable aggregate-only scenario/run fixture before production code or story tests are added.

- [X] T001 Create deterministic managed-run and legacy-scenario fixture builders with two-year `fct_workforce_snapshot`, canonical active/inactive and entered/left/retained cohorts, all six metric columns, append-only `run_metadata`, archived provenance, and `current_result.json` in `tests/fixtures/evidence_pack.py`.

**Checkpoint**: Tests can create a contained completed result with known endpoint metrics, cohort movements, provenance, and an unchanged-source signature without using the shared development database.

---

## Phase 2: Foundational Canonical and Read-Only Domain Contracts

**Purpose**: Establish the shared metric vocabulary, strict aggregate-only models, and safe result-target validation that every user story consumes.

**⚠️ CRITICAL**: Complete this phase before any user-story implementation.

- [X] T002 Add failing regression tests for the stable six-metric order, labels, required columns, SQL expressions, NULL-on-absence behavior, and existing canonical population semantics in `tests/test_ensemble_extract.py`.
- [X] T003 Promote canonical metric identifiers and metadata to a typed public registry while preserving `CANONICAL_METRICS` compatibility and refactor extraction to consume it in `planalign_ensemble/models.py` and `planalign_ensemble/extract.py`.
- [X] T004 [P] Add failing Pydantic invariant tests for citations, decimal strings, figure status/reason pairs, ordered drivers, always-present residual, provenance, warning order, common result-store binding, reconciliation, and PII/path rejection in `tests/test_evidence_pack_models.py`.
- [X] T005 Implement the strict immutable entities and validators from `data-model.md`, including `EvidenceFigure`, `Citation`, `PopulationEvidence`, `DriverContribution`, `Residual`, `PackProvenance`, `EvidencePack`, and `EvidencePackEnvelope`, in `planalign_evidence/models.py` and export the supported public surface from `planalign_evidence/__init__.py`.
- [X] T006 [P] Add failing target-validation tests for contained run-relative locators, required table/column discovery, available-year discovery, managed and legacy identity, short-lived `read_only=True` connections, and missing-result/schema errors in `tests/test_evidence_pack_target.py`.
- [X] T007 Implement the internal `EvidenceTarget`, typed not-found/unsupported/conflict exceptions, schema/year support probe, source signature helper, and context-managed read-only connection boundary in `planalign_evidence/service.py`.

**Checkpoint**: The project has one canonical metric registry, aggregate-only typed contracts, and a validated read-only result target; no decomposition or delivery surface exists yet.

---

## Phase 3: User Story 1 — See Why a Headline Number Moved (Priority: P1)

**Goal**: A Studio analyst selects any canonical metric and two simulated years and receives an ordered, cited decomposition with absolute contributions, shares, aggregate populations, and an explicit residual.

**Independent Test**: Open a completed scenario in Studio, request employer match cost for adjacent years, verify named contributions plus residual equal total change exactly, and independently re-execute every cited result column; repeat with a non-adjacent span and each remaining canonical metric.

### Tests for User Story 1

> **Write these tests first and confirm they fail before T013–T021.**

- [X] T008 [US1] Add failing service tests for exact active-headcount transitions, compensation entry/exit/retained movement, symmetric retained match/plan-cost factorization, cohort-aware participation/deferral ratios, fixed driver order, adjacent and non-adjacent spans, signed shares, population counts, deterministic repetition, and exact contribution-plus-residual reconciliation in `tests/test_evidence_pack_service.py`.
- [X] T009 [P] [US1] Add failing citation tests that re-execute every `Q1.<result_column>`, reproduce endpoint/change/driver/share/population/residual figures, reject write-capable SQL, and prove no employee identifier or employee-level value is projected in `tests/test_evidence_pack_citations.py`.
- [X] T010 [P] [US1] Add failing deterministic renderer tests for required provenance, movement, driver, residual, population-treatment, and deduplicated Q1 citation sections using canonical decimals and fixed ordering in `tests/test_evidence_pack_render.py`.
- [X] T011 [P] [US1] Add failing authenticated API contract tests for scenario ownership, one-time selected-result binding, all metric/year query parameters, structured envelope fields, canonical text parity, response run headers, and repeated response equality in `tests/api/test_evidence_pack_api.py`.
- [X] T012 [P] [US1] Add failing source-level Studio contract tests for a completed-result Evidence Pack entry, metric/base/target controls, invalid year-pair prevention, computing/error/empty states, driver table, populations, residual, provenance, and collapsible SQL citations in `tests/unit/test_evidence_pack_studio_contract.py`.

### Implementation for User Story 1

- [X] T013 [US1] Implement allowlisted two-year aggregate SQL for all six canonical metrics, FULL OUTER JOIN cohort formation, DECIMAL(38,12) inputs, per-figure result columns, and fixed driver/population registries without projecting employee data in `planalign_evidence/queries.py`.
- [X] T014 [US1] Implement canonical decimal normalization, figure construction, fixed driver ordering, signed share calculation, basic always-present residual calculation, and pack reconciliation from the one-row query result in `planalign_evidence/decompose.py`.
- [X] T015 [US1] Implement pack generation that validates metric/year support, executes one short-lived read-only query, binds every figure to the same exact query/result store, attaches the canonical population note, and verifies the source signature is unchanged in `planalign_evidence/service.py`.
- [X] T016 [US1] Implement the deterministic Markdown renderer and safe deterministic filename from the text contract, including canonical values and per-figure `Q1.<result_column>` mappings, in `planalign_evidence/render.py`.
- [X] T017 [US1] Add the API response model/re-export and selected-result adapter that resolves one workspace/scenario result, binds its run ID and run-relative locator, calls the shared builder/renderer, and never falls back to the project database in `planalign_api/models/evidence_pack.py` and `planalign_api/services/evidence_pack_service.py`.
- [X] T018 [US1] Implement the protected GET endpoint and domain-error mapping, export/register its router, and add its route name to scenario-read consistency headers in `planalign_api/routers/evidence_pack.py`, `planalign_api/routers/__init__.py`, and `planalign_api/main.py`.
- [X] T019 [US1] Add backend-aligned evidence-pack TypeScript interfaces and an authenticated `getScenarioEvidencePack` client with structured API error handling in `planalign_studio/services/api.ts`.
- [X] T020 [US1] Implement metric/year selection, on-demand loading, cancellation-safe state, endpoint/change summary, driver/population table, residual, provenance, and collapsible citations in `planalign_studio/components/EvidencePackPanel.tsx`.
- [X] T021 [US1] Add the Evidence Pack entry/panel for completed results, pass the active workspace/scenario context, and avoid requests for incomplete scenarios in `planalign_studio/components/SimulationDetail.tsx`.
- [X] T022 [US1] Run the US1 tests in `tests/test_evidence_pack_service.py`, `tests/test_evidence_pack_citations.py`, `tests/test_evidence_pack_render.py`, `tests/api/test_evidence_pack_api.py`, and `tests/unit/test_evidence_pack_studio_contract.py`, then run `npm run build` from `planalign_studio/package.json` and correct only US1-scoped failures.

**Checkpoint**: User Story 1 is independently usable in Studio for every canonical metric and year span, with exact cited figures and an explicit residual. It is a functional demo slice, but not releasable until the equal-priority honesty gate in User Story 2 passes.

---

## Phase 4: User Story 2 — Trust the Breakdown and Its Limits (Priority: P1) 🎯 MVP Release Gate

**Goal**: Preserve unexplained movement honestly, explain undefined/unstable cases, and surface exact-run provenance, configuration-generation mismatch, incomplete build, integrity, and active-attempt warnings prominently.

**Independent Test**: Build a fixture with deliberately unattributed movement, zero denominators, a near-zero/sign-flipping change, mixed `run_metadata`, and incomplete provenance; verify the residual is never redistributed, warnings have the required severity/wording, and a fully explained pack still reports residual zero.

### Tests for User Story 2

> **Write these tests first and confirm they fail before T026–T029.**

- [X] T023 [US2] Add failing honesty tests for explicit zero/nonzero residual, fixed-scale reconciliation, undefined retained payout factors, unavailable ratio endpoints, near-zero/sign-flip share suppression, deterministic materiality, residual dominance wording, missing metric columns versus legitimate zero, missing years with available range, and aggregate-only serialization in `tests/test_evidence_pack_honesty.py`.
- [X] T024 [P] [US2] Add failing trust tests for the run-ID-matched full fingerprint/seed/timestamp, current config/seed mismatch, mixed generation, full-reset behavior, incomplete capture/build, provenance integrity findings, legacy warnings, concurrent active attempts, unchanged database size/mtime/tables/rows, and immediate lock conflict in `tests/test_evidence_pack_trust.py`.
- [X] T025 [P] [US2] Extend API tests for prominent warning payloads and deterministic 404/409/422 mappings that name missing metrics/columns, available years, zero denominators, pointer integrity failures, and lock conflicts in `tests/api/test_evidence_pack_api.py`.

### Implementation for User Story 2

- [X] T026 [US2] Implement undefined-driver propagation, same-scale residual without named-driver balancing, share suppression, materiality/dominance classification, stable warning order, and exact reason text in `planalign_evidence/decompose.py` and `planalign_evidence/models.py`.
- [X] T027 [US2] Extract reusable latest-two-row drift/mixed-generation evaluation without changing comparison behavior, and expose a run-ID-aware trust result for evidence packs in `planalign_api/services/run_trust.py`, `planalign_api/services/config_diff_service.py`, and `planalign_api/models/comparison.py`.
- [X] T028 [US2] Combine bound-run metadata, archived provenance findings, direct year/schema completeness checks, legacy/current-attempt context, no-write signature enforcement, and DuckDB lock classification into pack warnings/errors in `planalign_api/services/evidence_pack_service.py`, `planalign_evidence/service.py`, and `planalign_api/routers/evidence_pack.py`.
- [X] T029 [US2] Render provenance and trust warnings before figures, show undefined/suppressed reasons, always show zero residual, and use caution/critical treatments for material and dominant residuals in `planalign_studio/components/EvidencePackPanel.tsx`.
- [X] T030 [US2] Run `tests/test_evidence_pack_honesty.py`, `tests/test_evidence_pack_trust.py`, `tests/api/test_evidence_pack_api.py`, and `tests/test_config_diff_service.py`, confirming all reads leave fixture result stores unchanged and no test writes to `dbt/simulation.duckdb`.

**Checkpoint**: The complete P1 scope is independently verifiable and releasable: packs explain what they can, identify what they cannot, and state whether the bound result is trustworthy.

---

## Phase 5: User Story 3 — Export a Self-Contained Evidence Pack (Priority: P2)

**Goal**: Download the displayed pack as deterministic Markdown that remains understandable and independently auditable outside PlanAlign without exposing an individual or workstation path.

**Independent Test**: Download a displayed pack, open it in a plain text editor, and verify every figure, population, residual, warning, provenance field, exact Q1 SQL, and result-column mapping is present with aggregate-only content.

### Tests for User Story 3

> **Write these tests first and confirm they fail before T033–T035.**

- [X] T031 [US3] Extend renderer tests for every defined/undefined/suppressed figure mapping, warning language/order, full provenance, zero and dominant residuals, one trailing LF, locale/time independence, repeated byte equality, and rejection of employee IDs, SSNs, absolute paths, and employee-level values in `tests/test_evidence_pack_render.py`.
- [X] T032 [P] [US3] Extend Studio source-contract tests for an authenticated Blob-based `.md` download, deterministic server filename, disabled export while loading/no pack, object-URL cleanup, and no `window.open` or client-side pack reconstruction in `tests/unit/test_evidence_pack_studio_contract.py`.

### Implementation for User Story 3

- [X] T033 [US3] Complete the canonical Markdown renderer so it emits every figure/citation mapping and all trust/residual/population context in the normative section order with deterministic UTF-8/LF bytes in `planalign_evidence/render.py`.
- [X] T034 [US3] Add authenticated browser download handling that saves the server-provided `text_export` and filename as `text/markdown;charset=utf-8` with Blob URL cleanup in `planalign_studio/services/api.ts`.
- [X] T035 [US3] Add the Export Evidence Pack action, disabled/loading/error feedback, and download invocation without recalculating or re-fetching the bound pack in `planalign_studio/components/EvidencePackPanel.tsx`.
- [X] T036 [US3] Run `tests/test_evidence_pack_render.py` and `tests/unit/test_evidence_pack_studio_contract.py`, build `planalign_studio/package.json`, and manually inspect one output against `specs/138-evidence-pack/contracts/evidence-pack-text.md` using only synthetic aggregate fixtures.

**Checkpoint**: User Story 3 is independently complete: the Studio download is the same canonical text already returned with the bound structured pack and is meaningful without product access.

---

## Phase 6: User Story 4 — Verify the Same Pack from the CLI (Priority: P3)

**Goal**: Produce the same canonical pack from a supplied scenario path for audit and scripting, with exact Studio parity and actionable nonzero exits for unsupported results.

**Independent Test**: Generate the same metric/year pack through API/Studio-style resolution and `planalign evidence-pack`, diff canonical figures and Markdown bytes, then request an unavailable metric/year and verify the CLI names the missing support and exits nonzero.

### Tests for User Story 4

> **Write these tests first and confirm they fail before T039–T040.**

- [X] T037 [P] [US4] Add failing Typer tests for managed and legacy scenario-path resolution, stdout purity, atomic `--output`, overwrite/`--force`, unsafe archive destination, canonical UUID/path validation, exit codes 1–4, available-year/missing-column diagnostics, lock conflict, and source no-write behavior in `tests/unit/cli/test_evidence_pack_command.py`.
- [X] T038 [P] [US4] Add a failing isolated cross-surface test asserting API envelope figures, API `text_export`, CLI stdout, and CLI file bytes are identical for the same bound scenario/metric/years in `tests/integration/test_evidence_pack.py`.

### Implementation for User Story 4

- [X] T039 [US4] Implement the scenario-path command adapter, managed current-result plus explicit legacy fallback, shared builder/renderer invocation, pure stdout, atomic safe file output, and documented error taxonomy in `planalign_cli/commands/evidence_pack.py`.
- [X] T040 [US4] Register the flat `planalign evidence-pack` command with required metric/base/target options and optional output/force options in `planalign_cli/main.py`.
- [X] T041 [US4] Run `tests/unit/cli/test_evidence_pack_command.py` and `tests/integration/test_evidence_pack.py` against disposable scenario directories and confirm byte parity plus nonzero unsupported-result behavior without modifying any run archive.

**Checkpoint**: All four user stories are complete; Studio remains primary, while CLI is a thin, scriptable adapter over the identical bound-run calculation and renderer.

---

## Phase 7: Polish and Cross-Cutting Validation

**Purpose**: Prove performance, privacy, API governance, isolated behavioral correctness, and repository quality gates across the full metric matrix.

- [X] T042 [P] Add a performance fixture/test with at least 60,000 employee-years, two-year scan verification, all six metrics, no sampling, and p95 <= 2 seconds in `tests/performance/test_evidence_pack_performance.py`.
- [X] T043 [P] Extend the isolated end-to-end test to cover all six metrics, adjacent/non-adjacent spans, citation reproduction, deterministic repeats, incomplete/mixed warnings, full aggregate-only privacy scan, and before/after result signatures in `tests/integration/test_evidence_pack.py`.
- [X] T044 Run the performance test and, only if measurement requires it, optimize bounded query execution/connection lifetime without caching, persistence, or sampling in `planalign_evidence/queries.py` and `planalign_evidence/service.py`.
- [X] T045 Regenerate and review the authenticated evidence-pack endpoint/model contract, then pass OpenAPI and protected-route coverage in `tests/api/snapshots/openapi_schema.json`, `tests/api/test_openapi_contract.py`, and `tests/api/test_route_auth_coverage.py`.
- [X] T046 Execute every command in `specs/138-evidence-pack/quickstart.md`, including targeted fast/API/CLI tests, isolated `DATABASE_PATH` integration, performance, `ruff check`/`mypy` on feature Python modules, and the Studio production build; update only actual commands, fixture names, and verified expected outcomes in `specs/138-evidence-pack/quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately; T001 supplies every later test fixture.
- **Foundational (Phase 2)**: Depends on T001 and blocks all stories. T002/T004/T006 test independent contracts; T003, T005, and T007 implement them in that order where required.
- **US1 (Phase 3)**: Depends on T002–T007. T008–T012 are written first; T013–T021 implement the full visible path; T022 is the story gate.
- **US2 (Phase 4)**: Depends on the US1 pack builder/panel. T023–T025 are written first; T026–T029 complete honesty/trust behavior; T030 is the P1 release gate.
- **US3 (Phase 5)**: Depends on the complete P1 pack and renderer. T031–T032 precede T033–T035; T036 is the export gate.
- **US4 (Phase 6)**: Depends on the shared builder and canonical renderer from US1–US3. T037–T038 precede T039–T040; T041 is the parity gate.
- **Polish (Phase 7)**: Depends on all selected stories. T042–T043 add cross-cutting tests, T044–T045 close measured/API gates, and T046 runs the documented final sequence.

### User Story Dependencies

- **US1 (P1)**: Starts after the foundation and delivers a testable Studio decomposition for all six metrics.
- **US2 (P1)**: Builds on US1’s pack but has an independent synthetic honesty/trust test. US1 and US2 together are the minimum releasable product because the specification forbids deferring the integrity guarantee.
- **US3 (P2)**: Builds on the complete pack/rendering domain and is independently verified by exported-text completeness and privacy.
- **US4 (P3)**: Builds on the shared builder/renderer and is independently verified by cross-surface byte parity and CLI error behavior.

### Dependency Graph

```text
Setup -> Canonical/read-only foundation -> US1 visible decomposition
                                      -> US2 honesty/trust (P1 release gate)
                                      -> US3 self-contained export
                                      -> US4 CLI parity
                                      -> Polish and full validation
```

### Within Each User Story

- Write the story’s failing tests and observe the expected failure before implementation.
- Implement query/model/domain behavior before adapters and UI.
- Keep API/Studio/CLI adapters free of duplicate decomposition or rendering logic.
- Complete the story checkpoint before starting the next priority in a single-developer flow.

### Parallel Opportunities

- In Foundation, T004 and T006 can be authored alongside the canonical-registry test/implementation because they target separate test and domain files.
- In US1, T009–T012 cover citations, rendering, API, and Studio in separate files after T008 defines the core expected figures.
- In US2, T024 and T025 cover trust and API error surfaces independently of the arithmetic edge tests in T023.
- In US3, T031 and T032 cover backend text and frontend download contracts in separate files.
- In US4, T037 and T038 cover CLI behavior and cross-surface integration independently.
- In Polish, T042 and T043 add performance and behavioral/privacy coverage in separate test modules.

## Parallel Execution Examples

### User Story 1

```text
Task: T009 — Re-executable aggregate citation and privacy tests
Task: T010 — Deterministic canonical renderer tests
Task: T011 — Authenticated API contract and run-binding tests
Task: T012 — Studio selector/panel/citation source contract
```

### User Story 2

```text
Task: T024 — Bound-run provenance, drift, incomplete, lock, and no-write tests
Task: T025 — API warning and deterministic error-mapping tests
```

### User Story 3

```text
Task: T031 — Complete portable Markdown/privacy tests
Task: T032 — Authenticated Blob download source contract
```

### User Story 4

```text
Task: T037 — Typer scenario-path/output/error tests
Task: T038 — API/CLI figure and byte-parity integration test
```

## Implementation Strategy

### MVP First: Both P1 Stories

1. Complete deterministic fixtures and the canonical/read-only foundation.
2. Deliver User Story 1 and stop to verify all six decompositions, citations, and Studio interaction.
3. Complete User Story 2 and stop to verify residual honesty, degenerate cases, provenance, and result-trust warnings.
4. Treat the combined US1+US2 checkpoint as the minimum releasable product; a US1-only build is a demo slice, not a client-safe release.

### Incremental Delivery

1. Establish one metric registry, typed aggregate contract, and safe target boundary.
2. Add the cited Studio decomposition for all canonical metrics (US1).
3. Close the integrity/trust gate (US2) and release the P1 product.
4. Add self-contained authenticated Markdown download (US3).
5. Add CLI verification and scripting parity (US4).
6. Close performance, OpenAPI/auth, privacy, isolated integration, lint/type, and quickstart gates.

## Notes

- Preserve canonical feature-133 metric semantics even where analytics/comparison services use different populations.
- Use `employee_id` only inside aggregate cohort SQL; never project or serialize it.
- Never distribute residual or rounding differences into a named driver.
- Never report missing schema support or an undefined denominator as zero.
- Do not add persistence, cache tables, sampling, model-service calls, new dependencies, or result-store writes.
- Keep the selected result bound for the entire API/CLI operation; display and download use one response.
- Run behavioral tests only against `tmp_path`/explicit isolated `DATABASE_PATH` databases.
