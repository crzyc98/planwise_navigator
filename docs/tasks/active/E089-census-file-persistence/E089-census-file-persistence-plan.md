# E089: Census File Upload Persistence Fix

## Issue Summary
**GitHub Issue:** #80 - Uploaded census file not persisted after navigating away from Simulation Config page

**Problem:** Census path is correctly saved to backend, but upon returning to the page, the old/default path is displayed. Even clicking "Save Config" doesn't fix this.

## Root Cause Analysis

### The Real Bug: React useEffect Race Condition

The data **IS being saved correctly** to `scenario.json`. The bug is in how ConfigStudio.tsx loads the data back:

**Two competing useEffects both set `censusDataPath`:**

1. **Scenario useEffect** (lines 496-657, dep: `[scenarioId, activeWorkspace?.id]`)
   - Loads `config_overrides.data_sources.census_parquet_path` from scenario
   - This correctly reads the saved census path

2. **Workspace useEffect** (lines 659-756, dep: `[activeWorkspace?.base_config]`)
   - Loads from `base_config.data_sources.census_parquet_path`
   - Workspace `base_config` does NOT have a `data_sources` section
   - Falls back to `prev.censusDataPath` (the default value)
   - **This fires AFTER scenario load and overwrites the correct value**

### The Overwrite at Line 667:
```tsx
censusDataPath: cfg.data_sources?.census_parquet_path || prev.censusDataPath
```
- `cfg` is `activeWorkspace.base_config` which has no `data_sources`
- `cfg.data_sources` is `undefined`
- Falls back to `prev.censusDataPath` which is the default: `'data/census_preprocessed.parquet'`

## Solution

1. Remove the `censusDataPath` line from the workspace useEffect entirely
2. Add auto-save on upload for better UX

## Files Modified
- `planalign_studio/components/ConfigStudio.tsx`
