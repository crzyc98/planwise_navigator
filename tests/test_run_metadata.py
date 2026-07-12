"""
Unit tests for run provenance stamping and config drift detection (Feature 109).

Covers:
- compute_config_fingerprint determinism and sensitivity (T002)
- run_metadata table lifecycle: lazy DDL, schema, append-only (T004)
- check_and_record_run state machine and messaging (T006)
- seed-distinct drift messaging (T011)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.run_metadata import (
    RUN_METADATA_TABLE,
    DriftCheckResult,
    DriftStatus,
    check_and_record_run,
    compute_config_fingerprint,
)
from planalign_orchestrator.utils import DatabaseConnectionManager

pytestmark = [pytest.mark.fast, pytest.mark.unit]

LOGGER_NAME = "planalign_orchestrator.run_metadata"


@pytest.fixture
def db_manager(tmp_path: Path) -> DatabaseConnectionManager:
    return DatabaseConnectionManager(db_path=tmp_path / "run_meta.duckdb")


def _stamp(db_manager, config, **overrides) -> DriftCheckResult:
    kwargs = dict(start_year=2025, end_year=2026, run_type="simulate")
    kwargs.update(overrides)
    return check_and_record_run(db_manager, config, **kwargs)


def _rows(db_manager) -> list[tuple]:
    with db_manager.get_connection() as conn:
        return conn.execute(
            f"SELECT * FROM {RUN_METADATA_TABLE} ORDER BY run_timestamp"
        ).fetchall()


# ---------------------------------------------------------------------------
# T002: compute_config_fingerprint
# ---------------------------------------------------------------------------


class TestConfigFingerprint:
    def test_identical_configs_produce_identical_hash(self, minimal_config):
        copy = minimal_config.model_copy(deep=True)
        assert compute_config_fingerprint(minimal_config) == compute_config_fingerprint(
            copy
        )

    def test_fingerprint_is_sha256_hex(self, minimal_config):
        fp = compute_config_fingerprint(minimal_config)
        assert len(fp) == 64
        int(fp, 16)  # raises ValueError if not hex

    def test_result_affecting_change_changes_hash(self, minimal_config):
        baseline = compute_config_fingerprint(minimal_config)
        changed = minimal_config.model_copy(deep=True)
        changed.simulation.target_growth_rate = (
            float(changed.simulation.target_growth_rate or 0.03) + 0.01
        )
        assert compute_config_fingerprint(changed) != baseline

    def test_seed_change_does_not_change_hash(self, minimal_config):
        baseline = compute_config_fingerprint(minimal_config)
        reseeded = minimal_config.model_copy(deep=True)
        reseeded.simulation.random_seed = 99999
        assert compute_config_fingerprint(reseeded) == baseline

    def test_non_result_affecting_setup_change_does_not_change_hash(
        self, minimal_config
    ):
        baseline = compute_config_fingerprint(minimal_config)
        toggled = minimal_config.model_copy(deep=True)
        # Mutate only the clear flags in place: setup also carries
        # result-affecting keys (census path, plan-year dates) that DO
        # legitimately flow into the fingerprint via to_dbt_vars.
        setup = dict(getattr(toggled, "setup", None) or {})
        setup["clear_tables"] = not setup.get("clear_tables", False)
        setup["clear_mode"] = "all"
        toggled.setup = setup
        assert compute_config_fingerprint(toggled) == baseline

    def test_decimal_fields_serialize_deterministically(
        self, config_with_decimal_fields
    ):
        copy = config_with_decimal_fields.model_copy(deep=True)
        assert compute_config_fingerprint(
            config_with_decimal_fields
        ) == compute_config_fingerprint(copy)


# ---------------------------------------------------------------------------
# T004: run_metadata table lifecycle
# ---------------------------------------------------------------------------


class TestTableLifecycle:
    def test_table_created_lazily_on_first_stamp(self, db_manager, minimal_config):
        _stamp(db_manager, minimal_config)
        with db_manager.get_connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='main' AND table_name=?",
                [RUN_METADATA_TABLE],
            ).fetchone()
        assert exists is not None

    def test_schema_matches_contract(self, db_manager, minimal_config):
        _stamp(db_manager, minimal_config)
        with db_manager.get_connection() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='main' AND table_name=?",
                    [RUN_METADATA_TABLE],
                ).fetchall()
            }
        assert columns == {
            "run_id",
            "run_timestamp",
            "run_type",
            "config_fingerprint",
            "random_seed",
            "start_year",
            "end_year",
            "scenario_id",
            "plan_design_id",
            "planalign_version",
            "full_reset",
        }

    def test_second_stamp_appends_and_retains_first(self, db_manager, minimal_config):
        _stamp(db_manager, minimal_config)
        _stamp(db_manager, minimal_config)
        rows = _rows(db_manager)
        assert len(rows) == 2

    def test_table_name_survives_full_reset_patterns(self):
        # maybe_full_reset clears tables starting with these prefixes;
        # run_metadata must match neither so history survives clean reruns.
        assert not RUN_METADATA_TABLE.startswith("int_")
        assert not RUN_METADATA_TABLE.startswith("fct_")


# ---------------------------------------------------------------------------
# T006: check_and_record_run state machine
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_no_history_is_info_not_warning(self, db_manager, minimal_config, caplog):
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            result = _stamp(db_manager, minimal_config)
        assert result.status is DriftStatus.NO_HISTORY
        assert not result.config_changed
        assert not result.seed_changed
        assert all(rec.levelno < logging.WARNING for rec in caplog.records)
        assert len(_rows(db_manager)) == 1

    def test_match_is_silent(self, db_manager, minimal_config, caplog):
        _stamp(db_manager, minimal_config)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            result = _stamp(db_manager, minimal_config)
        assert result.status is DriftStatus.MATCH
        assert caplog.records == []
        assert len(_rows(db_manager)) == 2

    def test_config_drift_warns_with_remedies(self, db_manager, minimal_config, caplog):
        _stamp(db_manager, minimal_config)
        changed = minimal_config.model_copy(deep=True)
        changed.simulation.target_growth_rate = (
            float(changed.simulation.target_growth_rate or 0.03) + 0.01
        )
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            result = _stamp(db_manager, changed)
        assert result.status is DriftStatus.DRIFT
        assert result.config_changed
        assert not result.seed_changed
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "configuration" in message
        # FR-010 remedies: isolated/fresh DB and clean rerun
        assert "isolated" in message or "fresh" in message
        assert "clear_tables" in message
        # prior run timestamp shown
        assert str(result.prior_timestamp.year) in message

    def test_drift_result_carries_fingerprints(self, db_manager, minimal_config):
        first = _stamp(db_manager, minimal_config)
        changed = minimal_config.model_copy(deep=True)
        changed.simulation.target_growth_rate = 0.123
        second = _stamp(db_manager, changed)
        assert second.prior_fingerprint == first.current_fingerprint
        assert second.current_fingerprint != second.prior_fingerprint

    def test_full_reset_downgrades_to_info(self, db_manager, minimal_config, caplog):
        _stamp(db_manager, minimal_config)
        changed = minimal_config.model_copy(deep=True)
        changed.simulation.target_growth_rate = 0.123
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            result = _stamp(db_manager, changed, full_reset=True)
        assert result.status is DriftStatus.DRIFT
        assert result.suppressed_by_full_reset
        assert all(rec.levelno < logging.WARNING for rec in caplog.records)

    def test_calibration_run_type_downgrades_to_info(
        self, db_manager, minimal_config, caplog
    ):
        _stamp(db_manager, minimal_config)
        changed = minimal_config.model_copy(deep=True)
        changed.simulation.target_growth_rate = 0.123
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            result = _stamp(db_manager, changed, run_type="calibration")
        assert result.status is DriftStatus.DRIFT
        assert all(rec.levelno < logging.WARNING for rec in caplog.records)

    def test_duckdb_error_degrades_to_unknown(self, minimal_config, caplog):
        class BrokenManager:
            @contextmanager
            def get_connection(self):
                raise duckdb.InvalidInputException("simulated failure")
                yield  # pragma: no cover

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            result = _stamp(BrokenManager(), minimal_config)
        assert result.status is DriftStatus.UNKNOWN
        assert result.current_fingerprint  # fingerprint still computed
        assert all(rec.levelno < logging.WARNING for rec in caplog.records)
        assert any("drift" in rec.getMessage().lower() for rec in caplog.records)

    def test_record_fields_populated(self, db_manager, minimal_config):
        _stamp(
            db_manager, minimal_config, run_type="batch", start_year=2025, end_year=2027
        )
        with db_manager.get_connection() as conn:
            row = conn.execute(
                f"SELECT run_type, random_seed, start_year, end_year, scenario_id, "
                f"plan_design_id, full_reset FROM {RUN_METADATA_TABLE}"
            ).fetchone()
        assert row == ("batch", 42, 2025, 2027, "test_scenario", "test_plan", False)


# ---------------------------------------------------------------------------
# T011 (US2): seed changes called out distinctly
# ---------------------------------------------------------------------------


class TestSeedDistinctMessaging:
    def test_seed_only_change_names_seed_with_values(
        self, db_manager, minimal_config, caplog
    ):
        _stamp(db_manager, minimal_config)  # seed 42
        reseeded = minimal_config.model_copy(deep=True)
        reseeded.simulation.random_seed = 4242
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            result = _stamp(db_manager, reseeded)
        assert result.status is DriftStatus.DRIFT
        assert result.seed_changed
        assert not result.config_changed
        assert result.prior_seed == 42
        assert result.current_seed == 4242
        message = next(
            r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
        )
        assert "seed" in message.lower()
        assert "42" in message and "4242" in message
        assert "configuration changed" not in message.lower()

    def test_seed_and_config_change_reports_both(
        self, db_manager, minimal_config, caplog
    ):
        _stamp(db_manager, minimal_config)
        changed = minimal_config.model_copy(deep=True)
        changed.simulation.random_seed = 4242
        changed.simulation.target_growth_rate = 0.123
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            result = _stamp(db_manager, changed)
        assert result.config_changed and result.seed_changed
        message = next(
            r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
        )
        assert "seed" in message.lower()
        assert "configuration" in message.lower()


# ---------------------------------------------------------------------------
# T010 (US1): CalibrationRunner wiring
# ---------------------------------------------------------------------------


class TestCalibrationWiring:
    def test_run_calibration_stamps_with_calibration_run_type(
        self, tmp_path, monkeypatch
    ):
        import planalign_orchestrator.calibration_runner as cal

        db_path = tmp_path / "calibration.duckdb"
        duckdb.connect(str(db_path)).close()  # existing file target

        monkeypatch.setattr(cal, "verify_dc_prerequisites", lambda path: None)
        calls: list[dict] = []

        def spy(db_manager, config, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(cal, "check_and_record_run", spy)

        runner = cal.CalibrationRunner(
            cal.CalibrationRun(start_year=2025, end_year=2026, database_path=db_path)
        )
        monkeypatch.setattr(runner, "_build_all_years", lambda: [])
        runner.run_calibration()

        assert len(calls) == 1
        assert calls[0]["run_type"] == "calibration"
        assert calls[0]["start_year"] == 2025
        assert calls[0]["end_year"] == 2026
