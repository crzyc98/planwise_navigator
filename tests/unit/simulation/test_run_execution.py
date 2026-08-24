"""Regression tests for simulation subprocess lifecycle cleanup."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planalign_api.services.simulation.run_execution import (
    ActiveProcessRegistry,
    execute_run,
)


class _Process:
    def __init__(self, *, block_until_killed: bool = False) -> None:
        self.actions: list[str] = []
        self.returncode: int | None = None
        self._block_until_killed = block_until_killed
        self._killed = asyncio.Event()

    def terminate(self) -> None:
        self.actions.append("terminate")

    def kill(self) -> None:
        self.actions.append("kill")
        self._killed.set()

    async def wait(self) -> int:
        self.actions.append("wait")
        if self._block_until_killed:
            await self._killed.wait()
        self.returncode = -15 if "kill" not in self.actions else -9
        return self.returncode


def _execute_with_stream_failure(
    process: _Process,
    registry: ActiveProcessRegistry,
    stream_error: Exception,
) -> None:
    async def run() -> None:
        with (
            patch(
                "planalign_api.services.simulation.run_execution.prepare_dbt_project",
                return_value=Path("/tmp/dbt-project"),
            ),
            patch(
                "planalign_api.services.simulation.run_execution.build_command",
                return_value=["simulate"],
            ),
            patch(
                "planalign_api.services.simulation.run_execution.create_subprocess",
                new=AsyncMock(return_value=(process, object())),
            ),
            patch(
                "planalign_api.services.simulation.run_execution.wait_for_ws_listener",
                new=AsyncMock(),
            ),
            patch(
                "planalign_api.services.simulation.run_execution.get_telemetry_service",
                return_value=MagicMock(),
            ),
            patch(
                "planalign_api.services.simulation.run_execution.stream_output",
                new=AsyncMock(side_effect=stream_error),
            ),
        ):
            await execute_run(
                run_dir=Path("/tmp/run"),
                start_year=2025,
                end_year=2027,
                total_years=3,
                run_id="run-576",
                update_run_status=MagicMock(),
                process_registry=registry,
            )

    asyncio.run(run())


@pytest.mark.fast
def test_stream_failure_terminates_reaps_and_unregisters_process() -> None:
    registry = ActiveProcessRegistry()
    process = _Process()

    with pytest.raises(RuntimeError, match="stream failed"):
        _execute_with_stream_failure(process, registry, RuntimeError("stream failed"))

    assert process.actions == ["terminate", "wait"]
    assert registry.processes == {}


@pytest.mark.fast
def test_stream_failure_kills_after_terminate_timeout_and_preserves_error() -> None:
    registry = ActiveProcessRegistry()
    process = _Process(block_until_killed=True)

    with patch(
        "planalign_api.services.simulation.run_execution.CANCEL_GRACE_SECONDS", 0.01
    ):
        with pytest.raises(ValueError, match="parser failed"):
            _execute_with_stream_failure(process, registry, ValueError("parser failed"))

    assert process.actions == ["terminate", "wait", "kill", "wait"]
    assert registry.processes == {}


@pytest.mark.fast
def test_cleanup_failure_is_logged_without_masking_stream_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class TerminateFailure(_Process):
        def terminate(self) -> None:
            raise OSError("terminate failed")

    registry = ActiveProcessRegistry()
    process = TerminateFailure()

    with pytest.raises(RuntimeError, match="stream failed"):
        _execute_with_stream_failure(process, registry, RuntimeError("stream failed"))

    assert "Cleanup after failed simulation run-576 was incomplete" in caplog.text
    assert registry.processes == {}
