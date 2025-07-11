# Story S074: Create Plan Configuration Schema

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 8
**Priority**: Medium

## Story

**As a** benefits analyst
**I want** YAML schema for plan design parameters
**So that** I can configure plans without code changes

## Business Context

This story establishes a comprehensive, type-safe configuration system for DC plan designs that allows benefits analysts to configure complex retirement plans through YAML without requiring code deployments. The schema supports all common 401(k) features while providing validation and documentation.

## Acceptance Criteria

### Core Configuration Features
- [ ] **YAML schema supports all common 401(k) features** including vesting schedules
- [ ] **Pydantic validation ensures configuration integrity** with detailed error messages
- [ ] **Documentation includes examples** for common plans and regulatory patterns
- [ ] **Support for effective-dated configuration changes** with version control
- [ ] **Template system for standard plan designs** with inheritance patterns

### Plan Features Coverage
- [ ] **Eligibility rules**: Age, service, hours requirements with flexible entry dates
- [ ] **Contribution types**: Pre-tax, Roth, after-tax, catch-up contributions
- [ ] **Matching formulas**: Complex multi-tier matching with true-up support
- [ ] **Vesting schedules**: Graded, cliff, and immediate vesting patterns
- [ ] **IRS compliance**: Automatic limit enforcement and validation
- [ ] **Scenario support**: Plan design variations within scenarios

## Technical Specifications

### Core Plan Configuration Schema
```yaml
# Example: Enhanced 401(k) Plan Configuration
plan_config:
  plan_id: "401k_enhanced"
  plan_name: "Enhanced 401(k) Plan"
  plan_year: 2025
  plan_type: "401(k)"
  effective_date: "2025-01-01"
  sponsor_ein: "12-3456789"

  # Plan Features
  features:
    roth: enabled
    after_tax: enabled
    catch_up: enabled
    hardship_withdrawals: enabled
    in_service_distributions: disabled
    auto_enrollment: enabled
    auto_escalation: enabled

  # Eligibility Rules
  eligibility:
    minimum_age: 21
    minimum_service_months: 12
    entry_dates: quarterly  # immediate, monthly, quarterly, semi-annual, annual
    hours_requirement: 1000
    excludes:
      - union_employees
      - leased_employees
      - nonresident_aliens

  # Auto-Enrollment Configuration
  auto_enrollment:
    enabled: true
    default_deferral_rate: 0.06
    default_investment: "target_date_fund"
    opt_out_window_days: 90
    escalation_enabled: true
    escalation_rate: 0.01
    escalation_frequency: annual
    escalation_max: 0.15

  # Vesting Schedule
  vesting:
    type: "graded"  # graded, cliff, immediate
    schedule:
      - years: 2
        percentage: 0.2
      - years: 3
        percentage: 0.4
      - years: 4
        percentage: 0.6
      - years: 5
        percentage: 0.8
      - years: 6
        percentage: 1.0
    service_computation_date: "hire_date"  # hire_date, plan_entry_date

  # Matching Formula
  matching:
    formula: "100% on first 3%, 50% on next 2%"
    enabled: true
    tiers:
      - employee_max: 0.03
        match_rate: 1.00
      - employee_max: 0.05
        match_rate: 0.50
    max_match_percentage: 0.04
    true_up: enabled
    true_up_frequency: annual
    eligibility_requirements:
      minimum_hours: 1000
      minimum_service_months: 12

  # Contribution Limits
  limits:
    employee_deferral: 23500  # 2025 limit
    catch_up: 7500
    annual_additions: 70000
    compensation: 350000

  # Investment Options
  investments:
    default_option: "target_date_fund"
    self_directed: enabled
    company_stock: disabled
    stable_value: enabled

  # Loan Provisions
  loans:
    enabled: true
    maximum_loans: 2
    minimum_amount: 1000
    maximum_percentage: 0.5
    repayment_frequency: payroll

  # Distribution Rules
  distributions:
    in_service_withdrawals:
      after_tax_only: true
      minimum_age: 59.5
    hardship_withdrawals:
      enabled: true
      requires_loan_first: false
      sources_available:
        - employee_pre_tax
        - employee_roth_contributions  # Not earnings
```

