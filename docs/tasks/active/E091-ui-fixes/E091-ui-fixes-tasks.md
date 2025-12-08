# E091 Task Checklist

**Last Updated**: 2025-12-08
**Status**: In Progress

## Tasks

- [x] Create feature branch `feature/E091-ui-year-range-compensation-fixes`
- [x] Create task documentation in `docs/tasks/active/E091-ui-fixes/`
- [x] Add year range debug logging
- [x] Fix compensation query to use `prorated_annual_compensation`
- [x] Investigate year range persistence issue
- [ ] Test 2025-2026 simulation
- [ ] Verify compensation calculation matches snapshot
- [ ] Update task status upon completion

## Progress Notes

### 2025-12-08
- Created feature branch
- Created task documentation
- Identified root cause: `simulation_service.py:707` uses `current_compensation` instead of `prorated_annual_compensation`
- Fixed compensation query to use `prorated_annual_compensation`
- Added E091 debug logging to:
  - `planalign_api/routers/simulations.py` (lines 110-115)
  - `planalign_api/services/simulation_service.py` (lines 235-241)
  - `planalign_api/storage/workspace_storage.py` (lines 414-422)
- Debug logging will trace year range from config merge through to CLI execution
- User should run a 2025-2026 simulation and check server logs for E091 messages to identify where year range is lost
