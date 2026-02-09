"""Promotion hazard configuration service.

This service handles reading, validating, and writing promotion hazard
parameters to dbt seed CSV files.
"""

import csv
import logging
from pathlib import Path
from typing import List, Optional

from ..models.promotion_hazard import (
    PromotionHazardAgeMultiplier,
    PromotionHazardBase,
    PromotionHazardConfig,
    PromotionHazardSaveResponse,
    PromotionHazardTenureMultiplier,
)

logger = logging.getLogger(__name__)

# Path to dbt seeds directory (relative to project root)
DBT_SEEDS_DIR = Path(__file__).parent.parent.parent / "dbt" / "seeds"


class PromotionHazardService:
    """Service for promotion hazard configuration management."""

    def __init__(self, dbt_seeds_dir: Optional[Path] = None):
        self.dbt_seeds_dir = dbt_seeds_dir or DBT_SEEDS_DIR

    def read_base_config(self) -> PromotionHazardBase:
        """Read base promotion hazard parameters from CSV."""
        csv_path = self.dbt_seeds_dir / "config_promotion_hazard_base.csv"

        if not csv_path.exists():
            raise FileNotFoundError(f"Promotion hazard base config not found: {csv_path}")

        try:
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                row = next(reader)
                return PromotionHazardBase(
                    base_rate=float(row["base_rate"]),
                    level_dampener_factor=float(row["level_dampener_factor"]),
                )
        except (KeyError, StopIteration) as e:
            raise ValueError(f"Malformed promotion hazard base CSV: {e}")

    def read_age_multipliers(self) -> List[PromotionHazardAgeMultiplier]:
        """Read age band multipliers from CSV."""
        csv_path = self.dbt_seeds_dir / "config_promotion_hazard_age_multipliers.csv"

        if not csv_path.exists():
            raise FileNotFoundError(f"Age multipliers config not found: {csv_path}")

        multipliers = []
        try:
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    multipliers.append(
                        PromotionHazardAgeMultiplier(
                            age_band=row["age_band"],
                            multiplier=float(row["multiplier"]),
                        )
                    )
        except KeyError as e:
            raise ValueError(f"Missing required column in age multipliers CSV: {e}")

        return multipliers

    def read_tenure_multipliers(self) -> List[PromotionHazardTenureMultiplier]:
        """Read tenure band multipliers from CSV."""
        csv_path = self.dbt_seeds_dir / "config_promotion_hazard_tenure_multipliers.csv"

        if not csv_path.exists():
            raise FileNotFoundError(f"Tenure multipliers config not found: {csv_path}")

        multipliers = []
        try:
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    multipliers.append(
                        PromotionHazardTenureMultiplier(
                            tenure_band=row["tenure_band"],
                            multiplier=float(row["multiplier"]),
                        )
                    )
        except KeyError as e:
            raise ValueError(f"Missing required column in tenure multipliers CSV: {e}")

        return multipliers

    def read_all(self) -> PromotionHazardConfig:
        """Read all promotion hazard configuration from CSV seed files."""
        return PromotionHazardConfig(
            base=self.read_base_config(),
            age_multipliers=self.read_age_multipliers(),
            tenure_multipliers=self.read_tenure_multipliers(),
        )

    def validate(self, config: PromotionHazardConfig) -> List[str]:
        """Validate promotion hazard configuration. Returns list of error strings."""
        errors: List[str] = []

        # Validate base parameters
        if config.base.base_rate < 0 or config.base.base_rate > 1:
            errors.append("base_rate must be between 0 and 1")
        if config.base.level_dampener_factor < 0 or config.base.level_dampener_factor > 1:
            errors.append("level_dampener_factor must be between 0 and 1")

        # Validate age multipliers
        if len(config.age_multipliers) != 6:
            errors.append(f"Expected 6 age multipliers, got {len(config.age_multipliers)}")
        for m in config.age_multipliers:
            if m.multiplier < 0:
                errors.append(f"Age multiplier for band '{m.age_band}' must be non-negative")

        # Validate tenure multipliers
        if len(config.tenure_multipliers) != 5:
            errors.append(f"Expected 5 tenure multipliers, got {len(config.tenure_multipliers)}")
        for m in config.tenure_multipliers:
            if m.multiplier < 0:
                errors.append(f"Tenure multiplier for band '{m.tenure_band}' must be non-negative")

        return errors

    def save_all(self, config: PromotionHazardConfig) -> PromotionHazardSaveResponse:
        """Validate and save all promotion hazard configuration to CSV seed files."""
        errors = self.validate(config)
        if errors:
            return PromotionHazardSaveResponse(
                success=False,
                errors=errors,
                message="Validation failed - see errors for details",
            )

        try:
            # Write base config
            base_path = self.dbt_seeds_dir / "config_promotion_hazard_base.csv"
            with open(base_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["base_rate", "level_dampener_factor"])
                writer.writeheader()
                writer.writerow(
                    {
                        "base_rate": config.base.base_rate,
                        "level_dampener_factor": config.base.level_dampener_factor,
                    }
                )

            # Write age multipliers
            age_path = self.dbt_seeds_dir / "config_promotion_hazard_age_multipliers.csv"
            with open(age_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["age_band", "multiplier"])
                writer.writeheader()
                for m in config.age_multipliers:
                    writer.writerow({"age_band": m.age_band, "multiplier": m.multiplier})

            # Write tenure multipliers
            tenure_path = self.dbt_seeds_dir / "config_promotion_hazard_tenure_multipliers.csv"
            with open(tenure_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["tenure_band", "multiplier"])
                writer.writeheader()
                for m in config.tenure_multipliers:
                    writer.writerow({"tenure_band": m.tenure_band, "multiplier": m.multiplier})

            logger.info("Successfully saved promotion hazard configurations")
            return PromotionHazardSaveResponse(
                success=True,
                errors=[],
                message="Promotion hazard configurations saved successfully",
            )
        except IOError as e:
            logger.error(f"Failed to save promotion hazard configurations: {e}")
            return PromotionHazardSaveResponse(
                success=False,
                errors=[str(e)],
                message=f"Failed to save: {e}",
            )
