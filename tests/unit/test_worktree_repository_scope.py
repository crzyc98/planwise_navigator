"""Repository checks must isolate nested checkouts without weakening root checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "check_worktree_gitlinks.py"
pytestmark = pytest.mark.fast


def git(repo: Path, *args: str, input: str | None = None) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, input=input, text=True
    ).strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--quiet")
    for name in (".gitignore", "pyproject.toml"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    return tmp_path


def run_guard(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD)], cwd=repo, capture_output=True, text=True
    )


def test_guard_checks_index_and_allows_staged_removal(repo: Path) -> None:
    # A gitlink needs no on-disk directory: scan the index, not the filesystem.
    oid = git(repo, "hash-object", "-w", "--stdin", input="fixture\n")
    path = ".worktrees/nested checkout\twith-tab"
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{oid},{path}")
    result = run_guard(repo)
    assert result.returncode == 1
    assert repr(path) in result.stderr
    assert "git rm --cached" in result.stderr

    git(repo, "rm", "--cached", "--", path)
    assert run_guard(repo).returncode == 0


def test_guard_allows_other_submodules_and_ordinary_files(repo: Path) -> None:
    oid = git(repo, "hash-object", "-w", "--stdin", input="fixture\n")
    for mode, path in (
        ("160000", "vendor/intentional-submodule"),
        ("160000", ".worktrees-other/intentional-submodule"),
        ("100644", ".worktrees/ordinary-file.txt"),
    ):
        git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}")
    assert run_guard(repo).returncode == 0


def test_nested_checkout_contents_are_ignored_by_parent_status(repo: Path) -> None:
    nested = repo / ".worktrees" / "future-checkout"
    nested.mkdir(parents=True)
    git(nested, "init", "--quiet")
    (nested / "dirty.py").write_text("value= 1\n")
    assert git(repo, "status", "--porcelain", "--", ".worktrees/") == ""
    assert git(repo, "check-ignore", ".worktrees/future-checkout/dirty.py")
    assert run_guard(repo).returncode == 0


@pytest.mark.parametrize(
    ("tool", "args", "bad_source"),
    [
        ("black", ["--check"], "value= 1\n"),
        ("ruff", ["check"], "import os\n"),
    ],
)
def test_tools_exclude_worktrees_but_check_active_files(
    repo: Path, tool: str, args: list[str], bad_source: str
) -> None:
    nested = repo / ".worktrees" / "future-checkout"
    nested.mkdir(parents=True)
    (nested / "bad.py").write_text(bad_source)
    (repo / "good.py").write_text("value = 1\n")
    command = [sys.executable, "-m", tool, *args]

    # Recursive CI-style checks and explicit pre-commit-style file arguments.
    for target in (".", ".worktrees/future-checkout/bad.py"):
        result = subprocess.run(
            [*command, target], cwd=repo, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr

    (repo / "active_bad.py").write_text(bad_source)
    result = subprocess.run([*command, "."], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "active_bad.py" in result.stdout + result.stderr
