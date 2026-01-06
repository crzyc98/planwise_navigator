#!/usr/bin/env python3
"""Install sqlparse token limit fix for dbt subprocess execution.

This script installs the sqlparse token limit fix to handle large dbt models.

On Windows: Uses sitecustomize.py (more reliable than .pth files on Windows)
On Linux/macOS: Uses .pth file with an import statement

Usage:
    python scripts/install_sqlparse_fix.py

The script is idempotent - it can be run multiple times safely.
"""

import site
import sys
from pathlib import Path

# Content for the sqlparse config module
SQLPARSE_CONFIG_CONTENT = '''"""Configure sqlparse token limits for large dbt models.

This module is automatically imported via sqlparse_config.pth when Python starts.
It configures sqlparse to handle models with >10,000 SQL tokens.

Installed by: scripts/install_sqlparse_fix.py
See: https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495
"""
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass  # Older sqlparse versions don't have this setting
'''

# Content for the .pth file - this executes the import
PTH_CONTENT = '''# Configure sqlparse token limits for large dbt models
# See: scripts/install_sqlparse_fix.py
import _sqlparse_config
'''

# Content for sitecustomize.py (used on Windows)
SITECUSTOMIZE_CONTENT = '''
# sqlparse token limit fix (installed by scripts/install_sqlparse_fix.py)
# See: https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass
'''


def get_site_packages_path() -> Path | None:
    """Get the site-packages path for the current virtual environment."""
    # Get site-packages directories
    site_packages = site.getsitepackages()

    # Prefer the first site-packages that exists and is writable
    for sp in site_packages:
        sp_path = Path(sp)
        if sp_path.exists() and sp_path.is_dir():
            return sp_path

    return None


def install_pth_fix() -> bool:
    """Install .pth file and config module in the virtual environment.

    Returns:
        True if installation was successful, False otherwise.
    """
    site_packages = get_site_packages_path()

    if site_packages is None:
        print("ERROR: Could not find site-packages directory")
        print("Available paths:", site.getsitepackages())
        return False

    # Create the config module
    config_path = site_packages / "_sqlparse_config.py"
    try:
        config_path.write_text(SQLPARSE_CONFIG_CONTENT)
        print(f"✓ Created {config_path}")
    except PermissionError:
        print(f"ERROR: Permission denied writing to {config_path}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to write {config_path}: {e}")
        return False

    # Create the .pth file
    pth_path = site_packages / "sqlparse_config.pth"
    try:
        pth_path.write_text(PTH_CONTENT)
        print(f"✓ Created {pth_path}")
    except PermissionError:
        print(f"ERROR: Permission denied writing to {pth_path}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to write {pth_path}: {e}")
        return False

    return True


def install_sitecustomize_fix() -> bool:
    """Install fix via sitecustomize.py (more reliable on Windows).

    Returns:
        True if installation was successful, False otherwise.
    """
    site_packages = get_site_packages_path()

    if site_packages is None:
        print("ERROR: Could not find site-packages directory")
        print("Available paths:", site.getsitepackages())
        return False

    sc_path = site_packages / "sitecustomize.py"
    try:
        if sc_path.exists():
            # Check if already installed
            existing = sc_path.read_text()
            if "MAX_GROUPING_TOKENS = 50000" in existing:
                print(f"✓ Fix already present in {sc_path}")
                return True
            # Append to existing
            sc_path.write_text(existing + "\n" + SITECUSTOMIZE_CONTENT)
            print(f"✓ Appended fix to {sc_path}")
        else:
            # Create new
            sc_path.write_text(SITECUSTOMIZE_CONTENT.lstrip())
            print(f"✓ Created {sc_path}")
        return True
    except PermissionError:
        print(f"ERROR: Permission denied writing to {sc_path}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to write {sc_path}: {e}")
        return False


def verify_installation() -> bool:
    """Verify that sqlparse is configured correctly.

    Note: The .pth file is only processed at Python startup, so this
    verification will only work in a new Python process.

    Returns:
        True if configuration is verified, False otherwise.
    """
    try:
        import sqlparse.engine.grouping

        current_limit = getattr(sqlparse.engine.grouping, "MAX_GROUPING_TOKENS", None)
        if current_limit == 50000:
            print(f"✓ MAX_GROUPING_TOKENS is set to {current_limit}")
            return True
        else:
            print(f"⚠ MAX_GROUPING_TOKENS is {current_limit} (expected 50000)")
            print("  This is expected - .pth files are only processed at Python startup")
            return False
    except ImportError:
        print("⚠ sqlparse is not installed")
        return False


def main() -> int:
    """Main entry point."""
    print("Installing sqlparse token limit fix...")
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print()

    # Use sitecustomize.py on Windows, .pth file on other platforms
    if sys.platform == "win32":
        print("Using sitecustomize.py method (Windows)")
        success = install_sitecustomize_fix()
    else:
        print("Using .pth file method (Linux/macOS)")
        success = install_pth_fix()

    if not success:
        return 1

    print()
    print("Verifying installation...")

    # In the current process, manually apply the config for verification
    try:
        import sqlparse.engine.grouping

        sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
    except (ImportError, AttributeError):
        pass

    verify_installation()

    print()
    print("Installation complete!")
    print()
    print("To verify in a new Python process:")
    print('  python -c "import sqlparse.engine.grouping; print(f\'MAX_GROUPING_TOKENS={sqlparse.engine.grouping.MAX_GROUPING_TOKENS}\')"')
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
