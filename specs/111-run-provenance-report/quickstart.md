# Quickstart: Validate Run Provenance Report

This guide proves execution-time capture, exact run binding, cross-channel parity, deterministic integrity, legacy/partial handling, privacy, and read-only generation. All behavioral checks use temporary workspaces and isolated databases; never run them against `dbt/simulation.duckdb`.

## Prerequisites

```bash
cd /Users/nicholasamaral/Developer/fidelity_planalign
source .venv/bin/activate
```

Review the contracts before validation:

- [Data model](./data-model.md)
- [API contract](./contracts/provenance-api.yaml)
- [CLI contract](./contracts/provenance-cli.md)
- [Canonical digest and audit-sheet contract](./contracts/report-schema.md)

## 1. Fast TDD loop

Run focused model, capture, report, CLI, and API tests first:

```bash
pytest -m fast \
  tests/unit/test_provenance_models.py \
  tests/unit/test_provenance_digest.py \
  tests/unit/test_provenance_capture.py \
  tests/unit/test_provenance_report.py \
  tests/unit/cli/test_provenance_command.py \
  tests/api/test_provenance_api.py -v
```

Expected:

- canonicalization is order-independent but sensitive to every covered value;
- sign-off edits do not change the evidence digest;
- complete, failed, cancelled, partial, malformed, legacy, and duplicate-ID fixtures receive the documented outcomes;
- JSON and Markdown evidence/digest parity is exact;
- physical paths, employee identifiers/rows, raw validation details, Git diff text, usernames, and credentials are absent;
- API token rules, `ETag`, JSON envelope, ZIP contents, and errors match the contract;
- archive files retain identical content hash, size, and modification time before and after generation.

## 2. Run-ID propagation and capture tests

```bash
pytest -m fast \
  tests/test_run_metadata.py \
  tests/unit/simulation/test_run_archiver.py \
  tests/unit/test_provenance_capture.py -v
```

Expected:

- the Studio run ID equals the archive directory, metadata ID, manifest ID, structured-record context, and new run's database metadata ID;
- direct non-archived simulations retain backward-compatible generated IDs;
- the manifest exists before subprocess execution and finalizes to the actual terminal state;
- `simulation.random_seed` is captured exactly; the legacy `simulation.seed` bug is not propagated;
- census and all scenario-local effective seeds are fingerprinted before execution;
- completed-year records are appended atomically and survive later failure/cancellation.

## 3. Full isolated multi-year behavior

Create a disposable location outside the repository's shared database:

```bash
mkdir -p /tmp/planalign-111/workspaces
mkdir -p /tmp/planalign-111/output-a
mkdir -p /tmp/planalign-111/output-b
```

Run the integration scenario with an explicit isolated database path:

```bash
DATABASE_PATH=/tmp/planalign-111/iso.duckdb \
PLANALIGN_API_WORKSPACES_ROOT=/tmp/planalign-111/workspaces \
pytest tests/integration/test_run_provenance_report.py -v
```

The integration fixture must execute the full configured year range, not a selective dbt run. Expected:

- every intended/completed year has event counts and a workforce reconciliation;
- each registered validation result has year, name, severity, pass/fail, and affected-record count;
- the completed run is `fully_verified` only when all required evidence and integrity checks pass;
- a controlled failed and cancelled run preserves captured inputs/stages/years and is never fully verified;
- changes made after execution to current config, census, seeds, repository state, or scenario database do not change the archived report;
- no file under the selected run archive is modified by either report channel.

## 4. CLI report generation

Use the run ID created by the isolated integration fixture or another retained run under the temporary workspace root:

```bash
planalign provenance "$RUN_ID" \
  --workspaces-root /tmp/planalign-111/workspaces \
  --output-dir /tmp/planalign-111/output-a
```

Expected output files:

```text
/tmp/planalign-111/output-a/<run-id>-provenance.json
/tmp/planalign-111/output-a/<run-id>-provenance.md
```

The terminal summary shows run ID, archived status, verification disposition, missing-required-evidence count, digest, and both output paths. An honest `incomplete` or `unverifiable` report still exits 0.

