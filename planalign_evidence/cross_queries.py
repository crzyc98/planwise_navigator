"""One-scenario, one-year aggregate queries for cross-scenario evidence."""

from __future__ import annotations

from planalign_ensemble.models import METRIC_REGISTRY

_DEFAULT_COLUMNS = frozenset(
    {
        "employment_status",
        "prorated_annual_compensation",
        "employer_match_amount",
        "employer_core_amount",
        "total_employer_contributions",
        "participation_status",
        "current_deferral_rate",
    }
)


def _decimal_source(column: str, columns: frozenset[str]) -> str:
    return (
        f"CAST({column} AS DECIMAL(38,12))"
        if column in columns
        else "NULL::DECIMAL(38,12)"
    )


def _currency_sum(column: str, columns: frozenset[str]) -> str:
    """Sum a DOUBLE currency column without its ~1e-11 representation noise.

    Six places keeps fractional cents (prorated compensation has them) while
    dropping float artifacts like 53218778.270000000061 from canonical values.
    """
    return f"ROUND(SUM({_decimal_source(column, columns)}), 6)"


def build_scenario_aggregate_query(
    metric: str, year: int, columns: frozenset[str] | None = None
) -> str:
    """Return a read-only aggregate without an employee identifier or join."""
    if metric not in METRIC_REGISTRY:
        raise ValueError(f"Unsupported canonical metric: {metric}")
    available = _DEFAULT_COLUMNS if columns is None else columns
    if metric == "active_headcount":
        active = (
            "LOWER(employment_status) = 'active'"
            if "employment_status" in available
            else "NULL::BOOLEAN"
        )
        fields = [
            f"COUNT(*) FILTER (WHERE {active}) AS value",
            f"COUNT(*) FILTER (WHERE {active}) AS population",
        ]
    elif metric == "total_compensation":
        compensation = _currency_sum("prorated_annual_compensation", available)
        fields = [f"{compensation} AS value", "COUNT(*) AS population"]
    elif metric == "employer_match_cost":
        fields = [
            f"{_currency_sum('employer_match_amount', available)} AS value",
            "COUNT(*) AS population",
            f"{_currency_sum('prorated_annual_compensation', available)} AS compensation_base",
        ]
    elif metric == "total_employer_plan_cost":
        fields = [
            f"{_currency_sum('total_employer_contributions', available)} AS value",
            "COUNT(*) AS population",
            f"{_currency_sum('employer_match_amount', available)} AS match_value",
            f"{_currency_sum('employer_core_amount', available)} AS core_value",
        ]
    elif metric == "participation_rate":
        participating = (
            "CASE WHEN LOWER(participation_status) = 'participating' "
            "THEN 1.0 ELSE 0.0 END"
            if "participation_status" in available
            else "NULL::DECIMAL(38,12)"
        )
        numerator = f"SUM({participating})"
        fields = [
            f"CASE WHEN COUNT(*) = 0 THEN NULL ELSE {numerator} / COUNT(*) END AS value",
            "COUNT(*) AS population",
            f"COALESCE({numerator}, 0) AS numerator_sum",
        ]
    else:
        deferral = _decimal_source("current_deferral_rate", available)
        count = f"COUNT(*) FILTER (WHERE {deferral} IS NOT NULL)"
        numerator = f"SUM({deferral}) FILTER (WHERE {deferral} IS NOT NULL)"
        fields = [
            f"CASE WHEN {count} = 0 THEN NULL ELSE {numerator} / {count} END AS value",
            f"{count} AS population",
            f"COALESCE({numerator}, 0) AS numerator_sum",
        ]
    projection = ",\n  ".join(
        f"CAST({field.rsplit(' AS ', 1)[0]} AS DECIMAL(38,12)) AS {field.rsplit(' AS ', 1)[1]}"
        for field in fields
    )
    return f"SELECT\n  {projection}\nFROM fct_workforce_snapshot\nWHERE simulation_year = {year}"


__all__ = ["build_scenario_aggregate_query"]
