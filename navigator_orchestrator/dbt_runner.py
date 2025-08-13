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
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple, Callable


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
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            jitter = random.uniform(0, 0.1) * delay
            time.sleep(delay + jitter)
            attempt += 1


class DbtRunner:
    def __init__(self, working_dir: Path = Path("dbt"), threads: int = 4, executable: str = "dbt", *, verbose: bool = False):
        self.working_dir = working_dir
        self.threads = threads
        self.executable = executable
        self.verbose = verbose

    def _build_command(
        self,
        command_args: Sequence[str],
        *,
        simulation_year: Optional[int] = None,
        dbt_vars: Optional[Dict[str, Any]] = None,
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
                    year_label = f" year={simulation_year}" if simulation_year is not None else ""
                    print(f"🧩 DbtRunner --vars{year_label}: {vars_json}")
                except Exception:
                    pass
            cmd.extend(["--vars", vars_json])
        # Attach threads if supported and not already present
        if "--threads" not in cmd and self.executable == "dbt":
            # Only add threads to commands that support it
            threads_supported_commands = [
                'run', 'test', 'build', 'compile', 'seed', 'snapshot',
                'docs', 'source', 'freshness', 'run-operation'
            ]
            if any(c in command_args for c in threads_supported_commands):
                cmd.extend(["--threads", str(self.threads)])
        return cmd

    def execute_command(
        self,
        command_args: Sequence[str],
        *,
        description: str = "Running dbt command",
        simulation_year: Optional[int] = None,
        dbt_vars: Optional[Dict[str, Any]] = None,
        stream_output: bool = True,
        on_line: Optional[Callable[[str], None]] = None,
        retry: bool = True,
        max_attempts: int = 3,
    ) -> DbtResult:
        """Execute a dbt command with enhanced error handling and optional retry."""

        def _run_once() -> DbtResult:
            return self._execute_once(
                command_args,
                description=description,
                simulation_year=simulation_year,
                dbt_vars=dbt_vars,
                stream_output=stream_output,
                on_line=on_line,
            )

        if not retry:
            return _run_once()

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

        return retry_with_backoff(_wrapped, max_attempts=max_attempts)

    def _execute_once(
        self,
        command_args: Sequence[str],
        *,
        description: str,
        simulation_year: Optional[int],
        dbt_vars: Optional[Dict[str, Any]],
        stream_output: bool,
        on_line: Optional[Callable[[str], None]],
    ) -> DbtResult:
        cmd = self._build_command(
            command_args,
            simulation_year=simulation_year,
            dbt_vars=dbt_vars,
        )

        start = time.perf_counter()

        if stream_output:
            return self._execute_with_streaming(cmd, on_line=on_line, start_ts=start)
        else:
            try:
                res = subprocess.run(
                    cmd,
                    cwd=self.working_dir,
                    check=False,
                    capture_output=True,
                    text=True,
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
            process = subprocess.Popen(
                cmd,
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
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
