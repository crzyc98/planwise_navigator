"""JSON-in/JSON-out child process for Studio calibration jobs."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from .calibration_optimizer import AutoCalibrationSettings, AutoCalibrator
from .calibration_runner import CalibrationRun, CalibrationRunner
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class WorkerRequest(BaseModel):
    kind: Literal["run", "optimize"]
    run: CalibrationRun
    settings: AutoCalibrationSettings | None = None


def atomic_write_json(path: Path, payload: object) -> None:
    """Publish a complete JSON document with an atomic rename."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".calibration-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def execute(request: WorkerRequest) -> object:
    if request.kind == "run":
        results = CalibrationRunner(request.run, threads=1).run_calibration()
        return [result.model_dump(mode="json") for result in results]
    if request.settings is None:
        raise ValueError("Optimize requires settings")
    outcome = AutoCalibrator(request.run, request.settings, threads=1).optimize()
    return outcome.model_dump(mode="json")


def main(job_dir: Path) -> int:
    """Run the unchanged engine and publish either a result or a safe error."""
    try:
        request = WorkerRequest.model_validate_json(
            (job_dir / "request.json").read_text(encoding="utf-8")
        )
        atomic_write_json(job_dir / "result.json", execute(request))
        return 0
    except ConfigurationError as exc:
        error = {"error": str(exc), "error_status": 409}
    except Exception:
        error_id = uuid4().hex
        logger.exception("Calibration job failed [error_id=%s]", error_id)
        error = {
            "error": f"Calibration job failed (error_id: {error_id})",
            "error_status": 500,
        }
    atomic_write_json(job_dir / "error.json", error)
    return 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
