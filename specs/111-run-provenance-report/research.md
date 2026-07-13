# Research: Run Provenance Report

**Feature**: 111-run-provenance-report | **Date**: 2026-07-13

No technical unknowns remain. Research below resolves the decisions needed to bind a deterministic report to one archived run without consulting current state.

## D1: One authoritative run ID across Studio, archive, and orchestrator

**Decision**: Treat the run ID allocated by the Studio/API run request as authoritative and propagate it into the simulation subprocess through a dedicated execution-context environment variable. Extend `check_and_record_run()` to accept that run ID instead of generating another UUID when the context is present. Direct simulations without an external run context retain their existing generated ID, but only runs retained under `runs/<run_id>/` qualify for this report.

**Rationale**: The current Studio run directory and `run_metadata.json` use the API run ID, while `planalign_orchestrator.run_metadata._append_record()` generates a different UUID and observability generates a third. Matching on timestamps or fingerprints would be inference, not proof. A single propagated ID allows future database stamps, structured records, and archive evidence to identify the same execution.

**Alternatives considered**:
- Match the latest database row by timestamp/configuration: rejected because concurrent or repeated runs can match and FR-014 forbids inferred binding.
- Replace the API run ID with the orchestrator-generated ID after launch: rejected because the run directory, active-run registry, telemetry, and clients already use the API ID.

## D2: Versioned execution evidence manifest as the report source of truth

**Decision**: Create `provenance.json` in `runs/<run_id>/` before the subprocess starts, update it atomically at completed stage/year boundaries, and finalize it with the terminal status. The manifest contains only run-bound, PII-safe evidence and aggregate outcomes. Report generation reads this manifest as its primary source and never reconstructs missing evidence from current workspace configuration, scenario databases, repository files, inputs, or seeds.

**Rationale**: Successful archives currently retain config, metadata, a database copy, a log, and optional Excel; failed/cancelled archives retain only config, metadata, and log. None contain all required provenance, and the current validation results are not persisted. An incrementally written manifest supports completed, failed, cancelled, and partial runs without changing public marts or storing employee rows.

**Alternatives considered**:
- Add all evidence to the DuckDB `run_metadata` table: rejected as the sole source because failed runs can lack an archived database, file fingerprints and nested validation evidence are awkward relational additions, and the table currently has a different identity lifecycle.
- Derive the report from the archived database on demand: rejected because fact rows are not keyed by run ID, mixed-generation years can remain, and validation/Git/input evidence is absent.
- Parse `simulation.log` during report generation: rejected because logs are unstructured, incomplete, and may contain unsafe details.

## D3: Capture inputs immediately before execution

**Decision**: After the effective config has been resolved and scenario-local seeds have been written, but before the subprocess starts, capture:

- PlanAlign version;
- Git commit SHA, clean/dirty/unavailable state, and a dirty-state SHA-256 fingerprint when dirty;
- PII-safe effective configuration plus the existing effective-config fingerprint;
- validated `simulation.random_seed` (never the legacy `simulation.seed` key);
- census SHA-256, safe logical label, byte size, and record count when safely available;
- a sorted manifest of every effective scenario-local seed file with safe relative logical name, SHA-256, and byte size.

**Rationale**: Scenario seed files are overwritten on the next run and census/config/source state can change after execution. Existing successful and failed archivers incorrectly read `simulation.seed`, which may record 42 or null instead of the actual `random_seed`; the new manifest captures the typed execution value.

**Alternatives considered**:
- Fingerprint repository default seeds only: rejected because Studio creates scenario-local copies and writes overrides before dbt runs.
- Store physical paths for audit convenience: rejected because absolute paths can expose usernames and sensitive environment layout.
- Copy census or seed contents into the report: rejected by the PII and safe-metadata requirements.

## D4: Dirty working-tree fingerprint without exposing filenames or content

**Decision**: Capture Git SHA and status at execution start. When dirty, compute a SHA-256 over a canonical byte stream representing the tracked diff plus the status and content digests of non-ignored untracked files; store only clean/dirty/unavailable and the resulting digest. Ignored files, file names, diff content, and user/environment metadata are not reported.

**Rationale**: A boolean dirty flag does not distinguish two executed working trees. Existing Git helpers in `ExcelExporter` and `ScenarioBatchRunner` capture SHA/branch/clean state but must be extracted and strengthened for execution-time evidence. Git-ignored census/runtime data remains outside the fingerprint and avoids PII exposure.

