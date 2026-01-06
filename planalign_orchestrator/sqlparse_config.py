"""Configure sqlparse token limits for large dbt SQL models.

This module provides a centralized configuration for sqlparse's MAX_GROUPING_TOKENS
limit. sqlparse 0.5.4+ introduced DoS protection that limits token processing to
10,000 tokens, but our complex dbt models (especially fct_workforce_snapshot.sql)
can exceed this limit in Year 2+ simulations.

The configuration is applied at import time to ensure sqlparse is configured before
any SQL parsing occurs. This module is imported by:
1. planalign_orchestrator/__init__.py (defense-in-depth for in-process dbt)
2. sitecustomize.py (for subprocess dbt execution)

See: https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495
"""

# Default limit that works for our complex SQL models
# 50,000 tokens is 5x the default 10,000 limit, sufficient for Year 2+ models
DEFAULT_MAX_GROUPING_TOKENS = 50000


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


# Apply configuration at import time
_configured = configure_sqlparse()
