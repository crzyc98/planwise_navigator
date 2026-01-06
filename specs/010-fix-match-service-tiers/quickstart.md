# Quickstart: Service-Based Match Contribution Tiers

**Feature**: 010-fix-match-service-tiers
**Date**: 2026-01-05

## Overview

This feature adds service-based employer match tiers as a new match formula option. When enabled, the match rate varies by employee years of service instead of deferral percentage.

## Prerequisites

- Python 3.11 with virtual environment activated
- dbt-core 1.8.8 and dbt-duckdb 1.8.1 installed
- PlanAlign Studio (frontend) running for UI configuration

## Quick Test

### 1. Configure via dbt Variables

For quick testing without UI, set dbt variables directly:

```bash
cd dbt

# Run match calculation with service-based tiers
dbt run --select int_employee_match_calculations \
  --vars '{
    "simulation_year": 2025,
    "employer_match_status": "graded_by_service",
    "employer_match_graded_schedule": [
      {"min_years": 0, "max_years": 5, "rate": 50, "max_deferral_pct": 6},
      {"min_years": 5, "max_years": null, "rate": 100, "max_deferral_pct": 6}
    ]
  }' --threads 1
```

### 2. Verify Results

Query the output to verify service-based calculations:

```bash
duckdb simulation.duckdb "
SELECT
    employee_id,
    employer_match_amount,
    applied_years_of_service,
    formula_type,
    deferral_rate,
    eligible_compensation
FROM int_employee_match_calculations
WHERE simulation_year = 2025
  AND applied_years_of_service IS NOT NULL  -- Service-based rows only
ORDER BY applied_years_of_service
LIMIT 20
"
```

### 3. Compare Tiers

Verify tier boundaries work correctly:

```bash
duckdb simulation.duckdb "
SELECT
    CASE
        WHEN applied_years_of_service < 5 THEN '0-4 years (50%)'
        ELSE '5+ years (100%)'
    END AS service_tier,
    COUNT(*) AS employee_count,
    ROUND(AVG(employer_match_amount), 2) AS avg_match,
    ROUND(AVG(employer_match_amount / NULLIF(eligible_compensation, 0) * 100), 2) AS avg_match_pct
FROM int_employee_match_calculations
WHERE simulation_year = 2025
  AND employer_match_amount > 0
GROUP BY 1
ORDER BY 1
"
```

## Configuration via PlanAlign Studio UI

### 1. Launch Studio

```bash
planalign studio
```

### 2. Configure Match

1. Open a workspace and scenario
2. Navigate to **Configuration** → **DC Plan Settings**
3. Find **Employer Match** section
4. Select **Match Type**: "Service-Based"
5. Add service tiers:
   - Tier 1: 0-5 years → 50% match up to 6%
   - Tier 2: 5+ years → 100% match up to 6%
6. Save configuration

### 3. Run Simulation

```bash
planalign simulate 2025-2027 --verbose
```

## Key Files

| File | Purpose |
|------|---------|
| `dbt/models/intermediate/events/int_employee_match_calculations.sql` | Match calculation logic |
| `dbt/macros/get_tiered_match_rate.sql` | Service tier rate lookup macro |
| `planalign_orchestrator/config/export.py` | Config transformation |
| `planalign_studio/components/ConfigStudio.tsx` | UI configuration |

## Troubleshooting

### Match amounts are all zero

1. Check `employer_match_status` is set to `'graded_by_service'`
2. Verify `employer_match_graded_schedule` has valid tiers
3. Ensure employees have deferral rates > 0

### applied_years_of_service is NULL

- This is expected for deferral-based mode
- For service-based mode, check join to `int_workforce_snapshot_optimized`

### Tier boundaries seem wrong

- Remember: [min, max) convention (min inclusive, max exclusive)
- Employee with exactly 5 years → uses 5+ tier, not 0-5 tier

## Example Calculation

**Employee**:
- Years of service: 7
- Salary: $100,000
- Deferral rate: 8%

**Tier Config**:
- 5+ years: 100% match up to 6%

**Calculation**:
```
match = rate × min(deferral%, max_deferral_pct) × compensation
      = 1.00 × min(0.08, 0.06) × $100,000
      = 1.00 × 0.06 × $100,000
      = $6,000
```
