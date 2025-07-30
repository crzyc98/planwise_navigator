# Story S022-02: Basic Employee Classification Rules (Epic E026)

## Story Overview

### Summary
Implement simple employee classification rules to exclude specific employee types (interns, contractors) from DC plan eligibility. This story has been moved from Epic E022 to Epic E026 to focus the E022 MVP on simple days-based eligibility only.

**Epic**: E026 - Advanced Eligibility Features
**Dependencies**: Epic E022 (Simple Eligibility Engine) must be completed first

### Business Value
- Ensures compliance with plan document exclusions
- Prevents ineligible employees from receiving plan benefits
- Reduces administrative errors and corrections

### Post-MVP Acceptance Criteria
- Exclude employees by employee_type field (intern, contractor)
- Use SQL boolean logic for performance
- Configuration via dbt variables
- Clear audit trail showing exclusion reason
- Process exclusions in single pass with other eligibility checks
- Generate exclusion events for comprehensive audit trail

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
**Enhanced to generate exclusion events for audit compliance.**

The classification logic is integrated into `int_eligibility_determination.sql` alongside other eligibility checks for maximum performance. The enhanced approach:

1. **Validates data quality** first (null/empty employee_type)
2. **Applies case-insensitive exclusions** for robustness
3. **Tracks specific exclusion reasons** for audit trail
4. **Generates EXCLUSION events** for excluded employees
5. **Flags problematic records** for manual review
6. **Combines with other eligibility checks** in single pass

```python
def generate_exclusion_events(self, simulation_year: int) -> List[Dict]:
    """Generate EXCLUSION events for employees excluded by classification rules"""

    query = f"""
    SELECT
        employee_id,
        classification_reason,
        employee_type
    FROM int_eligibility_determination
    WHERE simulation_year = {simulation_year}
    AND is_classification_eligible = false
    AND classification_reason LIKE 'excluded:%'
    """

    excluded_df = self.duckdb_conn.execute(query).df()

    events = []
    for _, row in excluded_df.iterrows():
        event = {
            "event_type": "EXCLUSION",
            "employee_id": row['employee_id'],
            "simulation_year": simulation_year,
            "event_date": f"{simulation_year}-01-01",
            "event_payload": {
                "exclusion_type": "employee_classification",
                "exclusion_reason": row['classification_reason'],
                "employee_type": row['employee_type'],
                "plan_participation_status": "excluded"
            }
        }
        events.append(event)

    return events
```

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

## Story Points: 5 (Post-MVP)

### Effort Breakdown
- Classification logic: 2 points
- Configuration integration: 1 point
- Testing: 1 point
- Documentation: 1 point

**Note**: This story has been moved to post-MVP phase to focus MVP on simple days-based eligibility only.

## Dependencies
- **Epic E022**: Simple Eligibility Engine (must be completed first)
- S022-01 (Core Eligibility Calculator) - provides foundation
- Employee data model with employee_type field
- dbt variables configuration infrastructure
- orchestrator_mvp multi-year simulation framework

## Related Epic
This story is part of **Epic E026: Advanced Eligibility Features**. See `/docs/epics/E026_advanced_eligibility_features.md` for the complete advanced eligibility roadmap.

## Definition of Done
- [ ] Classification rules exclude specified employee types
- [ ] Boolean masking implementation verified for performance
- [ ] Configuration changes work without code modifications
- [ ] Exclusion reasons properly tracked
- [ ] EXCLUSION events generated for excluded employees
- [ ] Event payload matches SimulationEvent schema
- [ ] Unit tests cover all exclusion scenarios
- [ ] Integration test with full eligibility engine
