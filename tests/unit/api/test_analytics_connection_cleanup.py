"""Analytics connections release resources without relying on finalization."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from planalign_api.services.analytics_service import AnalyticsService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.ndt_service import NDTService

METHODS = (
    "get_dc_plan_analytics",
    "get_available_years",
    "run_acp_test",
    "run_adp_test",
    "run_401a4_test",
    "run_415_test",
)
NDT_TESTS = METHODS[2:]


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "analytics.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE lock_probe (value INTEGER)")
    return path


@pytest.fixture
def retained_connection(database_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    conn = duckdb.connect(str(database_path), read_only=True)
    yield conn
    conn.close()


def _call_service(method: str, path: Path) -> object:
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    if method == "get_dc_plan_analytics":
        service = AnalyticsService(MagicMock(), db_resolver=resolver)
        # Some analytics helpers intentionally swallow query errors; force an
        # unexpected helper failure to exercise the outer exception handler.
        with patch.object(
            service,
            "_resolve_first_simulation_year",
            side_effect=RuntimeError("injected failure"),
        ):
            return service.get_dc_plan_analytics("ws", "sc", "Scenario")
    ndt = NDTService(MagicMock(), db_resolver=resolver)
    if method == "get_available_years":
        return ndt.get_available_years("ws", "sc")
    return getattr(ndt, method)("ws", "sc", "Scenario", 2025)


def _assert_closed(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        conn.execute("SELECT 1")


@pytest.mark.parametrize("method", METHODS)
def test_failure_closes_retained_connection(
    method: str, database_path: Path, retained_connection: duckdb.DuckDBPyConnection
) -> None:
    with patch("duckdb.connect", return_value=retained_connection) as connect:
        result = _call_service(method, database_path)
    connect.assert_called_once_with(str(database_path), read_only=True)
    if method == "get_dc_plan_analytics":
        assert result is None
    elif method == "get_available_years":
        assert result.years == []
        assert result.default_year is None
    else:
        assert result.test_result == "error"
        # Input validation reads the snapshot before any IRS-limit lookup.
        assert "fct_workforce_snapshot does not exist" in result.test_message
    _assert_closed(retained_connection)


@pytest.mark.parametrize("method", NDT_TESTS)
@pytest.mark.parametrize("has_limits", [False, True])
def test_ndt_early_return_and_later_query_failure_close_connection(
    method: str, database_path: Path, has_limits: bool
) -> None:
    with duckdb.connect(str(database_path)) as conn:
        conn.execute("""
            CREATE TABLE config_irs_limits (
                limit_year INTEGER, hce_compensation_threshold INTEGER,
                annual_additions_limit INTEGER, base_limit INTEGER,
                catch_up_age_threshold INTEGER, catch_up_limit INTEGER,
                super_catch_up_limit INTEGER, super_catch_up_age_min INTEGER,
                super_catch_up_age_max INTEGER
            )
        """)
        if has_limits:
            conn.execute(
                "INSERT INTO config_irs_limits VALUES "
                "(2025, 160000, 70000, 23500, 50, 31000, 34750, 60, 64)"
            )
        else:
            # Input validation runs first, so the limits early return needs a
            # valid snapshot to be reached.
            conn.execute("""
                CREATE TABLE fct_workforce_snapshot AS
                SELECT 'E1' AS employee_id, y AS simulation_year,
                    50000.0 AS current_compensation,
                    50000.0 AS prorated_annual_compensation,
                    0.0 AS prorated_annual_contributions,
                    0.0 AS employer_match_amount, 0.0 AS employer_core_amount,
                    'eligible' AS current_eligibility_status,
                    true AS is_enrolled_flag, 'active' AS employment_status
                FROM (VALUES (2024), (2025)) t(y)
            """)
    conn = duckdb.connect(str(database_path), read_only=True)
    try:
        with patch("duckdb.connect", return_value=conn):
            result = _call_service(method, database_path)
        assert result.test_result == "error"
        if has_limits:
            assert "fct_workforce_snapshot" in result.test_message
        else:
            assert "not found" in result.test_message
        _assert_closed(conn)
    finally:
        conn.close()


def test_available_years_success_closes_connection(database_path: Path) -> None:
    with duckdb.connect(str(database_path)) as conn:
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot AS SELECT 2025 AS simulation_year"
        )
    conn = duckdb.connect(str(database_path), read_only=True)
    try:
        with patch("duckdb.connect", return_value=conn):
            result = _call_service("get_available_years", database_path)
        assert result.years == [2025]
        assert result.default_year == 2025
        _assert_closed(conn)
    finally:
        conn.close()


def _try_writer(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import duckdb, sys; conn = duckdb.connect(sys.argv[1]); "
            "conn.execute('INSERT INTO lock_probe VALUES (1)'); conn.close()",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize("method", ["get_dc_plan_analytics", "run_acp_test"])
def test_failed_request_releases_lock_for_another_process(
    method: str, database_path: Path, retained_connection: duckdb.DuckDBPyConnection
) -> None:
    blocked = _try_writer(database_path)
    assert blocked.returncode != 0
    assert "lock" in blocked.stderr.lower()
    with patch("duckdb.connect", return_value=retained_connection):
        _call_service(method, database_path)
    _assert_closed(retained_connection)
    writer = _try_writer(database_path)
    assert writer.returncode == 0, writer.stderr
