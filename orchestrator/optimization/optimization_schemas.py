"""
Optimization schemas and data contracts for S047 optimization engine.
API versioning ensures backwards compatibility.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Literal
from datetime import datetime

class OptimizationRequest(BaseModel):
    """Optimization request configuration."""

    schema_version: str = Field(default="1.0.0", description="API schema version")
    scenario_id: str = Field(..., description="Unique scenario identifier")

    initial_parameters: Dict[str, float] = Field(
        ...,
        description="Starting parameter values",
        example={
            "merit_rate_level_1": 0.045,  # 4.5% (percentage, range: [0.02, 0.08])
            "cola_rate": 0.025,           # 2.5% (percentage, range: [0.0, 0.05])
            "promotion_rate_level_1": 0.15 # 15% (percentage, range: [0.0, 0.30])
        }
    )

    objectives: Dict[str, float] = Field(
        default={"cost": 0.4, "equity": 0.3, "targets": 0.3},
        description="Objective weights (must sum to 1.0)"
    )

    method: str = Field(default="SLSQP", description="Optimization algorithm")
    max_evaluations: int = Field(default=20, ge=5, le=1000, description="Maximum function evaluations")
    timeout_minutes: int = Field(default=60, ge=5, le=240, description="Maximum runtime")
    random_seed: Optional[int] = Field(default=42, description="Random seed for reproducibility")
    use_synthetic: bool = Field(default=True, description="Use synthetic objective functions for fast testing")

class OptimizationResult(BaseModel):
    """Optimization result with comprehensive metadata."""

    schema_version: str = Field(default="1.0.0", description="API schema version")
    scenario_id: str
    converged: bool

    optimal_parameters: Dict[str, float] = Field(
        ...,
        description="Optimized parameter values"
    )

    objective_value: float
    algorithm_used: str
    iterations: int
    function_evaluations: int
    runtime_seconds: float

    # Business impact with units
    estimated_cost_impact: Dict[str, Any] = Field(
        description="Cost impact with units",
        example={"value": 2450000.0, "unit": "USD", "confidence": "high"}
    )
    estimated_employee_impact: Dict[str, Any] = Field(
        description="Employee impact with metadata",
        example={"count": 1200, "percentage_of_workforce": 0.85, "risk_level": "medium"}
    )

    risk_assessment: Literal["LOW", "MEDIUM", "HIGH"]
    constraint_violations: Dict[str, float]
    solution_quality_score: float  # 0-1 scale

    # Evidence report generation
    evidence_report_url: Optional[str] = Field(description="Auto-generated MDX report URL")

    # Sensitivity analysis results
    parameter_sensitivities: Optional[Dict[str, float]] = Field(
        default=None,
        description="Parameter sensitivity coefficients"
    )

class OptimizationError(BaseModel):
    """Error result for failed optimizations."""

    schema_version: str = Field(default="1.0.0")
    scenario_id: str
    error_type: Literal["INFEASIBLE", "TIMEOUT", "NUMERICAL", "CONSTRAINT"]
    error_message: str
    best_found_solution: Optional[Dict[str, float]]
    recommendations: List[str]

# Parameter metadata with inline bounds and units
PARAMETER_SCHEMA = {
    "merit_rate_level_1": {
        "type": "float",
        "unit": "percentage",
        "range": [0.02, 0.08],
        "description": "Staff merit increase rate"
    },
    "merit_rate_level_2": {
        "type": "float",
        "unit": "percentage",
        "range": [0.025, 0.085],
        "description": "Senior merit increase rate"
    },
    "merit_rate_level_3": {
        "type": "float",
        "unit": "percentage",
        "range": [0.03, 0.09],
        "description": "Manager merit increase rate"
    },
    "merit_rate_level_4": {
        "type": "float",
        "unit": "percentage",
        "range": [0.035, 0.095],
        "description": "Director merit increase rate"
    },
    "merit_rate_level_5": {
        "type": "float",
        "unit": "percentage",
        "range": [0.04, 0.10],
        "description": "VP merit increase rate"
    },
    "cola_rate": {
        "type": "float",
        "unit": "percentage",
        "range": [0.0, 0.05],
        "description": "Cost of living adjustment"
    },
    "new_hire_salary_adjustment": {
        "type": "float",
        "unit": "multiplier",
        "range": [1.0, 1.30],
        "description": "New hire salary premium"
    },
    "promotion_probability_level_1": {
        "type": "float",
        "unit": "percentage",
        "range": [0.0, 0.30],
        "description": "Staff promotion probability"
    },
    "promotion_probability_level_2": {
        "type": "float",
        "unit": "percentage",
        "range": [0.0, 0.25],
        "description": "Senior promotion probability"
    },
    "promotion_probability_level_3": {
        "type": "float",
        "unit": "percentage",
        "range": [0.0, 0.20],
        "description": "Manager promotion probability"
    },
    "promotion_probability_level_4": {
        "type": "float",
        "unit": "percentage",
        "range": [0.0, 0.15],
        "description": "Director promotion probability"
    },
    "promotion_probability_level_5": {
        "type": "float",
        "unit": "percentage",
        "range": [0.0, 0.10],
        "description": "VP promotion probability"
    },
    "promotion_raise_level_1": {
        "type": "float",
        "unit": "percentage",
        "range": [0.08, 0.20],
        "description": "Staff promotion raise"
    },
    "promotion_raise_level_2": {
        "type": "float",
        "unit": "percentage",
        "range": [0.08, 0.20],
        "description": "Senior promotion raise"
    },
    "promotion_raise_level_3": {
        "type": "float",
        "unit": "percentage",
        "range": [0.08, 0.20],
        "description": "Manager promotion raise"
    },
    "promotion_raise_level_4": {
        "type": "float",
        "unit": "percentage",
        "range": [0.08, 0.20],
        "description": "Director promotion raise"
    },
    "promotion_raise_level_5": {
        "type": "float",
        "unit": "percentage",
        "range": [0.08, 0.20],
        "description": "VP promotion raise"
    }
}

class OptimizationCache:
    """Simple in-memory cache for function evaluations."""

    def __init__(self):
        self.cache: Dict[str, float] = {}
        self.hits = 0
        self.misses = 0

    def get_cache_key(self, parameters: Dict[str, float]) -> str:
        """Generate cache key from parameters."""
        # Sort by key to ensure consistent hashing
        sorted_params = sorted(parameters.items())
        return str(hash(tuple(sorted_params)))

    def get(self, parameters: Dict[str, float]) -> Optional[float]:
        """Get cached objective value."""
        key = self.get_cache_key(parameters)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, parameters: Dict[str, float], value: float):
        """Cache objective value."""
        key = self.get_cache_key(parameters)
        self.cache[key] = value

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
