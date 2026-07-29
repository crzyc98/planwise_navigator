"""The priors a fit shrinks toward: today's seed CSVs and config values.

Issue #443's rule is that thin cells fall back toward *the current seed value*,
not toward an arbitrary constant, so the fitter reads the shipped seeds and the
base config rather than hard-coding defaults. Everything here is read-only —
the fitter never writes into ``dbt/seeds`` or the base config.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from planalign_fit.bands import (
    AGE_SEGMENTS,
    DEFAULT_SEEDS_DIR,
    DEFERRAL_SEED_INCOME_SEGMENTS,
    INCOME_SEGMENTS,
)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "simulation_config.yaml"
)

TERMINATION_BASE_SEED = "config_termination_hazard_base.csv"
TERMINATION_AGE_SEED = "config_termination_hazard_age_multipliers.csv"
TERMINATION_TENURE_SEED = "config_termination_hazard_tenure_multipliers.csv"
PROMOTION_BASE_SEED = "config_promotion_hazard_base.csv"
PROMOTION_AGE_SEED = "config_promotion_hazard_age_multipliers.csv"
PROMOTION_TENURE_SEED = "config_promotion_hazard_tenure_multipliers.csv"
COMP_LEVERS_SEED = "comp_levers.csv"
DEFERRAL_RATES_SEED = "default_deferral_rates.csv"


class PriorsError(ValueError):
    """Current seeds or config could not be read."""


@dataclass(frozen=True)
class HazardPriors:
    """Current values of one multiplicative hazard's parameters."""

    base_rate: float
    age_multipliers: dict[str, float]
    tenure_multipliers: dict[str, float]
    # Structural constants the fitter holds fixed (see FitReport's
    # "not fitted" section for why).
    level_constants: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Priors:
    """Every prior a fit can shrink toward."""

    termination: HazardPriors
    promotion: HazardPriors
    merit_by_level: dict[int, float]
    cola_by_level: dict[int, float]
    deferral_rates: dict[tuple[str, str], float]
    config: Mapping[str, Any]
    seeds_dir: Path
    config_path: Path

    def config_value(self, path: str, default: Any = None) -> Any:
        """Read a dotted path out of the base config, or ``default``."""
        node: Any = self.config
        for key in path.split("."):
            if not isinstance(node, Mapping) or key not in node:
                return default
            node = node[key]
        return node


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise PriorsError(f"Seed not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _single_row(path: Path) -> dict[str, str]:
    rows = _read_csv(path)
    if len(rows) != 1:
        raise PriorsError(f"Expected exactly one row in {path.name}, found {len(rows)}")
    return rows[0]


def _multipliers(path: Path, key: str) -> dict[str, float]:
    return {row[key]: float(row["multiplier"]) for row in _read_csv(path)}


def _termination_priors(seeds_dir: Path) -> HazardPriors:
    base = _single_row(seeds_dir / TERMINATION_BASE_SEED)
    return HazardPriors(
        base_rate=float(base["base_rate_for_new_hire"]),
        age_multipliers=_multipliers(seeds_dir / TERMINATION_AGE_SEED, "age_band"),
        tenure_multipliers=_multipliers(
            seeds_dir / TERMINATION_TENURE_SEED, "tenure_band"
        ),
        level_constants={
            "level_discount_factor": float(base["level_discount_factor"]),
            "min_level_discount_multiplier": float(
                base["min_level_discount_multiplier"]
            ),
        },
    )


def _promotion_priors(seeds_dir: Path) -> HazardPriors:
    base = _single_row(seeds_dir / PROMOTION_BASE_SEED)
    return HazardPriors(
        base_rate=float(base["base_rate"]),
        age_multipliers=_multipliers(seeds_dir / PROMOTION_AGE_SEED, "age_band"),
        tenure_multipliers=_multipliers(
            seeds_dir / PROMOTION_TENURE_SEED, "tenure_band"
        ),
        level_constants={
            "level_dampener_factor": float(base["level_dampener_factor"]),
        },
    )


def _comp_lever_values(
    seeds_dir: Path, parameter_name: str, scenario_id: str = "default"
) -> dict[int, float]:
    """Latest per-level value of a RAISE lever across fiscal years."""
    latest: dict[int, tuple[int, float]] = {}
    for row in _read_csv(seeds_dir / COMP_LEVERS_SEED):
        if row.get("scenario_id") != scenario_id:
            continue
        if (
            row.get("event_type") != "RAISE"
            or row.get("parameter_name") != parameter_name
        ):
            continue
        try:
            level = int(row["job_level"])
            year = int(row["fiscal_year"])
            value = float(row["parameter_value"])
        except (KeyError, TypeError, ValueError):
            continue
        if level not in latest or year > latest[level][0]:
            latest[level] = (year, value)
    return {level: value for level, (_, value) in latest.items()}


def _deferral_priors(seeds_dir: Path) -> dict[tuple[str, str], float]:
    """Default deferral rate keyed by (age_segment, income_segment).

    Income segments are translated from the seed's ``low_income`` spelling to
    the ``low`` used by the enrollment SQL so every fit speaks one dialect.
    """
    translate = dict(zip(DEFERRAL_SEED_INCOME_SEGMENTS, INCOME_SEGMENTS))
    rates: dict[tuple[str, str], float] = {}
    for row in _read_csv(seeds_dir / DEFERRAL_RATES_SEED):
        if row.get("scenario_id") != "default":
            continue
        age_segment = row.get("age_segment", "")
        income_segment = translate.get(
            row.get("income_segment", ""), row.get("income_segment", "")
        )
        if age_segment in AGE_SEGMENTS and income_segment in INCOME_SEGMENTS:
            rates[(age_segment, income_segment)] = float(row["default_rate"])
    return rates


def load_priors(
    seeds_dir: Path | str | None = None,
    config_path: Path | str | None = None,
) -> Priors:
    """Read the shipped seeds and base config as the priors for a fit."""
    seeds = Path(seeds_dir) if seeds_dir else DEFAULT_SEEDS_DIR
    config_file = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not config_file.is_file():
        raise PriorsError(f"Base config not found: {config_file}")
    with config_file.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    return Priors(
        termination=_termination_priors(seeds),
        promotion=_promotion_priors(seeds),
        merit_by_level=_comp_lever_values(seeds, "merit_base"),
        cola_by_level=_comp_lever_values(seeds, "cola_rate"),
        deferral_rates=_deferral_priors(seeds),
        config=config,
        seeds_dir=seeds,
        config_path=config_file,
    )


def prior_for_bands(
    priors: Mapping[str, float], labels: Sequence[str], default: float = 1.0
) -> dict[str, float]:
    """Prior per band label, defaulting bands the current seeds do not cover."""
    return {label: priors.get(label, default) for label in labels}


def optional_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
