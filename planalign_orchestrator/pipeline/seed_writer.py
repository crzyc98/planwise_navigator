"""
Seed Writer Module

Writes configuration dictionaries to CSV seed files for dbt consumption.
Handles promotion hazard parameters, age bands, and tenure bands.
"""

import csv
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_promotion_hazard_csvs(config: dict[str, Any], seeds_dir: Path) -> None:
    """
    Write promotion hazard configuration to CSV seed files.

    Args:
        config: Dictionary with keys:
            - base_rate: float
            - level_dampener_factor: float
            - age_multipliers: list of dicts with {age_band, multiplier}
            - tenure_multipliers: list of dicts with {tenure_band, multiplier}
        seeds_dir: Path to dbt seeds directory
    """
    # Write base configuration (atomic)
    base_file = seeds_dir / "config_promotion_hazard_base.csv"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=seeds_dir, suffix=".csv.tmp")
    try:
        with os.fdopen(tmp_fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["base_rate", "level_dampener_factor"])
            writer.writeheader()
            writer.writerow({
                "base_rate": config["base_rate"],
                "level_dampener_factor": config["level_dampener_factor"]
            })
        os.replace(tmp_path, str(base_file))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    logger.info(f"Wrote promotion hazard base config to {base_file}")

    # Write age multipliers (atomic)
    age_file = seeds_dir / "config_promotion_hazard_age_multipliers.csv"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=seeds_dir, suffix=".csv.tmp")
    try:
        with os.fdopen(tmp_fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["age_band", "multiplier"])
            writer.writeheader()
            for entry in config["age_multipliers"]:
                writer.writerow({
                    "age_band": entry["age_band"],
                    "multiplier": entry["multiplier"]
                })
        os.replace(tmp_path, str(age_file))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    logger.info(f"Wrote {len(config['age_multipliers'])} age multipliers to {age_file}")

    # Write tenure multipliers (atomic)
    tenure_file = seeds_dir / "config_promotion_hazard_tenure_multipliers.csv"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=seeds_dir, suffix=".csv.tmp")
    try:
        with os.fdopen(tmp_fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["tenure_band", "multiplier"])
            writer.writeheader()
            for entry in config["tenure_multipliers"]:
                writer.writerow({
                    "tenure_band": entry["tenure_band"],
                    "multiplier": entry["multiplier"]
                })
        os.replace(tmp_path, str(tenure_file))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    logger.info(f"Wrote {len(config['tenure_multipliers'])} tenure multipliers to {tenure_file}")


def write_band_csvs(config: dict[str, Any], seeds_dir: Path) -> None:
    """
    Write age and/or tenure band configurations to CSV seed files.

    Args:
        config: Dictionary with optional keys:
            - age_bands: list of dicts with {band_id, band_label, min_value, max_value, display_order}
            - tenure_bands: list of dicts with same structure
        seeds_dir: Path to dbt seeds directory
    """
    fieldnames = ["band_id", "band_label", "min_value", "max_value", "display_order"]

    # Write age bands if present (atomic)
    if "age_bands" in config:
        age_file = seeds_dir / "config_age_bands.csv"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=seeds_dir, suffix=".csv.tmp")
        try:
            with os.fdopen(tmp_fd, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for band in config["age_bands"]:
                    writer.writerow({
                        "band_id": band["band_id"],
                        "band_label": band["band_label"],
                        "min_value": band["min_value"],
                        "max_value": band["max_value"],
                        "display_order": band["display_order"]
                    })
            os.replace(tmp_path, str(age_file))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        logger.info(f"Wrote {len(config['age_bands'])} age bands to {age_file}")

    # Write tenure bands if present (atomic)
    if "tenure_bands" in config:
        tenure_file = seeds_dir / "config_tenure_bands.csv"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=seeds_dir, suffix=".csv.tmp")
        try:
            with os.fdopen(tmp_fd, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for band in config["tenure_bands"]:
                    writer.writerow({
                        "band_id": band["band_id"],
                        "band_label": band["band_label"],
                        "min_value": band["min_value"],
                        "max_value": band["max_value"],
                        "display_order": band["display_order"]
                    })
            os.replace(tmp_path, str(tenure_file))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        logger.info(f"Wrote {len(config['tenure_bands'])} tenure bands to {tenure_file}")


def write_all_seed_csvs(merged_config: dict[str, Any], seeds_dir: Path) -> dict[str, bool]:
    """
    Write all configuration sections to CSV seed files based on merged config.

    Args:
        merged_config: Full merged configuration dictionary from get_merged_config()
        seeds_dir: Path to dbt seeds directory

    Returns:
        Dictionary indicating which sections were written, e.g.:
        {"promotion_hazard": True, "age_bands": True, "tenure_bands": False}
    """
    seeds_dir.mkdir(parents=True, exist_ok=True)

    written_sections = {
        "promotion_hazard": False,
        "age_bands": False,
        "tenure_bands": False
    }

    # Write promotion hazard configuration
    if "promotion_hazard" in merged_config:
        write_promotion_hazard_csvs(merged_config["promotion_hazard"], seeds_dir)
        written_sections["promotion_hazard"] = True
        logger.info("Wrote promotion_hazard configuration to seed CSVs")

    # Write age bands configuration
    if "age_bands" in merged_config:
        write_band_csvs({"age_bands": merged_config["age_bands"]}, seeds_dir)
        written_sections["age_bands"] = True
        logger.info("Wrote age_bands configuration to seed CSVs")

    # Write tenure bands configuration
    if "tenure_bands" in merged_config:
        write_band_csvs({"tenure_bands": merged_config["tenure_bands"]}, seeds_dir)
        written_sections["tenure_bands"] = True
        logger.info("Wrote tenure_bands configuration to seed CSVs")

    # Summary log
    written = [k for k, v in written_sections.items() if v]
    if written:
        logger.info(f"Seed CSV write complete. Sections written: {', '.join(written)}")
    else:
        logger.info("No seed CSV sections written (no matching configuration keys found)")

    return written_sections
