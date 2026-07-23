"""Atomic latest-success pointer contracts for managed simulations."""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from planalign_api.services.current_result import (
    CurrentResultIntegrityError,
    CurrentResultPointer,
    allocate_run_directory,
    publish_current_result,
    read_current_result,
    resolve_scenario_read_context,
)


def _completed_run(scenario: Path, run_id: str) -> Path:
    run_dir = scenario / "runs" / run_id
    run_dir.mkdir(parents=True)
    with duckdb.connect(str(run_dir / "simulation.duckdb")) as connection:
        connection.execute("CREATE TABLE result_marker (value INTEGER)")
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "completed",
                "start_year": 2025,
                "end_year": 2029,
            }
        )
    )
    (run_dir / "config.yaml").write_text(
        "simulation:\n  start_year: 2025\n  end_year: 2029\n"
    )
    return run_dir


def test_pointer_requires_canonical_uuid():
    run_id = uuid.uuid4()
    assert str(CurrentResultPointer(run_id=run_id).run_id) == str(run_id)
    with pytest.raises(ValueError):
        CurrentResultPointer(run_id="not-a-uuid")


def test_run_directory_allocation_is_exclusive_and_contained(tmp_path: Path):
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    run_id = str(uuid.uuid4())

    allocated = allocate_run_directory(scenario, run_id)

    assert allocated == scenario / "runs" / run_id
    with pytest.raises(FileExistsError):
        allocate_run_directory(scenario, run_id)
    with pytest.raises(ValueError):
        allocate_run_directory(scenario, "../escape")


def test_publish_validates_completed_target_and_atomically_replaces(tmp_path: Path):
    scenario = tmp_path / "scenario"
    run_id = str(uuid.uuid4())
    run_dir = _completed_run(scenario, run_id)

    with patch("planalign_api.services.current_result.os.replace") as replace:
        publish_current_result(scenario, run_id)
        replace.assert_called_once()
        temporary, target = replace.call_args.args
        assert Path(temporary).parent == scenario
        assert target == scenario / "current_result.json"
        assert Path(temporary).exists()

    # Complete the mocked replace so subsequent read validation exercises disk state.
    Path(temporary).replace(target)
    pointer = read_current_result(scenario)
    assert pointer is not None and str(pointer.run_id) == run_id
    assert pointer.database_path == run_dir / "simulation.duckdb"


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_publish_rejects_non_completed_target(tmp_path: Path, status: str):
    scenario = tmp_path / "scenario"
    run_id = str(uuid.uuid4())
    run_dir = _completed_run(scenario, run_id)
    metadata = json.loads((run_dir / "run_metadata.json").read_text())
    metadata["status"] = status
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata))

    with pytest.raises(CurrentResultIntegrityError, match="completed"):
        publish_current_result(scenario, run_id)
    assert not (scenario / "current_result.json").exists()


def test_failed_publication_does_not_mutate_existing_pointer(tmp_path: Path):
    scenario = tmp_path / "scenario"
    successful_id = str(uuid.uuid4())
    publish_current_result(scenario, _completed_run(scenario, successful_id).name)
    before = (scenario / "current_result.json").read_bytes()
    failed_id = str(uuid.uuid4())
    failed_dir = _completed_run(scenario, failed_id)
    metadata = json.loads((failed_dir / "run_metadata.json").read_text())
    metadata["status"] = "failed"
    (failed_dir / "run_metadata.json").write_text(json.dumps(metadata))

    with pytest.raises(CurrentResultIntegrityError):
        publish_current_result(scenario, failed_id)

    assert (scenario / "current_result.json").read_bytes() == before


def test_corrupt_or_traversing_pointer_fails_closed(tmp_path: Path):
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    (scenario / "current_result.json").write_text(
        '{"schema_version":1,"run_id":"../legacy"}'
    )

    with pytest.raises(CurrentResultIntegrityError):
        read_current_result(scenario)


def test_no_pointer_returns_none_for_legacy_resolver(tmp_path: Path):
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    assert read_current_result(scenario) is None


def test_read_context_splits_active_attempt_from_served_result(tmp_path: Path):
    scenario = tmp_path / "scenario"
    result_id = str(uuid.uuid4())
    active_id = str(uuid.uuid4())
    publish_current_result(scenario, _completed_run(scenario, result_id).name)
    (scenario / "scenario.json").write_text(
        json.dumps({"status": "running", "last_run_id": active_id})
    )

    context = resolve_scenario_read_context(scenario)

    assert context.result_run_id == uuid.UUID(result_id)
    assert context.active_run_id == uuid.UUID(active_id)
    assert context.warning == "run_in_progress"
    assert context.start_year == 2025 and context.end_year == 2029


def test_pointer_to_unreadable_database_is_integrity_error(tmp_path: Path):
    scenario = tmp_path / "scenario"
    run_id = str(uuid.uuid4())
    run_dir = _completed_run(scenario, run_id)
    publish_current_result(scenario, run_id)
    (run_dir / "simulation.duckdb").write_text("not duckdb")

    with pytest.raises(CurrentResultIntegrityError, match="readable"):
        read_current_result(scenario)
