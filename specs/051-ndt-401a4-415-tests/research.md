# Research: NDT 401(a)(4) & 415 Tests

**Branch**: `051-ndt-401a4-415-tests` | **Date**: 2026-02-19

## R1: 415 Annual Additions Limit in IRS Limits Seed

**Decision**: Add `annual_additions_limit` column to `config_irs_limits.csv`

**Rationale**: The column does not exist today. All other IRS thresholds (HCE, 402(g), 401(a)(17), catch-up) are stored in this seed. Adding 415 here follows the established pattern and allows the NDT service to query it the same way it queries `hce_compensation_threshold`.

**Alternatives considered**:
- Hard-code 415 limits in Python: Rejected — violates centralized seed pattern, requires code changes for annual IRS updates.
- Separate seed table: Rejected — adds unnecessary complexity; one row per year is sufficient.

**Values to add** (IRS-published and projected):
| Year | 415 Limit |
|------|-----------|
| 2024 | $69,000 |
| 2025 | $70,000 |
| 2026 | $70,000 |
| 2027 | $71,000 (est) |
| 2028+ | Projected +$1K/yr |

## R2: Catch-Up Contribution Separation for 415 Test

**Decision**: Calculate base deferrals at query time using `LEAST(prorated_annual_contributions, base_limit)` where `base_limit` comes from `config_irs_limits` for the test year.

**Rationale**: `fct_workforce_snapshot.prorated_annual_contributions` includes all employee deferrals (base + catch-up + super catch-up). The `int_employee_contributions.sql` model applies age-based limits (base < 50, catch-up 50-59, super catch-up 60-63) but does not output a separate catch-up column. Since IRS Section 415 excludes catch-up contributions, we cap at `base_limit` to extract the base deferral portion.

**Alternatives considered**:
- Add `base_deferral_amount` and `catch_up_amount` columns to `fct_workforce_snapshot`: Rejected for this feature — would require modifying the snapshot model (a large, critical mart) and all downstream consumers. Better as a future enhancement.
- Join to `int_employee_contributions` intermediate model: Rejected — the intermediate model is incremental and may not be reliably available for ad-hoc queries.

## R3: Uncapped Gross Compensation (415 Compensation)

**Decision**: Use `current_compensation` from `fct_workforce_snapshot` as "415 compensation."

**Rationale**: `current_compensation` is the full annual salary before any IRS caps. For the 415 "100% of compensation" rule, this is the correct figure. `prorated_annual_compensation` is prorated for partial-year employees but `current_compensation` represents the unreduced annual rate. For 415 purposes, using the full annual rate is conservative (higher limit = fewer violations flagged) and aligns with common plan document language.

**Note**: For partial-year employees, the 415 limit based on 100% of compensation should ideally use actual compensation earned. Using `current_compensation` (full annual rate) is slightly generous but avoids false positives. Plans requiring strict partial-year enforcement can be addressed in a future iteration.

**Alternatives considered**:
- Use `prorated_annual_compensation`: This is prorated for hire/termination dates. It would be more precise for partial-year employees but could over-flag new hires who worked a partial year.
- Compute W-2 equivalent: No W-2 data is currently ingested; not feasible.

## R4: Service-Based NEC Detection

**Decision**: Query the `employer_core_status` configuration variable at runtime to detect if NEC is service-based.

**Rationale**: The simulation config stores `employer_core_status: 'graded_by_service'` (or `'flat'` / `'none'`). This is passed to dbt as `var('employer_core_status')`. The NDT service can detect the formula type by:
1. Reading the scenario's `overrides.yaml` for `employer_core_contribution.status`
2. Falling back to `base_config.yaml` if not overridden
3. The workspace storage API already provides scenario config access

**Alternatives considered**:
- Infer from contribution data variance: Rejected — unreliable, could be flat with variance from eligibility differences.
- Add a metadata column to `fct_workforce_snapshot`: Rejected — adds unnecessary schema changes.

## R5: Existing Data Availability Summary

| Required Field | Source Column | Available? |
|---|---|---|
| Employer NEC amount | `employer_core_amount` | Yes |
| Employer match amount | `employer_match_amount` | Yes |
| Employee total deferrals | `prorated_annual_contributions` | Yes (includes catch-up) |
| Base deferrals (excl. catch-up) | Derived: `LEAST(prorated_annual_contributions, base_limit)` | Derivable |
| Uncapped gross compensation | `current_compensation` | Yes |
| Plan compensation (401(a)(17) capped) | `prorated_annual_compensation` | Yes |
| Years of service | `current_tenure` | Yes |
| HCE status | Derived from prior-year `current_compensation` vs threshold | Derivable (same as ACP) |
| Enrollment status | `is_enrolled_flag` | Yes |
| Eligibility status | `current_eligibility_status` | Yes |
| IRS 402(g) base limit | `config_irs_limits.base_limit` | Yes |
| IRS 415 limit | `config_irs_limits.annual_additions_limit` | **Needs adding** |
| HCE threshold | `config_irs_limits.hce_compensation_threshold` | Yes |

## R6: Frontend Architecture

**Decision**: Extend the existing `NDTTesting.tsx` component with a test-type selector (tabs or dropdown) rather than creating separate components for each test type.

**Rationale**: The existing component already handles scenario selection, year selection, comparison mode, and results display. Adding a test-type dimension keeps the UI consistent and reuses all existing selection/comparison logic.

**Pattern**: Add a `testType` state variable (`'acp' | '401a4' | '415'`) and conditionally render the results section based on test type. The run-test handler calls the appropriate API endpoint.
