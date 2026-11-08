"""Claude Code PostToolUse hook: lint the file Claude just edited.

Runs the same linters CI runs (ruff check for Python, eslint for Studio) on the
edited file only. Exit code 2 sends the lint output back to Claude to fix.
Missing tools are skipped silently so the hook never blocks a fresh checkout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDIO = ROOT / "planalign_studio"
STUDIO_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}


def lint_command(path: Path) -> tuple[list[str], Path] | None:
    """Return the lint command and its working directory, or None to skip."""
    if path.suffix == ".py":
        ruff = ROOT / ".venv" / "bin" / "ruff"
        return ([str(ruff), "check", str(path)], ROOT) if ruff.exists() else None
    if path.suffix in STUDIO_SUFFIXES and STUDIO in path.parents:
        eslint = STUDIO / "node_modules" / ".bin" / "eslint"
        if not eslint.exists():
            return None
        return ([str(eslint), "--max-warnings", "0", str(path)], STUDIO)
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path")
    if not file_path:
        return 0
    path = Path(file_path).resolve()
    if not path.exists() or ROOT not in path.parents:
        return 0
    command = lint_command(path)
    if command is None:
        return 0
    args, cwd = command
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return 0
    print(
        f"Lint failed for {path.relative_to(ROOT)}:\n{result.stdout}{result.stderr}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
