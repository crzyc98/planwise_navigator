# Tasks: Run Provenance Report

**Input**: Design documents from `/specs/111-run-provenance-report/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required by the project constitution and plan. Write each test task first, confirm it fails for the intended reason, then implement the paired production task.

**Organization**: Tasks are grouped by user story so each report capability remains independently testable. All database behavior uses `tmp_path` or an explicit isolated `DATABASE_PATH`; never validate against `dbt/simulation.duckdb`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel after its stated phase dependencies are satisfied because it uses different files or is a failing-test task that does not require another incomplete task.
- **[Story]**: Maps the task to US1, US2, or US3 from spec.md.
- Every task names the exact file or files it changes or validates.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the focused service package and reusable isolated archive fixtures without adding dependencies.

- [X] T001 Create the provenance service package and its minimal public export surface in `planalign_api/services/provenance/__init__.py`
- [X] T002 [P] Create reusable complete, legacy, failed, cancelled, partial, malformed, duplicate-ID, and minimal-DuckDB archive builders under `tmp_path` in `tests/fixtures/run_provenance.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the typed execution-evidence capture path shared by all report stories.

**⚠️ CRITICAL**: No user story implementation begins until the authoritative run identity, manifest models, capture lifecycle, validation records, and structured annual evidence are in place.

### Foundational Tests (write first and verify RED)

- [X] T003 [P] Add failing Pydantic model tests for manifest lifecycle, UUID/path identity, safe logical names, sorted unique annual evidence, finite values, redactions, findings, report dispositions, and forbidden extra/PII fields in `tests/unit/test_provenance_models.py`
- [X] T004 Implement strict Pydantic v2 manifest, evidence, finding, report, digest, and sign-off models with forward-compatible safe string fields in `planalign_api/models/provenance.py`, then export them from `planalign_api/models/__init__.py` to satisfy T003
- [X] T005 [P] Add failing capture tests for effective-config redaction/fingerprint preservation, validated `simulation.random_seed`, census SHA-256/safe metadata, complete scenario-local seed manifests, Git clean/dirty/unavailable state, dirty-state fingerprinting, atomic writes, and symlink/change-during-read failures in `tests/unit/test_provenance_capture.py`
- [X] T006 Implement bounded file hashing, PII-safe effective-config projection, Git source-state capture, census/seed fingerprint manifests, and atomic `provenance.json` lifecycle writes in `planalign_api/services/provenance/capture.py` to satisfy T005
- [X] T007 [P] Extend failing run-metadata tests for caller-supplied authoritative run IDs, UUID validation, unchanged direct-simulation fallback IDs, and append-only behavior in `tests/test_run_metadata.py` and `tests/test_run_metadata_integration.py`
- [X] T008 Extend `check_and_record_run()` and `_append_record()` to accept the propagated run ID without changing the `run_metadata` schema or drift semantics in `planalign_orchestrator/run_metadata.py` to satisfy T007
- [X] T009 [P] Add failing validation tests for exact execution result capture, severity-based overall disposition, zero affected records on pass, defined implicated-record counts on fail, unknown severities, and rule-exception ERROR results in `tests/test_validation_framework.py`
- [X] T010 Extend registered validation rules and `DataValidator` reporting to provide safe affected-record counts and deterministic `passed`/`passed_with_warnings`/`failed` disposition in `planalign_orchestrator/validation.py` to satisfy T009
- [X] T011 [P] Add failing structured telemetry tests for authoritative run ID, safe VALIDATION results, completed-year event counts including explicit zero years, workforce reconciliation fields/equations, deterministic ordering, and query failure degradation in `tests/test_telemetry_emitter.py`
- [X] T012 Execute registered rules once in each pipeline VALIDATION stage, enforce the existing `fail_on_validation_error` policy for failed ERROR checks, and emit their exact safe results plus annual event/reconciliation aggregates through hooks in `planalign_orchestrator/pipeline_orchestrator.py` and `planalign_orchestrator/pipeline/telemetry_emitter.py` to satisfy T011
- [X] T013 [P] Add failing simulation lifecycle tests proving the manifest is created after config/seed preparation but before subprocess launch, the authoritative run context reaches the subprocess/database stamp, no physical paths leak, and terminal archive metadata uses `random_seed` in `tests/unit/simulation/test_run_archiver.py` and `tests/unit/test_provenance_capture.py`
- [X] T014 Wire manifest initialization, `PLANALIGN_RUN_ID` execution context, structured-record ingestion, successful finalization, and corrected random-seed archival through `planalign_api/services/simulation/service.py` and `planalign_api/services/simulation/run_archiver.py` to satisfy T013

