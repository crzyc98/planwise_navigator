"""Keep absolute server paths out of what the API sends to clients (#1311).

Two tools:

- :func:`relative_to_root` turns a path a response model carries into one
  relative to a root the client already knows about (its workspace, the
  optimizer runs root, an ensemble root).
- :func:`redact_server_paths` replaces server directories in free text (job
  errors, run log lines) with neutral labels. The part of a path below the
  directory is kept, so a traceback still says which file and line.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path, PureWindowsPath

from ..config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# A root this short ("/", "C:\") would relabel every path in a message.
_MIN_ROOT_LENGTH = 4


def relative_to_root(path: str | Path, root: Path) -> str:
    """``path`` relative to ``root`` with forward slashes, or just its file name.

    A path outside ``root`` (a record from a moved workspace, say) is reduced
    to its file name so no directory outside the root is disclosed.
    """
    return relative_to_roots(path, [root]) or PureWindowsPath(str(path)).name


def relative_to_roots(path: str | Path, roots: Iterable[Path]) -> str | None:
    """``path`` relative to the first of ``roots`` that contains it, if any.

    Both sides are resolved first, so ``..`` segments and links never yield a
    relative path that climbs out of its root.
    """
    resolved = _resolved(Path(path))
    for root in roots:
        base = _resolved(root)
        if resolved.is_relative_to(base):
            return resolved.relative_to(base).as_posix()
    return None


def redact_server_paths(text: str, extra: Sequence[tuple[Path, str]] = ()) -> str:
    """Replace server directories in ``text`` with labels.

    ``extra`` names a caller's own directories and labels (a job's work
    folder, for one). They are replaced first, so a more specific label wins
    over the general ones for the workspaces root, the install directory, the
    Python environment, the temp directory and the home directory.
    """
    for pattern, label in _patterns(tuple(extra), _standard_roots()):
        text = pattern.sub(label.replace("\\", r"\\"), text)
    return text


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        return path


def _standard_roots() -> tuple[tuple[Path, str], ...]:
    roots = [
        (get_settings().workspaces_root, "<workspaces>"),
        (PROJECT_ROOT, "<app>"),
        (Path(sys.prefix), "<python>"),
        (Path(sys.exec_prefix), "<python>"),
        (Path(sys.base_prefix), "<python>"),
        (Path(tempfile.gettempdir()), "<tmp>"),
    ]
    try:
        roots.append((Path.home(), "<home>"))
    except RuntimeError:  # no home directory for this user; nothing to relabel
        pass
    return tuple(roots)


@lru_cache(maxsize=64)
def _patterns(
    extra: tuple[tuple[Path, str], ...], standard: tuple[tuple[Path, str], ...]
) -> tuple[tuple[re.Pattern[str], str], ...]:
    """One pattern per directory spelling: callers' first, then longest first.

    A match must be the whole directory: not the start of a longer name
    (``/app`` in ``/app-old``) and not the tail of another path (``/tmp`` in
    ``/var/tmp`` or after a label already put in). A full stop that ends a
    sentence after the directory doesn't count as part of a name.
    """
    flags = re.IGNORECASE if os.name == "nt" else 0
    return tuple(
        (
            re.compile(
                r"(?<![\w.>-])" + re.escape(spelling) + r"(?![\w-]|\.\w)", flags
            ),
            label,
        )
        for group in (extra, standard)
        for spelling, label in sorted(
            _spellings(group).items(), key=lambda item: len(item[0]), reverse=True
        )
    )


def _spellings(roots: Iterable[tuple[Path, str]]) -> dict[str, str]:
    """Each directory as written, resolved, with forward slashes, and with
    backslashes doubled, as Windows paths appear in an ``OSError`` message."""
    found: dict[str, str] = {}
    for path, label in roots:
        for variant in (path, _resolved(path)):
            text = str(variant)
            for spelling in (text, variant.as_posix(), text.replace("\\", "\\\\")):
                if len(spelling) >= _MIN_ROOT_LENGTH and Path(spelling).is_absolute():
                    found.setdefault(spelling, label)
    return found
