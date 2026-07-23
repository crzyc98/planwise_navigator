"""All-mart correctness parity helper (Feature 121).

Thin re-export shim. The canonical implementation now lives in
``planalign_orchestrator.change_validation`` (so ``planalign validate-change`` and the
tests share one source of truth). See
specs/121-reduce-dbt-invocations/contracts/correctness-parity.md.
"""

from __future__ import annotations

from planalign_orchestrator.change_validation import (  # noqa: F401
    AUDIT_TABLES,
    DEFAULT_EXCLUDED,
    assert_all_marts_identical,
    compare_marts,
    discover_marts,
)

__all__ = [
    "AUDIT_TABLES",
    "DEFAULT_EXCLUDED",
    "assert_all_marts_identical",
    "compare_marts",
    "discover_marts",
]
