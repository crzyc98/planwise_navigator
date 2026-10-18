"""Reject nested development worktree gitlinks in the prospective commit index."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
    gitlinks = []
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        if metadata.split()[0] == b"160000" and path.startswith(b".worktrees/"):
            gitlinks.append(path.decode(errors="backslashreplace"))
    if not gitlinks:
        return 0
    print("Nested .worktrees/ gitlinks must not be committed:", file=sys.stderr)
    for path in gitlinks:
        print(f"  {path!r}", file=sys.stderr)
    print(
        "Remove each from the index with git rm --cached -- <path>; "
        "keep the local directory.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