Repeat into a different output directory:

```bash
planalign provenance "$RUN_ID" \
  --workspaces-root /tmp/planalign-111/workspaces \
  --output-dir /tmp/planalign-111/output-b
```

Expected: the JSON report object, Markdown audit sheet, and displayed digest are identical; output directory and request time do not appear in covered evidence.

## 5. Studio API parity

Start the API against the disposable workspace root:

```bash
PLANALIGN_API_WORKSPACES_ROOT=/tmp/planalign-111/workspaces \
PLANALIGN_API_TOKEN=test-provenance-token \
planalign studio --api-only
```

In another terminal, request both representations:

```bash
curl -sS \
  -H 'X-API-Token: test-provenance-token' \
  -H 'Accept: application/json' \
  "http://127.0.0.1:8000/api/runs/$RUN_ID/provenance"
```

```bash
curl -sS \
  -H 'X-API-Token: test-provenance-token' \
  -H 'Accept: application/zip' \
  "http://127.0.0.1:8000/api/runs/$RUN_ID/provenance" \
  --output /tmp/planalign-111/provenance.zip
```

Expected:

- JSON contains `report` plus `audit_sheet`;
- strong `ETag` equals the quoted report digest;
- ZIP contains exactly `<run-id>-provenance.json` and `<run-id>-provenance.md`;
- API and CLI report evidence, Markdown, and digest match exactly;
- missing/invalid token returns 401; unknown run returns 404; duplicate/conflicting identity returns 422; unstable archive returns 409; unsupported `Accept` returns 406.

## 6. Legacy and incomplete archive behavior

```bash
pytest -m fast tests/unit/test_provenance_report.py \
  -k 'legacy or failed or cancelled or partial or missing or mismatch' -v
```

Expected:

- only safe evidence inside the exact selected run directory is used;
- there is no fallback to `results/`, latest run, current scenario config/database, project DB, current seeds, or current Git state;
- legacy seed conflicts are reported rather than silently choosing the wrong `seed` value;
- each required unavailable field receives its own safe finding;
- completed legacy runs with incomplete provenance are `unverifiable`;
- internally consistent failed/cancelled manifests are `incomplete` unless another required evidence gap makes them `unverifiable`.

## 7. Tamper and sign-off checks

```bash
pytest -m fast tests/unit/test_provenance_digest.py \
  -k 'tamper or sign_off or deterministic or parity' -v
```

Expected:

- changing, adding, or removing any covered evidence/finding/disposition changes the recomputed digest;
- changing only reviewer name, decision, timestamp, or comments leaves the evidence digest unchanged;
- both representations show the exact digest referenced by sign-off;
- canonicalization follows `planalign-provenance-json-v1` independently of pretty-print formatting.

## 8. Studio report workflow

Before the quality gates, verify the Studio workflow against an archived UUID-addressed run:

1. Open the scenario under **Simulate**.
2. Expand the run under **Run History**.
3. Confirm **View Provenance** opens `/simulate/<scenario-id>/runs/<run-id>/provenance` and displays the same digest as the API response.
4. Confirm **Download Audit Report** produces a ZIP containing only `<run-id>-provenance.json` and `<run-id>-provenance.md`.
5. Confirm the report page's individual JSON and Markdown downloads match those ZIP entries.

Validate the frontend contract and production bundle:

```bash
cd planalign_studio
npx tsc --noEmit
npm run build
cd ..
```

## 9. Quality gates

```bash
ruff check \
  planalign_orchestrator \
  planalign_api \
  planalign_cli \
  tests/unit/test_provenance_models.py \
  tests/unit/test_provenance_digest.py \
  tests/unit/test_provenance_capture.py \
  tests/unit/test_provenance_report.py \
  tests/api/test_provenance_api.py \
  tests/integration/test_run_provenance_report.py
```

```bash
mypy planalign_orchestrator/ planalign_api/ planalign_cli/ --ignore-missing-imports
```

After focused and isolated checks pass, run the broader fast suite:

```bash
pytest -m fast
```

No command in this guide runs dbt against or treats `dbt/simulation.duckdb` as validation ground truth.
