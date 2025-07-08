# Optimization Schemas Guide

## Overview

The `optimization_schemas.py` module provides a unified parameter schema system for PlanWise Navigator's compensation optimization interfaces. It standardizes parameter definitions, validation, and format transformations between `advanced_optimization.py` and `compensation_tuning.py`.

## Key Features

- **Unified Parameter Definitions**: Single source of truth for all compensation parameters
- **Type-Safe Validation**: Pydantic-based validation with comprehensive error handling
- **Risk Assessment**: Automatic risk level calculation based on parameter values
- **Format Transformation**: Seamless conversion between different parameter formats
- **Business Impact Analysis**: Built-in metadata for business impact assessment
- **Extensible Design**: Easy to add new parameters and validation rules

## Parameter Structure

### Parameter Categories

| Category | Description | Parameters |
|----------|-------------|------------|
| `MERIT` | Annual merit increase rates | `merit_rate_level_1` through `merit_rate_level_5` |
| `COLA` | Cost of living adjustments | `cola_rate` |
| `NEW_HIRE` | New hire compensation parameters | `new_hire_salary_adjustment` |
| `PROMOTION` | Promotion probabilities and raises | `promotion_probability_level_*`, `promotion_raise_level_*` |

### Parameter Types and Units

- **Percentage**: Merit rates, COLA rates, promotion probabilities (0.0-1.0 range)
- **Multiplier**: Salary adjustments (1.0+ range)
- **Currency**: Future support for absolute dollar amounts
- **Count**: Future support for headcount parameters

## Usage Examples

### For Advanced Optimization Interface

```python
from optimization_schemas import load_parameter_schema, get_default_parameters

# Load schema in advanced_optimization.py format
schema = load_parameter_schema()
defaults = get_default_parameters()

# Use in Streamlit sliders
for param_name, param_info in schema.items():
    value = st.slider(
        param_name,
        min_value=param_info["range"][0],
        max_value=param_info["range"][1],
        value=defaults[param_name],
        help=param_info["description"]
    )
```

### For Compensation Tuning Interface

```python
from optimization_schemas import get_parameter_schema

schema = get_parameter_schema()

# Get parameters in compensation_tuning.py format
defaults = schema.get_default_parameters()
comp_format = schema.transform_to_compensation_tuning_format(defaults)

# Use with existing comp_levers.csv structure
for category, values in comp_format.items():
    for level, value in values.items():
        print(f"{category} Level {level}: {value}")

# Convert back after modifications
modified_standard = schema.transform_from_compensation_tuning_format(comp_format)
```

### Parameter Validation

```python
from optimization_schemas import get_parameter_schema, validate_parameters

schema = get_parameter_schema()

# Validate parameter set
test_params = {
    'merit_rate_level_1': 0.08,  # 8% merit increase
    'cola_rate': 0.035,          # 3.5% COLA
    # ... other parameters
}

# Method 1: Simple validation
warnings, errors = validate_parameters(test_params)
if errors:
    print("Validation errors:", errors)

# Method 2: Comprehensive validation
results = schema.validate_parameter_set(test_params)
print(f"Valid: {results['is_valid']}")
print(f"Risk Level: {results['overall_risk']}")
print(f"Warnings: {len(results['warnings'])}")
```

### Risk Assessment

```python
from optimization_schemas import assess_parameter_risk, RiskLevel

risk = assess_parameter_risk(test_params)

if risk == RiskLevel.HIGH:
    print("⚠️ High risk parameters detected!")
elif risk == RiskLevel.MEDIUM:
    print("🔶 Medium risk - review recommended")
else:
    print("✅ Low risk parameters")
```

## Parameter Definitions

### Merit Rate Parameters

| Parameter | Job Level | Default | Range | Recommended Range |
|-----------|-----------|---------|-------|-------------------|
| `merit_rate_level_1` | Staff | 4.5% | 1.0% - 12.0% | 2.0% - 8.0% |
| `merit_rate_level_2` | Senior | 4.0% | 1.0% - 12.0% | 2.0% - 8.0% |
| `merit_rate_level_3` | Manager | 3.5% | 1.0% - 12.0% | 2.0% - 8.0% |
| `merit_rate_level_4` | Director | 3.5% | 1.0% - 12.0% | 2.0% - 8.0% |
| `merit_rate_level_5` | VP | 4.0% | 1.0% - 12.0% | 2.0% - 8.0% |