**Checkpoint**: A new Studio run now produces a typed, PII-safe, incrementally updated `provenance.json` bound to the same run ID as its archive and database stamp; no report endpoint exists yet.

---

## Phase 3: User Story 1 - Generate a Complete Audit Artifact (Priority: P1) 🎯 MVP

**Goal**: Generate matching machine-readable JSON and concise Markdown for one fully evidenced completed archive through both CLI and Studio API without rerunning or reading current state.

**Independent Test**: Create a completed archive with all required provenance, request it from both channels, and verify identical evidence/digest, full yearly event/reconciliation/validation sections, `fully_verified`, and unchanged archive files.

### Tests for User Story 1 (write first and verify RED)

- [X] T015 [P] [US1] Add failing report-service tests for exact completed-run resolution, complete evidence assembly, `fully_verified`, JSON/Markdown field parity, explicit zero-event years, safe aggregate-only output, and unchanged archive hashes/mtimes in `tests/unit/test_provenance_report.py`
- [X] T016 [P] [US1] Add failing authenticated API contract tests for `GET /api/runs/{run_id}/provenance`, default JSON envelope, two-file ZIP, no-store response, and exact report/audit-sheet parity in `tests/api/test_provenance_api.py`
- [X] T017 [P] [US1] Add failing Typer tests for `planalign provenance RUN_ID --output-dir`, both output files, Rich disposition/digest/path summary, existing-file refusal, `--force`, and refusal to write inside the run archive in `tests/unit/cli/test_provenance_command.py`
- [X] T018 [P] [US1] Add a failing full-year-range isolated completed-run acceptance test covering authoritative identity, input/source fingerprints, every year's aggregates, captured validations, both channels, and no current-state reads in `tests/integration/test_run_provenance_report.py`

### Implementation for User Story 1

- [X] T019 [US1] Implement exact run-ID scanning over an existing workspace root, terminal-archive checks, directory/metadata/manifest identity agreement, and read-only file snapshots in `planalign_api/services/provenance/locator.py` to support T015
- [X] T020 [US1] Implement complete-manifest evidence assembly, required-field checks, artifact fingerprint verification, completed-year/reconciliation/validation completeness, and `fully_verified` classification in `planalign_api/services/provenance/report.py` to satisfy the complete-run cases in T015
- [X] T021 [US1] Implement versioned canonical evidence normalization, base SHA-256 digest creation, pretty JSON serialization, and the ordered Markdown audit sheet from one typed model in `planalign_api/services/provenance/render.py` to satisfy T015
- [X] T022 [US1] Implement authenticated JSON-envelope and in-memory two-file ZIP responses for `GET /api/runs/{run_id}/provenance` in `planalign_api/routers/provenance.py` to satisfy T016
- [X] T023 [US1] Register the provenance router under existing token protection and expose response models without weakening loopback/token defaults in `planalign_api/main.py` and `planalign_api/models/__init__.py`
- [X] T024 [US1] Implement safe paired JSON/Markdown destination writes, overwrite policy, Rich summary, and success behavior for fully verified reports in `planalign_cli/commands/provenance.py` to satisfy T017
- [X] T025 [US1] Register the flat `planalign provenance` command with the exact contract arguments and no config/database/latest selectors in `planalign_cli/main.py`
- [X] T026 [US1] Complete ingestion of structured completed-year and validation records into the final manifest and make the isolated completed-run acceptance test pass in `planalign_api/services/simulation/service.py`, `planalign_api/services/provenance/capture.py`, and `tests/integration/test_run_provenance_report.py`

**Checkpoint**: US1 is deployable as the MVP: a fully captured completed run yields one matching JSON/Markdown audit artifact from CLI or API and is independently testable without US2/US3 edge-case extensions.

---

## Phase 4: User Story 2 - Detect Missing or Unverifiable Provenance (Priority: P2)

**Goal**: Produce honest field-level findings for legacy, failed, cancelled, partial, malformed, or unbound archives without substituting current state or presenting them as fully verified.

**Independent Test**: Request fixtures with known missing/conflicting evidence after changing current config, source, inputs, seeds, and scenario database; verify only exact archive evidence appears, every gap is listed, the run status is preserved, disposition is `incomplete` or `unverifiable`, and archives remain unchanged.

