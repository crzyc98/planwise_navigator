# filename: docs/migration_mapping.md

# Legacy to PlanWise Navigator Data Mapping

## Overview
This document maps legacy system fields to the new PlanWise Navigator schema.

## Employee Master Data Mapping

| Legacy Field | Legacy Type | New Field | New Type | Transformation | Notes |
|--------------|-------------|-----------|----------|----------------|-------|
| EMP_ID | VARCHAR(10) | employee_id | VARCHAR | Direct copy | Primary key |
| FNAME | VARCHAR(50) | first_name | VARCHAR | Trim whitespace | PII field |
| LNAME | VARCHAR(50) | last_name | VARCHAR | Trim whitespace | PII field |
| EMAIL_ADDR | VARCHAR(100) | email | VARCHAR | Lowercase, validate | PII field |
| JOB_LEVEL | CHAR(2) | level_id | INTEGER | Map: 'L1'→1, 'L2'→2, etc. | See level mapping |
| DEPT_CODE | VARCHAR(10) | department | VARCHAR | Lookup from DEPT table | Denormalized |
| LOC_CODE | VARCHAR(5) | location | VARCHAR | Map via location table | |
| BIRTH_DATE | DATE | age | INTEGER | Calculate from birth date | Remove PII |
| HIRE_DATE | DATE | hire_date | DATE | Direct copy | |
| YEARS_SERVICE | DECIMAL(5,2) | tenure_years | DECIMAL | Recalculate from hire_date | |
| BASE_SALARY | DECIMAL(10,2) | current_compensation | DECIMAL | Include bonuses | |
| BONUS_AMT | DECIMAL(10,2) | - | - | Add to current_compensation | |
| STATUS | CHAR(1) | active_flag | BOOLEAN | 'A'→true, else false | |
| TERM_DATE | DATE | termination_date | DATE | Direct copy if not null | |
| PERF_RATING | INTEGER | performance_rating | INTEGER | Direct copy | Validate 1-5 |
| MGR_ID | VARCHAR(10) | manager_id | VARCHAR | Direct copy | Optional field |

## Job Level Mapping

| Legacy Code | Legacy Description | New level_id | New level_name |
|-------------|-------------------|--------------|----------------|
| L1 | Associate | 1 | Entry Level |
| L2 | Senior Associate | 2 | Experienced |
| L3 | Manager | 3 | Senior |
| L4 | Senior Manager | 4 | Lead/Principal |
| L5 | Director | 5 | Executive |
| L6 | VP | 5 | Executive |
| L7+ | SVP/EVP | 5 | Executive |

## Department Mapping

| Legacy DEPT_CODE | Legacy Name | New department |
|------------------|-------------|----------------|
| ENG | Engineering | Engineering |
| SALES | Sales & Marketing | Sales |
| MKT | Sales & Marketing | Marketing |
| OPS | Operations | Operations |
| FIN | Finance & Accounting | Finance |
| HR | Human Resources | HR |
| IT | Information Technology | Engineering |
| LEGAL | Legal & Compliance | Operations |

## Hazard Table Mapping

| Legacy Table | Legacy Fields | New Model | Transformation |
|--------------|---------------|-----------|----------------|
| PROMO_RATES | LEVEL, AGE_BAND, RATE | config_promotion_hazard_* | Split into base + multipliers |
| TERM_RATES | LEVEL, TENURE_BAND, RATE | config_termination_hazard_* | Split into base + multipliers |
| MERIT_MATRIX | LEVEL, PERF, INCREASE_PCT | config_raises_hazard | Direct mapping |

## Migration Queries

```sql
-- Employee migration query
INSERT INTO stg_census_data
SELECT 
    EMP_ID as employee_id,
    FNAME as first_name,
    LNAME as last_name,
    LOWER(EMAIL_ADDR) as email,
    CASE 
        WHEN JOB_LEVEL = 'L1' THEN 1
        WHEN JOB_LEVEL = 'L2' THEN 2
        WHEN JOB_LEVEL = 'L3' THEN 3
        WHEN JOB_LEVEL = 'L4' THEN 4
        WHEN JOB_LEVEL IN ('L5', 'L6', 'L7', 'L8') THEN 5
        ELSE 1  -- Default to entry level
    END as level_id,
    d.DEPT_NAME as department,
    l.LOC_NAME as location,
    DATE_DIFF('year', BIRTH_DATE, CURRENT_DATE) as age,
    DATE_DIFF('year', HIRE_DATE, CURRENT_DATE) as tenure_years,
    HIRE_DATE as hire_date,
    BASE_SALARY + COALESCE(BONUS_AMT, 0) as current_compensation,
    PERF_RATING as performance_rating,
    CASE WHEN STATUS = 'A' THEN true ELSE false END as active_flag,
    TERM_DATE as termination_date
FROM LEGACY.EMPLOYEE e
LEFT JOIN LEGACY.DEPARTMENT d ON e.DEPT_CODE = d.DEPT_CODE
LEFT JOIN LEGACY.LOCATION l ON e.LOC_CODE = l.LOC_CODE
WHERE e.HIRE_DATE >= '2020-01-01';  -- Only recent employees