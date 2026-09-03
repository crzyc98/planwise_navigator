"""Acceptance contracts for per-design match and core formula dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.invariant_simulation import _simulation_config
from tests.fixtures.plan_design_formula_families import (
    CORE_FAMILIES,
    MATCH_FAMILIES,
    apply_single_design_formula,
    apply_two_design_formulas,
    core_gap_parameters,
    core_overlap_parameters,
    match_gap_parameters,
    match_overlap_parameters,
)

pytestmark = [pytest.mark.integration, pytest.mark.multi_year_invariants]

ROOT = Path(__file__).resolve().parents[2]
MATCH_MODEL = ROOT / "dbt/models/intermediate/int_employee_match_calculations.sql"
CORE_MODEL = ROOT / "dbt/models/intermediate/int_employer_core_contributions.sql"


@pytest.mark.parametrize("family", MATCH_FAMILIES)
def test_single_design_match_family_is_exported_for_parity(family: str) -> None:
    config = apply_single_design_formula(
        _simulation_config(Path("/tmp/feature_633_small.parquet")), family, "flat"
    )
    design = config.validated_plan_design_parameters().root[config.plan_design_id]
    assert design.match.family == family


@pytest.mark.parametrize("family", CORE_FAMILIES)
@pytest.mark.parametrize("integration_enabled", [False, True])
def test_single_design_core_family_and_integration_are_exported_for_parity(
    family: str, integration_enabled: bool
) -> None:
    config = apply_single_design_formula(
        _simulation_config(Path("/tmp/feature_633_small.parquet")),
        "deferral_based",
        family,
        integration_enabled=integration_enabled,
    )
    design = config.validated_plan_design_parameters().root[config.plan_design_id]
    assert design.employer_core.family == family
    assert design.employer_core.integration_enabled is integration_enabled


def test_two_design_payload_preserves_independent_families() -> None:
    config = apply_two_design_formulas(
        _simulation_config(Path("/tmp/feature_633_small.parquet"))
    )
    parameters = config.validated_plan_design_parameters().root
    assert parameters["legacy"].match.family == "deferral_based"
    assert parameters["legacy"].employer_core.family == "flat"
    assert parameters["new_hires"].match.family == "tenure_graded"
    assert parameters["new_hires"].employer_core.family == "age_banded"


def test_compiled_dispatch_is_limited_to_referenced_families() -> None:
    match_source = MATCH_MODEL.read_text()
    core_source = CORE_MODEL.read_text()
    assert "referenced_match_families" in match_source
    assert "referenced_core_families" in core_source
    assert "match_family_arm(" in match_source
    assert "core_family_rate(" in core_source
    assert "multi_design_formula_guard" in match_source
    assert "multi_design_formula_guard" in core_source


@pytest.mark.parametrize(
    "payload",
    [match_gap_parameters(), match_overlap_parameters()],
)
def test_match_guard_contract_is_fixture_backed(payload: dict) -> None:
    assert payload["match"]["family"] == "graded_by_service"
    source = MATCH_MODEL.read_text()
    for token in (
        "invocation_id",
        "match side",
        "employee_id",
        "plan_design_id",
        "simulation_year",
        "formula_family",
        "arm_count",
        "graded_schedule",
    ):
        assert token in source


@pytest.mark.parametrize(
    "payload",
    [core_gap_parameters(), core_overlap_parameters()],
)
def test_core_guard_contract_is_fixture_backed(payload: dict) -> None:
    assert payload["employer_core"]["family"] == "age_banded"
    source = CORE_MODEL.read_text()
    for token in (
        "invocation_id",
        "core side",
        "employee_id",
        "plan_design_id",
        "simulation_year",
        "core_formula_family",
        "band_match_count",
        "age_schedule",
        "core_rate_source",
    ):
        assert token in source


def test_guard_precedes_downstream_publication_and_dedup() -> None:
    match_source = MATCH_MODEL.read_text()
    core_source = CORE_MODEL.read_text()
    assert match_source.index("multi_design_formula_guard") < match_source.index(
        "final_match"
    )
    assert core_source.index("multi_design_formula_guard") < core_source.index(
        "WHERE rn = 1"
    )
    assert (
        "PARTITION BY pop.employee_id, pop.plan_design_id, pop.simulation_year"
        in core_source
    )


def test_integration_amounts_are_gated_on_a_resolved_core_rate() -> None:
    """Ineligible employees must not receive permitted-disparity amounts.

    The pre-feature run-global path gated every integration component behind
    ``core_contribution_rate > 0`` by passing a gated compensation expression
    into ``get_integrated_core_amounts``. The per-design branch computes the
    components inline and must apply the same gate, or ineligible employees are
    paid disparity while their base amount is zero.
    """
    core_source = CORE_MODEL.read_text()
    start = core_source.index("integration_components AS (")
    end = core_source.index("{% elif employer_core_integration_enabled %}")
    per_design_block = core_source[start:end]

    for component in ("excess_compensation", "disparity_core_amount"):
        assert component in per_design_block
    gate = (
        "CASE WHEN basis.core_contribution_rate > 0\n"
        "                THEN basis.recognized_compensation ELSE 0 END"
    )
    normalized = " ".join(per_design_block.split())
    expected = " ".join(gate.split())
    # base, excess, and disparity each gate recognized compensation on the rate.
    assert normalized.count(expected) == 3
