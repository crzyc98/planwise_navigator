# Data Model: Studio Band Configuration Management

**Feature Branch**: `003-studio-band-config`
**Created**: 2025-12-12

## Overview

This document defines the data entities for band configuration management. Bands are stored as dbt seed CSV files and exposed via Pydantic models in the API.

---

## Entities

### Band

A single band definition representing a range segment for age or tenure grouping.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| band_id | int | Required, >= 1 | Unique identifier for the band |
| band_label | str | Required, max 50 chars | Human-readable label (e.g., "25-34", "< 25") |
| min_value | int | Required, >= 0 | Lower bound (inclusive) |
| max_value | int | Required, > min_value | Upper bound (exclusive) |
| display_order | int | Required, >= 1 | Sort order for UI display |

**Validation Rules**:
- `min_value` must be >= 0
- `max_value` must be > `min_value`
- First band (by display_order) must have `min_value` = 0
- Last band must have `max_value` = 999 (or reasonable upper bound)
- Consecutive bands: `bands[i].max_value == bands[i+1].min_value` (no gaps)
- No overlapping ranges

**Source**: CSV files in `dbt/seeds/`
- `config_age_bands.csv` - 6 age bands
- `config_tenure_bands.csv` - 5 tenure bands

---

### BandConfig

Container for all band configurations (age and tenure).

| Field | Type | Description |
|-------|------|-------------|
| age_bands | list[Band] | List of age band definitions |
| tenure_bands | list[Band] | List of tenure band definitions |

---

### BandValidationError

Represents a validation error for band configurations.

| Field | Type | Description |
|-------|------|-------------|
| band_type | str | "age" or "tenure" |
| error_type | str | "gap", "overlap", "invalid_range", "coverage" |
| message | str | Human-readable error message |
| band_ids | list[int] | IDs of bands involved in the error |

---

### BandSaveRequest

Request payload for saving band configurations.

| Field | Type | Description |
|-------|------|-------------|
| age_bands | list[Band] | Updated age band definitions |
| tenure_bands | list[Band] | Updated tenure band definitions |

---

### BandSaveResponse

Response after saving band configurations.

| Field | Type | Description |
|-------|------|-------------|
| success | bool | Whether save was successful |
| validation_errors | list[BandValidationError] | Errors if save failed |
| message | str | Status message |

---

### BandAnalysisRequest

Request for census-based band analysis.

| Field | Type | Description |
|-------|------|-------------|
| file_path | str | Path to census file (relative to workspace or absolute) |

---

### BandAnalysisResult

Result from analyzing census data for band suggestions.

| Field | Type | Description |
|-------|------|-------------|
| suggested_bands | list[Band] | Suggested band definitions |
| distribution_stats | DistributionStats | Statistics about the analyzed distribution |
| analysis_type | str | Description of analysis (e.g., "Recent hires from 2024") |
| source_file | str | Path to source census file |

---

### DistributionStats

Statistics from census distribution analysis.

| Field | Type | Description |
|-------|------|-------------|
| total_employees | int | Number of employees analyzed |
| min_value | int | Minimum value in distribution |
| max_value | int | Maximum value in distribution |
| median_value | float | Median value |
| mean_value | float | Mean value |
| percentiles | dict[int, float] | Percentile values (10, 25, 50, 75, 90) |

---

## Pydantic Models (Python)

```python
# planalign_api/models/bands.py

from pydantic import BaseModel, Field, field_validator
from typing import Literal


class Band(BaseModel):
    """A single band definition."""
    band_id: int = Field(..., ge=1, description="Unique band identifier")
    band_label: str = Field(..., max_length=50, description="Human-readable label")
    min_value: int = Field(..., ge=0, description="Lower bound (inclusive)")
    max_value: int = Field(..., gt=0, description="Upper bound (exclusive)")
    display_order: int = Field(..., ge=1, description="Sort order for display")

    @field_validator("max_value")
    @classmethod
    def max_greater_than_min(cls, v, info):
        if "min_value" in info.data and v <= info.data["min_value"]:
            raise ValueError("max_value must be greater than min_value")
        return v


class BandConfig(BaseModel):
    """Container for all band configurations."""
    age_bands: list[Band]
    tenure_bands: list[Band]


class BandValidationError(BaseModel):
    """A validation error for band configurations."""
    band_type: Literal["age", "tenure"]
    error_type: Literal["gap", "overlap", "invalid_range", "coverage"]
    message: str
    band_ids: list[int] = Field(default_factory=list)


class BandSaveRequest(BaseModel):
    """Request payload for saving bands."""
    age_bands: list[Band]
    tenure_bands: list[Band]


class BandSaveResponse(BaseModel):
    """Response after saving bands."""
    success: bool
    validation_errors: list[BandValidationError] = Field(default_factory=list)
    message: str


class BandAnalysisRequest(BaseModel):
    """Request for census-based analysis."""
    file_path: str


class DistributionStats(BaseModel):
    """Statistics from distribution analysis."""
    total_employees: int
    min_value: int
    max_value: int
    median_value: float
    mean_value: float
    percentiles: dict[int, float] = Field(
        default_factory=dict,
        description="Percentile values keyed by percentile (10, 25, 50, 75, 90)"
    )


class BandAnalysisResult(BaseModel):
    """Result from census-based band analysis."""
    suggested_bands: list[Band]
    distribution_stats: DistributionStats
    analysis_type: str
    source_file: str
```