### Tests for User Story 2 (write first and verify RED)

- [X] T027 [US2] Extend failing model/report tests for the full disposition precedence matrix, one finding per missing required field, unknown future status/event/severity preservation, null affected counts, malformed fingerprints, and incomplete-year reconciliation in `tests/unit/test_provenance_models.py` and `tests/unit/test_provenance_report.py`
- [X] T028 [P] [US2] Add failing strict locator/legacy tests for unknown IDs, no `results/` or latest fallback, duplicate matches, directory/metadata/manifest conflicts, unstable before/after snapshots, no `WorkspaceStorage` creation, and no `DatabasePathResolver`/project-DB access in `tests/unit/test_provenance_report.py`
- [X] T029 [P] [US2] Add failing failed/cancelled/partial archive tests for incremental evidence preservation, terminal-stage timing, absent future-year findings, correct `random_seed`, and no database/Excel substitution in `tests/unit/simulation/test_run_archiver.py` and `tests/unit/test_provenance_capture.py`
- [X] T030 [P] [US2] Extend failing API tests for valid 200 incomplete/unverifiable reports plus 404 unknown, 409 unstable, 422 duplicate/identity-conflict, and 406 unsupported representation responses in `tests/api/test_provenance_api.py`
- [X] T031 [P] [US2] Extend failing CLI tests for exit 0 incomplete/unverifiable reports and exit codes 2/3/4 for unsafe arguments, missing runs, and identity/consistent-read failures in `tests/unit/cli/test_provenance_command.py`

### Implementation for User Story 2

- [X] T032 [US2] Implement safe legacy archive projection, field-level missing/malformed/unbound/integrity findings, legacy `seed` versus `random_seed` conflict handling, unknown-value preservation, and disposition precedence in `planalign_api/services/provenance/report.py` to satisfy T027
- [X] T033 [US2] Harden strict locator duplicate detection, terminal-state enforcement, symlink/path containment, pre/post consistent-view comparison, and sanitized errors in `planalign_api/services/provenance/locator.py` to satisfy T028
- [X] T034 [US2] Finalize failed/cancelled manifests with last captured stages/years, preserve partial structured evidence, and avoid invalid database/Excel claims in `planalign_api/services/provenance/capture.py`, `planalign_api/services/simulation/service.py`, and `planalign_api/services/simulation/run_archiver.py` to satisfy T029
- [X] T035 [US2] Map normal incomplete/unverifiable reports and strict locator failures to the documented HTTP statuses without exposing archive paths in `planalign_api/routers/provenance.py` to satisfy T030
- [X] T036 [US2] Map safe output, not-found, and archive-identity/consistency failures to documented CLI exit codes while leaving valid incomplete/unverifiable reports at exit 0 in `planalign_cli/commands/provenance.py` to satisfy T031
- [X] T037 [US2] Extend the isolated acceptance test with failed/cancelled runs and post-run mutations to current config, Git/input/seed files, and scenario database, asserting report stability and byte-for-byte archive immutability in `tests/integration/test_run_provenance_report.py`

**Checkpoint**: US2 independently demonstrates that incomplete and legacy archives remain reviewable but are never overstated or backfilled from current state.

---

## Phase 5: User Story 3 - Verify Integrity and Record Review Sign-Off (Priority: P3)

**Goal**: Let reviewers independently recompute the deterministic evidence digest, detect covered-content alteration, and record a human sign-off tied to that digest without formal electronic signing.

**Independent Test**: Generate the same report repeatedly through both channels, verify identical digests, mutate every class of covered content and observe verification failure, modify sign-off fields without changing the evidence digest, and confirm the sign-off references the reviewed digest.

### Tests for User Story 3 (write first and verify RED)

- [X] T038 [P] [US3] Add failing canonicalization tests for sorted semantic lists/keys, explicit nulls, Unicode NFC, UTC datetime policy, finite numeric forms, compact UTF-8 bytes, request/output metadata exclusion, and independent SHA-256 recomputation in `tests/unit/test_provenance_digest.py`
- [X] T039 [P] [US3] Add failing tamper/sign-off tests proving add/change/remove of any covered evidence/finding/disposition changes the digest while reviewer name/decision/timestamp/comments do not, and both renderers reference the same digest in `tests/unit/test_provenance_digest.py` and `tests/unit/test_provenance_report.py`
- [X] T040 [P] [US3] Extend failing API tests for a strong digest `ETag`, deterministic report bodies across requests, deterministic two-entry contents independent of ZIP metadata, and digest parity with JSON/Markdown in `tests/api/test_provenance_api.py`
- [X] T041 [P] [US3] Extend failing CLI tests for deterministic reports across output directories/request times, atomic two-file publication, cleanup after partial write failure, and digest parity with API fixtures in `tests/unit/cli/test_provenance_command.py`

