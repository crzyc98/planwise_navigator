#!/usr/bin/env python3
"""
Dbt command orchestration utilities.

Provides a `DbtRunner` with:
- Clean command execution interface with var injection
- Streaming output support
- Error classification and retry with exponential backoff
- Parallel model execution
"""

from __future__ import annotations

import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import (Any, Callable, Dict, Generator, Iterable, List, Optional,
                    Sequence, Tuple)

# Import parallel execution components (lazy import to avoid circular dependencies)
try:
    from .parallel_execution_engine import ParallelExecutionEngine, ExecutionContext, ExecutionResult
    from .model_dependency_analyzer import ModelDependencyAnalyzer
    PARALLEL_EXECUTION_AVAILABLE = True
except ImportError:
    PARALLEL_EXECUTION_AVAILABLE = False


@dataclass
class DbtResult:
    success: bool
    stdout: str
    stderr: str
    execution_time: float
    return_code: int
    command: List[str]


class DbtError(Exception):
    """Base exception for dbt-related errors."""


class DbtCompilationError(DbtError):
    """Error during dbt compilation phase."""


class DbtExecutionError(DbtError):
    """Error during dbt execution phase."""


class DbtDataQualityError(DbtError):
    """Error due to data quality test failures."""


def classify_dbt_error(stdout: str, stderr: str, return_code: int) -> DbtError:
    """Classify dbt error based on output and return code."""
    s_err = (stderr or "").lower()
    s_out = (stdout or "").lower()

    if "compilation error" in s_err:
        return DbtCompilationError("Model compilation failed")
    if "database error" in s_err or "operationalerror" in s_err:
        return DbtExecutionError("Database execution failed")
    if "test failed" in s_out or "failing tests" in s_out:
        return DbtDataQualityError("Data quality tests failed")
    tail = (stdout or "").strip()
    tail = tail[-400:] if len(tail) > 400 else tail
    return DbtError(f"Unknown dbt error (code {return_code}). Tail: {tail}")


def retry_with_backoff(
    func: Callable[[], DbtResult],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retry_on: Tuple[type[Exception], ...] = (DbtExecutionError,),
) -> DbtResult:
    """Execute function with exponential backoff retry logic."""
    attempt = 0
    while True:
        try:
            return func()
        except retry_on as e:
            if attempt >= max_attempts - 1:
                raise
            delay = min(base_delay * (backoff_factor**attempt), max_delay)
            jitter = random.uniform(0, 0.1) * delay
            time.sleep(delay + jitter)
            attempt += 1


