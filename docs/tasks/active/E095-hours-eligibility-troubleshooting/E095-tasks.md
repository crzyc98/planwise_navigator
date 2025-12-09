# E095: Task Checklist

Last Updated: 2025-12-09

## Tasks

- [x] Create `dbt/models/analysis/debug_hours_eligibility.sql`
  - [x] Employee hours base CTE
  - [x] Hours calculation breakdown CTE
  - [x] Summary statistics CTE
  - [x] Hours bucket distribution CTE
  - [x] Config validation CTE
  - [x] Final UNION ALL output

- [x] Update `dbt/models/analysis/schema.yml`
  - [x] Add model description
  - [x] Add column descriptions
  - [x] Add basic tests

- [x] Test the model
  - [x] Run dbt build
  - [x] Verify SUMMARY output
  - [x] Verify HOURS_BUCKET output
  - [x] Verify DETAIL output with edge cases

- [ ] Update tasks.md
  - [ ] Add E095 to Active Tasks
