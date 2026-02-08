# filename: config/events/validators.py
"""
Shared Decimal quantization validators for event payloads.

These functions standardize decimal precision across all event payloads,
ensuring consistent monetary and rate values throughout the simulation.

Precision Standards:
- Monetary amounts: 6 decimal places (0.000001) - matches (18,6) DB precision
- Rates/percentages: 4 decimal places (0.0001) - sufficient for contribution rates

Usage:
    from config.events.validators import quantize_amount, quantize_rate

    class MyPayload(BaseModel):
        amount: Decimal = Field(..., gt=0)
        rate: Decimal = Field(..., ge=0, le=1)

        @field_validator("amount")
        @classmethod
        def validate_amount(cls, v: Decimal) -> Decimal:
            return quantize_amount(v)

        @field_validator("rate")
        @classmethod
        def validate_rate(cls, v: Decimal) -> Decimal:
            return quantize_rate(v)
"""

from decimal import Decimal
from typing import Dict

# Precision constants
AMOUNT_PRECISION = Decimal("0.000001")  # 6 decimal places
RATE_PRECISION = Decimal("0.0001")  # 4 decimal places


def quantize_amount(v: Decimal) -> Decimal:
    """
    Quantize a monetary amount to 6 decimal places.

    Used for: compensation, contribution amounts, forfeitures, limits, thresholds.

    Args:
        v: Decimal value to quantize

    Returns:
        Decimal quantized to 6 decimal places

    Example:
        >>> quantize_amount(Decimal("100000.123456789"))
        Decimal('100000.123457')
    """
    return v.quantize(AMOUNT_PRECISION)


def quantize_rate(v: Decimal) -> Decimal:
    """
    Quantize a rate/percentage to 4 decimal places.

    Used for: contribution rates, vesting percentages, merit percentages.

    Args:
        v: Decimal value to quantize (typically 0-1 for percentages)

    Returns:
        Decimal quantized to 4 decimal places

    Example:
        >>> quantize_rate(Decimal("0.06789"))
        Decimal('0.0679')
    """
    return v.quantize(RATE_PRECISION)


def quantize_amount_dict(d: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """
    Quantize all values in a dictionary of amounts.

    Used for: source_balances_vested in VestingPayload.

    Args:
        d: Dictionary with string keys and Decimal values

    Returns:
        Dictionary with all values quantized to 6 decimal places

    Example:
        >>> quantize_amount_dict({"employer_match": Decimal("1234.5678901")})
        {'employer_match': Decimal('1234.567890')}
    """
    return {source: quantize_amount(amount) for source, amount in d.items()}


# Optional rate validator that handles None values
def quantize_rate_optional(v: Decimal | None) -> Decimal | None:
    """
    Quantize a rate/percentage, handling None values.

    Used for: optional rate fields like previous_pre_tax_rate.

    Args:
        v: Decimal value or None

    Returns:
        Quantized Decimal or None if input was None
    """
    if v is None:
        return None
    return quantize_rate(v)
