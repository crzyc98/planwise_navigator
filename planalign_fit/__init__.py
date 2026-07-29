"""Evidence loop I: fit hazards and behavioral parameters from census history.

``planalign fit <snapshots_dir>`` links 2-5 consecutive annual census snapshots
by ``employee_id``, classifies the observed transitions, and fits the exact
parameters the simulator already consumes (hazard seed CSVs + config YAML
fragments) into a self-describing **parameter pack**.

The pack is a drop-in: ``planalign simulate --params <pack_dir>`` applies it
with no simulator changes downstream of config loading, and stamps the pack's
fingerprint into ``run_metadata`` (extends Feature 109).

See ``docs/guides/parameter_fitting.md`` for the full workflow.
"""

from __future__ import annotations

from planalign_fit.bands import Band, BandDefinitions, load_band_definitions
from planalign_fit.models import FitResult, FittedValue, HazardFit, Unfittable
from planalign_fit.pack import (
    PackError,
    PackManifest,
    ParameterPack,
    deep_merge,
    load_pack,
    verify_pack,
    write_pack,
)
from planalign_fit.priors import Priors, load_priors
from planalign_fit.report import render_fit_report
from planalign_fit.runner import FitOptions, FitRun, fit_parameter_pack
from planalign_fit.smoothing import CredibilityResult, shrink_toward
from planalign_fit.snapshots import Snapshot, SnapshotError, SnapshotSet, load_snapshots
from planalign_fit.transitions import TransitionSet, build_transitions

__all__ = [
    "Band",
    "BandDefinitions",
    "CredibilityResult",
    "FitOptions",
    "FitResult",
    "FitRun",
    "FittedValue",
    "HazardFit",
    "PackError",
    "PackManifest",
    "ParameterPack",
    "Priors",
    "Snapshot",
    "SnapshotError",
    "SnapshotSet",
    "TransitionSet",
    "Unfittable",
    "build_transitions",
    "deep_merge",
    "fit_parameter_pack",
    "load_band_definitions",
    "load_pack",
    "load_priors",
    "load_snapshots",
    "render_fit_report",
    "shrink_toward",
    "verify_pack",
    "write_pack",
]
