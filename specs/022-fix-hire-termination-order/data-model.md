# Data Model: Fix Hire Date Before Termination Date Ordering

**Feature**: 022-fix-hire-termination-order
**Date**: 2026-01-21

## Entities

This feature modifies existing entities rather than creating new ones.

### Termination Event (Modified)

**Table**: `fct_yearly_events` (rows where `event_type = 'termination'`)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| employee_id | VARCHAR | NOT NULL, FK | References employee |
| event_type | VARCHAR | = 'termination' | Event type discriminator |
| effective_date | DATE | **>= employee_hire_date** | **NEW CONSTRAINT**: Must be on or after hire |
| employee_tenure | INTEGER | **>= 0** | **VALIDATED**: Calculated to termination date |
| simulation_year | INTEGER | NOT NULL | Year of simulation |

**Validation Rules**:
- `effective_date >= employee_hire_date` (FR-001)
- `effective_date <= simulation_year-12-31` (existing)
- `employee_tenure = floor(datediff(effective_date, employee_hire_date) / 365.25)` (FR-007)

---

### Workforce Snapshot (Modified)

**Table**: `fct_workforce_snapshot`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| employee_id | VARCHAR | NOT NULL, PK (composite) | Employee identifier |
| employee_hire_date | DATE | NOT NULL | Hire date |
| termination_date | DATE | NULLABLE, **>= employee_hire_date** | **NEW CONSTRAINT** |
| employment_status | VARCHAR | 'active' or 'terminated' | Employment status |
| current_tenure | INTEGER | **>= 0** | **MODIFIED**: Uses termination_date for terminated |
| simulation_year | INTEGER | NOT NULL, PK (composite) | Simulation year |

**Validation Rules**:
- For `employment_status = 'terminated'`: `termination_date >= employee_hire_date` (FR-001)
- For `employment_status = 'terminated'`: `current_tenure = floor(datediff(termination_date, employee_hire_date) / 365.25)` (FR-007)
- For `employment_status = 'active'`: `current_tenure = floor(datediff(year_end, employee_hire_date) / 365.25)` (existing)

---

## Macro Interface Changes

### generate_termination_date (Modified)

**Before**:
```sql
{% macro generate_termination_date(employee_id_column, simulation_year, random_seed=42) %}
```

**After**:
```sql
{% macro generate_termination_date(employee_id_column, simulation_year, hire_date_column, random_seed=42) %}
```

**New Parameter**:
- `hire_date_column`: Column name containing the employee's hire date

**Behavior Change**:
- Previous: `Jan 1 + (hash % 365)` → could produce date before hire
- New: `hire_date + (hash % days_until_year_end)` → always >= hire_date

---

## State Transitions

### Termination Date Generation

```
┌─────────────────────┐
│  Employee Selected  │
│   for Termination   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Calculate days from │
│ hire_date to Dec 31 │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ If days_available=0 │──────► Employee NOT terminated
│ (hired Dec 31)      │        (cannot fit termination)
└──────────┬──────────┘
           │ days_available > 0
           ▼
┌─────────────────────┐
│ Compute offset:     │
│ hash % days_avail   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ termination_date =  │
│ hire_date + offset  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Generate Event with │
│ tenure calculated   │
│ to termination_date │
└─────────────────────┘
```

### Tenure Calculation (Snapshot)

```
┌─────────────────────┐
│  Employee Record    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ employment_status?  │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌────────┐   ┌────────────┐
│ active │   │ terminated │
└───┬────┘   └─────┬──────┘
    │              │
    ▼              ▼
┌────────────┐  ┌───────────────┐
│ tenure to  │  │ tenure to     │
│ Dec 31     │  │ termination   │
└────────────┘  └───────────────┘
```

---

## Data Quality Constraints

### Test 1: Termination After Hire (FR-005)

```sql
-- test_termination_after_hire.sql
-- Returns rows that violate constraint (should be 0)
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    'fct_workforce_snapshot' AS source
FROM {{ ref('fct_workforce_snapshot') }}
WHERE termination_date IS NOT NULL
  AND termination_date < employee_hire_date
  AND simulation_year = {{ var('simulation_year') }}

UNION ALL

SELECT
    employee_id,
    NULL AS employee_hire_date,  -- Would need join to get hire date
    effective_date AS termination_date,
    'fct_yearly_events' AS source
FROM {{ ref('fct_yearly_events') }}
WHERE event_type = 'termination'
  AND simulation_year = {{ var('simulation_year') }}
  AND effective_date < (
      SELECT employee_hire_date
      FROM {{ ref('fct_workforce_snapshot') }} s
      WHERE s.employee_id = fct_yearly_events.employee_id
        AND s.simulation_year = {{ var('simulation_year') }}
  )
```

### Test 2: Tenure At Termination (FR-008)

```sql
-- test_tenure_at_termination.sql
-- Returns rows where tenure doesn't match formula (should be 0)
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    current_tenure AS actual_tenure,
    FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER AS expected_tenure
FROM {{ ref('fct_workforce_snapshot') }}
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND simulation_year = {{ var('simulation_year') }}
  AND current_tenure != FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER
```

---

## Relationships

```
┌─────────────────────┐
│   Employee Census   │
│   (stg_census_data) │
└──────────┬──────────┘
           │ employee_hire_date
           ▼
┌─────────────────────┐
│ int_baseline_       │
│ workforce           │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐         ┌─────────────────────┐
│ int_termination_    │────────►│ fct_yearly_events   │
│ events              │         │ (termination rows)  │
└──────────┬──────────┘         └──────────┬──────────┘
           │                               │
           │ hire_date constraint          │ effective_date
           │                               │ employee_tenure
           ▼                               ▼
┌─────────────────────────────────────────────────────┐
│                fct_workforce_snapshot                │
│  - termination_date (from events)                   │
│  - current_tenure (recalculated for terminated)     │
└─────────────────────────────────────────────────────┘
```