### Pydantic Validation Models
```python
from pydantic import BaseModel, Field, validator
from typing import Literal, List, Optional, Dict, Any
from decimal import Decimal
from datetime import date

class EligibilityConfig(BaseModel):
    minimum_age: int = Field(21, ge=18, le=65)
    minimum_service_months: int = Field(12, ge=0, le=24)
    entry_dates: Literal["immediate", "monthly", "quarterly", "semi-annual", "annual"] = "quarterly"
    hours_requirement: int = Field(1000, ge=0, le=2000)
    excludes: List[str] = Field(default_factory=list)

    @validator('excludes')
    def validate_exclusions(cls, v):
        valid_exclusions = [
            "union_employees", "leased_employees", "nonresident_aliens",
            "part_time", "seasonal", "contractors"
        ]
        for exclusion in v:
            if exclusion not in valid_exclusions:
                raise ValueError(f"Invalid exclusion: {exclusion}")
        return v

class VestingScheduleEntry(BaseModel):
    years: int = Field(..., ge=0, le=20)
    percentage: float = Field(..., ge=0, le=1)

class VestingConfig(BaseModel):
    type: Literal["graded", "cliff", "immediate"]
    schedule: List[VestingScheduleEntry] = Field(default_factory=list)
    service_computation_date: Literal["hire_date", "plan_entry_date"] = "hire_date"

    @validator('schedule')
    def validate_vesting_schedule(cls, v, values):
        if values.get('type') == 'immediate':
            return []

        if not v:
            raise ValueError("Vesting schedule required for non-immediate vesting")

        # Validate percentage progression
        for i, entry in enumerate(v):
            if i > 0 and entry.percentage <= v[i-1].percentage:
                raise ValueError("Vesting percentages must increase")

        # Final entry must be 100%
        if v and v[-1].percentage != 1.0:
            raise ValueError("Final vesting percentage must be 100%")

        return v

class MatchingTier(BaseModel):
    employee_max: float = Field(..., ge=0, le=1)
    match_rate: float = Field(..., ge=0, le=3)

class MatchingConfig(BaseModel):
    enabled: bool = True
    formula: str
    tiers: List[MatchingTier]
    max_match_percentage: float = Field(..., ge=0, le=0.25)
    true_up: Literal["enabled", "disabled"] = "enabled"
    true_up_frequency: Literal["annual", "quarterly"] = "annual"
    eligibility_requirements: Optional[Dict[str, Any]] = None

    @validator('tiers')
    def validate_matching_tiers(cls, v):
        if not v:
            raise ValueError("At least one matching tier required")

        # Validate tier progression
        for i, tier in enumerate(v):
            if i > 0 and tier.employee_max <= v[i-1].employee_max:
                raise ValueError("Employee contribution percentages must increase")

        return v

    @validator('max_match_percentage')
    def validate_max_match(cls, v, values):
        if 'tiers' in values:
            calculated_max = sum(
                (tier.employee_max - (values['tiers'][i-1].employee_max if i > 0 else 0)) * tier.match_rate
                for i, tier in enumerate(values['tiers'])
            )
            if abs(v - calculated_max) > 0.001:
                raise ValueError(f"Max match percentage {v} doesn't match calculated {calculated_max}")
        return v

class AutoEnrollmentConfig(BaseModel):
    enabled: bool = False
    default_deferral_rate: float = Field(0.03, ge=0, le=0.15)
    default_investment: str = "target_date_fund"
    opt_out_window_days: int = Field(90, ge=30, le=180)
    escalation_enabled: bool = False
    escalation_rate: float = Field(0.01, ge=0.005, le=0.02)
    escalation_frequency: Literal["annual", "semi-annual"] = "annual"
    escalation_max: float = Field(0.15, ge=0.10, le=0.25)

class PlanLimits(BaseModel):
    employee_deferral: int = Field(..., ge=15000, le=30000)
    catch_up: int = Field(..., ge=5000, le=10000)
    annual_additions: int = Field(..., ge=50000, le=100000)
    compensation: int = Field(..., ge=200000, le=500000)

    @validator('annual_additions')
    def validate_annual_additions(cls, v, values):
        if 'employee_deferral' in values and v <= values['employee_deferral']:
            raise ValueError("Annual additions limit must exceed employee deferral limit")
        return v

class PlanFeatures(BaseModel):
    roth: Literal["enabled", "disabled"] = "enabled"
    after_tax: Literal["enabled", "disabled"] = "disabled"
    catch_up: Literal["enabled", "disabled"] = "enabled"
    hardship_withdrawals: Literal["enabled", "disabled"] = "enabled"
    in_service_distributions: Literal["enabled", "disabled"] = "disabled"
    auto_enrollment: Literal["enabled", "disabled"] = "disabled"
    auto_escalation: Literal["enabled", "disabled"] = "disabled"

class PlanConfig(BaseModel):
    plan_id: str = Field(..., min_length=1, max_length=50)
    plan_name: str = Field(..., min_length=1, max_length=100)
    plan_year: int = Field(..., ge=2020, le=2050)
    plan_type: Literal["401(k)", "403(b)", "457(b)"] = "401(k)"
    effective_date: date
    sponsor_ein: str = Field(..., regex=r'^\d{2}-\d{7}$')

    features: PlanFeatures
    eligibility: EligibilityConfig
    auto_enrollment: Optional[AutoEnrollmentConfig] = None
    vesting: VestingConfig
    matching: MatchingConfig
    limits: PlanLimits

    # Scenario and design variation support
    scenario_id: Optional[str] = Field("baseline", min_length=1)
    plan_design_id: Optional[str] = Field("standard", min_length=1)
    base_plan_id: Optional[str] = None  # For plan variations
    design_variations: Optional[Dict[str, Any]] = None

    @validator('auto_enrollment')
    def validate_auto_enrollment_consistency(cls, v, values):
        if values.get('features', {}).auto_enrollment == "enabled" and not v:
            raise ValueError("Auto-enrollment config required when feature is enabled")
        return v

    @validator('effective_date')
    def validate_effective_date(cls, v, values):
        if 'plan_year' in values:
            expected_year = values['plan_year']
            if v.year != expected_year:
                raise ValueError(f"Effective date year {v.year} must match plan year {expected_year}")
        return v

    class Config:
        schema_extra = {
            "example": {
                "plan_id": "401k_standard",
                "plan_name": "Standard 401(k) Plan",
                "plan_year": 2025,
                "plan_type": "401(k)",
                "effective_date": "2025-01-01",
                "sponsor_ein": "12-3456789",
                "features": {
                    "roth": "enabled",
                    "after_tax": "disabled",
                    "catch_up": "enabled"
                },
                "eligibility": {
                    "minimum_age": 21,
                    "minimum_service_months": 12,
                    "entry_dates": "quarterly",
                    "hours_requirement": 1000
                },
                "vesting": {
                    "type": "graded",
                    "schedule": [
                        {"years": 2, "percentage": 0.2},
                        {"years": 6, "percentage": 1.0}
                    ]
                },
                "matching": {
                    "enabled": True,
                    "formula": "100% on first 3%",
                    "tiers": [{"employee_max": 0.03, "match_rate": 1.0}],
                    "max_match_percentage": 0.03,
                    "true_up": "enabled"
                },
                "limits": {
                    "employee_deferral": 23500,
                    "catch_up": 7500,
                    "annual_additions": 70000,
                    "compensation": 350000
                }
            }
        }
```

