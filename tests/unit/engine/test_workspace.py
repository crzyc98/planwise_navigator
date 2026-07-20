"""#470 regressions 3 & 5: explicit database targeting and bundle immutability.

RED against the prototype: `invoke_dbt_inprocess` relies on ambient
`DATABASE_PATH` (no profile generation), and compiled SQL is read from the
shared mutable `dbt/target/compiled`, which any delegation/build rewrites.
"""

from pathlib import Path

import pytest
import yaml

from tests.fixtures.compiled_execution import FakeDbManager

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


# --------------------------------------------------------------------- #
# Regression 3: delegation targets the explicit DB, never ambient env   #
# --------------------------------------------------------------------- #


def test_workspace_profile_embeds_explicit_database(tmp_path, monkeypatch):
    from planalign_orchestrator.engine.workspace import RunArtifactWorkspace

    explicit_db = tmp_path / "explicit.duckdb"
    decoy_db = tmp_path / "decoy.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(decoy_db))  # ambient must be ignored

    ws = RunArtifactWorkspace.create(
        db_manager=FakeDbManager(explicit_db), artifact_root=tmp_path / "ws"
    )
    profile = yaml.safe_load((ws.profiles_dir / "profiles.yml").read_text())
    (profile_name,) = [k for k in profile if k != "config"]
    target_name = profile[profile_name]["target"]
    output = profile[profile_name]["outputs"][target_name]
    assert Path(output["path"]).resolve() == explicit_db.resolve()
    assert str(decoy_db) not in str(output["path"])


def test_delegation_args_pin_profile_target_and_logs(tmp_path, monkeypatch):
    from planalign_orchestrator.engine.fallback import build_delegation_args
    from planalign_orchestrator.engine.workspace import RunArtifactWorkspace

    explicit_db = tmp_path / "explicit.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "decoy.duckdb"))
    ws = RunArtifactWorkspace.create(
        db_manager=FakeDbManager(explicit_db), artifact_root=tmp_path / "ws"
    )
    args = build_delegation_args(
        ["run", "--select", "stg_x"], workspace=ws, sequence=7, dbt_vars={"a": 1}
    )
    joined = " ".join(args)
    assert "--profiles-dir" in joined and str(ws.profiles_dir) in joined
    assert "--target-path" in joined and str(ws.delegation_root) in joined
    assert "--log-path" in joined
    assert "--threads 1" in joined
    # fresh mutable target per delegation, inside the workspace
    target_idx = args.index("--target-path") + 1
    assert Path(args[target_idx]).parent == ws.delegation_root


def test_workspace_refuses_shared_dev_database(tmp_path):
    from planalign_orchestrator.engine.workspace import (
        RunArtifactWorkspace,
        WorkspaceError,
    )
    from tests.fixtures.compiled_execution import SHARED_DEV_DB

    with pytest.raises(WorkspaceError):
        RunArtifactWorkspace.create(
            db_manager=FakeDbManager(SHARED_DEV_DB),
            artifact_root=tmp_path / "ws",
            validation_run=True,
        )


# --------------------------------------------------------------------- #
# Regression 5: published bundles are immutable and hash-verified       #
# --------------------------------------------------------------------- #


def _publish_minimal_bundle(ws, context_digest="c" * 64):
    """Publish a one-node bundle via the workspace publication protocol."""
    from planalign_orchestrator.engine.plan_cache import publish_bundle

    staging = ws.new_staging_dir()
    sql_rel = Path("compiled/pkg/models/m1.sql")
    (staging / sql_rel).parent.mkdir(parents=True, exist_ok=True)
    (staging / sql_rel).write_text("SELECT 1 AS x")
    (staging / "manifest.json").write_text("{}")
    return publish_bundle(
        workspace=ws,
        staging_dir=staging,
        context_digest=context_digest,
        nodes=[{"unique_id": "model.pkg.m1", "sql_path": str(sql_rel)}],
    )


def test_bundle_survives_mutation_of_staging_and_shared_targets(tmp_path):
    from planalign_orchestrator.engine.plan_cache import load_bundle_sql
    from planalign_orchestrator.engine.workspace import RunArtifactWorkspace

    ws = RunArtifactWorkspace.create(
        db_manager=FakeDbManager(tmp_path / "x.duckdb"), artifact_root=tmp_path / "ws"
    )
    bundle = _publish_minimal_bundle(ws)
    # simulate a later delegation/build recompiling into mutable targets:
    for mutable in (ws.staging_root, ws.delegation_root):
        victim = mutable / "compiled" / "pkg" / "models" / "m1.sql"
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_text("SELECT 999 AS corrupted")
    sql = load_bundle_sql(bundle, "model.pkg.m1")
    assert sql == "SELECT 1 AS x"


def test_bundle_corruption_fails_closed(tmp_path):
    from planalign_orchestrator.engine.plan_cache import (
        BundleIntegrityError,
        load_bundle_sql,
    )
    from planalign_orchestrator.engine.workspace import RunArtifactWorkspace

    ws = RunArtifactWorkspace.create(
        db_manager=FakeDbManager(tmp_path / "x.duckdb"), artifact_root=tmp_path / "ws"
    )
    bundle = _publish_minimal_bundle(ws)
    sql_file = bundle.root / "compiled" / "pkg" / "models" / "m1.sql"
    sql_file.chmod(0o644)
    sql_file.write_text("SELECT 666 AS tampered")
    with pytest.raises(BundleIntegrityError):
        load_bundle_sql(bundle, "model.pkg.m1")
