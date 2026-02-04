# Quickstart: Multi-Year Compensation Matrix

**Feature**: 033-compensation-matrix
**Date**: 2026-02-03

## Prerequisites

- Node.js 18+ installed
- PlanAlign Studio frontend dependencies installed
- At least one workspace with 2+ completed scenarios

## Development Setup

```bash
# Navigate to frontend directory
cd planalign_studio

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev
```

Frontend will be available at `http://localhost:5173`

## Testing the Feature

### Manual Test Steps

1. **Launch PlanAlign Studio**
   ```bash
   planalign studio
   ```

2. **Navigate to Compare Cost Page**
   - Open a workspace with completed scenarios
   - Click "Compare" in the navigation

3. **Select Scenarios**
   - In the sidebar, select 2+ completed scenarios
   - Set one as the anchor (baseline)

4. **Verify Compensation Matrix**
   - Scroll below the "Multi-Year Cost Matrix" table
   - Verify "Multi-Year Compensation Matrix" table appears
   - Check that:
     - Each scenario shows compensation values by year
     - Anchor row has blue highlighting
     - Variance column shows delta from anchor
     - Total column shows sum across all years

5. **Test Copy Functionality**
   - Click the copy button in the compensation matrix header
   - Verify checkmark icon appears briefly
   - Paste into a spreadsheet to verify tab-separated format

### Expected Behavior

| Test Case | Expected Result |
|-----------|-----------------|
| 2 scenarios selected | Both appear in compensation matrix |
| 6 scenarios selected | All 6 appear; horizontal scroll if needed |
| 1 scenario selected | Variance column shows "--" |
| Missing year data | Cell displays "-" |
| Copy to clipboard | TSV format pastes correctly in Excel |

## File to Modify

```
planalign_studio/components/ScenarioCostComparison.tsx
```

Key locations:
- Line 185: Add second `useCopyToClipboard` hook instance
- Line 571-607: Add parallel `compensationTableToTSV()` function
- Line 1141: Insert compensation matrix table JSX after cost matrix

## Validation Checklist

- [ ] Compensation matrix appears below cost matrix
- [ ] Same visual styling as cost matrix
- [ ] Anchor scenario highlighted in blue
- [ ] Variance shows orange (positive) or green (negative) badges
- [ ] Copy button works independently from cost matrix
- [ ] No TypeScript compilation errors
- [ ] No console errors in browser