**Alternatives considered**:
- Store the full patch: rejected because it can expose source secrets and makes the audit sheet unwieldy.
- Hash only `git diff`: rejected because untracked source files can affect execution.
- Treat every dirty tree as unavailable: rejected because a safe fingerprint can distinguish the state without disclosing it.

## D5: PII-safe effective configuration representation

**Decision**: Archive a report-safe effective configuration derived from the exact merged execution config. Replace path-valued census/input fields with stable logical placeholders and their separately captured safe input metadata; redact credentials and environment-specific path/user fields. Preserve all result-affecting non-sensitive values and record every redaction as part of the schema contract. Keep the existing archived execution `config.yaml` unchanged and outside report output.

**Rationale**: The current archived config can contain an absolute census path. The reviewer needs the effective assumptions, not a workstation username or physical data location. The captured configuration fingerprint remains the identity of the exact effective execution surface.

**Alternatives considered**:
- Emit `config.yaml` verbatim: rejected because it can expose sensitive paths.
- Omit all setup/input settings: rejected because reviewers would not see the effective assumptions.

## D6: Capture validation once during the run

**Decision**: Wire the existing registered `DataValidator` rules into the pipeline's `VALIDATION` stage. Persist each exact execution result with simulation year, rule name, severity, pass/fail, and affected-record count, plus an overall disposition. A failed ERROR check makes the disposition `failed`; failed WARNING checks produce `passed_with_warnings`; otherwise it is `passed`. Rule execution exceptions are already converted into failed ERROR results. Report generation never invokes validators.

**Rationale**: `ValidationResult` and `DataValidator.to_report_dict()` already provide the required shape, but `validate_year_results()` is currently not invoked by the main multi-year pipeline. `StageValidator` logs or raises for other stages but does not return structured results. Capturing the registered rules in the actual validation stage makes the evidence contemporaneous and testable.

**Alternatives considered**:
- Use `YearAuditor.generate_report()` on demand: rejected because that reruns checks against later database contents.
- Treat a successful dbt command as all validation checks passing: rejected because it loses rule identity, severity, outcome, and affected counts.
- Persist arbitrary validation `details` and messages: rejected because they are not required and may contain raw values or paths; the provenance artifact uses the safe required subset.

## D7: Capture annual aggregates at completed-year boundaries

**Decision**: Extend the existing structured telemetry hook to emit, after each successfully completed year, exact event counts by `simulation_year` and `event_type`, completed-year status, and a workforce reconciliation consisting of opening active workforce, actual hire events, actual termination events, expected closing workforce, actual closing active workforce, and variance. The Studio process consumes these structured records and atomically updates `provenance.json`. Missing tables or ambiguous start-year opening populations create field-level unavailable findings rather than inferred values.

**Rationale**: `TelemetryEmitter` already queries exact event counts with the orchestrator's own connection and emits year-completed records. Capturing aggregates while the simulation owns the database avoids later mixed-generation/current-database substitution and preserves completed years for failed/cancelled runs.

**Alternatives considered**:
- Query the scenario database after report request: rejected because it is current mutable state.
- Query the archived database copy for every report: rejected because it exists only for successful runs and fact rows lack run ownership.
- Use forecast fields from `int_workforce_needs`: rejected because the report requires actual reconciliation, not planned hiring/termination demand.

## D8: Deterministic report digest and sign-off boundary

**Decision**: Build one versioned canonical evidence payload containing all displayed evidence, explicit unavailable findings, and verification disposition. Normalize keys, list order, UTC timestamps, nulls, and finite numbers; serialize as UTF-8 JSON with sorted keys and compact separators; hash with SHA-256. Exclude the digest field itself, request/generation time, filenames, transport metadata, and sign-off values. Both JSON and Markdown render from the same typed report model and display the same digest. Sign-off fields explicitly reference that digest.

**Rationale**: This follows the repository's SHA-256/canonical JSON precedent while guaranteeing that channel, output directory, ZIP metadata, and later reviewer handwriting do not alter the evidence digest.

