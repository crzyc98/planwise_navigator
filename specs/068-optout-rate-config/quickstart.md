# Quickstart: Configurable Auto-Enrollment Opt-Out Rates

**Branch**: `068-optout-rate-config` | **Date**: 2026-03-10

## Overview

Expose the 8 hardcoded auto-enrollment opt-out rates (4 age-band, 4 income-band) as editable fields in PlanAlign Studio's DC Plan configuration panel. The dbt SQL layer already supports configurable rates via `{{ var() }}` — this feature threads values from the UI through the API and orchestrator.

## Architecture

```
Frontend (DCPlanSection.tsx)
  ├── types.ts          → Add 8 dcOptOutRate* fields to FormData
  ├── constants.ts      → Add defaults matching dbt_project.yml
  └── buildConfigPayload.ts → Map to dc_plan.opt_out_rate_* (% → decimal)

API (system.py)
  └── /config/defaults  → Add opt_out_rates to enrollment defaults

Orchestrator (export.py)
  └── _export_enrollment_vars() → Map dc_plan.opt_out_rate_* to dbt vars

dbt (int_enrollment_events.sql)
  └── Already uses {{ var('opt_out_rate_*') }} — NO CHANGES NEEDED
```

## Key Files to Modify

| File | Change |
|------|--------|
| `planalign_studio/components/config/types.ts` | Add 8 fields to FormData interface |
| `planalign_studio/components/config/constants.ts` | Add 8 defaults to DEFAULT_FORM_DATA |
| `planalign_studio/components/config/DCPlanSection.tsx` | Add collapsible "Opt-Out Assumptions" UI section |
| `planalign_studio/components/config/buildConfigPayload.ts` | Map 8 fields to dc_plan payload |
| `planalign_api/routers/system.py` | Add opt_out_rates to /config/defaults |
| `planalign_orchestrator/config/export.py` | Add 8 opt-out rate mappings in E095 dc_plan section |

## Key Design Decisions

1. **UI shows percentages** (35%), stores/transmits **decimals** (0.35)
2. **Defaults match `dbt_project.yml`**: young=0.35, mid=0.20, mature=0.15, senior=0.10
3. **Income rates are absolute** in UI (not multipliers), orchestrator passes directly to dbt
4. **No dbt changes needed** — the SQL already consumes these variables
5. **Backward compatible** — missing values fall back to dbt_project.yml defaults

## Development Order

1. Frontend types + constants (no visual yet)
2. buildConfigPayload mapping
3. API defaults endpoint
4. Orchestrator export mapping
5. DCPlanSection.tsx UI (collapsible section)
6. Integration test (set rates → run sim → verify enrollment)
