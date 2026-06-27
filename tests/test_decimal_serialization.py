"""
Unit tests for Decimal serialization using Pydantic's model_dump(mode='json').

These tests verify that Pydantic v2's mode='json' parameter correctly converts
Decimal types to JSON-safe strings in the resulting dictionary. Per issue #235,
Decimal serializes to string (not float) so exact precision is preserved at the
serialization boundary; both are JSON-serializable but only string is lossless.

IMPORTANT: These tests MUST be written to test the BEHAVIOR, not the implementation.
The focus is on verifying that Decimal values are converted to JSON-serializable
formats when using model_dump(mode='json').
"""

import json
import pytest
from decimal import Decimal
from tests.fixtures.decimal_models import (
    DecimalConfigModel,
    NestedDecimalListModel,
    NestedDecimalDictModel,
    ComplexDecimalModel,
    OptionalDecimalModel,
    LargeDecimalModel,
    EdgeCaseDecimalModel,
)
from tests.utils.json_validators import (
    is_json_serializable,
    assert_no_decimals_in_structure,
    count_decimal_occurrences,
)


class TestBasicDecimalConversion:
    """T004: Test basic Decimal to float conversion"""

    def test_model_dump_mode_json_converts_decimal(self):
        """
        Verify that model_dump(mode='json') makes Decimal JSON-serializable.

        Given: A Pydantic model with a Decimal field set to Decimal("125000.50")
        When: model_dump(mode='json') is called
        Then: The resulting dict should have Decimal converted to string (JSON-serializable)

        Note: Decimal → string (not float) preserves precision exactly.
        Both string and float are JSON-serializable, but string preserves the exact value.
        """
        model = DecimalConfigModel(
            salary=Decimal("125000.50"), contribution_rate=Decimal("0.06")
        )

        # Convert using mode='json'
        config_dict = model.model_dump(mode="json")

        # Verify Decimal types were converted to JSON-serializable type (string)
        assert isinstance(
            config_dict["salary"], str
        ), f"Expected str, got {type(config_dict['salary'])}"
        assert isinstance(
            config_dict["contribution_rate"], str
        ), f"Expected str, got {type(config_dict['contribution_rate'])}"
        assert config_dict["salary"] == "125000.50"
        assert config_dict["contribution_rate"] == "0.06"

    def test_model_dump_without_mode_contains_decimal(self):
        """
        Verify that model_dump() WITHOUT mode='json' keeps Decimal types.

        This test documents the difference between mode='json' and default behavior.
        """
        model = DecimalConfigModel(
            salary=Decimal("125000.50"), contribution_rate=Decimal("0.06")
        )

        # Without mode='json', Decimals remain as Decimal objects
        config_dict = model.model_dump()

        # This should show Decimals are NOT converted without mode='json'
        assert isinstance(config_dict["salary"], Decimal)
        assert isinstance(config_dict["contribution_rate"], Decimal)


class TestJsonParsing:
    """T005: Test JSON parsing of converted config"""

    def test_converted_dict_is_json_serializable(self):
        """
        Verify that converted dict can be serialized to JSON.

        Given: A Pydantic model with Decimal fields
        When: model_dump(mode='json') is used and result is passed to json.dumps()
        Then: No TypeError should be raised

        This is the CRITICAL test for the bug fix - json.dumps() must NOT raise
        "TypeError: Object of type Decimal is not JSON serializable"
        """
        model = DecimalConfigModel(
            salary=Decimal("125000.50"), contribution_rate=Decimal("0.06")
        )

        config_dict = model.model_dump(mode="json")

        # This should NOT raise TypeError (this was the bug!)
        json_str = json.dumps(config_dict)

        # Verify it's valid JSON by parsing it back
        parsed = json.loads(json_str)
        # Decimal values become strings, which is JSON-serializable
        assert parsed["salary"] == "125000.50"
        assert parsed["contribution_rate"] == "0.06"

    def test_json_parsing_roundtrip(self):
        """
        Verify that JSON serialization roundtrip preserves values.

        Given: A Pydantic model with Decimal fields
        When: Converted and serialized to JSON, then parsed back
        Then: Values should match as JSON-safe strings (exact precision)
        """
        original = DecimalConfigModel(
            salary=Decimal("99999.99"), contribution_rate=Decimal("0.075")
        )

        # Round-trip: model → dict → JSON → dict
        config_dict = original.model_dump(mode="json")
        json_str = json.dumps(config_dict)
        parsed = json.loads(json_str)

        # Decimal serializes to JSON-safe strings (preserves exact precision)
        assert parsed["salary"] == "99999.99"
        assert parsed["contribution_rate"] == "0.075"


