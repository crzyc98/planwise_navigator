"""SQL identifier validation for values DuckDB can't bind as parameters.

Lives in ``planalign_core`` so the orchestrator and the API share one check;
``planalign_api.services.sql_security`` re-exports it unchanged.
"""

import re

# Valid SQL identifier pattern: alphanumeric and underscores, must start with letter/underscore
VALID_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_]\w*$")

# Maximum identifier length (DuckDB limit)
MAX_IDENTIFIER_LENGTH = 255


class SQLSecurityError(ValueError):
    """Raised when a SQL security validation fails."""

    pass


def validate_column_name(column_name: str, context: str = "column") -> str:
    """
    Validate a column name is safe for SQL interpolation.

    Args:
        column_name: The column name to validate
        context: Description for error messages (e.g., "column", "table")

    Returns:
        The validated column name (unchanged if valid)

    Raises:
        SQLSecurityError: If the column name is invalid or potentially malicious
    """
    if not column_name:
        raise SQLSecurityError(f"Empty {context} name provided")

    if len(column_name) > MAX_IDENTIFIER_LENGTH:
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name[:50]}...': exceeds maximum length"
        )

    if not VALID_IDENTIFIER_PATTERN.match(column_name):
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name}': must contain only "
            "alphanumeric characters and underscores, starting with a letter or underscore"
        )

    # Additional check for SQL keywords that shouldn't be used as identifiers
    sql_keywords = {
        "select",
        "from",
        "where",
        "drop",
        "delete",
        "insert",
        "update",
        "create",
        "alter",
        "truncate",
        "execute",
        "exec",
        "union",
        "join",
    }
    if column_name.lower() in sql_keywords:
        raise SQLSecurityError(
            f"Invalid {context} name '{column_name}': reserved SQL keyword"
        )

    return column_name
