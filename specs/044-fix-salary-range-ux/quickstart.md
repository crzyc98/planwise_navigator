# Quickstart: Salary Range Configuration UX Improvements

**Feature**: 044-fix-salary-range-ux
**Date**: 2026-02-10

## Overview

Three localized changes to `planalign_studio/components/ConfigStudio.tsx`:

1. **Line 347**: Change scale factor default from `1.0` to `1.5`
2. **Lines 350-357**: Refactor input commit pattern (onChange → onBlur)
3. **Lines 2446-2466**: Widen inputs, reduce step, add min > max validation

## Prerequisites

```bash
# Ensure you're on the feature branch
git checkout 044-fix-salary-range-ux

# No dependency changes needed — frontend-only
```

## Implementation Steps

### Step 1: Change Scale Factor Default

In `ConfigStudio.tsx` line 347, change:
```typescript
const [compScaleFactor, setCompScaleFactor] = useState<number>(1.0);
```
to:
```typescript
const [compScaleFactor, setCompScaleFactor] = useState<number>(1.5);
```

### Step 2: Create CompensationInput Helper

Add a small helper component before the main ConfigStudio component (or at the top of the file after imports). This encapsulates the onBlur commit pattern:

```typescript
function CompensationInput({ value, onCommit, hasError, step = 500, min = 0 }: {
  value: number;
  onCommit: (v: number) => void;
  hasError?: boolean;
  step?: number;
  min?: number;
}) {
  const [localValue, setLocalValue] = useState(String(value));

  useEffect(() => {
    // Sync when parent value changes externally (e.g., Match Census)
    setLocalValue(String(value));
  }, [value]);

  const commit = () => {
    const parsed = parseFloat(localValue) || 0;
    const clamped = Math.max(parsed, min);
    onCommit(clamped);
    setLocalValue(String(clamped));
  };

  return (
    <input
      type="number"
      step={step}
      min={min}
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') commit(); }}
      className={`w-36 shadow-sm sm:text-sm rounded-md p-1 border text-right focus:ring-fidelity-green focus:border-fidelity-green ${
        hasError ? 'border-red-500' : 'border-gray-300'
      }`}
    />
  );
}
```

### Step 3: Replace Inline Inputs with CompensationInput

Replace the existing min/max `<input>` elements in the table (lines 2446-2466) with:

```tsx
{formData.jobLevelCompensation.map((row, idx) => {
  const hasRangeError = row.minComp > row.maxComp && row.minComp > 0 && row.maxComp > 0;
  return (
    <tr key={row.level}>
      <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.level}</td>
      <td className="px-4 py-2 text-sm text-gray-700">{row.name}</td>
      <td className="px-4 py-2">
        <CompensationInput
          value={row.minComp}
          onCommit={(v) => handleJobLevelCompChange(idx, 'minComp', String(v))}
          hasError={hasRangeError}
        />
      </td>
      <td className="px-4 py-2">
        <CompensationInput
          value={row.maxComp}
          onCommit={(v) => handleJobLevelCompChange(idx, 'maxComp', String(v))}
          hasError={hasRangeError}
        />
      </td>
      {hasRangeError && (
        <td className="px-2 py-2">
          <span className="text-xs text-red-600">Min exceeds max</span>
        </td>
      )}
    </tr>
  );
})}
```

**Note**: The `handleJobLevelCompChange` handler still receives a string and parses it. Since `onCommit` passes a pre-parsed number, the `String(v)` conversion ensures backward compatibility with the existing handler signature.

### Step 4: Verify

1. Launch PlanAlign Studio: `planalign studio`
2. Open a workspace and navigate to the compensation configuration
3. Verify:
   - Scale factor shows 1.5 by default
   - Salary inputs allow natural editing (delete, retype) without snapping
   - Large values ($500,000+) display fully without clipping
   - Arrow keys increment by $500
   - Setting min > max shows red borders and warning text
   - Match Census still works correctly with the new default
   - Saving configuration still persists values correctly
