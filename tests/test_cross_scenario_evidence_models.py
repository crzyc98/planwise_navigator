"""Contracts for strict cross-scenario evidence entities."""

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from planalign_evidence.cross_models import CrossCitation, CrossScenarioFigure
from planalign_evidence.models import validate_figure_status


def _citation() -> CrossCitation:
    return CrossCitation(
        result_store="runs/a/simulation.duckdb",
        query_id="QA",
        query="SELECT 1 AS value",
        result_column="value",
    )


@pytest.mark.fast
def test_shared_figure_contract_and_frozen_extra_forbid() -> None:
    figure = CrossScenarioFigure(
        value="1.25", unit="currency", status="defined", citations=(_citation(),)
    )
    validate_figure_status("defined", "1.25", None)
    with pytest.raises(ValidationError):
        CrossScenarioFigure(
            value="NaN", unit="currency", status="defined", citations=(_citation(),)
        )
    with pytest.raises(ValidationError):
        CrossScenarioFigure(
            value="1",
            unit="currency",
            status="suppressed",
            reason="suppressed",
            citations=(_citation(),),
        )
    with pytest.raises(ValidationError):
        CrossScenarioFigure(
            value="1",
            unit="currency",
            status="defined",
            citations=(_citation(),),
            unexpected=True,
        )
    with pytest.raises((ValidationError, FrozenInstanceError)):
        figure.value = "2"


@pytest.mark.fast
def test_citation_count_and_read_only_contract() -> None:
    for citations in ((), (_citation(), _citation(), _citation())):
        with pytest.raises(ValidationError):
            CrossScenarioFigure(
                value="1", unit="count", status="defined", citations=citations
            )
    with pytest.raises(ValidationError):
        CrossCitation(
            result_store="../simulation.duckdb",
            query_id="QA",
            query="SELECT 1 AS value",
            result_column="value",
        )
    with pytest.raises(ValidationError):
        CrossCitation(
            result_store="runs/a/simulation.duckdb",
            query_id="QA",
            query="CREATE TABLE leak AS SELECT 1",
            result_column="value",
        )
