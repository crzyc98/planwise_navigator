# Data Model: Run Provenance Report

**Feature**: 111-run-provenance-report | **Date**: 2026-07-13

## Design boundary

`provenance.json` is a versioned, PII-safe execution evidence manifest stored inside one run archive. It is created as part of the run lifecycle, not by report generation. The generated `ProvenanceReport` is a read-only projection of that manifest or, for legacy runs, only evidence already present in the exact selected archive plus explicit unavailable findings.

No employee-level records, physical paths, validation detail payloads, or source diffs are permitted in either model.

## Entity: Run Provenance Manifest

One manifest per `runs/<run_id>/`. Pydantic validates it at every atomic write and read.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `schema_version` | string | required; known version such as `1.0` | Manifest compatibility identifier |
| `run_id` | string | required; UUID; equals archive directory and metadata IDs | Authoritative execution identity |
| `capture_state` | enum | `capturing`, `completed`, `failed`, `cancelled` | Manifest lifecycle, distinct from verification disposition |
| `run_identity` | `RunIdentityEvidence` | required | Scenario, plan design, workspace, status, and years |
| `execution_timing` | `ExecutionTimingEvidence` | required | Run and captured stage timing |
| `software` | `SoftwareEvidence` | required | Version and Git state captured at execution start |
| `configuration` | `ConfigurationEvidence` | required | PII-safe effective config and captured fingerprint |
| `random_seed` | integer or null | required key | Exact `simulation.random_seed`; null produces unavailable finding |
| `census_input` | `InputFingerprint` or null | required key | Census safe metadata and SHA-256 |
| `seed_files` | list[`SeedFingerprint`] | sorted by logical name | Every effective scenario-local seed used by dbt |
| `event_counts` | list[`AnnualEventCount`] | unique `(year,event_type)`; deterministic order | Completed-year aggregate fact event counts |
| `workforce_reconciliations` | list[`AnnualWorkforceReconciliation`] | unique year | Completed-year workforce equation |
| `validation_results` | list[`CapturedValidationResult`] | unique execution result identity | Exact safe rule outcomes captured during VALIDATION |
| `validation_disposition` | enum | `passed`, `passed_with_warnings`, `failed`, `incomplete`, `unavailable` | Overall captured validation outcome |
| `completed_stages` | list[`StageCompletion`] | unique `(year,stage)` | Stage completion evidence for partial runs |
| `capture_findings` | list[`EvidenceFinding`] | sorted by field path/code | Capture-time missing/malformed/integrity findings |
| `archive_artifacts` | list[`ArtifactFingerprint`] | safe logical names only | Optional binding for config/database/log evidence without exposing content |
| `started_at` | UTC datetime | required | Capture/run start |
| `finalized_at` | UTC datetime or null | set exactly once on terminal state | Manifest terminal time |

### Lifecycle

```text
run directory created
        │
        ▼
  capturing ── completed-year records appended atomically ──┐
        │                                                   │
        ├── successful process/archive finalization ───────► completed
        ├── failed process/archive finalization ───────────► failed
        └── cancellation finalization ─────────────────────► cancelled
```

- Terminal manifests are immutable through the report service.
- A crash before terminal finalization leaves `capturing`; once the run is no longer active, a report classifies it as incomplete or unverifiable based on available evidence and never edits it.
- Atomic writes use a sibling temporary file and replacement during execution only. Report generation opens files read-only.

## Value object: Run Identity Evidence

| Field | Type | Rules |
|---|---|---|
| `run_id` | string | Must equal manifest ID, archive directory name, and `run_metadata.json.run_id` |
| `workspace_id` | string or null | Safe identifier; absent legacy value is a finding |
| `scenario_id` | string or null | Required for fully verified |
| `plan_design_id` | string or null | Required for fully verified |
| `status` | string | Preserve known or future archived status verbatim after safe validation |
| `intended_start_year` | integer or null | Must be <= intended end year |
| `intended_end_year` | integer or null | Must be >= intended start year |
| `completed_years` | list[integer] | Unique, sorted, within intended range |

## Value object: Execution Timing Evidence

