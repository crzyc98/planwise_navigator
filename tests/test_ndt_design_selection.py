"""Selected design must isolate current operands and prior classification pay."""

from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.ndt_service import NDTService
from tests.test_ndt_415 import _create_test_db, _insert_employee


@pytest.fixture
def selected_archive(tmp_path: Path) -> tuple[NDTService, Path]:
    path = tmp_path / "designs.duckdb"
    with duckdb.connect(str(path)) as conn:
        _create_test_db(conn)
        for year in (2024, 2025):
            for employee, pay in (("H", 200000), ("N", 100000)):
                _insert_employee(
                    conn,
                    employee,
                    year,
                    pay,
                    pay,
                    contributions=4000,
                    match_amount=2000,
                    core_amount=1000,
                )
        conn.execute(
            "ALTER TABLE fct_workforce_snapshot ADD COLUMN scenario_id VARCHAR DEFAULT 'configured'"
        )
        conn.execute(
            "ALTER TABLE fct_workforce_snapshot ADD COLUMN plan_design_id VARCHAR DEFAULT 'A'"
        )
        conn.execute(
            "INSERT INTO fct_workforce_snapshot SELECT * REPLACE ('B' AS plan_design_id, -1.0 AS prorated_annual_contributions, -1.0 AS employer_match_amount, -1.0 AS employer_core_amount) FROM fct_workforce_snapshot"
        )
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    return NDTService(Mock(), db_resolver=resolver), path


@pytest.mark.parametrize("kind", ["adp", "acp", "415", "401a4"])
def test_selected_design_ignores_other_design_invalid_operands(
    selected_archive, kind: str
) -> None:
    service, path = selected_archive
    result = getattr(service, f"run_{kind}_test")(
        "w", "studio", "test", 2025, plan_design_id="A", include_employees=True
    )
    assert result.test_result in ("pass", "unavailable"), result.test_message
    assert result.plan_design_id == "A"
    assert result.scenario_id == "studio"
    assert sorted(row.employee_id for row in result.employees) == ["H", "N"]
    with duckdb.connect(str(path), read_only=True) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot").fetchone()[0]
            == 8
        )
    unselected = getattr(service, f"run_{kind}_test")("w", "studio", "test", 2025)
    assert unselected.test_result == "error"


@pytest.mark.parametrize("design", ["missing", "A' OR TRUE --", " "])
def test_absent_or_invalid_design_is_not_a_population(
    selected_archive, design: str
) -> None:
    service, _ = selected_archive
    result = service.run_adp_test("w", "studio", "test", 2025, plan_design_id=design)
    assert result.test_result == "error"


def test_selected_years_and_safe_harbor_are_not_borrowed(selected_archive) -> None:
    service, _ = selected_archive
    assert service.get_available_years("w", "studio", plan_design_id="A").years == [
        2024,
        2025,
    ]
    assert (
        service.get_available_years("w", "studio", plan_design_id="absent").years == []
    )
    result = service.run_adp_test(
        "w", "studio", "test", 2025, plan_design_id="A", safe_harbor=True
    )
    assert result.test_result == "error"
    assert "safe harbor" in result.test_message


@pytest.mark.parametrize("source", ["workspace", "project"])
def test_shared_fallback_cannot_supply_selected_design(
    selected_archive, source: str
) -> None:
    service, path = selected_archive
    service.db_resolver.resolve.return_value = ResolvedDatabasePath(
        path=path, source=source
    )
    result = service.run_adp_test("w", "studio", "test", 2025, plan_design_id="A")
    assert result.test_result == "error"


@pytest.mark.parametrize("kind", ["adp", "acp", "415", "401a4"])
def test_route_forwards_explicit_selector(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from planalign_api.routers import ndt

    monkeypatch.setattr(ndt, "has_selected_result", lambda *args: True)
    storage = Mock()
    storage.get_scenario.return_value.name = "synthetic"
    storage.get_scenario.return_value.status = "completed"
    service = Mock()
    model = {
        "adp": "ADPScenarioResult",
        "acp": "ACPScenarioResult",
        "415": "Section415ScenarioResult",
        "401a4": "Section401a4ScenarioResult",
    }[kind]
    from planalign_api.services import ndt_service

    getattr(service, f"run_{kind}_test").return_value = getattr(ndt_service, model)(
        scenario_id="s",
        scenario_name="synthetic",
        simulation_year=2025,
        test_result="error",
        plan_design_id="A",
    )
    options = {
        "adp": {"safe_harbor": False, "testing_method": "current"},
        "401a4": {"include_match": False},
        "415": {"warning_threshold": 0.95},
        "acp": {},
    }[kind]
    getattr(ndt, f"run_{kind}_test")(
        "w",
        scenarios="s",
        year=2025,
        include_employees=False,
        plan_design_id="A",
        storage=storage,
        ndt_service=service,
        **options,
    )
    assert (
        getattr(service, f"run_{kind}_test").call_args.kwargs["plan_design_id"] == "A"
    )


@pytest.mark.parametrize("kind", ["adp", "acp", "415", "401a4"])
def test_unknown_design_is_checked_before_filtering_only_used_history(
    selected_archive: tuple[NDTService, Path], kind: str
) -> None:
    service, path = selected_archive
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "UPDATE fct_workforce_snapshot SET plan_design_id=NULL WHERE simulation_year=2024"
        )
    result = getattr(service, f"run_{kind}_test")(
        "w", "studio", "test", 2025, plan_design_id="A"
    )
    if kind == "415":
        assert result.test_result == "pass"
    else:
        assert result.test_result == "error"
        assert "unknown plan_design_id" in result.test_message


