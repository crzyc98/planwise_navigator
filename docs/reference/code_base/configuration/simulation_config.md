# simulation_config.yaml - Primary Simulation Configuration

## Purpose

The `config/simulation_config.yaml` file serves as the central configuration hub for Fidelity PlanAlign Engine, defining all parameters that control workforce simulation behavior, including growth targets, termination rates, promotion probabilities, and data quality thresholds.

## Architecture

This configuration file uses a hierarchical YAML structure with validation through Pydantic models, ensuring type safety and parameter consistency across the entire simulation pipeline.

## Key Components

### Simulation Control
```yaml
simulation:
  start_year: 2025              # Simulation starting year
  end_year: 2029                # Final simulation year
  random_seed: 42               # Reproducibility seed
  validation_enabled: true      # Enable/disable validation checks
```

### Workforce Dynamics
```yaml
workforce:
  target_growth_rate: 0.03      # 3% annual workforce growth
  total_termination_rate: 0.12  # 12% overall annual turnover
  new_hire_termination_rate: 0.25  # 25% first-year turnover
  backfill_percentage: 1.0      # 100% backfill terminated positions
```

### Promotion Parameters
```yaml
promotion:
  base_rate: 0.15               # 15% eligible for promotion
  level_caps:                   # Maximum promotions per level
    1: 0.20                     # 20% of L1 can promote to L2
    2: 0.15                     # 15% of L2 can promote to L3
    3: 0.10                     # 10% of L3 can promote to L4
    4: 0.05                     # 5% of L4 can promote to L5
  minimum_tenure_months:        # Required tenure for promotion
    1: 12                       # L1 -> L2: 12 months
    2: 18                       # L2 -> L3: 18 months
    3: 24                       # L3 -> L4: 24 months
    4: 36                       # L4 -> L5: 36 months
```

### Compensation Settings
```yaml
compensation:
  cola_rate: 0.025              # 2.5% cost of living adjustment
  merit_budget: 0.04            # 4% of payroll for merit raises
  promotion_increase: 0.15      # 15% salary increase on promotion
  merit_increase_range:
    min: 0.02                   # Minimum 2% merit increase
    max: 0.08                   # Maximum 8% merit increase
```

### Data Quality Thresholds
```yaml
validation:
  growth_rate_tolerance: 0.005  # ±0.5% tolerance for growth targets
  termination_rate_tolerance: 0.01  # ±1% tolerance for termination rates
  max_workforce_change: 0.50    # Maximum 50% workforce change per year
  min_headcount: 100            # Minimum viable workforce size
```

## Configuration Sections

### 1. Simulation Control
Controls the basic simulation parameters and execution settings.

**Key Parameters:**
- `start_year`: Initial year for simulation (typically current year + 1)
- `end_year`: Final projection year (usually 3-10 years forward)
- `random_seed`: Fixed seed for reproducible results in testing
- `validation_enabled`: Toggle for data quality checks

### 2. Workforce Dynamics
Defines the fundamental workforce behavior patterns.

**Growth Management:**
- `target_growth_rate`: Desired annual workforce expansion
- `backfill_percentage`: Replacement rate for departed employees
- `hiring_seasonality`: Optional monthly hiring patterns

**Turnover Modeling:**
- `total_termination_rate`: Overall annual turnover percentage
- `new_hire_termination_rate`: Higher turnover for recent hires
- `voluntary_vs_involuntary`: Split between resignation and termination

### 3. Career Progression
Controls promotion rates and career advancement patterns.

**Promotion Rates:**
- `base_rate`: Overall promotion eligibility percentage
- `level_caps`: Limits on promotions per organizational level
- `performance_multipliers`: Adjustment factors for performance ratings

**Tenure Requirements:**
- `minimum_tenure_months`: Required service time for promotion eligibility
- `accelerated_promotion`: Criteria for fast-track advancement