| Field | Type | Rules |
|---|---|---|
| `started_at` | UTC datetime or null | Required for fully verified |
| `completed_at` | UTC datetime or null | Required for completed status; may represent failure/cancel terminal time |
| `duration_seconds` | finite non-negative decimal or null | Must agree with timestamps within documented tolerance when all exist |
| `terminal_stage` | string or null | Last known stage, preserving unknown future names |
| `stage_completions` | list[`StageCompletion`] | Sorted by year then canonical stage order/time |

`StageCompletion` contains year, stage name, started/completed timestamps when captured, duration, and completion outcome. It contains no log text.

## Value object: Software Evidence

| Field | Type | Rules |
|---|---|---|
| `planalign_version` | string or null | Captured before execution; required for fully verified |
| `git_commit_sha` | string or null | 40 lowercase hex characters when available |
| `working_tree_state` | enum | `clean`, `dirty`, `unavailable` |
| `working_tree_fingerprint` | string or null | 64 hex SHA-256 required when state is dirty; null when clean; finding when unavailable |

Branch name, username, host, current working directory, filenames, and diff content are not report evidence.

## Value object: Configuration Evidence

| Field | Type | Rules |
|---|---|---|
| `effective` | JSON object or null | Exact result-affecting values with contract-defined path/secret redactions |
| `fingerprint` | string or null | 64 lowercase hex SHA-256 from the execution-time config function |
| `fingerprint_method` | string or null | Identifies the captured algorithm/version |
| `redactions` | list[string] | Sorted logical field paths replaced with safe markers |

Validation rejects non-finite numbers, arbitrary objects, path traversal values, and keys designated as credentials. A redaction marker is evidence that the value was intentionally generalized, not that the field was absent.

## Value object: Input Fingerprint

Used for the census input.

| Field | Type | Rules |
|---|---|---|
| `logical_name` | string | Safe basename/logical label only; no absolute path or separators outside approved relative syntax |
| `sha256` | string | 64 lowercase hex characters |
| `size_bytes` | integer or null | Non-negative |
| `record_count` | integer or null | Non-negative aggregate only |
| `format` | string or null | Safe normalized value such as `parquet` or `csv` |

No columns, rows, employee identifiers, sample values, or source path are stored.

## Value object: Seed Fingerprint

| Field | Type | Rules |
|---|---|---|
| `logical_name` | string | Unique normalized path relative to scenario seed root; no `..` or absolute path |
| `sha256` | string | 64 lowercase hex characters |
| `size_bytes` | integer | Non-negative |

The manifest must contain every regular file dbt can load under the effective seed root. Symlinks escaping the seed root, duplicate normalized names, unreadable files, or changes during capture create findings and prevent full verification.

## Entity: Annual Event Count

| Field | Type | Rules |
|---|---|---|
| `simulation_year` | integer | Must appear in `completed_years` |
| `event_type` | string | Safe captured value; unknown future types preserved |
| `count` | integer | Non-negative |

For a year known to have completed with no events, the manifest stores an explicit zero entry using a defined total/no-event representation; absence is not silently interpreted as zero.

## Entity: Annual Workforce Reconciliation

| Field | Type | Rules |
|---|---|---|
| `simulation_year` | integer | Unique; must appear in `completed_years` |
| `opening_workforce` | integer or null | Non-negative; start-year source explicitly identified |
| `hires` | integer or null | Actual hire event count, non-negative |
| `terminations` | integer or null | Actual termination event count, non-negative |
| `expected_closing_workforce` | integer or null | `opening + hires - terminations` when all inputs available |
| `actual_closing_workforce` | integer or null | Active closing workforce from completed snapshot |
| `variance` | integer or null | `actual_closing - expected_closing` |
| `opening_source` | enum or null | `baseline`, `prior_year_snapshot`, or `unavailable` |

Any unavailable component remains null and creates a field-level finding; the service does not fill it from current or forecast data.

## Entity: Captured Validation Result

| Field | Type | Rules |
|---|---|---|
| `simulation_year` | integer | Year whose results were checked |
| `check_name` | string | Stable registered rule name |
| `severity` | string | Preserve known `error`/`warning`/`info` and safe unknown future values |
| `passed` | boolean | Exact execution outcome |
| `affected_record_count` | integer or null | Non-negative; null creates unavailable finding |