### Plan Template System
```python
class PlanTemplate(BaseModel):
    template_id: str
    template_name: str
    description: str
    category: Literal["safe_harbor", "traditional", "startup", "enterprise"]
    base_config: PlanConfig
    customizable_fields: List[str]
    regulatory_notes: List[str]

# Standard Plan Templates
PLAN_TEMPLATES = {
    "safe_harbor_basic": PlanTemplate(
        template_id="safe_harbor_basic",
        template_name="Safe Harbor 401(k) - Basic Match",
        description="Basic safe harbor plan with 100% match on first 3%",
        category="safe_harbor",
        base_config=PlanConfig(
            plan_id="safe_harbor_basic",
            plan_name="Safe Harbor 401(k) Plan",
            plan_year=2025,
            matching=MatchingConfig(
                formula="100% on first 3%",
                tiers=[{"employee_max": 0.03, "match_rate": 1.0}],
                max_match_percentage=0.03,
                true_up="enabled"
            ),
            vesting=VestingConfig(type="immediate"),
            features=PlanFeatures(auto_enrollment="enabled")
        ),
        customizable_fields=["eligibility.minimum_age", "auto_enrollment.default_deferral_rate"],
        regulatory_notes=["Satisfies ADP/ACP safe harbor requirements", "Annual notice required"]
    ),

    "traditional_graded": PlanTemplate(
        template_id="traditional_graded",
        template_name="Traditional 401(k) - Graded Vesting",
        description="Traditional plan with graded vesting and enhanced match",
        category="traditional",
        base_config=PlanConfig(
            plan_id="traditional_graded",
            plan_name="Traditional 401(k) Plan",
            plan_year=2025,
            matching=MatchingConfig(
                formula="100% on first 3%, 50% on next 2%",
                tiers=[
                    {"employee_max": 0.03, "match_rate": 1.0},
                    {"employee_max": 0.05, "match_rate": 0.5}
                ],
                max_match_percentage=0.04,
                true_up="enabled"
            ),
            vesting=VestingConfig(
                type="graded",
                schedule=[
                    {"years": 2, "percentage": 0.2},
                    {"years": 3, "percentage": 0.4},
                    {"years": 4, "percentage": 0.6},
                    {"years": 5, "percentage": 0.8},
                    {"years": 6, "percentage": 1.0}
                ]
            )
        ),
        customizable_fields=["matching.tiers", "vesting.schedule"],
        regulatory_notes=["Subject to ADP/ACP testing", "Top-heavy testing required"]
    )
}
```

