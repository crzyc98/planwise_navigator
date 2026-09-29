"""Workspace-scoped census history sets for Studio fits (#588).

A history set is 2-5 annual snapshots uploaded together and stored byte for
byte under ``workspaces/<ws>/fit_history/<history_id>/files/``, so the sha256
Studio shows is exactly what ``planalign fit`` hashes. Sets are immutable once
created and are validated by the fitter itself (``load_snapshots``): whatever
the fitter would reject, the upload rejects, with the fitter's message.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Sequence
from uuid import uuid4

import duckdb

from planalign_backtest.errors import BacktestError
from planalign_backtest.split import plan_split
from planalign_fit.snapshots import (
    MAX_SNAPSHOTS,
    OPTIONAL_COLUMNS,
    SUPPORTED_SUFFIXES,
    SnapshotError,
    SnapshotSet,
    load_snapshots,
)

from ...models.param_fit import HistorySet, SnapshotInfo, SplitOption, SplitPreview

HISTORY_DIRNAME = "fit_history"
FILES_DIRNAME = "files"
RECORD_FILENAME = "history.json"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class HistoryError(ValueError):
    """An uploaded history set is not usable; the message is user-facing."""


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


class HistoryStore:
    """Create, read, and delete history sets under one workspaces root."""

    def __init__(self, workspaces_root: Path):
        self.workspaces_root = Path(workspaces_root)

    def root(self, workspace_id: str) -> Path:
        return self.workspaces_root / workspace_id / HISTORY_DIRNAME

    def files_dir(self, workspace_id: str, history_id: str) -> Path:
        return self.root(workspace_id) / history_id / FILES_DIRNAME

    def create(self, workspace_id: str, files: Sequence[UploadedFile]) -> HistorySet:
        """Validate and persist an upload; nothing is kept if it is invalid."""
        names = _safe_names(files)
        history_id = f"hist_{uuid4().hex[:12]}"
        self.root(workspace_id).mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self.root(workspace_id), prefix=".up-"))
        try:
            files_dir = staging / FILES_DIRNAME
            files_dir.mkdir()
            for name, upload in zip(names, files):
                (files_dir / name).write_bytes(upload.content)
            snapshot_set = _load(files_dir)
            created_at = datetime.now(timezone.utc)
            record = {"history_id": history_id, "created_at": created_at.isoformat()}
            (staging / RECORD_FILENAME).write_text(json.dumps(record), "utf-8")
            staging.rename(self.root(workspace_id) / history_id)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return _to_model(history_id, created_at, snapshot_set)

    def get(self, workspace_id: str, history_id: str) -> Optional[HistorySet]:
        """Re-hash and re-validate a stored set (raises HistoryError if broken)."""
        created_at = self._created_at(workspace_id, history_id)
        if created_at is None:
            return None
        snapshot_set = _load(self.files_dir(workspace_id, history_id))
        return _to_model(history_id, created_at, snapshot_set)

    def list_sets(self, workspace_id: str) -> list[HistorySet]:
        root = self.root(workspace_id)
        if not root.is_dir():
            return []
        found: list[HistorySet] = []
        for entry in root.iterdir():
            if entry.name.startswith("."):
                continue
            try:
                history = self.get(workspace_id, entry.name)
            except HistoryError:
                continue
            if history is not None:
                found.append(history)
        return sorted(found, key=lambda item: item.created_at, reverse=True)

    def exists(self, workspace_id: str, history_id: str) -> bool:
        return self._created_at(workspace_id, history_id) is not None

    def delete(self, workspace_id: str, history_id: str) -> bool:
        if not self.exists(workspace_id, history_id):
            return False
        shutil.rmtree(self.root(workspace_id) / history_id)
        return True

    def current_digest(self, workspace_id: str, history_id: str) -> Optional[str]:
        """The set's digest as it stands now, or None if it is gone or invalid."""
        try:
            history = self.get(workspace_id, history_id)
        except HistoryError:
            return None
        return history.source_digest if history is not None else None

    def _created_at(self, workspace_id: str, history_id: str) -> Optional[datetime]:
        if not history_id.replace("_", "").isalnum():
            return None
        record = self.root(workspace_id) / history_id / RECORD_FILENAME
        if not record.is_file():
            return None
        payload = json.loads(record.read_text(encoding="utf-8"))
        return datetime.fromisoformat(payload["created_at"])


def split_preview(snapshot_set: SnapshotSet, holdout: int) -> SplitOption:
    """The backtest split a holdout choice produces, or the reason it cannot."""
    try:
        split = plan_split(snapshot_set, holdout)
    except BacktestError as exc:
        return SplitOption(holdout_years=holdout, error=_studio_wording(str(exc)))
    return SplitOption(
        holdout_years=holdout,
        split=SplitPreview(
            fit_years=list(split.fit_years),
            holdout_years=list(split.holdout_years),
            boundary_year=split.boundary_year,
            # Matches planalign_backtest.simulate.configure_seed.
            simulation_effective_date=date(split.holdout_years[0], 12, 31),
        ),
    )


def _studio_wording(message: str) -> str:
    """The split planner speaks CLI flags; Studio analysts pick a holdout."""
    return message.replace("Use --holdout 1", "Choose a 1-year holdout")


def load_history_set(files_dir: Path) -> SnapshotSet:
    return _load(files_dir)


def _load(files_dir: Path) -> SnapshotSet:
    try:
        with duckdb.connect(":memory:") as conn:
            return load_snapshots(files_dir, conn)
    except SnapshotError as exc:
        raise HistoryError(_strip_paths(str(exc), files_dir)) from exc


def _to_model(
    history_id: str, created_at: datetime, snapshot_set: SnapshotSet
) -> HistorySet:
    snapshots = [
        SnapshotInfo(
            year=snapshot.year,
            filename=snapshot.path.name,
            row_count=snapshot.row_count,
            sha256=snapshot.sha256,
            as_of_date=date(snapshot.year, 12, 31),
            columns_present=[c for c in OPTIONAL_COLUMNS if snapshot.has(c)],
        )
        for snapshot in snapshot_set
    ]
    return HistorySet(
        history_id=history_id,
        created_at=created_at,
        snapshots=snapshots,
        source_digest=snapshot_set.source_digest,
        splits=[split_preview(snapshot_set, holdout) for holdout in (1, 2)],
    )


def _safe_names(files: Sequence[UploadedFile]) -> list[str]:
    if not files:
        raise HistoryError("Upload at least 2 annual census snapshot files.")
    if len(files) > MAX_SNAPSHOTS:
        raise HistoryError(
            f"Upload at most {MAX_SNAPSHOTS} snapshot files; got {len(files)}."
        )
    names: list[str] = []
    for upload in files:
        base = Path(upload.filename or "").name
        suffix = Path(base).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HistoryError(
                f"{base or 'A file'} is not a .parquet or .csv census snapshot."
            )
        name = _SAFE_NAME.sub("_", Path(base).stem).strip("._") or "snapshot"
        names.append(f"{name}{suffix}")
    if len(set(names)) != len(names):
        raise HistoryError("Two uploaded files have the same name.")
    return names


def _strip_paths(message: str, files_dir: Path) -> str:
    """Never echo server paths back to the client."""
    return message.replace(str(files_dir.resolve()), "upload").replace(
        str(files_dir), "upload"
    )
