"""Complete optimizer ledger and shareable spreadsheet/JSON exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .models import Candidate, OptimizerRun


def write_exports(run: OptimizerRun, output_dir: Path) -> None:
    """Write every candidate and a conditional Pareto sheet without omissions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [_candidate_row(candidate) for candidate in run.candidates]
    frame = pd.DataFrame(rows)
    frame.to_csv(output_dir / "candidates.csv", index=False)
    with pd.ExcelWriter(
        output_dir / "optimizer_results.xlsx", engine="openpyxl"
    ) as writer:
        frame.to_excel(writer, sheet_name="Candidates", index=False)
        if run.pareto_frontier is not None:
            frontier = frame[frame["candidate_id"].isin(run.pareto_frontier)]
            frontier.to_excel(writer, sheet_name="Pareto Frontier", index=False)
    (output_dir / "optimizer_results.json").write_text(
        json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _candidate_row(candidate: Candidate) -> dict[str, Any]:
    row: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "status": candidate.status,
        "db_path": str(candidate.db_path) if candidate.db_path else "",
        "is_duplicate_of": candidate.is_duplicate_of or "",
        "duration_seconds": candidate.duration_seconds,
        "lever_values": json.dumps(candidate.lever_values, sort_keys=True),
        "constraint_results": json.dumps(
            [result.model_dump(mode="json") for result in candidate.constraint_results],
            sort_keys=True,
        ),
    }
    row.update({f"lever.{key}": value for key, value in candidate.lever_values.items()})
    row.update(
        {f"objective.{key}": value for key, value in candidate.objective_values.items()}
    )
    return row
