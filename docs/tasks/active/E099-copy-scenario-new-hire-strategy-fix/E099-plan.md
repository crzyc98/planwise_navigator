# E099: Copy Scenario New Hire Strategy Fix

## Problem
The "Copy from Scenario" button in the ConfigStudio UI was not carrying forward several configuration fields, including:
- New hire strategy page settings
- DC Plan auto-enrollment hire date cutoff
- DC Plan core contribution eligibility fields
- DC Plan auto-escalation advanced settings

## Root Cause
The copy scenario modal (around line 2870-2972) was missing several field mappings that were present in the scenario load logic (around line 500-650). This was likely an oversight when new E084 fields were added - they were added to the load logic but not to the copy scenario modal.

## Solution
Added all missing field mappings to the copy scenario modal to match the scenario load logic:

### DC Plan - Auto-Enrollment Advanced (E084)
- `dcAutoEnrollWindowDays`
- `dcAutoEnrollOptOutGracePeriod`
- `dcAutoEnrollScope`
- `dcAutoEnrollHireDateCutoff`

### DC Plan - Core Eligibility (E084)
- `dcCoreMinTenureYears`
- `dcCoreRequireYearEndActive`
- `dcCoreMinHoursAnnual`
- `dcCoreAllowTerminatedNewHires`
- `dcCoreAllowExperiencedTerminations`

### DC Plan - Auto-Escalation Advanced (E084)
- `dcEscalationEffectiveDay`
- `dcEscalationDelayYears`
- `dcEscalationHireDateCutoff`

## Files Changed
- `planalign_studio/components/ConfigStudio.tsx` - Added missing field mappings to copy scenario modal

## Testing
- Frontend build passes with no TypeScript errors
- Manual testing: Copy from scenario should now carry forward all DC Plan and New Hire Strategy settings