### Implementation for User Story 3

- [X] T042 [US3] Complete `planalign-provenance-json-v1` normalization and independent verification metadata exactly as specified in `contracts/report-schema.md` within `planalign_api/services/provenance/render.py` to satisfy T038 and T039
- [X] T043 [US3] Add blank digest-bound review sign-off models, Markdown sign-off lines, machine-readable sign-off structure, and concise recomputation instructions without including sign-off in covered bytes in `planalign_api/models/provenance.py` and `planalign_api/services/provenance/render.py`
- [X] T044 [US3] Emit the strong quoted digest `ETag`, `Cache-Control: no-store`, and deterministic in-memory two-file ZIP with no archived artifacts in `planalign_api/routers/provenance.py` to satisfy T040
- [X] T045 [US3] Implement atomic paired destination publication, failure cleanup, deterministic output content, and digest-focused Rich summary in `planalign_cli/commands/provenance.py` to satisfy T041
- [X] T046 [US3] Add cross-channel repeated-generation, tamper, independent recomputation, and sign-off-exclusion acceptance coverage in `tests/integration/test_run_provenance_report.py`

**Checkpoint**: All three stories are independently demonstrable; reviewers can retrieve, assess completeness, verify integrity, and record a digest-bound human decision.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Enforce privacy, performance, usability, documentation, and repository-wide quality gates after the selected user stories are complete.

- [X] T047 [P] Add report-output privacy regression scans covering employee IDs/rows, physical paths, usernames, credentials, Git diff content, raw validation details, census content, and seed content in `tests/unit/test_provenance_privacy.py`
- [X] T048 [P] Add bounded-aggregate performance and typical-output-size tests for the <2-second p95 and <5 MB targets without employee-row loading in `tests/unit/test_provenance_performance.py`
- [X] T049 [P] Document report generation, disposition meanings, digest verification, sign-off boundaries, privacy guarantees, and legacy limitations in `docs/guides/run_provenance_report.md`
- [X] T050 Execute every manual CLI/API, legacy, tamper, and isolated multi-year scenario from `specs/111-run-provenance-report/quickstart.md` and correct any documentation mismatch in that file
- [X] T051 Run focused Ruff and mypy gates over `planalign_orchestrator/`, `planalign_api/`, `planalign_cli/`, and all new provenance test files listed in `specs/111-run-provenance-report/quickstart.md`, fixing only feature-scoped findings in those paths
- [X] T052 Run `pytest -m fast` and the full isolated `tests/integration/test_run_provenance_report.py` with explicit temporary `DATABASE_PATH` and workspace root, recording any unrelated pre-existing failures without modifying `dbt/simulation.duckdb`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependency; T001 and T002 may proceed independently.
- **Foundational (Phase 2)**: Depends on Phase 1 and blocks every story. Tests T003/T005/T007/T009/T011/T013 can be authored in parallel, then each paired implementation follows its failing test.
- **US1 (Phase 3)**: Depends on the complete foundation and delivers the MVP report path.
- **US2 (Phase 4)**: Depends on the US1 report/locator/adapters but is independently tested with incomplete and legacy fixtures.
- **US3 (Phase 5)**: Depends on the US1 report/render/adapters, not on US2; US2 and US3 can proceed in parallel after US1.
- **Polish (Phase 6)**: Depends on all stories selected for delivery; privacy, performance, and documentation tasks can start in parallel before final gates.

### User Story Dependency Graph

```text
Setup → Foundation → US1 (MVP complete verified report)
                         ├──→ US2 (missing/incomplete/unverifiable handling)
                         └──→ US3 (integrity verification and sign-off)
US2 + US3 → Polish and full isolated validation
```

### Within Each User Story

1. Write the story's test tasks and confirm RED for the intended missing behavior.
2. Implement models/services before adapters.
3. Keep the router and CLI as thin adapters over the same report object.
4. Run the story's independent test before starting another sequential story.
5. Preserve archive/database/config/input file hashes and mtimes during every report-generation test.

