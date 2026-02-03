# Research: Vesting Hours Requirement Toggle

**Feature**: 030-vesting-hours-toggle
**Date**: 2026-01-29

## Summary

No significant unknowns identified. All technical decisions are pre-determined by existing codebase patterns.

## Decisions

### 1. Backend API Support

**Decision**: Use existing `VestingScheduleConfig` fields
**Rationale**: Backend already supports `require_hours_credit` (boolean) and `hours_threshold` (int, 0-2080) in `planalign_api/models/vesting.py:38-52`
**Alternatives considered**: None - API is already complete

### 2. TypeScript Types

**Decision**: Use existing `VestingScheduleConfig` interface
**Rationale**: Types already defined in `planalign_studio/services/api.ts:1033-1038` with optional `require_hours_credit?: boolean` and `hours_threshold?: number`
**Alternatives considered**: None - types are already complete

### 3. UI Control Pattern

**Decision**: Checkbox toggle + conditional number input
**Rationale**:
- Matches existing component patterns in VestingAnalysis.tsx
- Checkbox is appropriate for boolean toggle (require_hours_credit)
- Number input with min/max validation for hours_threshold
- Conditional rendering when toggle is enabled
**Alternatives considered**:
- Switch component (rejected: not used elsewhere in codebase)
- Tooltip-only (rejected: need actual input control)

### 4. State Management

**Decision**: Extend existing `currentSchedule` and `proposedSchedule` state
**Rationale**: Current state already uses `VestingScheduleConfig | null` type which supports the optional fields
**Alternatives considered**:
- Separate state variables (rejected: more complex, unnecessary)

### 5. Results Display Location

**Decision**: Add hours requirement info to the Scenario Info Banner
**Rationale**:
- Banner already displays schedule names and analysis metadata
- Natural place to show "Hours Requirement: 1,000 hrs" or similar
- Keeps results section clean
**Alternatives considered**:
- KPI card (rejected: not a primary metric)
- New section (rejected: over-engineering)

### 6. Explanatory Text

**Decision**: Inline help text below toggle
**Rationale**: Small gray text immediately below the checkbox explaining impact
**Alternatives considered**:
- Tooltip (rejected: requires hover, less discoverable)
- Modal (rejected: disrupts workflow)

## Validation

All decisions align with:
- Existing VestingAnalysis.tsx patterns (~650 lines)
- Constitution Principle II (modular, single component change)
- Constitution Principle V (type-safe, using existing TypeScript interfaces)

## Next Steps

Proceed to Phase 1: Design & Contracts (data-model.md, quickstart.md)
