# Quickstart: Fix Target Compensation Growth Persistence

**Feature**: 064-fix-comp-growth-persist

## What This Fix Does

Adds persistence for the "Target Compensation Growth" slider value across sessions. Currently, the slider resets to 5.0% every time the Compensation section is loaded because the value is stored in local component state instead of the shared form data model.

## Files to Modify (in dependency order)

1. **`planalign_studio/components/config/types.ts`** — Add `targetCompensationGrowth: number` to `FormData` interface
2. **`planalign_studio/components/config/constants.ts`** — Add `targetCompensationGrowth: 5.0` to `DEFAULT_FORM_DATA`
3. **`planalign_studio/components/config/buildConfigPayload.ts`** — Add `target_compensation_growth_percent` to compensation payload
4. **`planalign_studio/components/config/ConfigContext.tsx`** — Hydrate field from scenario overrides + add dirty tracking
5. **`planalign_studio/components/config/CompensationSection.tsx`** — Replace `useState(5.0)` with `formData.targetCompensationGrowth`

## How to Test

1. Launch PlanAlign Studio: `planalign studio`
2. Open a workspace and scenario
3. Navigate to Compensation section
4. Set the Target Growth slider to 7.5%
5. Click "Calculate Settings" — verify derived rates change
6. Save the scenario
7. Navigate away, then return to Compensation section
8. Verify slider shows 7.5% (not 5.0%)
9. Click "Calculate Settings" — verify rates match 7.5%

## Backward Compatibility

Scenarios saved before this fix will load with a default of 5.0% — no errors, no migration needed.