### Parallel Opportunities

- T001 and T002 are independent setup tasks.
- T003, T005, T007, T009, T011, and T013 are parallel failing-test tasks over distinct concerns.
- T015-T018 can be written in parallel after the foundation.
- T028-T031 can be written in parallel for US2.
- T038-T041 can be written in parallel for US3.
- US2 and US3 can be implemented in parallel after US1.
- T047-T049 can proceed in parallel before T050-T052.

## Parallel Examples

### User Story 1

```text
Task T015: Complete-run report/no-write tests in tests/unit/test_provenance_report.py
Task T016: Authenticated JSON/ZIP contract tests in tests/api/test_provenance_api.py
Task T017: CLI paired-output tests in tests/unit/cli/test_provenance_command.py
Task T018: Full isolated completed-run test in tests/integration/test_run_provenance_report.py
```

### User Story 2

```text
Task T028: Strict locator/current-fallback tests in tests/unit/test_provenance_report.py
Task T029: Failed/cancelled capture tests in tests/unit/simulation/test_run_archiver.py and tests/unit/test_provenance_capture.py
Task T030: API incomplete/error contract tests in tests/api/test_provenance_api.py
Task T031: CLI disposition/exit tests in tests/unit/cli/test_provenance_command.py
```

### User Story 3

```text
Task T038: Canonicalization/recomputation tests in tests/unit/test_provenance_digest.py
Task T039: Tamper/sign-off exclusion tests in tests/unit/test_provenance_digest.py and tests/unit/test_provenance_report.py
Task T040: ETag/ZIP determinism tests in tests/api/test_provenance_api.py
Task T041: Atomic/repeated CLI output tests in tests/unit/cli/test_provenance_command.py
```

## Implementation Strategy

### MVP First (User Story 1)

1. Complete T001-T002 (setup).
2. Complete T003-T014 (authoritative run-bound capture foundation).
3. Complete T015-T026 (US1).
4. Stop and run the US1 unit, API, CLI, and full isolated completed-run test.
5. Demonstrate one `fully_verified` report through both channels before expanding edge cases.

### Incremental Delivery

1. **Foundation**: New runs retain safe, authoritative execution evidence without exposing it yet.
2. **US1/MVP**: Completed, fully evidenced runs produce matching reports.
3. **US2**: Legacy and incomplete runs become honestly reviewable with explicit gaps.
4. **US3**: Independent integrity verification and digest-bound sign-off are hardened.
5. **Polish**: Privacy, performance, documentation, lint/type, and full isolated gates complete the feature.

### Parallel Team Strategy

After the shared foundation and US1 report contracts are stable, one developer can implement US2 disposition/legacy behavior while another implements US3 canonicalization/sign-off hardening. They work in mostly separate test slices but must coordinate edits to `report.py`, `render.py`, router, and CLI through the dependency order above.

## Notes

- No task adds a dependency, public mart, database table, or employee-level report field.
- Never use current configuration, Git state, census/seed files, validators, scenario database, `DatabasePathResolver`, or `dbt/simulation.duckdb` to fill archived evidence during report generation.
- `provenance.json` may be written only by the active execution lifecycle; terminal report generation is strictly read-only.
- Unknown statuses/event types/severities are preserved safely but cannot produce `fully_verified` until supported.
- Formal electronic/cryptographic signing, report persistence in run history, and a separate verify command remain out of scope.

## Phase 7: Studio Report Viewer Extension

**Purpose**: Make the completed report workflow directly discoverable to analysts who execute simulations through PlanAlign Studio.

- [X] T053 Add typed authenticated JSON and ZIP provenance clients plus browser-safe JSON/Markdown downloads in `planalign_studio/services/api.ts`
- [X] T054 Add a dedicated report viewer with disposition, findings, identity, source/configuration/input evidence, aggregates, validation results, digest, and sign-off sections in `planalign_studio/components/RunProvenanceReport.tsx`
- [X] T055 Register the nested Studio report route in `planalign_studio/App.tsx`
- [X] T056 Add **View Provenance** and token-aware **Download Audit Report** actions for eligible archived runs in `planalign_studio/components/SimulationDetail.tsx`
- [X] T057 Document the Studio viewing and download workflow in `docs/guides/run_provenance_report.md` and `specs/111-run-provenance-report/quickstart.md`
- [X] T058 Validate the extension with TypeScript checking, a production Vite build, focused provenance API tests, and repository diff checks
