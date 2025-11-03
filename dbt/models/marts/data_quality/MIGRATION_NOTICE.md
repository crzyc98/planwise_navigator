# Data Quality Models Migration Notice

**Phase 1A of E079: Convert Validation Models to dbt Tests**

The following validation models have been converted to dbt tests in `dbt/tests/data_quality/`:

## Migrated Models

1. **dq_employee_contributions_validation** → `test_employee_contributions_validation.sql`
2. **dq_employee_id_validation** → `test_employee_id_format.sql`
3. **dq_new_hire_termination_match_validation** → `test_new_hire_termination_match.sql`

## Running the Tests

Instead of building validation models, run tests on-demand:

```bash
# Run all data quality tests
cd dbt && dbt test --select tag:data_quality

# Run specific test
dbt test --select test_employee_contributions_validation

# Run tests for a specific year
dbt test --select tag:data_quality --vars "simulation_year: 2025"
```

## Benefits

- **Performance**: Tests only run on-demand, not on every build
- **Speed**: Reduced build time by ~195 seconds (39 models eliminated from build)
- **Clarity**: Tests are clearly separated from data models
- **Flexibility**: Run tests selectively during development

## Schema File Updates Needed

The schema.yml file still contains references to deleted models. These will show warnings until cleaned up.
To remove warnings, delete the model definitions from:
- `models/marts/data_quality/schema.yml` (lines for deleted models)
- `models/analysis/schema.yml` (validate_enrollment_architecture reference)