### Configuration Loading and Validation
```python
import yaml
from pathlib import Path
from typing import Dict, List

class PlanConfigurationManager:
    """Manages loading, validation, and versioning of plan configurations"""

    def __init__(self, config_directory: Path):
        self.config_directory = config_directory
        self.templates = PLAN_TEMPLATES

    def load_plan_config(self, plan_id: str, plan_year: int) -> PlanConfig:
        """Load and validate plan configuration from YAML"""
        config_file = self.config_directory / f"{plan_id}_{plan_year}.yaml"

        if not config_file.exists():
            raise FileNotFoundError(f"Plan configuration not found: {config_file}")

        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        try:
            plan_config = PlanConfig(**config_data['plan_config'])
            return plan_config
        except ValidationError as e:
            raise ValueError(f"Invalid plan configuration: {e}")

    def create_from_template(self, template_id: str, customizations: Dict[str, Any]) -> PlanConfig:
        """Create plan configuration from template with customizations"""
        if template_id not in self.templates:
            raise ValueError(f"Unknown template: {template_id}")

        template = self.templates[template_id]
        base_config = template.base_config.dict()

        # Apply customizations
        for field_path, value in customizations.items():
            self._set_nested_field(base_config, field_path, value)

        return PlanConfig(**base_config)

    def validate_plan_variations(self, base_plan: PlanConfig, variations: List[Dict[str, Any]]) -> List[PlanConfig]:
        """Validate multiple plan design variations"""
        validated_plans = []

        for variation in variations:
            variation_config = base_plan.dict()
            variation_config.update(variation)

            try:
                validated_plan = PlanConfig(**variation_config)
                validated_plans.append(validated_plan)
            except ValidationError as e:
                raise ValueError(f"Invalid plan variation {variation.get('plan_design_id', 'unknown')}: {e}")

        return validated_plans

    def _set_nested_field(self, data: Dict, field_path: str, value: Any):
        """Set nested field value using dot notation"""
        keys = field_path.split('.')
        current = data

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
```

## Implementation Tasks

### Phase 1: Core Schema Definition
- [ ] **Define Pydantic models** for all plan configuration components
- [ ] **Create comprehensive validation rules** with detailed error messages
- [ ] **Implement YAML loading utilities** with error handling
- [ ] **Add schema documentation** with examples

### Phase 2: Template System
- [ ] **Create standard plan templates** for common configurations
- [ ] **Implement template inheritance** and customization system
- [ ] **Add regulatory compliance validation** for template combinations
- [ ] **Create template documentation** with use cases

### Phase 3: Integration and Testing
- [ ] **Integrate with dbt models** for plan parameter resolution
- [ ] **Add comprehensive unit tests** covering all validation scenarios
- [ ] **Create integration tests** with plan simulation pipeline
- [ ] **Implement configuration versioning** and migration support

## Dependencies

- **S072**: Retirement Plan Event Schema (uses plan configurations)
- **S073**: dbt Models for Plan Data (consumes configuration data)
- **IRS regulatory requirements**: Annual limit updates
- **YAML/JSON processing libraries**: PyYAML, Pydantic

## Success Metrics

### Usability Requirements
- [ ] **Configuration completeness**: Support for 95% of common 401(k) features
- [ ] **Validation accuracy**: Zero false positives/negatives in validation
- [ ] **Documentation quality**: Complete examples for all template types
- [ ] **Error messaging**: Clear, actionable error messages for analysts

### Technical Requirements
- [ ] **Loading performance**: <100ms to load and validate plan configuration
- [ ] **Memory efficiency**: <10MB memory usage for complex plan configurations
- [ ] **Template coverage**: Templates available for all major plan types
- [ ] **Backward compatibility**: Configuration format versioning support

## Definition of Done

- [ ] **Complete Pydantic schema** supporting all 401(k) features
- [ ] **Template system implemented** with standard plan templates
- [ ] **Validation framework** with comprehensive error handling
- [ ] **YAML configuration loading** with proper error reporting
- [ ] **Integration verified** with plan simulation pipeline
- [ ] **Comprehensive testing** covering edge cases and validation scenarios
- [ ] **Documentation complete** with examples and regulatory guidance
- [ ] **Analyst training materials** created for configuration management
