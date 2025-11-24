# Employee Identifier Strategy

## Overview

Fidelity PlanAlign Engine uses a dual-identifier approach for workforce management:
- **employee_id**: Primary unique identifier for all operations
- **employee_ssn**: Secondary identifier retained for compliance/reporting

## Identifier Patterns

### 1. Baseline Employees (Census Data)
- **Format**: `EMP_XXXXXX`
- **Example**: `EMP_000001`, `EMP_005234`
- **Source**: Initial census data load (year 2024)
- **Generation**: Sequential numbering with 6-digit zero-padding

### 2. New Hires (Simulation Generated)
- **Format**: `NH_YYYY_UUUUUUUU_XXXXXX`
- **Example**: `NH_2025_a1b2c3d4_000001`
- **Components**:
  - `NH_`: New Hire prefix
  - `YYYY`: Simulation year (e.g., 2025, 2026)
  - `UUUUUUUU`: First 8 characters of UUID for global uniqueness
  - `XXXXXX`: Sequential hire number within year (zero-padded)

## Key Design Decisions

### 1. Primary Key Strategy
- **employee_id** is the sole primary key across all tables
- Enforced uniqueness at the staging layer
- All foreign key relationships use employee_id

### 2. SSN Handling
- Retained for regulatory compliance and reporting
- NOT used as a unique constraint
- Can be shared across records (edge cases)
- Format: `SSN-XXXXXXXXX` for new hires

### 3. Deduplication Approach
- Raw census data may contain duplicates
- Deduplication logic in `stg_census_data`:
  - Keeps most recent hire date
  - Logs all duplicates to `stg_census_duplicates_audit`
  - Provides full audit trail

### 4. Global Uniqueness
- UUID component ensures no collisions across:
  - Multiple simulation runs
  - Different years
  - Parallel processing scenarios
- Year encoding provides temporal context
- Sequential numbering maintains readability

## Data Quality Monitoring

### Automated Checks
The `dq_employee_id_validation` model performs:
1. **Duplicate Detection**: IDs appearing multiple times
2. **Format Validation**: Compliance with expected patterns
3. **SSN Conflicts**: Multiple IDs sharing same SSN
4. **Cross-Year Validation**: Ensures no ID reuse

### Severity Levels
- **ERROR**: Critical issues that must be fixed (duplicates, SSN conflicts)
- **WARNING**: Format violations that may cause issues
- **INFO**: Legacy formats or deprecation notices

## Migration Notes

### From Legacy Systems
1. Original census uses `EMP_` prefix
2. Legacy new hires may use `NH_YYYY_XXXXXX` format (without UUID)
3. Both formats are supported but new hires always get UUID format

### Future Considerations
1. Consider migrating all IDs to UUID-based format
2. Implement employee_id regeneration utility for legacy records
3. Add support for external system ID mapping

## Best Practices

### For Developers
1. Always use employee_id for joins and lookups
2. Never assume SSN uniqueness
3. Check data quality reports before major operations
4. Use provided ID generation functions

### For Data Analysts
1. Filter by ID prefix to identify employee cohorts
2. Use year component in new hire IDs for temporal analysis
3. Consult audit tables for data lineage
4. Report any ID anomalies to data engineering team

## Example Queries

### Find all new hires for a specific year
```sql
SELECT *
FROM fct_workforce_snapshot
WHERE employee_id LIKE 'NH_2025_%'
```

### Check for duplicate IDs
```sql
SELECT *
FROM dq_employee_id_validation
WHERE check_type = 'DUPLICATE_IDS'
  AND severity = 'ERROR'
```

### Audit duplicate records
```sql
SELECT *
FROM stg_census_duplicates_audit
WHERE duplicate_count > 1
ORDER BY employee_id, occurrence_rank
```
