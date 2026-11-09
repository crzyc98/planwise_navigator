"""Find merged PRs that shipped a bug, as candidate cases for review_eval.py.

A candidate is a `fix` commit on main where most of the lines it removed were
added by one earlier PR (the "intro"). That is the same check used to confirm
the cases in review_eval_cases.json. A person still writes the one-line bug
description before a candidate becomes a case.

Usage: python3 scripts/review_eval_candidates.py [--since 2026-09-01] [--markdown]
Stdlib only, so CI can run it without installing the project.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "scripts" / "review_eval_cases.json"
FIX_SUBJECT = re.compile(r"^fix(\([^)]*\))?!?:")
SKIP_PATH = re.compile(r"test|CHANGELOG|\.md$|suppressions|\.lock$|package-lock")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? ")
MIN_REMOVED = 5  # fewer removed lines is too little evidence
MIN_OVERLAP = 0.6  # share of removed lines the intro PR added
MAX_INTRO_LINES = 1600  # larger diffs are too big to review in one eval run


@dataclass(frozen=True)
class Candidate:
    fix: str
    fix_subject: str
    intro: str
    intro_subject: str
    overlap: float
    removed: int


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def removed_lines(fix: str) -> dict[str, list[tuple[int, int]]]:
    """Map each non-test file to the (start, count) hunks the fix removed or changed."""
    hunks: dict[str, list[tuple[int, int]]] = {}
    current = ""
    for line in git("diff", "-U0", f"{fix}^", fix).splitlines():
        if line.startswith("--- a/"):
            current = "" if SKIP_PATH.search(line) else line[6:]
        match = HUNK.match(line)
        if current and match and int(match.group(2) or 1) > 0:
            hunks.setdefault(current, []).append(
                (int(match.group(1)), int(match.group(2) or 1))
            )
    return hunks


def blame_counts(fix: str) -> Counter[str]:
    """Count which commit last touched each line the fix removed."""
    counts: Counter[str] = Counter()
    for path, hunks in removed_lines(fix).items():
        for start, count in hunks:
            out = git("blame", "-l", "-s", f"-L{start},+{count}", f"{fix}^", "--", path)
            counts.update(row.split()[0].lstrip("^") for row in out.splitlines())
    return counts


def changed_line_count(sha: str) -> int:
    numbers = re.findall(
        r"(\d+) (?:insertion|deletion)", git("diff", "--shortstat", f"{sha}^", sha)
    )
    return sum(int(n) for n in numbers)


def candidate_for(fix: str, subject: str) -> Candidate | None:
    counts = blame_counts(fix)
    removed = sum(counts.values())
    if removed < MIN_REMOVED:
        return None
    intro, hits = counts.most_common(1)[0]
    if hits / removed < MIN_OVERLAP or changed_line_count(intro) > MAX_INTRO_LINES:
        return None
    intro_subject = git("log", "-1", "--format=%s", intro).strip()
    return Candidate(
        fix[:8], subject, intro[:8], intro_subject, hits / removed, removed
    )


def known_fixes() -> set[str]:
    spec = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    return {bug["fix"][:8] for case in spec["cases"] for bug in case["bugs"]}


def find_candidates(since: str) -> list[Candidate]:
    known = known_fixes()
    log = git(
        "log", "origin/main", "--first-parent", f"--since={since}", "--format=%H\t%s"
    )
    found = []
    for row in log.splitlines():
        sha, subject = row.split("\t", 1)
        if FIX_SUBJECT.match(subject) and sha[:8] not in known:
            candidate = candidate_for(sha, subject)
            if candidate:
                found.append(candidate)
    return found


def as_markdown(candidates: list[Candidate]) -> str:
    lines = [
        "Merged fixes whose bug traces back to one earlier PR. To add one to "
        "`scripts/review_eval_cases.json`, confirm the bug and write a one-line description.",
        "",
        "| Fix | Introduced by | Overlap |",
        "| --- | --- | --- |",
    ]
    for c in candidates:
        lines.append(
            f"| {c.fix} {c.fix_subject} | {c.intro} {c.intro_subject} | "
            f"{c.overlap:.0%} of {c.removed} lines |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default="60 days ago")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    candidates = find_candidates(args.since)
    if args.markdown:
        print(as_markdown(candidates) if candidates else "", end="")
        return
    for c in candidates:
        print(f"{c.fix} <- {c.intro} ({c.overlap:.0%} of {c.removed}): {c.fix_subject}")


if __name__ == "__main__":
    main()
