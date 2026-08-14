"""Fast validation tests for aggregate-only evidence-pack entities."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from planalign_evidence.models import Citation, EvidenceFigure, PackProvenance


def _citation(**updates) -> Citation:
    values = {
        "result_store": "runs/00000000-0000-0000-0000-000000000138/simulation.duckdb",
        "query_id": "Q1",
        "query": "SELECT CAST(1 AS DECIMAL(38,12)) AS base_value",
        "result_column": "base_value",
    }
    values.update(updates)
    return Citation(**values)


@pytest.mark.fast
def test_figure_status_and_decimal_contract() -> None:
    figure = EvidenceFigure(
        value="1.25",
        unit="currency",
        status="defined",
        reason=None,
        citation=_citation(),
    )
    assert figure.value == "1.25"
    with pytest.raises(ValidationError):
        EvidenceFigure(
            value=None,
            unit="currency",
            status="defined",
            reason=None,
            citation=_citation(),
        )
    with pytest.raises(ValidationError):
        EvidenceFigure(
            value="NaN",
            unit="currency",
            status="defined",
            reason=None,
            citation=_citation(),
        )


@pytest.mark.fast
def test_citation_rejects_paths_and_write_sql() -> None:
    with pytest.raises(ValidationError):
        _citation(result_store="/private/result.duckdb")
    with pytest.raises(ValidationError):
        _citation(query="CREATE TABLE leaked AS SELECT 1")


@pytest.mark.fast
def test_provenance_requires_full_fingerprint() -> None:
    provenance = PackProvenance(
        workspace_id="workspace",
        scenario_id="scenario",
        scenario_name="Scenario",
        run_id="00000000-0000-0000-0000-000000000138",
        run_timestamp=datetime(2026, 8, 12, tzinfo=timezone.utc),
        random_seed=42,
        config_fingerprint="a" * 64,
        result_store="runs/00000000-0000-0000-0000-000000000138/simulation.duckdb",
        verification_disposition="fully_verified",
    )
    assert len(provenance.config_fingerprint or "") == 64
