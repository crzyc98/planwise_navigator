#!/usr/bin/env python3
"""
Test to prevent regression of legacy database paths - Epic E050, Story S050-06

This test ensures that no Python files in the codebase use the legacy
simulation.duckdb path directly. All database connections should use
the standardized get_database_path() function.
"""

import glob
import re
from pathlib import Path


def test_no_legacy_db_paths():
    """Test that no Python files use legacy database paths."""
    project_root = Path(__file__).parent.parent
    offenders = []

    # Search all Python files for legacy patterns
    for py_file in project_root.glob("**/*.py"):
        # Skip this test file itself
        if py_file.name == "test_no_legacy_db_paths.py":
            continue

        # Skip migration utility which legitimately references both paths
        if py_file.name == "migrate_database_location.py":
            continue

        try:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Check for problematic patterns
            legacy_patterns = [
                # Direct duckdb.connect with root path
                r'duckdb\.connect\(\s*[\'"]simulation\.duckdb[\'"]',
                # String literals with root path (exclude comments)
                r'(?<!#.*)[\'"]simulation\.duckdb[\'"](?!\s*#)',
                # Path construction with root location
                r'Path\(\s*[\'"]simulation\.duckdb[\'"]',
                # os.path.join with root location
                r'os\.path\.join\([^)]*[\'"]simulation\.duckdb[\'"]',
            ]

            for pattern in legacy_patterns:
                if re.search(pattern, content):
                    offenders.append(str(py_file.relative_to(project_root)))
                    break  # One offense per file is enough

        except Exception as e:
            # Skip files that can't be read
            continue

    # Report results
    if offenders:
        offender_list = '\n  - '.join([''] + offenders)
        error_msg = f"""
Legacy database paths detected in {len(offenders)} files:{offender_list}

All database connections should use:
  from navigator_orchestrator.config import get_database_path
  conn = duckdb.connect(str(get_database_path()))

Or set DATABASE_PATH environment variable for standardized location.
"""
        assert False, error_msg


def test_standardized_imports_available():
    """Test that standardized database path function is available."""
    try:
        from navigator_orchestrator.config import get_database_path
        # Verify function works
        path = get_database_path()
        assert path.name == "simulation.duckdb"
        assert "dbt" in str(path)  # Should be in dbt subdirectory
    except ImportError as e:
        assert False, f"get_database_path function not available: {e}"


def test_environment_variable_support():
    """Test that DATABASE_PATH environment variable is respected."""
    import os
    import tempfile
    from navigator_orchestrator.config import get_database_path

    # Test with custom path
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_path = f"{temp_dir}/custom_db.duckdb"

        # Set environment variable
        original_value = os.environ.get('DATABASE_PATH')
        try:
            os.environ['DATABASE_PATH'] = custom_path

            # Import should reload and use new path
            import importlib
            import navigator_orchestrator.config
            importlib.reload(navigator_orchestrator.config)

            path = navigator_orchestrator.config.get_database_path()
            assert str(path) == str(Path(custom_path).resolve())

        finally:
            # Restore original environment
            if original_value is not None:
                os.environ['DATABASE_PATH'] = original_value
            else:
                os.environ.pop('DATABASE_PATH', None)

            # Reload to restore original configuration
            importlib.reload(navigator_orchestrator.config)


if __name__ == "__main__":
    test_no_legacy_db_paths()
    test_standardized_imports_available()
    test_environment_variable_support()
    print("✅ All database path standardization tests passed!")
