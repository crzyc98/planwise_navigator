"""
SciPy-based constraint solver for compensation optimization.

Implements multi-start optimization with constraint handling,
caching, and comprehensive monitoring.
"""

from __future__ import annotations
import numpy as np
from scipy.optimize import minimize, differential_evolution
from typing import Dict, Any, List, Tuple, Optional, Callable
import time
import logging
from datetime import datetime

from orchestrator.resources.duckdb_resource import DuckDBResource
from .optimization_schemas import (
    OptimizationRequest,
    OptimizationResult,
    OptimizationError,
    OptimizationCache,
    PARAMETER_SCHEMA
)
from .objective_functions import ObjectiveFunctions

logger = logging.getLogger(__name__)

class OptimizationMonitor:
    """Monitor optimization progress and performance."""

    def __init__(self):
        self.start_time: Optional[float] = None
        self.evaluations = 0
        self.best_value = float('inf')
        self.evaluation_history: List[Tuple[float, Dict[str, float]]] = []
        self.failures: List[str] = []

    def start(self):
        """Start monitoring."""
        self.start_time = time.time()
        self.evaluations = 0
        self.best_value = float('inf')
        self.evaluation_history.clear()
        self.failures.clear()

    def log_evaluation(self, value: float, parameters: Dict[str, float]):
        """Log function evaluation."""
        self.evaluations += 1
        if value < self.best_value:
            self.best_value = value
        self.evaluation_history.append((value, parameters.copy()))

    def log_failure(self, iteration: int, error_msg: str):
        """Log optimization failure."""
        self.failures.append(f"Iteration {iteration}: {error_msg}")

    @property
    def runtime_seconds(self) -> float:
        """Get current runtime in seconds."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

class CompensationOptimizer:
    """Advanced compensation parameter optimization engine using SciPy."""

    def __init__(self, duckdb_resource: DuckDBResource, scenario_id: str, use_synthetic: bool = False):
        self.duckdb_resource = duckdb_resource
        self.scenario_id = scenario_id
        self.use_synthetic = use_synthetic
        self.constraints: List[Callable] = []
        self.objectives: List[Tuple[Callable, float]] = []
        self.cache = OptimizationCache()
        self.monitor = OptimizationMonitor()

        # Initialize objective functions with use_synthetic flag
        self.obj_funcs = ObjectiveFunctions(duckdb_resource, scenario_id, use_synthetic=use_synthetic)

    def add_objective(self, objective_func: Callable, weight: float = 1.0):
        """Add objective function with weight."""
        self.objectives.append((objective_func, weight))

    def add_constraint(self, constraint_func: Callable):
        """Add constraint function."""
        self.constraints.append(constraint_func)

    def optimize(
        self,
        initial_parameters: Dict[str, float],
        objectives: Dict[str, float],
        method: str = 'SLSQP',
        max_evaluations: int = 200,
        timeout_minutes: int = 30,
        random_seed: Optional[int] = 42
    ) -> OptimizationResult:
        """
        Run multi-objective optimization with comprehensive monitoring.

        Args:
            initial_parameters: Starting parameter values
            objectives: Objective weights (must sum to 1.0)
            method: Optimization algorithm ('SLSQP', 'DE', 'GA')
            max_evaluations: Maximum function evaluations
            timeout_minutes: Maximum runtime
            random_seed: Random seed for reproducibility

        Returns:
            OptimizationResult with optimal parameters and metadata
        """
        # Set random seed for reproducibility
        if random_seed is not None:
            np.random.seed(random_seed)

        # Start monitoring
        self.monitor.start()

        # Validate inputs
        self._validate_inputs(initial_parameters, objectives)

        # Setup parameter bounds and constraints
        bounds, constraints = self._setup_optimization_problem(initial_parameters)

        # Create objective function
        def objective_wrapper(x_array: np.ndarray) -> float:
            # Convert array back to parameter dict
            param_dict = self._array_to_parameters(x_array, initial_parameters)

            # Check cache first
            cached_value = self.cache.get(param_dict)
            if cached_value is not None:
                return cached_value

            try:
                # Calculate combined objective
                obj_value = self.obj_funcs.combined_objective(param_dict, objectives)

                # Cache result
                self.cache.set(param_dict, obj_value)

                # Monitor progress
                self.monitor.log_evaluation(obj_value, param_dict)

                return obj_value

            except Exception as e:
                logger.error(f"Objective evaluation failed: {e}")
                return 1e6  # High penalty for failures

        # Run optimization with multiple strategies
        best_result = None

        try:
            if method.upper() == 'SLSQP':
                best_result = self._run_slsqp_optimization(
                    objective_wrapper, initial_parameters, bounds, constraints,
                    max_evaluations, timeout_minutes
                )
            elif method.upper() == 'DE':
                best_result = self._run_differential_evolution(
                    objective_wrapper, bounds, max_evaluations, timeout_minutes
                )
            else:
                raise ValueError(f"Unsupported optimization method: {method}")

        except Exception as e:
            detailed_error = f"Optimization failed: {type(e).__name__}: {str(e)}"
            logger.error(detailed_error)
            print(f"🚨 OPTIMIZATION ERROR: {detailed_error}")  # Additional console logging
            print(f"📊 Parameters that failed: {list(initial_parameters.keys())}")
            print(f"🎯 Objectives: {objectives}")
            # Add traceback for debugging
            import traceback
            print(f"📍 Traceback:")
            traceback.print_exc()
            return OptimizationError(
                scenario_id=self.scenario_id,
                error_type="NUMERICAL",
                error_message=detailed_error,
                best_found_solution=None,
                recommendations=["Try different algorithm", "Check parameter bounds"]
            )

        # Process results
        if best_result and best_result.success:
            return self._create_optimization_result(
                best_result, initial_parameters, objectives, method
            )
        else:
            return self._create_optimization_error(best_result, method)

    def _validate_inputs(
        self,
        initial_parameters: Dict[str, float],
        objectives: Dict[str, float]
    ):
        """Validate optimization inputs."""
        print(f"🔍 Validating inputs...")
        print(f"📊 Parameters: {initial_parameters}")
        print(f"🎯 Objectives: {objectives}")

        # Check parameter schema
        for param_name in initial_parameters:
            if param_name not in PARAMETER_SCHEMA:
                print(f"❌ Unknown parameter: {param_name}")
                raise ValueError(f"Unknown parameter: {param_name}")

        # Check objective weights
        weight_sum = sum(objectives.values())
        print(f"⚖️ Weight sum: {weight_sum}")
        if abs(weight_sum - 1.0) > 1e-6:
            print(f"❌ Weight sum error: {weight_sum}")
            raise ValueError(f"Objective weights must sum to 1.0, got {weight_sum}")

        # Check parameter bounds
        for param_name, value in initial_parameters.items():
            bounds = PARAMETER_SCHEMA[param_name]["range"]
            print(f"📏 Checking {param_name}: {value} in {bounds}")
            if not (bounds[0] <= value <= bounds[1]):
                print(f"❌ Bounds violation: {param_name} = {value}, bounds = {bounds}")
                raise ValueError(
                    f"Parameter {param_name} value {value} outside bounds {bounds}"
                )

        print(f"✅ Input validation passed!")

    def _setup_optimization_problem(
        self,
        initial_parameters: Dict[str, float]
    ) -> Tuple[List[Tuple[float, float]], List[Dict]]:
        """Setup bounds and constraints for optimization."""

        # Parameter bounds from schema
        bounds = []
        param_names = list(initial_parameters.keys())

        for param_name in param_names:
            bounds.append(tuple(PARAMETER_SCHEMA[param_name]["range"]))

        # Constraint functions (for SLSQP)
        constraints = []
        for constraint_func in self.constraints:
            constraints.append({
                'type': 'ineq',
                'fun': lambda x: constraint_func(self._array_to_parameters(x, initial_parameters))
            })

        return bounds, constraints

    def _parameters_to_array(self, parameters: Dict[str, float]) -> np.ndarray:
        """Convert parameter dict to numpy array."""
        return np.array(list(parameters.values()))

    def _array_to_parameters(
        self,
        x_array: np.ndarray,
        parameter_template: Dict[str, float]
    ) -> Dict[str, float]:
        """Convert numpy array back to parameter dict."""
        param_names = list(parameter_template.keys())
        return dict(zip(param_names, x_array))

    def _run_slsqp_optimization(
        self,
        objective_func: Callable,
        initial_parameters: Dict[str, float],
        bounds: List[Tuple[float, float]],
        constraints: List[Dict],
        max_evaluations: int,
        timeout_minutes: int
    ):
        """Run SLSQP optimization with multiple random starts."""

        best_result = None

        # Multiple random starts for robustness
        n_starts = min(5, max_evaluations // 20)  # Adaptive number of starts
        n_starts = max(1, n_starts)  # Ensure at least 1 start

        print(f"🔄 Running SLSQP with {n_starts} random starts, {max_evaluations} total evaluations")

        for start_idx in range(n_starts):
            try:
                # Generate random starting point (except first start)
                if start_idx == 0:
                    x0 = self._parameters_to_array(initial_parameters)
                else:
                    x0 = np.array([
                        np.random.uniform(bound[0], bound[1])
                        for bound in bounds
                    ])

                print(f"🎯 Start {start_idx + 1}/{n_starts}: Running optimization...")

                # Run optimization
                result = minimize(
                    fun=objective_func,
                    x0=x0,
                    method='SLSQP',
                    bounds=bounds,
                    constraints=constraints,
                    options={
                        'maxiter': max_evaluations // n_starts,
                        'ftol': 1e-6,
                        'disp': True  # Enable display for debugging
                    }
                )

                print(f"✅ Start {start_idx + 1} result: success={result.success}, fun={result.fun:.6f}, message={result.message}")

                # Track best result
                if best_result is None or result.fun < best_result.fun:
                    best_result = result

                # Check timeout
                if self.monitor.runtime_seconds > timeout_minutes * 60:
                    logger.warning("Optimization timeout reached")
                    break

            except Exception as e:
                print(f"❌ Start {start_idx + 1} failed: {e}")
                self.monitor.log_failure(start_idx, str(e))
                continue

        if best_result is None:
            print("⚠️ No successful optimization runs!")
        else:
            print(f"🏆 Best result: success={best_result.success}, fun={best_result.fun:.6f}")

        return best_result

    def _run_differential_evolution(
        self,
        objective_func: Callable,
        bounds: List[Tuple[float, float]],
        max_evaluations: int,
        timeout_minutes: int
    ):
        """Run differential evolution optimization."""

        try:
            result = differential_evolution(
                func=objective_func,
                bounds=bounds,
                maxiter=max_evaluations // 20,  # DE evaluates populations
                popsize=15,
                tol=1e-6,
                disp=False,
                seed=42
            )
            return result

        except Exception as e:
            logger.error(f"Differential evolution failed: {e}")
            return None

    def _create_optimization_result(
        self,
        scipy_result: Any,
        initial_parameters: Dict[str, float],
        objectives: Dict[str, float],
        method: str
    ) -> OptimizationResult:
        """Create OptimizationResult from SciPy result."""

        # Convert result back to parameters
        optimal_params = self._array_to_parameters(scipy_result.x, initial_parameters)

        # Calculate business impact
        if self.use_synthetic:
            # Use synthetic metrics for synthetic mode
            cost_impact = {
                "value": 85000000.0,  # $85M synthetic estimate
                "unit": "USD",
                "confidence": "high" if scipy_result.success else "medium"
            }
            employee_impact = {
                "count": 500,
                "percentage_of_workforce": 1.0,
                "risk_level": self._assess_risk_level(optimal_params)
            }
        else:
            # Get real metrics for real mode
            current_metrics = self.obj_funcs.get_current_metrics()

            # Estimate cost impact (simplified)
            cost_impact = {
                "value": current_metrics["workforce_metrics"]["total_compensation"],
                "unit": "USD",
                "confidence": "high" if scipy_result.success else "medium"
            }

            # Estimate employee impact
            employee_impact = {
                "count": current_metrics["workforce_metrics"]["total_workforce"],
                "percentage_of_workforce": 1.0,  # Affects all employees
                "risk_level": self._assess_risk_level(optimal_params)
            }

        # Check constraint violations
        constraint_violations = self._check_constraint_violations(optimal_params)

        return OptimizationResult(
            scenario_id=self.scenario_id,
            converged=scipy_result.success,
            optimal_parameters=optimal_params,
            objective_value=float(scipy_result.fun),
            algorithm_used=method,
            iterations=getattr(scipy_result, 'nit', self.monitor.evaluations),
            function_evaluations=self.monitor.evaluations,
            runtime_seconds=self.monitor.runtime_seconds,
            estimated_cost_impact=cost_impact,
            estimated_employee_impact=employee_impact,
            risk_assessment=self._assess_risk_level(optimal_params),
            constraint_violations=constraint_violations,
            solution_quality_score=self._calculate_quality_score(scipy_result),
            evidence_report_url=None  # To be generated separately
        )

    def _create_optimization_error(
        self,
        scipy_result: Any,
        method: str
    ) -> OptimizationError:
        """Create OptimizationError for failed optimization."""

        error_type = "NUMERICAL"
        if self.monitor.runtime_seconds > 1800:  # 30 minutes
            error_type = "TIMEOUT"
        elif scipy_result and hasattr(scipy_result, 'message'):
            if "infeasible" in scipy_result.message.lower():
                error_type = "INFEASIBLE"

        return OptimizationError(
            scenario_id=self.scenario_id,
            error_type=error_type,
            error_message=getattr(scipy_result, 'message', 'Optimization failed'),
            best_found_solution=None,
            recommendations=[
                "Try different starting point",
                "Relax constraints",
                "Use different algorithm",
                "Check parameter bounds"
            ]
        )

    def _assess_risk_level(self, parameters: Dict[str, float]) -> str:
        """Assess risk level of parameter combination."""

        # Simple risk assessment based on parameter ranges
        risk_score = 0.0

        for param_name, value in parameters.items():
            bounds = PARAMETER_SCHEMA[param_name]["range"]
            param_range = bounds[1] - bounds[0]

            # Distance from center as risk factor
            center = (bounds[0] + bounds[1]) / 2
            distance_from_center = abs(value - center) / (param_range / 2)
            risk_score += distance_from_center

        # Average risk across parameters
        avg_risk = risk_score / len(parameters)

        if avg_risk < 0.3:
            return "LOW"
        elif avg_risk < 0.7:
            return "MEDIUM"
        else:
            return "HIGH"

    def _check_constraint_violations(
        self,
        parameters: Dict[str, float]
    ) -> Dict[str, float]:
        """Check for constraint violations."""

        violations = {}

        # Check parameter bounds
        for param_name, value in parameters.items():
            bounds = PARAMETER_SCHEMA[param_name]["range"]
            if value < bounds[0]:
                violations[f"{param_name}_lower_bound"] = bounds[0] - value
            elif value > bounds[1]:
                violations[f"{param_name}_upper_bound"] = value - bounds[1]

        return violations

    def _calculate_quality_score(self, scipy_result: Any) -> float:
        """Calculate solution quality score (0-1 scale)."""

        if not scipy_result.success:
            return 0.0

        # Base score on convergence and function evaluations
        base_score = 0.8 if scipy_result.success else 0.0

        # Bonus for efficient convergence
        if self.monitor.evaluations < 100:
            base_score += 0.2
        elif self.monitor.evaluations < 200:
            base_score += 0.1

        # Cache hit rate bonus
        cache_bonus = min(0.1, self.cache.hit_rate * 0.1)

        return min(1.0, base_score + cache_bonus)
