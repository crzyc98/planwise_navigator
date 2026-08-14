"""Citation reproduction and aggregate-only projection tests."""

from decimal import Decimal

import duckdb
import pytest

from planalign_evidence.service import EvidenceTarget, build_evidence_pack
from tests.fixtures.evidence_pack import create_evidence_scenario


@pytest.mark.fast
def test_every_cited_figure_reexecutes_from_one_aggregate_row(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    pack = build_evidence_pack(target, "employer_match_cost", 2025, 2027)
    figures = pack._figures()
    assert len({figure.citation.query for figure in figures}) == 1

    with duckdb.connect(str(scenario.database_path), read_only=True) as connection:
        cursor = connection.execute(figures[0].citation.query)
        values = cursor.fetchone()
        row = dict(
            zip((column[0] for column in cursor.description), values, strict=True)
        )
    for figure in figures:
        actual = row[figure.citation.result_column]
        if figure.status == "defined":
            assert Decimal(str(actual)) == Decimal(figure.value or "0")
        else:
            assert actual is None

    final_select = figures[0].citation.query.rsplit("SELECT", 1)[1]
    assert "employee_id" not in final_select
    assert "ATTACH" not in figures[0].citation.query.upper()
    assert "COPY" not in figures[0].citation.query.upper()
