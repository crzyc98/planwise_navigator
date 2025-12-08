# E088: Remove Hardcoded Impact Preview Section

**Issue**: [#74](https://github.com/crzyc98/planwise_navigator/issues/74)
**Approach**: Option B - Remove the section until fully implemented

## Problem

The Impact Preview section in `ConfigStudio.tsx` displays hardcoded values:
- "Projected Headcount: 1,061" (static)
- "Turnover Cost: $2.4M" (static)

These values don't update when users change scenario parameters, which is misleading.

## Solution

Remove the entire Impact Preview `<div>` block from `ConfigStudio.tsx`.

## Files to Modify

| File | Change |
|------|--------|
| `planalign_studio/components/ConfigStudio.tsx` | Remove Impact Preview div (~lines 1193-1215) |

## Complexity

**Low** - Single file, ~23 lines to delete, no logic changes.
