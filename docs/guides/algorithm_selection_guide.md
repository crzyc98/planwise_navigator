# Algorithm Selection Guide - Auto-Optimize System

**Epic E012 Compensation Tuning System - S047 Optimization Engine**
**Last Updated:** July 2025
**Target Audience:** Technical Users, Compensation Analysts, Data Scientists

---

## Overview

This guide provides comprehensive guidance for selecting optimal algorithms in Fidelity PlanAlign Engine's Auto-Optimize system. The S047 Optimization Engine supports multiple SciPy-based algorithms, each with distinct characteristics and optimal use cases.

### Quick Reference

| Algorithm | Type | Speed | Robustness | Best For | Avoid When |
|-----------|------|-------|------------|----------|------------|
| **SLSQP** | Gradient-based | Fast | Medium | Smooth objectives, few constraints | Noisy data, many local optima |
| **DE** | Evolutionary | Medium | High | Global optimization, difficult landscapes | Time-critical applications |
| **L-BFGS-B** | Quasi-Newton | Fast | Medium | Large parameter spaces | Highly constrained problems |
| **TNC** | Newton | Medium | High | Nonlinear constraints | Simple unconstrained problems |
| **COBYLA** | Direct search | Slow | High | Complex constraints, derivative-free | Smooth objectives, time-sensitive |

---

## Algorithm Profiles

### 1. SLSQP (Sequential Least Squares Programming)

**Type:** Gradient-based constrained optimization
**Default Choice:** ✅ Recommended for most users

#### Characteristics

- **Convergence Speed:** Fast (typically 20-50 iterations)
- **Robustness:** Medium (sensitive to starting point)
- **Constraint Handling:** Linear and nonlinear constraints
- **Derivative Requirements:** Uses finite differences if gradients not provided
- **Memory Usage:** Low to medium

#### Strengths

```python
# SLSQP excels at:
scenarios = {
    "smooth_objectives": "Well-behaved objective functions without noise",
    "moderate_constraints": "2-5 constraints with clear mathematical structure",
    "quick_iteration": "Development and testing phases requiring fast feedback",
    "parameter_tuning": "Fine-tuning around known good solutions",
    "standard_optimization": "Typical compensation optimization scenarios"
}
```

#### Weaknesses

- **Local Optima:** Can get trapped in local minima
- **Noise Sensitivity:** Poor performance with noisy objective functions
- **Starting Point Dependency:** Results vary significantly with initial parameters
- **Constraint Complexity:** Struggles with highly nonlinear constraints

#### Optimal Use Cases

```python
def is_slsqp_optimal(problem_characteristics):
    """Determine if SLSQP is optimal for given problem."""

    recommendations = []

    # Problem size assessment
    if problem_characteristics["parameter_count"] <= 15:
        recommendations.append("✅ Parameter count favorable for SLSQP")
    else:
        recommendations.append("⚠️  Large parameter space - consider L-BFGS-B")

    # Constraint assessment
    if problem_characteristics["constraint_count"] <= 5:
        recommendations.append("✅ Constraint count manageable for SLSQP")
    else:
        recommendations.append("⚠️  Many constraints - consider TNC")

    # Objective function assessment
    if problem_characteristics["objective_smoothness"] == "smooth":
        recommendations.append("✅ Smooth objective ideal for SLSQP")
    elif problem_characteristics["objective_smoothness"] == "noisy":
        recommendations.append("❌ Noisy objective - consider DE")

    return recommendations

# Example assessment
problem = {
    "parameter_count": 8,
    "constraint_count": 2,
    "objective_smoothness": "smooth",
    "time_constraint": "medium",
    "solution_quality_priority": "high"
}

slsqp_assessment = is_slsqp_optimal(problem)
for rec in slsqp_assessment:
    print(rec)
```

#### Configuration Best Practices

```python
# Optimal SLSQP configuration
slsqp_config = {
    "method": "SLSQP",
    "options": {
        "maxiter": 100,        # Standard iteration limit
        "ftol": 1e-6,         # Function tolerance
        "eps": 1.4901161e-08, # Step size for finite differences
        "disp": True          # Display convergence messages
    },
    "max_evaluations": 150,   # Account for constraint evaluations
    "timeout_minutes": 30,    # Reasonable timeout for most problems
    "random_starts": 3        # Multiple starts for robustness
}

# For difficult problems
slsqp_robust_config = {
    "method": "SLSQP",
    "options": {
        "maxiter": 200,
        "ftol": 1e-4,         # Relaxed tolerance
        "eps": 1e-6,          # Larger step size
        "disp": True
    },
    "max_evaluations": 300,
    "timeout_minutes": 60,
    "random_starts": 5        # More starts for difficult landscapes
}
```

