# filename: tests/unit/test_validators.py
"""
Unit tests for shared Decimal quantization validators.

Tests cover:
- quantize_amount: Monetary values to 6 decimal places
- quantize_rate: Rates/percentages to 4 decimal places
- quantize_amount_dict: Dictionary of amounts
- quantize_rate_optional: Optional rate handling

User Story 4 (FR-007): Test shared validators independently.
"""

import pytest
from decimal import Decimal

from config.events.validators import (
    quantize_amount,
    quantize_rate,
    quantize_amount_dict,
    quantize_rate_optional,
    AMOUNT_PRECISION,
    RATE_PRECISION,
)


class TestQuantizeAmount:
    """Tests for quantize_amount function - monetary values to 6 decimal places."""

    def test_quantize_amount_precision(self):
        """Verify Decimal("100000.123456789") → Decimal("100000.123457")"""
        result = quantize_amount(Decimal("100000.123456789"))
        expected = Decimal("100000.123457")
        assert result == expected

    def test_quantize_amount_zero(self):
        """Verify Decimal("0") → Decimal("0.000000")"""
        result = quantize_amount(Decimal("0"))
        expected = Decimal("0.000000")
        assert result == expected

    def test_quantize_amount_large_number(self):
        """Verify large monetary values are quantized correctly."""
        result = quantize_amount(Decimal("999999999.999999999"))
        # Rounds to 6 decimal places
        expected = Decimal("1000000000.000000")
        assert result == expected

    def test_quantize_amount_small_number(self):
        """Verify small monetary values are quantized correctly."""
        result = quantize_amount(Decimal("0.0000001"))
        # Rounds to 6 decimal places (0.0000001 rounds to 0.000000)
        expected = Decimal("0.000000")
        assert result == expected

    def test_quantize_amount_negative(self):
        """Verify negative amounts are quantized (for refunds/adjustments)."""
        result = quantize_amount(Decimal("-500.123456789"))
        expected = Decimal("-500.123457")
        assert result == expected

    def test_quantize_amount_exact_precision(self):
        """Verify values already at 6 decimal places are unchanged."""
        result = quantize_amount(Decimal("12345.678901"))
        expected = Decimal("12345.678901")
        assert result == expected


class TestQuantizeRate:
    """Tests for quantize_rate function - rates/percentages to 4 decimal places."""

    def test_quantize_rate_precision(self):
        """Verify Decimal("0.12345") → Decimal("0.1234") (banker's rounding)"""
        result = quantize_rate(Decimal("0.12345"))
        # Decimal uses ROUND_HALF_EVEN by default (banker's rounding)
        # 0.12345 rounds to 0.1234 (even digit)
        expected = Decimal("0.1234")
        assert result == expected

    def test_quantize_rate_zero(self):
        """Verify Decimal("0") → Decimal("0.0000")"""
        result = quantize_rate(Decimal("0"))
        expected = Decimal("0.0000")
        assert result == expected

    def test_quantize_rate_one(self):
        """Verify Decimal("1") → Decimal("1.0000") (100% rate)"""
        result = quantize_rate(Decimal("1"))
        expected = Decimal("1.0000")
        assert result == expected

    def test_quantize_rate_typical_contribution(self):
        """Verify typical 6% contribution rate."""
        result = quantize_rate(Decimal("0.06"))
        expected = Decimal("0.0600")
        assert result == expected

    def test_quantize_rate_fractional(self):
        """Verify fractional rate like 3.5%."""
        result = quantize_rate(Decimal("0.035"))
        expected = Decimal("0.0350")
        assert result == expected

    def test_quantize_rate_rounding(self):
        """Verify proper rounding at 4 decimal places."""
        # 0.06789 should round to 0.0679
        result = quantize_rate(Decimal("0.06789"))
        expected = Decimal("0.0679")
        assert result == expected


class TestQuantizeAmountDict:
    """Tests for quantize_amount_dict function - dictionary of amounts."""

    def test_quantize_amount_dict_basic(self):
        """Verify dictionary values are quantized."""
        input_dict = {"employer_match": Decimal("1234.5678901")}
        result = quantize_amount_dict(input_dict)
        expected = {"employer_match": Decimal("1234.567890")}
        assert result == expected

    def test_quantize_amount_dict_multiple_sources(self):
        """Verify multiple sources are all quantized."""
        input_dict = {
            "employer_match": Decimal("1000.1234567"),
            "employer_nonelective": Decimal("500.9876543"),
            "employer_profit_sharing": Decimal("250.1111111"),
        }
        result = quantize_amount_dict(input_dict)
        expected = {
            "employer_match": Decimal("1000.123457"),
            "employer_nonelective": Decimal("500.987654"),
            "employer_profit_sharing": Decimal("250.111111"),
        }
        assert result == expected

    def test_quantize_amount_dict_empty(self):
        """Verify empty dictionary returns empty dictionary."""
        result = quantize_amount_dict({})
        assert result == {}

    def test_quantize_amount_dict_preserves_keys(self):
        """Verify dictionary keys are preserved exactly."""
        input_dict = {"special_key_123": Decimal("100.123456789")}
        result = quantize_amount_dict(input_dict)
        assert "special_key_123" in result
        assert result["special_key_123"] == Decimal("100.123457")


class TestQuantizeRateOptional:
    """Tests for quantize_rate_optional function - optional rate handling."""

    def test_quantize_rate_optional_none(self):
        """Verify None passthrough."""
        result = quantize_rate_optional(None)
        assert result is None

    def test_quantize_rate_optional_value(self):
        """Verify Decimal value is quantized."""
        result = quantize_rate_optional(Decimal("0.12346"))
        # 0.12346 rounds to 0.1235 (banker's rounding - rounds to even)
        expected = Decimal("0.1235")
        assert result == expected

    def test_quantize_rate_optional_zero(self):
        """Verify zero rate is quantized."""
        result = quantize_rate_optional(Decimal("0"))
        expected = Decimal("0.0000")
        assert result == expected


class TestPrecisionConstants:
    """Tests for precision constant values."""

    def test_amount_precision_value(self):
        """Verify AMOUNT_PRECISION is 6 decimal places."""
        assert AMOUNT_PRECISION == Decimal("0.000001")

    def test_rate_precision_value(self):
        """Verify RATE_PRECISION is 4 decimal places."""
        assert RATE_PRECISION == Decimal("0.0001")
