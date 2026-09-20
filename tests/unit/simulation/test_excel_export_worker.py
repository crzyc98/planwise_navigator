"""Tests for process-isolated Excel export execution."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from planalign_api.services.simulation.excel_export_worker import (
    export_run_excel_in_process,
    shutdown_excel_export_executor,
)


@pytest.mark.fast
def test_export_uses_dedicated_process_executor(tmp_path):
    executor = MagicMock()
    loop = MagicMock()
    loop.run_in_executor.return_value = asyncio.sleep(
        0, result=tmp_path / "results.xlsx"
    )

    with patch(
        "planalign_api.services.simulation.excel_export_worker._get_executor",
        return_value=executor,
    ), patch(
        "planalign_api.services.simulation.excel_export_worker.asyncio.get_running_loop",
        return_value=loop,
    ):
        result = asyncio.run(
            export_run_excel_in_process(
                scenario_path=tmp_path,
                scenario_name="Baseline",
                config={"simulation": {"random_seed": 42}},
                seed=42,
                run_dir=tmp_path / "runs" / "run-1",
            )
        )

    assert result == tmp_path / "results.xlsx"
    submitted_executor, submitted_export = loop.run_in_executor.call_args.args
    assert submitted_executor is executor
    assert submitted_export.func.__name__ == "export_run_excel"
    assert submitted_export.keywords["run_dir"] == tmp_path / "runs" / "run-1"


def test_shutdown_is_safe_before_executor_creation():
    shutdown_excel_export_executor()
