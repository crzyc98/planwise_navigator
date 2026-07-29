"""The fitted **parameter pack**: what a fit produces and a simulation consumes.

A pack is a directory, not a bundle format, so it can be diffed and reviewed::

    <pack>/
      manifest.json      provenance: pack id, fingerprint, fit date, source hashes
      parameters.yaml    config fragment, deep-merged over the base config
      seeds/*.csv        drop-in replacements for the dbt seeds it fits
      fit_report.md      sample sizes, confidence, and what could not be fitted

The seed CSVs keep the exact schema of the seeds they replace, so the overlay
project ``planalign simulate --params`` builds is a plain file swap. The
fingerprint covers the fragment and every seed byte, and lands in
``run_metadata`` for any run that uses the pack (extends Feature 109).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from _version import __version__
from planalign_fit.bands import (
    BandDefinitions,
    DEFERRAL_SEED_INCOME_SEGMENTS,
    INCOME_SEGMENTS,
)
from planalign_fit.models import FitResult, FittedValue, HazardFit
from planalign_fit.priors import (
    COMP_LEVERS_SEED,
    DEFERRAL_RATES_SEED,
    PROMOTION_AGE_SEED,
    PROMOTION_BASE_SEED,
    PROMOTION_TENURE_SEED,
    TERMINATION_AGE_SEED,
    TERMINATION_BASE_SEED,
    TERMINATION_TENURE_SEED,
    Priors,
)
from planalign_fit.snapshots import SnapshotSet

MANIFEST_FILENAME = "manifest.json"
PARAMETERS_FILENAME = "parameters.yaml"
REPORT_FILENAME = "fit_report.md"
SEEDS_DIRNAME = "seeds"

# Enough precision for a rate, few enough digits to review by eye.
VALUE_PRECISION = 6


class PackError(ValueError):
    """A parameter pack could not be built, written, or read."""


@dataclass(frozen=True)
class SourceSnapshot:
    """One census file a fit consumed."""

    year: int
    filename: str
    sha256: str
    row_count: int


@dataclass(frozen=True)
class PackManifest:
    """Everything needed to say where a pack came from and reproduce it."""

    pack_id: str
    fingerprint: str
    fit_date: str
    planalign_version: str
    snapshot_years: list[int]
    sources: list[SourceSnapshot]
    source_digest: str
    credibility_k: float
    min_exposure: float
    base_config: str
    base_seeds: str
    notes: str = ""
    unfittable: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = [asdict(s) for s in self.sources]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PackManifest":
        data = dict(payload)
        data["sources"] = [SourceSnapshot(**s) for s in data.get("sources", [])]
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True)
class ParameterPack:
    """A fitted pack in memory: provenance, config fragment, and seed files."""

    manifest: PackManifest
    config_fragment: dict[str, Any]
    seed_files: dict[str, str]

    def seed_names(self) -> list[str]:
        return sorted(self.seed_files)


def _round(value: float) -> float:
    return round(float(value), VALUE_PRECISION)


def _csv_text(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _multiplier_csv(key: str, values: Mapping[str, FittedValue]) -> str:
    return _csv_text(
        [key, "multiplier"],
        [
            {key: label, "multiplier": _round(value.value)}
            for label, value in values.items()
        ],
    )


def _termination_seeds(fit: HazardFit) -> dict[str, str]:
    constants = fit.level_constants
    return {
        TERMINATION_BASE_SEED: _csv_text(
            [
                "base_rate_for_new_hire",
                "level_discount_factor",
                "min_level_discount_multiplier",
            ],
            [
                {
                    "base_rate_for_new_hire": _round(fit.base_rate.value),
                    "level_discount_factor": constants["level_discount_factor"],
                    "min_level_discount_multiplier": constants[
                        "min_level_discount_multiplier"
                    ],
                }
            ],
        ),
        TERMINATION_AGE_SEED: _multiplier_csv("age_band", fit.age_multipliers),
        TERMINATION_TENURE_SEED: _multiplier_csv("tenure_band", fit.tenure_multipliers),
    }


def _promotion_seeds(fit: HazardFit) -> dict[str, str]:
    return {
        PROMOTION_BASE_SEED: _csv_text(
            ["base_rate", "level_dampener_factor"],
            [
                {
                    "base_rate": _round(fit.base_rate.value),
                    "level_dampener_factor": fit.level_constants[
                        "level_dampener_factor"
                    ],
                }
            ],
        ),
        PROMOTION_AGE_SEED: _multiplier_csv("age_band", fit.age_multipliers),
        PROMOTION_TENURE_SEED: _multiplier_csv("tenure_band", fit.tenure_multipliers),
    }


def _read_seed_rows(
    seeds_dir: Path, filename: str
) -> tuple[list[str], list[dict[str, str]]]:
    path = seeds_dir / filename
    if not path.is_file():
        raise PackError(f"Cannot build a pack without the base seed {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def _comp_levers_seed(seeds_dir: Path, merit: Mapping[int, FittedValue]) -> str:
    """Replace every ``merit_base`` value in comp_levers, leaving other levers alone."""
    fieldnames, rows = _read_seed_rows(seeds_dir, COMP_LEVERS_SEED)
    for row in rows:
        if (
            row.get("event_type") != "RAISE"
            or row.get("parameter_name") != "merit_base"
        ):
            continue
        try:
            level = int(row["job_level"])
        except (KeyError, TypeError, ValueError):
            continue
        fitted = merit.get(level)
        if fitted is not None:
            row["parameter_value"] = _round(fitted.value)
    return _csv_text(fieldnames, rows)


def _deferral_seed(
    seeds_dir: Path, rates: Mapping[tuple[str, str], FittedValue]
) -> str:
    """Replace every ``default_rate``, translating the seed's income spelling."""
    fieldnames, rows = _read_seed_rows(seeds_dir, DEFERRAL_RATES_SEED)
    translate = dict(zip(DEFERRAL_SEED_INCOME_SEGMENTS, INCOME_SEGMENTS))
    for row in rows:
        key = (
            row.get("age_segment", ""),
            translate.get(row.get("income_segment", ""), row.get("income_segment", "")),
        )
        fitted = rates.get(key)
        if fitted is not None:
            row["default_rate"] = _round(fitted.value)
    return _csv_text(fieldnames, rows)


