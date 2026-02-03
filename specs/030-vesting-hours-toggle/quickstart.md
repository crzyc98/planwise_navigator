# Quickstart: Vesting Hours Requirement Toggle

**Feature**: 030-vesting-hours-toggle
**Date**: 2026-01-29

## Prerequisites

- Node.js installed (for frontend development)
- PlanAlign Studio running (`planalign studio`)
- At least one workspace with a completed simulation

## Development Setup

```bash
# Navigate to frontend directory
cd planalign_studio

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev
```

## File to Modify

**Single file change**: `planalign_studio/components/VestingAnalysis.tsx`

## Implementation Steps

### Step 1: Update handleScheduleChange function (line ~233)

Currently creates config without hours fields. Update to preserve existing hours settings when changing schedule type:

```typescript
const handleScheduleChange = (type: 'current' | 'proposed', scheduleType: string) => {
  const schedule = schedules.find(s => s.schedule_type === scheduleType);
  if (schedule) {
    const existingConfig = type === 'current' ? currentSchedule : proposedSchedule;
    const config: VestingScheduleConfig = {
      schedule_type: schedule.schedule_type,
      name: schedule.name,
      // Preserve hours settings when switching schedule types (FR-008)
      require_hours_credit: existingConfig?.require_hours_credit ?? false,
      hours_threshold: existingConfig?.hours_threshold ?? 1000,
    };
    if (type === 'current') {
      setCurrentSchedule(config);
    } else {
      setProposedSchedule(config);
    }
  }
};
```

### Step 2: Add hours toggle handler

```typescript
const handleHoursToggle = (type: 'current' | 'proposed', enabled: boolean) => {
  const setter = type === 'current' ? setCurrentSchedule : setProposedSchedule;
  const current = type === 'current' ? currentSchedule : proposedSchedule;
  if (current) {
    setter({
      ...current,
      require_hours_credit: enabled,
      hours_threshold: enabled ? (current.hours_threshold ?? 1000) : undefined,
    });
  }
};

const handleHoursThresholdChange = (type: 'current' | 'proposed', value: number) => {
  const setter = type === 'current' ? setCurrentSchedule : setProposedSchedule;
  const current = type === 'current' ? currentSchedule : proposedSchedule;
  if (current) {
    setter({
      ...current,
      hours_threshold: Math.min(2080, Math.max(0, value)),
    });
  }
};
```

### Step 3: Add UI controls below each schedule selector

After each schedule `<select>` element, add:

```tsx
{/* Hours Requirement Toggle */}
<div className="mt-2">
  <label className="flex items-center text-sm text-gray-600">
    <input
      type="checkbox"
      checked={currentSchedule?.require_hours_credit ?? false}
      onChange={(e) => handleHoursToggle('current', e.target.checked)}
      className="mr-2 rounded border-gray-300 text-fidelity-green focus:ring-fidelity-green"
    />
    Require 1,000 hours
  </label>
  {currentSchedule?.require_hours_credit && (
    <div className="mt-1 flex items-center gap-2">
      <input
        type="number"
        min={0}
        max={2080}
        value={currentSchedule.hours_threshold ?? 1000}
        onChange={(e) => handleHoursThresholdChange('current', parseInt(e.target.value) || 0)}
        className="w-20 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-fidelity-green focus:border-fidelity-green"
      />
      <span className="text-xs text-gray-500">hours/year</span>
    </div>
  )}
  <p className="text-xs text-gray-400 mt-1">
    Employees below threshold lose 1 year vesting credit
  </p>
</div>
```

### Step 4: Display hours config in results

Update the Scenario Info Banner to show hours settings when enabled:

```tsx
<div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
  <div className="flex items-center justify-between">
    <div>
      <h3 className="font-semibold text-blue-900">{analysisResult.scenario_name}</h3>
      <p className="text-sm text-blue-700">
        Total Employer Contributions: {formatCurrency(analysisResult.summary.total_employer_contributions)}
      </p>
    </div>
    <div className="text-right text-sm text-blue-600">
      <p>Analysis Year: {analysisResult.summary.analysis_year}</p>
    </div>
  </div>
  {/* Hours Requirement Display (FR-006) */}
  {(analysisResult.current_schedule.require_hours_credit ||
    analysisResult.proposed_schedule.require_hours_credit) && (
    <div className="mt-2 pt-2 border-t border-blue-200 text-xs text-blue-600">
      <span className="font-medium">Hours Requirement:</span>
      {analysisResult.current_schedule.require_hours_credit && (
        <span className="ml-2">
          Current: {analysisResult.current_schedule.hours_threshold ?? 1000} hrs
        </span>
      )}
      {analysisResult.proposed_schedule.require_hours_credit && (
        <span className="ml-2">
          Proposed: {analysisResult.proposed_schedule.hours_threshold ?? 1000} hrs
        </span>
      )}
    </div>
  )}
</div>
```

## Testing

1. Start PlanAlign Studio: `planalign studio`
2. Navigate to Vesting Analysis page
3. Verify toggle appears below each schedule selector
4. Toggle on → threshold input appears with default 1000
5. Change threshold → verify value updates
6. Toggle off → threshold input hides
7. Click Analyze → verify request includes hours fields (browser DevTools)
8. Check results banner shows hours settings when enabled
9. Change schedule type → verify hours settings preserved (FR-008)

## Acceptance Criteria Verification

| Requirement | How to Test |
|-------------|-------------|
| FR-001: Toggle for each schedule | Visual: checkbox visible below each selector |
| FR-002: Threshold input when enabled | Toggle on → input appears with 1000 default |
| FR-003: Hidden when disabled | Toggle off → input not visible |
| FR-004: Validate 0-2080 | Try entering -1 or 3000 → should clamp |
| FR-005: API includes fields | DevTools Network → check request payload |
| FR-006: Results show config | Run analysis → check banner shows hours |
| FR-007: Explanatory text | Look for gray text below toggle |
| FR-008: Preserve on schedule change | Toggle on → change schedule → still on |
