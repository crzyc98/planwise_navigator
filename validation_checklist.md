# Workforce Snapshot Architecture Validation Checklist

## Phase 1: Contract Verification
- [ ] Run `dbt build --select fct_workforce_snapshot --full-refresh` to verify schema contracts
- [ ] Execute `dbt test --select fct_workforce_snapshot` to validate all contract tests pass
- [ ] Compare column names, data types, and constraints against original schema
- [ ] Verify all required columns are present with correct naming

## Phase 2: Dependency Smoke Tests
- [ ] Test SCD snapshots: `dbt build --select scd_workforce_state_optimized+ --vars '{"simulation_year":2025}'`
- [ ] Test mart models: `dbt build --select fct_compensation_growth fct_policy_optimization --vars '{"simulation_year":2025}'`
- [ ] Test monitoring models: `dbt build --select mon_pipeline_performance mon_data_quality --vars '{"simulation_year":2025}'`
- [ ] Test circular dependency models: `dbt build --select int_active_employees_prev_year_snapshot+ --vars '{"simulation_year":2026}'`

## Phase 3: Integration Testing
- [ ] Run full integration test suite: `pytest tests/integration/test_simulation_behavior_comparison.py -v`
- [ ] Execute multi-year simulation tests: `pytest tests/integration/test_multi_year_cold_start.py -v`
- [ ] Validate SCD data consistency: `pytest tests/integration/test_scd_data_consistency.py -v`
- [ ] Run compensation workflow tests: `pytest tests/test_compensation_workflow_integration.py -v`

## Phase 4: Behavior Validation
- [ ] Generate baseline data from original implementation (if available)
- [ ] Generate comparison data from refactored implementation
- [ ] Perform row-level comparison using SQL EXCEPT operations
- [ ] Validate employee counts, compensation totals, and event distributions

## Phase 5: Performance Validation
- [ ] Capture runtime metrics using `mon_pipeline_performance` model
- [ ] Compare execution times against previous baselines
- [ ] Verify incremental strategy still works efficiently
- [ ] Check memory usage and query performance

## Phase 6: Documentation Updates
- [ ] Update architecture documentation to reflect new intermediate models
- [ ] Regenerate DAG diagrams showing new model dependencies
- [ ] Document any performance changes or optimization recommendations
- [ ] Update developer guides with new model structure
