"""Merge complete CI timing artifacts and record observed shard elapsed times."""

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import subprocess
from typing import Any


def read_run(run_id: str) -> dict[str, Any]:
    result = subprocess.check_output(
        ["gh", "run", "view", run_id, "--json", "jobs,headSha,url"], text=True
    )
    run = json.loads(result)
    shards = {
        job["name"]: job for job in run["jobs"] if job["name"].startswith("test (")
    }
    if shards.keys() != {f"test ({index})" for index in range(1, 5)}:
        raise ValueError("Expected exactly four CI shard jobs")
    elapsed = {}
    for name, job in sorted(shards.items()):
        if job["conclusion"] != "success":
            raise ValueError(f"{name} did not succeed; refusing incomplete baseline")
        step = next(
            step for step in job["steps"] if step["name"].startswith("Run Python tests")
        )
        start = datetime.fromisoformat(step["startedAt"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(step["completedAt"].replace("Z", "+00:00"))
        elapsed[name] = (end - start).total_seconds()
    return {"url": run["url"], "head_sha": run["headSha"], "test_step_seconds": elapsed}


def merge_durations(artifacts: Path) -> dict[str, float]:
    merged: dict[str, float] = {}
    for index in range(1, 5):
        path = artifacts / f"test-durations-{index}" / ".test_durations"
        durations = json.loads(path.read_text())
        if not durations or not isinstance(durations, dict):
            raise ValueError(f"Empty or invalid shard timings: {path}")
        if duplicate := merged.keys() & durations.keys():
            raise ValueError(f"Duplicate tests across shards: {sorted(duplicate)}")
        for nodeid, duration in durations.items():
            if (
                not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or duration < 0
            ):
                raise ValueError(f"Invalid duration for {nodeid}: {duration}")
        merged.update(durations)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Source CI run ID")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--compare-run", help="Complete run using refreshed timings")
    args = parser.parse_args()
    before = read_run(args.run)
    durations = merge_durations(args.artifacts)
    provenance = {"source": before, "test_count": len(durations)}
    if args.compare_run:
        after = read_run(args.compare_run)
        provenance["comparison"] = after
        for name, elapsed in before["test_step_seconds"].items():
            current = after["test_step_seconds"][name]
            print(
                f"{name}: {elapsed:.0f}s -> {current:.0f}s ({current - elapsed:+.0f}s)"
            )
    Path(".test_durations").write_text(
        json.dumps(durations, indent=4, sort_keys=True) + "\n"
    )
    Path(".test_durations.provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
