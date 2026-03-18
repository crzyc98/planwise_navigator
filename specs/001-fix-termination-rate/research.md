# Phase 0 Research: Termination Rate Suggestion Bug

**Feature**: Fix termination rate always showing 100%
**Date**: 2026-03-18
**Status**: Research Plan (to be executed by implementation team)

## Research Objectives

Identify the root cause of the 100% termination rate suggestion and evaluate fix approaches.

## Areas of Investigation

### 1. Current Implementation Location

**Objective**: Locate the termination rate suggestion code

**Research Tasks**:
- [ ] Find the suggestion endpoint in `planalign_api/routers/` that returns termination rate
- [ ] Identify the service layer method in `planalign_api/services/` or `planalign_orchestrator/`
- [ ] Check if calculation is in Python service or dbt SQL model
- [ ] Trace the data flow from census data to suggestion response

**Success Criteria**: Can identify the exact file(s) and functions responsible for termination rate calculation

### 2. Current Calculation Logic & Root Cause

**Objective**: Understand existing implementation and identify the bug

**Research Tasks**:
- [ ] Extract the current termination rate calculation formula
- [ ] Identify all variables used (numerator, denominator, filters)
- [ ] Check for division-by-zero handling or try/except blocks that might fallback to 100%
- [ ] Verify denominator calculation (is it using active employees or something else?)
- [ ] Look for hardcoded "100" or percentage defaults in fallback cases
- [ ] Check for filter conditions that might return empty active employee lists
- [ ] Review recent commits or PRs related to termination rate changes

**Success Criteria**: Can articulate the specific bug (e.g., "division by zero returns 100" or "filter returns no active employees, causing 100% default")

### 3. Census Data Schema & Available Fields

**Objective**: Understand what data is available for calculation

**Research Tasks**:
- [ ] Document census data schema in `dbt/seeds/` or staging models
- [ ] Identify fields: employee_id, status, termination_date, hire_date, employment_status
- [ ] Check if terminated employee count is directly available or must be calculated
- [ ] Verify active employee count definition (status='ACTIVE', not terminated, etc.)
- [ ] Check for date filtering requirements (year-based, period-based)
- [ ] Look for any data quality issues that might cause empty result sets

**Success Criteria**: Can confirm all necessary fields are available to calculate (terminated count / active count)

### 4. Existing Test Patterns & Test Data

**Objective**: Understand how to test the fix

**Research Tasks**:
- [ ] Check `tests/fixtures/workforce_data.py` for sample employee data with terminations
- [ ] Find existing suggestion endpoint tests in `tests/test_*.py`
- [ ] Verify if there are test census files with known termination rates
- [ ] Check `tests/fixtures/database.py` for in-memory database setup
- [ ] Identify how to create test scenarios with various termination rates (0%, 5%, 50%, etc.)
- [ ] Look for integration tests that validate suggestion accuracy

**Success Criteria**: Can create test cases covering normal scenarios and edge cases with predictable outcomes

### 5. Edge Case Handling

**Objective**: Understand requirements for edge cases

**Research Tasks**:
- [ ] Check current error handling for empty census data
- [ ] Verify behavior when active employee count is zero (division by zero)
- [ ] Test with single employee scenario
- [ ] Check handling of null/missing termination data
- [ ] Review error message patterns (should return message instead of 100%)
- [ ] Look for any rate-smoothing or confidence interval logic

**Success Criteria**: Understand current behavior and what needs to change for proper edge case handling

## Findings & Decisions

*[To be filled by implementation team during Phase 0]*

### Decision: Root Cause
**Finding**: [Specific bug identified and location]
**Rationale**: [Evidence from code review]
**Alternatives Considered**: [Other possible causes ruled out]

### Decision: Calculation Formula
**Finding**: [Confirmed formula: (terminated employees / active employees) × 100%]
**Rationale**: [Matches business requirements in spec]
**Alternatives Considered**: [Other formulas evaluated]

### Decision: Data Availability
**Finding**: [Confirmed all necessary fields available in census/models]
**Rationale**: [Sources identified: seeds, staging models, etc.]
**Alternatives Considered**: [Workarounds if data unavailable]

### Decision: Testing Approach
**Finding**: [Use pytest fixtures with E075 patterns]
**Rationale**: [Consistent with project standards]
**Alternatives Considered**: [Manual testing vs. automated]

## Implementation Path (High-Level)

1. **Fix the calculation** in the identified service/endpoint
   - Replace hardcoded 100% or broken logic with correct formula
   - Add proper denominator handling (active employees)
   - Add zero-denominator checks with informative error messages

2. **Add comprehensive tests** following E075 patterns
   - Unit tests for calculation logic
   - Integration tests with sample census data
   - Edge case tests (zero denominator, empty data, single employee)

3. **Verify fixes** against success criteria
   - All test census files return realistic rates
   - Rates vary appropriately across different datasets
   - Edge cases return messages instead of 100%

## Research Status

- [ ] Investigation complete
- [ ] Root cause identified
- [ ] All unknowns resolved
- [ ] Ready for Phase 1 design

**Next Steps**: Complete Phase 1 (data-model.md, contracts, quickstart.md) based on research findings.
