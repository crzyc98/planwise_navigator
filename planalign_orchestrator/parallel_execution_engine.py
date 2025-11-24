#!/usr/bin/env python3
"""
Parallel Execution Engine for dbt Models

Provides sophisticated parallel execution capabilities while preserving data integrity
and deterministic results. Supports dependency-aware scheduling with resource management.
"""

from __future__ import annotations

import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Callable, Tuple
from pathlib import Path
from queue import Queue, Empty
import psutil

from .model_dependency_analyzer import ModelDependencyAnalyzer, ParallelizationOpportunity
from .model_execution_types import ModelClassifier, ModelExecutionType
from .dbt_runner import DbtRunner, DbtResult
from .resource_manager import ResourceManager, ResourcePressure
from .logger import ProductionLogger


@dataclass
class ExecutionContext:
    """Context information for model execution."""
    simulation_year: int
    dbt_vars: Dict[str, Any]
    stage_name: str
    execution_id: str
    start_time: float = field(default_factory=time.perf_counter)


@dataclass
class ExecutionResult:
    """Result of parallel execution phase."""
    success: bool
    model_results: Dict[str, DbtResult]
    execution_time: float
    parallelism_achieved: int
    resource_usage: Dict[str, float]
    errors: List[str] = field(default_factory=list)


@dataclass
class LegacyResourceMonitor:
    """Legacy resource monitor for backward compatibility."""
    memory_threshold_mb: float = 4000.0  # 4GB default
    cpu_threshold_pct: float = 90.0

    def check_resources(self) -> Dict[str, Any]:
        """Check current resource utilization."""
        memory_mb = psutil.virtual_memory().used / 1024 / 1024
        cpu_pct = psutil.cpu_percent(interval=1)

        return {
            "memory_mb": memory_mb,
            "cpu_percent": cpu_pct,
            "memory_pressure": memory_mb > self.memory_threshold_mb,
            "cpu_pressure": cpu_pct > self.cpu_threshold_pct,
            "safe_for_parallelization": memory_mb < self.memory_threshold_mb and cpu_pct < self.cpu_threshold_pct
        }


