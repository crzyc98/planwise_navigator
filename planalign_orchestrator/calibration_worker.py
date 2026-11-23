"""JSON-in/JSON-out child process for Studio calibration jobs."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
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


_POSIX_ABS_PATH_RE = re.compile(
    r"(?<![:\w.-])/(?:[^\s'\"()\[\],;:]+/)+[^\s'\"()\[\],;:]+"
)
_WINDOWS_ABS_PATH_RE = re.compile(r"(?<![\w.-])[A-Za-z]:[\\/][^\s'\"()\[\],;:]+")


def _sanitize_configuration_error(message: str) -> str:
    """Keep the human-readable reason while removing absolute filesystem paths."""
    if message.startswith("Calibration target database not found:"):
        return "Calibration target database not found"
    cleaned = _POSIX_ABS_PATH_RE.sub(
        lambda match: PurePosixPath(match.group(0)).name, message
    )
    return _WINDOWS_ABS_PATH_RE.sub(
        lambda match: PureWindowsPath(match.group(0)).name, cleaned
    )


def main(job_dir: Path) -> int:
    """Run the unchanged engine and publish either a result or a safe error."""
    try:
        request = WorkerRequest.model_validate_json(
            (job_dir / "request.json").read_text(encoding="utf-8")
        )
        atomic_write_json(job_dir / "result.json", execute(request))
        return 0
    except ConfigurationError as exc:
        logger.warning("Calibration configuration error: %s", exc)
        error = {
            "error": _sanitize_configuration_error(str(exc)),
            "error_status": 409,
        }
    except Exception:
        error_id = uuid4().hex
        logger.exception("Calibration job failed [error_id=%s]", error_id)
        error = {
            "error": f"Calibration job failed (error_id: {error_id})",
            "error_status": 500,
        }
    atomic_write_json(job_dir / "error.json", error)
    return 1


def run_as_worker(job_dir: Path) -> int:
    """Child-process entry: this process runs one job serially, so dbt can run
    in-process (PLANALIGN_DBT_IN_PROCESS). Never set by main(), so in-process
    callers (tests, the API) keep subprocess dbt."""
    os.environ["PLANALIGN_DBT_IN_PROCESS"] = "1"
    return main(job_dir)


if __name__ == "__main__":
    sys.exit(run_as_worker(Path(sys.argv[1])))