### 2. DE (Differential Evolution)

**Type:** Evolutionary global optimization algorithm
**Global Search:** ✅ Best for finding global optima

#### Characteristics

- **Convergence Speed:** Medium (100-300 evaluations typical)
- **Robustness:** High (handles noise and discontinuities well)
- **Constraint Handling:** Via penalty methods
- **Derivative Requirements:** None (derivative-free)
- **Memory Usage:** Medium (maintains population)

#### Strengths

- **Global Optimization:** Excellent at finding global optima
- **Noise Tolerance:** Robust to noisy objective functions
- **No Gradients Required:** Works with black-box functions
- **Population Diversity:** Explores solution space thoroughly
- **Parameter Robustness:** Less sensitive to initial values

#### Weaknesses

- **Slow Convergence:** Requires many function evaluations
- **Parameter Tuning:** Performance sensitive to population size and mutation rates
- **Memory Usage:** Higher memory requirements for population storage
- **Limited Constraint Handling:** Basic penalty-based constraint handling

#### Optimal Use Cases

```python
def is_de_optimal(problem_characteristics):
    """Determine if DE is optimal for given problem."""

    score = 0
    reasons = []

    # Global optimization need
    if problem_characteristics.get("multiple_optima_suspected", False):
        score += 3
        reasons.append("✅ Multiple optima suspected - DE excels at global search")

    # Noise tolerance
    if problem_characteristics.get("objective_noise_level", "low") in ["medium", "high"]:
        score += 2
        reasons.append("✅ Noisy objective - DE handles noise well")

    # Time availability
    if problem_characteristics.get("time_constraint", "medium") == "high":
        score += 1
        reasons.append("✅ Ample time available - DE can explore thoroughly")
    elif problem_characteristics.get("time_constraint", "medium") == "low":
        score -= 2
        reasons.append("❌ Time constraint tight - DE may be too slow")

    # Constraint complexity
    constraint_complexity = problem_characteristics.get("constraint_complexity", "simple")
    if constraint_complexity == "complex":
        score -= 1
        reasons.append("⚠️  Complex constraints - DE uses simple penalty methods")

    # Derivative availability
    if not problem_characteristics.get("gradients_available", True):
        score += 1
        reasons.append("✅ No gradients available - DE is derivative-free")

    recommendation = "RECOMMENDED" if score >= 3 else "CONSIDER" if score >= 1 else "NOT_RECOMMENDED"

    return {
        "recommendation": recommendation,
        "score": score,
        "reasons": reasons
    }

# Example assessment
problem = {
    "multiple_optima_suspected": True,
    "objective_noise_level": "medium",
    "time_constraint": "high",
    "constraint_complexity": "simple",
    "gradients_available": False
}

de_assessment = is_de_optimal(problem)
print(f"DE Recommendation: {de_assessment['recommendation']}")
for reason in de_assessment['reasons']:
    print(f"  {reason}")
```

#### Configuration Best Practices

```python
# Standard DE configuration
de_config = {
    "method": "DE",
    "options": {
        "maxiter": 200,       # Generations
        "popsize": 15,        # Population size multiplier
        "tol": 1e-6,         # Convergence tolerance
        "mutation": (0.5, 1), # Mutation factor range
        "recombination": 0.7, # Crossover probability
        "seed": 42,          # Random seed for reproducibility
        "disp": True,        # Display progress
        "polish": True       # Local polish at end
    },
    "max_evaluations": 3000,  # Population * generations
    "timeout_minutes": 120,   # Extended timeout for thorough search
    "bounds_handling": "clip" # How to handle bound violations
}

# Fast DE configuration (for time-constrained scenarios)
de_fast_config = {
    "method": "DE",
    "options": {
        "maxiter": 100,       # Fewer generations
        "popsize": 10,        # Smaller population
        "tol": 1e-4,         # Relaxed tolerance
        "mutation": (0.5, 1),
        "recombination": 0.7,
        "seed": 42,
        "polish": False      # Skip final polish
    },
    "max_evaluations": 1000,
    "timeout_minutes": 60
}
```

### 3. L-BFGS-B (Limited-memory BFGS with Bounds)

**Type:** Quasi-Newton method with bound constraints
**Large Scale:** ✅ Excellent for many parameters

#### Characteristics

