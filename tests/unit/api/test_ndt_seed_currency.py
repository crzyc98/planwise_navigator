"""NDT reads preserve archived IRS limits, including incomplete legacy schemas."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from planalign_api.routers.ndt import get_ndt_service
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.ndt_service import NDTService

pytestmark = pytest.mark.fast

NDT_TESTS = ("run_acp_test", "run_adp_test", "run_401a4_test", "run_415_test")


def _create_archive(database: Path, has_legacy_seed: bool) -> None:
    with duckdb.connect(str(database)) as conn:
        # Keep population evidence valid so this fixture isolates archived seed errors.
        conn.execute("""CREATE TABLE fct_workforce_snapshot AS SELECT
            'synthetic' AS employee_id, 2026 AS simulation_year,
            'eligible' AS current_eligibility_status,
            50000.0 AS current_compensation,
            50000.0 AS prorated_annual_compensation,
            3000.0 AS prorated_annual_contributions,
            1500.0 AS employer_match_amount, 0.0 AS employer_core_amount,
            0.0 AS employee_after_tax_contributions, 35 AS current_age
        """)
        if has_legacy_seed:
            conn.execute("CREATE TABLE config_irs_limits (limit_year INTEGER)")
            conn.execute("INSERT INTO config_irs_limits VALUES (2026)")


@pytest.mark.parametrize("method", NDT_TESTS)
@pytest.mark.parametrize("has_legacy_seed", [False, True])
def test_ndt_preserves_missing_or_legacy_seed(
    tmp_path: Path, method: str, has_legacy_seed: bool
) -> None:
    database = tmp_path / "owner's-archive.duckdb"
    _create_archive(database, has_legacy_seed)
    before = hashlib.sha256(database.read_bytes()).digest()
    service = get_ndt_service(MagicMock())
    service.db_resolver = MagicMock()
    service.db_resolver.resolve.return_value = ResolvedDatabasePath(
        path=database, source="run", run_id="archived"
    )
    # An existing reader also prevents a hidden read-write connection.
    with duckdb.connect(str(database), read_only=True) as reader:
        with patch("duckdb.connect", wraps=duckdb.connect) as connect:
            result = getattr(service, method)("ws", "sc", "Scenario", 2026)
        connect.assert_called_once_with(str(database), read_only=True)
        assert result.test_result == "error"
        assert result.test_message is not None
        assert any(
            name in result.test_message
            for name in (
                "config_irs_limits",
                "hce_compensation_threshold",
                "annual_additions_limit",
            )
        )
        if has_legacy_seed:
            assert reader.execute("SELECT * FROM config_irs_limits").fetchall() == [
                (2026,)
            ]
        else:
            assert reader.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'config_irs_limits'"
            ).fetchone() == (0,)
    assert hashlib.sha256(database.read_bytes()).digest() == before


def test_ndt_rejects_seed_refresh_mode() -> None:
    """Analytics cannot opt into replacing a run's statutory limits."""
    with pytest.raises(TypeError, match="refresh_seeds"):
        NDTService(MagicMock(), refresh_seeds=True)
