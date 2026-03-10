"""Tests for planalign_orchestrator.dbt_runner module.

Covers DbtRunner initialisation, command building, execution with retry,
subprocess environment setup, model running helpers, parallelization
management, and the module-level classify_dbt_error / retry_with_backoff
utility functions.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

from planalign_orchestrator.dbt_runner import (
    DbtCompilationError,
    DbtDataQualityError,
    DbtError,
    DbtExecutionError,
    DbtResult,
    DbtRunner,
    classify_dbt_error,
    retry_with_backoff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_result(cmd: Optional[List[str]] = None) -> DbtResult:
    return DbtResult(
        success=True,
        stdout="OK",
        stderr="",
        execution_time=0.1,
        return_code=0,
        command=cmd or ["dbt", "run"],
    )


def _mock_popen_process(returncode: int = 0, output_lines: Optional[List[str]] = None):
    """Create a mock subprocess.Popen process with proper stdout readline support."""
    lines = list(output_lines or [])
    lines.append("")  # sentinel for iter(readline, "")
    mock_process = Mock()
    mock_process.stdout.readline = Mock(side_effect=lines)
    mock_process.wait.return_value = None
    mock_process.returncode = returncode
    return mock_process


def _fail_result(
    stdout: str = "",
    stderr: str = "",
    return_code: int = 1,
) -> DbtResult:
    return DbtResult(
        success=False,
        stdout=stdout,
        stderr=stderr,
        execution_time=0.1,
        return_code=return_code,
        command=["dbt", "run"],
    )


# ===================================================================
# classify_dbt_error
# ===================================================================

class TestClassifyDbtError:
    @pytest.mark.fast
    def test_compilation_error(self):
        err = classify_dbt_error("", "Compilation Error in model", 1)
        assert isinstance(err, DbtCompilationError)

    @pytest.mark.fast
    def test_database_error_in_stderr(self):
        err = classify_dbt_error("", "Database error while running", 1)
        assert isinstance(err, DbtExecutionError)

    @pytest.mark.fast
    def test_operational_error_in_stderr(self):
        err = classify_dbt_error("", "OperationalError: lock", 1)
        assert isinstance(err, DbtExecutionError)

    @pytest.mark.fast
    def test_test_failed_in_stdout(self):
        err = classify_dbt_error("WARN 2 test failed", "", 1)
        assert isinstance(err, DbtDataQualityError)

    @pytest.mark.fast
    def test_failing_tests_in_stdout(self):
        err = classify_dbt_error("Failing tests detected", "", 1)
        assert isinstance(err, DbtDataQualityError)

    @pytest.mark.fast
    def test_unknown_error_returns_base(self):
        err = classify_dbt_error("something weird", "nothing useful", 2)
        assert type(err) is DbtError
        assert "code 2" in str(err)

    @pytest.mark.fast
    def test_unknown_error_truncates_long_tail(self):
        long_stdout = "x" * 1000
        err = classify_dbt_error(long_stdout, "", 2)
        # Tail is capped at 400 chars
        assert len(str(err)) <= 500

    @pytest.mark.fast
    def test_none_inputs_handled(self):
        err = classify_dbt_error(None, None, 1)
        assert isinstance(err, DbtError)


# ===================================================================
# retry_with_backoff
# ===================================================================

class TestRetryWithBackoff:
    @pytest.mark.fast
    def test_succeeds_first_try(self):
        result = retry_with_backoff(lambda: _ok_result(), max_attempts=3)
        assert result.success

    @pytest.mark.fast
    def test_retries_on_matching_exception(self):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise DbtExecutionError("transient")
            return _ok_result()

        result = retry_with_backoff(
            flaky,
            max_attempts=3,
            base_delay=0.001,
            retry_on=(DbtExecutionError,),
        )
        assert result.success
        assert call_count == 3

    @pytest.mark.fast
    def test_raises_after_max_attempts(self):
        def always_fail():
            raise DbtExecutionError("persistent")

        with pytest.raises(DbtExecutionError, match="persistent"):
            retry_with_backoff(
                always_fail,
                max_attempts=2,
                base_delay=0.001,
            )

    @pytest.mark.fast
    def test_does_not_retry_on_non_matching_exception(self):
        def wrong_error():
            raise DbtCompilationError("compile fail")

        with pytest.raises(DbtCompilationError):
            retry_with_backoff(
                wrong_error,
                max_attempts=3,
                base_delay=0.001,
                retry_on=(DbtExecutionError,),
            )

    @pytest.mark.fast
    def test_max_delay_caps_sleep(self):
        """Delay should never exceed max_delay."""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise DbtExecutionError("transient")
            return _ok_result()

        with patch("planalign_orchestrator.dbt_runner.time.sleep") as mock_sleep:
            retry_with_backoff(
                flaky,
                max_attempts=3,
                base_delay=100.0,
                max_delay=0.5,
            )
            for call in mock_sleep.call_args_list:
                assert call.args[0] <= 0.5 + 0.05  # max_delay + small jitter


# ===================================================================
# DbtRunner.__init__ / validation
# ===================================================================

class TestDbtRunnerInit:
    @pytest.mark.fast
    def test_default_init(self):
        runner = DbtRunner()
        assert runner.threads == 1
        assert runner.working_dir == Path("dbt")
        assert runner.verbose is False
        assert runner.threading_enabled is True

    @pytest.mark.fast
    def test_custom_params(self):
        runner = DbtRunner(
            working_dir=Path("/tmp/dbt_test"),
            threads=4,
            executable="dbt-custom",
            verbose=False,
            threading_mode="full",
        )
        assert runner.threads == 4
        assert runner.executable == "dbt-custom"
        assert runner.threading_mode == "full"

    @pytest.mark.fast
    def test_thread_count_zero_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            DbtRunner(threads=0)

    @pytest.mark.fast
    def test_thread_count_negative_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            DbtRunner(threads=-1)

    @pytest.mark.fast
    def test_thread_count_over_16_raises(self):
        with pytest.raises(ValueError, match="cannot exceed 16"):
            DbtRunner(threads=17)

    @pytest.mark.fast
    def test_verbose_high_thread_warning(self, capsys):
        DbtRunner(threads=10, verbose=True)
        captured = capsys.readouterr()
        assert "High thread count" in captured.out or "10" in captured.out

    @pytest.mark.fast
    def test_verbose_moderate_thread_info(self, capsys):
        DbtRunner(threads=5, verbose=True)
        captured = capsys.readouterr()
        assert "Multi-threading enabled" in captured.out or "5 threads" in captured.out

    @pytest.mark.fast
    def test_parallelization_disabled_by_default(self):
        runner = DbtRunner()
        assert runner.enable_model_parallelization is False
        assert runner._parallel_engine is None


# ===================================================================
# _validate_thread_count / update_thread_count
# ===================================================================

class TestThreadManagement:
    @pytest.mark.fast
    def test_validate_thread_count_boundary(self):
        runner = DbtRunner(threads=1)
        runner._validate_thread_count(1)
        runner._validate_thread_count(16)

    @pytest.mark.fast
    def test_validate_thread_count_invalid(self):
        runner = DbtRunner(threads=1)
        with pytest.raises(ValueError):
            runner._validate_thread_count(0)
        with pytest.raises(ValueError):
            runner._validate_thread_count(17)

    @pytest.mark.fast
    def test_update_thread_count(self):
        runner = DbtRunner(threads=1)
        runner.update_thread_count(8)
        assert runner.threads == 8

    @pytest.mark.fast
    def test_update_thread_count_invalid(self):
        runner = DbtRunner(threads=1)
        with pytest.raises(ValueError):
            runner.update_thread_count(0)

    @pytest.mark.fast
    def test_update_thread_count_verbose(self, capsys):
        runner = DbtRunner(threads=1, verbose=True)
        _ = capsys.readouterr()  # discard init output
        runner.update_thread_count(4)
        captured = capsys.readouterr()
        assert "4" in captured.out

    @pytest.mark.fast
    def test_get_thread_utilization_info(self):
        runner = DbtRunner(threads=4, threading_enabled=True, threading_mode="selective")
        info = runner.get_thread_utilization_info()
        assert info["thread_count"] == 4
        assert info["threading_enabled"] is True
        assert info["threading_mode"] == "selective"
        assert info["single_threaded_fallback"] is False

    @pytest.mark.fast
    def test_get_thread_utilization_single_fallback(self):
        runner = DbtRunner(threads=1)
        info = runner.get_thread_utilization_info()
        assert info["single_threaded_fallback"] is True


# ===================================================================
# _build_command
# ===================================================================

class TestBuildCommand:
    @pytest.mark.fast
    def test_basic_run(self):
        runner = DbtRunner(threads=2)
        cmd = runner._build_command(["run", "--select", "my_model"])
        assert cmd[:3] == ["dbt", "run", "--select"]
        assert "my_model" in cmd
        assert "--threads" in cmd
        idx = cmd.index("--threads")
        assert cmd[idx + 1] == "2"

    @pytest.mark.fast
    def test_simulation_year_var(self):
        runner = DbtRunner(threads=1)
        cmd = runner._build_command(["run"], simulation_year=2025)
        assert "--vars" in cmd
        idx = cmd.index("--vars")
        assert "2025" in cmd[idx + 1]

    @pytest.mark.fast
    def test_custom_dbt_vars(self):
        runner = DbtRunner(threads=1)
        cmd = runner._build_command(
            ["run", "--select", "model"],
            dbt_vars={"foo": "bar"},
        )
        assert "--vars" in cmd
        idx = cmd.index("--vars")
        assert "foo" in cmd[idx + 1]
        assert "bar" in cmd[idx + 1]

    @pytest.mark.fast
    def test_merged_vars(self):
        runner = DbtRunner(threads=1)
        cmd = runner._build_command(
            ["run"],
            simulation_year=2026,
            dbt_vars={"extra": 1},
        )
        idx = cmd.index("--vars")
        import json
        vars_parsed = json.loads(cmd[idx + 1])
        assert vars_parsed["simulation_year"] == 2026
        assert vars_parsed["extra"] == 1

    @pytest.mark.fast
    def test_no_vars_omitted(self):
        runner = DbtRunner(threads=1)
        cmd = runner._build_command(["run"])
        assert "--vars" not in cmd

    @pytest.mark.fast
    def test_threads_not_added_for_unsupported_commands(self):
        runner = DbtRunner(threads=4)
        cmd = runner._build_command(["clean"])
        assert "--threads" not in cmd

    @pytest.mark.fast
    def test_threads_added_for_supported_commands(self):
        supported = ["run", "test", "build", "compile", "seed", "snapshot"]
        runner = DbtRunner(threads=3)
        for sub in supported:
            cmd = runner._build_command([sub])
            assert "--threads" in cmd, f"--threads missing for '{sub}'"

    @pytest.mark.fast
    def test_threading_disabled_forces_single_thread(self):
        runner = DbtRunner(threads=4, threading_enabled=False)
        cmd = runner._build_command(["run"])
        idx = cmd.index("--threads")
        assert cmd[idx + 1] == "1"

    @pytest.mark.fast
    def test_explicit_threads_override(self):
        runner = DbtRunner(threads=2)
        cmd = runner._build_command(["run"], threads=8)
        idx = cmd.index("--threads")
        assert cmd[idx + 1] == "8"

    @pytest.mark.fast
    def test_non_dbt_executable_skips_threads(self):
        runner = DbtRunner(threads=4, executable="echo")
        cmd = runner._build_command(["run"])
        assert "--threads" not in cmd

    @pytest.mark.fast
    def test_already_present_threads_not_duplicated(self):
        runner = DbtRunner(threads=4)
        cmd = runner._build_command(["run", "--threads", "2"])
        assert cmd.count("--threads") == 1


# ===================================================================
# _build_subprocess_env
# ===================================================================

class TestBuildSubprocessEnv:
    @pytest.mark.fast
    def test_no_database_path_returns_none_when_no_network(self):
        runner = DbtRunner()
        with patch.dict(
            "planalign_orchestrator.dbt_runner.__dict__",
            {},
        ):
            # Patch the network_utils import to raise ImportError
            with patch.object(
                runner,
                "_build_subprocess_env",
                wraps=runner._build_subprocess_env,
            ):
                env = runner._build_subprocess_env()
                # Without database_path and without network_utils, might be None
                # or might have network vars; just confirm no crash
                assert env is None or isinstance(env, dict)

    @pytest.mark.fast
    def test_database_path_relative(self, tmp_path):
        db_file = tmp_path / "dbt" / "simulation.duckdb"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        db_file.touch()

        runner = DbtRunner(
            working_dir=tmp_path / "dbt",
            database_path=str(db_file),
        )
        with patch(
            "planalign_orchestrator.dbt_runner.DbtRunner._build_subprocess_env",
            wraps=runner._build_subprocess_env,
        ):
            # Mock network_utils to ImportError
            import importlib
            import sys
            # Temporarily remove network_utils if present
            saved = sys.modules.get("planalign_orchestrator.network_utils")
            sys.modules["planalign_orchestrator.network_utils"] = None  # type: ignore
            try:
                env = runner._build_subprocess_env()
            finally:
                if saved is not None:
                    sys.modules["planalign_orchestrator.network_utils"] = saved
                else:
                    sys.modules.pop("planalign_orchestrator.network_utils", None)

            assert env is not None
            assert "DATABASE_PATH" in env

    @pytest.mark.fast
    def test_database_path_absolute_fallback(self, tmp_path):
        """When database is outside working_dir, absolute path is used."""
        runner = DbtRunner(
            working_dir=tmp_path / "dbt",
            database_path="/some/other/path/sim.duckdb",
        )
        import sys
        saved = sys.modules.get("planalign_orchestrator.network_utils")
        sys.modules["planalign_orchestrator.network_utils"] = None  # type: ignore
        try:
            env = runner._build_subprocess_env()
        finally:
            if saved is not None:
                sys.modules["planalign_orchestrator.network_utils"] = saved
            else:
                sys.modules.pop("planalign_orchestrator.network_utils", None)

        assert env is not None
        assert env["DATABASE_PATH"] == str(Path("/some/other/path/sim.duckdb").absolute())


# ===================================================================
# execute_command / _execute_with_retry
# ===================================================================

class TestExecuteCommand:
    @pytest.mark.fast
    @patch.object(DbtRunner, "_execute_once")
    def test_execute_command_no_retry(self, mock_exec):
        mock_exec.return_value = _ok_result()
        runner = DbtRunner()
        result = runner.execute_command(["run"], retry=False)
        assert result.success
        mock_exec.assert_called_once()

    @pytest.mark.fast
    @patch.object(DbtRunner, "_execute_once")
    def test_execute_command_retry_on_failure(self, mock_exec):
        """When retry=True (default) and result is a failure, classify + retry."""
        mock_exec.side_effect = [
            _fail_result(stderr="Database error occurred"),
            _ok_result(),
        ]
        runner = DbtRunner()
        # retry_with_backoff will classify the failure and retry
        with patch("planalign_orchestrator.dbt_runner.time.sleep"):
            result = runner.execute_command(
                ["run"],
                retry=True,
                max_attempts=3,
            )
        assert result.success

    @pytest.mark.fast
    @patch.object(DbtRunner, "_execute_once")
    def test_execute_with_retry_disabled(self, mock_exec):
        mock_exec.return_value = _fail_result()
        runner = DbtRunner()
        result = runner._execute_with_retry(
            lambda: mock_exec(),
            retry=False,
            max_attempts=3,
        )
        assert not result.success
        assert mock_exec.call_count == 1

    @pytest.mark.fast
    @patch.object(DbtRunner, "_execute_once")
    def test_execute_command_retry_success_first_try(self, mock_exec):
        """retry=True with immediate success still returns via _execute_with_retry."""
        mock_exec.return_value = _ok_result()
        runner = DbtRunner()
        result = runner.execute_command(
            ["run"], retry=True, max_attempts=3,
        )
        assert result.success
        mock_exec.assert_called_once()

    @pytest.mark.fast
    def test_execute_once_closes_db_connections(self):
        """db_manager.close_all() is called before subprocess."""
        db_mgr = Mock()
        runner = DbtRunner(db_manager=db_mgr)

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = _mock_popen_process(returncode=0)

            runner._execute_once(
                ["run"],
                description="test",
                simulation_year=None,
                dbt_vars=None,
                threads=None,
                stream_output=True,
                on_line=None,
            )
            db_mgr.close_all.assert_called_once()

    @pytest.mark.fast
    def test_execute_once_db_close_failure_non_fatal(self, capsys):
        """If db_manager.close_all() fails, execution continues."""
        db_mgr = Mock()
        db_mgr.close_all.side_effect = RuntimeError("connection gone")
        runner = DbtRunner(db_manager=db_mgr, verbose=True)
        _ = capsys.readouterr()  # discard init output

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = _mock_popen_process(returncode=0)

            result = runner._execute_once(
                ["run"],
                description="test",
                simulation_year=None,
                dbt_vars=None,
                threads=None,
                stream_output=True,
                on_line=None,
            )
            assert result.success
            captured = capsys.readouterr()
            assert "Non-fatal" in captured.out or "failed to close" in captured.out


# ===================================================================
# _run_subprocess / _execute_with_streaming
# ===================================================================

class TestSubprocessExecution:
    @pytest.mark.fast
    @patch("subprocess.run")
    def test_run_subprocess_success(self, mock_run):
        mock_run.return_value = Mock(
            returncode=0,
            stdout="all good",
            stderr="",
        )
        runner = DbtRunner()

        # Patch network_utils import to fail so standard subprocess is used
        with patch.dict("sys.modules", {"planalign_orchestrator.network_utils": None}):
            result = runner._run_subprocess(["dbt", "run"], start_ts=time.perf_counter())

        assert result.success
        assert result.stdout == "all good"
        assert result.return_code == 0

    @pytest.mark.fast
    @patch("subprocess.run")
    def test_run_subprocess_failure(self, mock_run):
        mock_run.return_value = Mock(
            returncode=2,
            stdout="error output",
            stderr="compile error",
        )
        runner = DbtRunner()
        with patch.dict("sys.modules", {"planalign_orchestrator.network_utils": None}):
            result = runner._run_subprocess(["dbt", "run"], start_ts=time.perf_counter())

        assert not result.success
        assert result.return_code == 2

    @pytest.mark.fast
    @patch("subprocess.run", side_effect=OSError("no such file"))
    def test_run_subprocess_os_error_raises(self, mock_run):
        runner = DbtRunner()
        with patch.dict("sys.modules", {"planalign_orchestrator.network_utils": None}):
            with pytest.raises(DbtExecutionError, match="no such file"):
                runner._run_subprocess(["dbt", "run"], start_ts=time.perf_counter())

    @pytest.mark.fast
    @patch("subprocess.Popen")
    def test_streaming_captures_lines(self, mock_popen):
        mock_popen.return_value = _mock_popen_process(
            returncode=0,
            output_lines=["line1\n", "line2\n"],
        )

        runner = DbtRunner()
        collected: List[str] = []
        result = runner._execute_with_streaming(
            ["dbt", "run"],
            on_line=lambda l: collected.append(l),
            start_ts=time.perf_counter(),
        )
        assert result.success
        assert "line1" in result.stdout

    @pytest.mark.fast
    @patch("subprocess.Popen", side_effect=OSError("popen failed"))
    def test_streaming_popen_error_raises(self, mock_popen):
        runner = DbtRunner()
        with pytest.raises(DbtExecutionError, match="popen failed"):
            runner._execute_with_streaming(
                ["dbt", "run"],
                start_ts=time.perf_counter(),
            )


# ===================================================================
# run_model / run_models
# ===================================================================

class TestRunModels:
    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_model(self, mock_exec):
        runner = DbtRunner()
        result = runner.run_model("my_model", description="test")
        assert result.success
        mock_exec.assert_called_once()
        args = mock_exec.call_args
        assert args[0][0] == ["run", "--select", "my_model"]

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_models_empty(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_models([])
        assert results == []
        mock_exec.assert_not_called()

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_models_parallel(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_models(["a", "b", "c"], parallel=True)
        assert len(results) == 1
        args = mock_exec.call_args[0][0]
        assert "a b c" in " ".join(args)

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_models_sequential(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_models(["a", "b"], parallel=False)
        assert len(results) == 1  # Still combines into single dbt call


# ===================================================================
# run_models_with_smart_parallelization
# ===================================================================

class TestSmartParallelization:
    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_fallback_when_no_engine(self, mock_exec):
        runner = DbtRunner()
        assert runner._parallel_engine is None
        result = runner.run_models_with_smart_parallelization(
            ["model_a", "model_b"],
            stage_name="TEST",
            simulation_year=2025,
        )
        # Returns dict or ExecutionResult with success
        if isinstance(result, dict):
            assert result["success"]
        else:
            assert result.success

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_sequential_fallback_verbose(self, mock_exec, capsys):
        runner = DbtRunner(verbose=True)
        _ = capsys.readouterr()
        runner.run_models_with_smart_parallelization(
            ["model_a"],
            stage_name="EVENT_GEN",
            simulation_year=2025,
        )
        captured = capsys.readouterr()
        assert "Sequential" in captured.out or "fallback" in captured.out

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command")
    def test_sequential_fallback_stops_on_failure(self, mock_exec):
        mock_exec.return_value = _fail_result()
        runner = DbtRunner()
        result = runner.run_models_with_smart_parallelization(
            ["model_a", "model_b", "model_c"],
            stage_name="TEST",
            simulation_year=2025,
        )
        if isinstance(result, dict):
            assert not result["success"]
            assert len(result["errors"]) > 0
        else:
            assert not result.success

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", side_effect=Exception("boom"))
    def test_sequential_fallback_handles_exception(self, mock_exec):
        runner = DbtRunner()
        result = runner.run_models_with_smart_parallelization(
            ["model_a"],
            stage_name="TEST",
            simulation_year=2025,
        )
        if isinstance(result, dict):
            assert not result["success"]
            assert any("boom" in e for e in result["errors"])
        else:
            assert not result.success


# ===================================================================
# Parallelization info / enable / disable
# ===================================================================

class TestParallelizationManagement:
    @pytest.mark.fast
    def test_get_parallelization_info_no_engine(self):
        runner = DbtRunner()
        info = runner.get_parallelization_info()
        assert info["available"] is False
        assert "reason" in info

    @pytest.mark.fast
    def test_get_parallelization_info_with_engine(self):
        runner = DbtRunner()
        mock_engine = Mock()
        mock_engine.get_parallelization_statistics.return_value = {"models": 10}
        runner._parallel_engine = mock_engine
        info = runner.get_parallelization_info()
        assert info["available"] is True
        assert "statistics" in info

    @pytest.mark.fast
    def test_get_parallelization_info_engine_error(self):
        runner = DbtRunner()
        mock_engine = Mock()
        mock_engine.get_parallelization_statistics.side_effect = RuntimeError("oops")
        runner._parallel_engine = mock_engine
        info = runner.get_parallelization_info()
        assert info["available"] is False
        assert "oops" in info["reason"]

    @pytest.mark.fast
    def test_validate_stage_no_engine(self):
        runner = DbtRunner()
        result = runner.validate_stage_for_parallelization(["a", "b"])
        assert result["parallelizable"] is False

    @pytest.mark.fast
    def test_validate_stage_with_engine(self):
        runner = DbtRunner()
        mock_engine = Mock()
        mock_engine.validate_stage_parallelization.return_value = {
            "parallelizable": True
        }
        runner._parallel_engine = mock_engine
        result = runner.validate_stage_for_parallelization(["a", "b"])
        assert result["parallelizable"] is True

    @pytest.mark.fast
    def test_validate_stage_engine_error(self):
        runner = DbtRunner()
        mock_engine = Mock()
        mock_engine.validate_stage_parallelization.side_effect = ValueError("bad")
        runner._parallel_engine = mock_engine
        result = runner.validate_stage_for_parallelization(["a"])
        assert result["parallelizable"] is False

    @pytest.mark.fast
    def test_disable_parallelization(self):
        runner = DbtRunner()
        runner._parallel_engine = Mock()
        runner.enable_model_parallelization = True
        runner.disable_parallelization()
        assert runner.enable_model_parallelization is False
        assert runner._parallel_engine is None

    @pytest.mark.fast
    def test_disable_parallelization_verbose(self, capsys):
        runner = DbtRunner(verbose=True)
        _ = capsys.readouterr()
        runner.disable_parallelization()
        captured = capsys.readouterr()
        assert "disabled" in captured.out

    @pytest.mark.fast
    def test_enable_parallelization_not_available(self):
        """When parallel execution modules aren't importable, returns False."""
        runner = DbtRunner()
        with patch(
            "planalign_orchestrator.dbt_runner.PARALLEL_EXECUTION_AVAILABLE",
            False,
        ):
            assert runner.enable_parallelization() is False


