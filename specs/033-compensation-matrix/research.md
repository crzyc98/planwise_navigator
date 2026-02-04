# Research: Multi-Year Compensation Matrix

**Feature**: 033-compensation-matrix
**Date**: 2026-02-03

## Summary

This feature has no technical unknowns requiring research. All necessary data, patterns, and dependencies are already established in the codebase.

## Findings

### 1. Data Availability

**Decision**: Use existing `total_compensation` field from API response
**Rationale**: The `ContributionYearSummary` interface already includes `total_compensation` (line 807 of `api.ts`), populated by the backend DC Plan analytics endpoint.
**Alternatives Considered**: None - data is already available and typed.

### 2. Component Pattern

**Decision**: Mirror the existing Multi-Year Cost Matrix table structure exactly
**Rationale**: The cost matrix at lines 1039-1141 of `ScenarioCostComparison.tsx` provides a proven, tested pattern for displaying scenario comparison data in tabular form.
**Alternatives Considered**:
- Separate component file: Rejected because the table is tightly coupled to component state (`orderedScenarioIds`, `anchorAnalytics`, `years`, etc.)
- Different visual design: Rejected per FR-003/SC-004 requirements for visual consistency

### 3. Copy-to-Clipboard

**Decision**: Use existing `useCopyToClipboard` hook with separate state for compensation matrix
**Rationale**: The hook at `hooks/useCopyToClipboard.ts` already provides the exact functionality needed with visual feedback (checkmark icon, timed reset).
**Alternatives Considered**: Single copy button for both tables - Rejected because each table should be independently copyable.

### 4. Placement

**Decision**: Insert compensation matrix immediately after cost matrix, before methodology footer
**Rationale**: This maintains the logical flow: costs → compensation → methodology explanation.
**Alternatives Considered**: Side-by-side layout - Rejected due to horizontal space constraints with 6+ years of data.

## Unresolved Questions

None. All technical decisions are validated by existing patterns in the codebase.

## Next Steps

Proceed to Phase 1: Generate data-model.md and quickstart.md.
