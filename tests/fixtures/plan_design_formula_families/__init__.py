"""Deterministic fixtures for per-design contribution formula families."""

from .config import (
    CORE_FAMILIES,
    MATCH_FAMILIES,
    apply_legacy_single_design_formula,
    apply_single_design_formula,
    apply_two_design_formulas,
    build_capacity_census,
    core_gap_parameters,
    core_overlap_parameters,
    match_gap_parameters,
    match_overlap_parameters,
    relation_contract_payload,
)

FIXTURE_SEED = 113435436
BASELINE_CENSUS_SIZES = (7_500, 60_000)
CANONICAL_TABLES = (
    "int_employee_match_calculations",
    "int_employer_core_contributions",
    "fct_employer_match_events",
    "fct_workforce_snapshot",
)
NONDETERMINISTIC_COLUMNS = {
    "int_employee_match_calculations": ("created_at",),
    "int_employer_core_contributions": ("created_at",),
    "fct_employer_match_events": ("created_at",),
    "fct_workforce_snapshot": ("snapshot_created_at",),
}

__all__ = [
    "BASELINE_CENSUS_SIZES",
    "CANONICAL_TABLES",
    "CORE_FAMILIES",
    "FIXTURE_SEED",
    "MATCH_FAMILIES",
    "NONDETERMINISTIC_COLUMNS",
    "apply_legacy_single_design_formula",
    "apply_single_design_formula",
    "apply_two_design_formulas",
    "build_capacity_census",
    "core_gap_parameters",
    "core_overlap_parameters",
    "match_gap_parameters",
    "match_overlap_parameters",
    "relation_contract_payload",
]
