from pathlib import Path
import subprocess

import pytest

from planalign_api.services.provenance.capture import (
    CaptureError,
    ProvenanceRecorder,
    fingerprint_seed_directory,
    capture_source_state,
    initialize_manifest,
    safe_effective_config,
    sha256_file,
)
from tests.fixtures.run_provenance import RUN_ID

pytestmark = pytest.mark.fast


def test_capture_redacts_paths_and_secrets_and_ingests_annual_evidence(tmp_path: Path):
    census = tmp_path / "census.parquet"
    census.write_bytes(b"not-real-parquet")
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "config.csv").write_text("key,value\na,1\n", encoding="utf-8")
    run_dir = tmp_path / "runs" / RUN_ID
    config = {
        "simulation": {"start_year": 2025, "end_year": 2025, "random_seed": 17},
        "setup": {"census_parquet_path": str(census)},
        "api_token": "do-not-record",
    }
    recorder = initialize_manifest(
        run_dir=run_dir,
        run_id=RUN_ID,
        workspace_id="workspace",
        scenario_id="scenario-a",
        config=config,
        seed_root=seeds,
        project_root=tmp_path,
    )
    manifest = recorder.read()
    payload = manifest.model_dump_json()
    assert str(tmp_path) not in payload
    assert "do-not-record" not in payload
    assert manifest.random_seed == 17
    assert manifest.run_identity.plan_design_id == "default"
    assert manifest.census_input.sha256 == sha256_file(census)[0]
    assert [seed.logical_name for seed in manifest.seed_files] == ["config.csv"]
    recorder.ingest(
        {
            "record": "year_completed",
            "run_id": RUN_ID,
            "year": 2025,
            "event_counts": {},
            "workforce_reconciliation": {
                "opening_workforce": 1,
                "hires": 0,
                "terminations": 0,
                "expected_closing_workforce": 1,
                "actual_closing_workforce": 1,
                "variance": 0,
                "opening_source": "baseline",
            },
        }
    )
    recorder.ingest(
        {
            "record": "validation_results",
            "run_id": RUN_ID,
            "year": 2025,
            "disposition": "passed",
            "results": [
                {
                    "check_name": "safe",
                    "severity": "error",
                    "passed": True,
                    "affected_record_count": 0,
                }
            ],
        }
    )
    recorder.finalize("completed")
    final = recorder.read()
    assert final.capture_state == "completed"
    assert final.event_counts[0].event_type == "TOTAL"
    assert final.validation_results[0].affected_record_count == 0


def test_seed_capture_rejects_symlinks(tmp_path: Path):
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    target = tmp_path / "outside.csv"
    target.write_text("secret", encoding="utf-8")
    (seeds / "link.csv").symlink_to(target)
    with pytest.raises(CaptureError):
        fingerprint_seed_directory(seeds)


def test_atomic_manifest_is_always_valid_json(tmp_path: Path):
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    recorder = ProvenanceRecorder(run_dir)
    assert not recorder.path.exists()
    assert list(run_dir.glob(".provenance-*.tmp")) == []


def test_safe_config_projection_preserves_result_values():
    projected, redactions = safe_effective_config(
        {"rate": 0.3, "database_path": "/x/a.duckdb"}
    )
    assert projected == {"database_path": "<redacted-path>", "rate": 0.3}
    assert redactions == ["database_path"]


def test_git_dirty_fingerprint_tracks_content_and_unavailable_state(tmp_path: Path):
    unavailable = capture_source_state(tmp_path)
    assert unavailable.working_tree_state == "unavailable"
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )
    assert capture_source_state(tmp_path).working_tree_state == "clean"
    tracked.write_text("two", encoding="utf-8")
    first = capture_source_state(tmp_path)
    tracked.write_text("three", encoding="utf-8")
    second = capture_source_state(tmp_path)
    assert first.working_tree_state == "dirty"
    assert first.working_tree_fingerprint != second.working_tree_fingerprint
