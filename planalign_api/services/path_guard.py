"""Filesystem containment guards for client-supplied storage identifiers.

Workspace and scenario identifiers arrive as route strings and are used to
build storage paths. Every lookup goes through ``resolve_child_path``: the
id must be one safe path component and the result a direct child of its
root. Deletion targets additionally follow the fail-closed pattern already
used by ``current_result.resolve_run_directory``:

1. The identifier must be a canonical UUID string (server-generated IDs).
2. The target must resolve to a *direct child* of the expected root.
3. Symlinks are refused before resolution so a link pointing outside the
   root can never pass containment via ``Path.resolve()``.
4. A metadata marker inside the target must exist and embed the expected
   identity before anything destructive happens.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Dict, NoReturn

from .sql_security import SQLSecurityError, validate_file_path

_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class PathGuardError(ValueError):
    """A client-supplied identifier or path is malformed or not permitted."""


class ProtectedPathError(LookupError):
    """A target is missing, escapes its expected root, is a symlink,
    or fails its metadata marker identity check."""


def require_canonical_uuid(value: str, *, label: str) -> uuid.UUID:
    """Parse ``value`` and require its canonical lowercase string form."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise PathGuardError(f"{label} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise PathGuardError(f"{label} must be a canonical UUID")
    return parsed


def require_safe_path_component(value: str, *, label: str) -> str:
    """Require ``value`` to be one safe path component and return it.

    Accepts ASCII letters, digits, ``-`` and ``_`` starting with a letter or
    digit, up to 128 characters. That covers canonical UUIDs and the
    readable ids older workspaces and tests use, and rules out separators of
    either kind, ``.``/``..``, null bytes and hidden names.
    """
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise PathGuardError(f"{label} is not a valid identifier")
    return value


def resolve_child_path(root: Path, identifier: str, *, label: str) -> Path:
    """Return ``root / identifier`` once it is proven a contained direct child.

    The target need not exist. The unresolved path is returned so valid ids
    keep the same path strings as before.

    Raises:
        PathGuardError: ``identifier`` is not a safe path component.
        ProtectedPathError: The candidate is a symlink or escapes ``root``.
    """
    component = require_safe_path_component(identifier, label=label)
    _contained_child(root, component)
    return root / component


def resolve_direct_child(root: Path, identifier: uuid.UUID | str) -> Path:
    """Resolve ``root / identifier`` and prove it is a contained directory.

    Raises:
        ProtectedPathError: The candidate escapes the root, is a symlink,
            or does not exist as a directory.
    """
    canonical = identifier if isinstance(identifier, uuid.UUID) else _parse(identifier)
    candidate = _contained_child(root, str(canonical))
    if not candidate.is_dir():
        raise ProtectedPathError(f"Target {canonical} not found")
    return candidate


def _contained_child(root: Path, component: str) -> Path:
    """Resolve ``root / component``, refusing symlinks and escapes."""
    contained_root = root.resolve()
    raw_candidate = contained_root / component
    if raw_candidate.is_symlink():
        raise ProtectedPathError(f"Target {component} is not a permitted directory")
    candidate = raw_candidate.resolve()
    if candidate.parent != contained_root:
        raise ProtectedPathError(f"Target {component} escapes its expected root")
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


def resolve_within_roots(
    raw_path: str | Path,
    allowed_roots: Sequence[Path],
    *,
    anchor: Path | None = None,
) -> Path:
    """Resolve a client-supplied path inside one of ``allowed_roots``.

    The path is fully resolved, following symlinks, before containment is
    checked, so ``..`` segments and links that leave every root are refused.
    A relative path is tried as given (against the working directory), then
    under ``anchor``. Responses name a path relative to the root that holds
    it, so when neither of those exists, an existing file or directory under
    another allowed root is accepted too.

    Raises:
        PathGuardError: One generic message for every rejection, so callers
            never reveal whether a path outside the roots exists.
    """
    path = Path(raw_path)
    candidates = [path]
    if anchor is not None and not path.is_absolute():
        candidates.append(anchor / path)
    first = next(
        (
            found
            for candidate in candidates
            if (found := _within_any_root(candidate, allowed_roots)) is not None
        ),
        None,
    )
    if path.is_absolute() or (first is not None and first.exists()):
        return first if first is not None else _refuse()
    for root in allowed_roots:
        found = _within_any_root(root / path, allowed_roots)
        if found is not None and found.exists():
            return found
    if first is not None:
        return first
    return _refuse()


def _refuse() -> NoReturn:
    raise PathGuardError("path is outside the allowed directories")


def _within_any_root(candidate: Path, allowed_roots: Sequence[Path]) -> Path | None:
    for root in allowed_roots:
        try:
            return validate_file_path(candidate, root, context="request")
        except ValueError:  # outside this root, or a NUL byte in the path
            continue
    return None


def resolve_workspace_file_path(
    workspaces_root: Path, workspace_id: str, file_path: str
) -> Path:
    """Validate workspace_id, resolve file_path, and enforce workspaces_root containment.

    Checks workspace identifier syntax and root containment before any
    filesystem existence or metadata check, raising a uniform error so callers
    never reveal whether a path outside ``workspaces_root`` exists.
    """
    workspace_dir = resolve_child_path(
        workspaces_root, workspace_id, label="workspace_id"
    )
    if "\x00" in file_path:
        raise SQLSecurityError("Invalid census file path")
    raw_path = Path(file_path)
    candidate = raw_path if raw_path.is_absolute() else workspace_dir / raw_path
    try:
        resolved = candidate.resolve()
        allowed_root = workspaces_root.resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise SQLSecurityError("Invalid census file path") from exc
    if not resolved.is_relative_to(allowed_root):
        raise SQLSecurityError("Invalid census file path")
    return resolved
