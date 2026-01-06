"""Unit tests for sqlparse configuration module.

Feature: 011-sqlparse-token-limit-fix
Test coverage: sqlparse_config module functions

These tests verify the sqlparse configuration module works correctly
for setting MAX_GROUPING_TOKENS to handle large SQL models.
"""

import pytest

from planalign_orchestrator.sqlparse_config import (
    DEFAULT_MAX_GROUPING_TOKENS,
    configure_sqlparse,
    ensure_pth_installed,
    get_current_limit,
    is_configured,
    is_pth_installed,
)


class TestConfigureSqlparse:
    """Tests for configure_sqlparse function."""

    def test_configure_sqlparse_sets_default_limit(self):
        """Test that configure_sqlparse sets the default limit."""
        # Act
        result = configure_sqlparse()

        # Assert
        assert result is True
        assert get_current_limit() == DEFAULT_MAX_GROUPING_TOKENS

    def test_configure_sqlparse_with_custom_limit(self):
        """Test that configure_sqlparse accepts custom limit."""
        # Arrange
        custom_limit = 100000

        # Act
        result = configure_sqlparse(max_tokens=custom_limit)

        # Assert
        assert result is True
        assert get_current_limit() == custom_limit

        # Cleanup - restore default
        configure_sqlparse()

    def test_configure_sqlparse_returns_true_on_success(self):
        """Test that configure_sqlparse returns True when successful."""
        result = configure_sqlparse()
        assert result is True


class TestGetCurrentLimit:
    """Tests for get_current_limit function."""

    def test_get_current_limit_returns_int(self):
        """Test that get_current_limit returns an integer."""
        result = get_current_limit()
        assert isinstance(result, int)

    def test_get_current_limit_returns_configured_value(self):
        """Test that get_current_limit returns the configured value."""
        # Arrange
        configure_sqlparse(75000)

        # Act
        result = get_current_limit()

        # Assert
        assert result == 75000

        # Cleanup
        configure_sqlparse()


class TestIsConfigured:
    """Tests for is_configured function."""

    def test_is_configured_returns_true_when_limit_is_high(self):
        """Test is_configured returns True when limit >= DEFAULT."""
        # Arrange
        configure_sqlparse(DEFAULT_MAX_GROUPING_TOKENS)

        # Act
        result = is_configured()

        # Assert
        assert result is True

    def test_is_configured_returns_true_when_limit_exceeds_default(self):
        """Test is_configured returns True when limit > DEFAULT."""
        # Arrange
        configure_sqlparse(DEFAULT_MAX_GROUPING_TOKENS * 2)

        # Act
        result = is_configured()

        # Assert
        assert result is True

        # Cleanup
        configure_sqlparse()

    def test_is_configured_returns_false_when_limit_is_low(self):
        """Test is_configured returns False when limit < DEFAULT."""
        # Arrange - temporarily set low limit
        import sqlparse.engine.grouping

        original = sqlparse.engine.grouping.MAX_GROUPING_TOKENS
        sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 10000

        try:
            # Act
            result = is_configured()

            # Assert
            assert result is False
        finally:
            # Cleanup
            sqlparse.engine.grouping.MAX_GROUPING_TOKENS = original


class TestModuleImportBehavior:
    """Tests for module-level configuration behavior."""

    def test_sqlparse_is_configured_on_module_import(self):
        """Test that importing the module configures sqlparse."""
        # The module applies configuration at import time via _configured
        from planalign_orchestrator import sqlparse_config

        # Verify module-level _configured flag
        assert hasattr(sqlparse_config, "_configured")
        assert sqlparse_config._configured is True

    def test_default_limit_is_50000(self):
        """Test that the default limit is 50,000 tokens."""
        assert DEFAULT_MAX_GROUPING_TOKENS == 50000


class TestIntegrationWithSqlparse:
    """Integration tests with sqlparse module."""

    def test_sqlparse_can_parse_large_sql(self):
        """Test that sqlparse can parse SQL after configuration."""
        import sqlparse

        # Arrange - configure limits
        configure_sqlparse()

        # Create a moderately large SQL statement
        columns = ", ".join([f"col_{i}" for i in range(100)])
        sql = f"SELECT {columns} FROM my_table WHERE id = 1"

        # Act - parse should not raise
        parsed = sqlparse.parse(sql)

        # Assert
        assert len(parsed) == 1
        assert parsed[0].get_type() == "SELECT"

    def test_sqlparse_format_works_with_configured_limit(self):
        """Test that sqlparse.format works after configuration."""
        import sqlparse

        # Arrange
        configure_sqlparse()
        sql = "SELECT a, b, c FROM table WHERE x = 1"

        # Act - format should not raise
        formatted = sqlparse.format(sql, reindent=True, keyword_case="upper")

        # Assert
        assert "SELECT" in formatted
        assert "FROM" in formatted


class TestPthInstallation:
    """Tests for .pth file auto-installation functions."""

    def test_is_pth_installed_returns_bool(self):
        """Test that is_pth_installed returns a boolean."""
        result = is_pth_installed()
        assert isinstance(result, bool)

    def test_ensure_pth_installed_returns_true_when_already_installed(self):
        """Test ensure_pth_installed returns True when .pth exists."""
        # The .pth file should already be installed by module import
        result = ensure_pth_installed(silent=True)
        assert result is True

    def test_ensure_pth_installed_silent_mode(self):
        """Test that silent mode doesn't raise errors."""
        # Should not raise, should return True (already installed)
        result = ensure_pth_installed(silent=True)
        assert result is True

    def test_pth_installed_after_module_import(self):
        """Test that .pth is installed after importing the module."""
        from planalign_orchestrator import sqlparse_config

        # The module auto-installs .pth on import
        assert hasattr(sqlparse_config, "_pth_installed")
        assert sqlparse_config._pth_installed is True
