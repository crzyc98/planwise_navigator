"""
Pydantic models with Decimal fields for testing JSON serialization.

These models are used to verify that model_dump(mode='json') correctly
converts Decimal types to floats for JSON output.
"""

from decimal import Decimal
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class DecimalConfigModel(BaseModel):
    """Test model with basic Decimal field."""

    salary: Decimal
    contribution_rate: Decimal


class NestedDecimalListModel(BaseModel):
    """Test model with Decimal values in a list."""

    rates: List[Decimal]
    amounts: List[Decimal]


class NestedDecimalDictModel(BaseModel):
    """Test model with Decimal values in a dict."""

    salary_breakdown: Dict[str, Decimal]
    benefits: Dict[str, Decimal]


class ComplexDecimalModel(BaseModel):
    """Test model with complex nested Decimal structures."""

    employee_id: str
    salary: Decimal
    rates: List[Decimal]
    benefits: Dict[str, Decimal]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OptionalDecimalModel(BaseModel):
    """Test model with optional Decimal fields."""

    required_amount: Decimal
    optional_amount: Optional[Decimal] = None
    optional_rate: Optional[Decimal] = None


class LargeDecimalModel(BaseModel):
    """Test model with very large Decimal values."""

    large_amount: Decimal = Field(default=Decimal("999999999.99999999"))
    small_amount: Decimal = Field(default=Decimal("0.00000001"))
    negative_amount: Decimal = Field(default=Decimal("-125000.50"))
    zero_amount: Decimal = Field(default=Decimal("0"))


class EdgeCaseDecimalModel(BaseModel):
    """Test model with edge case Decimal values."""

    normal: Decimal = Field(default=Decimal("100.00"))
    very_large: Decimal = Field(default=Decimal("1" + "0" * 50))  # 50+ digit number
    very_small: Decimal = Field(default=Decimal("0.000000000001"))
    zero_amount: Decimal = Field(default=Decimal("0"))
    negative_zero: Decimal = Field(default=Decimal("-0"))
