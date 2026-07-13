# Contract: Provenance Report Canonicalization and Human Audit Sheet

## Canonical evidence payload

The SHA-256 digest covers exactly this object:

```json
{
  "report_schema_version": "1.0",
  "evidence": {},
  "missing_evidence": [],
  "verification_disposition": "fully_verified"
}
```

The `evidence` and `missing_evidence` shapes are defined by [data-model.md](../data-model.md) and [provenance-api.yaml](./provenance-api.yaml).

## Normalization rules (`planalign-provenance-json-v1`)

1. Validate the report with the version-matched Pydantic model before canonicalization.
2. Include all declared keys, including explicit nulls and empty arrays. Reject undeclared keys.
3. Sort object keys lexicographically during serialization.
4. Sort semantic lists before serialization:
   - completed years numerically;
   - seed files by normalized logical name;
   - event counts by year then event type;
   - reconciliations by year;
   - validation results by year, check name, severity, then pass/fail;
   - stage completions by year, canonical stage order, then completion time;
   - findings by field path, code, then reason.
5. Normalize datetimes to UTC RFC 3339 with `Z` and a fixed microsecond policy defined by the schema version.
6. Serialize integers as base-10 JSON integers. Serialize contract decimals using their normalized decimal-string field representation; reject NaN and infinity.
7. Normalize strings to Unicode NFC and reject control characters outside JSON whitespace rules.
8. Serialize UTF-8 with the equivalent of `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, and `allow_nan=False`; no trailing newline is hashed.
9. Compute lowercase hexadecimal SHA-256 over those exact bytes.

The digest object, sign-off values, generation/request timestamps, output names, formatting whitespace, HTTP headers, and ZIP metadata are excluded.

## Machine-readable representation

The JSON file is a pretty-printed complete `ProvenanceReport`, including:

- the canonical evidence fields;
- deterministic `digest` metadata/value;
- a blank `sign_off` object whose `report_digest` is pre-filled.

An independent verifier removes `digest` and `sign_off`, constructs the four-key canonical payload above, applies the named normalization, hashes it, and compares the result with `digest.value` and `sign_off.report_digest`.

## Human-readable audit sheet

Markdown uses this stable section order:

1. Title, run ID, archived status, and prominent verification disposition
2. Missing/Unavailable Evidence (shown near the top; explicit `None` only when empty)
3. Run Identity and Execution Timing
4. Software and Source State
5. Effective Configuration and Fingerprint
6. Census Input and Effective Seed Files
7. Event Counts by Simulation Year and Event Type
8. Annual Workforce Reconciliation
9. Captured Validation Results and Overall Validation Disposition
10. Integrity Verification (algorithm, canonicalization ID, digest, concise recomputation instructions)
11. Reviewer Sign-Off

Every evidence value in Markdown comes from the same typed report model used for JSON. The renderer never reads archive/config/database files directly.

### Sign-off template

```text
Report digest approved: <64-hex digest>
Reviewer name: ______________________________
Decision:      ______________________________
Timestamp:     ______________________________
Comments:      ______________________________
               ______________________________
```

Editing this section does not change the evidence digest. It is a human attestation reference, not an identity-backed electronic or cryptographic signature.

## ZIP representation

The API ZIP contains exactly the JSON and Markdown files named with the run ID. Entry timestamps/order/compression are transport metadata and do not affect the evidence digest. No archive database, config file, log, census/seed file, or employee-level artifact is included.
