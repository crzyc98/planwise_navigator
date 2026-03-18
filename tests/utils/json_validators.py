"""
Helper utilities for validating JSON serialization in tests.

These utilities assist in verifying that Python objects (especially those with
Decimal fields) are properly serialized to valid JSON.
"""

import json
from typing import Any, Dict, List, Union
from decimal import Decimal


def is_json_serializable(obj: Any) -> bool:
    """
    Check if a Python object is JSON serializable.

    Args:
        obj: The object to test for JSON serializability

    Returns:
        True if the object can be serialized to JSON, False otherwise

    Examples:
        >>> is_json_serializable({"value": 100.50})
        True
        >>> is_json_serializable({"value": Decimal("100.50")})
        False
    """
    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


def assert_json_parseable(json_str: str, error_msg: str = "") -> Dict[str, Any]:
    """
    Assert that a string is valid JSON and parse it.

    Args:
        json_str: The JSON string to validate
        error_msg: Optional custom error message

    Returns:
        The parsed JSON as a Python dict

    Raises:
        AssertionError: If the string is not valid JSON

    Examples:
        >>> result = assert_json_parseable('{"key": "value"}')
        >>> result["key"] == "value"
        True
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        msg = error_msg or f"JSON parsing failed: {e}"
        raise AssertionError(msg) from e


def assert_decimal_in_dict_converted(original_dict: Dict[str, Any],
                                    converted_dict: Dict[str, Any],
                                    decimal_keys: List[str]) -> None:
    """
    Assert that Decimal values in specified keys have been converted to floats.

    Args:
        original_dict: Dict that may contain Decimal values
        converted_dict: Dict that should have floats instead of Decimals
        decimal_keys: List of keys that contained Decimal values

    Raises:
        AssertionError: If any specified key still contains a Decimal

    Examples:
        >>> orig = {"salary": Decimal("100000.50")}
        >>> conv = {"salary": 100000.50}
        >>> assert_decimal_in_dict_converted(orig, conv, ["salary"])
    """
    for key in decimal_keys:
        if key not in converted_dict:
            raise AssertionError(f"Key '{key}' not found in converted dict")

        original_value = original_dict.get(key)
        converted_value = converted_dict.get(key)

        # If original was Decimal, converted should be float or compatible
        if isinstance(original_value, Decimal):
            if isinstance(converted_value, Decimal):
                raise AssertionError(
                    f"Key '{key}': Value is still a Decimal ({converted_value}), "
                    f"should be float"
                )


def validate_decimal_to_float_conversion(original: Decimal,
                                        converted: Union[float, int]) -> None:
    """
    Validate that a Decimal was properly converted to float.

    Checks that the numeric value is preserved (within float precision limits).

    Args:
        original: The original Decimal value
        converted: The converted float value

    Raises:
        AssertionError: If the conversion lost significant precision

    Examples:
        >>> validate_decimal_to_float_conversion(Decimal("100.50"), 100.5)
    """
    if not isinstance(converted, (float, int)):
        raise AssertionError(
            f"Expected float or int, got {type(converted).__name__}"
        )

    # Allow for floating-point precision differences
    original_float = float(original)
    if abs(original_float - converted) > abs(original_float * 1e-15):
        # More than floating-point rounding error
        raise AssertionError(
            f"Precision loss in conversion: {original} → {converted} "
            f"(difference: {abs(original_float - converted)})"
        )


def count_decimal_occurrences(obj: Any) -> int:
    """
    Recursively count Decimal objects in a nested structure.

    Useful for verifying that all Decimals were converted.

    Args:
        obj: Any Python object (dict, list, etc.)

    Returns:
        Number of Decimal instances found

    Examples:
        >>> count_decimal_occurrences({"salary": Decimal("100")})
        1
        >>> count_decimal_occurrences({"salary": 100.0})
        0
    """
    if isinstance(obj, Decimal):
        return 1
    elif isinstance(obj, dict):
        return sum(count_decimal_occurrences(v) for v in obj.values())
    elif isinstance(obj, (list, tuple)):
        return sum(count_decimal_occurrences(item) for item in obj)
    else:
        return 0


def assert_no_decimals_in_structure(obj: Any, structure_name: str = "object") -> None:
    """
    Assert that no Decimal objects exist in a nested structure.

    Args:
        obj: The structure to validate
        structure_name: Name for error messages

    Raises:
        AssertionError: If any Decimal objects are found

    Examples:
        >>> converted_dict = {"salary": 100000.50}
        >>> assert_no_decimals_in_structure(converted_dict, "config dict")
    """
    count = count_decimal_occurrences(obj)
    if count > 0:
        raise AssertionError(
            f"{structure_name} contains {count} Decimal object(s) - "
            f"use model_dump(mode='json') to convert"
        )
