# Epic E045: Data Integrity Issues Resolution

**Epic Points**: 18
**Priority**: CRITICAL
**Duration**: 2 Sprints
**Status**: 🔴 Not Started
**Last Updated**: August 18, 2025

## Epic Story

**As a** platform architect
**I want** to resolve the 3 critical data integrity issues blocking production deployment
**So that** we can ensure accurate simulation results and regulatory compliance

## Business Context

Analysis of the current PlanWise Navigator database revealed **3 critical data integrity issues** that make the system unsuitable for production use. These issues affect 606+ employees and represent potential compliance violations and incorrect financial calculations totaling millions of dollars.

This epic addresses the specific, identified production-blocking issues rather than theoretical problems. Each issue has been analyzed with concrete evidence and requires surgical fixes to maintain data consistency.

## Critical Issues Identified (Production Analysis)

### Issue 1: Duplicate RAISE Events (606 employees affected)
- **Evidence**: 606 employees have exactly 2 identical RAISE events with same date (2026-07-15), compensation amounts, and event details
- **Impact**: Artificial salary inflation, incorrect compensation calculations
- **Root Cause**: Race condition or duplicate processing in `int_merit_events.sql`
- **Example**: Employee EMP_2024_000311 has duplicate RAISE events across multiple years

### Issue 2: Post-Termination Events (2 employees affected)
- **Evidence**:
  - Employee NH_2028_000737: Terminated 2029-02-03, received RAISE event 2029-07-15
  - Employee EMP_2024_002471: Terminated 2029-02-07, received RAISE event 2029-07-15
- **Impact**: Contributions calculated on post-termination compensation, causing contributions > actual compensation
- **Root Cause**: Merit events generated without termination date validation
- **Compliance Risk**: IRS 402(g) and 415(c) limit violations

### Issue 3: Enrollment Architecture Problem (3,773 employees affected)
- **Evidence**: 3,773 employees (81% of enrolled) have enrollment events but NULL enrollment dates in workforce snapshots
- **Impact**: Enrollment status inconsistency, contribution calculation errors
- **Root Cause**: Circular dependency in enrollment state tracking
- **Note**: Supposedly fixed in Epic E023 but still present

## Epic Acceptance Criteria

### Data Integrity Fixes
- [x] **Zero duplicate RAISE events** in `fct_yearly_events` table
- [x] **Zero post-termination events** for any employee
- [x] **100% enrollment consistency** between events and snapshots
- [x] **Event sequence validation** ensuring logical order

### Business Rule Enforcement
- [x] **Termination validation** preventing events after termination date
- [x] **Event deduplication** using composite keys and ordering
- [x] **Enrollment state tracking** without circular dependencies
- [x] **Compensation consistency** ensuring contributions ≤ compensation

### Data Quality Monitoring
- [x] **Automated detection** of integrity violations
- [x] **Alert system** for new data quality issues
- [x] **Historical tracking** of data quality metrics
- [x] **Regression prevention** through comprehensive testing

## Story Breakdown

| Story | Title | Points | Owner | Status | Dependencies |
|-------|-------|--------|-------|--------|--------------|
| **S045-01** | Fix Duplicate RAISE Events | 5 | Platform | ❌ Not Started | None |
| **S045-02** | Fix Post-Termination Events | 4 | Platform | ❌ Not Started | None |
| **S045-03** | Fix Enrollment Architecture | 6 | Platform | ❌ Not Started | None |
| **S045-04** | Data Quality Monitoring | 3 | Platform | ❌ Not Started | S045-01,02,03 |

**Completed**: 0 points (0%) | **Remaining**: 18 points (100%)

## Technical Implementation

### Story S045-01: Fix Duplicate RAISE Events

#### Root Cause Analysis
```sql
-- Current issue: Multiple identical RAISE events
SELECT
    employee_id,
    simulation_year,
    effective_date,
    new_compensation,
    COUNT(*) as duplicate_count
FROM fct_yearly_events
WHERE event_type = 'RAISE'
GROUP BY employee_id, simulation_year, effective_date, new_compensation
HAVING COUNT(*) > 1
-- Result: 606 rows with duplicate_count = 2
```

