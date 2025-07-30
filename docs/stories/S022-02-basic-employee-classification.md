# Story S022-02: Basic Employee Classification Rules (MVP)

## Story Overview

### Summary
Implement simple employee classification rules to exclude specific employee types (interns, contractors) from DC plan eligibility. This MVP version uses basic employee_type field matching with boolean masking for efficient filtering.

### Business Value
- Ensures compliance with plan document exclusions
- Prevents ineligible employees from receiving plan benefits
- Reduces administrative errors and corrections

### Acceptance Criteria
- ✅ Exclude employees by employee_type field (intern, contractor)
- ✅ Use vectorized boolean masking for performance
- ✅ Configuration via YAML without code changes
- ✅ Clear audit trail showing exclusion reason
- ✅ Process exclusions in single pass with other eligibility checks

## Technical Specifications

### Configuration Schema
```yaml
# config/eligibility_rules.yaml
eligibility:
  excluded_employee_types:
    - intern
    - contractor
    - seasonal

  # MVP: Simple type-based exclusions only
  # Post-MVP: location, division, union status
```

### Implementation Pattern (Updated)
**Key Changes**: Add data quality checks, specific exclusion reasons, handle case sensitivity.

```sql
-- Integrated into int_eligibility_determination.sql
WITH classification_checks AS (
    SELECT
        *,
        -- Data quality checks
        CASE
            WHEN employee_type IS NULL OR trim(employee_type) = '' THEN 'DATA_QUALITY_ISSUE'
            WHEN lower(trim(employee_type)) NOT IN ('regular', 'intern', 'contractor', 'seasonal', 'temp') THEN 'UNKNOWN_EMPLOYEE_TYPE'
            ELSE 'VALID_TYPE'
        END as type_validation,

        -- Classification eligibility (case-insensitive)
        lower(trim(employee_type)) NOT IN ('intern', 'contractor', 'seasonal') as is_classification_eligible,

        -- Specific exclusion reason tracking
        CASE
            WHEN employee_type IS NULL OR trim(employee_type) = '' THEN 'missing_employee_type'
            WHEN lower(trim(employee_type)) = 'intern' THEN 'excluded:intern'
            WHEN lower(trim(employee_type)) = 'contractor' THEN 'excluded:contractor'
            WHEN lower(trim(employee_type)) = 'seasonal' THEN 'excluded:seasonal'
            WHEN lower(trim(employee_type)) NOT IN ('regular', 'intern', 'contractor', 'seasonal', 'temp') THEN 'unknown_type:' || employee_type
            ELSE 'classification_eligible'
        END as classification_reason

    FROM employees
)

SELECT
    *,
    -- Flag data quality issues for review
    CASE
        WHEN type_validation != 'VALID_TYPE' THEN true
        ELSE false
    END as requires_manual_review

FROM classification_checks
```

### Data Quality Checks Added
```python
def validate_employee_classification(self, conn) -> Dict[str, int]:
    """Run data quality checks on employee classification"""

    validation_query = """
    SELECT
        type_validation,
        COUNT(*) as employee_count
    FROM int_eligibility_determination
    GROUP BY type_validation
    """

    results = conn.execute(validation_query).fetchall()
    validation_summary = dict(results)

    # Log warnings for data quality issues
    if validation_summary.get('DATA_QUALITY_ISSUE', 0) > 0:
        print(f"WARNING: {validation_summary['DATA_QUALITY_ISSUE']} employees have missing/empty employee_type")

    if validation_summary.get('UNKNOWN_EMPLOYEE_TYPE', 0) > 0:
        print(f"WARNING: {validation_summary['UNKNOWN_EMPLOYEE_TYPE']} employees have unexpected employee_type values")

    return validation_summary
```

### Integration with Eligibility Engine (Updated)
**Now handled directly in the SQL model - no separate integration needed.**

The classification logic is integrated into `int_eligibility_determination.sql` alongside other eligibility checks for maximum performance. The SQL approach:

1. **Validates data quality** first (null/empty employee_type)
2. **Applies case-insensitive exclusions** for robustness
3. **Tracks specific exclusion reasons** for audit trail
4. **Flags problematic records** for manual review
5. **Combines with other eligibility checks** in single pass

## MVP Simplifications

### Included in MVP
- Employee type exclusions (intern, contractor, seasonal)
- Simple string matching on employee_type field
- YAML configuration for excluded types
- Clear exclusion reason tracking

### Deferred to Post-MVP
- Location-based exclusions
- Division/department exclusions
- Union status exclusions
- Complex multi-field exclusion logic
- Effective dating of exclusion rules
- Statutory exclusions (non-resident aliens)

## Test Scenarios

1. **Intern Exclusion**: Verify interns are excluded regardless of age/service
2. **Contractor Exclusion**: Verify contractors are excluded
3. **Regular Employee**: Verify non-excluded types proceed to other checks
4. **Mixed Population**: Test performance with 20% excluded employees
5. **Configuration Change**: Add/remove excluded types via YAML

## Performance Considerations

- Boolean masking is O(n) operation
- Single pass through DataFrame
- No row-by-row operations
- Exclusions checked first to minimize subsequent calculations

## Story Points: 5

### Effort Breakdown
- Classification logic: 2 points
- Configuration integration: 1 point
- Testing: 1 point
- Documentation: 1 point

## Dependencies
- S022-01 (Core Eligibility Calculator)
- Employee data model with employee_type field
- YAML configuration infrastructure

## Definition of Done
- [ ] Classification rules exclude specified employee types
- [ ] Boolean masking implementation verified for performance
- [ ] Configuration changes work without code modifications
- [ ] Exclusion reasons properly tracked
- [ ] Unit tests cover all exclusion scenarios
- [ ] Integration test with full eligibility engine