def _nest(overrides: Mapping[str, FittedValue]) -> dict[str, Any]:
    """Turn dotted config paths into the nested mapping a YAML fragment needs."""
    fragment: dict[str, Any] = {}
    for path, fitted in sorted(overrides.items()):
        node = fragment
        keys = path.split(".")
        for key in keys[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise PackError(f"Conflicting config override path: {path}")
        node[keys[-1]] = _round(fitted.value)
    return fragment


def _fingerprint(
    config_fragment: Mapping[str, Any],
    seed_files: Mapping[str, str],
    source_digest: str,
) -> str:
    """SHA-256 over the pack's effective content — fragment, seeds, and sources."""
    payload = {
        "config_fragment": config_fragment,
        "seeds": {
            name: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for name, text in sorted(seed_files.items())
        },
        "source_digest": source_digest,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_pack(
    *,
    result: FitResult,
    snapshot_set: SnapshotSet,
    priors: Priors,
    bands: BandDefinitions,
    credibility_k: float,
    min_exposure: float,
    pack_id: Optional[str] = None,
    notes: str = "",
    fit_date: Optional[datetime] = None,
) -> ParameterPack:
    """Assemble a pack from a completed fit. Writes nothing."""
    del bands  # cell grouping is already baked into the fitted values

    seed_files: dict[str, str] = {}
    if result.termination is not None:
        seed_files.update(_termination_seeds(result.termination))
    if result.promotion is not None:
        seed_files.update(_promotion_seeds(result.promotion))
    if result.merit_by_level:
        seed_files[COMP_LEVERS_SEED] = _comp_levers_seed(
            priors.seeds_dir, result.merit_by_level
        )
    if result.deferral_rates:
        seed_files[DEFERRAL_RATES_SEED] = _deferral_seed(
            priors.seeds_dir, result.deferral_rates
        )

    config_fragment = _nest(result.config_overrides)
    fingerprint = _fingerprint(config_fragment, seed_files, snapshot_set.source_digest)
    stamped = fit_date or datetime.now(timezone.utc)

    manifest = PackManifest(
        pack_id=pack_id or _default_pack_id(snapshot_set, stamped),
        fingerprint=fingerprint,
        fit_date=stamped.isoformat(),
        planalign_version=__version__,
        snapshot_years=list(snapshot_set.years),
        sources=[
            SourceSnapshot(
                year=s.year,
                filename=s.path.name,
                sha256=s.sha256,
                row_count=s.row_count,
            )
            for s in snapshot_set
        ],
        source_digest=snapshot_set.source_digest,
        credibility_k=credibility_k,
        min_exposure=min_exposure,
        base_config=str(priors.config_path),
        base_seeds=str(priors.seeds_dir),
        notes=notes,
        unfittable=[u.to_dict() for u in result.unfittable],
        warnings=list(result.warnings),
    )
    return ParameterPack(
        manifest=manifest, config_fragment=config_fragment, seed_files=seed_files
    )


def _default_pack_id(snapshot_set: SnapshotSet, stamped: datetime) -> str:
    years = snapshot_set.years
    return f"fit-{years[0]}-{years[-1]}-{stamped.strftime('%Y%m%dT%H%M%SZ')}"


def write_pack(
    pack: ParameterPack,
    output_dir: Path | str,
    *,
    report: str = "",
    force: bool = False,
) -> Path:
    """Materialize a pack on disk. Refuses to overwrite unless ``force``."""
    destination = Path(output_dir)
    if destination.exists() and any(destination.iterdir()):
        if not force:
            raise PackError(
                f"{destination} already exists and is not empty. Pass --force to "
                "replace it, or choose a new output directory."
            )
        shutil.rmtree(destination)

    seeds_dir = destination / SEEDS_DIRNAME
    seeds_dir.mkdir(parents=True, exist_ok=True)

    (destination / MANIFEST_FILENAME).write_text(
        json.dumps(pack.manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / PARAMETERS_FILENAME).write_text(
        _render_fragment(pack), encoding="utf-8"
    )
    for name, text in pack.seed_files.items():
        (seeds_dir / name).write_text(text, encoding="utf-8")
    if report:
        (destination / REPORT_FILENAME).write_text(report, encoding="utf-8")
    return destination


def _render_fragment(pack: ParameterPack) -> str:
    header = (
        "# Fitted parameter pack — config fragment\n"
        f"# pack_id:     {pack.manifest.pack_id}\n"
        f"# fingerprint: {pack.manifest.fingerprint}\n"
        f"# fitted:      {pack.manifest.fit_date} from "
        f"{', '.join(str(y) for y in pack.manifest.snapshot_years)}\n"
        "#\n"
        "# Deep-merged over the base config by `planalign simulate --params`.\n"
        "# Every value here was fitted from the source snapshots; anything absent\n"
        "# kept its base-config value (see fit_report.md).\n"
    )
    body = yaml.safe_dump(
        pack.config_fragment, default_flow_style=False, sort_keys=True
    )
    return header + body


def load_pack(pack_dir: Path | str) -> ParameterPack:
    """Read a pack written by :func:`write_pack`."""
    root = Path(pack_dir)
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise PackError(
            f"{root} is not a parameter pack: no {MANIFEST_FILENAME}. Point "
            "--params at a directory produced by `planalign fit`."
        )
    try:
        manifest = PackManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PackError(f"Corrupt manifest in {manifest_path}: {exc}") from exc

    fragment_path = root / PARAMETERS_FILENAME
    config_fragment: dict[str, Any] = {}
    if fragment_path.is_file():
        config_fragment = (
            yaml.safe_load(fragment_path.read_text(encoding="utf-8")) or {}
        )

    seeds_dir = root / SEEDS_DIRNAME
    seed_files = (
        {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(seeds_dir.glob("*.csv"))
        }
        if seeds_dir.is_dir()
        else {}
    )
    return ParameterPack(
        manifest=manifest, config_fragment=config_fragment, seed_files=seed_files
    )


def verify_pack(pack: ParameterPack) -> bool:
    """True when the pack's content still hashes to its recorded fingerprint."""
    return (
        _fingerprint(pack.config_fragment, pack.seed_files, pack.manifest.source_digest)
        == pack.manifest.fingerprint
    )


def deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` into a copy of ``base``; overlay wins."""
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged
