"""
Shared Parameter Schema Module for Fidelity PlanAlign Engine Optimization
Provides unified parameter definitions, validation, and transformation functions
for both compensation_tuning.py and advanced_optimization.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field, validator


class ParameterType(str, Enum):
    """Parameter data types supported by the system."""

    FLOAT = "float"
    PERCENTAGE = "percentage"
    MULTIPLIER = "multiplier"
    INTEGER = "integer"


class ParameterUnit(str, Enum):
    """Standard units for compensation parameters."""

    PERCENTAGE = "percentage"
    MULTIPLIER = "multiplier"
    CURRENCY = "currency"
    COUNT = "count"
    RATIO = "ratio"


class ParameterCategory(str, Enum):
    """Parameter groupings for UI organization."""

    MERIT = "merit"
    COLA = "cola"
    PROMOTION = "promotion"
    NEW_HIRE = "new_hire"
    TERMINATION = "termination"
    GENERAL = "general"


class RiskLevel(str, Enum):
    """Risk assessment levels for parameter values."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ParameterBounds:
    """Parameter bounds with validation logic."""

    min_value: float
    max_value: float
    default_value: float
    recommended_min: Optional[float] = None
    recommended_max: Optional[float] = None

    def __post_init__(self):
        """Validate bounds after initialization."""
        if self.min_value >= self.max_value:
            raise ValueError(
                f"min_value ({self.min_value}) must be less than max_value ({self.max_value})"
            )
        if not (self.min_value <= self.default_value <= self.max_value):
            raise ValueError(
                f"default_value ({self.default_value}) must be within bounds [{self.min_value}, {self.max_value}]"
            )

        # Set recommended bounds if not provided
        if self.recommended_min is None:
            self.recommended_min = (
                self.min_value + (self.max_value - self.min_value) * 0.1
            )
        if self.recommended_max is None:
            self.recommended_max = (
                self.max_value - (self.max_value - self.min_value) * 0.1
            )


@dataclass
class ParameterDefinition:
    """Complete parameter definition with metadata."""

    name: str
    display_name: str
    description: str
    category: ParameterCategory
    parameter_type: ParameterType
    unit: ParameterUnit
    bounds: ParameterBounds
    job_levels: List[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    event_types: List[str] = Field(default_factory=lambda: ["RAISE"])
    is_level_specific: bool = True
    validation_rules: Optional[Dict[str, Any]] = None
    business_impact: str = ""

    def get_parameter_names(self) -> List[str]:
        """Generate all parameter names for this definition."""
        if self.is_level_specific:
            return [f"{self.name}_level_{level}" for level in self.job_levels]
        else:
            return [self.name]

    def validate_value(
        self, value: float, level: Optional[int] = None
    ) -> Tuple[bool, List[str], RiskLevel]:
        """Validate a parameter value and return warnings/errors."""
        warnings = []
        errors = []

        # Basic bounds checking
        if value < self.bounds.min_value:
            errors.append(
                f"Value {value:.4f} below minimum {self.bounds.min_value:.4f}"
            )
        elif value > self.bounds.max_value:
            errors.append(
                f"Value {value:.4f} above maximum {self.bounds.max_value:.4f}"
            )

        # Risk assessment
        risk_level = self._assess_risk(value)

        # Recommended bounds warnings
        if value < self.bounds.recommended_min:
            warnings.append(
                f"Value {value:.4f} below recommended minimum {self.bounds.recommended_min:.4f}"
            )
        elif value > self.bounds.recommended_max:
            warnings.append(
                f"Value {value:.4f} above recommended maximum {self.bounds.recommended_max:.4f}"
            )

        # Category-specific validation
        if self.category == ParameterCategory.MERIT:
            if value > 0.10:  # 10%
                warnings.append("Merit rate above 10% may exceed budget guidelines")
            elif value < 0.01:  # 1%
                warnings.append("Merit rate below 1% may impact employee retention")

        elif self.category == ParameterCategory.COLA:
            if value > 0.06:  # 6%
                warnings.append("COLA rate above 6% is unusually high")
            elif value == 0:
                warnings.append(
                    "Zero COLA may indicate oversight - confirm intentional"
                )

        elif self.category == ParameterCategory.PROMOTION:
            if self.name == "promotion_probability" and value > 0.30:  # 30%
                warnings.append("Promotion probability above 30% may be unrealistic")
            elif self.name == "promotion_raise" and value > 0.25:  # 25%
                warnings.append("Promotion raise above 25% is very aggressive")

        is_valid = len(errors) == 0
        return is_valid, warnings + errors, risk_level

    def _assess_risk(self, value: float) -> RiskLevel:
        """Assess risk level based on parameter value."""
        # Calculate position within bounds
        bounds_range = self.bounds.max_value - self.bounds.min_value
        value_position = (value - self.bounds.min_value) / bounds_range

        # Risk based on how extreme the value is
        if value < self.bounds.recommended_min or value > self.bounds.recommended_max:
            if value_position < 0.1 or value_position > 0.9:
                return RiskLevel.HIGH
            else:
                return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW


class ParameterSchema:
    """Main parameter schema containing all parameter definitions."""

    def __init__(self):
        """Initialize the parameter schema with all standard parameters."""
        self._parameters = self._build_parameter_definitions()

    def _build_parameter_definitions(self) -> Dict[str, ParameterDefinition]:
        """Build the complete parameter schema."""
        parameters = {}

        # Merit Rate Parameters (by job level)
        merit_defaults = {1: 0.045, 2: 0.040, 3: 0.035, 4: 0.035, 5: 0.040}
        for level in range(1, 6):
            param_name = f"merit_rate_level_{level}"
            parameters[param_name] = ParameterDefinition(
                name="merit_rate",
                display_name=f"Merit Rate - Level {level}",
                description=f"Annual merit increase rate for job level {level}",
                category=ParameterCategory.MERIT,
                parameter_type=ParameterType.PERCENTAGE,
                unit=ParameterUnit.PERCENTAGE,
                bounds=ParameterBounds(
                    min_value=0.01,
                    max_value=0.12,
                    default_value=merit_defaults[level],
                    recommended_min=0.02,
                    recommended_max=0.08,
                ),
                job_levels=[level],
                business_impact="Directly affects annual compensation growth and employee satisfaction",
            )

        # COLA Rate Parameter (uniform across levels)
        parameters["cola_rate"] = ParameterDefinition(
            name="cola_rate",
            display_name="Cost of Living Adjustment",
            description="Annual cost of living adjustment applied to all employees",
            category=ParameterCategory.COLA,
            parameter_type=ParameterType.PERCENTAGE,
            unit=ParameterUnit.PERCENTAGE,
            bounds=ParameterBounds(
                min_value=0.0,
                max_value=0.08,
                default_value=0.025,
                recommended_min=0.015,
                recommended_max=0.05,
            ),
            job_levels=[1, 2, 3, 4, 5],
            is_level_specific=False,
            business_impact="Maintains purchasing power; affects all employees equally",
        )

        # New Hire Salary Adjustment
        parameters["new_hire_salary_adjustment"] = ParameterDefinition(
            name="new_hire_salary_adjustment",
            display_name="New Hire Salary Premium",
            description="Salary multiplier for new hires relative to existing employees",
            category=ParameterCategory.NEW_HIRE,
            parameter_type=ParameterType.MULTIPLIER,
            unit=ParameterUnit.MULTIPLIER,
            bounds=ParameterBounds(
                min_value=1.0,
                max_value=1.5,
                default_value=1.15,
                recommended_min=1.05,
                recommended_max=1.30,
            ),
            job_levels=[1, 2, 3, 4, 5],
            is_level_specific=False,
            event_types=["HIRE"],
            business_impact="Affects recruitment competitiveness and hiring costs",
        )

        # Promotion Probability Parameters
        promo_prob_defaults = {1: 0.12, 2: 0.08, 3: 0.05, 4: 0.02, 5: 0.01}
        for level in range(1, 6):
            param_name = f"promotion_probability_level_{level}"
            parameters[param_name] = ParameterDefinition(
                name="promotion_probability",
                display_name=f"Promotion Probability - Level {level}",
                description=f"Annual probability of promotion for level {level} employees",
                category=ParameterCategory.PROMOTION,
                parameter_type=ParameterType.PERCENTAGE,
                unit=ParameterUnit.PERCENTAGE,
                bounds=ParameterBounds(
                    min_value=0.0,
                    max_value=0.30,
                    default_value=promo_prob_defaults[level],
                    recommended_min=0.01,
                    recommended_max=0.20,
                ),
                job_levels=[level],
                event_types=["PROMOTION"],
                business_impact="Affects career progression and internal mobility",
            )

        # Promotion Raise Parameters
        for level in range(1, 6):
            param_name = f"promotion_raise_level_{level}"
            parameters[param_name] = ParameterDefinition(
                name="promotion_raise",
                display_name=f"Promotion Raise - Level {level}",
                description=f"Salary increase percentage when promoted from level {level}",
                category=ParameterCategory.PROMOTION,
                parameter_type=ParameterType.PERCENTAGE,
                unit=ParameterUnit.PERCENTAGE,
                bounds=ParameterBounds(
                    min_value=0.05,
                    max_value=0.30,
                    default_value=0.12,
                    recommended_min=0.08,
                    recommended_max=0.20,
                ),
                job_levels=[level],
                event_types=["PROMOTION"],
                business_impact="Incentivizes high performance and career advancement",
            )

        return parameters

    def get_parameter(self, name: str) -> Optional[ParameterDefinition]:
        """Get parameter definition by name."""
        return self._parameters.get(name)

    def get_parameters_by_category(
        self, category: ParameterCategory
    ) -> Dict[str, ParameterDefinition]:
        """Get all parameters in a specific category."""
        return {
            name: param
            for name, param in self._parameters.items()
            if param.category == category
        }

    def get_all_parameter_names(self) -> List[str]:
        """Get all parameter names in the schema."""
        return list(self._parameters.keys())

    def get_default_parameters(self) -> Dict[str, float]:
        """Get default values for all parameters."""
        return {
            name: param.bounds.default_value for name, param in self._parameters.items()
        }

    def validate_parameter_set(self, parameters: Dict[str, float]) -> Dict[str, Any]:
        """Validate a complete set of parameters."""
        results = {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "parameter_results": {},
            "overall_risk": RiskLevel.LOW,
        }

        risk_levels = []

        for param_name, value in parameters.items():
            param_def = self.get_parameter(param_name)
            if param_def:
                is_valid, messages, risk = param_def.validate_value(value)

                results["parameter_results"][param_name] = {
                    "is_valid": is_valid,
                    "messages": messages,
                    "risk_level": risk,
                    "value": value,
                }

                if not is_valid:
                    results["is_valid"] = False
                    results["errors"].extend(
                        [f"{param_name}: {msg}" for msg in messages]
                    )
                else:
                    results["warnings"].extend(
                        [f"{param_name}: {msg}" for msg in messages]
                    )

                risk_levels.append(risk)
            else:
                results["warnings"].append(f"Unknown parameter: {param_name}")

        # Calculate overall risk level
        if RiskLevel.CRITICAL in risk_levels:
            results["overall_risk"] = RiskLevel.CRITICAL
        elif RiskLevel.HIGH in risk_levels:
            results["overall_risk"] = RiskLevel.HIGH
        elif RiskLevel.MEDIUM in risk_levels:
            results["overall_risk"] = RiskLevel.MEDIUM
        else:
            results["overall_risk"] = RiskLevel.LOW

        return results

    def transform_to_compensation_tuning_format(
        self, parameters: Dict[str, float]
    ) -> Dict[str, Dict[int, float]]:
        """Transform parameters to compensation_tuning.py format."""
        result = {
            "merit_base": {},
            "cola_rate": {},
            "new_hire_salary_adjustment": {},
            "promotion_probability": {},
            "promotion_raise": {},
        }

        # Map merit rates
        for level in range(1, 6):
            merit_key = f"merit_rate_level_{level}"
            if merit_key in parameters:
                result["merit_base"][level] = parameters[merit_key]

        # Map COLA rate (uniform across levels)
        if "cola_rate" in parameters:
            for level in range(1, 6):
                result["cola_rate"][level] = parameters["cola_rate"]

        # Map new hire adjustment
        if "new_hire_salary_adjustment" in parameters:
            for level in range(1, 6):
                result["new_hire_salary_adjustment"][level] = parameters[
                    "new_hire_salary_adjustment"
                ]

        # Map promotion parameters
        for level in range(1, 6):
            prob_key = f"promotion_probability_level_{level}"
            raise_key = f"promotion_raise_level_{level}"

            if prob_key in parameters:
                result["promotion_probability"][level] = parameters[prob_key]

            if raise_key in parameters:
                result["promotion_raise"][level] = parameters[raise_key]

        return result

    def transform_from_compensation_tuning_format(
        self, comp_tuning_params: Dict[str, Dict[int, float]]
    ) -> Dict[str, float]:
        """Transform parameters from compensation_tuning.py format."""
        result = {}

        # Merit rates
        if "merit_base" in comp_tuning_params:
            for level, value in comp_tuning_params["merit_base"].items():
                result[f"merit_rate_level_{level}"] = value

        # COLA rate (take from level 1 as it's uniform)
        if "cola_rate" in comp_tuning_params and 1 in comp_tuning_params["cola_rate"]:
            result["cola_rate"] = comp_tuning_params["cola_rate"][1]

        # New hire adjustment (take from level 1 as it's uniform)
        if (
            "new_hire_salary_adjustment" in comp_tuning_params
            and 1 in comp_tuning_params["new_hire_salary_adjustment"]
        ):
            result["new_hire_salary_adjustment"] = comp_tuning_params[
                "new_hire_salary_adjustment"
            ][1]

        # Promotion parameters
        for param_type in ["promotion_probability", "promotion_raise"]:
            if param_type in comp_tuning_params:
                for level, value in comp_tuning_params[param_type].items():
                    result[f"{param_type}_level_{level}"] = value

        return result

    def get_parameter_groups(self) -> Dict[str, Dict[str, ParameterDefinition]]:
        """Get parameters organized by display groups for UI layout."""
        return {
            "Merit Rates": self.get_parameters_by_category(ParameterCategory.MERIT),
            "Cost of Living": self.get_parameters_by_category(ParameterCategory.COLA),
            "New Hire Parameters": self.get_parameters_by_category(
                ParameterCategory.NEW_HIRE
            ),
            "Promotion Probabilities": {
                k: v
                for k, v in self.get_parameters_by_category(
                    ParameterCategory.PROMOTION
                ).items()
                if "probability" in k
            },
            "Promotion Raises": {
                k: v
                for k, v in self.get_parameters_by_category(
                    ParameterCategory.PROMOTION
                ).items()
                if "raise" in k
            },
        }


# Singleton instance
_parameter_schema = None


def get_parameter_schema() -> ParameterSchema:
    """Get the singleton parameter schema instance."""
    global _parameter_schema
    if _parameter_schema is None:
        _parameter_schema = ParameterSchema()
    return _parameter_schema


# Convenience functions for backward compatibility
def load_parameter_schema() -> Dict[str, Dict[str, Any]]:
    """Load parameter schema in advanced_optimization.py format."""
    schema = get_parameter_schema()
    result = {}

    for param_name, param_def in schema._parameters.items():
        result[param_name] = {
            "type": param_def.parameter_type.value,
            "unit": param_def.unit.value,
            "range": [param_def.bounds.min_value, param_def.bounds.max_value],
            "description": param_def.description,
        }

    return result


def get_default_parameters() -> Dict[str, float]:
    """Get default parameter values."""
    return get_parameter_schema().get_default_parameters()


def validate_parameters(params: Dict[str, float]) -> Tuple[List[str], List[str]]:
    """Validate parameters and return warnings and errors."""
    schema = get_parameter_schema()
    results = schema.validate_parameter_set(params)
    return results["warnings"], results["errors"]


def assess_parameter_risk(params: Dict[str, float]) -> RiskLevel:
    """Assess overall risk level for parameter set."""
    schema = get_parameter_schema()
    results = schema.validate_parameter_set(params)
    return results["overall_risk"]


# Example usage and testing
if __name__ == "__main__":
    # Test the schema
    schema = get_parameter_schema()

    # Get default parameters
    defaults = schema.get_default_parameters()
    print("Default Parameters:")
    for name, value in defaults.items():
        print(f"  {name}: {value}")

    # Test validation
    test_params = defaults.copy()
    test_params["merit_rate_level_1"] = 0.15  # Above recommended max

    validation_results = schema.validate_parameter_set(test_params)
    print(f"\nValidation Results:")
    print(f"  Valid: {validation_results['is_valid']}")
    print(f"  Overall Risk: {validation_results['overall_risk']}")
    print(f"  Warnings: {len(validation_results['warnings'])}")
    print(f"  Errors: {len(validation_results['errors'])}")

    # Test format transformation
    comp_tuning_format = schema.transform_to_compensation_tuning_format(defaults)
    print(f"\nCompensation Tuning Format:")
    for category, values in comp_tuning_format.items():
        print(f"  {category}: {values}")
