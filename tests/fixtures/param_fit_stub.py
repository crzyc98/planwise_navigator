"""A stand-in for ``planalign fit|backtest`` in Studio job tests (#588).

Invoked as ``python param_fit_stub.py <behaviour> <pack_dir> [<fixture_pack>]``.
It speaks the real progress protocol and exits with the real CLI exit codes,
so the job runner can be tested for every outcome without fitting anything.
"""

from __future__ import annotations

import shutil
import sys
import time

from planalign_fit.progress import emit


def main(behaviour: str, pack_dir: str, fixture_pack: str = "") -> int:
    emit("stage", stage="loading_history")
    emit("stage", stage="fitting")
    if behaviour in ("success", "backtest"):
        if behaviour == "backtest":
            for index, seed in enumerate((42, 43), start=1):
                emit("seed_started", seed=seed, index=index, total=2, years=[2025])
                emit("seed_completed", seed=seed, index=index, total=2)
            emit("stage", stage="scoring")
        emit("stage", stage="writing_pack")
        shutil.copytree(fixture_pack, pack_dir)
        emit("completed", pack_id="stub")
        return 0
    if behaviour == "sleep":
        print("working", flush=True)
        time.sleep(120)
        return 0
    if behaviour == "simfail":
        emit("seed_started", seed=43, index=1, total=1, years=[2025])
        emit(
            "simulation_failed",
            seed=43,
            year=2025,
            message=f"Backtest simulation failed for seed 43, year 2025. {pack_dir}",
        )
        print("Backtest simulation failed for seed 43, year 2025.")
        return 4
    if behaviour.startswith("exit:"):
        print(f"stub failure message for {pack_dir}", flush=True)
        return int(behaviour.split(":", 1)[1])
    raise SystemExit(f"unknown behaviour {behaviour}")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
