"""Band and segment definitions, read from the seeds the simulator already uses.

Fitted cells must line up 1:1 with the simulator's grouping, so the band edges
come from ``config_age_bands.csv`` / ``config_tenure_bands.csv`` (the same
sources behind the ``assign_age_band`` / ``assign_tenure_band`` macros) and the
level edges from ``config_job_levels.csv``. Bands use the repository's
``[min, max)`` convention: lower bound inclusive, upper bound exclusive.

The demographic *segments* (young/mid_career/mature/senior and
low/moderate/high/executive) are hard-coded in the enrollment SQL rather than
seeded, so they are mirrored here as constants with a pointer to their source.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_SEEDS_DIR = Path(__file__).resolve().parents[1] / "dbt" / "seeds"

AGE_BANDS_SEED = "config_age_bands.csv"
TENURE_BANDS_SEED = "config_tenure_bands.csv"
JOB_LEVELS_SEED = "config_job_levels.csv"

# Mirrors dbt/models/intermediate/int_voluntary_enrollment_decision.sql. Upper
# bound exclusive, consistent with the band convention above.
AGE_SEGMENT_EDGES: tuple[tuple[str, float], ...] = (
    ("young", 31.0),
    ("mid_career", 46.0),
    ("mature", 56.0),
    ("senior", float("inf")),
)
INCOME_SEGMENT_EDGES: tuple[tuple[str, float], ...] = (
    ("low", 50_000.0),
    ("moderate", 100_000.0),
    ("high", 200_000.0),
    ("executive", float("inf")),
)

AGE_SEGMENTS = tuple(name for name, _ in AGE_SEGMENT_EDGES)
INCOME_SEGMENTS = tuple(name for name, _ in INCOME_SEGMENT_EDGES)

# default_deferral_rates.csv spells the lowest income segment 'low_income',
# while the enrollment SQL spells it 'low'. Keep both, translate at the edge.
DEFERRAL_SEED_INCOME_SEGMENTS = ("low_income", "moderate", "high", "executive")


class BandDefinitionError(ValueError):
    """Band or level seeds could not be read."""


@dataclass(frozen=True)
class Band:
    """One ``[min_value, max_value)`` band."""

    band_id: int
    label: str
    min_value: float
    max_value: float
    display_order: int

    def contains(self, value: float) -> bool:
        return self.min_value <= value < self.max_value


@dataclass(frozen=True)
class Level:
    """One job level with its compensation range (upper bound exclusive)."""

    level_id: int
    name: str
    min_compensation: float
    max_compensation: float


@dataclass(frozen=True)
class BandDefinitions:
    """The grouping the fitter and the simulator share."""

    age_bands: tuple[Band, ...]
    tenure_bands: tuple[Band, ...]
    levels: tuple[Level, ...]

    @property
    def age_band_labels(self) -> tuple[str, ...]:
        return tuple(b.label for b in self.age_bands)

    @property
    def tenure_band_labels(self) -> tuple[str, ...]:
        return tuple(b.label for b in self.tenure_bands)

    @property
    def level_ids(self) -> tuple[int, ...]:
        return tuple(level.level_id for level in self.levels)

    def age_band_case(self, column: str) -> str:
        return _band_case(column, self.age_bands)

    def tenure_band_case(self, column: str) -> str:
        return _band_case(column, self.tenure_bands)

    def level_case(self, column: str) -> str:
        """SQL that assigns the lowest level whose comp range contains ``column``.

        Mirrors ``int_baseline_workforce``: unmatched compensation falls back to
        level 1.
        """
        ordered = sorted(self.levels, key=lambda level: level.level_id)
        whens = "\n".join(
            f"    WHEN {column} >= {level.min_compensation} "
            f"AND {column} < {level.max_compensation} THEN {level.level_id}"
            for level in ordered
        )
        return f"CASE\n{whens}\n    ELSE 1\n  END"

    def age_segment_case(self, column: str) -> str:
        return _segment_case(column, AGE_SEGMENT_EDGES)

    def income_segment_case(self, column: str) -> str:
        return _segment_case(column, INCOME_SEGMENT_EDGES)


def _band_case(column: str, bands: Sequence[Band]) -> str:
    ordered = sorted(bands, key=lambda b: b.min_value)
    whens = "\n".join(
        f"    WHEN {column} >= {b.min_value} AND {column} < {b.max_value} "
        f"THEN '{b.label}'"
        for b in ordered
    )
    fallback = ordered[-1].label if ordered else "unknown"
    return f"CASE\n{whens}\n    ELSE '{fallback}'\n  END"


def _segment_case(column: str, edges: Sequence[tuple[str, float]]) -> str:
    parts = []
    for name, upper in edges:
        if upper == float("inf"):
            parts.append(f"    ELSE '{name}'")
        else:
            parts.append(f"    WHEN {column} < {upper} THEN '{name}'")
    body = "\n".join(parts)
    return f"CASE\n{body}\n  END"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise BandDefinitionError(f"Seed not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parse_bands(rows: Sequence[dict[str, str]], source: Path) -> tuple[Band, ...]:
    bands: list[Band] = []
    for row in rows:
        try:
            bands.append(
                Band(
                    band_id=int(row["band_id"]),
                    label=row["band_label"],
                    min_value=float(row["min_value"]),
                    max_value=float(row["max_value"]),
                    display_order=int(row["display_order"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BandDefinitionError(f"Malformed band row in {source}: {row}") from exc
    if not bands:
        raise BandDefinitionError(f"No bands defined in {source}")
    return tuple(sorted(bands, key=lambda b: b.display_order))


def _parse_levels(rows: Sequence[dict[str, str]], source: Path) -> tuple[Level, ...]:
    levels: list[Level] = []
    for row in rows:
        try:
            raw_max = row.get("max_compensation") or ""
            levels.append(
                Level(
                    level_id=int(row["level_id"]),
                    name=row.get("name") or f"L{row['level_id']}",
                    min_compensation=float(row["min_compensation"]),
                    max_compensation=float(raw_max) if raw_max else float("inf"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BandDefinitionError(
                f"Malformed level row in {source}: {row}"
            ) from exc
    if not levels:
        raise BandDefinitionError(f"No job levels defined in {source}")
    return tuple(sorted(levels, key=lambda level: level.level_id))


def load_band_definitions(seeds_dir: Path | str | None = None) -> BandDefinitions:
    """Read age bands, tenure bands, and job levels from the dbt seeds."""
    root = Path(seeds_dir) if seeds_dir else DEFAULT_SEEDS_DIR
    age_path = root / AGE_BANDS_SEED
    tenure_path = root / TENURE_BANDS_SEED
    levels_path = root / JOB_LEVELS_SEED
    return BandDefinitions(
        age_bands=_parse_bands(_read_csv(age_path), age_path),
        tenure_bands=_parse_bands(_read_csv(tenure_path), tenure_path),
        levels=_parse_levels(_read_csv(levels_path), levels_path),
    )
