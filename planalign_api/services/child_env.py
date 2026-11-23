"""Environment for processes the API launches."""

from __future__ import annotations

import os
from collections.abc import Mapping

from planalign_core.process_security import scrub_child_env


def build_child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy the API's environment for a child process, minus API credentials.

    This is a denylist, not an allowlist: ``PLANALIGN_API_TOKEN`` and any
    ``PLANALIGN_API_*`` name containing ``TOKEN``, ``SECRET`` or ``PASSWORD``
    are removed and everything else is kept. The engine legitimately reads many
    variables (``NAV_*``, ``DBT_*``, ``DATABASE_PATH``, ``DYLD_*``, proxy and
    locale settings), so an allowlist would break real deployments. ``extra``
    is applied afterwards and is also filtered.
    """
    env = dict(os.environ)
    if extra:
        env.update(extra)
    return scrub_child_env(env)
