"""Guards against reintroducing event-loop-blocking async route handlers.

An `async def` FastAPI route handler runs directly on the asyncio event
loop; only plain `def` handlers are offloaded to the threadpool. A handler
declared `async def` with no `await` anywhere in its body gains nothing
from being async and instead stalls the whole server for its full
duration whenever it does blocking I/O (DuckDB, filesystem, Excel, ...).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.fast

ROUTERS_DIR = pathlib.Path(__file__).resolve().parents[2] / "planalign_api" / "routers"


def _is_router_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(target, ast.Attribute)
        and getattr(target.value, "id", None) == "router"
    )


def _has_await(node: ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(descendant, (ast.Await, ast.AsyncWith, ast.AsyncFor))
        for descendant in ast.walk(node)
    )


def _blocking_async_handlers() -> list[str]:
    offenders = []
    for path in sorted(ROUTERS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(_is_router_decorator(d) for d in node.decorator_list):
                continue
            if not _has_await(node):
                offenders.append(f"{path.name}:{node.lineno} {node.name}")
    return offenders


def test_no_async_route_handlers_without_await():
    offenders = _blocking_async_handlers()
    assert offenders == [], (
        "async route handlers with no await block the event loop for their "
        "full duration; convert to a plain `def` (FastAPI runs it in its "
        "threadpool) or add a genuine await:\n" + "\n".join(offenders)
    )
