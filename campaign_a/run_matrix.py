"""Serial baseline runner; preserve failed attempts and never retry implicitly."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = Path("/tmp/nhcal/matrix_logs")
STAGES = (
    "baseline",
    "prerequisite_repair",
    "hire_date_fix",
    "search_fix",
    "indexed_cola",
    "prior_hire_turnover",
    "turnover_indexed_3pct",
    "backfill_by_level",
    "two_dial",
    "promo_backfill",
)


def run_matrix(stage: str = "baseline", limit: int | None = None) -> None:
    if stage not in STAGES or (limit is not None and limit < 1):
        raise ValueError("Unsupported stage or nonpositive limit")
    launched = 0
    cells = json.loads((ROOT / "campaign_a/matrix.json").read_text())
    logs = LOG_ROOT if stage == "baseline" else LOG_ROOT / stage
    logs.mkdir(parents=True, exist_ok=True)
    for cell in cells:
        for seed in cell["seeds"]:
            path = ROOT / "campaign_a/cells" / f"{cell['id']}.json"
            prior = json.loads(path.read_text()).get("runs", {}).get(stage, {})
            if str(seed) in prior:
                print(
                    f"Preserved {cell['id']} seed {seed}: {prior[str(seed)]['status']}",
                    flush=True,
                )
                continue
            if limit is not None and launched >= limit:
                return
            stamp = datetime.now(timezone.utc).isoformat()
            print(f"{stamp} START {cell['id']} seed {seed}", flush=True)
            command = [
                sys.executable,
                "-m",
                "campaign_a.run_cell",
                "--cell",
                cell["id"],
                "--seed",
                str(seed),
                "--stage",
                stage,
            ]
            with (logs / f"{cell['id']}_{seed}.log").open("x") as log:
                log.write(f"Started {stamp}\n")
                log.flush()
                result = subprocess.run(
                    command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False
                )
            launched += 1
            print(
                f"{datetime.now(timezone.utc).isoformat()} END {cell['id']} seed {seed}: exit {result.returncode}",
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=list(STAGES),
        default="baseline",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run_matrix(args.stage, args.limit)


if __name__ == "__main__":
    main()