### General Compensation Parameters

| Parameter | Default | Range | Recommended Range | Description |
|-----------|---------|-------|-------------------|-------------|
| `cola_rate` | 2.5% | 0.0% - 8.0% | 1.5% - 5.0% | Annual cost of living adjustment |
| `new_hire_salary_adjustment` | 115% | 100% - 150% | 105% - 130% | New hire salary premium |

### Promotion Parameters

| Parameter Type | Default | Range | Recommended Range |
|----------------|---------|-------|-------------------|
| **Promotion Probabilities** | | | |
| Level 1 | 12.0% | 0.0% - 30.0% | 1.0% - 20.0% |
| Level 2 | 8.0% | 0.0% - 30.0% | 1.0% - 20.0% |
| Level 3 | 5.0% | 0.0% - 30.0% | 1.0% - 20.0% |
| Level 4 | 2.0% | 0.0% - 30.0% | 1.0% - 20.0% |
| Level 5 | 1.0% | 0.0% - 30.0% | 1.0% - 20.0% |
| **Promotion Raises** | | | |
| All Levels | 12.0% | 5.0% - 30.0% | 8.0% - 20.0% |

## Validation Rules

### Merit Rate Validation
- **High Warning**: Merit rate > 10% may exceed budget guidelines
- **Low Warning**: Merit rate < 1% may impact employee retention
- **Error**: Merit rate outside absolute bounds [1%, 12%]

### COLA Validation
- **High Warning**: COLA rate > 6% is unusually high
- **Zero Warning**: Zero COLA may indicate oversight
- **Error**: COLA rate outside bounds [0%, 8%]

### Promotion Validation
- **Probability Warning**: Promotion probability > 30% may be unrealistic
- **Raise Warning**: Promotion raise > 25% is very aggressive
- **Error**: Values outside absolute bounds

### Risk Level Assessment

| Risk Level | Criteria | Action Required |
|------------|----------|-----------------|
| **LOW** | All parameters within recommended ranges | None - safe to proceed |
| **MEDIUM** | Some parameters outside recommended ranges | Review and justify |
| **HIGH** | Parameters near absolute bounds | Careful review required |
| **CRITICAL** | Parameters violate absolute bounds | Must fix before proceeding |

## Format Transformations

### Advanced Optimization Format
```python
{
    'merit_rate_level_1': 0.045,
    'merit_rate_level_2': 0.040,
    'cola_rate': 0.025,
    'new_hire_salary_adjustment': 1.15,
    'promotion_probability_level_1': 0.12,
    'promotion_raise_level_1': 0.12,
    # ... etc
}
```

### Compensation Tuning Format
```python
{
    'merit_base': {1: 0.045, 2: 0.040, 3: 0.035, 4: 0.035, 5: 0.040},
    'cola_rate': {1: 0.025, 2: 0.025, 3: 0.025, 4: 0.025, 5: 0.025},
    'new_hire_salary_adjustment': {1: 1.15, 2: 1.15, 3: 1.15, 4: 1.15, 5: 1.15},
    'promotion_probability': {1: 0.12, 2: 0.08, 3: 0.05, 4: 0.02, 5: 0.01},
    'promotion_raise': {1: 0.12, 2: 0.12, 3: 0.12, 4: 0.12, 5: 0.12}
}
```

## Integration with Existing Systems

### Database Integration (comp_levers.csv)

The schema supports transformation to the database format used in `comp_levers.csv`:

```csv
scenario_id,fiscal_year,job_level,event_type,parameter_name,parameter_value,is_locked,created_at,created_by
default,2025,1,RAISE,merit_base,0.045,1,2025-07-01,optimizer
default,2025,1,RAISE,cola_rate,0.025,1,2025-07-01,optimizer
default,2025,1,HIRE,new_hire_salary_adjustment,1.15,1,2025-07-01,optimizer
default,2025,1,PROMOTION,promotion_probability,0.12,1,2025-07-01,optimizer
default,2025,1,PROMOTION,promotion_raise,0.12,1,2025-07-01,optimizer
```

### dbt Model Integration

The schema aligns with the `int_effective_parameters` dbt model structure:

