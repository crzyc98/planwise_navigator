# Research: Salary Range Configuration UX Improvements

**Feature**: 044-fix-salary-range-ux
**Date**: 2026-02-10

## R1: React Number Input — onBlur vs onChange Pattern

**Decision**: Use onBlur commit pattern with local string state

**Rationale**: The current implementation uses controlled inputs where `value={row.minComp}` (a number) is bound directly, and `onChange` immediately calls `parseFloat(value) || 0`. This causes two problems:
1. Empty strings during editing produce `NaN` → fallback to `0`, snapping the field
2. Every keystroke triggers a full `setFormData` state update, causing unnecessary re-renders of the entire form

The onBlur pattern separates "editing state" (local string) from "committed state" (formData number). The input displays the local string during editing, and only commits the parsed number when the user finishes editing (blur or Enter key).

**Alternatives considered**:
- **Debounced onChange**: Delays commit by ~300ms. Rejected because it still parses intermediate values and creates a confusing "delayed reaction" feel.
- **Uncontrolled inputs with refs**: Would work but breaks React's controlled component pattern used throughout the component. Higher refactoring risk.
- **Third-party library (react-number-format)**: Adds unnecessary dependency for a simple fix.

## R2: Input Width for Large Salary Values

**Decision**: Use `w-36` (144px) Tailwind class

**Rationale**: The current `w-28` (112px) can display ~6 digits comfortably with the `text-right` alignment and padding. For values like $500,000+ (6 digits), the text clips. `w-36` (144px) provides enough room for 6-digit values with dollar formatting potential and padding. Testing: "$999,999" in a `text-sm` font needs approximately 130px with padding.

**Alternatives considered**:
- **w-32** (128px): Marginal improvement, still tight for 6-digit values with padding.
- **w-40** (160px): Too wide, wastes table space for the common 5-digit case.
- **Auto-sizing**: Overly complex for this use case; would require measuring text width dynamically.

## R3: Step Size for Arrow Key Increments

**Decision**: Change from `step="1000"` to `step="500"`

**Rationale**: A $1,000 step is too coarse for fine-tuning salary ranges. A $500 step provides a good balance between speed (not too many clicks to traverse a range) and precision (meaningful increments for salary planning). Most salary ranges span $20K-$200K, so $500 steps require 40-400 presses to traverse — reasonable for arrow key use.

**Alternatives considered**:
- **step="100"**: Too fine; would require many clicks to make meaningful changes.
- **Remove step entirely** (default step=1): Far too fine for salary values; arrow keys would be useless.
- **step="250"**: Unusual increment that doesn't align with typical salary rounding.

## R4: Min > Max Validation Display Pattern

**Decision**: Red border on both inputs + small warning text below the row

**Rationale**: Inline visual feedback needs to be immediately noticeable without blocking the user's editing flow. A red border on the affected inputs (using Tailwind's `border-red-500`) plus a small `text-xs text-red-600` message "Min exceeds max" below the row provides clear feedback. This is non-blocking — the user can still save and continue editing.

**Alternatives considered**:
- **Tooltip on hover**: Too hidden; user might not hover over the field.
- **Toast/alert**: Too intrusive for a non-blocking validation.
- **Red background**: Too aggressive; border change is sufficient visual signal.
- **Blocking save**: Rejected per spec assumption — validation is advisory, not blocking.

## R5: CompensationInput Helper Component vs Inline Logic

**Decision**: Create a small `CompensationInput` component inline within ConfigStudio.tsx

**Rationale**: The onBlur pattern requires local state (the editable string). Rather than duplicating this logic for both min and max inputs across all rows, a small helper component encapsulates:
- `localValue: string` state
- Focus/blur/keydown handlers
- Validation styling (receives `hasError: boolean` prop)

Defined at the top of ConfigStudio.tsx (or just before the return statement) as a function component. No separate file needed — this is a 20-line helper specific to this component.

**Alternatives considered**:
- **Separate file**: Overkill for a 20-line helper used only in one place.
- **useRef per input**: Would require managing refs for each cell, more complex than local component state.
- **Custom hook**: Possible but a component is simpler since it also manages rendering.