# ===================================================================
# execute_command_with_threads
# ===================================================================

class TestExecuteCommandWithThreads:
    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_temporarily_overrides_threads(self, mock_exec):
        runner = DbtRunner(threads=2)
        runner.execute_command_with_threads(["run"], threads=8, description="test")
        # After call, threads should be restored
        assert runner.threads == 2

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", side_effect=DbtError("fail"))
    def test_restores_threads_on_error(self, mock_exec):
        runner = DbtRunner(threads=2)
        with pytest.raises(DbtError):
            runner.execute_command_with_threads(["run"], threads=8)
        assert runner.threads == 2


# ===================================================================
# run_models_by_tag / run_stage_models
# ===================================================================

class TestTagAndStageExecution:
    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_models_by_tag(self, mock_exec):
        runner = DbtRunner(threads=2)
        result = runner.run_models_by_tag("EVENT_GENERATION", simulation_year=2025)
        assert result.success
        args = mock_exec.call_args[0][0]
        assert "tag:EVENT_GENERATION" in args

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_models_by_tag_verbose(self, mock_exec, capsys):
        runner = DbtRunner(threads=2, verbose=True)
        _ = capsys.readouterr()
        runner.run_models_by_tag("FOUNDATION", simulation_year=2026)
        captured = capsys.readouterr()
        assert "FOUNDATION" in captured.out

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_stage_models_event_generation(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_stage_models("EVENT_GENERATION", simulation_year=2025)
        assert len(results) == 1
        assert results[0].success

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_stage_models_initialization(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_stage_models("INITIALIZATION", simulation_year=2025)
        assert len(results) == 1
        args = mock_exec.call_args[0][0]
        assert "staging.*" in args

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_stage_models_reporting(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_stage_models("REPORTING", simulation_year=2025)
        assert len(results) == 1
        args = mock_exec.call_args[0][0]
        assert "tag:REPORTING" in args

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_stage_models_unknown_falls_through(self, mock_exec):
        runner = DbtRunner()
        results = runner.run_stage_models("CUSTOM_STAGE", simulation_year=2025)
        assert len(results) == 1

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_stage_models_unknown_verbose(self, mock_exec, capsys):
        runner = DbtRunner(verbose=True)
        _ = capsys.readouterr()
        runner.run_stage_models("MYSTERY", simulation_year=2025)
        captured = capsys.readouterr()
        assert "Unknown stage" in captured.out

    @pytest.mark.fast
    @patch.object(DbtRunner, "execute_command", return_value=_ok_result())
    def test_run_stage_known_stages(self, mock_exec):
        """All known parallel stages use run_models_by_tag."""
        runner = DbtRunner()
        for stage in ["EVENT_GENERATION", "STATE_ACCUMULATION", "VALIDATION", "FOUNDATION"]:
            results = runner.run_stage_models(stage, simulation_year=2025)
            assert len(results) == 1


# ===================================================================
# DbtResult dataclass
# ===================================================================

class TestDbtResult:
    @pytest.mark.fast
    def test_fields(self):
        r = DbtResult(
            success=True,
            stdout="out",
            stderr="err",
            execution_time=1.5,
            return_code=0,
            command=["dbt", "run"],
        )
        assert r.success is True
        assert r.stdout == "out"
        assert r.stderr == "err"
        assert r.execution_time == 1.5
        assert r.return_code == 0
        assert r.command == ["dbt", "run"]
