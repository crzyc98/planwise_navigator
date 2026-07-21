"""Product wrapper delegation and wiring tests."""

from pathlib import Path
from types import SimpleNamespace

from planalign_cli.integration import orchestrator_wrapper as wrapper_module
from planalign_cli.integration.orchestrator_wrapper import OrchestratorWrapper
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import InitializationPolicy


def test_wrapper_delegates_to_canonical_builder(monkeypatch, tmp_path):
    config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
    wrapper = OrchestratorWrapper(
        Path("tests/fixtures/invariant_config.yaml"),
        tmp_path / "run.duckdb",
        dbt_project_dir=tmp_path / "overlay",
    )
    wrapper._config = config
    sentinel = SimpleNamespace()
    captured = {}

    def fake_build(spec):
        captured["spec"] = spec
        return SimpleNamespace(orchestrator=sentinel, signature=object())

    monkeypatch.setattr(wrapper_module, "build_orchestrator", fake_build, raising=False)

    result = wrapper.create_orchestrator(threads=1)

    assert result is sentinel
    spec = captured["spec"]
    assert spec.config is config
    assert spec.database is wrapper.db
    assert spec.threads == 1
    assert spec.dbt_project_dir == tmp_path / "overlay"
    assert spec.initialization is InitializationPolicy.NONE
    assert spec.entry_point == "cli.simulate"


def test_wrapper_preserves_progress_adapter(monkeypatch, tmp_path):
    wrapper = OrchestratorWrapper(
        Path("tests/fixtures/invariant_config.yaml"),
        tmp_path / "run.duckdb",
    )
    orchestrator = SimpleNamespace()
    monkeypatch.setattr(
        wrapper_module,
        "build_orchestrator",
        lambda _spec: SimpleNamespace(orchestrator=orchestrator, signature=object()),
        raising=False,
    )

    callback = object()
    result = wrapper.create_orchestrator(progress_callback=callback)

    assert isinstance(result, wrapper_module.ProgressAwareOrchestrator)
    assert result.orchestrator is orchestrator
    assert result.progress_callback is callback
