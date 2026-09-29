"""Turn a reviewed parameter pack into a NEW Studio scenario (#588).

A pack is two things: a config fragment and replacement seed CSVs. Studio
scenarios are config overrides, and every Studio run rebuilds its seeds from
the shipped defaults and then rewrites the promotion-hazard and band seeds
from (always-present) config. So applying a pack means:

* overrides = source overrides + pack fragment + ``param_pack`` provenance;
* the pack's promotion seeds become the scenario's ``promotion_hazard``
  section — visible and editable in Studio's promotion-hazard editor, and an
  edit there wins, exactly like any other scenario setting;
* the pack itself is copied to ``scenarios/<id>/param_pack/`` and its seeds are
  layered over the defaults on every run (``write_seeds``), covering the seeds
  Studio has no editor for (termination hazard, merit levers, deferral rates).

The source scenario is never touched.
"""

from __future__ import annotations

import csv
import io
import shutil
from pathlib import Path
from typing import Any, Iterable, Optional

from planalign_fit.apply import provenance_block
from planalign_fit.pack import deep_merge
from planalign_fit.priors import (
    PROMOTION_AGE_SEED,
    PROMOTION_BASE_SEED,
    PROMOTION_TENURE_SEED,
)

from ...models.comparison import ConfigDelta
from ...models.scenario import Scenario, ScenarioCreate
from ...storage.workspace_storage import WorkspaceStorage
from ..config_diff_service import diff_configs
from .results import PackState

PACK_DIRNAME = "param_pack"
PROVENANCE_KEY = "param_pack"


def promotion_hazard_from_pack(
    seed_files: dict[str, str],
) -> Optional[dict[str, Any]]:
    """The pack's promotion seeds in the ``promotion_hazard`` config schema."""
    names = (PROMOTION_BASE_SEED, PROMOTION_AGE_SEED, PROMOTION_TENURE_SEED)
    if not all(name in seed_files for name in names):
        return None
    base = _rows(seed_files[PROMOTION_BASE_SEED])[0]
    return {
        "base_rate": float(base["base_rate"]),
        "level_dampener_factor": float(base["level_dampener_factor"]),
        "age_multipliers": [
            {"age_band": row["age_band"], "multiplier": float(row["multiplier"])}
            for row in _rows(seed_files[PROMOTION_AGE_SEED])
        ],
        "tenure_multipliers": [
            {"tenure_band": row["tenure_band"], "multiplier": float(row["multiplier"])}
            for row in _rows(seed_files[PROMOTION_TENURE_SEED])
        ],
    }


def build_overrides(
    source_overrides: dict[str, Any], state: PackState, pack_dir: Path
) -> dict[str, Any]:
    """The new scenario's overrides: source + fragment + hazard + provenance."""
    pack = state.pack
    overrides = deep_merge(source_overrides, pack.config_fragment)
    hazard = promotion_hazard_from_pack(pack.seed_files)
    if hazard is not None:
        overrides["promotion_hazard"] = hazard
    block = provenance_block(pack.manifest, pack=pack, pack_dir=pack_dir)
    # Only a verified, current scorecard is recorded as this pack's backtest.
    block.pop("backtest", None)
    if state.backtest is not None:
        block["backtest"] = state.backtest
    overrides[PROVENANCE_KEY] = block
    return overrides


def required_acknowledgements(state: PackState, thin_count: Optional[int]) -> list[str]:
    """Conditions the analyst must explicitly accept before applying (FR-025)."""
    required: list[str] = []
    if thin_count:
        required.append("thin_cells")
    if state.pack.manifest.unfittable:
        required.append("unfittable")
    verdict = (state.backtest or {}).get("verdict")
    if verdict is None:
        required.append("no_backtest")
    elif verdict in ("warn", "fail"):
        required.append(f"backtest_{verdict}")
    return required


def config_diff(before: dict[str, Any], after: dict[str, Any]) -> list[ConfigDelta]:
    """What applying changes, minus the provenance block shown separately."""
    deltas, _ = diff_configs(
        _without(before, PROVENANCE_KEY), _without(after, PROVENANCE_KEY)
    )
    return deltas


def unique_name(base_name: str, existing: Iterable[str]) -> str:
    """Mirror the optimizer's name-collision suffixing: ``Name (2)``, …"""
    taken = {name.lower() for name in existing}
    counter = 2
    while f"{base_name} ({counter})".lower() in taken:
        counter += 1
    return f"{base_name} ({counter})"


def create_pack_scenario(
    storage: WorkspaceStorage,
    workspace_id: str,
    create: ScenarioCreate,
    pack_dir: Path,
) -> Optional[Scenario]:
    """Create the scenario and copy the pack beside it, all or nothing."""
    scenario = storage.create_scenario(workspace_id, create)
    if scenario is None:
        return None
    target = storage._scenario_path(workspace_id, scenario.id) / PACK_DIRNAME
    try:
        shutil.copytree(pack_dir, target)
    except OSError:
        storage.delete_scenario(workspace_id, scenario.id)
        raise
    return scenario


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _without(config: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in config.items() if name != key}
