"""Package code must resolve the default database through get_database_path().

A literal "dbt/simulation.duckdb" default ignores DATABASE_PATH, so a run meant
for an isolated database silently reads or writes the shared dev database.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.config]

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = (
    "planalign_orchestrator",
    "planalign_api",
    "planalign_cli",
    "planalign_core",
)
SHARED_DB = "dbt/simulation.duckdb"
# Guards that compare a path against the shared DB to refuse it.
ALLOWED = {"planalign_orchestrator/construction/builder.py"}


def _shared_db_literals() -> list[str]:
    hits = []
    for package in PACKAGES:
        for path in sorted((ROOT / package).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative in ALLOWED:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and node.value == SHARED_DB:
                    hits.append(f"{relative}:{node.lineno}")
    return hits


def test_no_hard_coded_shared_database_default() -> None:
    assert (
        _shared_db_literals() == []
    ), f'Use get_database_path() instead of a literal "{SHARED_DB}"'
