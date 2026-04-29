# Research: Fix DC Plan Match UI for Tenure-Based and Points-Based Modes

## Root Cause Analysis: matchRate > 100% Stored as 2% Instead of 200%

### Decision: Fix load deserialization in ConfigContext.tsx only

**Rationale**: The save path (`buildConfigPayload.ts`) is already correct — it divides `matchRate` by 100 before sending to the API (e.g., 200 → 2.0). The bug is exclusively in the load path in `ConfigContext.tsx`, which uses a heuristic function `convertRateToPercent` that has a condition `if (value <= 1) return value * 100`.

When `match_rate` is stored as `2.0` (representing 200%), the condition `2.0 <= 1` is false, so it returns `2.0` as-is, displaying as `2` in the form instead of `200`.

**The fix**: Replace lines 149 and 156 in `ConfigContext.tsx`:
```
// BEFORE (broken for values > 1)
matchRate: convertRateToPercent(t.match_rate, 0)

// AFTER (consistent with deferral-based tiers at line 142)
matchRate: (t.match_rate ?? 0) * 100
```

**Alternatives considered**:
- Fix `convertRateToPercent` to not use the heuristic — rejected because the function is also used for `maxDeferralPct` and `contribution_rate` fields where values are always stored as decimals <= 1, and changing the function could break those.
- Change the save path to not divide by 100 — rejected because that would break the backend which expects `match_rate` as a decimal (0.0–2.0), and CopyScenarioModal/TemplateModal already correctly use `(t.match_rate ?? 0) * 100` for all tier types.

**Evidence**: `CopyScenarioModal.tsx` (lines 118, 126) and `TemplateModal.tsx` (lines 57, 65) already use the correct `(t.match_rate ?? 0) * 100` formula for tenure and points tiers — confirming the fix is the right approach.

---

## UI Redesign: Deferral Range Format for Tenure/Points Tiers

### Decision: Reorder fields in each tier row to put deferral range first, in `X% to X% deferrals → matchRate% match` format

**Rationale**: The deferral-based tier rows show `[deferralMin]% to [deferralMax]% deferrals → [matchRate]% match`. Tenure/points tier rows show `[minYears] to [maxYears] yrs → [matchRate]% match, max [maxDeferralPct]% def`, which buries the deferral cap at the end and uses a different reading order than deferral-based mode.

**Proposed new row format** (tenure-based):
```
[idx]. [minYears] to [maxYears] yrs | 0% to [maxDeferralPct]% deferrals → [matchRate]% match [delete]
```

The tenure range remains as the tier identifier (left side), and the deferral + match portion mirrors the deferral-based layout.

**Data model impact**: `TenureMatchTier` and `PointsMatchTier` types already have `maxDeferralPct`. A `minDeferralPct` field is not needed — the minimum always defaults to 0% (match applies to deferrals from 0 up to the cap). No type changes or API changes required.

**Alternatives considered**:
- Add a `minDeferralPct` field to support non-zero deferral minimums within a tier — deferred as scope creep; not part of the request and no plan designs require it.
- Remove the tenure/points range from the row and only show deferral info — rejected because the tenure/points range is the tier discriminator; removing it would make tiers indistinguishable.

---

## Scope Boundary

The following are **out of scope** for this feature:
- Auto-migration of existing saved scenarios with corrupted matchRate values (e.g., 2% stored when 200% was intended)
- Adding a `minDeferralPct` field to tenure/points tiers
- Changes to the backend API or dbt models
- Changes to how `maxDeferralPct` is handled (it serializes correctly)
