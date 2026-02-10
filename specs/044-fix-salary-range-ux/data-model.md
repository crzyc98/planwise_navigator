# Data Model: Salary Range Configuration UX Improvements

**Feature**: 044-fix-salary-range-ux
**Date**: 2026-02-10

## Entities

This feature modifies no persistent data models. All changes are to React component state.

### JobLevelCompensationRow (existing — no changes)

Represents a single row in the job level compensation table.

| Field | Type | Description |
| ----- | ---- | ----------- |
| level | number | Job level identifier (1-5) |
| name | string | Level name (e.g., "Staff", "Manager") |
| minComp | number | Minimum compensation for this level |
| maxComp | number | Maximum compensation for this level |

**Lifecycle**: Created from defaults on component mount, or loaded from API when a workspace/scenario is selected. Updated via user input or Match Census. Persisted to API on save.

### CompensationInput Props (new — helper component)

| Prop | Type | Description |
| ---- | ---- | ----------- |
| value | number | The committed numeric value from formData |
| onCommit | (value: number) => void | Callback to commit the final parsed value |
| hasError | boolean | Whether to show red border (min > max condition) |
| step | number | Arrow key step size (default: 500) |
| min | number | Minimum allowed value (default: 0) |

### CompensationInput Internal State

| State | Type | Description |
| ----- | ---- | ----------- |
| localValue | string | The editable string displayed during editing |
| isFocused | boolean | Whether the input currently has focus (implicit via onFocus/onBlur) |

**State transitions**:
1. **Mount / value prop changes (while not focused)**: `localValue` = `String(value)`
2. **Focus**: No change (localValue already set)
3. **Keystroke**: `localValue` = user's typed string (no parsing)
4. **Blur / Enter**: Parse `localValue` → `parseFloat(localValue) || 0` → call `onCommit(parsed)` → `localValue` = `String(parsed)`

## Validation Rules

| Rule | Condition | Display |
| ---- | --------- | ------- |
| Min > Max | `row.minComp > row.maxComp && row.minComp > 0 && row.maxComp > 0` | Red border on both inputs + "Min exceeds max" text |
| Scale factor bounds | `compScaleFactor < 0.5 || compScaleFactor > 3.0` | Input rejects value (existing behavior) |

**Note**: The `minComp > 0 && maxComp > 0` guard prevents false positives when one field is still at the default 0 during initial entry.
