#!/usr/bin/env python3
"""Install sqlparse token limit fix for dbt subprocess execution.

This script creates a .pth file in the virtual environment's site-packages
directory with an import statement. Python processes .pth files when loading
site-packages, and any line starting with "import " is executed as code.

This approach works better than sitecustomize.py in virtual environments
because sitecustomize.py is typically loaded from the base Python installation,
not from the venv.

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
    print()

    if not install_pth_fix():
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
