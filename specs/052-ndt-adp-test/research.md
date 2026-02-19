# Research: NDT ADP Test

**Branch**: `052-ndt-adp-test` | **Date**: 2026-02-19

## R1: ADP Calculation Data Source

**Decision**: Use `prorated_annual_contributions` from `fct_workforce_snapshot` as the numerator for individual ADP calculations, and `prorated_annual_compensation` as the denominator.

**Rationale**: The existing ACP test uses `employer_match_amount / prorated_annual_compensation`. ADP mirrors this structure but measures employee elective deferrals instead of employer match. The `prorated_annual_contributions` column already represents employee deferrals (pre-tax + Roth combined) and handles mid-year proration automatically via the simulation engine. This column is also used by the 415 test for employee deferrals.

**Alternatives considered**:
- `current_compensation` as denominator: Rejected because `prorated_annual_compensation` is the plan compensation that accounts for mid-year entrants and the 401(a)(17) compensation limit, consistent with ACP and 401(a)(4).
- Separate pre-tax and Roth columns: Not available in current schema; combined `prorated_annual_contributions` is sufficient since ADP treats both identically.

## R2: Two-Prong Test Implementation

**Decision**: Reuse the exact same two-prong test logic from ACP's `_compute_test_result()` method, adapted for ADP naming.

**Rationale**: The IRS ADP and ACP tests use identical threshold formulas:
- Basic: NHCE avg × 1.25
- Alternative: lesser of (NHCE avg × 2.0) and (NHCE avg + 2 percentage points)

The `_compute_test_result()` method in the existing NDT service already implements this correctly. The ADP version should be a new dedicated method (`_compute_adp_result()`) to avoid coupling, but with identical math.

**Alternatives considered**:
- Shared generic method for ADP and ACP: Rejected for now. While the math is identical, the result models differ (ADP has `excess_hce_amount`, different field names). A shared method would require awkward generics. If a third test uses the same prongs, refactoring to a shared helper would be warranted.

## R3: Excess HCE Deferral Calculation (Corrective Suggestion)

**Decision**: Calculate the aggregate dollar amount by which HCE deferrals exceed the passing threshold, using a leveling-down approach.

**Rationale**: When the test fails, the excess is calculated as: `(hce_avg_adp - applied_threshold) × total_hce_compensation`. This gives the total dollar amount of HCE deferrals that would need to be reduced (distributed back) for the HCE average ADP to equal the threshold. This is the standard corrective distribution calculation per IRS guidelines.

**Alternatives considered**:
- Per-employee excess allocation (top-down from highest-paid HCE): More accurate for actual corrective distributions but significantly more complex. Out of scope per clarification — the feature provides an aggregate suggestion, not individual allocation.
- QNEC calculation (how much employer must contribute to NHCEs): Explicitly excluded per clarification (Option B, not C).

## R4: Safe Harbor Toggle Implementation

**Decision**: Implement as a frontend toggle (off by default) passed as a query parameter to the API endpoint. When enabled, the backend returns an "exempt" result immediately without performing any calculation.

**Rationale**: This mirrors the "Include Match" toggle pattern used by the 401(a)(4) test. It is the simplest approach that avoids plan configuration schema changes. The user explicitly controls exemption per test run.

**Alternatives considered**:
- Plan-level config stored in workspace settings: Would require schema changes and adds complexity for a simple boolean flag. Can be added later if needed.
- Auto-detection from plan design: Not feasible — safe harbor status depends on plan amendment filings not captured in simulation data.

## R5: Prior Year Testing Method

**Decision**: Implement as a query parameter (`testing_method`: "current" or "prior", default "current"). When "prior" is selected, compute NHCE average ADP from the prior simulation year's data and use that as the baseline for the two-prong test. HCE ADP still comes from the current year.

**Rationale**: IRS allows either current or prior year testing method. The prior year method uses the prior year's NHCE ADP as the baseline, which provides more predictability for plan sponsors. The current year method (default) uses the same year's data for both groups.

**Alternatives considered**:
- Requiring a prior-year ADP test to have been run first: Too restrictive. Computing NHCE ADP from prior year snapshot data on-the-fly is straightforward.
- Storing prior year NHCE ADP results: Unnecessary given the data is already in `fct_workforce_snapshot`.

## R6: HCE Classification Reuse

**Decision**: Use the identical HCE determination pattern from the existing ACP test: prior-year compensation from `fct_workforce_snapshot` compared against `hce_compensation_threshold` from `config_irs_limits`.

**Rationale**: HCE determination is defined by IRS regulations and is identical across ADP, ACP, 401(a)(4), and all other nondiscrimination tests. The existing implementation in `run_acp_test()` (lines 293-360 of ndt_service.py) is correct and well-tested.

**Alternatives considered**: None — this is a regulatory requirement with a single correct implementation.

## R7: Frontend Component Architecture

**Decision**: Add `'adp'` to the existing `TestType` union and create `ADPSingleResult` and `ADPComparisonResults` components within `NDTTesting.tsx`, following the exact pattern of ACP components.

**Rationale**: All existing NDT test components live in a single file (`NDTTesting.tsx`, 1345 lines). Adding ADP components (~200 lines) keeps the file under 1600 lines and maintains the established pattern. The ADP single result component is structurally identical to ACP but with different field labels and the addition of excess amount display on failure.

**Alternatives considered**:
- Separate file for ADP components: Would break the established pattern where all NDT components coexist. Not warranted for ~200 lines of additional code.
- Shared generic result component for ADP/ACP: The visual layout differences (excess amount section, safe harbor badge) make a generic component more complex than two simple components.
