from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.check_fast_suite_runtime import main


def test_propagates_child_failure():
    with patch(
        "scripts.check_fast_suite_runtime.subprocess.run",
        return_value=MagicMock(returncode=3),
    ):
        assert main(["--max-seconds", "10"]) == 3


def test_returns_timeout_status_when_child_times_out():
    with patch(
        "scripts.check_fast_suite_runtime.subprocess.run",
        side_effect=__import__("subprocess").TimeoutExpired("pytest", 10),
    ):
        assert main(["--max-seconds", "10"]) == 124


def test_returns_success_under_budget():
    with patch(
        "scripts.check_fast_suite_runtime.subprocess.run",
        return_value=MagicMock(returncode=0),
    ):
        with patch(
            "scripts.check_fast_suite_runtime.time.monotonic", side_effect=[0.0, 0.2]
        ):
            assert main(["--max-seconds", "10"]) == 0
