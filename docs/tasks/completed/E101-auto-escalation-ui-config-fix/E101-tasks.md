# E101: Task Checklist

## Last Updated
2024-12-11

## Tasks

### Implementation
- [x] Swap export order in `to_dbt_vars()` (export.py lines 657-658)
- [x] Add comment explaining priority order

### Testing
- [x] Verified fix with functional test (UI 2026-01-01 overrides legacy 2020-01-01)
- [x] Run existing tests to ensure no regressions (112 unit tests pass)

### Validation
- [ ] Manual test: Run 3 scenarios with different dcEscalationHireDateCutoff values
- [ ] Verify different escalation counts in results

### Completion
- [ ] Create PR
- [ ] Move task folder to completed/
- [ ] Update docs/tasks/tasks.md
