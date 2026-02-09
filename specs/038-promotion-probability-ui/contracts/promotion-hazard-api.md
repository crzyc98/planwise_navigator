# API Contract: Promotion Hazard Configuration

## New Endpoints

Two new endpoints following the band configuration pattern.

### GET `/{workspace_id}/config/promotion-hazards`

**Summary**: Retrieve current promotion hazard parameters from dbt seed files.

**Response** (`PromotionHazardConfig`):

```json
{
  "base": {
    "base_rate": 0.02,
    "level_dampener_factor": 0.15
  },
  "age_multipliers": [
    { "age_band": "< 25", "multiplier": 1.6 },
    { "age_band": "25-34", "multiplier": 1.4 },
    { "age_band": "35-44", "multiplier": 1.1 },
    { "age_band": "45-54", "multiplier": 0.7 },
    { "age_band": "55-64", "multiplier": 0.3 },
    { "age_band": "65+", "multiplier": 0.1 }
  ],
  "tenure_multipliers": [
    { "tenure_band": "< 2", "multiplier": 0.5 },
    { "tenure_band": "2-4", "multiplier": 1.5 },
    { "tenure_band": "5-9", "multiplier": 1.8 },
    { "tenure_band": "10-19", "multiplier": 0.8 },
    { "tenure_band": "20+", "multiplier": 0.2 }
  ]
}
```

**Error responses**:
- `500`: CSV file not found or malformed

### PUT `/{workspace_id}/config/promotion-hazards`

**Summary**: Validate and save promotion hazard parameters to dbt seed files.

**Request body** (`PromotionHazardConfig`): Same structure as GET response.

**Response** (`PromotionHazardSaveResponse`):

```json
{
  "success": true,
  "errors": [],
  "message": "Promotion hazard configurations saved successfully"
}
```

**Validation failure response**:

```json
{
  "success": false,
  "errors": [
    "base_rate must be between 0 and 1",
    "Age multiplier for band '25-34' must be non-negative"
  ],
  "message": "Validation failed - see errors for details"
}
```

## Pydantic Models

### PromotionHazardBase

```python
class PromotionHazardBase(BaseModel):
    base_rate: float = Field(..., ge=0, le=1, description="Base promotion rate (0.0-1.0)")
    level_dampener_factor: float = Field(..., ge=0, le=1, description="Level dampening factor (0.0-1.0)")
```

### PromotionHazardAgeMultiplier

```python
class PromotionHazardAgeMultiplier(BaseModel):
    age_band: str = Field(..., description="Age band label (read-only)")
    multiplier: float = Field(..., ge=0, description="Promotion hazard multiplier")
```

### PromotionHazardTenureMultiplier

```python
class PromotionHazardTenureMultiplier(BaseModel):
    tenure_band: str = Field(..., description="Tenure band label (read-only)")
    multiplier: float = Field(..., ge=0, description="Promotion hazard multiplier")
```

### PromotionHazardConfig

```python
class PromotionHazardConfig(BaseModel):
    base: PromotionHazardBase
    age_multipliers: List[PromotionHazardAgeMultiplier]
    tenure_multipliers: List[PromotionHazardTenureMultiplier]
```

### PromotionHazardSaveResponse

```python
class PromotionHazardSaveResponse(BaseModel):
    success: bool
    errors: List[str] = Field(default_factory=list)
    message: str
```

## Router Registration

```python
# In planalign_api/main.py
app.include_router(promotion_hazard_router, prefix="/api/workspaces", tags=["Promotion Hazard"])
```
