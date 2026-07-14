# Run Provenance Report

Generate a read-only audit artifact for one archived Studio run without rerunning the simulation:

```bash
planalign provenance RUN_ID --output-dir ./audit-reports
```

For a non-default Studio archive root, add `--workspaces-root DIRECTORY`. Existing report files are protected unless `--force` is supplied. The command will never write inside the selected run archive.

The Studio API exposes the same evidence at `GET /api/runs/{run_id}/provenance`. The default response contains the typed JSON report and Markdown audit sheet; request `Accept: application/zip` for a two-file bundle. Existing API token rules apply.

## View and download in PlanAlign Studio

Studio is the primary report workflow:

1. Open **Simulate** and select the scenario.
2. Expand a completed, failed, or cancelled run under **Run History**.
3. Select **View Provenance** to open the human-readable report inside Studio.
4. Select **Download Audit Report** to download the matching JSON and Markdown files as a ZIP.

The report page also offers individual **JSON** and **Markdown** downloads. It displays missing evidence near the top, followed by run identity and timing, source/configuration evidence, input fingerprints, annual event counts, workforce reconciliations, captured validation results, the deterministic digest, and the digest-bound sign-off template.

Studio uses its existing API authentication headers for every report request and download. Active runs and non-UUID legacy placeholders do not show report actions. No Studio report action reruns a simulation or writes into the archived run.

## Dispositions

- `fully_verified`: the completed run has bound execution-time identity, source, configuration, input, yearly aggregate, reconciliation, and validation evidence.
- `incomplete`: identity is sound, but execution did not complete or has non-integrity gaps.
- `unverifiable`: required evidence is absent, malformed, unbound, or fails integrity checks.

Legacy, failed, cancelled, and partial archives remain reportable when their identity is sound. Missing fields are listed individually; report generation never fills them from current configuration, Git state, inputs, validators, or databases.

## Integrity and sign-off

The report digest is SHA-256 over the canonical four-field payload described by `planalign-provenance-json-v1`: schema version, evidence, missing-evidence findings, and disposition. An independent verifier can remove `digest` and `sign_off`, apply the documented canonicalization, and recompute SHA-256. The API also returns the digest as a strong `ETag`.

The audit sheet includes blank reviewer name, decision, timestamp, and comments lines tied to the digest. Those fields are excluded from the evidence digest. This is a human attestation template, not identity-backed electronic or cryptographic signing.

## Privacy boundary

Reports include aggregate counts and safe fingerprints only. They exclude census rows, employee identifiers, employee events, seed contents, source diffs, physical input paths, credentials, and raw validation details. Report generation reads only the exact selected archive and does not modify run history, simulation outputs, or databases.
