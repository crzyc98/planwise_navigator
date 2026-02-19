# Quickstart: NDT ACP Testing

**Branch**: `050-ndt-acp-testing` | **Date**: 2026-02-19

## What This Feature Does

Adds a Non-Discriminatory Testing (NDT) page to PlanAlign Studio where plan administrators can run the IRS ACP (Actual Contribution Percentage) test against completed simulations. The test classifies employees as HCE/NHCE based on prior-year compensation, computes per-employee ACP from employer matching contributions, and determines pass/fail per IRS regulations.

## Architecture Overview

This is a **read-only analytics feature** with three layers:

1. **Seed data** — Add HCE threshold to `config_irs_limits.csv`
2. **API service** — New router + service that queries `fct_workforce_snapshot` to compute HCE determination and ACP test results
3. **Frontend** — New NDT Testing page with scenario/year selection and results display

No dbt intermediate models are needed — all computation happens at query time in the API service layer using DuckDB analytical queries against the completed simulation database.

## Key Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `planalign_api/routers/ndt.py` | FastAPI router for NDT endpoints |
| `planalign_api/services/ndt_service.py` | NDT business logic and DuckDB queries |
| `planalign_studio/components/NDTTesting.tsx` | Main NDT Testing page component |

### Modified Files
| File | Change |
|------|--------|
| `dbt/seeds/config_irs_limits.csv` | Add `hce_compensation_threshold` column |
| `planalign_api/main.py` | Register NDT router |
| `planalign_studio/components/Layout.tsx` | Add NDT nav item |
| `planalign_studio/App.tsx` | Add NDT route |
| `planalign_studio/services/api.ts` | Add NDT API functions |

## Core SQL Query (ACP Test Logic)

```sql
-- HCE determination + ACP calculation in a single analytical query
WITH irs_limits AS (
  SELECT hce_compensation_threshold
  FROM config_irs_limits
  WHERE limit_year = :test_year - 1
),
prior_year AS (
  SELECT employee_id, current_compensation AS prior_year_comp
  FROM fct_workforce_snapshot
  WHERE simulation_year = :test_year - 1
),
current_year AS (
  SELECT
    s.employee_id,
    s.current_eligibility_status,
    s.is_enrolled_flag,
    s.employer_match_amount,
    s.prorated_annual_compensation,
    COALESCE(p.prior_year_comp, s.current_compensation) AS prior_year_comp,
    l.hce_compensation_threshold,
    CASE WHEN COALESCE(p.prior_year_comp, s.current_compensation) > l.hce_compensation_threshold
         THEN TRUE ELSE FALSE END AS is_hce
  FROM fct_workforce_snapshot s
  LEFT JOIN prior_year p ON s.employee_id = p.employee_id
  CROSS JOIN irs_limits l
  WHERE s.simulation_year = :test_year
    AND s.current_eligibility_status = 'eligible'
    AND s.prorated_annual_compensation > 0
),
per_employee AS (
  SELECT *,
    COALESCE(employer_match_amount, 0) / prorated_annual_compensation AS individual_acp
  FROM current_year
),
grouped AS (
  SELECT
    is_hce,
    COUNT(*) AS group_count,
    AVG(individual_acp) AS avg_acp
  FROM per_employee
  GROUP BY is_hce
)
SELECT * FROM grouped;
```

## How to Test

```bash
# 1. Ensure a simulation is completed
source .venv/bin/activate
planalign simulate 2025

# 2. Seed the IRS limits (after adding hce_compensation_threshold)
cd dbt && dbt seed --threads 1 && cd ..

# 3. Start the Studio
planalign studio

# 4. Navigate to NDT Testing, select scenario + year, run test
```

## Patterns to Follow

- **API router**: Copy `planalign_api/routers/analytics.py` structure
- **API service**: Copy `planalign_api/services/analytics_service.py` constructor pattern
- **Frontend page**: Copy `planalign_studio/components/DCPlanAnalytics.tsx` layout
- **Scenario selection**: Copy toggle handler + pill UI from DCPlanAnalytics
- **Year selection**: Copy cascading effect + dropdown from VestingAnalysis
