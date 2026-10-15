from pathlib import Path
import subprocess
from unittest.mock import patch

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
from tests.fixtures.run_provenance import build_archive

pytestmark = pytest.mark.fast


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.py").write_text("original\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
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
    return tmp_path


@pytest.mark.parametrize("entry", ["repository", "worktree", "symlink", "gitlink"])
def test_unsupported_source_preserves_sha_and_dirty_state(
    source_repo: Path, entry: str
):
    clean = capture_source_state(source_repo)
    nested = source_repo / "nested"
    if entry == "symlink":
        nested.symlink_to(source_repo / "source.py")
    elif entry == "repository":
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        (nested / "source.py").write_text("nested content")
    elif entry == "worktree":
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(nested), "HEAD"],
            cwd=source_repo,
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            [
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{clean.git_commit_sha},nested",
            ],
            cwd=source_repo,
            check=True,
        )
    findings = []
    captured = capture_source_state(source_repo, findings=findings)
    assert captured.git_commit_sha == clean.git_commit_sha
    assert captured.working_tree_state == "dirty"
    assert captured.working_tree_fingerprint is None
    assert findings[0].field_path == "evidence.software.working_tree_fingerprint"
    assert "nested" in findings[0].reason or "non-regular" in findings[0].reason
    assert str(source_repo) not in findings[0].reason


@pytest.mark.parametrize("failed_command", ["status", "rev-parse"])
def test_git_failures_preserve_independent_source_evidence(
    source_repo: Path,
    failed_command: str,
):
    real_run = subprocess.run

    def fail_command(args, **kwargs):
        if args[1] == failed_command:
            raise subprocess.TimeoutExpired(args, 10)
        return real_run(args, **kwargs)

    findings = []
    with patch(
        "planalign_api.services.provenance.capture.subprocess.run", fail_command
    ):
        captured = capture_source_state(source_repo, findings=findings)
    if failed_command == "status":
        assert captured.git_commit_sha
        assert captured.working_tree_state == "unavailable"
        assert findings[0].field_path == "evidence.software.working_tree_state"
    else:
        assert captured.git_commit_sha is None
        assert captured.working_tree_state == "clean"
        assert findings[0].field_path == "evidence.software.git_commit_sha"


def test_untracked_regular_source_bytes_are_bound(source_repo: Path):
    new_source = source_repo / "new.py"
    new_source.write_text("one")
    first = capture_source_state(source_repo)
    new_source.write_text("two")
    second = capture_source_state(source_repo)
    assert first.working_tree_fingerprint
    assert first.working_tree_fingerprint != second.working_tree_fingerprint


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
    (run_dir / "config.yaml").write_text(
        "simulation:\n  start_year: 2025\n  end_year: 2025\n  random_seed: 17\n",
        encoding="utf-8",
    )
    manifest = recorder.read()
    payload = manifest.model_dump_json()
    assert str(tmp_path) not in payload
    assert "do-not-record" not in payload
    assert manifest.random_seed == 17
    assert manifest.run_identity.plan_design_id == "default"
    assert {finding.field_path for finding in manifest.capture_findings} == {
        "evidence.software.git_commit_sha",
        "evidence.software.working_tree_state",
    }
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
    assert [item.logical_name for item in final.archive_artifacts] == ["config.yaml"]
    assert final.archive_artifacts[0].sha256 == sha256_file(run_dir / "config.yaml")[0]


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
    findings = []
    unavailable = capture_source_state(tmp_path, findings=findings)
    assert unavailable.working_tree_state == "unavailable"
    assert unavailable.git_commit_sha is None
    assert len(findings) == 2
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


@pytest.mark.parametrize(
    ("first_severity", "first_disposition", "expected_disposition"),
    [
        ("error", "failed", "failed"),
        ("warning", "passed_with_warnings", "passed_with_warnings"),
    ],
)
def test_later_pass_cannot_overwrite_prior_failed_disposition(
    tmp_path: Path,
    first_severity: str,
    first_disposition: str,
    expected_disposition: str,
):
    run_dir = build_archive(tmp_path)
    recorder = ProvenanceRecorder(run_dir)
    recorder.ingest(
        {
            "record": "validation_results",
            "run_id": RUN_ID,
            "year": 2025,
            "disposition": first_disposition,
            "results": [
                {
                    "check_name": "event_sequence_validation",
                    "severity": first_severity,
                    "passed": False,
                    "affected_record_count": 7,
                }
            ],
        }
    )
    recorder.ingest(
        {
            "record": "validation_results",
            "run_id": RUN_ID,
            "year": 2026,
            "disposition": "passed",
            "results": [
                {
                    "check_name": "event_sequence_validation",
                    "severity": "error",
                    "passed": True,
                    "affected_record_count": 0,
                }
            ],
        }
    )
    manifest = recorder.read()
    assert manifest.validation_disposition == expected_disposition
    assert [row.affected_record_count for row in manifest.validation_results] == [7, 0]