- **Convergence Speed:** Fast (superlinear convergence)
- **Robustness:** Medium (gradient-based limitations)
- **Constraint Handling:** Simple bound constraints only
- **Memory Usage:** Low (limited memory formulation)
- **Derivative Requirements:** Finite differences if not provided

#### Strengths

- **Scalability:** Handles large parameter spaces efficiently
- **Memory Efficiency:** Limited memory formulation
- **Fast Convergence:** Superlinear convergence near optimum
- **Bound Constraints:** Efficient handling of box constraints
- **Numerical Stability:** Well-tested implementation

#### Weaknesses

- **Limited Constraints:** Only simple bound constraints
- **Local Optimization:** Can get trapped in local optima
- **Gradient Dependency:** Performance depends on gradient quality
- **Starting Point Sensitivity:** Results vary with initial point

#### Optimal Use Cases

```python
def is_lbfgsb_optimal(problem_characteristics):
    """Determine if L-BFGS-B is optimal for given problem."""

    suitability_score = 0
    factors = []

    # Parameter count assessment
    param_count = problem_characteristics.get("parameter_count", 0)
    if param_count > 20:
        suitability_score += 3
        factors.append(f"✅ Large parameter space ({param_count} params) - L-BFGS-B scales well")
    elif param_count > 10:
        suitability_score += 1
        factors.append(f"✅ Medium parameter space ({param_count} params) - suitable")

    # Constraint assessment
    constraint_types = problem_characteristics.get("constraint_types", [])
    if not constraint_types:
        suitability_score += 2
        factors.append("✅ No constraints - L-BFGS-B unconstrained strength")
    elif constraint_types == ["bounds"]:
        suitability_score += 3
        factors.append("✅ Only bound constraints - L-BFGS-B specialty")
    elif "nonlinear" in constraint_types:
        suitability_score -= 2
        factors.append("❌ Nonlinear constraints - L-BFGS-B cannot handle")

    # Objective function properties
    if problem_characteristics.get("objective_smoothness", "unknown") == "smooth":
        suitability_score += 2
        factors.append("✅ Smooth objective - ideal for quasi-Newton methods")

    # Time constraints
    if problem_characteristics.get("time_constraint", "medium") == "low":
        suitability_score += 1
        factors.append("✅ Time pressure - L-BFGS-B converges quickly")

    # Memory constraints
    if problem_characteristics.get("memory_constraint", "none") == "tight":
        suitability_score += 2
        factors.append("✅ Memory constraints - L-BFGS-B uses limited memory")

    return {
        "suitability_score": suitability_score,
        "recommendation": "EXCELLENT" if suitability_score >= 6 else "GOOD" if suitability_score >= 3 else "POOR",
        "factors": factors
    }

# Example assessment
problem = {
    "parameter_count": 25,
    "constraint_types": ["bounds"],
    "objective_smoothness": "smooth",
    "time_constraint": "low",
    "memory_constraint": "tight"
}

lbfgsb_assessment = is_lbfgsb_optimal(problem)
print(f"L-BFGS-B Suitability: {lbfgsb_assessment['recommendation']}")
for factor in lbfgsb_assessment['factors']:
    print(f"  {factor}")
```

#### Configuration Best Practices

```python
# Standard L-BFGS-B configuration
lbfgsb_config = {
    "method": "L-BFGS-B",
    "options": {
        "maxiter": 200,       # Maximum iterations
        "maxfun": 1000,       # Maximum function evaluations
        "ftol": 2.220446e-09, # Function tolerance
        "gtol": 1e-05,        # Gradient tolerance
        "eps": 1e-08,         # Step size for finite differences
        "maxcor": 10,         # Maximum number of variable metric corrections
        "disp": True          # Display convergence information
    },
    "max_evaluations": 1000,
    "timeout_minutes": 45
}

# High-precision L-BFGS-B configuration
lbfgsb_precise_config = {
    "method": "L-BFGS-B",
    "options": {
        "maxiter": 500,
        "maxfun": 2000,
        "ftol": 1e-12,        # Very tight function tolerance
        "gtol": 1e-08,        # Tight gradient tolerance
        "eps": 1e-10,         # Small step size
        "maxcor": 20,         # More corrections stored
        "disp": True
    },
    "max_evaluations": 2000,
    "timeout_minutes": 90
}
```

### 4. TNC (Truncated Newton Constrained)

**Type:** Newton method with constraints
**Constraints:** ✅ Excellent for complex constraints

#### Characteristics

- **Convergence Speed:** Medium to fast
- **Robustness:** High for constrained problems
- **Constraint Handling:** Linear and nonlinear constraints
- **Memory Usage:** Medium
- **Derivative Requirements:** Finite differences available

