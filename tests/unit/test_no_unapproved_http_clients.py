"""Guard against unapproved HTTP client imports in runtime packages (#1192).

PlanAlign Engine is an on-premises platform with zero cloud dependencies
(see SECURITY.md). Any HTTP client import introduced into a ``planalign_*``
package must be reviewed and explicitly allowlisted below with a clear reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_HTTP_LIBRARIES: frozenset[str] = frozenset(
    {
        "requests",
        "httpx",
        "urllib.request",
        "urllib3",
        "aiohttp",
        "http.client",
    }
)

# Explicit allowlist of repo-relative paths permitted to import an HTTP client
# library, each mapped to a one-line justification.
#
# Currently empty: workspace Git sync uses GitPython (not an HTTP client),
# API test clients live under tests/, and the unused outbound connectivity
# checks in planalign_core/network_config.py and
# planalign_orchestrator/network_utils.py were removed in #1192.
HTTP_CLIENT_IMPORT_ALLOWLIST: dict[str, str] = {}


def _matches_forbidden(module_name: str) -> str | None:
    for forbidden in FORBIDDEN_HTTP_LIBRARIES:
        if module_name == forbidden or module_name.startswith(f"{forbidden}."):
            return forbidden
    return None


def _find_forbidden_imports(
    source: str, filename: str = "<memory>"
) -> list[tuple[int, str]]:
    """Return ``(lineno, library)`` for every forbidden HTTP client import in source."""
    tree = ast.parse(source, filename=filename)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                matched = _matches_forbidden(alias.name)
                if matched:
                    findings.append((node.lineno, matched))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            matched = _matches_forbidden(module)
            if matched:
                findings.append((node.lineno, matched))
                continue
            for alias in node.names:
                combined = f"{module}.{alias.name}" if module else alias.name
                matched_alias = _matches_forbidden(combined)
                if matched_alias:
                    findings.append((node.lineno, matched_alias))
    return sorted(findings)


def _iter_runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for pkg_dir in sorted(REPO_ROOT.glob("planalign_*")):
        if pkg_dir.is_dir():
            files.extend(sorted(pkg_dir.rglob("*.py")))
    return files


def test_runtime_packages_do_not_import_unapproved_http_clients() -> None:
    files = _iter_runtime_python_files()
    assert files, "expected at least one Python file under planalign_* packages"

    violations: list[str] = []
    for path in files:
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        if rel_path in HTTP_CLIENT_IMPORT_ALLOWLIST:
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, library in _find_forbidden_imports(source, filename=rel_path):
            violations.append(f"{rel_path}:{lineno} imports {library}")

    assert not violations, (
        "Unapproved HTTP client import(s) in planalign_* packages "
        "(remove the outbound client or add a justified entry to "
        "HTTP_CLIENT_IMPORT_ALLOWLIST):\n  " + "\n  ".join(violations)
    )


def test_http_client_allowlist_entries_exist_and_are_documented() -> None:
    for rel_path, reason in HTTP_CLIENT_IMPORT_ALLOWLIST.items():
        assert (
            reason.strip()
        ), f"Allowlist entry {rel_path} must include a one-line reason"
        assert (REPO_ROOT / rel_path).is_file(), f"Stale allowlist entry: {rel_path}"


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("import requests\n", [(1, "requests")]),
        ("from requests.adapters import HTTPAdapter\n", [(1, "requests")]),
        ("import httpx\n", [(1, "httpx")]),
        ("import urllib.request\n", [(1, "urllib.request")]),
        ("from urllib import request\n", [(1, "urllib.request")]),
        ("from urllib.request import urlopen\n", [(1, "urllib.request")]),
        ("import urllib3\n", [(1, "urllib3")]),
        ("import aiohttp\n", [(1, "aiohttp")]),
        ("import http.client\n", [(1, "http.client")]),
        ("from http import client\n", [(1, "http.client")]),
        ("from urllib.parse import urlparse\n", []),
    ],
)
def test_forbidden_import_detector_handles_all_import_forms(
    snippet: str, expected: list[tuple[int, str]]
) -> None:
    assert _find_forbidden_imports(snippet) == expected
