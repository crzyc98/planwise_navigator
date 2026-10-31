"""Resume and preservation contracts; subprocesses never execute the engine."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from campaign_a import run_matrix as matrix

pytestmark = pytest.mark.fast


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "campaign_a"
    (root / "cells").mkdir(parents=True)
    cells = [{"id": "one", "seeds": [42, 101]}, {"id": "two", "seeds": [42]}]
    (root / "matrix.json").write_text(json.dumps(cells))
    for cell in cells:
        (root / "cells" / f"{cell['id']}.json").write_text(json.dumps({"runs": {}}))
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "LOG_ROOT", tmp_path / "logs")
    execute = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(matrix.subprocess, "run", execute)
    return root, execute


def test_repair_skips_completed_and_preserves_failed_baseline(runner):
    root, execute = runner
    path = root / "cells/one.json"
    path.write_text(
        json.dumps(
            {
                "runs": {
                    "baseline": {"42": {"status": "failed"}},
                    "prerequisite_repair": {"42": {"status": "completed"}},
                }
            }
        )
    )
    before = path.read_bytes()
    matrix.run_matrix("prerequisite_repair", limit=1)
    assert path.read_bytes() == before
    command = execute.call_args.args[0]
    assert command[-3:] == ["101", "--stage", "prerequisite_repair"]
    assert execute.call_count == 1
    assert (matrix.LOG_ROOT / "prerequisite_repair/one_101.log").exists()
    assert not (matrix.LOG_ROOT / "prerequisite_repair/one_42.log").exists()


def test_default_baseline_preserves_all_existing_statuses(runner):
    root, execute = runner
    path = root / "cells/one.json"
    path.write_text(
        json.dumps(
            {
                "runs": {
                    "baseline": {
                        "42": {"status": "failed"},
                        "101": {"status": "interrupted"},
                    }
                }
            }
        )
    )
    before = path.read_bytes()
    matrix.run_matrix()
    assert path.read_bytes() == before
    assert execute.call_count == 1
    assert execute.call_args.args[0][-1] == "baseline"
    assert (matrix.LOG_ROOT / "two_42.log").exists()


def test_existing_stage_log_refuses_overwrite(runner):
    _, execute = runner
    log = matrix.LOG_ROOT / "prerequisite_repair/one_42.log"
    log.parent.mkdir(parents=True)
    log.write_text("original interrupted log")
    with pytest.raises(FileExistsError):
        matrix.run_matrix("prerequisite_repair")
    assert log.read_text() == "original interrupted log"
    execute.assert_not_called()


@pytest.mark.parametrize(
    "stage,limit", [("unknown", None), ("baseline", 0), ("baseline", -1)]
)
def test_invalid_bounds_never_launch(runner, stage, limit):
    with pytest.raises(ValueError):
        matrix.run_matrix(stage, limit)
    runner[1].assert_not_called()


def test_promo_backfill_stage(runner) -> None:
    _, execute = runner
    matrix.run_matrix("promo_backfill", limit=1)
    assert execute.call_args.args[0][-2:] == ["--stage", "promo_backfill"]
    assert matrix.STAGES.index("promo_backfill") == matrix.STAGES.index("two_dial") + 1