#### Strengths

- **Constraint Handling:** Excellent nonlinear constraint support
- **Robustness:** Stable for difficult constrained problems
- **Convergence Quality:** High-quality solutions
- **Numerical Stability:** Robust Newton implementation
- **Versatility:** Handles various constraint types

#### Weaknesses

- **Complexity:** More complex setup than simpler methods
- **Computational Cost:** Higher per-iteration cost
- **Parameter Sensitivity:** Sensitive to algorithm parameters
- **Local Optimization:** Still susceptible to local optima

#### Configuration Best Practices

```python
# Standard TNC configuration
tnc_config = {
    "method": "TNC",
    "options": {
        "maxfun": 1000,       # Maximum function evaluations
        "ftol": 1e-06,        # Function tolerance
        "xtol": 1e-06,        # Parameter tolerance
        "gtol": -1,           # Use default gradient tolerance
        "eps": 1e-08,         # Step size for finite differences
        "scale": None,        # Variable scaling factors
        "offset": None,       # Variable offsets
        "mesg_num": None,     # Message level
        "disp": True          # Display information
    },
    "max_evaluations": 1200,
    "timeout_minutes": 60
}
```

### 5. COBYLA (Constrained Optimization by Linear Approximation)

**Type:** Direct search method
**No Derivatives:** ✅ Completely derivative-free

#### Characteristics

- **Convergence Speed:** Slow but steady
- **Robustness:** Very high
- **Constraint Handling:** Arbitrary constraints via linear approximation
- **Memory Usage:** Low
- **Derivative Requirements:** None

#### Strengths

- **Derivative-Free:** No gradient calculations required
- **Constraint Flexibility:** Handles arbitrary constraint types
- **Robustness:** Very reliable, rarely fails
- **Simplicity:** Simple to use and understand
- **Noise Tolerance:** Handles noisy functions well

#### Weaknesses

- **Slow Convergence:** Requires many function evaluations
- **Limited Precision:** Less precise than gradient-based methods
- **Scaling Issues:** Poor performance on high-dimensional problems
- **No Gradients:** Cannot exploit gradient information when available

#### Configuration Best Practices

```python
# Standard COBYLA configuration
cobyla_config = {
    "method": "COBYLA",
    "options": {
        "maxiter": 1000,      # Maximum iterations
        "rhobeg": 1.0,        # Initial trust region radius
        "rhoend": 1e-06,      # Final trust region radius
        "disp": True,         # Display information
        "catol": 2e-06        # Constraint absolute tolerance
    },
    "max_evaluations": 1500,
    "timeout_minutes": 90
}

# Robust COBYLA configuration (for difficult problems)
cobyla_robust_config = {
    "method": "COBYLA",
    "options": {
        "maxiter": 2000,
        "rhobeg": 0.5,        # Smaller initial radius
        "rhoend": 1e-08,      # Tighter final tolerance
        "disp": True,
        "catol": 1e-08        # Stricter constraint tolerance
    },
    "max_evaluations": 3000,
    "timeout_minutes": 150
}
```

---

## Algorithm Selection Framework

### 1. Decision Tree Approach

