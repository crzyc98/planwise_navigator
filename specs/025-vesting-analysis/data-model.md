# Data Model: Vesting Analysis

**Feature Branch**: `025-vesting-analysis`
**Date**: 2026-01-21

## Overview

This document defines the data models for the Vesting Analysis feature. Models are split between Python (Pydantic v2) for API and TypeScript for frontend.

---

## Entity Relationship

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Vesting Analysis Flow                            │
└─────────────────────────────────────────────────────────────────────────┘

   ┌──────────────────┐         ┌─────────────────────────┐
   │ VestingSchedule  │◄────────│ VestingScheduleConfig   │
   │   (Pre-defined)  │         │    (User Selection)     │
   └──────────────────┘         └─────────────────────────┘
           │                              │
           │ defines percentages          │ current + proposed
           ▼                              ▼
   ┌──────────────────┐         ┌─────────────────────────┐
   │ fct_workforce_   │         │ VestingAnalysisRequest  │
   │    snapshot      │────────►│    (API Request)        │
   │ (DuckDB Table)   │ query   └─────────────────────────┘
   └──────────────────┘                   │
           │                              │
           │ terminated employees         │ analysis
           ▼                              ▼
   ┌──────────────────┐         ┌─────────────────────────┐
   │ EmployeeVesting  │◄───────►│ VestingAnalysisResponse │
   │    Detail        │  part of│     (API Response)      │
   └──────────────────┘         └─────────────────────────┘
                                          │
                                          │ contains
                                          ▼
                                ┌─────────────────────────┐
                                │ VestingAnalysisSummary  │
                                │ TenureBandSummary[]     │
                                │ EmployeeVestingDetail[] │
                                └─────────────────────────┘
