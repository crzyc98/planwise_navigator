"""Bound-run trust, warning, and no-write behavior."""

import json

import duckdb
import pytest

from planalign_api import config as api_config
from planalign_api.services.evidence_pack_service import get_scenario_evidence_pack
from planalign_evidence.service import EvidenceConflictError, EvidenceTarget
from tests.fixtures.evidence_pack import RUN_ID, create_evidence_scenario


@pytest.mark.fast
def test_api_reports_mixed_generation_and_concurrent_attempt_without_writing(
    tmp_path, monkeypatch
) -> None:
    scenario = create_evidence_scenario(tmp_path)
    with duckdb.connect(str(scenario.database_path)) as connection:
        connection.execute(
            "UPDATE run_metadata SET run_id = '00000000-0000-0000-0000-000000000137', full_reset = FALSE"
        )
        connection.execute(
            "INSERT INTO run_metadata VALUES (?, TIMESTAMP '2026-08-12 13:00:00', 'simulate', ?, 43, 2025, 2027, ?, 'default', '2.4.0', FALSE)",
            [RUN_ID, "2" * 64, scenario.scenario_id],
        )
    metadata = json.loads((scenario.scenario_path / "scenario.json").read_text())
    metadata.update(
        {"status": "running", "last_run_id": "00000000-0000-0000-0000-000000000139"}
    )
    (scenario.scenario_path / "scenario.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    monkeypatch.setattr(
        api_config,
        "settings",
        api_config.APISettings(workspaces_root=tmp_path / "workspaces"),
    )
    before = scenario.database_path.stat()

    envelope = get_scenario_evidence_pack(
        scenario.workspace_id, scenario.scenario_id, "active_headcount", 2025, 2027
    )

    after = scenario.database_path.stat()
    codes = {warning.code for warning in envelope.pack.warnings}
    assert {"mixed_generation", "run_in_progress", "incomplete_provenance"} <= codes
    assert envelope.pack.provenance.run_id == RUN_ID
    assert envelope.pack.provenance.config_fingerprint == "2" * 64
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


@pytest.mark.fast
def test_read_only_target_classifies_conflicting_lock(tmp_path, monkeypatch) -> None:
    scenario = create_evidence_scenario(tmp_path)
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    from planalign_evidence import service as service_module

    def locked(*args, **kwargs):
        raise duckdb.IOException("Conflicting lock is held")

    monkeypatch.setattr(service_module.duckdb, "connect", locked)
    with pytest.raises(EvidenceConflictError, match="locked"):
        with target.connect():
            pass