Arbitrary `message` and `details` from `ValidationResult` are not copied because they may contain paths or raw data. Registered rules must return 0 affected records on pass and a defined implicated-record count on failure for full verification.

## Entity: Evidence Finding

| Field | Type | Rules |
|---|---|---|
| `field_path` | string | Stable report schema path, never a physical path |
| `code` | enum | `unavailable`, `malformed`, `unbound`, `identity_conflict`, `integrity_mismatch`, `unsafe_metadata`, `incomplete_capture` |
| `reason` | string | Safe bounded explanation with no employee values or environment path |
| `required` | boolean | Whether the finding blocks `fully_verified` |

Findings are unique by `(field_path,code)` and sorted deterministically.

## Entity: Provenance Report

Generated in memory from exactly one resolved archive.

| Field | Type | Description |
|---|---|---|
| `report_schema_version` | string | Machine contract/canonicalization version |
| `evidence` | `ReportEvidence` | All run evidence and aggregate outcomes displayed in both representations |
| `missing_evidence` | list[`EvidenceFinding`] | Capture plus read-time findings |
| `verification_disposition` | enum | `fully_verified`, `incomplete`, or `unverifiable` |
| `digest` | `ReportDigest` | Method, canonicalization ID, and 64-hex value |
| `sign_off` | `ReviewSignOff` | Blank structure referencing the digest |

### Verification disposition rules

1. Any identity conflict or unstable/inconsistent archive prevents report emission and returns a request error.
2. Any required missing, malformed, unbound, unsafe, or mismatched evidence yields `unverifiable`.
3. Otherwise, a failed/cancelled/partial/capturing run yields `incomplete`.
4. Otherwise, only completed status, all intended years completed, full reconciliation, and a non-failed captured validation disposition yield `fully_verified`.

Unknown statuses are preserved and cannot yield `fully_verified` until explicitly supported.

## Value object: Report Digest

| Field | Type | Rules |
|---|---|---|
| `algorithm` | literal | `SHA-256` |
| `canonicalization` | string | Versioned identifier such as `planalign-provenance-json-v1` |
| `value` | string | 64 lowercase hex characters |

Covered payload:

```text
report_schema_version + evidence + missing_evidence + verification_disposition
```

Excluded: digest object, sign-off values, generation/request time, output filenames, Markdown/pretty-JSON whitespace, HTTP headers, and ZIP metadata.

## Value object: Review Sign-Off

| Field | Type | Rules |
|---|---|---|
| `report_digest` | string | Pre-filled exact digest value being reviewed |
| `reviewer_name` | string or null | Blank at generation |
| `decision` | string or null | Blank at generation; intended reviewer decision |
| `timestamp` | datetime or null | Blank at generation |
| `comments` | string or null | Blank at generation |

Changing sign-off values does not change the evidence digest. Formal identity verification and cryptographic signature fields are intentionally absent.

## Relationships

```text
Archived Run 1 ── 1 Run Provenance Manifest
Manifest    1 ── * Annual Event Counts
Manifest    1 ── * Annual Workforce Reconciliations
Manifest    1 ── * Captured Validation Results
Manifest    1 ── * Seed Fingerprints
Manifest    1 ── * Evidence Findings
Archived Run 1 ── 1 generated Provenance Report (per request, not persisted)
Report      1 ── 1 Report Digest
Report      1 ── 1 blank Review Sign-Off reference
```

There are no database foreign keys or employee relationships. The authoritative run ID is the application-level join across the archive directory, metadata, manifest, telemetry context, and optional `run_metadata` row.

## Legacy mapping

When `provenance.json` is absent, the report service may read only safe evidence inside the exact selected archive:

- directory name and matching `run_metadata.json` identity/status/timing;
- a PII-safe projection of archived `config.yaml` when parseable;
- safe artifact presence/fingerprints when they can be captured without opening current state.

It must not select a `run_metadata` database row by latest timestamp, trust legacy `run_metadata.json.seed` when it conflicts with `simulation.random_seed`, query outcome rows lacking authoritative run binding, run validators, or consult current workspace/scenario/repository files. Every unavailable required field is listed and the report is `unverifiable`.
