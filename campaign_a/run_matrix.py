"""Serial baseline runner; preserve failed attempts and never retry implicitly."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cells = json.loads((ROOT / "campaign_a/matrix.json").read_text())
    logs = Path("/tmp/nhcal/matrix_logs")
    logs.mkdir(parents=True, exist_ok=True)
    for cell in cells:
        for seed in cell["seeds"]:
            path = ROOT / "campaign_a/cells" / f"{cell['id']}.json"
            prior = json.loads(path.read_text()).get("runs", {}).get("baseline", {})
            if str(seed) in prior:
                print(
                    f"Preserved {cell['id']} seed {seed}: {prior[str(seed)]['status']}",
                    flush=True,
                )
                continue
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
                "baseline",
            ]
            with (logs / f"{cell['id']}_{seed}.log").open("x") as log:
                log.write(f"Started {stamp}\n")
                log.flush()
                result = subprocess.run(
                    command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False
                )
            print(
                f"{datetime.now(timezone.utc).isoformat()} END {cell['id']} seed {seed}: exit {result.returncode}",
                flush=True,
            )


if __name__ == "__main__":
    main()
