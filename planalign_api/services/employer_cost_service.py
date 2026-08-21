"""The one definition of employer cost, gross and net of forfeitures (#444).

Employer cost used to be spelled out separately in ``analytics_service``,
``comparison_service`` and ``report_service``. This module holds the single
definition — the SQL fragments the aggregate queries share, plus the
policy and timing rules that turn a forfeiture projection into a net cost.

It deliberately imports no other service, so ``vesting_service`` can use the
offset builder without a cycle. Callers that need a full net-cost series pass
the forfeiture rows in.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence

from ..models.employer_cost import (
    POLICY_REDUCES_EMPLOYER_COST,
    EmployerCostOffsetRow,
    EmployerCostSeries,
    EmployerCostYear,
    ForfeiturePolicy,
)
from ..models.vesting import ForfeitureYearRow

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")

# --------------------------------------------------------------------------
# The shared gross-cost definition
# --------------------------------------------------------------------------
# Every surface that reports employer cost sums these three columns of
# fct_workforce_snapshot. Keeping the expressions here means a change to what
# counts as employer cost lands in one place rather than three.
GROSS_MATCH_SQL = "COALESCE(SUM(employer_match_amount), 0)"
GROSS_CORE_SQL = "COALESCE(SUM(employer_core_amount), 0)"
GROSS_EMPLOYER_COST_SQL = (
    "COALESCE(SUM(employer_match_amount) + SUM(employer_core_amount), 0)"
)
TOTAL_COMPENSATION_SQL = "COALESCE(SUM(prorated_annual_compensation), 0)"


def _cents(value) -> Decimal:
    """Round a DOUBLE column to cents without float round-tripping."""
    return Decimal(str(value or 0)).quantize(CENTS)


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (numerator / denominator * 100).quantize(CENTS)


def query_gross_employer_cost(conn, where_clause: str = "") -> List[EmployerCostYear]:
    """Gross employer cost per simulation year from a scenario database.

    ``where_clause`` is an already-composed SQL predicate (including the
    ``WHERE`` keyword) so callers can reuse their own cohort filters. The
    returned rows carry no offset yet — see :func:`apply_forfeiture_offsets`.
    """
    rows = conn.execute(
        f"""
        SELECT
            simulation_year,
            {GROSS_MATCH_SQL} AS gross_match,
            {GROSS_CORE_SQL} AS gross_core,
            {TOTAL_COMPENSATION_SQL} AS total_compensation
        FROM fct_workforce_snapshot
        {where_clause}
        GROUP BY simulation_year
        ORDER BY simulation_year
        """
    ).fetchall()

    series: List[EmployerCostYear] = []
    for year, match, core, compensation in rows:
        gross_match = _cents(match)
        gross_core = _cents(core)
        gross_cost = gross_match + gross_core
        total_compensation = _cents(compensation)
        series.append(
            EmployerCostYear(
                simulation_year=int(year),
                gross_employer_match=gross_match,
                gross_employer_core=gross_core,
                gross_employer_cost=gross_cost,
                total_compensation=total_compensation,
                offset_basis_available=False,
                offset_unavailable_reason="No forfeiture projection requested",
                gross_cost_pct_of_compensation=_pct(gross_cost, total_compensation),
            )
        )
    return series


# --------------------------------------------------------------------------
# Forfeiture policy and timing
# --------------------------------------------------------------------------
NO_PRIOR_YEAR_REASON = (
    "No prior plan year within the simulation horizon, so no forfeitures have "
    "been recognized yet."
)


def _no_basis_reason(source_year: int) -> str:
    return (
        f"{source_year} terminations have no employer-contribution history "
        "within the simulation horizon, so their forfeiture cannot be measured."
    )


def build_employer_cost_offsets(
    forfeiture_rows: Sequence[ForfeitureYearRow],
    policy: ForfeiturePolicy,
) -> List[EmployerCostOffsetRow]:
    """Turn a forfeiture projection into per-year employer cost offsets.

    Timing: forfeitures from year N terminations are recognized and applied in
    year N + 1. A year whose source year has no measurable contribution basis
    gets ``basis_available=False`` and a null offset — never a $0 that reads as
    "this design forfeits nothing".
    """
    reduces_cost = POLICY_REDUCES_EMPLOYER_COST[policy]
    by_year = {row.simulation_year: row for row in forfeiture_rows}
    offsets: List[EmployerCostOffsetRow] = []

    for year in sorted(by_year):
        source_year = year - 1
        source = by_year.get(source_year)

        if source is None:
            offsets.append(
                EmployerCostOffsetRow(
                    simulation_year=year,
                    source_year=None,
                    basis_available=False,
                    unavailable_reason=NO_PRIOR_YEAR_REASON,
                )
            )
            continue

        if not source.has_prior_year_basis:
            offsets.append(
                EmployerCostOffsetRow(
                    simulation_year=year,
                    source_year=source_year,
                    basis_available=False,
                    unavailable_reason=_no_basis_reason(source_year),
                )
            )
            continue

        generated = source.forfeited_amount
        offsets.append(
            EmployerCostOffsetRow(
                simulation_year=year,
                source_year=source_year,
                forfeitures_generated=generated,
                offset_amount=generated if reduces_cost else Decimal("0.00"),
                participant_allocation=Decimal("0.00") if reduces_cost else generated,
                basis_available=True,
            )
        )

    return offsets


def apply_forfeiture_offsets(
    gross: Iterable[EmployerCostYear],
    offsets: Sequence[EmployerCostOffsetRow],
) -> List[EmployerCostYear]:
    """Attach offsets to gross rows, producing net cost where measurable."""
    by_year = {row.simulation_year: row for row in offsets}
    combined: List[EmployerCostYear] = []

    for row in gross:
        offset = by_year.get(row.simulation_year)
        if offset is None or not offset.basis_available:
            combined.append(
                row.model_copy(
                    update={
                        "forfeitures_generated": None,
                        "forfeiture_offset_applied": None,
                        "net_employer_cost": None,
                        "net_cost_pct_of_compensation": None,
                        "offset_basis_available": False,
                        "offset_unavailable_reason": (
                            offset.unavailable_reason
                            if offset is not None
                            else "No forfeiture projection for this year"
                        ),
                    }
                )
            )
            continue

        applied = offset.offset_amount or Decimal("0.00")
        net = row.gross_employer_cost - applied
        combined.append(
            row.model_copy(
                update={
                    "forfeitures_generated": offset.forfeitures_generated,
                    "forfeiture_offset_applied": applied,
                    "net_employer_cost": net,
                    "net_cost_pct_of_compensation": _pct(net, row.total_compensation),
                    "offset_basis_available": True,
                    "offset_unavailable_reason": None,
                }
            )
        )

    return combined


def build_employer_cost_series(
    scenario_id: str,
    scenario_name: str,
    schedule_name: str,
    policy: ForfeiturePolicy,
    gross: Iterable[EmployerCostYear],
    forfeiture_rows: Sequence[ForfeitureYearRow],
) -> EmployerCostSeries:
    """The canonical net-cost series for one scenario.

    Horizon totals include every year's gross cost. Years whose offset could
    not be measured contribute gross unchanged and are listed in
    ``years_without_offset_basis`` so the total is never quietly overstated as
    if those years had genuinely zero forfeitures.
    """
    offsets = build_employer_cost_offsets(forfeiture_rows, policy)
    years = apply_forfeiture_offsets(gross, offsets)

    total_gross = sum((row.gross_employer_cost for row in years), Decimal("0.00"))
    total_offset = sum(
        (row.forfeiture_offset_applied or Decimal("0.00") for row in years),
        Decimal("0.00"),
    )
    return EmployerCostSeries(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        forfeiture_policy=policy,
        schedule_name=schedule_name,
        years=years,
        total_gross_employer_cost=total_gross,
        total_forfeiture_offset=total_offset,
        total_net_employer_cost=total_gross - total_offset,
        years_without_offset_basis=[
            row.simulation_year for row in years if not row.offset_basis_available
        ],
    )


def compute_employer_cost(
    conn,
    scenario_id: str,
    scenario_name: str,
    schedule,
    policy: ForfeiturePolicy,
    where_clause: str = "",
) -> Optional[EmployerCostSeries]:
    """Read one scenario database and return its net employer cost series.

    Returns ``None`` when the database has no simulation years. The forfeiture
    projection is the same one the Vesting screens report, so the offset ties to
    ``VestingService`` totals exactly.
    """
    # Deferred: vesting_service imports this module for the offset builder.
    from .vesting_service import project_forfeitures_for_connection

    gross = query_gross_employer_cost(conn, where_clause)
    if not gross:
        return None

    forfeiture_rows = project_forfeitures_for_connection(conn, schedule)
    return build_employer_cost_series(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        schedule_name=schedule.name,
        policy=policy,
        gross=gross,
        forfeiture_rows=forfeiture_rows,
    )
