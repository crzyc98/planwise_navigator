"""Select CI suites and validate the aggregate CI gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SIMULATION_MARKERS = ("multi_year_invariants", "edge_config_matrix")

BASE_JOBS = {
    "lint",
    "studio",
    "fast-tests",
    "python-dependency-audit",
    "validate-models",
}
SIMULATION_JOBS = {"simulation-suites"}
FULL_JOBS = {"test", "coverage"}


def gate_errors(jobs: dict[str, dict], simulation: bool, full: bool) -> list[str]:
    required = BASE_JOBS | {"ci-scope"}
    if simulation:
        required |= SIMULATION_JOBS
    if full:
        required |= FULL_JOBS | SIMULATION_JOBS
    errors = [
        f"{name}: expected success, got {jobs.get(name, {}).get('result', 'missing')}"
        for name in sorted(required)
        if jobs.get(name, {}).get("result") != "success"
    ]
    errors.extend(
        f"{name}: {job.get('result')}"
        for name, job in jobs.items()
        if name not in required and job.get("result") not in {"success", "skipped"}
    )
    return errors


def simulation_suites(root: Path = ROOT) -> list[str]:
    """Test files that run real simulations; CI gives each its own runner."""
    marker = re.compile(rf"pytest\.mark\.({'|'.join(SIMULATION_MARKERS)})\b")
    suites = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("test_*.py")
        if marker.search(path.read_text())
    )
    if not suites:
        raise SystemExit("No simulation suites found; the matrix would be empty")
    return suites


def select() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    full = os.environ["GITHUB_EVENT_NAME"] != "pull_request" or any(
        label["name"] == "full-ci"
        for label in event.get("pull_request", {}).get("labels", [])
    )
    # Simulations run after merge and nightly; full-ci asks for them on a PR.
    simulation = full
    values = (
        f"full={str(full).lower()}\nsimulation={str(simulation).lower()}\n"
        f"suites={json.dumps(simulation_suites())}\n"
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(values)
    print(values)


def main() -> None:
    if sys.argv[1] == "select":
        select()
        return
    jobs = json.loads(os.environ["CI_NEEDS"])
    outputs = jobs.get("ci-scope", {}).get("outputs", {})
    if any(outputs.get(key) not in {"true", "false"} for key in ("simulation", "full")):
        raise SystemExit("Missing or invalid CI selection outputs")
    errors = gate_errors(
        jobs, outputs["simulation"] == "true", outputs["full"] == "true"
    )
    if errors:
        raise SystemExit("\n".join(errors))
    print("All selected CI checks passed")


if __name__ == "__main__":
    main()
