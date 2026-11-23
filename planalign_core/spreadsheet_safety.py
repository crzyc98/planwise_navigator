"""Helpers to keep exported spreadsheet text cells from running as formulas."""

from __future__ import annotations

# Leading characters spreadsheet apps (Excel, Sheets, Calc) interpret as a formula.
FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def neutralize_formula(value: str) -> str:
    """Prefix a leading apostrophe when *value* starts with a formula trigger."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value
