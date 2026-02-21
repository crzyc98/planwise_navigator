# Quickstart: Deferral Distribution Comparison

**Branch**: `059-deferral-dist-comparison` | **Date**: 2026-02-21

## Overview

Add a grouped bar chart to the DC Plan comparison section that compares deferral rate distributions across scenarios with a year selector.

## Files to Modify

### Backend (3 files)

1. **`planalign_api/models/analytics.py`** — Add `DeferralDistributionYear` model and extend `DCPlanAnalytics`
2. **`planalign_api/services/analytics_service.py`** — Add `_get_deferral_distribution_all_years()` method
3. **`planalign_studio/services/api.ts`** — Add `DeferralDistributionYear` TypeScript interface

### Frontend (1 file)

4. **`planalign_studio/components/DCPlanComparisonSection.tsx`** — Add grouped bar chart with year selector

## Implementation Order

1. Backend models → Backend service → Frontend types → Frontend chart
2. Total: ~4 files changed, ~150 lines added

## Key Patterns to Follow

- **SQL**: Reuse existing bucketing CASE expression from `_get_deferral_distribution()`, parameterize by year
- **Models**: Follow `ContributionYearSummary` / `contribution_by_year` pattern
- **Charts**: Follow existing Recharts `BarChart` pattern in `DCPlanComparisonSection`
- **Colors**: Use `scenarioColors` prop already passed to `DCPlanComparisonSection`

## Testing

- Backend: Verify `deferral_distribution_by_year` field is populated with correct bucket counts per year
- Frontend: Verify grouped bar chart renders with correct colors, tooltips, and year switching
