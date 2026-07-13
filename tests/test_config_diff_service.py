"""Tests for effective configuration diffing and provenance."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from _version import __version__
from planalign_api.services import config_diff_service as config_diff_module
from planalign_api.services.config_diff_service import ConfigDiffService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from tests.fixtures.scenario_diff import create_scenario_database


def _service(configs: dict[str, dict], paths: dict[str, object] | None = None):
    storage = MagicMock()
    storage.get_merged_config.side_effect = lambda _, scenario_id: configs[scenario_id]
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda _, scenario_id: ResolvedDatabasePath(
        path=paths.get(scenario_id) if paths else None,
        source="scenario" if paths else None,
    )
    return ConfigDiffService(storage, resolver)


def test_deep_diff_is_sorted_atomic_and_cosmetic_free() -> None:
    configs = {
        "a": {
            "name": "A",
            "simulation": {"growth": 0.03, "seed": 1},
            "tiers": [{"rate": 0.5}],
            "only_a": True,
        },
        "b": {
            "name": "B",
            "simulation": {"growth": 0.05, "seed": 1},
            "tiers": [{"rate": 1.0}],
            "only_b": True,
        },
    }
    result = _service(configs).compare("ws", "a", "b", {"a": "A", "b": "B"})
    paths = [item.path for item in result.differences]
    assert paths == sorted(paths)
    assert "name" not in paths
    assert "tiers" in paths
    assert {item.status for item in result.differences} == {
        "changed",
        "only_a",
        "only_b",
    }
    assert result.unchanged_count == 1


def test_identical_effective_configs_have_no_differences() -> None:
    config = {"simulation": {"growth": 0.03}}
    result = _service({"a": config, "b": config}).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )
    assert result.differences == []
    assert result.unchanged_count == 1


def test_provenance_seed_mismatch_and_mixed_generation(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    a_path = create_scenario_database(
        tmp_path,
        "a",
        metadata=[
            {"timestamp": now - timedelta(days=1), "fingerprint": "1" * 64, "seed": 7},
            {"timestamp": now, "fingerprint": "2" * 64, "seed": 7},
        ],
    )
    b_path = create_scenario_database(
        tmp_path,
        "b",
        metadata=[{"timestamp": now, "fingerprint": "3" * 64, "seed": 8}],
    )
    configs = {
        "a": {"simulation": {"random_seed": 7}},
        "b": {"simulation": {"random_seed": 8}},
    }
    result = _service(configs, {"a": a_path, "b": b_path}).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )
    assert result.seeds_match is False
    assert result.provenance["a"].config_fingerprint == "2" * 12
    assert "mixed_generation" in result.provenance["a"].drift_reasons
    assert result.drift_warning is True


def test_null_simulation_section_does_not_crash(tmp_path) -> None:
    """config_overrides is a loosely-typed Dict[str, Any]; a scenario whose
    merged config has simulation: null (e.g. an override that nulled out the
    base section) must not raise AttributeError when checking the current
    seed against a stored run's seed."""
    now = datetime.now(timezone.utc)
    a_path = create_scenario_database(
        tmp_path,
        "a",
        metadata=[{"timestamp": now, "fingerprint": "1" * 64, "seed": 7}],
    )
    configs = {"a": {"simulation": None}, "b": {"simulation": {"random_seed": 1}}}

    result = _service(configs, {"a": a_path}).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )

    assert result.provenance["a"].available is True
    assert result.provenance["a"].drift_reasons == []


def test_missing_metadata_degrades_gracefully(tmp_path) -> None:
    a_path = create_scenario_database(tmp_path, "a")
    b_path = create_scenario_database(tmp_path, "b")
    result = _service({"a": {}, "b": {}}, {"a": a_path, "b": b_path}).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )
    assert result.seeds_match is None
    assert not result.provenance["a"].available


def test_current_config_and_seed_mismatch_reasons(tmp_path, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    a_path = create_scenario_database(
        tmp_path,
        "a",
        metadata=[
            {
                "timestamp": now,
                "fingerprint": "1" * 64,
                "seed": 7,
                "version": __version__,
            }
        ],
    )
    b_path = create_scenario_database(
        tmp_path,
        "b",
        metadata=[
            {
                "timestamp": now,
                "fingerprint": "2" * 64,
                "seed": 9,
                "version": __version__,
            }
        ],
    )
    monkeypatch.setattr(
        config_diff_module.SimulationConfig,
        "model_validate",
        lambda _: object(),
    )
    monkeypatch.setattr(
        config_diff_module,
        "compute_config_fingerprint",
        lambda _: "f" * 64,
    )
    configs = {
        "a": {"simulation": {"random_seed": 8}},
        "b": {"simulation": {"random_seed": 9}},
    }

    result = _service(configs, {"a": a_path, "b": b_path}).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )

    assert result.provenance["a"].drift_reasons == [
        "current_seed_mismatch",
        "current_config_mismatch",
    ]
    assert result.provenance["b"].drift_reasons == ["current_config_mismatch"]


def test_stale_app_version_suppresses_config_mismatch_false_positive(
    tmp_path, monkeypatch
) -> None:
    """get_merged_config injects backward-compat defaults (employer_match,
    employer_core_contribution) that didn't exist when older scenarios ran,
    which would otherwise always fingerprint as "changed" with no real edit.
    A fingerprint mismatch against a run stamped under an older app version
    must not be reported as current_config_mismatch."""
    now = datetime.now(timezone.utc)
    a_path = create_scenario_database(
        tmp_path,
        "a",
        metadata=[
            {
                "timestamp": now,
                "fingerprint": "1" * 64,
                "seed": 7,
                "version": "0.0.1-legacy",
            }
        ],
    )
    monkeypatch.setattr(
        config_diff_module.SimulationConfig, "model_validate", lambda _: object()
    )
    monkeypatch.setattr(
        config_diff_module, "compute_config_fingerprint", lambda _: "f" * 64
    )
    configs = {"a": {"simulation": {"random_seed": 7}}, "b": {}}

    result = _service(configs, {"a": a_path}).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )

    assert result.provenance["a"].drift_reasons == []
    assert result.provenance["a"].drift_warning is False


def test_full_reset_and_calibration_suppress_mixed_generation(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    paths = {}
    for scenario_id, latest in (
        ("a", {"fingerprint": "2" * 64, "full_reset": True}),
        ("b", {"fingerprint": "3" * 64, "run_type": "calibration"}),
    ):
        paths[scenario_id] = create_scenario_database(
            tmp_path,
            scenario_id,
            metadata=[
                {"timestamp": now - timedelta(days=1), "fingerprint": "1" * 64},
                {"timestamp": now, **latest},
            ],
        )
    result = _service({"a": {}, "b": {}}, paths).compare(
        "ws", "a", "b", {"a": "A", "b": "B"}
    )
    assert "mixed_generation" not in result.provenance["a"].drift_reasons
    assert "mixed_generation" not in result.provenance["b"].drift_reasons


def test_provenance_read_does_not_modify_database(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    paths = {
        scenario_id: create_scenario_database(
            tmp_path,
            scenario_id,
            metadata=[{"timestamp": now, "seed": 42}],
        )
        for scenario_id in ("a", "b")
    }
    before = {
        key: (path.stat().st_size, path.stat().st_mtime_ns)
        for key, path in paths.items()
    }

    _service({"a": {}, "b": {}}, paths).compare("ws", "a", "b", {"a": "A", "b": "B"})

    after = {
        key: (path.stat().st_size, path.stat().st_mtime_ns)
        for key, path in paths.items()
    }
    assert after == before