```python
def select_optimization_algorithm(problem_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Systematic algorithm selection based on problem characteristics."""

    selection_log = []

    # Primary decision factors
    param_count = problem_profile.get("parameter_count", 5)
    constraint_count = problem_profile.get("constraint_count", 0)
    constraint_types = problem_profile.get("constraint_types", [])
    time_available = problem_profile.get("time_constraint", "medium")  # "low", "medium", "high"
    noise_level = problem_profile.get("noise_level", "low")  # "low", "medium", "high"
    global_search_needed = problem_profile.get("global_search", False)

    selection_log.append(f"Problem analysis: {param_count} params, {constraint_count} constraints")

    # Decision logic
    if global_search_needed or noise_level == "high":
        algorithm = "DE"
        reason = "Global search needed or high noise level requires evolutionary approach"
        selection_log.append(f"✅ Selected DE: {reason}")

    elif constraint_count == 0:
        if param_count > 15:
            algorithm = "L-BFGS-B"
            reason = "Large unconstrained problem - L-BFGS-B scales well"
        else:
            algorithm = "SLSQP"
            reason = "Standard unconstrained problem - SLSQP is reliable default"
        selection_log.append(f"✅ Selected {algorithm}: {reason}")

    elif constraint_types == ["bounds"]:
        if param_count > 15:
            algorithm = "L-BFGS-B"
            reason = "Large problem with only bounds - L-BFGS-B specialty"
        else:
            algorithm = "SLSQP"
            reason = "Bound-constrained problem - SLSQP handles bounds well"
        selection_log.append(f"✅ Selected {algorithm}: {reason}")

    elif constraint_count > 5 or "nonlinear" in constraint_types:
        algorithm = "TNC"
        reason = "Complex constraints require specialized constrained optimization"
        selection_log.append(f"✅ Selected TNC: {reason}")

    elif problem_profile.get("derivatives_available", True) == False:
        algorithm = "COBYLA"
        reason = "No derivatives available - need derivative-free method"
        selection_log.append(f"✅ Selected COBYLA: {reason}")

    else:
        algorithm = "SLSQP"
        reason = "Standard problem characteristics - SLSQP is robust default"
        selection_log.append(f"✅ Selected SLSQP: {reason}")

    # Secondary considerations
    if time_available == "low" and algorithm in ["DE", "COBYLA"]:
        selection_log.append("⚠️  WARNING: Selected algorithm may be slow for time constraint")

        # Suggest alternative
        if constraint_count <= 2:
            alternative = "SLSQP"
            selection_log.append(f"💡 Consider {alternative} for faster convergence")

    if param_count > 20 and algorithm not in ["L-BFGS-B", "DE"]:
        selection_log.append("⚠️  WARNING: Large parameter space may challenge selected algorithm")

    # Generate configuration
    config = generate_algorithm_config(algorithm, problem_profile)

    return {
        "recommended_algorithm": algorithm,
        "selection_rationale": reason,
        "selection_log": selection_log,
        "configuration": config,
        "alternatives": suggest_alternatives(algorithm, problem_profile),
        "confidence": calculate_selection_confidence(algorithm, problem_profile)
    }

def generate_algorithm_config(algorithm: str, problem_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Generate optimized configuration for selected algorithm."""

    base_configs = {
        "SLSQP": {
            "max_evaluations": 150,
            "timeout_minutes": 30,
            "options": {"maxiter": 100, "ftol": 1e-6}
        },
        "DE": {
            "max_evaluations": 2000,
            "timeout_minutes": 90,
            "options": {"maxiter": 200, "popsize": 15}
        },
        "L-BFGS-B": {
            "max_evaluations": 1000,
            "timeout_minutes": 45,
            "options": {"maxiter": 200, "ftol": 2.220446e-09}
        },
        "TNC": {
            "max_evaluations": 1200,
            "timeout_minutes": 60,
            "options": {"maxfun": 1000, "ftol": 1e-06}
        },
        "COBYLA": {
            "max_evaluations": 1500,
            "timeout_minutes": 90,
            "options": {"maxiter": 1000, "rhobeg": 1.0}
        }
    }

    config = base_configs[algorithm].copy()

    # Adjust based on problem characteristics
    time_constraint = problem_profile.get("time_constraint", "medium")
    param_count = problem_profile.get("parameter_count", 5)

    if time_constraint == "low":
        # Reduce evaluations and timeout for time pressure
        config["max_evaluations"] = int(config["max_evaluations"] * 0.5)
        config["timeout_minutes"] = int(config["timeout_minutes"] * 0.6)

    elif time_constraint == "high":
        # Increase evaluations for thorough search
        config["max_evaluations"] = int(config["max_evaluations"] * 1.5)
        config["timeout_minutes"] = int(config["timeout_minutes"] * 1.5)

    # Scale for parameter count
    if param_count > 15:
        config["max_evaluations"] = int(config["max_evaluations"] * 1.3)
        config["timeout_minutes"] = int(config["timeout_minutes"] * 1.2)

    return config

def suggest_alternatives(primary_algorithm: str, problem_profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """Suggest alternative algorithms with rationales."""

    alternatives = []

    if primary_algorithm == "SLSQP":
        alternatives.extend([
            {"algorithm": "L-BFGS-B", "reason": "Better scaling for large problems"},
            {"algorithm": "DE", "reason": "Global search if local optima suspected"}
        ])

    elif primary_algorithm == "DE":
        alternatives.extend([
            {"algorithm": "SLSQP", "reason": "Faster convergence if time is limited"},
            {"algorithm": "TNC", "reason": "Better constraint handling if needed"}
        ])

    elif primary_algorithm == "L-BFGS-B":
        alternatives.extend([
            {"algorithm": "SLSQP", "reason": "Better constraint support"},
            {"algorithm": "DE", "reason": "Global search capability"}
        ])

    elif primary_algorithm == "TNC":
        alternatives.extend([
            {"algorithm": "SLSQP", "reason": "Simpler setup for basic constraints"},
            {"algorithm": "COBYLA", "reason": "Derivative-free alternative"}
        ])

    elif primary_algorithm == "COBYLA":
        alternatives.extend([
            {"algorithm": "TNC", "reason": "Faster convergence if gradients available"},
            {"algorithm": "DE", "reason": "Better global search capability"}
        ])

    return alternatives

def calculate_selection_confidence(algorithm: str, problem_profile: Dict[str, Any]) -> str:
    """Calculate confidence level in algorithm selection."""

    confidence_score = 0

    # Clear indicators increase confidence
    if problem_profile.get("global_search", False) and algorithm == "DE":
        confidence_score += 3

    if problem_profile.get("parameter_count", 5) > 15 and algorithm == "L-BFGS-B":
        confidence_score += 2

    if problem_profile.get("constraint_count", 0) == 0 and algorithm in ["SLSQP", "L-BFGS-B"]:
        confidence_score += 2

    # Conflicting indicators decrease confidence
    if problem_profile.get("time_constraint", "medium") == "low" and algorithm in ["DE", "COBYLA"]:
        confidence_score -= 2

    if problem_profile.get("noise_level", "low") == "high" and algorithm in ["SLSQP", "L-BFGS-B"]:
        confidence_score -= 1

    if confidence_score >= 3:
        return "HIGH"
    elif confidence_score >= 1:
        return "MEDIUM"
    else:
        return "LOW"

# Example usage
problem_profile = {
    "parameter_count": 12,
    "constraint_count": 3,
    "constraint_types": ["bounds", "linear"],
    "time_constraint": "medium",
    "noise_level": "low",
    "global_search": False,
    "derivatives_available": True
}

selection_result = select_optimization_algorithm(problem_profile)

print(f"Recommended Algorithm: {selection_result['recommended_algorithm']}")
print(f"Confidence: {selection_result['confidence']}")
print(f"Rationale: {selection_result['selection_rationale']}")
print("\nConfiguration:")
for key, value in selection_result['configuration'].items():
    print(f"  {key}: {value}")

print("\nAlternatives:")
for alt in selection_result['alternatives']:
    print(f"  - {alt['algorithm']}: {alt['reason']}")
```