class TestNestedDecimalStructures:
    """T006 & T007: Test nested Decimals in lists and dicts"""

    def test_decimal_list_conversion(self):
        """
        T006: Verify nested Decimals in lists are converted.

        Given: A model with a list of Decimal values
        When: model_dump(mode='json') is called
        Then: All Decimal values in the list should be JSON-safe strings
        """
        model = NestedDecimalListModel(
            rates=[Decimal("0.06"), Decimal("0.10"), Decimal("0.15")],
            amounts=[Decimal("100.50"), Decimal("200.75")],
        )

        config_dict = model.model_dump(mode="json")

        # Verify all list items are JSON-safe strings (Decimal -> str preserves precision)
        for rate in config_dict["rates"]:
            assert isinstance(rate, str), f"Expected str, got {type(rate)}"
        for amount in config_dict["amounts"]:
            assert isinstance(amount, str), f"Expected str, got {type(amount)}"

        # Verify values are correct
        assert config_dict["rates"] == ["0.06", "0.10", "0.15"]
        assert config_dict["amounts"] == ["100.50", "200.75"]

    def test_decimal_dict_conversion(self):
        """
        T007: Verify nested Decimals in dicts are converted.

        Given: A model with dicts containing Decimal values
        When: model_dump(mode='json') is called
        Then: All Decimal values in dicts should be JSON-safe strings
        """
        model = NestedDecimalDictModel(
            salary_breakdown={
                "base": Decimal("100000.00"),
                "bonus": Decimal("25000.00"),
            },
            benefits={"401k_match": Decimal("0.06"), "hsa": Decimal("500.00")},
        )

        config_dict = model.model_dump(mode="json")

        # Verify all dict values are JSON-safe strings
        for value in config_dict["salary_breakdown"].values():
            assert isinstance(value, str), f"Expected str, got {type(value)}"
        for value in config_dict["benefits"].values():
            assert isinstance(value, str), f"Expected str, got {type(value)}"

        # Verify values are correct
        assert config_dict["salary_breakdown"]["base"] == "100000.00"
        assert config_dict["benefits"]["401k_match"] == "0.06"

    def test_deeply_nested_decimals(self):
        """
        T027: Verify deeply nested Decimals in complex structures.

        Given: A complex model with multiple levels of nesting
        When: model_dump(mode='json') is called
        Then: All Decimals at all nesting levels should be converted
        """
        model = ComplexDecimalModel(
            employee_id="EMP_001",
            salary=Decimal("125000.00"),
            rates=[Decimal("0.06"), Decimal("0.10")],
            benefits={"401k": Decimal("7500.00"), "hsa": Decimal("3000.00")},
        )

        config_dict = model.model_dump(mode="json")

        # Verify no Decimals remain anywhere in the structure
        assert (
            count_decimal_occurrences(config_dict) == 0
        ), "Found Decimal objects in converted dict - conversion incomplete"

        # Verify all values are JSON-serializable
        json_str = json.dumps(config_dict)
        assert isinstance(json_str, str)


class TestLargeDecimalValues:
    """T008: Test large Decimal precision handling"""

    def test_large_decimal_conversion(self):
        """
        Verify very large Decimal values are converted without error.

        Given: A model with very large Decimal(999999999.99999999)
        When: model_dump(mode='json') is called
        Then: Conversion should succeed (acceptable precision loss for logging)
        """
        model = LargeDecimalModel(
            large_amount=Decimal("999999999.99999999"),
            small_amount=Decimal("0.00000001"),
        )

        config_dict = model.model_dump(mode="json")

        # Decimal serializes to JSON-safe strings (exact precision preserved)
        assert isinstance(config_dict["large_amount"], str)
        assert isinstance(config_dict["small_amount"], str)

        # Verify JSON serialization works
        json_str = json.dumps(config_dict)
        parsed = json.loads(json_str)

        # Values parse back to positive numbers
        assert float(parsed["large_amount"]) > 0
        assert float(parsed["small_amount"]) > 0


