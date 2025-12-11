# E100: Copy Scenario Data Sources Fix

## Problem
The "Copy from Scenario" button was not copying the Data Sources tab configuration (census file path).

## Root Cause
The copy scenario modal was missing the `censusDataPath` and `censusDataStatus` field mappings that were present in the scenario load logic.

## Solution
Added data sources field mappings to the copy scenario modal:
- `censusDataPath` from `cfg.data_sources?.census_parquet_path`
- `censusDataStatus` set to 'validating' when path exists
- Added census file validation after copy to populate row count and metadata

## Files Changed
- `planalign_studio/components/ConfigStudio.tsx` - Added data sources fields to copy scenario modal

## Testing
- Frontend build passes with no TypeScript errors
- Manual testing: Copy from scenario should now carry forward census file path
