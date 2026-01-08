# Research: Compare Variance Alignment & Copy Button

**Feature**: 015-compare-variance-copy
**Date**: 2026-01-08

## Research Tasks

### 1. Variance Row Alignment Issue

**Question**: Why does the variance row appear misaligned with other rows?

**Finding**: The `VarianceDisplay` component (lines 98-128 in `ScenarioCostComparison.tsx`) uses `inline-flex items-center` styling:
```tsx
<div className={`inline-flex items-center ${colorClass}`}>
  <Icon size={16} className="mr-1" />
  <span className="font-medium">...</span>
</div>
```

This creates a flex container that doesn't respect the `text-right` alignment of the parent `<td>`. The icon and text are grouped together as a unit, but the unit itself floats left within the cell.

**Decision**: Modify the `VarianceDisplay` component to use `justify-end` to push content to the right, matching the other rows' right-aligned values.

**Alternatives Considered**:
1. Remove the icon from variance display (rejected - reduces visual scanning utility)
2. Use absolute positioning (rejected - fragile across different table widths)
3. Apply `text-right` to the flex container with `justify-end` (chosen - clean, maintains existing structure)

---

### 2. Clipboard API Best Practices

**Question**: What is the standard approach for copy-to-clipboard in modern React?

**Finding**: The Clipboard API (`navigator.clipboard.writeText()`) is the modern standard:
- Supported in all target browsers (Chrome 66+, Firefox 63+, Safari 13.1+, Edge 79+)
- Returns a Promise for async handling
- Requires secure context (HTTPS or localhost)
- User-initiated action (button click) automatically grants permission

**Decision**: Use `navigator.clipboard.writeText()` with async/await. Wrap in a custom hook `useCopyToClipboard` for reusability and state management.

**Alternatives Considered**:
1. `document.execCommand('copy')` (rejected - deprecated, synchronous, requires text selection)
2. Third-party library like `clipboard.js` (rejected - adds dependency for trivial functionality)
3. Direct API call without hook (rejected - less reusable, harder to manage feedback state)

---

### 3. TSV Format for Excel Compatibility

**Question**: What format ensures proper paste into Excel?

**Finding**: Tab-Separated Values (TSV) is universally compatible:
- Columns separated by `\t` (tab character)
- Rows separated by `\n` (newline)
- No quoting needed for simple numeric/text values
- Works in Excel, Google Sheets, Numbers, LibreOffice Calc

**Decision**: Generate TSV string from table data. Include header row with "Scenario" and year columns. Include all three data rows (Baseline, Comparison, Variance).

**Example Output**:
```
Scenario	2025	2026	2027
Baseline	92.5%	93.1%	93.8%
Comparison	94.2%	94.8%	95.1%
Variance	+1.7% (+1.8%)	+1.7% (+1.8%)	+1.3% (+1.4%)
```

**Alternatives Considered**:
1. CSV format (rejected - commas in formatted numbers cause issues)
2. HTML table format (rejected - limited compatibility)
3. JSON format (rejected - not directly pasteable to spreadsheet cells)

---

### 4. Copy Button UX Pattern

**Question**: How should the copy button provide feedback?

**Finding**: Industry standard patterns:
- Icon-based button (clipboard icon) positioned near content
- State change on click: icon changes to checkmark for ~2 seconds
- Optional tooltip: "Copy to clipboard" on hover, "Copied!" after success
- Lucide-react provides `Copy` and `Check` icons

**Decision**: Add a small copy button (lucide `Copy` icon) in the table header next to the metric title. On click, change to `Check` icon with green color for 2 seconds, then revert.

**Alternatives Considered**:
1. Toast notification (rejected - too disruptive for small action)
2. Tooltip only (rejected - less discoverable than icon change)
3. Button with text label (rejected - clutters header, inconsistent with existing icon-only patterns)

---

### 5. Copy All Tables Feature

**Question**: How should "Copy All" work for multiple tables?

**Finding**: For bulk export, tables should be separated with blank lines and metric titles as section headers.

**Decision**: Add a "Copy All Tables" button in the Year-by-Year Breakdown section header. Each table is separated by two newlines with the metric title as a header.

**Example Output**:
```
Participation Rate
Scenario	2025	2026	2027
Baseline	92.5%	93.1%	93.8%
...

Avg Deferral Rate
Scenario	2025	2026	2027
...
```

---

## Summary

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Alignment Fix | Use `justify-end` on VarianceDisplay flex container | Maintains icon+text grouping while respecting right alignment |
| Clipboard API | `navigator.clipboard.writeText()` in custom hook | Modern, Promise-based, widely supported |
| Data Format | Tab-separated values (TSV) | Universal spreadsheet compatibility |
| Copy Feedback | Icon swap (Copy → Check) for 2 seconds | Non-intrusive, clear visual confirmation |
| Copy All | Section headers + blank line separators | Clean structure for multi-table export |

## No Outstanding NEEDS CLARIFICATION

All technical decisions resolved. Ready for Phase 1.
