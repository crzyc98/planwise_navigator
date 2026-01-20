# Quickstart: Expand Scenario Comparison Limit

**Feature**: 019-expand-scenario-comparison
**Date**: 2026-01-20

## Prerequisites

- Node.js 18+ installed
- Access to the `planalign_studio/` directory
- Development environment set up per main README

## Quick Implementation Steps

### 1. Add MAX_SCENARIO_SELECTION Constant

**File**: `planalign_studio/constants.ts`

```typescript
// Add near the top with other constants
export const MAX_SCENARIO_SELECTION = 6;
```

### 2. Extend Color Palette

**File**: `planalign_studio/constants.ts`

```typescript
// Update COLORS.charts from 5 to 6 colors
export const COLORS = {
  primary: '#00853F',
  secondary: '#4CAF50',
  accent: '#FF9800',
  danger: '#F44336',
  charts: ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#E91E63']  // Added pink
};
```

### 3. Update Selection Limit in Component

**File**: `planalign_studio/components/ScenarioCostComparison.tsx`

```typescript
// Import the constant
import { COLORS, MAX_SCENARIO_SELECTION } from '../constants';

// Update the toggle function (around line 370)
} else {
  // Selecting - use constant instead of hardcoded 5
  if (prev.length < MAX_SCENARIO_SELECTION) {
    return [...prev, id];
  }
  return prev;
}
```

### 4. Add Disabled State with Tooltip

**File**: `planalign_studio/components/ScenarioCostComparison.tsx`

In the scenario list rendering section, add disabled state logic:

```typescript
const isAtLimit = selectedScenarioIds.length >= MAX_SCENARIO_SELECTION;
const isSelected = selectedScenarioIds.includes(scenario.id);
const isDisabled = isAtLimit && !isSelected;

// On the checkbox button
<button
  onClick={() => toggleSelection(scenario.id)}
  disabled={isDisabled}
  title={isDisabled ? `Maximum of ${MAX_SCENARIO_SELECTION} scenarios selected` : undefined}
  className={`... ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
>
```

## Verification Steps

1. Start the development server:
   ```bash
   cd planalign_studio
   npm run dev
   ```

2. Navigate to the Compare Costs page

3. Test scenarios:
   - Select 6 scenarios → all 6 should display in charts
   - Verify 6 distinct colors appear
   - With 6 selected, verify unchecked scenarios show disabled checkboxes
   - Hover over disabled checkbox → verify tooltip appears
   - Deselect one → verify checkboxes re-enable
   - Copy data → verify all 6 scenarios in clipboard

## Files Changed

| File | Change |
|------|--------|
| `planalign_studio/constants.ts` | Add `MAX_SCENARIO_SELECTION = 6`, extend color palette |
| `planalign_studio/components/ScenarioCostComparison.tsx` | Use constant, add disabled state with tooltip |

## Estimated Effort

- Implementation: ~30 minutes
- Testing: ~15 minutes
- Total: ~45 minutes
