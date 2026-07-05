# filename: config/schema.py
"""Configuration schema for Fidelity PlanAlign Engine."""

from datetime import date, datetime
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, validator


class SimulationConfig(BaseModel):
    """Primary simulation configuration."""

    # Simulation parameters
    start_year: int = Field(..., ge=2020, le=2050, description="Simulation start year")
    end_year: int = Field(..., ge=2020, le=2050, description="Simulation end year")
    random_seed: int = Field(42, ge=1, description="Random seed for reproducibility")

    # Workforce parameters
    target_growth_rate: float = Field(
        0.03, ge=-0.5, le=0.5, description="Annual workforce growth rate"
    )
    total_termination_rate: float = Field(
        0.12, ge=0.0, le=1.0, description="Overall annual termination rate"
    )
    new_hire_termination_rate: float = Field(
        0.25, ge=0.0, le=1.0, description="First-year termination rate"
    )

    # Promotion parameters
    promotion_budget_pct: float = Field(
        0.15, ge=0.0, le=0.5, description="Percent of workforce eligible for promotion"
    )
    promotion_level_caps: Dict[int, float] = Field(
        default_factory=lambda: {
            1: 0.20,  # L1 -> L2
            2: 0.15,  # L2 -> L3
            3: 0.10,  # L3 -> L4
            4: 0.05,  # L4 -> L5
        },
        description="Maximum promotion rates by level",
    )

    # Compensation parameters
    cola_rate: float = Field(
        0.025, ge=0.0, le=0.10, description="Cost of living adjustment"
    )
    merit_budget_pct: float = Field(
        0.04, ge=0.0, le=0.10, description="Merit increase budget as % of payroll"
    )
    promotion_increase_pct: float = Field(
        0.15, ge=0.0, le=0.50, description="Salary increase on promotion"
    )

    @validator("end_year")
    def validate_end_year(cls, v, values):
        if "start_year" in values and v <= values["start_year"]:
            raise ValueError("end_year must be after start_year")
        return v

    @validator("new_hire_termination_rate")
    def validate_new_hire_term_rate(cls, v, values):
        if "total_termination_rate" in values and v < values["total_termination_rate"]:
            raise ValueError(
                "new_hire_termination_rate should be >= total_termination_rate"
            )
        return v

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationConfig":
        """Create SimulationConfig from dict, filtering unknown keys.

        This classmethod robustly handles config dicts that may contain unknown keys
        from scenario overrides (Studio) or config merging. Unknown keys are silently
        filtered before model construction.

        Args:
            data: Dictionary that may contain known SimulationConfig fields plus
                  extra keys from scenario overrides or config merging

        Returns:
            Reconstructed SimulationConfig instance with validation applied

        Raises:
            ValidationError: If required fields are missing or values are invalid

        Example:
            >>> config_dict = {"start_year": 2025, "end_year": 2026, "extra_key": "ignored"}
            >>> config = SimulationConfig.from_dict(config_dict)
            >>> config.start_year
            2025
        """
        # Filter to known fields only - silently drop unknown keys
        known_fields = cls.model_fields.keys()
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        # Construct with Pydantic validation
        return cls(**filtered_data)

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
        }


class LevelConfig(BaseModel):
    """Job level configuration."""

    level_id: int = Field(..., ge=1, le=5)
    level_name: str
    min_salary: float = Field(..., ge=0)
    max_salary: float = Field(..., ge=0)

    @validator("max_salary")
    def validate_salary_range(cls, v, values):
        if "min_salary" in values and v <= values["min_salary"]:
            raise ValueError("max_salary must be greater than min_salary")
        return v


class HazardConfig(BaseModel):
    """Hazard table configuration."""

    event_type: Literal["promotion", "termination", "merit"]
    level_id: int = Field(..., ge=1, le=5)
    base_rate: float = Field(..., ge=0.0, le=1.0)
    age_multipliers: Optional[Dict[str, float]] = None
    tenure_multipliers: Optional[Dict[str, float]] = None


class EmployeeRecord(BaseModel):
    """Employee data model."""

    employee_id: str
    level_id: int = Field(..., ge=1, le=5)
    age: int = Field(..., ge=18, le=100)
    tenure: float = Field(..., ge=0)
    compensation: float = Field(..., ge=0)
    hire_date: date
    active_flag: bool = True

    class Config:
        json_encoders = {date: lambda v: v.isoformat()}


class SimulationEvent(BaseModel):
    """Workforce event model."""

    event_id: str
    employee_id: str
    event_type: Literal["hire", "promotion", "termination", "merit"]
    effective_date: date
    simulation_year: int
    old_value: Optional[float] = None
    new_value: Optional[float] = None

    class Config:
        json_encoders = {date: lambda v: v.isoformat()}


class SimulationMetrics(BaseModel):
    """Simulation output metrics."""

    simulation_year: int
    total_headcount: int
    headcount_by_level: Dict[int, int]
    total_compensation: float
    avg_compensation: float
    events_summary: Dict[str, int]
    growth_rate_actual: float
    termination_rate_actual: float

    class Config:
        json_encoders = {float: lambda v: round(v, 2)}
