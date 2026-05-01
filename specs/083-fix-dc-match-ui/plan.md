# Implementation Plan: Fix DC Plan Match UI for Tenure-Based and Points-Based Modes

**Branch**: `083-fix-dc-match-ui` | **Date**: 2026-04-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/083-fix-dc-match-ui/spec.md`

## Summary

Two frontend-only bugs in the DC Plan Configure page's tenure-based and points-based match tier editors:

1. **Load deserialization bug**: `ConfigContext.tsx` uses `convertRateToPercent()` (which has a `value <= 1` heuristic) for `match_rate` on tenure/points tiers. This means a stored value of `2.0` (representing 200%) is returned as `2` instead of `200`. Fix: replace with `(t.match_rate ?? 0) * 100`, consistent with deferral-based tiers and with CopyScenarioModal/TemplateModal which already use this pattern.

2. **UI layout inconsistency**: Tenure-based and points-based tier rows show `matchRate% match, max X% def` format, while deferral-based rows show `X% to X% deferrals → matchRate% match`. Redesign tenure/points rows to lead with the deferral range in the same format.

No backend, API, or dbt changes required.

## Technical Context

**Language/Version**: TypeScript (React 18 / Vite frontend)
**Primary Dependencies**: React 18, Tailwind CSS v4
**Storage**: N/A (UI-only changes; scenario config persisted via existing API)
**Testing**: Manual browser testing via `planalign studio`
**Target Platform**: Web browser (PlanAlign Studio frontend)
**Project Type**: Web application (React/Vite frontend)
**Performance Goals**: Standard interactive UI response (<100ms for form updates)
**Constraints**: No backend changes; no data migration; no type interface changes
**Scale/Scope**: 2 files changed, ~10 lines total

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | UI-only change; no event store modifications |
| II. Modular Architecture | ✅ Pass | Changes confined to existing modules; no new files needed |
| III. Test-First Development | ✅ Pass | Manual UI testing sufficient for a 2-line bug fix + cosmetic reorder |
| IV. Enterprise Transparency | ✅ Pass | No audit or logging changes required |
| V. Type-Safe Configuration | ✅ Pass | No TypeScript type changes; existing `TenureMatchTier`/`PointsMatchTier` interfaces are correct |
| VI. Performance & Scalability | ✅ Pass | Cosmetic changes only; no performance impact |

No gate violations.

## Project Structure

### Documentation (this feature)

```text
specs/083-fix-dc-match-ui/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Root cause analysis
├── data-model.md        # Entity reference (no schema changes)
├── quickstart.md        # Testing guide
└── checklists/
    └── requirements.md  # Quality checklist (all pass)
```

### Source Code (files to change)

```text
planalign_studio/components/config/
├── ConfigContext.tsx     # Fix: lines 149, 156 — load deserialization bug
└── DCPlanSection.tsx     # Fix: ~lines 210-257 (tenure) and ~305-354 (points) — UI row layout
```

## Implementation Steps

### Step 1: Fix matchRate deserialization bug (ConfigContext.tsx)

**File**: `planalign_studio/components/config/ConfigContext.tsx`

Change lines 149 and 156 from:
```typescript
matchRate: convertRateToPercent(t.match_rate, 0),
```
To:
```typescript
matchRate: (t.match_rate ?? 0) * 100,
```

This makes tenure/points tier load consistent with:
- Deferral-based tiers (line 142): already uses `(t.match_rate ?? 0) * 100`
- CopyScenarioModal.tsx (lines 118, 126): already uses `(t.match_rate ?? 0) * 100`
- TemplateModal.tsx (lines 57, 65): already uses `(t.match_rate ?? 0) * 100`

### Step 2: Redesign tenure-based tier row layout (DCPlanSection.tsx)

**File**: `planalign_studio/components/config/DCPlanSection.tsx`, lines ~210–257

**Before** (current row reading order):
```
[idx]. [minYears] to [maxYears] yrs → [matchRate]% match, max [maxDeferralPct]% def
```

**After** (new row reading order):
```
[idx]. [minYears] to [maxYears] yrs | 0% to [maxDeferralPct]% deferrals → [matchRate]% match
```

Specifically:
- Keep the years range inputs (`minYears`, `maxYears`) as the tier identifier on the left
- Add a visual separator (pipe or label)
- Show `0%` as a static label for the deferral minimum (no new field needed)
- Move `maxDeferralPct` input to appear after `0% to` and before `% deferrals →`
- Move `matchRate` input to appear after `% deferrals →` and before `% match`
- Remove the old `% match, max` and `% def` labels

### Step 3: Redesign points-based tier row layout (DCPlanSection.tsx)

**File**: `planalign_studio/components/config/DCPlanSection.tsx`, lines ~305–354

Same pattern as Step 2 but for points tiers:

**Before**:
```
[idx]. [minPoints] to [maxPoints] pts → [matchRate]% match, max [maxDeferralPct]% def
```

**After**:
```
[idx]. [minPoints] to [maxPoints] pts | 0% to [maxDeferralPct]% deferrals → [matchRate]% match
```

### Step 4: Manual verification

1. `planalign studio` → open a scenario → DC Plan config
2. Switch to Tenure-Based → add tier → enter `200` match rate, `6` deferral cap → save → reopen → confirm `200` persists
3. Confirm row displays `0% to 6% deferrals → 200% match`
4. Repeat for Points-Based mode
5. Switch to Deferral-Based — confirm no regressions