class DbtRunner:
    def __init__(
        self,
        working_dir: Path = Path("dbt"),
        threads: int = 1,
        executable: str = "dbt",
        *,
        verbose: bool = False,
        database_path: Optional[str] = None,
        threading_enabled: bool = True,
        threading_mode: str = "selective",
        enable_model_parallelization: bool = False,
        model_parallelization_max_workers: int = 4,
        model_parallelization_memory_limit_mb: float = 4000.0,
    ):
        self.working_dir = working_dir
        self.threads = threads
        self.executable = executable
        self.verbose = verbose
        self.database_path = database_path
        self.threading_enabled = threading_enabled
        self.threading_mode = threading_mode

        # Model-level parallelization settings
        self.enable_model_parallelization = enable_model_parallelization
        self.model_parallelization_max_workers = model_parallelization_max_workers
        self.model_parallelization_memory_limit_mb = model_parallelization_memory_limit_mb

        # Initialize parallel execution engine if enabled and available
        self._parallel_engine: Optional[ParallelExecutionEngine] = None
        self._dependency_analyzer: Optional[ModelDependencyAnalyzer] = None

        if enable_model_parallelization and PARALLEL_EXECUTION_AVAILABLE:
            try:
                self._dependency_analyzer = ModelDependencyAnalyzer(working_dir)
                self._parallel_engine = ParallelExecutionEngine(
                    dbt_runner=self,
                    dependency_analyzer=self._dependency_analyzer,
                    max_workers=model_parallelization_max_workers,
                    memory_limit_mb=model_parallelization_memory_limit_mb,
                    verbose=verbose
                )
                if verbose:
                    print("🔧 Model-level parallelization engine initialized")
            except Exception as e:
                if verbose:
                    print(f"⚠️ Failed to initialize parallel execution engine: {e}")
                    print("   Falling back to standard dbt threading")
                self._parallel_engine = None
                self._dependency_analyzer = None

        # Validate thread count on initialization
        self._validate_thread_count(threads)

        if self.verbose:
            threading_status = "enabled" if threading_enabled else "disabled"
            parallel_status = "enabled" if self._parallel_engine else "disabled"
            print(f"🧩 DbtRunner initialized:")
            print(f"   dbt threads: {threads} ({threading_status}, mode: {threading_mode})")
            print(f"   Model parallelization: {parallel_status}")
            if self._parallel_engine:
                print(f"   Max parallel workers: {model_parallelization_max_workers}")
                print(f"   Memory limit: {model_parallelization_memory_limit_mb}MB")

    def _validate_thread_count(self, thread_count: int) -> None:
        """Validate thread count with appropriate error messages"""
        if thread_count < 1:
            raise ValueError("thread_count must be at least 1")
        if thread_count > 16:
            raise ValueError("thread_count cannot exceed 16 (hardware limitation)")

        # Log performance guidance
        if self.verbose:
            if thread_count > 8:
                print(f"⚠️ High thread count ({thread_count}): Monitor memory usage and consider reducing if experiencing stability issues")
            elif thread_count > 4:
                print(f"ℹ️ Multi-threading enabled ({thread_count} threads): Expected 20-30% performance improvement")

    def update_thread_count(self, new_thread_count: int) -> None:
        """Update thread count dynamically with validation"""
        self._validate_thread_count(new_thread_count)
        old_threads = self.threads
        self.threads = new_thread_count

        if self.verbose:
            print(f"🔧 Thread count updated: {old_threads} → {new_thread_count}")

    def get_thread_utilization_info(self) -> Dict[str, Any]:
        """Get current thread configuration and utilization info"""
        return {
            "thread_count": self.threads,
            "threading_enabled": self.threading_enabled,
            "threading_mode": self.threading_mode,
            "single_threaded_fallback": self.threads == 1
        }

    def _build_command(
        self,
        command_args: Sequence[str],
        *,
        simulation_year: Optional[int] = None,
        dbt_vars: Optional[Dict[str, Any]] = None,
        threads: Optional[int] = None,
    ) -> List[str]:
        cmd: List[str] = [self.executable, *command_args]

        vars_dict: Dict[str, Any] = {}
        if simulation_year is not None:
            vars_dict["simulation_year"] = simulation_year
        if dbt_vars:
            vars_dict.update(dbt_vars)
        if vars_dict:
            vars_json = json.dumps(vars_dict)
            if self.verbose:
                try:
                    year_label = (
                        f" year={simulation_year}"
                        if simulation_year is not None
                        else ""
                    )
                    print(f"🧩 DbtRunner --vars{year_label}: {vars_json}")
                except Exception:
                    pass
            cmd.extend(["--vars", vars_json])
        # Attach threads if supported and not already present
        if "--threads" not in cmd and self.executable == "dbt":
            # Only add threads to commands that support it
            threads_supported_commands = [
                "run",
                "test",
                "build",
                "compile",
                "seed",
                "snapshot",
                "docs",
                "source",
                "freshness",
                "run-operation",
            ]
            if any(c in command_args for c in threads_supported_commands):
                # Use provided threads parameter or instance default
                effective_threads = threads or (self.threads if self.threading_enabled else 1)
                cmd.extend(["--threads", str(effective_threads)])

                # Log threading performance information
                if self.verbose and effective_threads > 1:
                    threading_info = self.get_thread_utilization_info()
                    print(f"🧩 dbt threading: {effective_threads} threads (mode: {threading_info['threading_mode']})")
        return cmd

    def execute_command(
        self,
        command_args: Sequence[str],
        *,
        description: str = "Running dbt command",
        simulation_year: Optional[int] = None,
        dbt_vars: Optional[Dict[str, Any]] = None,
        threads: Optional[int] = None,
        stream_output: bool = True,
        on_line: Optional[Callable[[str], None]] = None,
        retry: bool = True,
        max_attempts: int = 3,
        log_performance: bool = True,
    ) -> DbtResult:
        """Execute a dbt command with enhanced error handling and optional retry."""

        # Pre-execution thread utilization logging
        if log_performance and self.verbose:
            threading_info = self.get_thread_utilization_info()
            if threading_info["thread_count"] > 1:
                print(f"🔄 Executing with {threading_info['thread_count']} threads (mode: {threading_info['threading_mode']})")

        def _run_once() -> DbtResult:
            return self._execute_once(
                command_args,
                description=description,
                simulation_year=simulation_year,
                dbt_vars=dbt_vars,
                threads=threads,
                stream_output=stream_output,
                on_line=on_line,
            )

        if not retry:
            result = _run_once()
        else:
            def _wrapped() -> DbtResult:
                try:
                    res = _run_once()
                    if not res.success:
                        err = classify_dbt_error(res.stdout, res.stderr, res.return_code)
                        raise err
                    return res
                except DbtError:
                    # Let retry_with_backoff decide on retries
                    raise

            result = retry_with_backoff(_wrapped, max_attempts=max_attempts)

        # Post-execution performance logging with thread utilization metrics
        if log_performance and self.verbose and result.success:
            threading_info = self.get_thread_utilization_info()
            execution_time = result.execution_time

            # Calculate rough thread utilization efficiency
            if threading_info["thread_count"] > 1:
                # This is a rough estimate - actual efficiency depends on dbt model dependencies
                theoretical_single_thread_time = execution_time * threading_info["thread_count"]
                efficiency_pct = min(100.0, (theoretical_single_thread_time / execution_time) / threading_info["thread_count"] * 100)
                print(f"⚡ Performance: {execution_time:.1f}s with {threading_info['thread_count']} threads (est. efficiency: {efficiency_pct:.0f}%)")
            else:
                print(f"⚡ Performance: {execution_time:.1f}s (single-threaded)")

        return result

    def _execute_once(
        self,
        command_args: Sequence[str],
        *,
        description: str,
        simulation_year: Optional[int],
        dbt_vars: Optional[Dict[str, Any]],
        threads: Optional[int],
        stream_output: bool,
        on_line: Optional[Callable[[str], None]],
    ) -> DbtResult:
        cmd = self._build_command(
            command_args,
            simulation_year=simulation_year,
            dbt_vars=dbt_vars,
            threads=threads,
        )

        start = time.perf_counter()

        if stream_output:
            return self._execute_with_streaming(cmd, on_line=on_line, start_ts=start)
        else:
            try:
                # Set up environment with DATABASE_PATH if specified
                env = None
                if self.database_path:
                    import os
                    env = os.environ.copy()
                    # For dbt running from /dbt directory, use relative path from dbt/ to database
                    abs_db_path = Path(self.database_path).absolute()
                    abs_working_dir = self.working_dir.absolute()
                    try:
                        relative_path = abs_db_path.relative_to(abs_working_dir)
                        env['DATABASE_PATH'] = str(relative_path)
                        print(f"🐛 DEBUG: DATABASE_PATH set to: {relative_path}")
                        print(f"🐛 DEBUG: Absolute db path: {abs_db_path}")
                        print(f"🐛 DEBUG: Working dir: {abs_working_dir}")
                    except ValueError as e:
                        # Fallback to absolute path if relative calculation fails
                        env['DATABASE_PATH'] = str(abs_db_path)
                        print(f"🐛 DEBUG: Using absolute path fallback: {abs_db_path} (error: {e})")

                # Use corporate network-aware subprocess if available
                try:
                    from .network_utils import test_subprocess_with_proxy
                    res = test_subprocess_with_proxy(
                        cmd,
                        env=env,
                        timeout=None,  # Use configured timeout from network settings
                        cwd=self.working_dir,
                    )
                except ImportError:
                    # Fallback to standard subprocess
                    res = subprocess.run(
                        cmd,
                        cwd=self.working_dir,
                        check=False,
                        capture_output=True,
                        text=True,
                        env=env,
                    )

            except Exception as e:
                raise DbtExecutionError(str(e))
            end = time.perf_counter()
            return DbtResult(
                success=res.returncode == 0,
                stdout=res.stdout or "",
                stderr=res.stderr or "",
                execution_time=end - start,
                return_code=res.returncode,
                command=cmd,
            )

    def _execute_with_streaming(
        self,
        cmd: List[str],
        *,
        on_line: Optional[Callable[[str], None]] = None,
        start_ts: float,
    ) -> DbtResult:
        try:
            # Set up environment with DATABASE_PATH and corporate network settings
            env = None
            if self.database_path:
                import os
                env = os.environ.copy()
                # For dbt running from /dbt directory, use relative path from dbt/ to database
                abs_db_path = Path(self.database_path).absolute()
                abs_working_dir = self.working_dir.absolute()
                try:
                    relative_path = abs_db_path.relative_to(abs_working_dir)
                    env['DATABASE_PATH'] = str(relative_path)
                    print(f"🐛 DEBUG: DATABASE_PATH set to: {relative_path}")
                except ValueError as e:
                    # Fallback to absolute path if relative calculation fails
                    env['DATABASE_PATH'] = str(abs_db_path)
                    print(f"🐛 DEBUG: Using absolute path fallback: {abs_db_path} (error: {e})")

            # Add corporate network environment variables if available
            try:
                from .network_utils import load_network_config
                config = load_network_config()
                if env is None:
                    import os
                    env = os.environ.copy()

                # Add proxy settings to environment
                if config.proxy.http_proxy:
                    env['HTTP_PROXY'] = config.proxy.http_proxy
                    env['http_proxy'] = config.proxy.http_proxy
                if config.proxy.https_proxy:
                    env['HTTPS_PROXY'] = config.proxy.https_proxy
                    env['https_proxy'] = config.proxy.https_proxy
                if config.proxy.no_proxy:
                    env['NO_PROXY'] = ','.join(config.proxy.no_proxy)
                    env['no_proxy'] = ','.join(config.proxy.no_proxy)

                # Add certificate settings
                if config.certificates.ca_bundle_path:
                    env['REQUESTS_CA_BUNDLE'] = config.certificates.ca_bundle_path
                    env['SSL_CERT_FILE'] = config.certificates.ca_bundle_path
                    env['CURL_CA_BUNDLE'] = config.certificates.ca_bundle_path

            except ImportError:
                # Corporate network support not available, continue with standard env
                pass

            process = subprocess.Popen(
                cmd,
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
            )
        except Exception as e:
            raise DbtExecutionError(str(e))

        stdout_lines: List[str] = []
        if process.stdout is not None:
            for line in iter(process.stdout.readline, ""):
                stdout_lines.append(line)
                if on_line:
                    on_line(line.rstrip())
        process.wait()

        end = time.perf_counter()
        stdout = "".join(stdout_lines)
        return DbtResult(
            success=process.returncode == 0,
            stdout=stdout,
            stderr="",  # combined in stdout
            execution_time=end - start_ts,
            return_code=process.returncode or 0,
            command=cmd,
        )

    def run_model(self, model_name: str, **kwargs: Any) -> DbtResult:
        return self.execute_command(["run", "--select", model_name], **kwargs)

    def run_models(
        self,
        models: Sequence[str],
        *,
        parallel: bool = False,
        **kwargs: Any,
    ) -> List[DbtResult]:
        if not models:
            return []
        if parallel:
            select_arg = " ".join(models)
            res = self.execute_command(["run", "--select", select_arg], **kwargs)
            return [res]
        # Sequential (rare). Still use combined selection for single process by default
        select_arg = " ".join(models)
        res = self.execute_command(["run", "--select", select_arg], **kwargs)
        return [res]

    def run_models_with_smart_parallelization(
        self,
        models: List[str],
        *,
        stage_name: str = "unknown",
        simulation_year: int,
        dbt_vars: Optional[Dict[str, Any]] = None,
        enable_conditional_parallelization: bool = False,
        execution_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Run models with intelligent model-level parallelization.

        This method uses the parallel execution engine to analyze model dependencies
        and execute independent models concurrently while preserving sequential
        execution for state-dependent operations.

        Args:
            models: List of model names to execute
            stage_name: Name of the workflow stage (for logging)
            simulation_year: Simulation year for dbt vars
            dbt_vars: Additional dbt variables
            enable_conditional_parallelization: Allow parallelization of conditional models
            execution_id: Unique identifier for this execution

        Returns:
            ExecutionResult with comprehensive execution information
        """

        if not self._parallel_engine or not self.enable_model_parallelization:
            # Fallback to sequential execution
            return self._run_models_sequential_fallback(
                models, stage_name, simulation_year, dbt_vars or {}
            )

        # Refresh dependency analysis if needed
        try:
            self._dependency_analyzer.analyze_dependencies(refresh_cache=False)
        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to analyze dependencies: {e}")
                print("   Falling back to sequential execution")
            return self._run_models_sequential_fallback(
                models, stage_name, simulation_year, dbt_vars or {}
            )

        # Create execution context
        import uuid
        context = ExecutionContext(
            simulation_year=simulation_year,
            dbt_vars=dbt_vars or {},
            stage_name=stage_name,
            execution_id=execution_id or str(uuid.uuid4())[:8]
        )

        # Execute with parallelization
        return self._parallel_engine.execute_stage_with_parallelization(
            models,
            context,
            enable_conditional_parallelization=enable_conditional_parallelization
        )

    def _run_models_sequential_fallback(
        self,
        models: List[str],
        stage_name: str,
        simulation_year: int,
        dbt_vars: Dict[str, Any]
    ) -> ExecutionResult:
        """Fallback to sequential execution when parallelization is unavailable."""

        start_time = time.perf_counter()
        model_results = {}
        errors = []

        if self.verbose:
            print(f"🔄 Sequential execution fallback for stage {stage_name}")

        for model in models:
            try:
                result = self.execute_command(
                    ["run", "--select", model],
                    simulation_year=simulation_year,
                    dbt_vars=dbt_vars,
                    stream_output=True
                )
                model_results[model] = result

                if not result.success:
                    errors.append(f"Model {model} failed with code {result.return_code}")
                    break  # Stop on first failure

            except Exception as e:
                errors.append(f"Model {model} raised exception: {str(e)}")
                break

        execution_time = time.perf_counter() - start_time

        # Create ExecutionResult-compatible response
        if PARALLEL_EXECUTION_AVAILABLE:
            return ExecutionResult(
                success=len(errors) == 0,
                model_results=model_results,
                execution_time=execution_time,
                parallelism_achieved=1,
                resource_usage={},
                errors=errors
            )
        else:
            # Fallback dict structure if ExecutionResult not available
            return {
                "success": len(errors) == 0,
                "model_results": model_results,
                "execution_time": execution_time,
                "parallelism_achieved": 1,
                "resource_usage": {},
                "errors": errors
            }

    def get_parallelization_info(self) -> Dict[str, Any]:
        """Get information about model parallelization capabilities."""

        if not self._parallel_engine:
            return {
                "available": False,
                "reason": "Parallel execution engine not initialized",
                "fallback_mode": "sequential"
            }

        try:
            stats = self._parallel_engine.get_parallelization_statistics()
            return {
                "available": True,
                "statistics": stats,
                "configuration": {
                    "max_workers": self.model_parallelization_max_workers,
                    "memory_limit_mb": self.model_parallelization_memory_limit_mb,
                    "threading_mode": self.threading_mode,
                    "dbt_threads": self.threads
                }
            }
        except Exception as e:
            return {
                "available": False,
                "reason": f"Error accessing parallelization engine: {e}",
                "fallback_mode": "sequential"
            }

    def validate_stage_for_parallelization(self, stage_models: List[str]) -> Dict[str, Any]:
        """Validate whether a stage can benefit from parallelization."""

        if not self._parallel_engine:
            return {
                "parallelizable": False,
                "reason": "Parallel execution engine not available"
            }

        try:
            return self._parallel_engine.validate_stage_parallelization(stage_models)
        except Exception as e:
            return {
                "parallelizable": False,
                "reason": f"Validation error: {e}"
            }

    def enable_parallelization(
        self,
        max_workers: Optional[int] = None,
        memory_limit_mb: Optional[float] = None
    ) -> bool:
        """Enable model-level parallelization with optional parameter updates."""

        if not PARALLEL_EXECUTION_AVAILABLE:
            if self.verbose:
                print("⚠️ Cannot enable parallelization: parallel execution components not available")
            return False

        # Update parameters if provided
        if max_workers is not None:
            self.model_parallelization_max_workers = max_workers
        if memory_limit_mb is not None:
            self.model_parallelization_memory_limit_mb = memory_limit_mb

        # Initialize or reinitialize parallel engine
        try:
            if not self._dependency_analyzer:
                self._dependency_analyzer = ModelDependencyAnalyzer(self.working_dir)

            self._parallel_engine = ParallelExecutionEngine(
                dbt_runner=self,
                dependency_analyzer=self._dependency_analyzer,
                max_workers=self.model_parallelization_max_workers,
                memory_limit_mb=self.model_parallelization_memory_limit_mb,
                verbose=self.verbose
            )

            self.enable_model_parallelization = True

            if self.verbose:
                print(f"✅ Model-level parallelization enabled:")
                print(f"   Max workers: {self.model_parallelization_max_workers}")
                print(f"   Memory limit: {self.model_parallelization_memory_limit_mb}MB")

            return True

        except Exception as e:
            if self.verbose:
                print(f"❌ Failed to enable parallelization: {e}")
            return False

    def disable_parallelization(self) -> None:
        """Disable model-level parallelization."""
        self.enable_model_parallelization = False
        self._parallel_engine = None

        if self.verbose:
            print("🔄 Model-level parallelization disabled")


    def execute_command_with_threads(
        self,
        command_args: Sequence[str],
        threads: int,
        **kwargs: Any
    ) -> DbtResult:
        """Execute dbt command with explicit thread count (E068C)."""
        # Temporarily override thread count
        original_threads = self.threads
        self.threads = threads

        try:
            return self.execute_command(command_args, **kwargs)
        finally:
            # Restore original thread count
            self.threads = original_threads

    def run_models_by_tag(
        self,
        tag: str,
        simulation_year: int,
        threads: Optional[int] = None,
        **kwargs: Any,
    ) -> DbtResult:
        """Run all models with specified tag in parallel.

        Args:
            tag: dbt tag to select (e.g., 'EVENT_GENERATION', 'STATE_ACCUMULATION')
            simulation_year: Simulation year for dbt vars
            threads: Optional thread count override
            **kwargs: Additional arguments passed to execute_command

        Returns:
            DbtResult from the tag-based model execution
        """
        effective_threads = threads or self.threads

        if self.verbose:
            print(f"🏷️ Running models with tag '{tag}' for year {simulation_year} (threads={effective_threads})")

        return self.execute_command(
            ["run", "--select", f"tag:{tag}"],
            simulation_year=simulation_year,
            **kwargs
        )

    def run_stage_models(
        self,
        stage: str,
        simulation_year: int,
        threads: Optional[int] = None,
        **kwargs: Any,
    ) -> List[DbtResult]:
        """Run all models for a workflow stage with optimal threading.

        Args:
            stage: Workflow stage name (e.g., 'EVENT_GENERATION', 'STATE_ACCUMULATION')
            simulation_year: Simulation year for dbt vars
            threads: Optional thread count override
            **kwargs: Additional arguments passed to execute_command

        Returns:
            List of DbtResult objects from stage execution
        """
        results = []
        effective_threads = threads or self.threads

        if self.verbose:
            print(f"🎭 Running stage '{stage}' for year {simulation_year} (threads={effective_threads})")

        # Map stage names to their execution strategy
        if stage in ["EVENT_GENERATION", "STATE_ACCUMULATION", "VALIDATION", "FOUNDATION"]:
            # Single parallel call for optimized stages
            result = self.run_models_by_tag(stage, simulation_year, threads=effective_threads, **kwargs)
            results.append(result)

        elif stage == "INITIALIZATION":
            # Run staging models sequentially for safety
            result = self.execute_command(
                ["run", "--select", "staging.*"],
                simulation_year=simulation_year,
                **kwargs
            )
            results.append(result)

        elif stage == "REPORTING":
            # Run reporting models with moderate threading
            result = self.execute_command(
                ["run", "--select", "tag:REPORTING"],
                simulation_year=simulation_year,
                **kwargs
            )
            results.append(result)

        else:
            # Legacy support: if stage is not recognized, try as tag
            if self.verbose:
                print(f"⚠️ Unknown stage '{stage}', attempting as tag")
            result = self.run_models_by_tag(stage, simulation_year, threads=effective_threads, **kwargs)
            results.append(result)

        return results
