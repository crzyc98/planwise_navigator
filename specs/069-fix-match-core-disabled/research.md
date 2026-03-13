# Research: Fix DC Plan Match/Core Contributions When Disabled

**Date**: 2026-03-13
**Feature**: 069-fix-match-core-disabled

## R1: Root Cause — Match Enabled Flag Not Propagated

**Decision**: The `match_enabled` flag is sent by the UI but dropped in the orchestrator config export. The fix requires adding 3 lines in `export.py` and a master gate in the dbt model.

**Rationale**: Traced the full data flow end-to-end:

| Layer | Component | Status |
|-------|-----------|--------|
| Frontend | `buildConfigPayload.ts:94` sends `match_enabled: Boolean(formData.dcMatchEnabled)` | Working |
| API | `scenarios.py` stores in `config_overrides` | Working |
| Config Export | `export.py:_export_employer_match_vars()` lines 429-562 | **BROKEN** — never reads `dc_plan.match_enabled` |
| dbt Variable | `int_employee_match_calculations.sql` lines 59-73 | **MISSING** — no `employer_match_enabled` variable |
| dbt Gate | `int_employee_match_calculations.sql` lines 331-392 | **MISSING** — no master on/off conditional |

**Alternatives considered**:
- Gate at the UI level (hide match config when disabled): Rejected — does not prevent CLI path from calculating match
- Gate at the API level (strip match config): Rejected — loses configuration for re-enabling
- Gate at both export.py AND dbt model: **Selected** — follows the proven `employer_core_enabled` pattern

## R2: Core Contribution Path Verification

**Decision**: The core contribution path is fully wired and working correctly. No fix needed.

**Rationale**: Traced end-to-end:
- `buildConfigPayload.ts:120` sends `core_enabled: Boolean(formData.dcCoreEnabled)`
- `export.py:799-801` reads `dc_plan_dict.get("core_enabled")` and sets `dbt_vars["employer_core_enabled"]`
- `int_employer_core_contributions.sql:51` defines `{% set employer_core_enabled = var('employer_core_enabled', true) %}`
- `int_employer_core_contributions.sql:250` gates with `WHEN {{ employer_core_enabled }}`

**Alternatives considered**: None — the implementation is correct.

## R3: Implementation Pattern — Follow Core Contribution Pattern

**Decision**: Mirror the exact pattern used for `employer_core_enabled` in the match path.

**Rationale**: The core contribution implementation is production-proven and uses the same config export pipeline. The pattern is:

1. **export.py**: Read `dc_plan_dict.get("match_enabled")` → set `dbt_vars["employer_match_enabled"]`
2. **dbt model**: Add `{% set employer_match_enabled = var('employer_match_enabled', true) %}` variable
3. **dbt model**: Wrap the final match amount in a `{% if employer_match_enabled %}...{% else %}0{% endif %}` gate

**Alternatives considered**:
- Complex CTE restructuring to skip all match CTEs: Rejected — over-engineered, the final gate is sufficient and simpler
- Add a separate `int_match_enabled_gate` model: Rejected — unnecessary abstraction for a single boolean check

## R4: Backward Compatibility

**Decision**: Default `employer_match_enabled` to `true` so existing scenarios and CLI runs are unaffected.

**Rationale**:
- The dbt variable defaults to `true`: `var('employer_match_enabled', true)`
- The YAML config has no `match_enabled` field — the default handles this
- Only scenarios explicitly configured via the DC Plan UI with `match_enabled: false` will disable match
- This matches the core contribution pattern where `employer_core_enabled` defaults to `true`

## R5: Downstream Impact

**Decision**: Only `int_employee_match_calculations.sql` needs the gate. Downstream models (`fct_employer_match_events`, `fct_workforce_snapshot`) consume the already-gated values.

**Rationale**:
- `fct_employer_match_events.sql` reads `employer_match_amount` from `int_employee_match_calculations` — if it's $0, the downstream is $0
- `fct_workforce_snapshot` aggregates match amounts — $0 inputs produce $0 totals
- No additional downstream changes needed

## R6: Match Status Tracking When Disabled

**Decision**: When `employer_match_enabled` is false, set `match_status` to `'disabled'` for audit trail clarity.

**Rationale**: The existing match_status field has values: `'ineligible'`, `'no_deferrals'`, `'calculated'`. Adding `'disabled'` distinguishes between "employee was ineligible" and "match was turned off for the entire scenario". This is important for audit/reporting.