**Alternatives considered**:
- Hash rendered Markdown or pretty JSON bytes: rejected because whitespace and formatting changes would alter the digest without changing evidence.
- Include sign-off inside the digest: rejected because the sign-off is completed after generation and approves the pre-existing report digest.
- Add cryptographic signing: rejected as explicitly out of initial scope.

## D9: Verification disposition matrix

**Decision**:

- `fully_verified`: terminal status completed; authoritative identity agrees across directory, metadata, and manifest; every required field is present; captured artifact fingerprints match; all intended years completed; reconciliation is complete; and validation evidence has no failed ERROR disposition.
- `incomplete`: terminal status failed/cancelled/partial and the available manifest is internally consistent. The run status and every absent future-stage field remain visible.
- `unverifiable`: any required provenance is missing, malformed, unbound, identity-conflicting, or integrity-mismatched. If the run also failed/cancelled, preserve that run status alongside `unverifiable`.

**Rationale**: This implements FR-017/018 without overstating legacy or partial evidence. A completed legacy run with missing capture is unverifiable, not implicitly trusted.

**Alternatives considered**:
- Mark completed legacy archives verified using current reconstruction: rejected by FR-015.
- Treat every failed run as unverifiable: rejected because a failed run may have complete, internally consistent partial evidence and should be distinguishable as incomplete.

## D10: Strict read-only archive resolution

**Decision**: Resolve a run ID by scanning the configured existing workspace root for exact `runs/<run_id>` directories without constructing `WorkspaceStorage` (its constructor creates directories). Require exactly one match and require the directory name, archived metadata ID, and manifest ID to agree when present. Never fall back to `results/`, `scenario.last_run_id`, a scenario database, `DatabasePathResolver`, or the project database. Read and fingerprint required files before/after assembly; fail with a consistent-read error if the archive changes during the request.

**Rationale**: Existing `get_run()` falls back to `results/` for unknown IDs, and `DatabasePathResolver` can fall back to mutable databases. A global scan needs no persisted index, remains read-only, and is bounded by the current small retained-run count.

**Alternatives considered**:
- Require workspace and scenario selectors: viable but unnecessary because run IDs are UUIDs and the feature requires selection by run ID; extra selectors can conflict.
- Create a global run index: rejected in v1 because report generation must not mutate run history and default retention keeps scans small.
- Pick the first duplicate ID: rejected; duplicates are an identity conflict.

## D11: Shared service with CLI and authenticated Studio API adapters

**Decision**: Implement one report assembly/rendering service used by:

- `planalign provenance <RUN_ID> --output-dir <DIR> [--workspaces-root <PATH>] [--force]`, which always writes `<run-id>-provenance.json` and `.md` outside the archive; and
- authenticated `GET /api/runs/{run_id}/provenance`, returning a JSON envelope containing typed report evidence and the Markdown audit sheet, with `application/zip` available for a two-file download and the digest exposed as a strong `ETag`.

Both adapters return the same evidence and digest. A valid incomplete/unverifiable report is a successful result; unknown/duplicate/identity-conflicting or unstable archives return explicit errors.

**Rationale**: The CLI already imports API services for sync/Studio workflows, and the API already centralizes token auth and authenticated blob downloads. Sharing one service prevents format or digest drift.

**Alternatives considered**:
- Separate CLI and API builders: rejected because parity is a core success criterion.
- Persist generated reports in the run directory: rejected because generation must not modify archived artifacts.
- Add a verify subcommand now: deferred; the report exposes canonicalization metadata sufficient for independent verification.

## D12: Read-only, isolated validation strategy

**Decision**: Use fast unit tests for models, canonicalization, digest, disposition, safe metadata, render parity, strict lookup, and CLI/API errors. Use temporary workspace archives and minimal run-bound DuckDB fixtures for service tests, asserting file sizes, mtimes, and content hashes are unchanged. Use a full multi-year Studio simulation against an isolated database/workspace for cross-year capture, then mutate current config/source inputs and confirm the archived report is unchanged. Never validate against `dbt/simulation.duckdb`.

**Rationale**: The feature changes execution evidence capture and multi-year reporting. Only a full isolated run proves completed-year ownership, reconciliation, validation capture, failure handling, and no current-state substitution.

**Alternatives considered**:
- Unit tests only: rejected because run-ID propagation and subprocess evidence capture cross process boundaries.
- Targeted dbt runs in the shared database: rejected by repository policy and insufficient for multi-year invariants.
