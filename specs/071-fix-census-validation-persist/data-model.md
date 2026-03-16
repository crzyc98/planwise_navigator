# Data Model: Fix Census Validation Warning Persistence

## No Data Model Changes

This is a frontend-only bug fix. No database schema, event types, or persistent data models are affected.

## Transient State Model (Frontend)

The following React component state is relevant to this fix:

### Upload State (DataSourcesSection)

| Field | Type | Description |
|-------|------|-------------|
| `uploadStatus` | `'idle' \| 'uploading' \| 'success' \| 'error'` | Current upload lifecycle phase |
| `uploadMessage` | `string` | Status message displayed to user |
| `structuredWarnings` | `StructuredWarning[]` | Field-level validation findings (missing columns, aliases) |
| `dataQualityWarnings` | `DataQualityWarning[]` | Row-level validation findings (nulls, bad dates, negative values) |
| `dqExpanded` | `boolean` | Whether the data quality section is expanded |
| `expandedFields` | `Set<string>` | Which fields have their detail sections expanded |

### State Transitions

```
idle → uploading: User selects file (warnings MUST clear)
uploading → success: Upload completes (new warnings populate)
uploading → error: Upload fails (warnings cleared, error shown)
success → uploading: User selects another file (warnings MUST clear)
```

### Key Constraint

The HTML file input's `.value` property MUST be reset after each upload completes, so that re-selecting the same filename triggers the `onChange` event.
