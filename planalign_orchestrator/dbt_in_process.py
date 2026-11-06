"""Serial, worker-only dbt invocation; process globals are not thread safe."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Iterator

from .dbt_runner import DbtResult


@contextmanager
def invocation_context(working_dir: Path, env: dict[str, str]) -> Iterator[None]:
    """Apply subprocess cwd/environment, restoring even dbt-added environment keys."""
    previous_env = os.environ.copy()
    previous_cwd = Path.cwd()
    try:
        os.environ.clear()
        os.environ.update(env)
        os.chdir(working_dir)
        yield
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)


def invoke_dbt(
    cmd: list[str], working_dir: Path, env: dict[str, str], *, start_ts: float
) -> DbtResult:
    """Capture output without live streaming; never reuse a parsed manifest.

    dbt-duckdb 1.9 caches its environment on the connection manager. Its public
    close_all_connections API drops that environment (LocalEnvironment's
    destructor closes the root DuckDB connection), releasing the file lock.
    """
    from dbt.adapters.duckdb.connections import DuckDBConnectionManager
    from dbt.cli.main import dbtRunner

    stdout, stderr = StringIO(), StringIO()
    code = 2
    with (
        invocation_context(working_dir, env),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        try:
            try:
                result = dbtRunner().invoke(cmd[1:])
                code = 0 if result.success else 1
                if result.exception is not None:
                    code = 2
                    stderr.write(str(result.exception))
            finally:
                DuckDBConnectionManager.close_all_connections()
        except Exception as exc:
            code = 2
            stderr.write(str(exc))
    return DbtResult(
        code == 0,
        stdout.getvalue(),
        stderr.getvalue(),
        time.perf_counter() - start_ts,
        code,
        cmd,
    )
