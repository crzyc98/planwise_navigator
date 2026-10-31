"""Compile and load the production dbt manifest for graph-contract tests."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from planalign_orchestrator.dbt_executable import find_dbt_executable

ROOT = Path(__file__).parents[2]


def load_production_manifest(
    simulation_year: int = 2025, *, deferral_rate_changes_enabled: bool = False
) -> dict[str, Any]:
    """Return a freshly parsed manifest so tests never trust stale target state."""
    # Normalize the arguments: lru_cache keys `f()`, `f(2025)` and
    # `f(deferral_rate_changes_enabled=False)` separately, which re-ran the parse.
    return _parse_manifest(simulation_year, deferral_rate_changes_enabled)


@lru_cache(maxsize=None)
def _parse_manifest(
    simulation_year: int, deferral_rate_changes_enabled: bool
) -> dict[str, Any]:
    dbt = find_dbt_executable()
    if dbt is None:
        raise AssertionError("dbt executable is required for graph-contract tests")

    # `dbt parse` runs no SQL, but the duckdb adapter still opens the profile's
    # database -- and profiles.yml resolves
    # `path: {{ env_var('DATABASE_PATH', 'simulation.duckdb') }}` relative to
    # dbt/, so an unset DATABASE_PATH makes parsing CREATE the shared dev
    # database dbt/simulation.duckdb as a side effect. Point it at a throwaway
    # file instead: parsing must never touch or materialize the shared DB.
    env = dict(os.environ)
    # Graph checks need no telemetry; avoid network retries and shutdown flushes.
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    with tempfile.TemporaryDirectory(prefix="dbt-parse-") as scratch:
        env["DATABASE_PATH"] = str(Path(scratch) / "parse-only.duckdb")
        # xdist workers must not overwrite or read one another's manifests.
        target = Path(scratch) / "target"
        env["DBT_TARGET_PATH"] = str(target)
        env["DBT_LOG_PATH"] = str(Path(scratch) / "logs")
        result = subprocess.run(
            [
                dbt,
                "parse",
                "--no-partial-parse",
                "--quiet",
                "--vars",
                json.dumps(
                    {
                        "simulation_year": simulation_year,
                        "start_year": 2025,
                        "deferral_rate_changes_enabled": deferral_rate_changes_enabled,
                    }
                ),
            ],
            cwd=ROOT / "dbt",
            capture_output=True,
            check=False,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise AssertionError(f"dbt parse failed:\n{result.stdout}\n{result.stderr}")
        return json.loads((target / "manifest.json").read_text())


def clear_manifest_cache() -> None:
    """Forget parsed manifests (for tests that stub the parse)."""
    _parse_manifest.cache_clear()


def model_nodes(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index production model nodes by relation name."""
    return {
        node["name"]: node
        for node in manifest["nodes"].values()
        if node.get("resource_type") == "model"
    }
