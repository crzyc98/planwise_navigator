"""Measure how often merged work needs a quick follow-up fix.

A follow-up fix is a `fix(...)` commit on main that touches a file a non-fix
commit changed in the previous WINDOW_DAYS. Reverts are near zero in this repo,
so this is the guardrail to watch when review moves from people to automation:
if it rises, review time was moved, not saved.

Usage: python3 scripts/fix_followup_rate.py [--since 2026-06-01] [--window 14]
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

FIX_SUBJECT = re.compile(r"^fix(\([^)]*\))?!?:")
RECORD = "\x1e"


@dataclass
class Commit:
    timestamp: int
    subject: str
    files: set[str] = field(default_factory=set)

    @property
    def is_fix(self) -> bool:
        return bool(FIX_SUBJECT.match(self.subject))

    @property
    def month(self) -> str:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).strftime("%Y-%m")


def load_commits(since: str, branch: str) -> list[Commit]:
    """Return first-parent commits on branch since the date, oldest first."""
    out = subprocess.run(
        [
            "git",
            "log",
            branch,
            "--first-parent",
            f"--since={since}",
            "--reverse",
            "--name-only",
            f"--format={RECORD}%ct\t%s",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    commits = []
    for block in out.split(RECORD)[1:]:
        header, *paths = block.strip("\n").split("\n")
        timestamp, subject = header.split("\t", 1)
        commits.append(Commit(int(timestamp), subject, {p for p in paths if p}))
    return commits


def is_followup(fix: Commit, earlier: list[Commit], window_seconds: int) -> bool:
    """True when a recent non-fix commit touched any file this fix touches."""
    return any(
        not prior.is_fix
        and fix.timestamp - prior.timestamp <= window_seconds
        and prior.files & fix.files
        for prior in earlier
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default="2026-06-01")
    parser.add_argument("--window", type=int, default=14, help="days")
    parser.add_argument("--branch", default="origin/main")
    args = parser.parse_args()

    commits = load_commits(args.since, args.branch)
    window_seconds = args.window * 86_400
    totals: dict[str, int] = defaultdict(int)
    followups: dict[str, int] = defaultdict(int)
    for index, commit in enumerate(commits):
        totals[commit.month] += 1
        if commit.is_fix and is_followup(commit, commits[:index], window_seconds):
            followups[commit.month] += 1

    print(f"{'month':8} {'merged':>6} {'follow-up fixes':>15} {'rate':>6}")
    for month in sorted(totals):
        rate = followups[month] / totals[month]
        print(f"{month:8} {totals[month]:6d} {followups[month]:15d} {rate:6.1%}")


if __name__ == "__main__":
    main()
