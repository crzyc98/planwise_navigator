# Quickstart: Core Contribution Tier Validation & Points-Based Mode

**Branch**: `053-core-contribution-tiers` | **Date**: 2026-02-19

## Overview

This feature adds two enhancements to the DC Plan configuration page:
1. **Tier validation warnings** for graded-by-service core contributions (parity with match tier editors)
2. **Points-based core contribution mode** (new option alongside flat rate and graded by service)

## Key Files to Modify

### Frontend (P1 + P2)

| File | Change | Priority |
|------|--------|----------|
| `planalign_studio/components/config/DCPlanSection.tsx` | Add validation warnings to graded core section (lines 522-599); add points_based option to dropdown (line 513); add points-based core tier editor | P1, P2 |
| `planalign_studio/components/config/types.ts` | Add `PointsCoreTier` interface; add `dcCorePointsSchedule` to `FormData` | P2 |
| `planalign_studio/components/config/constants.ts` | Add default `dcCorePointsSchedule` to `DEFAULT_FORM_DATA` | P2 |
| `planalign_studio/components/config/buildConfigPayload.ts` | Add `core_points_schedule` to API payload | P2 |
| `planalign_studio/components/config/ConfigContext.tsx` | Load `dcCorePointsSchedule` from saved config | P2 |

### Backend (P3)

| File | Change | Priority |
|------|--------|----------|
| `planalign_orchestrator/config/export.py` | Export `employer_core_points_schedule` dbt variable in `_export_core_contribution_vars()` | P3 |
| `dbt/models/intermediate/int_employer_core_contributions.sql` | Add `points_based` conditional branch using `get_points_based_match_rate` macro | P3 |

## Development Approach

### P1: Graded Core Validation (Frontend Only)

Add the `validateMatchTiers()` call and amber warning box after the graded schedule editor (after line 597 in DCPlanSection.tsx). Pattern to follow: lines 195-212 (tenure match tier warnings).

### P2: Points-Based Core UI (Frontend Only)

1. Add `PointsCoreTier` type and `dcCorePointsSchedule` form field
2. Add `'points_based'` option to core contribution type dropdown
3. Add points tier editor (copy structure from points-based match editor, lines 217-309)
4. Add validation warnings to points-based core editor
5. Add payload mapping in buildConfigPayload.ts

### P3: Points-Based Core Backend

1. Add export logic for `employer_core_points_schedule` in export.py
2. Add `points_based` branch in `int_employer_core_contributions.sql` using existing `get_points_based_match_rate` macro

## Testing

```bash
# Frontend: visual testing via PlanAlign Studio
planalign studio

# Backend: run simulation with points-based core config
planalign simulate 2025

# dbt: verify core contribution model compiles
cd dbt && dbt compile --select int_employer_core_contributions --threads 1
```
