# Contract: Census eligibility column

The optional per-employee eligibility input carried in the census, and how it is normalized in `stg_census_data`.

## Input column

| Property | Value |
|----------|-------|
| Canonical name | `eligibility_override` |
| Type | BOOLEAN (nullable) |
| Optional | Yes — census files without it remain valid (FR-005) |
| Recognized values | `TRUE` (eligible), `FALSE` (ineligible), empty/NULL (unspecified → eligible) |

## Normalization (`stg_census_data`)

Mirrors the `auto_escalation_opt_out` (#316) scaffold:

```sql
-- Schema scaffold (WHERE false branch): column always exists
NULL::BOOLEAN AS eligibility_override

-- Data branch: lenient coercion, invalid → NULL → eligible
TRY_CAST(eligibility_override AS BOOLEAN) AS eligibility_override
```

**Contract guarantees**:
- Absent column → scaffold supplies `NULL` for every row → everyone eligible (FR-005).
- Unrecognized/garbage value → `TRY_CAST` yields `NULL` → eligible; a non-fatal import warning identifies affected values (FR-012, clarify Decision 5). The run proceeds.
- `NULL` is never treated as ineligible — only an explicit `FALSE` suppresses participation.

## Tests (`schema.yml`)

- `accepted_values` on the recognized states (documenting `[true, false]`; NULL allowed).
- A data test / import warning enumerates rows whose raw value failed to cast (observability, non-blocking).
