"""Select CI suites and validate the aggregate CI gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

BASE_JOBS = {
    "lint",
    "studio",
    "fast-tests",
    "python-dependency-audit",
    "validate-models",
}
SIMULATION_JOBS = {"multi-year-invariants", "edge-config-matrix"}
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


def select() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    full = os.environ["GITHUB_EVENT_NAME"] != "pull_request" or any(
        label["name"] == "full-ci"
        for label in event.get("pull_request", {}).get("labels", [])
    )
    # Simulations run after merge and nightly; full-ci asks for them on a PR.
    simulation = full
    values = f"full={str(full).lower()}\nsimulation={str(simulation).lower()}\n"
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
