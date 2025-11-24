"""
Fidelity PlanAlign Engine CLI Package

A Rich-based CLI wrapper for Fidelity PlanAlign Engine providing enhanced user experience
with beautiful terminal interfaces, progress bars, and interactive commands.
"""

from .main import app
from _version import __version__, get_full_version, get_version_dict

__all__ = ["app", "__version__", "get_full_version", "get_version_dict"]