---

## TypeScript Interfaces (Frontend)

```typescript
// planalign_studio/services/api.ts

export interface Band {
  band_id: number;
  band_label: string;
  min_value: number;
  max_value: number;
  display_order: number;
}

export interface BandConfig {
  age_bands: Band[];
  tenure_bands: Band[];
}

export interface BandValidationError {
  band_type: 'age' | 'tenure';
  error_type: 'gap' | 'overlap' | 'invalid_range' | 'coverage';
  message: string;
  band_ids: number[];
}

export interface BandSaveRequest {
  age_bands: Band[];
  tenure_bands: Band[];
}

export interface BandSaveResponse {
  success: boolean;
  validation_errors: BandValidationError[];
  message: string;
}

export interface BandAnalysisRequest {
  file_path: string;
}

export interface DistributionStats {
  total_employees: number;
  min_value: number;
  max_value: number;
  median_value: number;
  mean_value: number;
  percentiles: Record<number, number>;
}

export interface BandAnalysisResult {
  suggested_bands: Band[];
  distribution_stats: DistributionStats;
  analysis_type: string;
  source_file: string;
}
```

---

## CSV Schema (dbt Seeds)

### config_age_bands.csv

```csv
band_id,band_label,min_value,max_value,display_order
1,< 25,0,25,1
2,25-34,25,35,2
3,35-44,35,45,3
4,45-54,45,55,4
5,55-64,55,65,5
6,65+,65,999,6
```

### config_tenure_bands.csv

```csv
band_id,band_label,min_value,max_value,display_order
1,< 2,0,2,1
2,2-4,2,5,2
3,5-9,5,10,3
4,10-19,10,20,4
5,20+,20,999,5
```

---

## Relationships

```text
BandConfig
├── age_bands: list[Band]     (1:N)
└── tenure_bands: list[Band]  (1:N)

BandAnalysisResult
└── suggested_bands: list[Band]  (1:N)
└── distribution_stats: DistributionStats  (1:1)
```

---

## State Transitions

Bands don't have explicit state transitions. They are configuration data that:
1. Are loaded from CSV at startup
2. Can be edited by users
3. Are saved back to CSV
4. Are reloaded by dbt at simulation start

---

## Validation Examples

### Valid Configuration

```json
{
  "age_bands": [
    {"band_id": 1, "band_label": "< 25", "min_value": 0, "max_value": 25, "display_order": 1},
    {"band_id": 2, "band_label": "25-34", "min_value": 25, "max_value": 35, "display_order": 2},
    {"band_id": 3, "band_label": "35+", "min_value": 35, "max_value": 999, "display_order": 3}
  ]
}
```

### Invalid: Gap

```json
{
  "age_bands": [
    {"band_id": 1, "band_label": "< 25", "min_value": 0, "max_value": 25, "display_order": 1},
    {"band_id": 2, "band_label": "26-34", "min_value": 26, "max_value": 35, "display_order": 2}
  ]
}
// Error: Gap between bands 1 and 2 (25 to 26)
```

### Invalid: Overlap

```json
{
  "age_bands": [
    {"band_id": 1, "band_label": "< 30", "min_value": 0, "max_value": 30, "display_order": 1},
    {"band_id": 2, "band_label": "25-34", "min_value": 25, "max_value": 35, "display_order": 2}
  ]
}
// Error: Overlap between bands 1 and 2 (25 to 30)
```
