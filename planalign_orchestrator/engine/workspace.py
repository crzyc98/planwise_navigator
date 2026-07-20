"""Run-isolated dbt artifact workspace (#470, research R2).

Every compiled-engine run owns a workspace under ``var/compiled_execution/
<run_id>/`` containing a generated dbt profile that pins the run's explicit
absolute database path, plus separated mutable (staging/delegations/logs)
and immutable (bundles) artifact roots. No dbt command ever receives a
published bundle as a target, and ambient ``DATABASE_PATH`` never decides
where dbt writes.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = REPO_ROOT / "dbt"
SHARED_DEV_DB = DBT_DIR / "simulation.duckdb"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "var" / "compiled_execution"
PROFILE_NAME = "fidelity_planalign_engine"
TARGET_NAME = "compiled_run"


class WorkspaceError(RuntimeError):
    """Workspace construction or targeting invariant violated."""


@dataclass
class RunArtifactWorkspace:
    run_id: str
    root: Path
    database_path: Path
    state: str = field(default="ACTIVE")

    @property
    def profiles_dir(self) -> Path:
        return self.root / "profile"

    @property
    def staging_root(self) -> Path:
        return self.root / "staging"

    @property
    def delegation_root(self) -> Path:
        return self.root / "delegations"

    @property
    def log_root(self) -> Path:
        return self.root / "logs"

    @property
    def bundle_root(self) -> Path:
        return self.root / "bundles"

    # ------------------------------------------------------------------ #

    @classmethod
    def create(
        cls,
        *,
        db_manager: Any,
        artifact_root: Optional[Path] = None,
        run_id: Optional[str] = None,
        validation_run: bool = False,
    ) -> "RunArtifactWorkspace":
        db_path = getattr(db_manager, "db_path", None)
        if db_path is None:
            raise WorkspaceError("db_manager must expose db_path")
        database_path = Path(db_path).resolve()
        if validation_run and database_path == SHARED_DEV_DB.resolve():
            raise WorkspaceError(
                "compiled-engine validation runs must not target the shared "
                f"dev database ({SHARED_DEV_DB})"
            )
        run_id = run_id or uuid.uuid4().hex
        root = Path(artifact_root or DEFAULT_ARTIFACT_ROOT) / run_id
        ws = cls(run_id=run_id, root=root, database_path=database_path)
        for directory in (
            ws.profiles_dir,
            ws.staging_root,
            ws.delegation_root,
            ws.log_root,
            ws.bundle_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        ws._write_profile()
        return ws

    def _write_profile(self) -> None:
        """Generate the explicit-run profile, mirroring the repo profile's
        settings but pinning the absolute database path (never env-derived)."""
        settings: dict = {}
        repo_profile = DBT_DIR / "profiles.yml"
        if repo_profile.exists():
            try:
                parsed = yaml.safe_load(repo_profile.read_text()) or {}
                dev = parsed.get(PROFILE_NAME, {}).get("outputs", {}).get("dev", {})
                settings = dict(dev.get("settings") or {})
            except yaml.YAMLError as exc:
                logger.warning("could not mirror repo profile settings: %s", exc)
        profile = {
            PROFILE_NAME: {
                "target": TARGET_NAME,
                "outputs": {
                    TARGET_NAME: {
                        "type": "duckdb",
                        "path": str(self.database_path),
                        "schema": "main",
                        "threads": 1,
                        **({"settings": settings} if settings else {}),
                    }
                },
            }
        }
        (self.profiles_dir / "profiles.yml").write_text(
            yaml.safe_dump(profile, sort_keys=False)
        )

    # ------------------------------------------------------------------ #

    def new_staging_dir(self) -> Path:
        path = self.staging_root / uuid.uuid4().hex
        path.mkdir(parents=True)
        return path

    def new_delegation_dir(self, sequence: int) -> Path:
        path = self.delegation_root / f"{sequence:04d}-{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True)
        return path

    def new_log_dir(self, sequence: int) -> Path:
        path = self.log_root / f"{sequence:04d}-{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True)
        return path

    def assert_database(self, db_manager: Any) -> None:
        current = Path(getattr(db_manager, "db_path")).resolve()
        if current != self.database_path:
            raise WorkspaceError(
                f"workspace pinned to {self.database_path} but runner targets {current}"
            )

    def close(self, *, failed: bool = False, retain: bool = False) -> None:
        self.state = "FAILED_RETAINED" if (failed and retain) else "CLOSED"
        if not failed and not retain:
            for mutable in (self.staging_root, self.delegation_root):
                shutil.rmtree(mutable, ignore_errors=True)