### 4. Compensation Management
Manages salary adjustments and budget allocation.

**Annual Adjustments:**
- `cola_rate`: Cost of living increases applied to all employees
- `merit_budget`: Total budget available for performance-based raises
- `promotion_increase`: Standard salary lift for promotions

**Merit Distribution:**
- `merit_increase_range`: Min/max bounds for individual merit raises
- `budget_allocation_method`: Algorithm for distributing merit budget

## Usage Examples

### Basic Configuration
```yaml
# Minimal configuration for testing
simulation:
  start_year: 2025
  end_year: 2027
  random_seed: 12345

workforce:
  target_growth_rate: 0.02
  total_termination_rate: 0.10
```

### Production Configuration
```yaml
simulation:
  start_year: 2025
  end_year: 2030
  random_seed: null  # Use random seed
  validation_enabled: true

workforce:
  target_growth_rate: 0.035
  total_termination_rate: 0.125
  new_hire_termination_rate: 0.28
  hiring_constraints:
    max_monthly_hires: 50
    budget_cap: 15000000
```

### Scenario Planning
```yaml
# Conservative growth scenario
scenarios:
  conservative:
    workforce:
      target_growth_rate: 0.015
      total_termination_rate: 0.15

  # Aggressive growth scenario
  aggressive:
    workforce:
      target_growth_rate: 0.05
      total_termination_rate: 0.08
```

## Dependencies

### Configuration Validation
- **Pydantic Models**: Type checking and validation
- **Custom Validators**: Business rule enforcement
- **Environment Overrides**: Runtime parameter adjustment

### Integration Points
- **dbt Variables**: Configuration values passed to SQL models
- **Dagster Resources**: Pipeline parameter injection
- **Dashboard Controls**: UI parameter modification

## Common Issues

### Parameter Validation Errors
**Problem**: Configuration values outside acceptable ranges
**Solution**: Check validation rules and business constraints

```yaml
# Example validation error
workforce:
  target_growth_rate: 1.5  # ERROR: >100% growth not realistic

# Corrected version
workforce:
  target_growth_rate: 0.15  # 15% growth is reasonable
```

### Inconsistent Growth Targets
**Problem**: Termination and hiring rates don't achieve growth targets
**Solution**: Balance termination rates with hiring capacity

```yaml
# Ensure net growth = hiring - terminations + backfill
workforce:
  target_growth_rate: 0.03      # Want 3% growth
  total_termination_rate: 0.12  # 12% turnover
  # Need ~15% hiring rate to achieve net 3% growth
```

### Configuration Conflicts
**Problem**: Parameters conflict across sections
**Solution**: Use configuration validation and dependency checks

## Related Files

### Configuration Management
- `config/multi_year_config.yaml` - Multi-year simulation parameters
- `config/test_config.yaml` - Testing scenarios
- `config/dashboard_config.yaml` - Dashboard-specific settings

### Integration Files
- `orchestrator/utils/config_loader.py` - Configuration loading utilities
- `dbt/dbt_project.yml` - dbt variable integration
- `definitions.py` - Dagster resource configuration

### Validation Components
- `orchestrator/assets/validation.py` - Configuration validation assets
- `scripts/validation_checks.py` - Parameter validation utilities
- `tests/test_config.py` - Configuration testing

## Implementation Notes

### Configuration Hierarchy
1. **Default Values**: Built-in reasonable defaults
2. **Environment Overrides**: Runtime parameter adjustment
3. **Scenario Configs**: Named parameter sets for what-if analysis
4. **User Customization**: Dashboard-driven parameter modification

### Performance Considerations
- Cache parsed configuration to avoid repeated YAML parsing
- Validate configuration once at startup, not during execution
- Use configuration-driven model selection for performance optimization

### Security Guidelines
- Never store sensitive data in configuration files
- Use environment variables for credentials and secrets
- Implement access controls for configuration modification
- Audit configuration changes for compliance
