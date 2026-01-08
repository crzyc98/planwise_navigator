# Quickstart: Compare Variance Alignment & Copy Button

**Feature**: 015-compare-variance-copy
**Date**: 2026-01-08

## Prerequisites

- Node.js 18+ installed
- PlanAlign Studio frontend development environment set up
- Access to the `planalign_studio/` directory

## Development Setup

```bash
# Navigate to frontend directory
cd planalign_studio

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev

# Open http://localhost:5173 in browser
# Navigate to Compare page with completed scenarios
```

## Key Files to Modify

| File | Purpose |
|------|---------|
| `planalign_studio/components/ScenarioCostComparison.tsx` | Main component containing MetricTable and VarianceDisplay |
| `planalign_studio/hooks/useCopyToClipboard.ts` | New hook for clipboard operations (create this) |

## Implementation Steps (Summary)

### Step 1: Fix Variance Alignment

Modify the `VarianceDisplay` component (lines 120-127):

```tsx
// Before
<div className={`inline-flex items-center ${colorClass}`}>

// After
<div className={`inline-flex items-center justify-end ${colorClass}`}>
```

### Step 2: Create useCopyToClipboard Hook

Create `planalign_studio/hooks/useCopyToClipboard.ts`:

```typescript
import { useState, useCallback } from 'react';

export function useCopyToClipboard(resetDelay = 2000) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = useCallback(async (text: string): Promise<boolean> => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setError(null);
      setTimeout(() => setCopied(false), resetDelay);
      return true;
    } catch (err) {
      setError('Clipboard access denied');
      setCopied(false);
      return false;
    }
  }, [resetDelay]);

  return { copy, copied, error };
}
```

### Step 3: Add Copy Button to MetricTable

Add `Copy` and `Check` icons from lucide-react, add copy button next to title in header.

### Step 4: Implement tableToTSV Utility

Add utility function to convert table data to tab-separated values format.

### Step 5: Add Copy All Button

Add button in the Year-by-Year Breakdown section header.

## Testing Checklist

- [ ] Variance row values align with year columns (visual check)
- [ ] Copy button appears in each table header
- [ ] Clicking copy changes icon to checkmark for 2 seconds
- [ ] Paste into Excel shows correct columns/rows
- [ ] Copy All exports all 6 tables with headers
- [ ] Copy disabled when no data loaded
- [ ] Error shown if clipboard access denied

## Verification Commands

```bash
# Build to check for TypeScript errors
cd planalign_studio
npm run build

# Lint check
npm run lint
```

## Common Issues

| Issue | Solution |
|-------|----------|
| Clipboard API not available | Ensure running on localhost or HTTPS |
| Copy not working in Safari | Ensure button click triggers copy (user-initiated) |
| TSV pasting incorrectly | Check for extra spaces or missing tabs |
