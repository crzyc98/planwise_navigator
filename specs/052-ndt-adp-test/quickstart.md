# Quickstart: NDT ADP Test

**Branch**: `052-ndt-adp-test` | **Date**: 2026-02-19

## Overview

Add ADP (Actual Deferral Percentage) test to the NDT suite. The ADP test calculates each eligible participant's ratio of elective deferrals to plan compensation, groups participants into HCE/NHCE, and applies the IRS two-prong nondiscrimination test. Includes safe harbor exemption toggle, prior/current year testing method, and excess HCE deferral calculation on failure.

## Files to Modify

### Backend (Python/FastAPI)

| File | Change | Lines (approx) |
|------|--------|-----------------|
| `planalign_api/services/ndt_service.py` | Add `ADPEmployeeDetail`, `ADPScenarioResult`, `ADPTestResponse` models; add `run_adp_test()` and `_compute_adp_result()` methods | ~200 new |
| `planalign_api/routers/ndt.py` | Add `GET /{workspace_id}/analytics/ndt/adp` endpoint | ~50 new |

### Frontend (React/TypeScript)

| File | Change | Lines (approx) |
|------|--------|-----------------|
| `planalign_studio/components/NDTTesting.tsx` | Add `'adp'` to TestType union; add safe harbor toggle; add `ADPSingleResult` and `ADPComparisonResults` components; update `handleRunTest()` and `handleToggleEmployees()` dispatch | ~250 new |
| `planalign_studio/services/api.ts` | Add `ADPEmployeeDetail`, `ADPScenarioResult`, `ADPTestResponse` interfaces; add `runADPTest()` function | ~60 new |

### Tests

| File | Change | Lines (approx) |
|------|--------|-----------------|
| `tests/test_ndt_adp.py` | New file: ADP test suite covering pass/fail/exempt/error, two-prong thresholds, excess calculation, edge cases | ~300 new |

## Key Implementation Pattern

The ADP test mirrors the ACP test structure exactly, with these differences:

| Aspect | ACP | ADP |
|--------|-----|-----|
| Numerator | `employer_match_amount` | `prorated_annual_contributions` |
| Denominator | `prorated_annual_compensation` | `prorated_annual_compensation` |
| Rate name | individual_acp | individual_adp |
| Extra fields | `eligible_not_enrolled_count` | `excess_hce_amount`, `testing_method`, `safe_harbor` |
| Toggles | none | Safe Harbor, Testing Method |
| On failure | margin only | margin + excess HCE dollar amount |

## Quick Verification

```bash
# Run ADP tests
pytest tests/test_ndt_adp.py -v

# Start studio to test UI
planalign studio

# Test API directly
curl "http://localhost:8000/api/workspaces/{ws_id}/analytics/ndt/adp?scenarios=baseline&year=2025"
```