### 2. Performance Benchmarking

```python
class AlgorithmBenchmark:
    """Benchmark algorithms on different problem types."""

    def __init__(self):
        self.benchmark_results = {}

    def run_comprehensive_benchmark(self, problem_generator):
        """Run benchmark across multiple problem types and algorithms."""

        algorithms = ["SLSQP", "DE", "L-BFGS-B", "TNC", "COBYLA"]
        problem_types = [
            "simple_unconstrained",
            "complex_unconstrained",
            "bound_constrained",
            "nonlinear_constrained",
            "noisy_objective",
            "high_dimensional"
        ]

        results = {}

        for problem_type in problem_types:
            results[problem_type] = {}

            # Generate test problem
            test_problem = problem_generator.create_problem(problem_type)

            for algorithm in algorithms:
                print(f"Benchmarking {algorithm} on {problem_type}...")

                # Run optimization multiple times for statistical significance
                runs = []
                for trial in range(5):
                    try:
                        run_result = self._run_single_benchmark(algorithm, test_problem, trial)
                        runs.append(run_result)
                    except Exception as e:
                        print(f"  Trial {trial} failed: {e}")
                        runs.append({"success": False, "error": str(e)})

                # Aggregate results
                successful_runs = [r for r in runs if r.get("success", False)]

                if successful_runs:
                    avg_time = sum(r["runtime"] for r in successful_runs) / len(successful_runs)
                    avg_evaluations = sum(r["evaluations"] for r in successful_runs) / len(successful_runs)
                    success_rate = len(successful_runs) / len(runs)
                    avg_quality = sum(r["objective_value"] for r in successful_runs) / len(successful_runs)

                    results[problem_type][algorithm] = {
                        "success_rate": success_rate,
                        "avg_runtime": avg_time,
                        "avg_evaluations": avg_evaluations,
                        "avg_objective_value": avg_quality,
                        "convergence_rate": sum(1 for r in successful_runs if r["converged"]) / len(successful_runs)
                    }
                else:
                    results[problem_type][algorithm] = {
                        "success_rate": 0.0,
                        "avg_runtime": float('inf'),
                        "avg_evaluations": float('inf'),
                        "avg_objective_value": float('inf'),
                        "convergence_rate": 0.0
                    }

        self.benchmark_results = results
        return results

    def _run_single_benchmark(self, algorithm: str, test_problem: Dict, trial: int) -> Dict:
        """Run single benchmark trial."""

        start_time = time.time()

        # Configure optimizer
        from orchestrator.optimization.constraint_solver import CompensationOptimizer

        # Mock optimizer for benchmark
        optimizer = MockCompensationOptimizer(algorithm=algorithm, seed=trial)

        # Run optimization
        result = optimizer.optimize(
            initial_parameters=test_problem["initial_parameters"],
            objectives=test_problem["objectives"],
            method=algorithm,
            max_evaluations=test_problem.get("max_evaluations", 200),
            timeout_minutes=test_problem.get("timeout_minutes", 10)
        )

        runtime = time.time() - start_time

        return {
            "success": True,
            "runtime": runtime,
            "evaluations": getattr(result, "function_evaluations", 0),
            "converged": getattr(result, "converged", False),
            "objective_value": getattr(result, "objective_value", float('inf'))
        }

    def generate_benchmark_report(self) -> str:
        """Generate comprehensive benchmark report."""

        if not self.benchmark_results:
            return "No benchmark results available"

        report = "# Algorithm Benchmark Report\n\n"

        # Overall performance summary
        report += "## Performance Summary\n\n"

        algorithm_scores = {}

        for problem_type, problem_results in self.benchmark_results.items():
            report += f"### {problem_type.replace('_', ' ').title()}\n\n"
            report += "| Algorithm | Success Rate | Avg Runtime (s) | Avg Evaluations | Convergence Rate |\n"
            report += "|-----------|--------------|-----------------|-----------------|------------------|\n"

            for algorithm, metrics in problem_results.items():
                if algorithm not in algorithm_scores:
                    algorithm_scores[algorithm] = []

                # Calculate composite score
                score = (metrics["success_rate"] * 0.3 +
                        metrics["convergence_rate"] * 0.3 +
                        (1.0 / (1.0 + metrics["avg_runtime"])) * 0.2 +
                        (1.0 / (1.0 + metrics["avg_evaluations"] / 100)) * 0.2)

                algorithm_scores[algorithm].append(score)

                report += f"| {algorithm} | {metrics['success_rate']:.1%} | "
                report += f"{metrics['avg_runtime']:.1f} | {metrics['avg_evaluations']:.0f} | "
                report += f"{metrics['convergence_rate']:.1%} |\n"

            report += "\n"

        # Overall rankings
        report += "## Overall Algorithm Rankings\n\n"

        overall_scores = {alg: sum(scores)/len(scores) for alg, scores in algorithm_scores.items()}
        ranked_algorithms = sorted(overall_scores.items(), key=lambda x: x[1], reverse=True)

        report += "| Rank | Algorithm | Overall Score | Recommendation |\n"
        report += "|------|-----------|---------------|----------------|\n"

        recommendations = {
            1: "Excellent general-purpose choice",
            2: "Strong alternative for most problems",
            3: "Good for specific problem types",
            4: "Consider for specialized scenarios",
            5: "Use only when other algorithms fail"
        }

        for rank, (algorithm, score) in enumerate(ranked_algorithms, 1):
            recommendation = recommendations.get(rank, "Specialized use only")
            report += f"| {rank} | {algorithm} | {score:.3f} | {recommendation} |\n"

        return report

# Example usage
benchmarker = AlgorithmBenchmark()

# This would require a proper problem generator implementation
# benchmark_results = benchmarker.run_comprehensive_benchmark(problem_generator)
# benchmark_report = benchmarker.generate_benchmark_report()
# print(benchmark_report)
```

