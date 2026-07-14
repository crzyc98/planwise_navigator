"""Strict read-only resolution of one exact archived run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


class ProvenanceArchiveError(RuntimeError):
    pass


class RunNotFoundError(ProvenanceArchiveError):
    pass


class IdentityConflictError(ProvenanceArchiveError):
    pass


class ArchiveUnstableError(ProvenanceArchiveError):
    pass


@dataclass(frozen=True)
class LocatedArchive:
    run_id: str
    run_dir: Path
    files: dict[str, bytes]
    snapshot: str

    def assert_unchanged(self) -> None:
        if _snapshot(self.run_dir) != self.snapshot:
            raise ArchiveUnstableError("archived run changed during report generation")


def locate_run_archive(workspaces_root: Path, run_id: str) -> LocatedArchive:
    """Resolve only ``runs/<exact UUID>`` below an existing workspace root."""
    try:
        canonical_id = str(UUID(run_id))
    except ValueError as exc:
        raise RunNotFoundError("archived run ID was not found") from exc
    if canonical_id != run_id.lower() or not workspaces_root.is_dir():
        raise RunNotFoundError("archived run ID was not found")
    root = workspaces_root.resolve(strict=True)
    matches: list[Path] = []
    for runs_dir in root.rglob("runs"):
        candidate = runs_dir / canonical_id
        if candidate.is_dir():
            matches.append(candidate)
    if not matches:
        raise RunNotFoundError(f"archived run {canonical_id} was not found")
    if len(matches) != 1:
        raise IdentityConflictError(f"multiple archives claim run {canonical_id}")
    run_dir = matches[0]
    if run_dir.is_symlink():
        raise IdentityConflictError("run archive cannot be a symlink")
    resolved = run_dir.resolve(strict=True)
    if root not in resolved.parents or resolved.name != canonical_id:
        raise IdentityConflictError("run archive identity is not safely contained")
    before = _snapshot(resolved)
    files: dict[str, bytes] = {}
    for name in ("run_metadata.json", "provenance.json", "config.yaml"):
        path = resolved / name
        if path.is_symlink():
            raise IdentityConflictError("run archive evidence cannot be a symlink")
        if path.is_file():
            files[name] = path.read_bytes()
    after = _snapshot(resolved)
    if before != after:
        raise ArchiveUnstableError("archived run changed during report generation")
    _check_identity(canonical_id, files)
    return LocatedArchive(canonical_id, resolved, files, after)


def _check_identity(run_id: str, files: dict[str, bytes]) -> None:
    for name in ("run_metadata.json", "provenance.json"):
        if name not in files:
            continue
        try:
            claimed = json.loads(files[name]).get("run_id")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            continue
        if claimed is not None and str(claimed) != run_id:
            raise IdentityConflictError(f"{name} conflicts with requested run identity")


def _snapshot(run_dir: Path) -> str:
    digest = hashlib.sha256()
    try:
        for path in sorted(run_dir.iterdir(), key=lambda item: item.name):
            stat = path.stat(follow_symlinks=False)
            digest.update(path.name.encode("utf-8"))
            digest.update(f"{stat.st_mode}:{stat.st_size}:{stat.st_mtime_ns}".encode())
            if path.name in {"run_metadata.json", "provenance.json", "config.yaml"}:
                if stat.st_size > 50 * 1024 * 1024:
                    raise ArchiveUnstableError(
                        "archived evidence exceeds the safe read limit"
                    )
                digest.update(path.read_bytes())
    except OSError as exc:
        raise ArchiveUnstableError(
            "archived run could not provide a consistent view"
        ) from exc
    return digest.hexdigest()