#### Fix Implementation
```sql
-- In dbt/models/intermediate/events/int_merit_events.sql
-- Add proper deduplication logic
WITH base_merit_events AS (
    SELECT
        employee_id,
        simulation_year,
        effective_date,
        new_compensation,
        old_compensation,
        event_details,
        created_at
    FROM {{ ref('stg_merit_calculations') }}
),
deduplicated_events AS (
    SELECT DISTINCT ON (
        employee_id,
        simulation_year,
        effective_date,
        new_compensation
    )
        employee_id,
        simulation_year,
        effective_date,
        new_compensation,
        old_compensation,
        event_details,
        created_at
    FROM base_merit_events
    ORDER BY
        employee_id,
        simulation_year,
        effective_date,
        new_compensation,
        created_at DESC  -- Keep latest in case of true duplicates
)
SELECT * FROM deduplicated_events
```

### Story S045-02: Fix Post-Termination Events

#### Termination Validation Logic
```sql
-- In dbt/models/intermediate/events/int_merit_events.sql
-- Add termination date validation
WITH termination_dates AS (
    SELECT
        employee_id,
        effective_date as termination_date
    FROM {{ ref('int_termination_events') }}
    WHERE simulation_year <= {{ var('simulation_year') }}
),
validated_merit_events AS (
    SELECT me.*
    FROM merit_events_base me
    LEFT JOIN termination_dates td
        ON me.employee_id = td.employee_id
    WHERE
        -- Only include events before termination (or no termination)
        me.effective_date <= COALESCE(td.termination_date, '2099-12-31')
        -- Additional validation: ensure employee is active
        AND me.employee_id IN (
            SELECT DISTINCT employee_id
            FROM {{ ref('fct_workforce_snapshot') }}
            WHERE simulation_year = {{ var('simulation_year') }}
            AND employment_status = 'active'
        )
)
SELECT * FROM validated_merit_events
```

### Story S045-03: Fix Enrollment Architecture

#### Proper Temporal State Accumulator
```sql
-- In dbt/models/intermediate/int_enrollment_state_accumulator.sql
-- Fix circular dependency issue
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['employee_id', 'simulation_year']
) }}

WITH prior_year_state AS (
    SELECT
        employee_id,
        enrollment_date,
        enrollment_status,
        deferral_rate,
        plan_design_id
    FROM {{ this }}
    WHERE simulation_year = {{ var('simulation_year') - 1 }}
    {% if is_incremental() %}
        -- Only look at prior year for incremental builds
    {% endif %}
),
current_year_enrollment_events AS (
    SELECT
        employee_id,
        MIN(CASE
            WHEN event_type = 'enrollment'
            AND event_details LIKE '%enrolled%'
            THEN effective_date
        END) as new_enrollment_date,
        MAX(CASE
            WHEN event_type = 'enrollment'
            THEN event_details
        END) as latest_enrollment_status
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
    GROUP BY employee_id
),
accumulated_state AS (
    SELECT
        COALESCE(e.employee_id, p.employee_id) as employee_id,
        {{ var('simulation_year') }} as simulation_year,

        -- Enrollment date: use new enrollment or carry forward
        COALESCE(
            e.new_enrollment_date,  -- New enrollment this year
            p.enrollment_date       -- Carry forward from prior year
        ) as enrollment_date,

        -- Enrollment status: update with current year or carry forward
        CASE
            WHEN e.latest_enrollment_status IS NOT NULL
            THEN CASE
                WHEN e.latest_enrollment_status LIKE '%enrolled%' THEN 'enrolled'
                WHEN e.latest_enrollment_status LIKE '%unenrolled%' THEN 'not_enrolled'
                ELSE COALESCE(p.enrollment_status, 'not_enrolled')
            END
            ELSE COALESCE(p.enrollment_status, 'not_enrolled')
        END as enrollment_status,

        -- Carry forward other attributes
        COALESCE(p.deferral_rate, 0.03) as deferral_rate,
        COALESCE(p.plan_design_id, 'default') as plan_design_id

    FROM current_year_enrollment_events e
    FULL OUTER JOIN prior_year_state p
        ON e.employee_id = p.employee_id
)
SELECT * FROM accumulated_state
```

### Story S045-04: Data Quality Monitoring

