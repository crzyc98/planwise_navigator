"""Filesystem containment guards for client-supplied storage identifiers.

Workspace and scenario identifiers arrive as route strings and are used to
build deletion targets. This module centralizes the fail-closed validation
pattern already used by ``current_result.resolve_run_directory``:

1. The identifier must be a canonical UUID string (server-generated IDs).
2. The target must resolve to a *direct child* of the expected root.
3. Symlinks are refused before resolution so a link pointing outside the
   root can never pass containment via ``Path.resolve()``.
4. A metadata marker inside the target must exist and embed the expected
   identity before anything destructive happens.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict


class PathGuardError(ValueError):
    """A client-supplied identifier is not a canonical UUID string."""


class ProtectedPathError(LookupError):
    """A deletion target is missing, escapes its expected root, is a
    symlink, or fails its metadata marker identity check."""


def require_canonical_uuid(value: str, *, label: str) -> uuid.UUID:
    """Parse ``value`` and require its canonical lowercase string form."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise PathGuardError(f"{label} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise PathGuardError(f"{label} must be a canonical UUID")
    return parsed


def resolve_direct_child(root: Path, identifier: uuid.UUID | str) -> Path:
    """Resolve ``root / identifier`` and prove it is a contained directory.

    Raises:
        ProtectedPathError: The candidate escapes the root, is a symlink,
            or does not exist as a directory.
    """
    canonical = identifier if isinstance(identifier, uuid.UUID) else _parse(identifier)
    contained_root = root.resolve()
    raw_candidate = contained_root / str(canonical)
    if raw_candidate.is_symlink():
        raise ProtectedPathError(f"Target {canonical} is not a permitted directory")
    candidate = raw_candidate.resolve()
    if candidate.parent != contained_root:
        raise ProtectedPathError(f"Target {canonical} escapes its expected root")
    if not candidate.is_dir():
        raise ProtectedPathError(f"Target {canonical} not found")
    return candidate


def verify_marker_identity(
    marker_path: Path, required_fields: Dict[str, str], *, label: str
) -> None:
    """Require a JSON marker file whose fields match the expected identity.

    Raises:
        ProtectedPathError: The marker is missing, unreadable, or any
            required field does not match its expected value.
    """
    if not marker_path.is_file():
        raise ProtectedPathError(f"{label} marker is missing")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtectedPathError(f"{label} marker is unreadable") from exc
    if not isinstance(payload, dict):
        raise ProtectedPathError(f"{label} marker is unreadable")
    for field, expected in required_fields.items():
        if payload.get(field) != expected:
            raise ProtectedPathError(f"{label} marker identity mismatch")


def _parse(value: str) -> uuid.UUID:
    try:
        return require_canonical_uuid(value, label="identifier")
    except PathGuardError as exc:
        raise ProtectedPathError(str(exc)) from exc