class ParallelExecutionEngine:
    """Engine for executing dbt models with sophisticated parallelization and advanced resource management."""

    def __init__(
        self,
        dbt_runner: DbtRunner,
        dependency_analyzer: ModelDependencyAnalyzer,
        *,
        max_workers: int = 4,
        resource_monitoring: bool = True,
        deterministic_execution: bool = True,
        memory_limit_mb: float = 4000.0,
        verbose: bool = False,
        resource_manager: Optional[ResourceManager] = None,
        logger: Optional[ProductionLogger] = None,
        enable_adaptive_scaling: bool = True
    ):
        self.dbt_runner = dbt_runner
        self.dependency_analyzer = dependency_analyzer
        self.max_workers = max_workers
        self.resource_monitoring = resource_monitoring
        self.deterministic_execution = deterministic_execution
        self.verbose = verbose
        self.enable_adaptive_scaling = enable_adaptive_scaling
        self.logger = logger

        self.classifier = ModelClassifier()

        # Advanced resource management (S067-03)
        if resource_manager is not None:
            self.resource_manager = resource_manager
            self.legacy_resource_monitor = None
        else:
            # Fall back to legacy resource monitoring for backward compatibility
            self.resource_manager = None
            self.legacy_resource_monitor = LegacyResourceMonitor(memory_threshold_mb=memory_limit_mb)

        # Thread safety
        self._execution_lock = threading.RLock()
        self._active_executions: Set[str] = set()

        # Adaptive scaling state
        self._current_thread_count = max_workers
        self._scaling_history: List[Dict[str, Any]] = []

        if verbose:
            print(f"🔧 ParallelExecutionEngine initialized:")
            print(f"   Max workers: {max_workers}")
            print(f"   Resource monitoring: {resource_monitoring}")
            print(f"   Deterministic execution: {deterministic_execution}")
            print(f"   Memory limit: {memory_limit_mb}MB")
            print(f"   Advanced resource management: {'enabled' if resource_manager else 'disabled'}")
            print(f"   Adaptive scaling: {'enabled' if enable_adaptive_scaling else 'disabled'}")

    def execute_stage_with_parallelization(
        self,
        stage_models: List[str],
        context: ExecutionContext,
        enable_conditional_parallelization: bool = False
    ) -> ExecutionResult:
        """Execute a stage with intelligent parallelization and advanced resource management."""

        if self.verbose:
            print(f"🚀 Executing stage {context.stage_name} with {len(stage_models)} models")

        start_time = time.perf_counter()

        # Advanced resource management integration (S067-03)
        if self.resource_manager:
            # Use advanced resource management
            if not self.resource_manager.check_resource_health():
                if self.verbose:
                    print("⚠️ Critical resource pressure detected, falling back to sequential execution")
                return self._execute_sequential_fallback(stage_models, context)

            # Adaptive thread count optimization
            if self.enable_adaptive_scaling:
                optimal_threads, reason = self.resource_manager.optimize_thread_count(
                    self._current_thread_count,
                    {"stage": context.stage_name, "model_count": len(stage_models)}
                )

                if optimal_threads != self._current_thread_count:
                    if self.verbose:
                        print(f"📊 Adjusting thread count: {self._current_thread_count} → {optimal_threads} ({reason})")
                    self._current_thread_count = optimal_threads

                    # Record scaling decision
                    self._scaling_history.append({
                        "timestamp": time.time(),
                        "stage": context.stage_name,
                        "old_threads": self._current_thread_count,
                        "new_threads": optimal_threads,
                        "reason": reason
                    })

            effective_max_workers = self._current_thread_count

        elif self.legacy_resource_monitor and self.resource_monitoring:
            # Fallback to legacy resource monitoring
            initial_resources = self.legacy_resource_monitor.check_resources()
            if not initial_resources["safe_for_parallelization"]:
                if self.verbose:
                    print("⚠️ Resource pressure detected, falling back to sequential execution")
                return self._execute_sequential_fallback(stage_models, context)
            effective_max_workers = self.max_workers
        else:
            # No resource monitoring
            effective_max_workers = self.max_workers

        # Create execution plan with adaptive thread count
        execution_plan = self.dependency_analyzer.create_execution_plan(
            stage_models,
            max_parallelism=effective_max_workers,
            enable_conditional_parallelization=enable_conditional_parallelization
        )

        if self.verbose:
            self._log_execution_plan(execution_plan)

        # Execute phases
        all_results: Dict[str, DbtResult] = {}
        total_parallelism = 0
        errors = []

        for phase in execution_plan["execution_phases"]:
            try:
                if phase["type"] == "parallel":
                    phase_result = self._execute_parallel_phase(phase, context)
                    total_parallelism = max(total_parallelism, phase_result.parallelism_achieved)
                else:
                    phase_result = self._execute_sequential_phase(phase, context)

                all_results.update(phase_result.model_results)
                errors.extend(phase_result.errors)

                if not phase_result.success:
                    break

            except Exception as e:
                errors.append(f"Phase execution failed: {str(e)}")
                break

        execution_time = time.perf_counter() - start_time

        # Final resource check and performance recording
        final_resources = {}
        if self.resource_manager:
            final_resources = self.resource_manager.get_resource_status()

            # Record performance for future optimization
            if self.enable_adaptive_scaling and total_parallelism > 0:
                self.resource_manager.thread_adjuster.record_performance(
                    total_parallelism, execution_time
                )

        elif self.legacy_resource_monitor and self.resource_monitoring:
            final_resources = self.legacy_resource_monitor.check_resources()

        # Enhanced execution result with resource management metrics
        execution_result = ExecutionResult(
            success=len(errors) == 0 and all(r.success for r in all_results.values()),
            model_results=all_results,
            execution_time=execution_time,
            parallelism_achieved=total_parallelism,
            resource_usage=final_resources,
            errors=errors
        )

        # Log execution summary with resource metrics
        if self.verbose and self.resource_manager:
            resource_status = final_resources
            print(f"📈 Stage execution complete: {context.stage_name}")
            print(f"   Duration: {execution_time:.1f}s")
            print(f"   Parallelism: {total_parallelism} threads")
            print(f"   Memory: {resource_status.get('memory', {}).get('usage_mb', 0):.0f}MB")
            print(f"   Success: {execution_result.success}")

        return execution_result

    def _execute_parallel_phase(
        self,
        phase: Dict[str, Any],
        context: ExecutionContext
    ) -> ExecutionResult:
        """Execute a parallel phase with thread pool and deterministic result collection."""

        models = phase["models"]
        max_parallel = min(len(models), self.max_workers)

        if self.verbose:
            print(f"   🔄 Parallel phase: {len(models)} models, {max_parallel} threads")
            print(f"      Models: {', '.join(models)}")
            print(f"      Group: {phase.get('group', 'unknown')}")
            print(f"      Estimated speedup: {phase.get('estimated_speedup', 1.0):.1f}x")

        # Validate execution safety
        safety_check = self.dependency_analyzer.validate_execution_safety(models)
        if not safety_check["safe"]:
            if self.verbose:
                print(f"   ⚠️ Safety issues detected, falling back to sequential:")
                for issue in safety_check["issues"]:
                    print(f"      - {issue}")

            return self._execute_sequential_phase(
                {"type": "sequential", "models": models}, context
            )

        start_time = time.perf_counter()
        model_results = {}
        errors = []

        # Ensure deterministic execution if requested
        if self.deterministic_execution:
            models = sorted(models)  # Deterministic ordering

        # DETERMINISM FIX: Use deterministic thread-safe execution
        if self.deterministic_execution:
            return self._execute_parallel_deterministic(models, context, max_parallel, start_time)

        with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="dbt-model") as executor:
            # Submit all models
            future_to_model = {}
            for model in models:
                future = executor.submit(self._execute_single_model, model, context)
                future_to_model[future] = model

            # Collect results as they complete
            for future in as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    result = future.result()
                    model_results[model] = result

                    if not result.success:
                        errors.append(f"Model {model} failed with code {result.return_code}")
                        if self.verbose:
                            print(f"   ❌ {model}: failed")
                    elif self.verbose:
                        print(f"   ✅ {model}: {result.execution_time:.1f}s")

                except Exception as e:
                    errors.append(f"Model {model} raised exception: {str(e)}")
                    if self.verbose:
                        print(f"   💥 {model}: {str(e)}")

        execution_time = time.perf_counter() - start_time

        if self.verbose:
            success_count = sum(1 for r in model_results.values() if r.success)
            print(f"   📊 Parallel phase complete: {success_count}/{len(models)} succeeded in {execution_time:.1f}s")

        return ExecutionResult(
            success=len(errors) == 0,
            model_results=model_results,
            execution_time=execution_time,
            parallelism_achieved=max_parallel,
            resource_usage={},
            errors=errors
        )

    def _execute_parallel_deterministic(
        self,
        models: List[str],
        context: ExecutionContext,
        max_parallel: int,
        start_time: float
    ) -> ExecutionResult:
        """Execute parallel phase with deterministic result collection for reproducible results."""

        if self.verbose:
            print(f"   🔐 Deterministic parallel execution: {len(models)} models")

        model_results = {}
        errors = []

        # DETERMINISM FIX: Use a queue to maintain deterministic execution order
        from queue import Queue
        result_queue = Queue()

        with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="dbt-model-det") as executor:
            # Submit models in sorted order for deterministic execution
            future_to_model = {}
            for i, model in enumerate(models):
                # Create deterministic execution context for each model
                model_context = ExecutionContext(
                    simulation_year=context.simulation_year,
                    dbt_vars=context.dbt_vars.copy(),
                    stage_name=context.stage_name,
                    execution_id=f"{context.execution_id}:model_{i:03d}:{model}",
                    start_time=context.start_time
                )

                future = executor.submit(self._execute_single_model_deterministic, model, model_context, i)
                future_to_model[future] = (model, i)

            # Collect results in deterministic order (not completion order)
            completed_futures = {}

            for future in as_completed(future_to_model):
                model, order_idx = future_to_model[future]
                try:
                    result = future.result()
                    completed_futures[order_idx] = (model, result)

                    if not result.success:
                        errors.append(f"Model {model} failed with code {result.return_code}")
                        if self.verbose:
                            print(f"   ❌ {model}: failed (order: {order_idx})")
                    elif self.verbose:
                        print(f"   ✅ {model}: {result.execution_time:.1f}s (order: {order_idx})")

                except Exception as e:
                    errors.append(f"Model {model} raised exception: {str(e)}")
                    if self.verbose:
                        print(f"   💥 {model}: {str(e)} (order: {order_idx})")

            # Process results in deterministic order
            for i in sorted(completed_futures.keys()):
                model, result = completed_futures[i]
                model_results[model] = result

        execution_time = time.perf_counter() - start_time

        if self.verbose:
            success_count = sum(1 for r in model_results.values() if r.success)
            print(f"   🔐 Deterministic phase complete: {success_count}/{len(models)} succeeded in {execution_time:.1f}s")

        return ExecutionResult(
            success=len(errors) == 0,
            model_results=model_results,
            execution_time=execution_time,
            parallelism_achieved=max_parallel,
            resource_usage={},
            errors=errors
        )

    def _execute_parallel_with_monitoring(
        self,
        models: List[str],
        context: ExecutionContext,
        max_parallel: int,
        resource_manager: ResourceManager
    ) -> ExecutionResult:
        """Execute parallel phase with advanced resource monitoring."""

        start_time = time.perf_counter()
        model_results = {}
        errors = []

        # Ensure deterministic execution if requested
        if self.deterministic_execution:
            models = sorted(models)

        # Track per-thread resource usage
        thread_resource_tracking = {}

        with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="dbt-model") as executor:
            # Submit all models with resource tracking
            future_to_model = {}
            for model in models:
                future = executor.submit(self._execute_single_model_with_monitoring, model, context, resource_manager)
                future_to_model[future] = model

            # Collect results as they complete with resource monitoring
            for future in as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    result = future.result()
                    model_results[model] = result

                    if not result.success:
                        errors.append(f"Model {model} failed with code {result.return_code}")
                        if self.verbose:
                            print(f"   ❌ {model}: failed")
                    elif self.verbose:
                        print(f"   ✅ {model}: {result.execution_time:.1f}s")

                    # Check for resource pressure after each model completion
                    if not resource_manager.check_resource_health():
                        if self.verbose:
                            print(f"   ⚠️ Resource pressure detected, may affect remaining models")

                except Exception as e:
                    errors.append(f"Model {model} raised exception: {str(e)}")
                    if self.verbose:
                        print(f"   💥 {model}: {str(e)}")

        execution_time = time.perf_counter() - start_time

        if self.verbose:
            success_count = sum(1 for r in model_results.values() if r.success)
            print(f"   📈 Parallel phase complete: {success_count}/{len(models)} succeeded in {execution_time:.1f}s")

        return ExecutionResult(
            success=len(errors) == 0,
            model_results=model_results,
            execution_time=execution_time,
            parallelism_achieved=max_parallel,
            resource_usage=resource_manager.get_resource_status() if resource_manager else {},
            errors=errors
        )

    def _execute_parallel_legacy(
        self,
        models: List[str],
        context: ExecutionContext,
        max_parallel: int
    ) -> ExecutionResult:
        """Legacy parallel execution without advanced resource management."""

        start_time = time.perf_counter()
        model_results = {}
        errors = []

        # Ensure deterministic execution if requested
        if self.deterministic_execution:
            models = sorted(models)

        with ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="dbt-model") as executor:
            # Submit all models
            future_to_model = {}
            for model in models:
                future = executor.submit(self._execute_single_model, model, context)
                future_to_model[future] = model

            # Collect results as they complete
            for future in as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    result = future.result()
                    model_results[model] = result

                    if not result.success:
                        errors.append(f"Model {model} failed with code {result.return_code}")
                        if self.verbose:
                            print(f"   ❌ {model}: failed")
                    elif self.verbose:
                        print(f"   ✅ {model}: {result.execution_time:.1f}s")

                except Exception as e:
                    errors.append(f"Model {model} raised exception: {str(e)}")
                    if self.verbose:
                        print(f"   💥 {model}: {str(e)}")

        execution_time = time.perf_counter() - start_time

        if self.verbose:
            success_count = sum(1 for r in model_results.values() if r.success)
            print(f"   📈 Parallel phase complete: {success_count}/{len(models)} succeeded in {execution_time:.1f}s")

        return ExecutionResult(
            success=len(errors) == 0,
            model_results=model_results,
            execution_time=execution_time,
            parallelism_achieved=max_parallel,
            resource_usage={},
            errors=errors
        )

    def _execute_sequential_phase(
        self,
        phase: Dict[str, Any],
        context: ExecutionContext
    ) -> ExecutionResult:
        """Execute a sequential phase."""

        models = phase["models"]

        if self.verbose:
            print(f"   📋 Sequential phase: {len(models)} models")
            if "reason" in phase:
                print(f"      Reason: {phase['reason']}")

        start_time = time.perf_counter()
        model_results = {}
        errors = []

        for model in models:
            try:
                result = self._execute_single_model(model, context)
                model_results[model] = result

                if not result.success:
                    errors.append(f"Model {model} failed with code {result.return_code}")
                    if self.verbose:
                        print(f"   ❌ {model}: failed")
                    break  # Stop on first failure in sequential phase
                elif self.verbose:
                    print(f"   ✅ {model}: {result.execution_time:.1f}s")

            except Exception as e:
                errors.append(f"Model {model} raised exception: {str(e)}")
                if self.verbose:
                    print(f"   💥 {model}: {str(e)}")
                break

        execution_time = time.perf_counter() - start_time

        return ExecutionResult(
            success=len(errors) == 0,
            model_results=model_results,
            execution_time=execution_time,
            parallelism_achieved=1,
            resource_usage={},
            errors=errors
        )

    def _execute_single_model(
        self,
        model: str,
        context: ExecutionContext
    ) -> DbtResult:
        """Execute a single model with proper context."""

        with self._execution_lock:
            execution_key = f"{context.execution_id}:{model}"
            if execution_key in self._active_executions:
                raise RuntimeError(f"Model {model} is already being executed")
            self._active_executions.add(execution_key)

        try:
            # Resource check before execution if monitoring enabled (legacy)
            if self.legacy_resource_monitor and self.resource_monitoring:
                resources = self.legacy_resource_monitor.check_resources()
                if resources["memory_pressure"]:
                    if self.verbose:
                        print(f"   ⚠️ Memory pressure during {model} execution: {resources['memory_mb']:.0f}MB")

            # DETERMINISM FIX: Create deterministic dbt_vars with thread-local seed
            deterministic_vars = context.dbt_vars.copy()

            if self.deterministic_execution:
                # Generate deterministic thread-local seed based on model name and context
                import hashlib
                thread_seed_str = f"{context.execution_id}:{model}:{context.simulation_year}:{context.dbt_vars.get('random_seed', 42)}"
                thread_seed_hash = hashlib.sha256(thread_seed_str.encode()).hexdigest()[:8]
                thread_seed = int(thread_seed_hash, 16) % (2**31)  # Ensure 32-bit signed int

                # Override random_seed with deterministic thread-local value
                deterministic_vars['thread_local_seed'] = thread_seed
                deterministic_vars['model_execution_id'] = f"{context.execution_id}:{model}"

            # Execute the model
            result = self.dbt_runner.execute_command(
                ["run", "--select", model],
                simulation_year=context.simulation_year,
                dbt_vars=deterministic_vars,
                stream_output=False,  # Disable streaming for parallel execution
                retry=True,
                max_attempts=2  # Reduced retries for parallel execution
            )

            return result

        finally:
            with self._execution_lock:
                self._active_executions.discard(execution_key)

    def _execute_single_model_deterministic(
        self,
        model: str,
        context: ExecutionContext,
        execution_order: int
    ) -> DbtResult:
        """Execute a single model with deterministic state isolation for reproducible results."""

        with self._execution_lock:
            execution_key = f"{context.execution_id}:{model}:{execution_order}"
            if execution_key in self._active_executions:
                raise RuntimeError(f"Model {model} is already being executed")
            self._active_executions.add(execution_key)

        try:
            # Resource check before execution if monitoring enabled (legacy)
            if self.legacy_resource_monitor and self.resource_monitoring:
                resources = self.legacy_resource_monitor.check_resources()
                if resources["memory_pressure"]:
                    if self.verbose:
                        print(f"   ⚠️ Memory pressure during {model} execution: {resources['memory_mb']:.0f}MB")

            # DETERMINISM FIX: Create completely isolated deterministic execution context
            deterministic_vars = context.dbt_vars.copy()

            # Generate deterministic model-specific seed
            import hashlib
            model_seed_str = f"{execution_order:03d}:{model}:{context.simulation_year}:{context.dbt_vars.get('random_seed', 42)}"
            model_seed_hash = hashlib.sha256(model_seed_str.encode()).hexdigest()[:8]
            model_seed = int(model_seed_hash, 16) % (2**31)  # Ensure 32-bit signed int

            # Override dbt vars with deterministic values
            deterministic_vars.update({
                'thread_local_seed': model_seed,
                'model_execution_order': execution_order,
                'model_execution_id': execution_key,
                'deterministic_execution': True
            })

            if self.verbose:
                print(f"   🔐 {model} (order: {execution_order:03d}, seed: {model_seed})")

            # Execute the model with isolated state
            result = self.dbt_runner.execute_command(
                ["run", "--select", model],
                simulation_year=context.simulation_year,
                dbt_vars=deterministic_vars,
                stream_output=False,  # Disable streaming for parallel execution
                retry=True,
                max_attempts=2  # Reduced retries for parallel execution
            )

            return result

        finally:
            with self._execution_lock:
                self._active_executions.discard(execution_key)

    def _execute_single_model_with_monitoring(
        self,
        model: str,
        context: ExecutionContext,
        resource_manager: ResourceManager
    ) -> DbtResult:
        """Execute a single model with advanced resource monitoring."""

        with self._execution_lock:
            execution_key = f"{context.execution_id}:{model}"
            if execution_key in self._active_executions:
                raise RuntimeError(f"Model {model} is already being executed")
            self._active_executions.add(execution_key)

        thread_id = threading.current_thread().name

        try:
            # Track thread-specific memory usage
            resource_manager.memory_monitor.track_thread_memory(thread_id)

            # Resource health check before execution
            if not resource_manager.check_resource_health():
                if self.verbose:
                    print(f"   ⚠️ Resource pressure during {model} execution")

                # Trigger resource cleanup if needed
                cleanup_result = resource_manager.trigger_resource_cleanup()
                if self.logger:
                    self.logger.info(f"Resource cleanup for {model}", **cleanup_result)

            # Execute the model with resource monitoring context
            with resource_manager.monitor_execution(f"model_{model}", 1):
                result = self.dbt_runner.execute_command(
                    ["run", "--select", model],
                    simulation_year=context.simulation_year,
                    dbt_vars=context.dbt_vars,
                    stream_output=False,  # Disable streaming for parallel execution
                    retry=True,
                    max_attempts=2  # Reduced retries for parallel execution
                )

            return result

        finally:
            with self._execution_lock:
                self._active_executions.discard(execution_key)

    def _execute_sequential_fallback(
        self,
        models: List[str],
        context: ExecutionContext
    ) -> ExecutionResult:
        """Fallback to sequential execution when parallelization isn't safe."""

        if self.verbose:
            print("   🔄 Sequential fallback execution")

        start_time = time.perf_counter()
        model_results = {}
        errors = []

        for model in models:
            try:
                result = self._execute_single_model(model, context)
                model_results[model] = result

                if not result.success:
                    errors.append(f"Model {model} failed with code {result.return_code}")
                    break

            except Exception as e:
                errors.append(f"Model {model} raised exception: {str(e)}")
                break

        execution_time = time.perf_counter() - start_time

        return ExecutionResult(
            success=len(errors) == 0,
            model_results=model_results,
            execution_time=execution_time,
            parallelism_achieved=1,
            resource_usage={},
            errors=errors
        )

    def _log_execution_plan(self, plan: Dict[str, Any]) -> None:
        """Log the execution plan for transparency."""
        print(f"   📋 Execution plan:")
        print(f"      Total models: {plan['total_models']}")
        print(f"      Parallelizable: {plan['parallelizable_models']}")
        print(f"      Estimated speedup: {plan['estimated_total_speedup']:.1f}x")
        print(f"      Phases: {len(plan['execution_phases'])}")

        for i, phase in enumerate(plan["execution_phases"], 1):
            if phase["type"] == "parallel":
                print(f"         Phase {i} (Parallel): {len(phase['models'])} models, {phase.get('group', 'mixed')} group")
            else:
                print(f"         Phase {i} (Sequential): {len(phase['models'])} models")

    def get_parallelization_statistics(self) -> Dict[str, Any]:
        """Get statistics about parallelization capabilities."""
        all_models = list(self.dependency_analyzer.dependency_graph.nodes.keys())

        parallel_safe = self.classifier.get_parallel_safe_models(all_models)
        sequential = self.classifier.get_sequential_models(all_models)
        conditional = [
            model for model in all_models
            if self.classifier.classify_model(model).execution_type == ModelExecutionType.CONDITIONAL
        ]

        return {
            "total_models": len(all_models),
            "parallel_safe": len(parallel_safe),
            "sequential_required": len(sequential),
            "conditional": len(conditional),
            "parallelization_ratio": len(parallel_safe) / len(all_models) if all_models else 0,
            "max_theoretical_speedup": min(len(parallel_safe), self.max_workers) if parallel_safe else 1,
            "parallel_groups": self.classifier.get_parallel_groups(parallel_safe),
            "resource_limits": {
                "max_workers": self.max_workers,
                "memory_limit_mb": self.legacy_resource_monitor.memory_threshold_mb if self.legacy_resource_monitor else 0,
                "cpu_threshold_pct": self.legacy_resource_monitor.cpu_threshold_pct if self.legacy_resource_monitor else 0
            }
        }

    def validate_stage_parallelization(self, stage_models: List[str]) -> Dict[str, Any]:
        """Validate parallelization safety for a specific stage."""
        opportunities = self.dependency_analyzer.identify_parallelization_opportunities(
            stage_models, self.max_workers
        )

        total_parallelizable = sum(len(op.parallel_models) for op in opportunities)
        high_safety = sum(
            len(op.parallel_models) for op in opportunities
            if op.safety_level == "high"
        )

        return {
            "stage_models": len(stage_models),
            "parallelizable_models": total_parallelizable,
            "high_safety_models": high_safety,
            "parallelization_opportunities": len(opportunities),
            "estimated_speedup": max([op.estimated_speedup for op in opportunities] + [1.0]),
            "safety_breakdown": {
                op.safety_level: len(op.parallel_models)
                for op in opportunities
            },
            "recommendations": self._generate_parallelization_recommendations(opportunities)
        }

    def _generate_parallelization_recommendations(
        self,
        opportunities: List[ParallelizationOpportunity]
    ) -> List[str]:
        """Generate recommendations for improving parallelization."""
        recommendations = []

        high_safety_ops = [op for op in opportunities if op.safety_level == "high"]
        if high_safety_ops:
            total_models = sum(len(op.parallel_models) for op in high_safety_ops)
            recommendations.append(
                f"Enable parallelization for {total_models} high-safety models to achieve "
                f"{max(op.estimated_speedup for op in high_safety_ops):.1f}x speedup"
            )

        medium_safety_ops = [op for op in opportunities if op.safety_level == "medium"]
        if medium_safety_ops:
            recommendations.append(
                f"Consider enabling conditional parallelization for {sum(len(op.parallel_models) for op in medium_safety_ops)} additional models"
            )

        if not opportunities:
            recommendations.append("No parallelization opportunities found - all models require sequential execution")

        return recommendations