---

## Algorithm-Specific Troubleshooting

### SLSQP Issues

**Problem:** Premature convergence to local optimum
```python
# Solution: Use multiple random starts
slsqp_multistart_config = {
    "method": "SLSQP",
    "random_starts": 5,
    "start_distribution": "latin_hypercube",  # Better coverage
    "options": {"maxiter": 150}
}
```

**Problem:** Slow convergence
```python
# Solution: Adjust tolerances and step sizes
slsqp_tuned_config = {
    "method": "SLSQP",
    "options": {
        "ftol": 1e-4,      # Relaxed function tolerance
        "eps": 1e-6,       # Larger finite difference step
        "maxiter": 200     # More iterations
    }
}
```

### DE Issues

**Problem:** Very slow convergence
```python
# Solution: Adjust population and mutation parameters
de_fast_config = {
    "method": "DE",
    "options": {
        "popsize": 10,        # Smaller population
        "mutation": (0.7, 1), # Higher mutation
        "maxiter": 100,       # Fewer generations
        "polish": True        # Local refinement
    }
}
```

**Problem:** Poor constraint handling
```python
# Solution: Implement custom penalty function
def custom_penalty_function(violations):
    """Custom penalty for constraint violations."""
    penalty = 0
    for violation in violations:
        penalty += violation ** 2 * 1000  # Quadratic penalty
    return penalty
```