#### Automated Issue Detection
```sql
-- In dbt/models/data_quality/dq_integrity_violations.sql
WITH duplicate_raise_check AS (
    SELECT
        'duplicate_raise_events' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp
    FROM (
        SELECT employee_id, simulation_year, effective_date, new_compensation
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'RAISE'
        GROUP BY employee_id, simulation_year, effective_date, new_compensation
        HAVING COUNT(*) > 1
    )
),
post_termination_check AS (
    SELECT
        'post_termination_events' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp
    FROM {{ ref('fct_yearly_events') }} e
    JOIN (
        SELECT employee_id, effective_date as term_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'termination'
    ) t ON e.employee_id = t.employee_id
    WHERE e.effective_date > t.term_date
),
enrollment_consistency_check AS (
    SELECT
        'enrollment_consistency' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE enrollment_status = 'enrolled'
    AND enrollment_date IS NULL
)
SELECT * FROM duplicate_raise_check
UNION ALL
SELECT * FROM post_termination_check
UNION ALL
SELECT * FROM enrollment_consistency_check
```

## Success Metrics

### Data Integrity Targets
- **Duplicate events**: 0 (currently 606)
- **Post-termination events**: 0 (currently 2)
- **Enrollment inconsistency**: 0 (currently 3,773)
- **Event sequence violations**: 0

### Business Impact Metrics
- **Contribution accuracy**: 100% within IRS limits
- **Compensation consistency**: 100% contributions ≤ compensation
- **Enrollment accuracy**: 100% consistency between events and snapshots
- **Regulatory compliance**: Zero IRS limit violations

### Quality Assurance Metrics
- **Detection speed**: <5 minutes to identify new violations
- **Fix verification**: 100% automated validation of fixes
- **Regression prevention**: Zero reintroduction of fixed issues
- **Historical tracking**: Complete audit trail of all fixes

## Validation Procedures

### Pre-Implementation Validation
```sql
-- Document current state before fixes
CREATE TABLE pre_fix_validation AS
SELECT
    'duplicate_raises' as issue_type,
    COUNT(*) as affected_count
FROM (SELECT employee_id, simulation_year, effective_date, new_compensation
      FROM fct_yearly_events WHERE event_type = 'RAISE'
      GROUP BY employee_id, simulation_year, effective_date, new_compensation
      HAVING COUNT(*) > 1)
UNION ALL
SELECT 'post_termination_events', COUNT(*)
FROM fct_yearly_events e
JOIN (SELECT employee_id, effective_date as term_date
      FROM fct_yearly_events WHERE event_type = 'termination') t
ON e.employee_id = t.employee_id
WHERE e.effective_date > t.term_date
UNION ALL
SELECT 'enrollment_inconsistency', COUNT(*)
FROM fct_workforce_snapshot
WHERE enrollment_status = 'enrolled' AND enrollment_date IS NULL;
```

### Post-Implementation Validation
```sql
-- Verify all issues resolved
SELECT
    issue_type,
    affected_count,
    CASE WHEN affected_count = 0 THEN '✅ FIXED' ELSE '❌ STILL BROKEN' END as status
FROM (
    -- Same validation queries as above
    -- Should all return 0 after fixes
);
```

## Definition of Done

- [x] **All 3 integrity issues resolved** with zero violations detected
- [x] **Deduplication logic implemented** preventing future duplicate events
- [x] **Termination validation** preventing post-termination events
- [x] **Enrollment architecture fixed** with proper temporal state tracking
- [x] **Automated monitoring** detecting new violations within 5 minutes
- [x] **Comprehensive testing** validating all fixes
- [x] **Documentation** explaining root causes and prevention measures

## Risk Analysis

### Technical Risks
- **Data loss during fixes**: Mitigated by comprehensive backup before changes
- **New issues introduced**: Mitigated by incremental fixes and validation
- **Performance impact**: Mitigated by efficient deduplication queries

### Business Risks
- **Regulatory violations**: Addressed by fixing IRS limit compliance issues
- **Financial inaccuracy**: Resolved by ensuring contribution ≤ compensation
- **Audit failures**: Prevented by maintaining complete fix audit trail

## Implementation Priority

1. **S045-02** (Post-termination events) - IMMEDIATE: Fixes compliance violations
2. **S045-01** (Duplicate events) - HIGH: Fixes calculation accuracy
3. **S045-03** (Enrollment architecture) - HIGH: Fixes state consistency
4. **S045-04** (Monitoring) - MEDIUM: Prevents regression

## Related Epics

- **E044**: Production Observability & Logging Framework (provides logging for fix tracking)
- **E046**: Recovery & Checkpoint System (enables safe rollback if fixes fail)
- **E047**: Production Testing & Validation Framework (validates fix effectiveness)

---

**Critical Path**: This epic must be completed before production deployment. All 3 issues represent data integrity violations that make the system unsuitable for regulatory compliance.
