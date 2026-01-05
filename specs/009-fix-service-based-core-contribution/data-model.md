# Data Model: Service-Based Core Contribution

**Date**: 2026-01-05
**Feature Branch**: `009-fix-service-based-core-contribution`

## Overview

This document defines the data entities involved in service-based (graded by service) core contribution calculations.

---

## Entities

### Service Tier (Configuration Input)

Represents a single tier in the graded-by-service schedule.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `min_years` | INT | Minimum years of service (inclusive) | >= 0 |
| `max_years` | INT \| NULL | Maximum years of service (exclusive) | > min_years or NULL for infinity |
| `rate` | DECIMAL(5,2) | Contribution rate as percentage | 0.00 - 100.00 |

**Source**: `employer_core_graded_schedule` dbt variable (from UI configuration)

**Example**:
```json
[
  {"min_years": 0, "max_years": 10, "rate": 6.0},
  {"min_years": 10, "max_years": null, "rate": 8.0}
]
```

**Validation Rules**:
- Tiers must not overlap
- Tiers should cover all possible tenure values (no gaps)
- First tier should start at `min_years = 0`
- Last tier should have `max_years = null` (infinity)

---

### Core Contribution Status (Configuration Input)

Controls the contribution calculation mode.

| Value | Description |
|-------|-------------|
| `'none'` | Core contributions disabled |
| `'flat'` | Single flat rate for all employees |
| `'graded_by_service'` | Service-based tiered rates |

**Source**: `employer_core_status` dbt variable

---

### Employee Tenure (Derived)

Years of service for tier matching.

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `employee_id` | STRING | Unique employee identifier | `int_workforce_snapshot_optimized` |
| `current_tenure` | DECIMAL(10,4) | Decimal years of service | Calculated from hire_date |
| `years_of_service` | INT | Integer years (floor) | `FLOOR(current_tenure)` |

**Calculation**:
```sql
FLOOR(current_tenure) AS years_of_service
```

---

### Employer Core Contribution (Output)

The enhanced output schema with tier audit fields.

| Field | Type | Description | New/Existing |
|-------|------|-------------|--------------|
| `employee_id` | STRING | Employee identifier | Existing |
| `simulation_year` | INT | Simulation year | Existing |
| `eligible_compensation` | DECIMAL(12,2) | Compensation basis | Existing |
| `employment_status` | STRING | Active/terminated | Existing |
| `eligible_for_core` | BOOLEAN | Eligibility flag | Existing |
| `employer_core_amount` | DECIMAL(12,2) | Calculated contribution | Existing |
| `core_contribution_rate` | DECIMAL(5,4) | Applied rate | Existing (enhanced) |
| `contribution_method` | STRING | 'configurable_rate' or 'disabled' | Existing |
| `standard_core_rate` | DECIMAL(5,4) | Flat rate from config | Existing |
| `applied_years_of_service` | INT | Tenure used for tier lookup | **NEW** |
| `scenario_id` | STRING | Scenario identifier | Existing |
| `parameter_scenario_id` | STRING | Parameter scenario | Existing |
| `created_at` | TIMESTAMP | Record creation time | Existing |

**Note on `core_contribution_rate`**: This field now reflects the actual rate applied (either flat or from service tier), providing audit capability.

---

## Relationships

```
┌─────────────────────────┐
│   Service Tier Config   │
│  (employer_core_graded_ │
│        schedule)        │
└───────────┬─────────────┘
            │ 1:N lookup
            ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│   Employee Tenure       │──────│  Employer Core          │
│   (snapshot_flags CTE)  │      │  Contribution           │
└─────────────────────────┘      │  (output table)         │
            ▲                    └─────────────────────────┘
            │
┌───────────┴─────────────┐
│ int_workforce_snapshot_ │
│      optimized          │
└─────────────────────────┘
```

---

## State Transitions

N/A - This is a bug fix. No new state machines introduced.

---

## Data Volume Assumptions

| Table | Expected Rows | Notes |
|-------|---------------|-------|
| Service Tiers | 2-10 per scenario | Typically 2-4 tiers |
| Employees | 100K+ | Enterprise scale |
| Core Contributions | 100K+ per year | 1:1 with employees |

---

## Migration Notes

No migration required. This fix:
1. Adds logic to read existing (unused) configuration variables
2. Adds optional audit field (`applied_years_of_service`)
3. Does not change existing column types or constraints
4. Maintains backward compatibility (flat-rate scenarios unchanged)
