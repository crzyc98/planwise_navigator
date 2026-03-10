"""Tests for the _check_system_health helper in simulate.py."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from click.exceptions import Exit as ClickExit

from planalign_cli.commands.simulate import _check_system_health


@pytest.mark.fast
class TestCheckSystemHealth:
    """Tests for _check_system_health extracted helper."""

    def _make_wrapper(self, healthy: bool, issues: list[str] | None = None) -> MagicMock:
        """Create a mock OrchestratorWrapper with a preset health response."""
        wrapper = MagicMock()
        wrapper.check_system_health.return_value = {
            "healthy": healthy,
            "issues": issues or [],
        }
        return wrapper

    def test_healthy_system_does_not_raise(self):
        """When the system is healthy, no exception is raised."""
        wrapper = self._make_wrapper(healthy=True)

        # Should complete without raising
        _check_system_health(wrapper)

        wrapper.check_system_health.assert_called_once()

    @patch("planalign_cli.commands.simulate.console")
    @patch("planalign_cli.commands.simulate.show_error_message")
    def test_unhealthy_system_raises_exit(self, mock_show_error, mock_console):
        """When the system is unhealthy, typer.Exit(1) is raised."""
        wrapper = self._make_wrapper(
            healthy=False, issues=["Database is locked"]
        )

        with pytest.raises(ClickExit) as exc_info:
            _check_system_health(wrapper)

        assert exc_info.value.exit_code == 1
        mock_show_error.assert_called_once_with("System health check failed")
        mock_console.print.assert_called_once()
        # Verify the issue text was printed
        call_args = mock_console.print.call_args[0][0]
        assert "Database is locked" in call_args

    @patch("planalign_cli.commands.simulate.console")
    @patch("planalign_cli.commands.simulate.show_error_message")
    def test_unhealthy_system_shows_all_issues(self, mock_show_error, mock_console):
        """When multiple issues exist, all are printed before exit."""
        issues = [
            "Configuration error: missing field",
            "Database is locked",
            "DuckDB version mismatch",
        ]
        wrapper = self._make_wrapper(healthy=False, issues=issues)

        with pytest.raises(ClickExit) as exc_info:
            _check_system_health(wrapper)

        assert exc_info.value.exit_code == 1
        mock_show_error.assert_called_once_with("System health check failed")

        # Each issue should have its own console.print call
        assert mock_console.print.call_count == len(issues)
        printed_texts = [
            call[0][0] for call in mock_console.print.call_args_list
        ]
        for issue in issues:
            assert any(issue in text for text in printed_texts), (
                f"Issue '{issue}' was not printed"
            )

    def test_healthy_system_does_not_call_show_error(self):
        """When healthy, show_error_message and console.print are not called for issues."""
        wrapper = self._make_wrapper(healthy=True)

        with patch("planalign_cli.commands.simulate.show_error_message") as mock_show_error:
            _check_system_health(wrapper)

        mock_show_error.assert_not_called()
