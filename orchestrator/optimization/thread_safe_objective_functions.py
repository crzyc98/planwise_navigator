"""
Thread-safe objective functions for compensation optimization.

Implements thread-safe, pure functional objective functions that eliminate
global state mutations and provide numerical stability for concurrent optimization.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import math
import threading
import hashlib
import json
import time
from typing import Dict, Any, Optional, List, Callable
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import tempfile
import os
import copy

from orchestrator.resources.duckdb_resource import DuckDBResource


@dataclass
class OptimizationResult:
    """Result of a single objective evaluation."""
    objective_value: float
    computation_time: float
    thread_id: int
    cache_hit: bool
    error: Optional[str] = None


class RobustNumericalCalculations:
    """Robust numerical calculations with division-by-zero protection."""

    @staticmethod
    def safe_growth_rate(current: float, baseline: float,
                        max_growth_cap: float = 50.0) -> float:
        """Calculate growth rate with division-by-zero protection."""
        # Handle edge cases
        if math.isnan(current) or math.isnan(baseline):
            return 0.0

        if baseline == 0.0:
            if current == 0.0:
                return 0.0
            else:
                # Return capped growth when growing from zero baseline
                return min(max_growth_cap, max(-max_growth_cap, current * 100))

        # Calculate growth rate with overflow protection
        try:
            growth_rate = ((current - baseline) / baseline) * 100

            # Handle infinite or very large values
            if math.isinf(growth_rate) or abs(growth_rate) > 1000:
                return max_growth_cap if growth_rate > 0 else -max_growth_cap

            return growth_rate

        except (ZeroDivisionError, OverflowError):
            return 0.0

    @staticmethod
    def safe_coefficient_of_variation(mean: float, std: float) -> float:
        """Calculate coefficient of variation with protection."""
        if mean == 0.0 or math.isnan(mean) or math.isnan(std):
            return 0.0

        try:
            cv = abs(std / mean)  # Use absolute value for stability
            return min(cv, 10.0)  # Cap at 1000% variation
        except (ZeroDivisionError, OverflowError):
            return 0.0

    @staticmethod
    def safe_normalize(value: float, min_val: float, max_val: float) -> float:
        """Normalize value with range protection."""
        if max_val == min_val:
            return 0.5  # Return middle value if no range

        try:
            normalized = (value - min_val) / (max_val - min_val)
            return max(0.0, min(1.0, normalized))  # Clamp to [0, 1]
        except (ZeroDivisionError, OverflowError):
            return 0.5


class ThreadSafeParameterCache:
    """Thread-safe parameter caching with advanced memoization."""

    def __init__(self, max_size: int = 1000):
        self._cache = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._access_count = {}
        self._computation_times = {}

    def get_canonical_key(self, parameters: Dict[str, float]) -> str:
        """Generate canonical, thread-safe cache key."""
        # Sort parameters for consistent hashing
        sorted_items = sorted(parameters.items())
        # Create reproducible hash
        param_json = json.dumps(sorted_items, sort_keys=True)
        return hashlib.md5(param_json.encode()).hexdigest()

    def get_or_compute(self, parameters: Dict[str, float], objective_type: str,
                      compute_func: Callable) -> OptimizationResult:
        """Thread-safe get-or-compute pattern with improved coordination."""
        cache_key = f"{objective_type}:{self.get_canonical_key(parameters)}"
        thread_id = threading.get_ident()

        # Keep track of in-progress computations to avoid duplicate work
        if not hasattr(self, '_computing'):
            self._computing = set()
            self._computing_lock = threading.Lock()

        # First check - fast path for cache hits
        with self._lock:
            if cache_key in self._cache:
                self._access_count[cache_key] = self._access_count.get(cache_key, 0) + 1
                cached_result = self._cache[cache_key]
                return OptimizationResult(
                    objective_value=cached_result,
                    computation_time=self._computation_times.get(cache_key, 0.0),
                    thread_id=thread_id,
                    cache_hit=True
                )

        # Check if another thread is already computing this key
        with self._computing_lock:
            if cache_key in self._computing:
                # Another thread is computing, wait a bit and check cache again
                pass
            else:
                # Mark as computing
                self._computing.add(cache_key)
                should_compute = True

        if cache_key in getattr(self, '_computing', set()) and cache_key not in self._cache:
            # Wait briefly for the other thread to complete
            import time
            time.sleep(0.05)

            # Check cache again after waiting
            with self._lock:
                if cache_key in self._cache:
                    self._access_count[cache_key] = self._access_count.get(cache_key, 0) + 1
                    cached_result = self._cache[cache_key]
                    return OptimizationResult(
                        objective_value=cached_result,
                        computation_time=self._computation_times.get(cache_key, 0.0),
                        thread_id=thread_id,
                        cache_hit=True
                    )

        # Only proceed with computation if we marked ourselves as computing
        if not hasattr(self, '_computing') or cache_key not in self._computing:
            # Another thread is handling this, return a penalty value
            return OptimizationResult(
                objective_value=1000.0,  # Default penalty
                computation_time=0.0,
                thread_id=thread_id,
                cache_hit=False,
                error="Computation handled by another thread"
            )

        # Compute the result
        start_time = time.time()
        try:
            result = compute_func(parameters, objective_type)
            computation_time = time.time() - start_time

            # Store result in cache
            with self._lock:
                # Double check before storing
                if cache_key not in self._cache:
                    # Add to cache with eviction if needed
                    if len(self._cache) >= self._max_size:
                        self._evict_least_used()

                    self._cache[cache_key] = result
                    self._access_count[cache_key] = 1
                    self._computation_times[cache_key] = computation_time
                else:
                    # Another thread stored it first, use their result
                    result = self._cache[cache_key]
                    computation_time = self._computation_times.get(cache_key, computation_time)

                return OptimizationResult(
                    objective_value=result,
                    computation_time=computation_time,
                    thread_id=thread_id,
                    cache_hit=False
                )

        except Exception as e:
            return OptimizationResult(
                objective_value=float('inf'),  # High penalty for errors
                computation_time=time.time() - start_time,
                thread_id=thread_id,
                cache_hit=False,
                error=str(e)
            )
        finally:
            # Remove from computing set
            with self._computing_lock:
                if hasattr(self, '_computing') and cache_key in self._computing:
                    self._computing.remove(cache_key)

    def _evict_least_used(self):
        """Evict least recently used items."""
        if not self._access_count:
            return

        # Find least accessed item
        min_access = min(self._access_count.values())
        keys_to_remove = [k for k, v in self._access_count.items() if v == min_access]

        # Remove oldest among least accessed
        for key in keys_to_remove[:len(keys_to_remove)//2]:
            if key in self._cache:
                del self._cache[key]
            if key in self._access_count:
                del self._access_count[key]
            if key in self._computation_times:
                del self._computation_times[key]


class ThreadSafeAdaptivePenalty:
    """Thread-safe adaptive penalty scaling for optimization algorithms."""

    def __init__(self, initial_penalty: float = 1000.0):
        self._penalty_histories = {}  # Thread-specific penalty histories
        self._lock = threading.RLock()
        self._initial_penalty = initial_penalty

    def calculate_penalty(self, thread_id: int, error_history: List[float]) -> float:
        """Calculate adaptive penalty based on thread-specific history."""
        with self._lock:
            # Get thread-specific history
            if thread_id not in self._penalty_histories:
                self._penalty_histories[thread_id] = []

            thread_history = self._penalty_histories[thread_id]

            # Handle empty history case
            if not error_history:
                return self._initial_penalty

            # Calculate adaptive penalty
            penalty = self._compute_adaptive_penalty(error_history, thread_history)

            # Update thread-specific history
            thread_history.append(penalty)
            if len(thread_history) > 10:  # Keep last 10 penalties
                thread_history.pop(0)

            return penalty

    def _compute_adaptive_penalty(self, error_history: List[float],
                                 penalty_history: List[float]) -> float:
        """Compute adaptive penalty with numerical stability."""
        if not error_history:
            return self._initial_penalty

        # Use absolute values to prevent negative penalties
        recent_errors = [abs(error) for error in error_history[-5:]]
        recent_avg = np.mean(recent_errors)

        # Adaptive scaling based on error magnitude
        if recent_avg > 0:
            # Scale penalty proportionally to recent error magnitude
            base_penalty = max(10 * recent_avg, 100)
        else:
            base_penalty = self._initial_penalty

        # Apply exponential smoothing with penalty history
        if penalty_history:
            smoothing_factor = 0.7
            smoothed_penalty = (smoothing_factor * base_penalty +
                              (1 - smoothing_factor) * penalty_history[-1])
        else:
            smoothed_penalty = base_penalty

        # Ensure penalty is within reasonable bounds
        return max(min(smoothed_penalty, 10000.0), 10.0)

    def reset_thread_history(self, thread_id: int):
        """Reset penalty history for specific thread."""
        with self._lock:
            if thread_id in self._penalty_histories:
                del self._penalty_histories[thread_id]


class ThreadSafeObjectiveFunctions:
    """Thread-safe objective functions with immutable parameter handling."""

    def __init__(self, duckdb_resource: DuckDBResource, scenario_id: str, use_synthetic: bool = False):
        self.duckdb_resource = duckdb_resource
        self.scenario_id = scenario_id
        self.simulation_year = 2025
        self.use_synthetic = use_synthetic

        # Thread-safe components
        self._parameter_cache = ThreadSafeParameterCache()
        self._penalty_calculator = ThreadSafeAdaptivePenalty()
        self._numerical_calculator = RobustNumericalCalculations()

        # Thread-local storage for optimization state
        self._local_storage = threading.local()

        # Read-only baseline data (loaded once, never modified)
        self._baseline_data = self._load_baseline_data()

    def _load_baseline_data(self) -> Dict[str, Any]:
        """Load baseline data once for all optimizations."""
        try:
            with self.duckdb_resource.get_connection() as conn:
                # Load baseline workforce data
                baseline_query = """
                    SELECT
                        COUNT(*) as baseline_workforce,
                        AVG(current_compensation) as avg_compensation,
                        STDDEV(current_compensation) as std_compensation
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = 2024
                    AND detailed_status_code IN ('continuous_active', 'new_hire_active')
                """
                baseline_result = conn.execute(baseline_query).fetchone()

                if baseline_result:
                    return {
                        'baseline_workforce': baseline_result[0] or 0,
                        'avg_compensation': baseline_result[1] or 0.0,
                        'std_compensation': baseline_result[2] or 0.0
                    }
                else:
                    return {
                        'baseline_workforce': 0,
                        'avg_compensation': 0.0,
                        'std_compensation': 0.0
                    }
        except Exception as e:
            print(f"⚠️ Failed to load baseline data: {e}")
            return {
                'baseline_workforce': 1000,  # Default fallback
                'avg_compensation': 75000.0,
                'std_compensation': 15000.0
            }

    def cost_objective(self, parameters: Dict[str, float]) -> float:
        """Thread-safe cost objective function - no side effects."""
        def compute_cost(params: Dict[str, float], obj_type: str) -> float:
            if self.use_synthetic:
                return self._synthetic_cost_objective(params)
            else:
                return self._pure_cost_objective(params)

        result = self._parameter_cache.get_or_compute(parameters, 'cost', compute_cost)

        if result.error:
            thread_id = threading.get_ident()
            error_history = getattr(self._local_storage, 'error_history', [])
            return self._penalty_calculator.calculate_penalty(thread_id, error_history)

        return result.objective_value

    def equity_objective(self, parameters: Dict[str, float]) -> float:
        """Thread-safe equity objective function - no side effects."""
        def compute_equity(params: Dict[str, float], obj_type: str) -> float:
            if self.use_synthetic:
                return self._synthetic_equity_objective(params)
            else:
                return self._pure_equity_objective(params)

        result = self._parameter_cache.get_or_compute(parameters, 'equity', compute_equity)

        if result.error:
            thread_id = threading.get_ident()
            error_history = getattr(self._local_storage, 'error_history', [])
            return self._penalty_calculator.calculate_penalty(thread_id, error_history)

        return result.objective_value

    def targets_objective(self, parameters: Dict[str, float]) -> float:
        """Thread-safe targets objective function - no side effects."""
        def compute_targets(params: Dict[str, float], obj_type: str) -> float:
            if self.use_synthetic:
                return self._synthetic_targets_objective(params)
            else:
                return self._pure_targets_objective(params)

        result = self._parameter_cache.get_or_compute(parameters, 'targets', compute_targets)

        if result.error:
            thread_id = threading.get_ident()
            error_history = getattr(self._local_storage, 'error_history', [])
            return self._penalty_calculator.calculate_penalty(thread_id, error_history)

        return result.objective_value

    def _pure_cost_objective(self, parameters: Dict[str, float]) -> float:
        """Pure cost calculation without side effects."""
        # Calculate cost impact directly from parameters without file mutations
        baseline_workforce = self._baseline_data['baseline_workforce']
        avg_compensation = self._baseline_data['avg_compensation']

        if baseline_workforce == 0:
            return 0.0  # No cost impact if no workforce

        # Estimate cost impact from parameter changes
        total_cost_impact = 0.0

        # Merit rate impact
        for level in range(1, 6):
            param_name = f"merit_rate_level_{level}"
            if param_name in parameters:
                merit_rate = parameters[param_name]
                # Estimate employees per level (equal distribution assumption)
                level_employees = baseline_workforce / 5
                level_cost_impact = level_employees * avg_compensation * merit_rate
                total_cost_impact += level_cost_impact

        # COLA impact (affects all employees)
        if "cola_rate" in parameters:
            cola_rate = parameters["cola_rate"]
            cola_cost_impact = baseline_workforce * avg_compensation * cola_rate
            total_cost_impact += cola_cost_impact

        # New hire adjustment impact (estimated)
        if "new_hire_salary_adjustment" in parameters:
            new_hire_adj = parameters["new_hire_salary_adjustment"]
            # Estimate 10% new hires
            estimated_new_hires = baseline_workforce * 0.1
            new_hire_impact = estimated_new_hires * avg_compensation * (new_hire_adj - 1.0)
            total_cost_impact += new_hire_impact

        # Promotion impact
        for level in range(1, 5):  # Levels 1-4 can get promoted
            prob_param = f"promotion_probability_level_{level}"
            raise_param = f"promotion_raise_level_{level}"

            if prob_param in parameters and raise_param in parameters:
                prob = parameters[prob_param]
                raise_pct = parameters[raise_param]
                level_employees = baseline_workforce / 5
                promotion_impact = level_employees * prob * avg_compensation * raise_pct
                total_cost_impact += promotion_impact

        return total_cost_impact

    def _pure_equity_objective(self, parameters: Dict[str, float]) -> float:
        """Pure equity calculation without side effects."""
        # Calculate coefficient of variation across parameter values
        param_values = list(parameters.values())

        if not param_values:
            return 0.0

        mean_val = np.mean(param_values)
        std_val = np.std(param_values)

        # Use robust coefficient of variation calculation
        cv = self._numerical_calculator.safe_coefficient_of_variation(mean_val, std_val)

        return cv

    def _pure_targets_objective(self, parameters: Dict[str, float]) -> float:
        """Pure targets calculation without side effects."""
        baseline_workforce = self._baseline_data['baseline_workforce']

        if baseline_workforce == 0:
            return 1000.0  # High penalty for zero baseline

        # Estimate growth impact from parameters
        estimated_growth_rate = self._estimate_growth_from_parameters(parameters)
        target_growth_rate = 3.0  # 3% default target

        # Calculate squared error with robust growth calculation
        growth_error = self._numerical_calculator.safe_growth_rate(
            estimated_growth_rate, target_growth_rate
        )

        return growth_error ** 2

    def _estimate_growth_from_parameters(self, parameters: Dict[str, float]) -> float:
        """Estimate growth rate from parameters without running full simulation."""
        # This is a simplified estimation model
        # In practice, this could be a trained ML model or regression

        # Base growth from retention (opposite of termination)
        base_growth = 2.0  # Assume 2% base growth

        # Hiring impact (estimated)
        if "new_hire_salary_adjustment" in parameters:
            hiring_adjustment = parameters["new_hire_salary_adjustment"]
            # Higher salary adjustment should improve hiring
            hiring_impact = (hiring_adjustment - 1.0) * 10  # Scale factor
            base_growth += hiring_impact

        # Merit and COLA impact on retention (estimated)
        total_compensation_increase = 0.0

        # Sum merit rates
        for level in range(1, 6):
            param_name = f"merit_rate_level_{level}"
            if param_name in parameters:
                total_compensation_increase += parameters[param_name]

        # Add COLA
        if "cola_rate" in parameters:
            total_compensation_increase += parameters["cola_rate"]

        # Higher compensation increases should improve retention
        retention_impact = total_compensation_increase * 5  # Scale factor
        base_growth += retention_impact

        return max(0.0, min(20.0, base_growth))  # Cap between 0-20%

    def _synthetic_cost_objective(self, parameters: Dict[str, float]) -> float:
        """Synthetic cost objective for testing."""
        # Simple quadratic function for testing
        return sum(p**2 for p in parameters.values()) * 1000

    def _synthetic_equity_objective(self, parameters: Dict[str, float]) -> float:
        """Synthetic equity objective for testing."""
        param_values = list(parameters.values())
        if not param_values:
            return 0.0
        return abs(max(param_values) - min(param_values))

    def _synthetic_targets_objective(self, parameters: Dict[str, float]) -> float:
        """Synthetic targets objective for testing."""
        # Target all parameters to be around 0.05 (5%)
        target = 0.05
        return sum((p - target)**2 for p in parameters.values())

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        with self._parameter_cache._lock:
            return {
                'cache_size': len(self._parameter_cache._cache),
                'max_size': self._parameter_cache._max_size,
                'total_accesses': sum(self._parameter_cache._access_count.values()),
                'unique_computations': len(self._parameter_cache._access_count),
                'avg_computation_time': np.mean(list(self._parameter_cache._computation_times.values())) if self._parameter_cache._computation_times else 0.0
            }

    def clear_cache(self):
        """Clear the parameter cache."""
        with self._parameter_cache._lock:
            self._parameter_cache._cache.clear()
            self._parameter_cache._access_count.clear()
            self._parameter_cache._computation_times.clear()


# Factory function for backward compatibility
def create_thread_safe_objective_functions(duckdb_resource: DuckDBResource,
                                         scenario_id: str,
                                         use_synthetic: bool = False) -> ThreadSafeObjectiveFunctions:
    """Create thread-safe objective functions instance."""
    return ThreadSafeObjectiveFunctions(duckdb_resource, scenario_id, use_synthetic)
