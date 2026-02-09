"""
Seed Configuration Validator

Pure validation logic for seed-based configurations (promotion hazard, age bands, tenure bands).
No database access, no file I/O - just validation rules.

Usage:
    from planalign_api.services.seed_config_validator import validate_seed_configs

    errors = validate_seed_configs(config_overrides)
    if errors:
        # Handle validation errors
        for err in errors:
            print(f"{err.section}.{err.field}: {err.message}")
"""

from dataclasses import dataclass
from typing import List


@dataclass
class SeedConfigValidationError:
    """Structured validation error for seed configurations."""
    section: str  # e.g., "promotion_hazard", "age_bands", "tenure_bands"
    field: str    # e.g., "base_rate", "level_dampener_factor", "band_3"
    message: str  # Human-readable error message


def validate_promotion_hazard(config: dict) -> List[SeedConfigValidationError]:
    """
    Validate promotion hazard configuration.

    Args:
        config: Dict with keys:
            - base_rate: float (0.0-1.0)
            - level_dampener_factor: float (0.0-1.0)
            - age_multipliers: list of {age_band: str, multiplier: float}
            - tenure_multipliers: list of {tenure_band: str, multiplier: float}

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Validate base_rate
    base_rate = config.get("base_rate")
    if base_rate is None:
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="base_rate",
            message="base_rate is required"
        ))
    elif not isinstance(base_rate, (int, float)):
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="base_rate",
            message="base_rate must be a number"
        ))
    elif not (0.0 <= base_rate <= 1.0):
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="base_rate",
            message=f"base_rate must be between 0.0 and 1.0, got {base_rate}"
        ))

    # Validate level_dampener_factor
    level_dampener = config.get("level_dampener_factor")
    if level_dampener is None:
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="level_dampener_factor",
            message="level_dampener_factor is required"
        ))
    elif not isinstance(level_dampener, (int, float)):
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="level_dampener_factor",
            message="level_dampener_factor must be a number"
        ))
    elif not (0.0 <= level_dampener <= 1.0):
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="level_dampener_factor",
            message=f"level_dampener_factor must be between 0.0 and 1.0, got {level_dampener}"
        ))

    # Validate age_multipliers
    age_multipliers = config.get("age_multipliers", [])
    if not isinstance(age_multipliers, list):
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="age_multipliers",
            message="age_multipliers must be a list"
        ))
    else:
        for idx, mult in enumerate(age_multipliers):
            if not isinstance(mult, dict):
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"age_multipliers[{idx}]",
                    message="Each age_multiplier must be a dict"
                ))
                continue

            multiplier_val = mult.get("multiplier")
            if multiplier_val is None:
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"age_multipliers[{idx}].multiplier",
                    message="multiplier is required"
                ))
            elif not isinstance(multiplier_val, (int, float)):
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"age_multipliers[{idx}].multiplier",
                    message="multiplier must be a number"
                ))
            elif multiplier_val < 0:
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"age_multipliers[{idx}].multiplier",
                    message=f"multiplier must be >= 0, got {multiplier_val}"
                ))

            if "age_band" not in mult:
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"age_multipliers[{idx}].age_band",
                    message="age_band is required"
                ))

    # Validate tenure_multipliers
    tenure_multipliers = config.get("tenure_multipliers", [])
    if not isinstance(tenure_multipliers, list):
        errors.append(SeedConfigValidationError(
            section="promotion_hazard",
            field="tenure_multipliers",
            message="tenure_multipliers must be a list"
        ))
    else:
        for idx, mult in enumerate(tenure_multipliers):
            if not isinstance(mult, dict):
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"tenure_multipliers[{idx}]",
                    message="Each tenure_multiplier must be a dict"
                ))
                continue

            multiplier_val = mult.get("multiplier")
            if multiplier_val is None:
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"tenure_multipliers[{idx}].multiplier",
                    message="multiplier is required"
                ))
            elif not isinstance(multiplier_val, (int, float)):
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"tenure_multipliers[{idx}].multiplier",
                    message="multiplier must be a number"
                ))
            elif multiplier_val < 0:
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"tenure_multipliers[{idx}].multiplier",
                    message=f"multiplier must be >= 0, got {multiplier_val}"
                ))

            if "tenure_band" not in mult:
                errors.append(SeedConfigValidationError(
                    section="promotion_hazard",
                    field=f"tenure_multipliers[{idx}].tenure_band",
                    message="tenure_band is required"
                ))

    return errors


def validate_bands(bands: list, band_type: str) -> List[SeedConfigValidationError]:
    """
    Validate age or tenure band configuration.

    Args:
        bands: List of dicts with keys:
            - band_id: str
            - band_label: str
            - min_value: float
            - max_value: float
            - display_order: int
        band_type: "age" or "tenure" (for error messages)

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    section = f"{band_type}_bands"

    # At least one band required
    if not bands:
        errors.append(SeedConfigValidationError(
            section=section,
            field="bands",
            message=f"At least one {band_type} band is required"
        ))
        return errors

    if not isinstance(bands, list):
        errors.append(SeedConfigValidationError(
            section=section,
            field="bands",
            message="bands must be a list"
        ))
        return errors

    # Validate each band structure
    for idx, band in enumerate(bands):
        if not isinstance(band, dict):
            errors.append(SeedConfigValidationError(
                section=section,
                field=f"band[{idx}]",
                message="Each band must be a dict"
            ))
            continue

        # Required fields
        for field in ["band_id", "band_label", "min_value", "max_value", "display_order"]:
            if field not in band:
                errors.append(SeedConfigValidationError(
                    section=section,
                    field=f"band[{idx}].{field}",
                    message=f"{field} is required"
                ))

        # Validate min_value < max_value
        min_val = band.get("min_value")
        max_val = band.get("max_value")

        if min_val is not None and max_val is not None:
            if not isinstance(min_val, (int, float)):
                errors.append(SeedConfigValidationError(
                    section=section,
                    field=f"band[{idx}].min_value",
                    message="min_value must be a number"
                ))
            elif not isinstance(max_val, (int, float)):
                errors.append(SeedConfigValidationError(
                    section=section,
                    field=f"band[{idx}].max_value",
                    message="max_value must be a number"
                ))
            elif max_val <= min_val:
                errors.append(SeedConfigValidationError(
                    section=section,
                    field=f"band[{idx}]",
                    message=f"max_value ({max_val}) must be greater than min_value ({min_val})"
                ))

    # If there were structural errors, return early before checking gaps/overlaps
    if errors:
        return errors

    # Sort bands by min_value for gap/overlap checking
    sorted_bands = sorted(bands, key=lambda b: b["min_value"])

    # First band must start at 0
    if sorted_bands[0]["min_value"] != 0:
        errors.append(SeedConfigValidationError(
            section=section,
            field=f"band[0].min_value",
            message=f"First {band_type} band must start at 0, got {sorted_bands[0]['min_value']}"
        ))

    # Check for gaps and overlaps between consecutive bands
    for i in range(len(sorted_bands) - 1):
        current_band = sorted_bands[i]
        next_band = sorted_bands[i + 1]

        current_max = current_band["max_value"]
        next_min = next_band["min_value"]

        if current_max < next_min:
            # Gap detected
            errors.append(SeedConfigValidationError(
                section=section,
                field=f"band[{i}]-band[{i+1}]",
                message=f"Gap detected: band ending at {current_max} and band starting at {next_min}"
            ))
        elif current_max > next_min:
            # Overlap detected
            errors.append(SeedConfigValidationError(
                section=section,
                field=f"band[{i}]-band[{i+1}]",
                message=f"Overlap detected: band ending at {current_max} overlaps band starting at {next_min}"
            ))

    return errors


def validate_seed_configs(config_overrides: dict) -> List[SeedConfigValidationError]:
    """
    Validate all seed-based configurations.

    Only validates sections that are present in config_overrides.
    Absent sections are allowed (fallback to defaults).

    Args:
        config_overrides: Dict with optional keys:
            - promotion_hazard: dict
            - age_bands: list
            - tenure_bands: list

    Returns:
        Combined list of validation errors from all present sections
    """
    errors = []

    # Validate promotion_hazard if present
    if "promotion_hazard" in config_overrides:
        promotion_hazard = config_overrides["promotion_hazard"]
        if not isinstance(promotion_hazard, dict):
            errors.append(SeedConfigValidationError(
                section="promotion_hazard",
                field="promotion_hazard",
                message="promotion_hazard must be a dict"
            ))
        else:
            errors.extend(validate_promotion_hazard(promotion_hazard))

    # Validate age_bands if present
    if "age_bands" in config_overrides:
        age_bands = config_overrides["age_bands"]
        errors.extend(validate_bands(age_bands, "age"))

    # Validate tenure_bands if present
    if "tenure_bands" in config_overrides:
        tenure_bands = config_overrides["tenure_bands"]
        errors.extend(validate_bands(tenure_bands, "tenure"))

    return errors
