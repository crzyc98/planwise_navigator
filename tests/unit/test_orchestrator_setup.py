"""Unit tests for planalign_orchestrator.orchestrator_setup."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from planalign_orchestrator import orchestrator_setup


def _parallel_config() -> MagicMock:
    """Config mock with model parallelization enabled and no resource mgmt."""
    config = MagicMock()
    threading = config.orchestrator.threading
    threading.parallelization.enabled = True
    threading.parallelization.max_workers = 2
    threading.parallelization.deterministic_execution = True
    threading.resource_management = None  # skip resource-manager branch
    return config


@pytest.mark.fast
class TestSetupParallelization:
    def test_dependency_analyzer_gets_project_dir_not_manifest_path(
        self, tmp_path, monkeypatch
    ):
        """ModelDependencyAnalyzer must receive the dbt project root (Path('dbt')),
        not the manifest file path — it resolves <project>/target/manifest.json
        itself (regression guard for #344)."""
        # Real relative path the code checks: <cwd>/dbt/target/manifest.json
        manifest = tmp_path / "dbt" / "target" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}")
        monkeypatch.chdir(tmp_path)

        with patch.object(
            orchestrator_setup, "MODEL_PARALLELIZATION_AVAILABLE", True
        ), patch.object(
            orchestrator_setup, "ModelDependencyAnalyzer"
        ) as mock_analyzer, patch.object(
            orchestrator_setup, "ParallelExecutionEngine"
        ):
            (
                engine,
                parallel_cfg,
                resource_manager,
                analyzer,
                enabled,
            ) = orchestrator_setup.setup_parallelization(
                _parallel_config(), MagicMock(), verbose=False
            )

        mock_analyzer.assert_called_once_with(Path("dbt"))
        assert enabled is True
        assert resource_manager is None
        assert analyzer is mock_analyzer.return_value

    def test_returns_disabled_when_manifest_missing(self, tmp_path, monkeypatch):
        """No manifest -> parallelization disabled, analyzer never constructed."""
        monkeypatch.chdir(tmp_path)  # no dbt/target/manifest.json here

        with patch.object(
            orchestrator_setup, "MODEL_PARALLELIZATION_AVAILABLE", True
        ), patch.object(orchestrator_setup, "ModelDependencyAnalyzer") as mock_analyzer:
            result = orchestrator_setup.setup_parallelization(
                _parallel_config(), MagicMock(), verbose=False
            )

        assert result == (None, None, None, None, False)
        mock_analyzer.assert_not_called()
