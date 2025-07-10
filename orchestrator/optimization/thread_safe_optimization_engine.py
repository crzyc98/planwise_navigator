"""
Thread-safe optimization engine with isolation guarantees.

Provides concurrent optimization capabilities with proper thread isolation,
numerical stability, and performance monitoring.
"""

from __future__ import annotations
import threading
import concurrent.futures
import numpy as np
import math
import time
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, asdict
from scipy.optimize import minimize, OptimizeResult
import logging

from orchestrator.resources.duckdb_resource import DuckDBResource
from orchestrator.optimization.thread_safe_objective_functions import (
    ThreadSafeObjectiveFunctions,
    ThreadSafeAdaptivePenalty,
    RobustNumericalCalculations
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OptimizationRequest:
    """Configuration for a single optimization run."""
    scenario_id: str
    initial_params: Dict[str, float]
    param_names: List[str]
    param_bounds: List[Tuple[float, float]]
    objectives: Dict[str, float]  # Objective weights
    method: str = 'SLSQP'
    max_evaluations: int = 100
    tolerance: float = 1e-6
    use_synthetic: bool = False


@dataclass
class OptimizationResponse:
    """Result of a single optimization run."""
    scenario_id: str
    success: bool
    optimal_params: Dict[str, float]
    objective_value: float
    iterations: int
    function_evaluations: int
    execution_time: float
    thread_id: int
    cache_stats: Dict[str, Any]
    convergence_history: List[float]
    error: Optional[str] = None


@dataclass
class ConcurrentOptimizationResults:
    """Results of concurrent optimization runs."""
    total_optimizations: int
    successful_optimizations: int
    failed_optimizations: int
    total_execution_time: float
    average_execution_time: float
    results: List[OptimizationResponse]
    performance_metrics: Dict[str, Any]


class ThreadSafeOptimizationEngine:
    """Thread-safe optimization engine with isolation guarantees."""

    def __init__(self, duckdb_resource: DuckDBResource, max_concurrent: int = 4):
        self.duckdb_resource = duckdb_resource
        self.max_concurrent = max_concurrent
        self._optimization_lock = threading.RLock()
        self._active_optimizations = {}
        self._performance_metrics = {
            'total_optimizations': 0,
            'successful_optimizations': 0,
            'failed_optimizations': 0,
            'total_execution_time': 0.0,
            'average_objective_evaluations': 0.0
        }

        # Numerical stability calculator
        self._numerical_calc = RobustNumericalCalculations()

    def optimize_single(self, request: OptimizationRequest) -> OptimizationResponse:
        """Run a single optimization with thread safety."""
        start_time = time.time()
        thread_id = threading.get_ident()

        logger.info(f"Starting optimization {request.scenario_id} on thread {thread_id}")

        try:
            # Register active optimization
            with self._optimization_lock:
                self._active_optimizations[thread_id] = request.scenario_id

            # Create isolated objective functions for this thread
            objective_functions = ThreadSafeObjectiveFunctions(
                self.duckdb_resource,
                request.scenario_id,
                request.use_synthetic
            )

            # Create adaptive penalty calculator for this thread
            penalty_calculator = ThreadSafeAdaptivePenalty()

            # Track convergence history
            convergence_history = []
            evaluation_count = 0

            def combined_objective(params_array: np.ndarray) -> float:
                """Combined objective function with thread-safe evaluation."""
                nonlocal evaluation_count
                evaluation_count += 1

                # Convert array to parameter dict with bounds validation
                param_dict = self._array_to_params_with_validation(
                    params_array, request.param_names, request.param_bounds
                )

                try:
                    # Calculate combined objective
                    total_objective = 0.0

                    if 'cost' in request.objectives:
                        cost_obj = objective_functions.cost_objective(param_dict)
                        total_objective += request.objectives['cost'] * cost_obj

                    if 'equity' in request.objectives:
                        equity_obj = objective_functions.equity_objective(param_dict)
                        total_objective += request.objectives['equity'] * equity_obj

                    if 'targets' in request.objectives:
                        targets_obj = objective_functions.targets_objective(param_dict)
                        total_objective += request.objectives['targets'] * targets_obj

                    # Validate numerical result
                    if math.isnan(total_objective) or math.isinf(total_objective):
                        raise ValueError("Objective function returned invalid value")

                    # Track convergence
                    convergence_history.append(total_objective)

                    return total_objective

                except Exception as e:
                    logger.warning(f"Objective evaluation failed in thread {thread_id}: {e}")
                    # Calculate adaptive penalty
                    penalty = penalty_calculator.calculate_penalty(thread_id, convergence_history)
                    convergence_history.append(penalty)
                    return penalty

            # Validate initial parameters
            initial_array = np.array(list(request.initial_params.values()))
            if not self._validate_parameter_bounds(initial_array, request.param_bounds):
                # Clamp initial parameters to bounds
                initial_array = self._clamp_to_bounds(initial_array, request.param_bounds)

            # Run optimization with robust settings
            optimization_result = minimize(
                fun=combined_objective,
                x0=initial_array,
                method=request.method,
                bounds=request.param_bounds,
                options={
                    'maxiter': request.max_evaluations,
                    'ftol': request.tolerance,
                    'disp': False
                }
            )

            # Process results
            execution_time = time.time() - start_time

            optimal_params = self._array_to_params_with_validation(
                optimization_result.x, request.param_names, request.param_bounds
            )

            # Get cache statistics
            cache_stats = objective_functions.get_cache_stats()

            response = OptimizationResponse(
                scenario_id=request.scenario_id,
                success=optimization_result.success,
                optimal_params=optimal_params,
                objective_value=optimization_result.fun,
                iterations=optimization_result.nit,
                function_evaluations=evaluation_count,
                execution_time=execution_time,
                thread_id=thread_id,
                cache_stats=cache_stats,
                convergence_history=convergence_history
            )

            # Update performance metrics
            self._update_performance_metrics(response)

            logger.info(f"Optimization {request.scenario_id} completed in {execution_time:.2f}s")
            return response

        except Exception as e:
            execution_time = time.time() - start_time
            error_response = OptimizationResponse(
                scenario_id=request.scenario_id,
                success=False,
                optimal_params=request.initial_params,
                objective_value=float('inf'),
                iterations=0,
                function_evaluations=evaluation_count if 'evaluation_count' in locals() else 0,
                execution_time=execution_time,
                thread_id=thread_id,
                cache_stats={},
                convergence_history=convergence_history if 'convergence_history' in locals() else [],
                error=str(e)
            )

            self._update_performance_metrics(error_response)
            logger.error(f"Optimization {request.scenario_id} failed: {e}")
            return error_response

        finally:
            # Cleanup thread registration
            with self._optimization_lock:
                if thread_id in self._active_optimizations:
                    del self._active_optimizations[thread_id]

    def optimize_concurrent(self, requests: List[OptimizationRequest]) -> ConcurrentOptimizationResults:
        """Run multiple optimizations concurrently with thread safety."""
        start_time = time.time()

        logger.info(f"Starting {len(requests)} concurrent optimizations")

        # Validate maximum concurrent limit
        if len(requests) > self.max_concurrent:
            logger.warning(f"Requested {len(requests)} optimizations exceeds max_concurrent={self.max_concurrent}")

        with ThreadPoolExecutor(max_workers=min(self.max_concurrent, len(requests))) as executor:
            # Submit all optimization tasks
            future_to_request = {
                executor.submit(self.optimize_single, request): request
                for request in requests
            }

            results = []
            successful = 0
            failed = 0

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_request):
                request = future_to_request[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result.success:
                        successful += 1
                    else:
                        failed += 1

                except Exception as e:
                    # Handle unexpected failures
                    error_result = OptimizationResponse(
                        scenario_id=request.scenario_id,
                        success=False,
                        optimal_params=request.initial_params,
                        objective_value=float('inf'),
                        iterations=0,
                        function_evaluations=0,
                        execution_time=0.0,
                        thread_id=0,
                        cache_stats={},
                        convergence_history=[],
                        error=f"Unexpected error: {e}"
                    )
                    results.append(error_result)
                    failed += 1

        total_execution_time = time.time() - start_time
        avg_execution_time = total_execution_time / len(requests) if requests else 0.0

        # Calculate performance metrics
        performance_metrics = self._calculate_concurrent_performance_metrics(results)

        concurrent_results = ConcurrentOptimizationResults(
            total_optimizations=len(requests),
            successful_optimizations=successful,
            failed_optimizations=failed,
            total_execution_time=total_execution_time,
            average_execution_time=avg_execution_time,
            results=results,
            performance_metrics=performance_metrics
        )

        logger.info(f"Concurrent optimization completed: {successful}/{len(requests)} successful in {total_execution_time:.2f}s")
        return concurrent_results

    def _array_to_params_with_validation(self, array: np.ndarray,
                                       param_names: List[str],
                                       bounds: List[Tuple[float, float]]) -> Dict[str, float]:
        """Convert array to parameters with bounds validation."""
        # Clamp values to bounds
        clamped_array = self._clamp_to_bounds(array, bounds)

        # Convert to dictionary
        param_dict = {}
        for i, name in enumerate(param_names):
            if i < len(clamped_array):
                value = float(clamped_array[i])
                # Additional numerical validation
                if math.isnan(value) or math.isinf(value):
                    # Use midpoint of bounds as fallback
                    lower, upper = bounds[i] if i < len(bounds) else (0.0, 1.0)
                    value = (lower + upper) / 2.0
                param_dict[name] = value

        return param_dict

    def _validate_parameter_bounds(self, array: np.ndarray,
                                 bounds: List[Tuple[float, float]]) -> bool:
        """Validate that all parameters are within bounds."""
        for i, value in enumerate(array):
            if i < len(bounds):
                lower, upper = bounds[i]
                if value < lower or value > upper:
                    return False
        return True

    def _clamp_to_bounds(self, array: np.ndarray,
                        bounds: List[Tuple[float, float]]) -> np.ndarray:
        """Clamp array values to their respective bounds."""
        clamped = array.copy()
        for i in range(len(clamped)):
            if i < len(bounds):
                lower, upper = bounds[i]
                clamped[i] = max(lower, min(upper, clamped[i]))
        return clamped

    def _update_performance_metrics(self, response: OptimizationResponse):
        """Update global performance metrics."""
        with self._optimization_lock:
            self._performance_metrics['total_optimizations'] += 1

            if response.success:
                self._performance_metrics['successful_optimizations'] += 1
            else:
                self._performance_metrics['failed_optimizations'] += 1

            self._performance_metrics['total_execution_time'] += response.execution_time

            # Update average
            total = self._performance_metrics['total_optimizations']
            if total > 0:
                self._performance_metrics['average_objective_evaluations'] = (
                    (self._performance_metrics['average_objective_evaluations'] * (total - 1) +
                     response.function_evaluations) / total
                )

    def _calculate_concurrent_performance_metrics(self, results: List[OptimizationResponse]) -> Dict[str, Any]:
        """Calculate performance metrics for concurrent optimization run."""
        if not results:
            return {}

        successful_results = [r for r in results if r.success]

        metrics = {
            'success_rate': len(successful_results) / len(results),
            'avg_execution_time': np.mean([r.execution_time for r in results]),
            'max_execution_time': max(r.execution_time for r in results),
            'min_execution_time': min(r.execution_time for r in results),
            'avg_function_evaluations': np.mean([r.function_evaluations for r in results]),
            'avg_iterations': np.mean([r.iterations for r in results]),
            'thread_distribution': {}
        }

        # Calculate thread distribution
        thread_counts = {}
        for result in results:
            thread_id = result.thread_id
            thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1

        metrics['thread_distribution'] = thread_counts

        # Calculate cache performance if available
        total_cache_hits = 0
        total_cache_size = 0
        cache_results = [r for r in results if r.cache_stats]

        if cache_results:
            for result in cache_results:
                cache_stats = result.cache_stats
                total_cache_size += cache_stats.get('cache_size', 0)

            metrics['avg_cache_size'] = total_cache_size / len(cache_results)

        return metrics

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        with self._optimization_lock:
            return self._performance_metrics.copy()

    def get_active_optimizations(self) -> Dict[int, str]:
        """Get currently active optimizations."""
        with self._optimization_lock:
            return self._active_optimizations.copy()

    def reset_performance_metrics(self):
        """Reset performance metrics."""
        with self._optimization_lock:
            self._performance_metrics = {
                'total_optimizations': 0,
                'successful_optimizations': 0,
                'failed_optimizations': 0,
                'total_execution_time': 0.0,
                'average_objective_evaluations': 0.0
            }


# Factory function
def create_thread_safe_optimization_engine(duckdb_resource: DuckDBResource,
                                         max_concurrent: int = 4) -> ThreadSafeOptimizationEngine:
    """Create thread-safe optimization engine."""
    return ThreadSafeOptimizationEngine(duckdb_resource, max_concurrent)
