# E089: Context & Key Files

## Key Files

| File | Purpose |
|------|---------|
| `planalign_studio/components/ConfigStudio.tsx` | Main config studio component with the bug |
| `planalign_api/storage/workspace_storage.py` | Backend storage (works correctly) |
| `planalign_api/routers/scenarios.py` | Scenario API (works correctly) |

## Key Decisions

1. **Remove `censusDataPath` from workspace useEffect** - Census path is scenario-specific, not workspace-level
2. **Add auto-save on upload** - Automatically persist census path after successful upload

## Line References

- Line 667: BUG - workspace useEffect overwrites scenario census path
- Line 531: GOOD - scenario useEffect correctly loads census path
- Lines 1248-1277: File upload handler (needs auto-save addition)

Last Updated: 2025-12-08
