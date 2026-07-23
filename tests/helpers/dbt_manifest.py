"""Compile and load the production dbt manifest for graph-contract tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]


@lru_cache(maxsize=1)
def load_production_manifest() -> dict[str, Any]:
    """Return a freshly parsed manifest so tests never trust stale target state."""
    dbt = shutil.which("dbt")
    if dbt is None:
        raise AssertionError("dbt executable is required for graph-contract tests")

    result = subprocess.run(
        [dbt, "parse", "--no-partial-parse", "--quiet"],
        cwd=ROOT / "dbt",
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"dbt parse failed:\n{result.stdout}\n{result.stderr}")

    return json.loads((ROOT / "dbt/target/manifest.json").read_text())


def model_nodes(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index production model nodes by relation name."""
    return {
        node["name"]: node
        for node in manifest["nodes"].values()
        if node.get("resource_type") == "model"
    }
