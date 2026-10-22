"""Architectural guard for the single canonical construction seam."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CANONICAL_BUILDER = ROOT / "planalign_orchestrator/construction/builder.py"
THIS_TEST = Path(__file__).resolve()


def test_pipeline_orchestrator_is_instantiated_only_by_canonical_builder():
    # Tracked files only: skips venvs, var/, and nested worktrees (full repo
    # copies whose own canonical builders would otherwise register here).
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split("\0")
    violations = []
    for path in (ROOT / name for name in tracked if name):
        if path in {CANONICAL_BUILDER, THIS_TEST} or not path.exists():
            continue
        constructor_token = "PipelineOrchestrator" + "("
        if constructor_token in path.read_text(encoding="utf-8"):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_retired_factory_module_does_not_exist():
    assert not (ROOT / "planalign_orchestrator/factory.py").exists()
