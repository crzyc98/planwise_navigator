#!/usr/bin/env python3
"""Fail when the repository's fast pytest suite exceeds its hard time budget."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds", type=float, required=True)
    parser.add_argument("--pytest", default="pytest")
    args, remainder = parser.parse_known_args(argv)
    command = [args.pytest, "-m", "fast", *remainder]
    started = time.monotonic()
    try:
        completed = subprocess.run(command, timeout=args.max_seconds, check=False)
    except subprocess.TimeoutExpired:
        print(f"Fast suite exceeded {args.max_seconds:.1f}s", file=sys.stderr)
        return 124
    elapsed = time.monotonic() - started
    if completed.returncode:
        return completed.returncode
    if elapsed > args.max_seconds:
        print(
            f"Fast suite exceeded {args.max_seconds:.1f}s ({elapsed:.2f}s)",
            file=sys.stderr,
        )
        return 124
    print(f"Fast suite completed in {elapsed:.2f}s (budget {args.max_seconds:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
