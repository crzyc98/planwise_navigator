"""What changed since a scenario's previous run (#1186).

Every fixture is synthetic and lives under pytest's tmp_path.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from _version import __version__
from planalign_api.models.comparison import RunChangesResponse
from planalign_api.services import run_trust as run_trust_module
from planalign_api.services.comparison_integrity import ComparisonIntegrityService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.run_history import find_previous_run
from tests.test_comparison_integrity import (
    BASE_CONFIG,
    SEEDS,
    _client,
    _evaluate,
    _run,
    _scenario,
    _with,
)

pytestmark = [pytest.mark.fast]

NOW = datetime(2026, 11, 14, 9, 0)


def _metadata(
    resolved: ResolvedDatabasePath,
    started_at: datetime,
    status: str = "completed",
    years: tuple[int, int] = (2026, 2028),
    seed: int = 42,
) -> Path:
    """Write the run_metadata.json the archiver writes (naive local time)."""
    assert resolved.path is not None and resolved.run_id is not None
    run_dir = resolved.path.parent
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": resolved.run_id,
                "started_at": started_at.isoformat(),
                "start_year": years[0],
                "end_year": years[1],
                "seed": seed,
                "status": status,
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _rerun(
    tmp_path: Path, scenario_id: str, previous: dict[str, Any], **current: Any
) -> ResolvedDatabasePath:
    """A selected result plus one earlier completed run of the same scenario."""
    _metadata(
        _run(tmp_path, scenario_id, **previous),
        NOW - timedelta(days=1),
        seed=previous.get("seed", 42),
    )
    selected = _run(tmp_path, scenario_id, **current)
    _metadata(selected, NOW, seed=current.get("seed", 42))
    return selected


def _changes(selected: ResolvedDatabasePath) -> RunChangesResponse:
    resolver = MagicMock()
    resolver.resolve.return_value = selected
    service = ComparisonIntegrityService(MagicMock(), resolver)
    return service.run_changes("ws", "a", "A")


def test_changed_assumption_is_named_with_both_values(tmp_path: Path) -> None:
    selected = _rerun(
        tmp_path,
        "a",
        {},
        config=_with("workforce.total_termination_rate", 0.15),
    )

    result = _changes(selected)

    assert result.has_previous_run
    assert result.previous_run_at is not None
    [change] = result.changes
    assert (change.code, change.path, change.group) == (
        "config_differs",
        "workforce.total_termination_rate",
        "workforce_and_pay",
    )
    assert (change.previous_value, change.current_value) == (0.12, 0.15)
    assert result.unevaluated == []


def test_facts_come_before_assumptions_and_plan_design_last(tmp_path: Path) -> None:
    config = _with("dc_plan.match_cap_percent", 0.06)
    config["workforce"]["total_termination_rate"] = 0.15
    selected = _rerun(tmp_path, "a", {"version": "3.1.0"}, config=config)

    result = _changes(selected)

    assert [(c.code, c.group) for c in result.changes] == [
        ("engine_version_differs", None),
        ("config_differs", "workforce_and_pay"),
        ("config_differs", "plan_design"),
    ]
    assert (result.changes[0].previous_value, result.changes[0].current_value) == (
        "3.1.0",
        __version__,
    )


def test_same_settings_report_no_changes(tmp_path: Path) -> None:
    result = _changes(_rerun(tmp_path, "a", {}))

    assert result.has_previous_run
    assert result.changes == []
    assert result.unevaluated == []


def test_single_retained_run_has_no_previous_run(tmp_path: Path) -> None:
    selected = _run(tmp_path, "a")
    _metadata(selected, NOW)

    result = _changes(selected)

    assert not result.has_previous_run
    assert result.previous_run_at is None
    assert result.changes == []


def test_previous_run_is_latest_completed_run_started_earlier(tmp_path: Path) -> None:
    _metadata(_run(tmp_path, "a"), NOW - timedelta(days=3))
    previous = _metadata(_run(tmp_path, "a", seed=7), NOW - timedelta(days=2))
    _metadata(_run(tmp_path, "a"), NOW - timedelta(days=1), status="failed")
    _metadata(_run(tmp_path, "a"), NOW + timedelta(days=1))
    selected = _metadata(_run(tmp_path, "a"), NOW)

    found = find_previous_run(selected)

    assert found is not None and found.path == previous


def test_previous_run_without_provenance_is_not_claimed_unchanged(
    tmp_path: Path,
) -> None:
    result = _changes(_rerun(tmp_path, "a", {"manifest": False}))

    assert result.has_previous_run
    assert set(result.unevaluated) == {"census", "engine_version", "seed_files"}


def test_assumption_change_adds_a_note_and_keeps_the_verdict(tmp_path: Path) -> None:
    runs = {
        "a": _rerun(tmp_path, "a", {"seed": 7}),
        "b": _run(tmp_path, "b"),
    }

    result = _evaluate(runs)

    verdict = result.scenarios[0]
    assert verdict.verdict == "like_for_like"
    [note] = verdict.reasons
    assert (note.code, note.effect, note.scenario_id) == (
        "changed_since_previous_run",
        "note",
        "a",
    )


def test_plan_design_only_rerun_adds_no_note(tmp_path: Path) -> None:
    runs = {
        "a": _run(tmp_path, "a"),
        "b": _rerun(tmp_path, "b", {}, config=_with("dc_plan.match_cap_percent", 0.06)),
    }

    result = _evaluate(runs)

    assert result.scenarios[0].verdict == "like_for_like"
    assert result.scenarios[0].reasons == []
    assert [c.group for c in _changes(runs["b"]).changes] == ["plan_design"]


def test_previous_run_is_read_without_opening_its_database(
    tmp_path: Path, monkeypatch
) -> None:
    runs = {
        "a": _rerun(tmp_path, "a", {"seed": 7}),
        "b": _rerun(tmp_path, "b", {"config": BASE_CONFIG}),
    }
    opened: list[str] = []
    real_connect = run_trust_module.duckdb.connect

    def counting_connect(path: str, read_only: bool = False) -> Any:
        opened.append(path)
        return real_connect(path, read_only=read_only)

    monkeypatch.setattr(run_trust_module.duckdb, "connect", counting_connect)
    _evaluate(runs)

    assert sorted(opened) == sorted(str(run.path) for run in runs.values())


def test_endpoint_reports_changes_and_unknown_scenario(tmp_path: Path) -> None:
    selected = _rerun(
        tmp_path, "a", {}, config=_with("workforce.total_termination_rate", 0.15)
    )
    storage = MagicMock()
    storage.get_workspace.return_value = MagicMock(id="ws")
    storage.get_scenario.side_effect = lambda _, scenario_id: (
        _scenario(scenario_id) if scenario_id == "a" else None
    )
    resolver = MagicMock()
    resolver.resolve.return_value = selected
    client = _client(storage, ComparisonIntegrityService(storage, resolver))

    body = client.get("/api/workspaces/ws/scenarios/a/run-changes").json()
    missing = client.get("/api/workspaces/ws/scenarios/z/run-changes")

    assert body["has_previous_run"] is True
    assert body["scenario_name"] == "A"
    assert body["changes"][0]["previous_value"] == 0.12
    assert missing.status_code == 404


def test_legacy_result_has_no_previous_run(tmp_path: Path) -> None:
    result = _changes(
        ResolvedDatabasePath(path=tmp_path / "x.duckdb", source="scenario")
    )

    assert not result.has_previous_run


def test_engine_upgrade_alone_adds_no_note_but_is_listed(tmp_path: Path) -> None:
    runs = {
        "a": _rerun(tmp_path, "a", {"version": "3.1.0"}),
        "b": _run(tmp_path, "b"),
    }

    result = _evaluate(runs)

    assert result.scenarios[0].verdict == "like_for_like"
    assert result.scenarios[0].reasons == []
    assert [c.code for c in _changes(runs["a"]).changes] == ["engine_version_differs"]


def test_seed_table_change_is_listed_with_file_names(tmp_path: Path) -> None:
    changed = {**SEEDS, "config_job_levels.csv": "e" * 64}
    selected = _rerun(tmp_path, "a", {}, seeds=changed)

    [change] = _changes(selected).changes

    assert (change.code, change.files) == (
        "seed_files_differ",
        ["config_job_levels.csv"],
    )


def test_selected_run_files_are_read_once_per_request(
    tmp_path: Path, monkeypatch
) -> None:
    from planalign_api.services import comparison_integrity as service_module

    runs = {
        "a": _rerun(tmp_path, "a", {"seed": 7}),
        "b": _rerun(tmp_path, "b", {}),
    }
    manifests: list[str] = []
    configs: list[str] = []
    real_manifest = service_module.read_run_manifest
    real_config = service_module.read_run_config

    def counting_manifest(run_dir: Path) -> Any:
        manifests.append(run_dir.name)
        return real_manifest(run_dir)

    def counting_config(path: Path | None) -> Any:
        configs.append(path.parent.name if path else "")
        return real_config(path)

    monkeypatch.setattr(service_module, "read_run_manifest", counting_manifest)
    monkeypatch.setattr(service_module, "read_run_config", counting_config)
    _evaluate(runs)

    # Each run directory (two selected, two previous) is read exactly once.
    assert len(manifests) == len(set(manifests)) == 4
    assert len(configs) == len(set(configs)) == 4
