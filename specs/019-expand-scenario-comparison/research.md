# Research: Expand Scenario Comparison Limit

**Feature**: 019-expand-scenario-comparison
**Date**: 2026-01-20

## Research Tasks

### 1. Color Palette for 6 Distinct Scenarios

**Context**: The current `COLORS.charts` array has 5 colors. We need 6 distinct, accessible colors for scenario differentiation in charts.

**Decision**: Extend the existing color palette with a 6th color that maintains visual distinction.

**Rationale**:
- The existing 5 colors are: `#0088FE` (blue), `#00C49F` (teal), `#FFBB28` (yellow/gold), `#FF8042` (orange), `#8884d8` (purple)
- A 6th color should have sufficient contrast with all existing colors
- Pink/magenta (`#E91E63` or `#EC407A`) provides strong contrast against the existing palette
- This follows standard data visualization best practices for categorical color scales

**Alternatives Considered**:
- Red (`#F44336`): Rejected - too close to orange `#FF8042` and may conflict with error states
- Green (`#4CAF50`): Rejected - too close to teal `#00C49F`
- Brown (`#795548`): Rejected - low saturation, hard to distinguish on charts
- Pink (`#E91E63`): Selected - distinct hue, good contrast, no conflict with existing colors

**Final Color Palette (6 colors)**:
```typescript
charts: ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#E91E63']
```

### 2. Checkbox Disable Pattern with Tooltip

**Context**: When 6 scenarios are selected, unchecked checkboxes should be disabled with a tooltip explaining the limit.

**Decision**: Use the `disabled` attribute on checkbox inputs with a `title` attribute for native tooltip.

**Rationale**:
- Native HTML `title` attribute provides tooltip without additional dependencies
- Disabled styling should use `opacity-50` and `cursor-not-allowed` for visual feedback
- The checkbox icon should change to indicate disabled state (gray color)
- This pattern is consistent with existing UI patterns in the codebase

**Implementation Pattern**:
```tsx
<button
  onClick={() => handleToggle(scenario.id)}
  disabled={isAtLimit && !selectedIds.includes(scenario.id)}
  title={isAtLimit && !selectedIds.includes(scenario.id)
    ? "Maximum of 6 scenarios selected"
    : undefined}
  className={isAtLimit && !selectedIds.includes(scenario.id)
    ? "opacity-50 cursor-not-allowed"
    : ""}
>
  {/* checkbox icon */}
</button>
```

**Alternatives Considered**:
- Custom tooltip component: Rejected - adds complexity; native tooltip is sufficient
- Toast notification on click: Rejected - spec clarification chose disabled state over toast
- Modal dialog: Rejected - overly intrusive for a simple limit

### 3. Selection Limit Constant

**Context**: The current limit of 5 is hardcoded at line 370 in `ScenarioCostComparison.tsx`.

**Decision**: Extract to a named constant `MAX_SCENARIO_SELECTION = 6` for maintainability.

**Rationale**:
- Named constant is self-documenting
- Single location for future limit adjustments
- Can be placed in `constants.ts` alongside other configuration values

**Alternatives Considered**:
- Keep inline magic number: Rejected - harder to maintain and understand
- Environment variable: Rejected - overkill for a UI constant
- Component prop: Rejected - no current use case for variable limits per instance

### 4. Backend API Compatibility

**Context**: The `compareDCPlanAnalytics` API is called with selected scenario IDs.

**Decision**: No backend changes required.

**Rationale**:
- Reviewed `/workspace/planalign_studio/services/api.ts`
- The API accepts an array of scenario IDs with no hardcoded limit
- Adding a 6th ID will be handled without modification

**Verification**: Manual testing will confirm API handles 6 scenarios correctly.

## Summary

| Research Item | Decision | Risk Level |
|---------------|----------|------------|
| Color Palette | Add `#E91E63` (pink) as 6th color | Low |
| Checkbox Disable | Native `disabled` + `title` tooltip | Low |
| Limit Constant | `MAX_SCENARIO_SELECTION = 6` in constants.ts | Low |
| Backend API | No changes required | Low |

**All NEEDS CLARIFICATION items resolved.** Ready for Phase 1.