@pytest.mark.parametrize("kind", ["adp", "acp", "415", "401a4"])
def test_archived_config_identity_must_match_snapshot(
    selected_archive: tuple[NDTService, Path], kind: str, tmp_path: Path
) -> None:
    service, path = selected_archive
    config = tmp_path / "config.yaml"
    config.write_text("scenario_id: different\n")
    service.db_resolver.resolve.return_value = ResolvedDatabasePath(
        path=path, source="run", run_id="frozen", config_path=config
    )
    result = getattr(service, f"run_{kind}_test")(
        "w", "studio", "test", 2025, plan_design_id="A"
    )
    assert result.test_result == "error"
    assert "does not match archived configuration" in result.test_message
    config.write_text("scenario_id: configured\n")
    result = getattr(service, f"run_{kind}_test")(
        "w", "studio", "test", 2025, plan_design_id="A"
    )
    assert result.test_result in ("pass", "unavailable"), result.test_message


@pytest.mark.parametrize(
    "family,global_status,expected",
    [
        ("age_banded", "flat", True),
        ("flat", "age_banded", False),
        (None, "age_banded", True),
    ],
)
@pytest.mark.parametrize("only_nhce", [False, True])
def test_401a4_diagnostic_uses_selected_archive_and_design(
    selected_archive: tuple[NDTService, Path],
    tmp_path: Path,
    family: str | None,
    global_status: str,
    expected: bool,
    only_nhce: bool,
) -> None:
    import yaml

    service, path = selected_archive
    if only_nhce:
        with duckdb.connect(str(path)) as conn:
            conn.execute(
                "UPDATE fct_workforce_snapshot SET current_compensation=100000"
            )
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        yaml.safe_dump(
            {
                "scenario_id": "configured",
                "employer_core_contribution": {"status": global_status},
                "plan_design_parameters": {"A": {"employer_core": {"family": family}}},
            }
        )
    )
    second.write_text(
        "scenario_id: configured\nemployer_core_contribution:\n  status: age_banded\n"
    )
    service.db_resolver.resolve.side_effect = [
        ResolvedDatabasePath(path=path, source="run", config_path=config)
        for config in (first, second)
    ]
    result = service.run_401a4_test(
        "w", "studio", "Synthetic", 2025, plan_design_id="A"
    )
    assert result.test_result == "unavailable"
    assert result.service_risk_flag is expected
    assert service.db_resolver.resolve.call_count == 1
    service.storage.get_merged_config.assert_not_called()


def test_year_discovery_keeps_design_choices_when_scoped(
    selected_archive: tuple[NDTService, Path],
) -> None:
    service, path = selected_archive
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "DELETE FROM fct_workforce_snapshot WHERE plan_design_id='B' AND simulation_year=2024"
        )
    result = service.get_available_years("w", "studio", plan_design_id="B")
    assert result.years == [2025]
    assert result.plan_design_ids == ["A", "B"]
    absent = service.get_available_years("w", "studio", plan_design_id="missing")
    assert absent.years == []
    assert absent.plan_design_ids == ["A", "B"]
    service.db_resolver.resolve.return_value = ResolvedDatabasePath(
        path=path, source="project"
    )
    assert service.get_available_years("w", "studio").plan_design_ids == []


def test_legacy_year_discovery_has_no_design_candidates(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    with duckdb.connect(str(path)) as conn:
        _create_test_db(conn)
        _insert_employee(conn, "N", 2025, 100000, 100000)
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    result = NDTService(Mock(), db_resolver=resolver).get_available_years("w", "s")
    assert result.years == [2025]
    assert result.plan_design_ids == []
