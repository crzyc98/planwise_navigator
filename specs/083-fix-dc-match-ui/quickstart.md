# Quickstart: Fix DC Plan Match UI for Tenure-Based and Points-Based Modes

## What changed

Two issues are fixed in this feature — both are frontend-only changes:

1. **matchRate bug**: Entering a match rate above 100% (e.g., 200) in tenure-based or points-based tiers saved correctly but loaded back as 2% instead of 200%. Root cause: wrong deserialization in `ConfigContext.tsx`.

2. **UI layout**: Tenure-based and points-based tier rows now show the deferral range in the same `X% to X% deferrals → matchRate% match` format used by deferral-based tiers, instead of the old "matchRate% match, max X% def" format.

## Files to change

| File | Change |
|------|--------|
| `planalign_studio/components/config/ConfigContext.tsx` | Lines 149, 156: replace `convertRateToPercent(t.match_rate, 0)` with `(t.match_rate ?? 0) * 100` |
| `planalign_studio/components/config/DCPlanSection.tsx` | Reorder tenure tier row (lines ~210–257) and points tier row (lines ~305–354) to show deferral range before match rate |

## Testing

1. Launch PlanAlign Studio: `planalign studio`
2. Open a workspace, open a scenario, go to DC Plan configuration
3. Switch match mode to **Tenure-Based**
4. Add a tier, enter `200` in the match rate field, enter `6` in the deferral cap field
5. Save and reopen — confirm match rate shows `200`, not `2`
6. Confirm tier row reads `0% to 6% deferrals → 200% match`
7. Repeat for **Points-Based** mode
8. Switch to **Deferral-Based** — confirm no regressions in that mode

## No backend changes

No dbt models, Python orchestrator code, or API models need to change.
