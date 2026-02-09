"""
Unit tests for planalign_api.services.seed_config_validator.

Tests cover all three public functions:
  - validate_promotion_hazard(config)
  - validate_bands(bands, band_type)
  - validate_seed_configs(config_overrides)
"""

import pytest

from planalign_api.services.seed_config_validator import (
    SeedConfigValidationError,
    validate_bands,
    validate_promotion_hazard,
    validate_seed_configs,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _valid_promotion_hazard() -> dict:
    """Return a minimal valid promotion hazard config."""
    return {
        "base_rate": 0.15,
        "level_dampener_factor": 0.8,
        "age_multipliers": [
            {"age_band": "25-34", "multiplier": 1.2},
            {"age_band": "35-44", "multiplier": 1.0},
        ],
        "tenure_multipliers": [
            {"tenure_band": "0-2", "multiplier": 1.3},
            {"tenure_band": "2-5", "multiplier": 1.0},
        ],
    }


def _valid_band(band_id: str, label: str, min_val: float, max_val: float, order: int) -> dict:
    return {
        "band_id": band_id,
        "band_label": label,
        "min_value": min_val,
        "max_value": max_val,
        "display_order": order,
    }


def _valid_age_bands() -> list:
    """Return a contiguous, valid list of age bands starting at 0."""
    return [
        _valid_band("age_1", "0-25", 0, 25, 1),
        _valid_band("age_2", "25-35", 25, 35, 2),
        _valid_band("age_3", "35-45", 35, 45, 3),
        _valid_band("age_4", "45-55", 45, 55, 4),
        _valid_band("age_5", "55-65", 55, 65, 5),
        _valid_band("age_6", "65+", 65, 120, 6),
    ]


def _valid_tenure_bands() -> list:
    return [
        _valid_band("ten_1", "0-2", 0, 2, 1),
        _valid_band("ten_2", "2-5", 2, 5, 2),
        _valid_band("ten_3", "5-10", 5, 10, 3),
        _valid_band("ten_4", "10-20", 10, 20, 4),
        _valid_band("ten_5", "20+", 20, 50, 5),
    ]


def _field_in_errors(errors, field_substring: str) -> bool:
    """Return True if any error's field contains the given substring."""
    return any(field_substring in e.field for e in errors)


# ===================================================================
# validate_promotion_hazard
# ===================================================================


class TestValidatePromotionHazard:
    """Tests for validate_promotion_hazard()."""

    def test_valid_complete_config_passes(self):
        errors = validate_promotion_hazard(_valid_promotion_hazard())
        assert errors == []

    # --- base_rate ---

    def test_missing_base_rate(self):
        config = _valid_promotion_hazard()
        del config["base_rate"]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "base_rate"
        assert "required" in errors[0].message

    def test_base_rate_negative(self):
        config = _valid_promotion_hazard()
        config["base_rate"] = -0.1
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "base_rate"
        assert "between 0.0 and 1.0" in errors[0].message

    def test_base_rate_greater_than_one(self):
        config = _valid_promotion_hazard()
        config["base_rate"] = 1.5
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "base_rate"
        assert "between 0.0 and 1.0" in errors[0].message

    def test_base_rate_zero_is_valid(self):
        config = _valid_promotion_hazard()
        config["base_rate"] = 0.0
        errors = validate_promotion_hazard(config)
        assert errors == []

    def test_base_rate_one_is_valid(self):
        config = _valid_promotion_hazard()
        config["base_rate"] = 1.0
        errors = validate_promotion_hazard(config)
        assert errors == []

    def test_base_rate_non_numeric(self):
        config = _valid_promotion_hazard()
        config["base_rate"] = "high"
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "base_rate"
        assert "must be a number" in errors[0].message

    def test_base_rate_integer_accepted(self):
        config = _valid_promotion_hazard()
        config["base_rate"] = 1  # int, not float
        errors = validate_promotion_hazard(config)
        assert errors == []

    # --- level_dampener_factor ---

    def test_missing_level_dampener_factor(self):
        config = _valid_promotion_hazard()
        del config["level_dampener_factor"]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "level_dampener_factor"
        assert "required" in errors[0].message

    def test_level_dampener_factor_negative(self):
        config = _valid_promotion_hazard()
        config["level_dampener_factor"] = -0.01
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "level_dampener_factor"
        assert "between 0.0 and 1.0" in errors[0].message

    def test_level_dampener_factor_greater_than_one(self):
        config = _valid_promotion_hazard()
        config["level_dampener_factor"] = 2.0
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "level_dampener_factor"

    def test_level_dampener_factor_non_numeric(self):
        config = _valid_promotion_hazard()
        config["level_dampener_factor"] = "medium"
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "level_dampener_factor"
        assert "must be a number" in errors[0].message

    # --- age_multipliers ---

    def test_missing_age_multipliers(self):
        config = _valid_promotion_hazard()
        del config["age_multipliers"]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "age_multipliers"
        assert "required" in errors[0].message

    def test_age_multipliers_not_a_list(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = "not_a_list"
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "age_multipliers"
        assert "must be a list" in errors[0].message

    def test_age_multiplier_entry_not_a_dict(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = ["bad_entry"]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "age_multipliers[0]" in errors[0].field
        assert "must be a dict" in errors[0].message

    def test_age_multiplier_missing_multiplier_field(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = [{"age_band": "25-34"}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "multiplier" in errors[0].field
        assert "required" in errors[0].message

    def test_age_multiplier_negative_multiplier(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = [{"age_band": "25-34", "multiplier": -0.5}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "multiplier" in errors[0].field
        assert ">= 0" in errors[0].message

    def test_age_multiplier_non_numeric_multiplier(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = [{"age_band": "25-34", "multiplier": "high"}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "multiplier" in errors[0].field
        assert "must be a number" in errors[0].message

    def test_age_multiplier_missing_age_band(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = [{"multiplier": 1.0}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "age_band" in errors[0].field
        assert "required" in errors[0].message

    def test_age_multiplier_zero_multiplier_is_valid(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = [{"age_band": "25-34", "multiplier": 0.0}]
        errors = validate_promotion_hazard(config)
        assert errors == []

    def test_age_multipliers_empty_list_is_valid(self):
        """An empty list is structurally valid (no entries to validate)."""
        config = _valid_promotion_hazard()
        config["age_multipliers"] = []
        errors = validate_promotion_hazard(config)
        assert errors == []

    # --- tenure_multipliers ---

    def test_missing_tenure_multipliers(self):
        config = _valid_promotion_hazard()
        del config["tenure_multipliers"]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "tenure_multipliers"
        assert "required" in errors[0].message

    def test_tenure_multipliers_not_a_list(self):
        config = _valid_promotion_hazard()
        config["tenure_multipliers"] = {"bad": "type"}
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert errors[0].field == "tenure_multipliers"
        assert "must be a list" in errors[0].message

    def test_tenure_multiplier_entry_not_a_dict(self):
        config = _valid_promotion_hazard()
        config["tenure_multipliers"] = [42]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "tenure_multipliers[0]" in errors[0].field
        assert "must be a dict" in errors[0].message

    def test_tenure_multiplier_missing_multiplier_field(self):
        config = _valid_promotion_hazard()
        config["tenure_multipliers"] = [{"tenure_band": "0-2"}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "multiplier" in errors[0].field
        assert "required" in errors[0].message

    def test_tenure_multiplier_negative_multiplier(self):
        config = _valid_promotion_hazard()
        config["tenure_multipliers"] = [{"tenure_band": "0-2", "multiplier": -1}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "multiplier" in errors[0].field
        assert ">= 0" in errors[0].message

    def test_tenure_multiplier_non_numeric_multiplier(self):
        config = _valid_promotion_hazard()
        config["tenure_multipliers"] = [{"tenure_band": "0-2", "multiplier": None}]
        errors = validate_promotion_hazard(config)
        # None is caught by "is None" check -> "multiplier is required"
        assert len(errors) == 1
        assert "required" in errors[0].message

    def test_tenure_multiplier_missing_tenure_band(self):
        config = _valid_promotion_hazard()
        config["tenure_multipliers"] = [{"multiplier": 1.0}]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 1
        assert "tenure_band" in errors[0].field
        assert "required" in errors[0].message

    # --- multiple errors ---

    def test_multiple_missing_fields_all_reported(self):
        """All four required fields missing produces four errors."""
        errors = validate_promotion_hazard({})
        assert len(errors) == 4
        fields = {e.field for e in errors}
        assert fields == {"base_rate", "level_dampener_factor", "age_multipliers", "tenure_multipliers"}

    def test_multiple_bad_multiplier_entries(self):
        config = _valid_promotion_hazard()
        config["age_multipliers"] = [
            {"age_band": "25-34", "multiplier": -1},
            {"multiplier": 1.0},  # missing age_band
        ]
        errors = validate_promotion_hazard(config)
        assert len(errors) == 2

    def test_section_is_always_promotion_hazard(self):
        errors = validate_promotion_hazard({})
        for e in errors:
            assert e.section == "promotion_hazard"


# ===================================================================
# validate_bands
# ===================================================================


class TestValidateBands:
    """Tests for validate_bands()."""

    def test_valid_age_band_list_passes(self):
        errors = validate_bands(_valid_age_bands(), "age")
        assert errors == []

    def test_valid_tenure_band_list_passes(self):
        errors = validate_bands(_valid_tenure_bands(), "tenure")
        assert errors == []

    # --- empty / wrong type ---

    def test_empty_band_list(self):
        errors = validate_bands([], "age")
        assert len(errors) == 1
        assert "At least one" in errors[0].message
        assert errors[0].section == "age_bands"

    def test_band_not_a_dict(self):
        errors = validate_bands(["not_a_dict"], "tenure")
        assert len(errors) >= 1
        assert "must be a dict" in errors[0].message
        assert errors[0].section == "tenure_bands"

    # --- missing required fields ---

    @pytest.mark.parametrize("missing_field", [
        "band_id", "band_label", "min_value", "max_value", "display_order",
    ])
    def test_missing_required_field(self, missing_field):
        band = _valid_band("b1", "0-25", 0, 25, 1)
        del band[missing_field]
        errors = validate_bands([band], "age")
        assert any(missing_field in e.field and "required" in e.message for e in errors)

    # --- max_value <= min_value ---

    def test_max_value_equal_to_min_value(self):
        band = _valid_band("b1", "degenerate", 10, 10, 1)
        errors = validate_bands([band], "age")
        assert any("must be greater than" in e.message for e in errors)

    def test_max_value_less_than_min_value(self):
        band = _valid_band("b1", "inverted", 25, 10, 1)
        errors = validate_bands([band], "age")
        assert any("must be greater than" in e.message for e in errors)

    # --- first band doesn't start at 0 ---

    def test_first_band_not_starting_at_zero(self):
        bands = [
            _valid_band("b1", "5-25", 5, 25, 1),
            _valid_band("b2", "25-50", 25, 50, 2),
        ]
        errors = validate_bands(bands, "age")
        assert len(errors) == 1
        assert "must start at 0" in errors[0].message

    # --- gap between bands ---

    def test_gap_between_bands(self):
        bands = [
            _valid_band("b1", "0-20", 0, 20, 1),
            _valid_band("b2", "25-50", 25, 50, 2),  # gap: 20..25
        ]
        errors = validate_bands(bands, "tenure")
        assert len(errors) == 1
        assert "Gap detected" in errors[0].message

    # --- overlap between bands ---

    def test_overlap_between_bands(self):
        bands = [
            _valid_band("b1", "0-30", 0, 30, 1),
            _valid_band("b2", "25-50", 25, 50, 2),  # overlap: 25..30
        ]
        errors = validate_bands(bands, "age")
        assert len(errors) == 1
        assert "Overlap detected" in errors[0].message

    # --- non-numeric min_value / max_value ---

    def test_non_numeric_min_value(self):
        band = _valid_band("b1", "bad", "zero", 25, 1)
        errors = validate_bands([band], "age")
        assert any("min_value must be a number" in e.message for e in errors)

    def test_non_numeric_max_value(self):
        band = _valid_band("b1", "bad", 0, "twenty-five", 1)
        errors = validate_bands([band], "age")
        assert any("max_value must be a number" in e.message for e in errors)

    # --- section name reflects band_type ---

    def test_section_name_uses_band_type_age(self):
        errors = validate_bands([], "age")
        assert errors[0].section == "age_bands"

    def test_section_name_uses_band_type_tenure(self):
        errors = validate_bands([], "tenure")
        assert errors[0].section == "tenure_bands"

    # --- sorting for gap/overlap detection ---

    def test_bands_out_of_order_still_validated_correctly(self):
        """Bands supplied in reverse order should still pass if contiguous."""
        bands = list(reversed(_valid_age_bands()))
        errors = validate_bands(bands, "age")
        assert errors == []

    # --- single band edge case ---

    def test_single_valid_band_starting_at_zero(self):
        bands = [_valid_band("b1", "0-100", 0, 100, 1)]
        errors = validate_bands(bands, "age")
        assert errors == []

    # --- structural errors short-circuit gap/overlap checks ---

    def test_structural_error_prevents_gap_overlap_check(self):
        """When a band has max <= min, we get the structural error but not gap/overlap."""
        bands = [
            _valid_band("b1", "bad", 10, 5, 1),   # max < min
            _valid_band("b2", "also_bad", 20, 15, 2),  # max < min
        ]
        errors = validate_bands(bands, "age")
        # Should get structural errors only, not gap/overlap
        assert all("must be greater than" in e.message for e in errors)


# ===================================================================
# validate_seed_configs
# ===================================================================


class TestValidateSeedConfigs:
    """Tests for validate_seed_configs()."""

    def test_empty_config_no_errors(self):
        errors = validate_seed_configs({})
        assert errors == []

    def test_valid_promotion_hazard_no_errors(self):
        errors = validate_seed_configs({"promotion_hazard": _valid_promotion_hazard()})
        assert errors == []

    def test_valid_age_bands_no_errors(self):
        errors = validate_seed_configs({"age_bands": _valid_age_bands()})
        assert errors == []

    def test_valid_tenure_bands_no_errors(self):
        errors = validate_seed_configs({"tenure_bands": _valid_tenure_bands()})
        assert errors == []

    def test_all_valid_sections_no_errors(self):
        errors = validate_seed_configs({
            "promotion_hazard": _valid_promotion_hazard(),
            "age_bands": _valid_age_bands(),
            "tenure_bands": _valid_tenure_bands(),
        })
        assert errors == []

    def test_invalid_promotion_hazard_returns_errors_with_correct_section(self):
        errors = validate_seed_configs({"promotion_hazard": {"base_rate": 5.0}})
        assert len(errors) > 0
        # At minimum: base_rate out of range, missing level_dampener, missing age/tenure multipliers
        sections = {e.section for e in errors}
        assert sections == {"promotion_hazard"}

    def test_invalid_bands_returns_errors(self):
        errors = validate_seed_configs({"age_bands": []})
        assert len(errors) == 1
        assert errors[0].section == "age_bands"

    def test_promotion_hazard_not_a_dict(self):
        errors = validate_seed_configs({"promotion_hazard": "not_a_dict"})
        assert len(errors) == 1
        assert errors[0].section == "promotion_hazard"
        assert "must be a dict" in errors[0].message

    def test_promotion_hazard_as_list_rejected(self):
        errors = validate_seed_configs({"promotion_hazard": [1, 2, 3]})
        assert len(errors) == 1
        assert "must be a dict" in errors[0].message

    def test_multiple_invalid_sections_all_errors_collected(self):
        errors = validate_seed_configs({
            "promotion_hazard": {},         # missing all 4 fields
            "age_bands": [],                # empty
            "tenure_bands": [],             # empty
        })
        sections_with_errors = {e.section for e in errors}
        assert "promotion_hazard" in sections_with_errors
        assert "age_bands" in sections_with_errors
        assert "tenure_bands" in sections_with_errors

    def test_unknown_sections_are_ignored(self):
        """Sections not recognized by the validator should not cause errors."""
        errors = validate_seed_configs({"unknown_section": {"foo": "bar"}})
        assert errors == []

    def test_only_present_sections_are_validated(self):
        """If only age_bands is present, promotion_hazard is not validated."""
        errors = validate_seed_configs({"age_bands": _valid_age_bands()})
        assert errors == []
        # No promotion_hazard errors even though it's absent

    def test_invalid_tenure_bands_with_valid_promotion_hazard(self):
        """Errors from one section don't suppress validation of other sections."""
        errors = validate_seed_configs({
            "promotion_hazard": _valid_promotion_hazard(),
            "tenure_bands": [],
        })
        assert len(errors) == 1
        assert errors[0].section == "tenure_bands"


# ===================================================================
# SeedConfigValidationError dataclass
# ===================================================================


class TestSeedConfigValidationError:
    """Tests for the SeedConfigValidationError dataclass itself."""

    def test_fields_accessible(self):
        err = SeedConfigValidationError(
            section="promotion_hazard",
            field="base_rate",
            message="base_rate is required",
        )
        assert err.section == "promotion_hazard"
        assert err.field == "base_rate"
        assert err.message == "base_rate is required"

    def test_equality(self):
        a = SeedConfigValidationError("s", "f", "m")
        b = SeedConfigValidationError("s", "f", "m")
        assert a == b

    def test_inequality(self):
        a = SeedConfigValidationError("s", "f", "m1")
        b = SeedConfigValidationError("s", "f", "m2")
        assert a != b