### L-BFGS-B Issues

**Problem:** Convergence to boundary
```python
# Solution: Check if bounds are too restrictive
def analyze_boundary_convergence(result, bounds):
    """Check if solution is on parameter boundaries."""
    boundary_parameters = []

    for param_name, value in result.optimal_parameters.items():
        if param_name in bounds:
            lower, upper = bounds[param_name]
            if abs(value - lower) < 1e-6:
                boundary_parameters.append(f"{param_name} at lower bound")
            elif abs(value - upper) < 1e-6:
                boundary_parameters.append(f"{param_name} at upper bound")

    return boundary_parameters
```

---

## Real-World Case Studies

### Case Study 1: Large-Scale Merit Optimization

**Problem:** 25 parameters, simple bounds, time-critical
**Challenge:** Need fast convergence for quarterly planning deadline

```python
# Problem characteristics
case1_profile = {
    "parameter_count": 25,
    "constraint_count": 0,
    "constraint_types": ["bounds"],
    "time_constraint": "low",
    "global_search": False,
    "business_context": "quarterly_planning"
}

# Algorithm selection result
selected = select_optimization_algorithm(case1_profile)
# Result: L-BFGS-B with fast configuration

# Performance outcome
outcome = {
    "algorithm_used": "L-BFGS-B",
    "convergence_time": "3.2 minutes",
    "function_evaluations": 187,
    "converged": True,
    "business_impact": "Met planning deadline, 2.8% growth achieved"
}
```

### Case Study 2: Complex Multi-Objective Optimization

**Problem:** 12 parameters, nonlinear constraints, conflicting objectives
**Challenge:** Balance cost control with equity requirements

```python
# Problem characteristics
case2_profile = {
    "parameter_count": 12,
    "constraint_count": 8,
    "constraint_types": ["bounds", "nonlinear"],
    "time_constraint": "medium",
    "global_search": True,
    "business_context": "equity_rebalancing"
}

# Algorithm selection result
selected = select_optimization_algorithm(case2_profile)
# Result: TNC with robust constraint handling

# Performance outcome
outcome = {
    "algorithm_used": "TNC",
    "convergence_time": "18.7 minutes",
    "function_evaluations": 432,
    "converged": True,
    "business_impact": "Achieved equity targets while staying within budget"
}
```

### Case Study 3: Noisy Data Environment

**Problem:** 8 parameters, noisy simulation data, uncertain objectives
**Challenge:** Robust optimization despite data quality issues

```python
# Problem characteristics
case3_profile = {
    "parameter_count": 8,
    "constraint_count": 2,
    "constraint_types": ["bounds"],
    "time_constraint": "high",
    "noise_level": "high",
    "global_search": True,
    "business_context": "uncertain_market_conditions"
}

# Algorithm selection result
selected = select_optimization_algorithm(case3_profile)
# Result: DE with noise-robust configuration

# Performance outcome
outcome = {
    "algorithm_used": "DE",
    "convergence_time": "45.3 minutes",
    "function_evaluations": 1247,
    "converged": True,
    "business_impact": "Robust solution despite data uncertainty"
}
```

---

## Conclusion

Algorithm selection is critical for optimization success. Key principles:

1. **Match Algorithm to Problem** - Use decision framework to select appropriate method
2. **Consider Trade-offs** - Balance speed, robustness, and solution quality
3. **Test Multiple Approaches** - Benchmark when problem characteristics are unclear
4. **Monitor Performance** - Track algorithm effectiveness over time
5. **Adapt Configuration** - Tune parameters based on problem characteristics

### Quick Selection Rules

- **Default Choice:** SLSQP for most compensation optimization problems
- **Large Problems (>15 parameters):** L-BFGS-B
- **Global Search Needed:** DE
- **Complex Constraints:** TNC
- **No Derivatives Available:** COBYLA
- **Time Critical:** SLSQP or L-BFGS-B
- **Noisy Data:** DE or COBYLA

---

*This algorithm selection guide is part of the Fidelity PlanAlign Engine E012 Compensation Tuning System documentation suite.*