```

---

## Python Models (Pydantic v2)

### File: `planalign_api/models/vesting.py`

```python
"""Pydantic models for vesting analysis."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class VestingScheduleType(str, Enum):
    """Pre-defined vesting schedule types."""

    IMMEDIATE = "immediate"
    CLIFF_2_YEAR = "cliff_2_year"
    CLIFF_3_YEAR = "cliff_3_year"
    CLIFF_4_YEAR = "cliff_4_year"
    QACA_2_YEAR = "qaca_2_year"
    GRADED_3_YEAR = "graded_3_year"
    GRADED_4_YEAR = "graded_4_year"
    GRADED_5_YEAR = "graded_5_year"


class VestingScheduleInfo(BaseModel):
    """Information about a vesting schedule for display."""

    schedule_type: VestingScheduleType
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., max_length=200)
    percentages: dict[int, float] = Field(
        ...,
        description="Year -> vesting percentage mapping"
    )


class VestingScheduleConfig(BaseModel):
    """User-selected vesting schedule configuration."""

    schedule_type: VestingScheduleType
    name: str = Field(..., min_length=1, max_length=50)
    require_hours_credit: bool = Field(
        default=False,
        description="If true, employees must meet hours threshold for vesting credit"
    )
    hours_threshold: int = Field(
        default=1000,
        ge=0,
        le=2080,
        description="Minimum annual hours for vesting credit (default: 1000)"
    )


class VestingAnalysisRequest(BaseModel):
    """Request to run vesting analysis comparing two schedules."""

    current_schedule: VestingScheduleConfig = Field(
        ...,
        description="Current vesting schedule to analyze"
    )
    proposed_schedule: VestingScheduleConfig = Field(
        ...,
        description="Proposed vesting schedule to compare"
    )
    simulation_year: Optional[int] = Field(
        default=None,
        ge=2020,
        le=2050,
        description="Simulation year to analyze (default: final year)"
    )


class EmployeeVestingDetail(BaseModel):
    """Vesting calculation details for a single employee."""

    employee_id: str = Field(..., min_length=1)
    hire_date: date
    termination_date: date
    tenure_years: int = Field(..., ge=0)
    tenure_band: str
    annual_hours_worked: int = Field(..., ge=0)
    total_employer_contributions: Decimal = Field(..., ge=0)

    # Current schedule results
    current_vesting_pct: Decimal = Field(..., ge=0, le=1)
    current_vested_amount: Decimal = Field(..., ge=0)
    current_forfeiture: Decimal = Field(..., ge=0)

    # Proposed schedule results
    proposed_vesting_pct: Decimal = Field(..., ge=0, le=1)
    proposed_vested_amount: Decimal = Field(..., ge=0)
    proposed_forfeiture: Decimal = Field(..., ge=0)

    # Comparison
    forfeiture_variance: Decimal = Field(
        ...,
        description="Proposed - Current forfeiture (negative = less forfeiture)"
    )


class TenureBandSummary(BaseModel):
    """Forfeiture summary for a tenure band."""

    tenure_band: str
    employee_count: int = Field(..., ge=0)
    total_contributions: Decimal = Field(..., ge=0)
    current_forfeitures: Decimal = Field(..., ge=0)
    proposed_forfeitures: Decimal = Field(..., ge=0)
    forfeiture_variance: Decimal


class VestingAnalysisSummary(BaseModel):
    """High-level summary of vesting analysis."""

    analysis_year: int
    terminated_employee_count: int = Field(..., ge=0)
    total_employer_contributions: Decimal = Field(..., ge=0)

    # Current schedule totals
    current_total_vested: Decimal = Field(..., ge=0)
    current_total_forfeited: Decimal = Field(..., ge=0)

    # Proposed schedule totals
    proposed_total_vested: Decimal = Field(..., ge=0)
    proposed_total_forfeited: Decimal = Field(..., ge=0)

    # Comparison
    forfeiture_variance: Decimal = Field(
        ...,
        description="Proposed - Current total forfeiture"
    )
    forfeiture_variance_pct: Decimal = Field(
        ...,
        description="Percentage change in forfeitures"
    )


class VestingAnalysisResponse(BaseModel):
    """Complete response from vesting analysis."""

    scenario_id: str
    scenario_name: str
    current_schedule: VestingScheduleConfig
    proposed_schedule: VestingScheduleConfig
    summary: VestingAnalysisSummary
    by_tenure_band: List[TenureBandSummary]
    employee_details: List[EmployeeVestingDetail]


class VestingScheduleListResponse(BaseModel):
    """Response listing available vesting schedules."""

    schedules: List[VestingScheduleInfo]
```

---

## TypeScript Types

### File: `planalign_studio/services/api.ts` (additions)

```typescript
// ============================================================================
// Vesting Analysis Types (Feature 025)
// ============================================================================

export type VestingScheduleType =
  | 'immediate'
  | 'cliff_2_year'
  | 'cliff_3_year'
  | 'cliff_4_year'
  | 'qaca_2_year'
  | 'graded_3_year'
  | 'graded_4_year'
  | 'graded_5_year';

export interface VestingScheduleInfo {
  schedule_type: VestingScheduleType;
  name: string;
  description: string;
  percentages: Record<number, number>;
}

export interface VestingScheduleConfig {
  schedule_type: VestingScheduleType;
  name: string;
  require_hours_credit?: boolean;
  hours_threshold?: number;
}

export interface VestingAnalysisRequest {
  current_schedule: VestingScheduleConfig;
  proposed_schedule: VestingScheduleConfig;
  simulation_year?: number;
}

export interface EmployeeVestingDetail {
  employee_id: string;
  hire_date: string;
  termination_date: string;
  tenure_years: number;
  tenure_band: string;
  annual_hours_worked: number;
  total_employer_contributions: number;
  current_vesting_pct: number;
  current_vested_amount: number;
  current_forfeiture: number;
  proposed_vesting_pct: number;
  proposed_vested_amount: number;
  proposed_forfeiture: number;
  forfeiture_variance: number;
}

export interface TenureBandSummary {
  tenure_band: string;
  employee_count: number;
  total_contributions: number;
  current_forfeitures: number;
  proposed_forfeitures: number;
  forfeiture_variance: number;
}

export interface VestingAnalysisSummary {
  analysis_year: number;
  terminated_employee_count: number;
  total_employer_contributions: number;
  current_total_vested: number;
  current_total_forfeited: number;
  proposed_total_vested: number;
  proposed_total_forfeited: number;
  forfeiture_variance: number;
  forfeiture_variance_pct: number;
}

export interface VestingAnalysisResponse {
  scenario_id: string;
  scenario_name: string;
  current_schedule: VestingScheduleConfig;
  proposed_schedule: VestingScheduleConfig;
  summary: VestingAnalysisSummary;
  by_tenure_band: TenureBandSummary[];
  employee_details: EmployeeVestingDetail[];
}

export interface VestingScheduleListResponse {
  schedules: VestingScheduleInfo[];
}
```

---

## Data Source: fct_workforce_snapshot

### Relevant Columns for Vesting Analysis

| Column | Type | Description |
|--------|------|-------------|
| `employee_id` | VARCHAR | Unique employee identifier |
| `employee_hire_date` | DATE | Original hire date |
| `termination_date` | TIMESTAMP | Date of termination |
| `current_tenure` | FLOAT | Years of service |
| `tenure_band` | VARCHAR | Tenure band category (e.g., "2-4", "5-9") |
| `employment_status` | VARCHAR | "active" or "terminated" |
| `employer_match_amount` | DECIMAL | Employer match contributions |
| `employer_core_amount` | DECIMAL | Employer core contributions |
| `total_employer_contributions` | DECIMAL | Sum of match + core |
| `annual_hours_worked` | INTEGER | Hours worked in year |
| `simulation_year` | INTEGER | Year of snapshot |

### Query Pattern

```sql
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    current_tenure,
    tenure_band,
    employer_match_amount,
    employer_core_amount,
    total_employer_contributions,
    annual_hours_worked
FROM fct_workforce_snapshot
WHERE simulation_year = :year
  AND UPPER(employment_status) = 'TERMINATED'
  AND total_employer_contributions > 0
ORDER BY total_employer_contributions DESC
```

---

## Vesting Schedule Definitions

### Pre-defined Schedules

```python
VESTING_SCHEDULES: dict[VestingScheduleType, dict[int, float]] = {
    VestingScheduleType.IMMEDIATE: {
        0: 1.0
    },
    VestingScheduleType.CLIFF_2_YEAR: {
        0: 0.0,
        1: 0.0,
        2: 1.0
    },
    VestingScheduleType.CLIFF_3_YEAR: {
        0: 0.0,
        1: 0.0,
        2: 0.0,
        3: 1.0
    },
    VestingScheduleType.CLIFF_4_YEAR: {
        0: 0.0,
        1: 0.0,
        2: 0.0,
        3: 0.0,
        4: 1.0
    },
    VestingScheduleType.QACA_2_YEAR: {
        0: 0.0,
        1: 0.0,
        2: 1.0
    },
    VestingScheduleType.GRADED_3_YEAR: {
        0: 0.0,
        1: 0.3333,
        2: 0.6667,
        3: 1.0
    },
    VestingScheduleType.GRADED_4_YEAR: {
        0: 0.0,
        1: 0.25,
        2: 0.50,
        3: 0.75,
        4: 1.0
    },
    VestingScheduleType.GRADED_5_YEAR: {
        0: 0.0,
        1: 0.20,
        2: 0.40,
        3: 0.60,
        4: 0.80,
        5: 1.0
    }
}
```

### Display Information

```python
SCHEDULE_INFO: dict[VestingScheduleType, VestingScheduleInfo] = {
    VestingScheduleType.IMMEDIATE: VestingScheduleInfo(
        schedule_type=VestingScheduleType.IMMEDIATE,
        name="Immediate",
        description="100% vested from day one",
        percentages={0: 1.0}
    ),
    VestingScheduleType.CLIFF_2_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_2_YEAR,
        name="2-Year Cliff",
        description="0% until 2 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 1.0}
    ),
    VestingScheduleType.CLIFF_3_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_3_YEAR,
        name="3-Year Cliff",
        description="0% until 3 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 0.0, 3: 1.0}
    ),
    VestingScheduleType.CLIFF_4_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.CLIFF_4_YEAR,
        name="4-Year Cliff",
        description="0% until 4 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 1.0}
    ),
    VestingScheduleType.QACA_2_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.QACA_2_YEAR,
        name="QACA 2-Year",
        description="0% until 2 years, then 100%",
        percentages={0: 0.0, 1: 0.0, 2: 1.0}
    ),
    VestingScheduleType.GRADED_3_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_3_YEAR,
        name="3-Year Graded",
        description="33.33% per year from year 1-3",
        percentages={0: 0.0, 1: 0.3333, 2: 0.6667, 3: 1.0}
    ),
    VestingScheduleType.GRADED_4_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_4_YEAR,
        name="4-Year Graded",
        description="25% per year from year 1-4",
        percentages={0: 0.0, 1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}
    ),
    VestingScheduleType.GRADED_5_YEAR: VestingScheduleInfo(
        schedule_type=VestingScheduleType.GRADED_5_YEAR,
        name="5-Year Graded",
        description="20% per year from year 1-5",
        percentages={0: 0.0, 1: 0.20, 2: 0.40, 3: 0.60, 4: 0.80, 5: 1.0}
    )
}
```

---

## Validation Rules

### VestingAnalysisRequest Validation

1. **schedule_type**: Must be valid VestingScheduleType enum value
2. **hours_threshold**: Must be between 0 and 2080 (max annual hours)
3. **simulation_year**: If provided, must be between 2020 and 2050
4. **Both schedules required**: current_schedule and proposed_schedule cannot be None

### Business Rules

1. **Tenure truncation**: Tenure is truncated to whole years for vesting lookup
2. **Hours credit**: If hours threshold not met, reduce effective tenure by 1 year
3. **Maximum vesting**: Tenure beyond max schedule year uses 100% vesting
4. **Zero contributions**: Employees with zero employer contributions are excluded
5. **Active employees**: Only terminated employees are included in analysis

---

## State Transitions

### Employee Vesting State

This feature does not track state transitions - it calculates vesting at a point in time based on:
- Current tenure at termination
- Hours worked in final year
- Total employer contributions at termination

No new events or state changes are created by this feature.
