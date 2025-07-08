# S050: Advanced Optimization Features

**Story Points**: 8
**Priority**: HIGH
**Dependencies**: S049 (Optimization Engine Robustness)

## Problem Statement

The current optimization engine lacks advanced features that would significantly improve convergence speed and analyst productivity:

1. **No Warm-Start**: Each optimization starts fresh, ignoring valuable historical data
2. **No Sensitivity Analysis**: Analysts can't see which parameters drive outcomes most
3. **Fixed Merit Distribution**: Hard-coded ratios (1.1x, 1.0x, 0.9x...) limit optimization space
4. **No Business Constraints**: Can't enforce realistic business rules during optimization

## Success Criteria

- [ ] Implement parameter cache with success/failure tracking
- [ ] Display gradient-based sensitivity metrics for all parameters
- [ ] Automatic initial guess selection based on historical success
- [ ] Configurable merit distribution and business constraints
- [ ] A/B test framework to validate synthetic vs real simulation correlation
- [ ] 50% reduction in average convergence time through warm-start

## Technical Design

### 1. Warm-Start Parameter Cache
```python
class OptimizationCache:
    def __init__(self, cache_dir="./optimization_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "parameter_history.json"

    def add_result(self, target_growth, params, objective_value, converged):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'target_growth': target_growth,
            'params': params,
            'objective_value': objective_value,
            'converged': converged,
            'distance_to_target': abs(objective_value)
        }
        # Append to cache with automatic pruning

    def get_best_initial_guess(self, target_growth, tolerance=0.5):
        """Find best historical params for similar target"""
        history = self.load_cache()
        similar = [h for h in history
                   if abs(h['target_growth'] - target_growth) < tolerance
                   and h['converged']]
        if similar:
            return min(similar, key=lambda x: x['objective_value'])['params']
        return None
```

### 2. Parameter Sensitivity Analysis
```python
def calculate_sensitivity(objective_func, params, epsilon=1e-4):
    """Calculate parameter sensitivities using finite differences"""
    base_value = objective_func(params)
    sensitivities = {}

    for i, param_name in enumerate(['cola', 'merit_avg', 'hire_adj']):
        params_plus = params.copy()
        params_plus[i] += epsilon

        gradient = (objective_func(params_plus) - base_value) / epsilon
        sensitivities[param_name] = {
            'gradient': gradient,
            'relative_impact': abs(gradient * params[i] / base_value),
            'direction': 'increase' if gradient < 0 else 'decrease'
        }

    return sensitivities
```

### 3. Configurable Merit Distribution
```python
class MeritDistribution:
    def __init__(self, strategy='linear'):
        self.strategy = strategy

    def distribute(self, avg_merit, num_levels=5):
        if self.strategy == 'linear':
            # Current hard-coded approach
            factors = [1.1, 1.0, 0.9, 0.8, 0.7]
        elif self.strategy == 'exponential':
            # Steeper drop for higher levels
            factors = [1.2, 1.0, 0.85, 0.7, 0.55]
        elif self.strategy == 'flat':
            # Equal merit for all levels
            factors = [1.0] * num_levels
        elif self.strategy == 'custom':
            # User-defined distribution
            factors = self.custom_factors

        return {i+1: avg_merit * f for i, f in enumerate(factors)}
```

### 4. Business Constraints Framework
```python
class OptimizationConstraints:
    def __init__(self):
        self.constraints = []

    def add_budget_constraint(self, max_total_increase=0.05):
        """Total compensation increase < 5%"""
        def constraint(params):
            cola, merit, hire = params
            total_impact = cola + merit * 0.8  # 80% get merit
            return max_total_increase - total_impact
        self.constraints.append(constraint)

    def add_retention_constraint(self, min_cola=0.01):
        """COLA must be at least 1% for retention"""
        def constraint(params):
            return params[0] - min_cola
        self.constraints.append(constraint)

    def get_scipy_constraints(self):
        return [{'type': 'ineq', 'fun': c} for c in self.constraints]
```

### 5. A/B Testing Framework
```python
class OptimizationABTest:
    def __init__(self, test_name, variants=['synthetic', 'real']):
        self.test_name = test_name
        self.variants = variants
        self.results = {v: [] for v in variants}

    def run_variant(self, variant, config):
        start_time = time.time()
        result = run_optimization(config, use_synthetic=(variant=='synthetic'))
        elapsed = time.time() - start_time

        self.results[variant].append({
            'converged': result['converged'],
            'iterations': result['iterations'],
            'final_error': result['objective_value'],
            'time_seconds': elapsed
        })

    def analyze(self):
        """Compare variants on speed, accuracy, convergence"""
        return {
            'convergence_rate': {
                v: sum(r['converged'] for r in self.results[v]) / len(self.results[v])
                for v in self.variants
            },
            'avg_iterations': {
                v: np.mean([r['iterations'] for r in self.results[v]])
                for v in self.variants
            },
            'avg_time': {
                v: np.mean([r['time_seconds'] for r in self.results[v]])
                for v in self.variants
            }
        }
```

## UI Enhancements

### Sensitivity Display
```python
st.subheader("📊 Parameter Sensitivity Analysis")
sensitivities = calculate_sensitivity(objective_func, current_params)

for param, data in sensitivities.items():
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(param.upper(), f"{data['gradient']:.4f}",
                  help="Rate of change in objective per unit parameter change")
    with col2:
        st.metric("Relative Impact", f"{data['relative_impact']:.1%}",
                  help="How much this parameter affects the outcome")
    with col3:
        st.metric("Recommendation", data['direction'].title(),
                  help="Direction to move parameter for improvement")
```

## Testing Requirements

- Test warm-start improves convergence time by >30%
- Test sensitivity calculations are numerically stable
- Test business constraints are properly enforced
- Test A/B framework produces statistically valid comparisons

## Implementation Notes

1. **Cache Management**: Auto-prune cache entries older than 30 days
2. **Sensitivity Updates**: Recalculate every 5 iterations to track changes
3. **Constraint Validation**: Verify all constraints are feasible before optimization
4. **A/B Sample Size**: Minimum 20 runs per variant for statistical validity

## Definition of Done

- [ ] Warm-start cache implemented and tested
- [ ] Sensitivity analysis UI integrated
- [ ] Configurable constraints framework complete
- [ ] A/B testing shows synthetic mode accuracy >85%
- [ ] Documentation includes constraint examples
- [ ] Performance improvements validated
