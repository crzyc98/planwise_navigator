"""Tests for subprocess_utils module."""

import platform
import pytest

from planalign_api.services.simulation.subprocess_utils import (
    IS_WINDOWS,
    create_subprocess,
    wait_subprocess,
)


@pytest.mark.fast
class TestSubprocessUtilsConstants:
    """Test subprocess utility constants."""

    def test_is_windows_matches_platform(self):
        """IS_WINDOWS should match platform detection."""
        expected = platform.system() == "Windows"
        assert IS_WINDOWS == expected

    def test_is_windows_is_boolean(self):
        """IS_WINDOWS should be a boolean."""
        assert isinstance(IS_WINDOWS, bool)


@pytest.mark.fast
class TestSubprocessUtilsFunctions:
    """Test subprocess utility function signatures."""

    def test_create_subprocess_is_async(self):
        """create_subprocess should be an async function."""
        import asyncio
        assert asyncio.iscoroutinefunction(create_subprocess)

    def test_wait_subprocess_is_async(self):
        """wait_subprocess should be an async function."""
        import asyncio
        assert asyncio.iscoroutinefunction(wait_subprocess)


@pytest.mark.fast
class TestBackwardCompatibility:
    """Test backward compatibility imports."""

    def test_import_from_old_path(self):
        """Should be able to import from simulation_service.py."""
        from planalign_api.services.simulation_service import (
            IS_WINDOWS as OLD_IS_WINDOWS,
            create_subprocess as old_create_subprocess,
            wait_subprocess as old_wait_subprocess,
        )

        # Should be the same objects
        assert OLD_IS_WINDOWS == IS_WINDOWS
        assert old_create_subprocess is create_subprocess
        assert old_wait_subprocess is wait_subprocess

    def test_import_from_new_path(self):
        """Should be able to import from simulation package."""
        from planalign_api.services.simulation import (
            IS_WINDOWS as NEW_IS_WINDOWS,
            create_subprocess as new_create_subprocess,
            wait_subprocess as new_wait_subprocess,
        )

        # Should be the same objects
        assert NEW_IS_WINDOWS == IS_WINDOWS
        assert new_create_subprocess is create_subprocess
        assert new_wait_subprocess is wait_subprocess

    def test_underscore_prefixed_imports(self):
        """Underscore-prefixed names should also work for backward compat."""
        from planalign_api.services.simulation_service import (
            _create_subprocess,
            _wait_subprocess,
        )

        assert _create_subprocess is create_subprocess
        assert _wait_subprocess is wait_subprocess