```sql
SELECT
    scenario_id,
    fiscal_year,
    job_level,
    event_type,
    parameter_name,
    parameter_value,
    is_locked
FROM {{ ref('stg_comp_levers') }}
WHERE scenario_id = 'default'
    AND fiscal_year BETWEEN {{ var('start_year') }} AND {{ var('end_year') }}
```

## Extending the Schema

### Adding New Parameters

1. **Define the parameter** in `ParameterSchema._build_parameter_definitions()`:

```python
parameters["new_parameter"] = ParameterDefinition(
    name="new_parameter",
    display_name="New Parameter",
    description="Description of the new parameter",
    category=ParameterCategory.GENERAL,
    parameter_type=ParameterType.PERCENTAGE,
    unit=ParameterUnit.PERCENTAGE,
    bounds=ParameterBounds(
        min_value=0.0,
        max_value=1.0,
        default_value=0.5,
        recommended_min=0.1,
        recommended_max=0.9
    ),
    business_impact="Business impact description"
)
```

2. **Add validation rules** in `ParameterDefinition.validate_value()` if needed.

3. **Update format transformations** in transform methods if the parameter needs special handling.

### Adding New Validation Rules

Custom validation can be added to `ParameterDefinition.validate_value()`:

```python
# Category-specific validation
if self.category == ParameterCategory.NEW_CATEGORY:
    if value > threshold:
        warnings.append("Custom warning message")
```

### Adding New Parameter Categories

1. Add to `ParameterCategory` enum
2. Update `get_parameter_groups()` method
3. Add category-specific validation rules

## Testing

Run the comprehensive test suite:

```bash
python tests/test_optimization_schemas.py
```

Test categories:
- **Parameter Bounds Validation**: Ensures bounds logic works correctly
- **Parameter Definition**: Tests parameter name generation and validation
- **Schema Functionality**: Tests the main schema operations
- **Format Transformations**: Validates round-trip transformations
- **Integration Scenarios**: Tests realistic usage patterns
- **Risk Assessment**: Validates risk level calculations

## Performance Considerations

- **Singleton Pattern**: Schema instance is cached for performance
- **Validation Caching**: Consider caching validation results for repeated parameter sets
- **Memory Usage**: Schema definitions are lightweight and loaded once
- **Computation**: Validation is fast (< 1ms for typical parameter sets)

## Migration Guide

### From advanced_optimization.py

Replace the local `load_parameter_schema()` function:

```python
# Old approach
@st.cache_data
def load_parameter_schema():
    return {
        "merit_rate_level_1": {"type": "float", "unit": "percentage", ...}
    }

# New approach
from optimization_schemas import load_parameter_schema
schema = load_parameter_schema()  # Now uses shared schema
```

### From compensation_tuning.py

Update parameter loading and validation:

```python
# Old approach
def load_current_parameters():
    # Custom parameter loading logic
    pass

# New approach
from optimization_schemas import get_parameter_schema

schema = get_parameter_schema()
defaults = schema.get_default_parameters()
comp_format = schema.transform_to_compensation_tuning_format(defaults)
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `streamlit_dashboard` is in Python path
2. **Parameter Not Found**: Check parameter name spelling and case
3. **Validation Failures**: Check parameter values are within absolute bounds
4. **Format Transformation Issues**: Ensure all required parameters are present

### Debug Tools

```python
# Check available parameters
schema = get_parameter_schema()
print("Available parameters:", schema.get_all_parameter_names())

# Validate individual parameter
param_def = schema.get_parameter("merit_rate_level_1")
is_valid, messages, risk = param_def.validate_value(0.05)
print(f"Valid: {is_valid}, Messages: {messages}, Risk: {risk}")

# Check parameter groups
groups = schema.get_parameter_groups()
for group_name, params in groups.items():
    print(f"{group_name}: {len(params)} parameters")
```

## Future Enhancements

- **Dynamic Parameter Loading**: Load parameters from database or configuration files
- **Historical Parameter Tracking**: Track parameter changes over time
- **Advanced Risk Models**: More sophisticated risk assessment algorithms
- **Parameter Dependencies**: Support for parameters that depend on other parameters
- **Optimization Constraints**: Built-in support for optimization constraints
- **Scenario Templates**: Pre-defined parameter sets for common scenarios

---

*This guide covers the optimization_schemas.py module as of PlanWise Navigator v1.0.0. For updates and additional examples, see the `examples/` directory.*
