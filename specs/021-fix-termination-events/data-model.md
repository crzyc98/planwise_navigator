# Data Model: Fix Termination Event Data Quality

**Feature**: 021-fix-termination-events
**Date**: 2026-01-21

## Entity Relationships

```
┌─────────────────────────────────────┐
│        fct_yearly_events            │
│  (Immutable Event Store)            │
├─────────────────────────────────────┤
│  employee_id        VARCHAR PK      │
│  event_type         VARCHAR         │◄──┬── 'termination' | 'hire' | etc.
│  simulation_year    INTEGER PK      │   │
│  effective_date     DATE            │◄──┼── YEAR-DISTRIBUTED (fix)
│  event_category     VARCHAR         │◄──┴── 'new_hire_termination' (fix)
│  event_details      VARCHAR         │
│  compensation_amount DECIMAL        │
└─────────────────────────────────────┘
                    │
                    │ aggregated by
                    ▼
┌─────────────────────────────────────┐
│   employee_events_consolidated      │
│   (Derived CTE in snapshot)         │
├─────────────────────────────────────┤
│  employee_id        VARCHAR PK      │
│  is_new_hire        BOOLEAN         │◄── COUNT(hire events) > 0
│  is_new_hire_termination BOOLEAN    │◄── event_category = 'new_hire_termination' (fix)
│  has_termination    BOOLEAN         │
│  termination_date   DATE            │
└─────────────────────────────────────┘
                    │
                    │ joined to
                    ▼
┌─────────────────────────────────────┐
│      fct_workforce_snapshot         │
│      (Point-in-Time State)          │
├─────────────────────────────────────┤
│  employee_id        VARCHAR PK      │
│  simulation_year    INTEGER PK      │
│  employment_status  VARCHAR         │◄── 'active' | 'terminated'
│  termination_date   TIMESTAMP       │◄── populated for ALL terminations (fix)
│  detailed_status_code VARCHAR       │◄── accurate classification (fix)
│  employee_hire_date DATE            │
│  ...                                │
└─────────────────────────────────────┘
```

## Key Entities

### Termination Event

**Source**: `int_termination_events.sql`, `int_new_hire_termination_events.sql`
**Destination**: `fct_yearly_events`

| Field | Type | Description | Fix Required |
|-------|------|-------------|--------------|
| employee_id | VARCHAR | Unique employee identifier | No |
| event_type | VARCHAR | Always 'termination' | No |
| simulation_year | INTEGER | Year of the event | No |
| effective_date | DATE | **Day of termination** | **YES** - Must be year-distributed |
| event_category | VARCHAR | 'new_hire_termination' or NULL | **YES** - Column name alignment |
| termination_reason | VARCHAR | Reason code | No |

**Validation Rules**:
- `effective_date` must be within `[simulation_year-01-01, simulation_year-12-31]`
- `effective_date` distribution: no single month > 20% of total
- `event_category` must be 'new_hire_termination' for new hire terminations

### Workforce Snapshot

**Source**: `fct_workforce_snapshot.sql`

| Field | Type | Description | Fix Required |
|-------|------|-------------|--------------|
| employee_id | VARCHAR | Unique employee identifier | No |
| simulation_year | INTEGER | Snapshot year | No |
| employment_status | VARCHAR | 'active' or 'terminated' | **YES** - Must reflect termination |
| termination_date | TIMESTAMP | Date of termination | **YES** - Must be populated |
| detailed_status_code | VARCHAR | Classification | **YES** - Accurate assignment |
| employee_hire_date | DATE | Original hire date | No |

**State Transitions**:

```
[baseline_employee] ──hire_year=prior──▶ [continuous_active]
                                              │
                                    terminate │
                                              ▼
                                    [experienced_termination]

[new_hire_year_N] ──no_termination──▶ [new_hire_active]
                                              │
                                    terminate │
                                              ▼
                                    [new_hire_termination]
```

**Validation Rules**:
- `detailed_status_code = 'new_hire_active'` IFF `is_new_hire = true` AND `employment_status = 'active'` AND hire event exists in current year
- `detailed_status_code = 'new_hire_termination'` IFF `is_new_hire = true` AND `employment_status = 'terminated'` AND hire event exists in current year
- `termination_date IS NOT NULL` when `employment_status = 'terminated'`

## Data Flow

```
Census Data ──▶ int_baseline_workforce
                        │
                        ▼
               int_termination_events ───────────────────┐
               (experienced terminations)                │
                        │                                │
                        │ year-aware hash for dates      │
                        ▼                                │
               int_hiring_events                         │
                        │                                │
                        ▼                                │
               int_new_hire_termination_events ──────────┤
               (first-year turnover)                     │
                        │                                │
                        │ renamed event_category         │
                        ▼                                │
               fct_yearly_events ◄───────────────────────┘
                        │
                        │ consolidated aggregation
                        ▼
               employee_events_consolidated (CTE)
                        │
                        │ joined with base workforce
                        ▼
               fct_workforce_snapshot
               (final materialized state)
```

## Changes Summary

| Component | Change | Impact |
|-----------|--------|--------|
| `int_termination_events.sql` | Hash includes `simulation_year` | Date distribution fixed |
| `int_new_hire_termination_events.sql` | Rename `termination_type` → `event_category` | NH termination detection fixed |
| `fct_workforce_snapshot.sql` | Explicit hire event check in status logic | Status code accuracy fixed |
| `generate_termination_date.sql` (new macro) | Encapsulate year-aware hash logic | Reusability, consistency |
