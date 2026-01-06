"""Configure sqlparse token limits for large dbt SQL models.

This module provides a centralized configuration for sqlparse's MAX_GROUPING_TOKENS
limit. sqlparse 0.5.4+ introduced DoS protection that limits token processing to
10,000 tokens, but our complex dbt models (especially fct_workforce_snapshot.sql)
can exceed this limit in Year 2+ simulations.

The configuration is applied at import time to ensure sqlparse is configured before
any SQL parsing occurs. This module also auto-installs the .pth file on first import
to ensure subprocess dbt execution is configured.

See: https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495
"""

import site
import sys
from pathlib import Path

# Default limit that works for our complex SQL models
# 50,000 tokens is 5x the default 10,000 limit, sufficient for Year 2+ models
DEFAULT_MAX_GROUPING_TOKENS = 50000

# Content for the .pth file and config module
_PTH_CONFIG_CONTENT = '''"""Configure sqlparse token limits for large dbt models.

This module is automatically imported via sqlparse_config.pth when Python starts.
It configures sqlparse to handle models with >10,000 SQL tokens.

Auto-installed by: planalign_orchestrator.sqlparse_config
See: https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495
"""
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass  # Older sqlparse versions don't have this setting
'''

_PTH_FILE_CONTENT = '''# Configure sqlparse token limits for large dbt models
# Auto-installed by planalign_orchestrator
import _sqlparse_config
'''


def configure_sqlparse(max_tokens: int = DEFAULT_MAX_GROUPING_TOKENS) -> bool:
    """Configure sqlparse MAX_GROUPING_TOKENS limit.

    Args:
        max_tokens: Maximum number of tokens allowed during SQL grouping.
                   Default is 50,000 (5x the sqlparse default of 10,000).

    Returns:
        True if configuration was applied successfully, False otherwise.
        Returns False if sqlparse is not installed or doesn't have the
        MAX_GROUPING_TOKENS attribute (older versions).
    """
    try:
        import sqlparse.engine.grouping

        sqlparse.engine.grouping.MAX_GROUPING_TOKENS = max_tokens
        return True
    except (ImportError, AttributeError):
        # Older sqlparse versions don't have this setting
        return False


def get_current_limit() -> int | None:
    """Get the current sqlparse MAX_GROUPING_TOKENS limit.

    Returns:
        The current limit value, or None if sqlparse is not installed
        or doesn't have the MAX_GROUPING_TOKENS attribute.
    """
    try:
        import sqlparse.engine.grouping

        return getattr(sqlparse.engine.grouping, "MAX_GROUPING_TOKENS", None)
    except ImportError:
        return None


def is_configured() -> bool:
    """Check if sqlparse is configured with our custom token limit.

    Returns:
        True if MAX_GROUPING_TOKENS is set to at least DEFAULT_MAX_GROUPING_TOKENS,
        False otherwise.
    """
    current = get_current_limit()
    return current is not None and current >= DEFAULT_MAX_GROUPING_TOKENS


def is_pth_installed() -> bool:
    """Check if the .pth file is installed in site-packages.

    Returns:
        True if sqlparse_config.pth exists in any site-packages directory.
    """
    for sp in site.getsitepackages():
        pth_path = Path(sp) / "sqlparse_config.pth"
        if pth_path.exists():
            return True
    return False


def ensure_pth_installed(silent: bool = False) -> bool:
    """Ensure the .pth file is installed for subprocess sqlparse configuration.

    This function auto-installs the .pth file if it doesn't exist, making
    the sqlparse configuration automatic for dbt subprocess execution.

    Args:
        silent: If True, don't print any messages.

    Returns:
        True if .pth is installed (or was just installed), False if installation failed.
    """
    if is_pth_installed():
        return True

    # Try to install to site-packages
    for sp in site.getsitepackages():
        sp_path = Path(sp)
        if sp_path.exists() and sp_path.is_dir():
            try:
                # Write the config module
                config_path = sp_path / "_sqlparse_config.py"
                config_path.write_text(_PTH_CONFIG_CONTENT)

                # Write the .pth file
                pth_path = sp_path / "sqlparse_config.pth"
                pth_path.write_text(_PTH_FILE_CONTENT)

                if not silent:
                    print(
                        f"✓ Auto-installed sqlparse fix to {sp_path}\n"
                        f"  Restart your Python interpreter for subprocess dbt to use the fix.",
                        file=sys.stderr,
                    )
                return True
            except (PermissionError, OSError):
                continue

    return False


# Apply configuration at import time (for in-process dbt)
_configured = configure_sqlparse()

# Auto-install .pth file on first import (for subprocess dbt)
# This runs silently after the first successful install
_pth_installed = ensure_pth_installed(silent=is_pth_installed())
