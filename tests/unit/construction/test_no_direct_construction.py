"""Architectural guard for the single canonical construction seam."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANONICAL_BUILDER = ROOT / "planalign_orchestrator/construction/builder.py"
THIS_TEST = Path(__file__).resolve()


def test_pipeline_orchestrator_is_instantiated_only_by_canonical_builder():
    violations = []
    for path in ROOT.rglob("*.py"):
        if path in {CANONICAL_BUILDER, THIS_TEST} or any(
            part in {".venv", "var", ".git"} for part in path.parts
        ):
            continue
        constructor_token = "PipelineOrchestrator" + "("
        if constructor_token in path.read_text(encoding="utf-8"):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_retired_factory_module_does_not_exist():
    assert not (ROOT / "planalign_orchestrator/factory.py").exists()
