# E099: Context

## Key Files
- `planalign_studio/components/ConfigStudio.tsx:2870-2990` - Copy scenario modal logic (fixed)
- `planalign_studio/components/ConfigStudio.tsx:500-650` - Scenario load logic (reference)

## Decision Log
- **2025-12-11**: Fixed copy scenario modal to include all E084 fields that were added to scenario load but missing from copy functionality

## Field Mapping Locations
1. **Scenario Load** (lines 500-650): Full field mapping when loading a scenario
2. **Workspace Load** (lines 690-780): Partial field mapping from workspace base_config
3. **Copy Scenario** (lines 2870-2990): Should mirror scenario load - NOW FIXED