class TestDecimalEdgeCases:
    """T009: Test Decimal edge cases"""

    def test_decimal_zero_variants(self):
        """
        Verify Decimal(0) and Decimal(-0) are handled correctly.
        """
        model = EdgeCaseDecimalModel(
            normal=Decimal("100.00"),
            zero_amount=Decimal("0"),
            negative_zero=Decimal("-0"),
        )

        config_dict = model.model_dump(mode="json")

        # All should be JSON-safe strings
        assert isinstance(config_dict["normal"], str)
        assert isinstance(config_dict["zero_amount"], str)
        assert isinstance(config_dict["negative_zero"], str)

        # Zero variants parse back to 0.0
        assert float(config_dict["zero_amount"]) == 0.0
        assert float(config_dict["negative_zero"]) == 0.0

    def test_optional_decimal_none_value(self):
        """
        T026: Verify None values in optional Decimal fields become null in JSON.
        """
        model = OptionalDecimalModel(
            required_amount=Decimal("1000.00"), optional_amount=None, optional_rate=None
        )

        config_dict = model.model_dump(mode="json")

        # Required should be a JSON-safe string
        assert isinstance(config_dict["required_amount"], str)

        # Optional None should be None (null in JSON)
        assert config_dict["optional_amount"] is None
        assert config_dict["optional_rate"] is None

        # Should be JSON serializable
        json_str = json.dumps(config_dict)
        parsed = json.loads(json_str)
        assert parsed["optional_amount"] is None

    def test_optional_decimal_with_value(self):
        """
        Verify optional Decimal fields with values are converted correctly.
        """
        model = OptionalDecimalModel(
            required_amount=Decimal("1000.00"),
            optional_amount=Decimal("500.50"),
            optional_rate=Decimal("0.05"),
        )

        config_dict = model.model_dump(mode="json")

        # All should be JSON-safe strings
        assert isinstance(config_dict["required_amount"], str)
        assert isinstance(config_dict["optional_amount"], str)
        assert isinstance(config_dict["optional_rate"], str)

        # Values should be preserved
        assert config_dict["optional_amount"] == "500.50"
        assert config_dict["optional_rate"] == "0.05"

    def test_very_large_digit_decimal(self):
        """
        Verify very large decimal numbers (50+ digits) are handled.
        """
        model = EdgeCaseDecimalModel(
            very_large=Decimal("1" + "0" * 50)  # 50-digit number
        )

        config_dict = model.model_dump(mode="json")

        # Serializes to a JSON-safe string (exact precision preserved)
        assert isinstance(config_dict["very_large"], str)
        assert float(config_dict["very_large"]) > 0

    def test_very_small_decimal(self):
        """
        Verify very small Decimal values (many decimal places) are handled.
        """
        model = EdgeCaseDecimalModel(very_small=Decimal("0.000000000001"))

        config_dict = model.model_dump(mode="json")

        # Serializes to a JSON-safe string
        assert isinstance(config_dict["very_small"], str)
        assert float(config_dict["very_small"]) > 0


@pytest.mark.fast
class TestDecimalSerializationFast:
    """Fast-running tests (< 1 second total) for CI/TDD workflow"""

    def test_basic_decimal_conversion_fast(self):
        """Quick smoke test for Decimal conversion"""
        model = DecimalConfigModel(
            salary=Decimal("100000.00"), contribution_rate=Decimal("0.06")
        )
        config_dict = model.model_dump(mode="json")
        assert is_json_serializable(config_dict)

    def test_no_decimals_remain_fast(self):
        """Quick check that no Decimals remain in converted dict"""
        model = ComplexDecimalModel(
            employee_id="TEST",
            salary=Decimal("100000.00"),
            rates=[Decimal("0.06")],
            benefits={"401k": Decimal("6000.00")},
        )
        config_dict = model.model_dump(mode="json")
        assert_no_decimals_in_structure(config_dict, "converted config")
