"""Human-readable optimizer run reporting."""

from __future__ import annotations

from pathlib import Path

from .models import OptimizerRun


def write_report(run: OptimizerRun, output_dir: Path) -> Path:
    """Write ranking, Pareto, failure, and binding-constraint summaries."""
    lines = [
        "# Plan-Design Optimizer Report",
        "",
        f"- Run ID: `{run.run_id}`",
        f"- Search seed: `{run.search_seed}`",
        f"- Evaluated candidates: {sum(candidate.is_duplicate_of is None for candidate in run.candidates)} / {run.max_runs}",
        f"- Candidate rows: {len(run.candidates)}",
        "",
        "## Results",
        "",
    ]
    if run.ranked_feasible:
        lines.extend(
            [
                "Feasible candidates, best first:",
                "",
                *[
                    f"{index}. `{candidate_id}`"
                    for index, candidate_id in enumerate(run.ranked_feasible, 1)
                ],
            ]
        )
    elif run.pareto_frontier:
        lines.extend(
            [
                "Pareto-efficient candidates:",
                "",
                *[f"- `{item}`" for item in run.pareto_frontier],
            ]
        )
    else:
        lines.append("Zero candidates satisfied every constraint.")
    if run.binding_infeasible_constraints:
        lines.extend(
            [
                "",
                "Binding constraints never satisfied:",
                "",
                *[f"- `{metric}`" for metric in run.binding_infeasible_constraints],
            ]
        )
    lines.extend(
        [
            "",
            "## Candidate Ledger",
            "",
            "See `candidates.csv` for every feasible, infeasible, non-evaluable, failed, and reused candidate.",
        ]
    )
    path = output_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
