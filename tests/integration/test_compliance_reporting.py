"""Compliance reports over a complete isolated multi-year simulation."""

from dataclasses import replace

import duckdb
import pytest
import yaml
from unittest.mock import MagicMock

from planalign_api.services.compliance_service import ComplianceService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from tests.edge_config.catalog import CATALOG
from tests.fixtures.edge_config_matrix import run_case, require_completed

pytestmark = pytest.mark.integration


def test_compliance_reports_preserve_multi_year_evidence(tmp_path):
    case = next(c for c in CATALOG if c.name == "auto_escalation_low_cap")
    config = yaml.safe_load(case.config_path.read_text())
    config["simulation"]["end_year"] = 2027
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))
    case = replace(case, config_path=config_path, end_year=2027)
    database = require_completed(run_case(case, tmp_path / "simulation.duckdb"))
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedDatabasePath(
        path=database, source="run", run_id="isolated-compliance"
    )
    service = ComplianceService(MagicMock(), resolver)
    for year in (2025, 2026, 2027):
        summary = service.summary("workspace", "scenario", "Isolated", year)
        assert summary.participant_count > 0
        assert summary.limits.is_estimated == (year == 2027)
        assert summary.deferrals.over_limit == 0
        assert summary.deferrals.unavailable == 0
        page = service.employees(
            "workspace", "scenario", year, summary.evidence, "402g", limit=200
        )
        assert page.total == summary.participant_count
        assert all(e.deferrals.status != "unavailable" for e in page.employees)
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT base_limit, annual_additions_limit FROM config_irs_limits WHERE limit_year = 2026"
        ).fetchone() == (24500, 72000)
        assert [
            r[0]
            for r in connection.execute(
                "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY 1"
            ).fetchall()
        ] == [2025, 2026, 2027]
