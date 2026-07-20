"""Feature 119 (#470): compiled DAG execution engine.

Lazy exports keep the package importable regardless of submodule import
order during the state-machine rebuild.
"""

from typing import Any

__all__ = ["CompiledRunner", "FallbackRecord", "RecordLog", "RunArtifactWorkspace"]


def __getattr__(name: str) -> Any:
    if name == "CompiledRunner":
        from .compiled_runner import CompiledRunner

        return CompiledRunner
    if name in ("FallbackRecord", "RecordLog"):
        from . import fallback

        return getattr(fallback, name)
    if name == "RunArtifactWorkspace":
        from .workspace import RunArtifactWorkspace

        return RunArtifactWorkspace
    raise AttributeError(name)
