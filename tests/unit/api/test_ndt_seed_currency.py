"""NDT seed-currency behavior for updated statutory-limit schemas."""

from __future__ import annotations

import duckdb

from planalign_api.services.ndt_service import NDTService


def test_ensure_seed_current_refreshes_missing_social_security_wage_base(
    tmp_path,
) -> None:
    """A database materialized before the new statutory field self-heals."""
    database = tmp_path / "stale.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            CREATE TABLE config_irs_limits (
                limit_year INTEGER,
                hce_compensation_threshold INTEGER,
                super_catch_up_limit INTEGER,
                annual_additions_limit INTEGER
            )
            """
        )

    NDTService._seed_verified.discard(str(database))
    NDTService._ensure_seed_current(database)

    with duckdb.connect(str(database), read_only=True) as connection:
        columns = {
            row[0]
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'config_irs_limits'
                """
            ).fetchall()
        }
        assert "social_security_wage_base" in columns
        value = connection.execute(
            "SELECT social_security_wage_base FROM config_irs_limits WHERE limit_year = 2026"
        ).fetchone()

    assert value == (184500,)
