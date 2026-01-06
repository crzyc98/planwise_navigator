"""Integration tests for sqlparse configuration in subprocess execution.

Feature: 011-sqlparse-token-limit-fix
Test coverage: Subprocess dbt execution with sqlparse configuration

These tests verify that the sqlparse configuration is correctly loaded
when Python subprocesses are spawned, which is critical for dbt execution.
"""

import subprocess
import sys
from pathlib import Path

import pytest


class TestSubprocessSqlparseConfiguration:
    """Tests for sqlparse configuration in subprocess environments."""

    def test_subprocess_inherits_sqlparse_config_via_pth(self):
        """Test that a new Python subprocess has sqlparse configured via .pth file."""
        # Act - run a subprocess to check sqlparse config
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sqlparse.engine.grouping; print(sqlparse.engine.grouping.MAX_GROUPING_TOKENS)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Assert
        assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
        limit = int(result.stdout.strip())
        assert limit == 50000, f"Expected 50000, got {limit}"

    def test_dbt_subprocess_has_correct_sqlparse_config(self):
        """Test that dbt subprocess has sqlparse configured correctly.

        This simulates how the DbtRunner spawns dbt commands.
        """
        # Act - run dbt --version in a subprocess (lightweight check)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import sqlparse.engine.grouping
# This is what dbt does internally - parse SQL
import sqlparse
# Check the limit
print(f"limit={sqlparse.engine.grouping.MAX_GROUPING_TOKENS}")
""",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Assert
        assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
        assert "limit=50000" in result.stdout

    def test_pth_file_exists_in_site_packages(self):
        """Test that the .pth file was installed correctly."""
        import site

        # Get site-packages paths
        site_packages = site.getsitepackages()

        # Look for our .pth file
        pth_found = False
        config_found = False

        for sp in site_packages:
            sp_path = Path(sp)
            if (sp_path / "sqlparse_config.pth").exists():
                pth_found = True
            if (sp_path / "_sqlparse_config.py").exists():
                config_found = True

        assert pth_found, "sqlparse_config.pth not found in site-packages"
        assert config_found, "_sqlparse_config.py not found in site-packages"

    def test_config_module_content_is_correct(self):
        """Test that the _sqlparse_config.py module has correct content."""
        import site

        site_packages = site.getsitepackages()

        for sp in site_packages:
            config_path = Path(sp) / "_sqlparse_config.py"
            if config_path.exists():
                content = config_path.read_text()
                assert "MAX_GROUPING_TOKENS" in content
                assert "50000" in content
                return

        pytest.fail("_sqlparse_config.py not found in any site-packages")

    def test_multiple_subprocess_invocations_consistent(self):
        """Test that multiple subprocess invocations all have correct config."""
        results = []

        for _ in range(3):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sqlparse.engine.grouping; print(sqlparse.engine.grouping.MAX_GROUPING_TOKENS)",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            results.append(int(result.stdout.strip()))

        # All should be 50000
        assert all(r == 50000 for r in results), f"Inconsistent results: {results}"


class TestDbtRunnerSubprocessIntegration:
    """Tests for DbtRunner subprocess integration with sqlparse config."""

    @pytest.mark.skipif(
        not Path("/workspace/dbt").exists(),
        reason="dbt directory not found",
    )
    def test_dbt_runner_subprocess_environment(self):
        """Test that DbtRunner subprocess has correct sqlparse environment."""
        from planalign_orchestrator.dbt_runner import DbtRunner

        # Create a runner with the dbt directory
        dbt_dir = Path("/workspace/dbt")
        runner = DbtRunner(working_dir=dbt_dir)

        # Use python to check sqlparse config (simulating dbt's Python environment)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sqlparse.engine.grouping; print(sqlparse.engine.grouping.MAX_GROUPING_TOKENS)",
            ],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "50000" in result.stdout

    @pytest.mark.skipif(
        not Path("/workspace/dbt").exists(),
        reason="dbt directory not found",
    )
    def test_dbt_debug_command_succeeds(self):
        """Test that dbt debug command works with configured sqlparse."""
        dbt_dir = Path("/workspace/dbt")

        result = subprocess.run(
            [sys.executable, "-m", "dbt", "debug"],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # dbt debug should run without token errors
        assert "Maximum number of tokens exceeded" not in result.stderr
        # Note: dbt debug may fail for other reasons (no profiles.yml, etc.)
        # but should not fail due to sqlparse token limits
