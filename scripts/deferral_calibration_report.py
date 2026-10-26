"""On-demand continuous-participant calibration (design #986, section 7).

Percentages use 0–100; pp metrics use percentage points. Decrease averages
are signed. Empty conditional averages/shares are NULL, not zero.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import duckdb

Row = dict[str, Any]
BANDS: dict[str, tuple[str, list[tuple[str, float, float | None]]]] = {
    "age": (
        "current_age",
        [(f"{x}-{x + 9}", x, x + 10) for x in range(20, 70, 10)] + [("70+", 70, None)],
    ),
    "income": (
        "current_compensation",
        list(
            zip(
                [
                    "<25k",
                    "25-40k",
                    "40-50k",
                    "50-60k",
                    "60-75k",
                    "75-100k",
                    "100-125k",
                    "125-150k",
                    "150-200k",
                    "200-250k",
                    "250k+",
                ],
                [
                    float("-inf"),
                    25000,
                    40000,
                    50000,
                    60000,
                    75000,
                    100000,
                    125000,
                    150000,
                    200000,
                    250000,
                ],
                [
                    25000,
                    40000,
                    50000,
                    60000,
                    75000,
                    100000,
                    125000,
                    150000,
                    200000,
                    250000,
                    None,
                ],
                strict=True,
            )
        ),
    ),
    "tenure": (
        "current_tenure",
        [
            (f"{a}-{b}", a, b)
            for a, b in [
                (1, 2),
                (2, 3),
                (3, 4),
                (4, 5),
                (5, 10),
                (10, 15),
                (15, 20),
                (20, 25),
                (25, 30),
            ]
        ]
        + [("30+", 30, None)],
    ),
}


def continuous_sql() -> str:
    """Join adjacent year-ends and aggregate events before joining to avoid fanout."""
    return """
    WITH attribution AS (
      SELECT scenario_id, employee_id, simulation_year,
        BOOL_OR(event_type = 'deferral_change' AND event_category IN
          ('proactive_increase', 'restart')) AS proactive,
        BOOL_OR(event_type = 'deferral_escalation') AS aip
      FROM fct_yearly_events GROUP BY ALL
    )
    SELECT c.simulation_year, c.current_age, c.current_compensation,
      c.current_tenure, p.current_deferral_rate AS previous_rate,
      c.current_deferral_rate AS current_rate,
      CAST(c.current_deferral_rate - p.current_deferral_rate AS DOUBLE) AS delta,
      CASE WHEN a.proactive THEN 'proactive' WHEN a.aip THEN 'aip'
        ELSE 'other' END AS attribution
    FROM fct_workforce_snapshot c
    JOIN fct_workforce_snapshot p ON c.employee_id = p.employee_id
      AND c.scenario_id IS NOT DISTINCT FROM p.scenario_id
      AND c.simulation_year = p.simulation_year + 1
    LEFT JOIN attribution a ON c.employee_id = a.employee_id
      AND (c.scenario_id IS NULL OR a.scenario_id IS NULL
        OR c.scenario_id = a.scenario_id)
      AND c.simulation_year = a.simulation_year
    WHERE c.employment_status = 'active' AND p.employment_status = 'active'
      AND c.is_enrolled_flag AND p.is_enrolled_flag
      AND (? IS NULL OR c.scenario_id = ?)
    """


def band_sql() -> str:
    """Generate reporting-only half-open band predicates from data."""
    parts = ["SELECT *, 'overall' AS dimension, 'overall' AS band FROM continuous"]
    for dimension, (column, bands) in BANDS.items():
        for label, lower, upper in bands:
            bounds = [] if lower == float("-inf") else [f"{column} >= {lower}"]
            if upper is not None:
                bounds.append(f"{column} < {upper}")
            parts.append(
                f"SELECT *, '{dimension}' AS dimension, '{label}' AS band "
                f"FROM continuous WHERE {' AND '.join(bounds)}"
            )
    return " UNION ALL ".join(parts)


def metric_sql() -> str:
    expressions = ["COUNT(*) AS n_continuous"]
    for name, predicate in {
        "same": "ABS(delta) < 0.00005",
        "increase": "delta >= 0.00005",
        "decrease": "delta <= -0.00005",
        "to_zero": "previous_rate > 0 AND current_rate = 0",
        "from_zero": "previous_rate = 0 AND current_rate > 0",
    }.items():
        expressions.append(f"100.0 * AVG(CAST({predicate} AS INTEGER)) AS pct_{name}")
    for source in ("proactive", "aip", "other"):
        condition = f"delta >= 0.00005 AND attribution = '{source}'"
        expressions.append(
            f"100.0 * COUNT(*) FILTER (WHERE {condition}) / "
            f"NULLIF(COUNT(*) FILTER (WHERE delta >= 0.00005), 0) AS pct_increases_{source}"
        )
        if source != "other":
            expressions.append(
                f"100 * AVG(delta) FILTER (WHERE {condition}) AS avg_increase_pp_{source}"
            )
    expressions.extend(
        [
            "100 * AVG(delta) FILTER (WHERE delta >= 0.00005) AS avg_increase_pp",
            "100 * AVG(delta) FILTER (WHERE delta <= -0.00005) AS avg_decrease_pp",
            "100 * AVG(delta) AS net_change_pp",
        ]
    )
    return ",\n".join(expressions)


def build_report(
    connection: duckdb.DuckDBPyConnection, scenario_id: str | None = None
) -> list[Row]:
    query = (
        f"WITH continuous AS ({continuous_sql()}), banded AS ({band_sql()}) "
        f"SELECT simulation_year, dimension, band, {metric_sql()} FROM banded "
        "GROUP BY simulation_year, dimension, band ORDER BY simulation_year, dimension, band"
    )
    result = connection.execute(query, [scenario_id, scenario_id])
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def compare_targets(rows: list[Row], path: Path) -> list[Row]:
    with path.open(newline="") as handle:
        targets = list(csv.DictReader(handle))
    comparisons = []
    for row in rows:
        for target in targets:
            if (row["dimension"], row["band"]) != (target["dimension"], target["band"]):
                continue
            metric = target["metric"]
            simulated, expected = row[metric], float(target["value"])
            comparisons.append(
                {
                    "simulation_year": row["simulation_year"],
                    "dimension": row["dimension"],
                    "band": row["band"],
                    "metric": metric,
                    "simulated": simulated,
                    "target": expected,
                    "diff": None if simulated is None else simulated - expected,
                }
            )
    return comparisons


def print_table(rows: list[Row]) -> None:
    if not rows:
        print("No matching continuous participants or targets.")
        return
    columns = list(rows[0])
    formatted = [
        [f"{row[c]:.4f}" if isinstance(row[c], float) else str(row[c]) for c in columns]
        for row in rows
    ]
    widths = [
        max(len(c), *(len(row[i]) for row in formatted)) for i, c in enumerate(columns)
    ]
    for values in [columns, *formatted]:
        print(
            "  ".join(
                value.ljust(width) for value, width in zip(values, widths, strict=True)
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--scenario-id")
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        rows = build_report(connection, args.scenario_id)
    if args.targets:
        rows = compare_targets(rows, args.targets)
    print_table(rows)
    if args.output and rows:
        with args.output.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
