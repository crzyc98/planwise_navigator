"""Save-time validation for import field mappings.

Saving a mapping and applying a template both run these checks, so a mapping
that the engine would refuse is never stored.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import List, Optional, get_args

from ..models.imports import (
    FieldMapping,
    MappingValidationError,
    Transformation,
    TransformType,
)
from .census_schema import CANONICAL_NAMES, CENSUS_DATE_FORMATS, is_canonical
from .mapping_engine import MappingError, validate_expression

MAX_NULL_REPLACE_TEXT_LENGTH = 256
_TRANSFORM_TYPES = frozenset(get_args(TransformType))


class MappingValidationFailed(MappingError):
    """A mapping failed save-time validation; ``errors`` lists each problem."""

    def __init__(self, errors: List[MappingValidationError]) -> None:
        super().__init__("The field mapping is not valid.")
        self.errors = errors


def _null_replace_error(value: object) -> Optional[str]:
    if value is not None and not isinstance(value, (str, int, float, bool)):
        return "Replacement value must be text, a number, true/false, or empty."
    if isinstance(value, str) and len(value) > MAX_NULL_REPLACE_TEXT_LENGTH:
        return (
            "Replacement value is longer than "
            f"{MAX_NULL_REPLACE_TEXT_LENGTH} characters."
        )
    return None


def transformation_error(
    transform: Transformation, columns: Iterable[str]
) -> Optional[str]:
    """Why ``transform`` can't be saved, or None when it is valid."""
    kind = transform.transform_type
    params = transform.params
    if kind not in _TRANSFORM_TYPES:
        return f"Unknown transformation {kind!r}."
    if kind == "calculated_field":
        try:
            validate_expression(params.get("expression", ""), frozenset(columns))
        except MappingError as exc:
            return str(exc)
    elif kind == "date_parse" and params.get("format") not in CENSUS_DATE_FORMATS:
        return "Date format must be one of: " + ", ".join(CENSUS_DATE_FORMATS) + "."
    elif kind == "null_replace":
        return _null_replace_error(params.get("value"))
    return None


def _column_errors(
    m: FieldMapping, detected_names: set[str], seen_output: set[str]
) -> List[MappingValidationError]:
    errors: List[MappingValidationError] = []
    if m.input_column not in detected_names:
        errors.append(
            MappingValidationError(
                field="input_column",
                input_column=m.input_column,
                message=f"Column {m.input_column!r} not found in detected columns",
            )
        )
    if not is_canonical(m.output_column):
        valid_names = ", ".join(sorted(CANONICAL_NAMES))
        errors.append(
            MappingValidationError(
                field="output_column",
                input_column=m.input_column,
                message=(
                    f"Output column {m.output_column!r} is not a recognized census field. "
                    f"Valid fields: {valid_names}"
                ),
            )
        )
    if m.output_column in seen_output:
        errors.append(
            MappingValidationError(
                field="output_column",
                input_column=m.input_column,
                message=f"Duplicate output column name {m.output_column!r}",
            )
        )
    return errors


def validate_mappings(
    mappings: Iterable[FieldMapping], detected_names: set[str]
) -> List[MappingValidationError]:
    """Every problem that would stop ``mappings`` from being saved.

    Calculated fields may reference source columns and the outputs of earlier
    mappings, matching how the engine builds its working frame.
    """
    errors: List[MappingValidationError] = []
    seen_output: set[str] = set()
    for m in mappings:
        if m.is_excluded:
            continue
        errors.extend(_column_errors(m, detected_names, seen_output))
        available = detected_names | seen_output
        for transform in m.transformations:
            message = transformation_error(transform, available)
            if message is not None:
                errors.append(
                    MappingValidationError(
                        field="transformations",
                        input_column=m.input_column,
                        message=message,
                    )
                )
        seen_output.add(m.output_column)
    return errors


def require_valid_mappings(
    mappings: Iterable[FieldMapping], detected_names: set[str]
) -> None:
    """Raise MappingValidationFailed when ``mappings`` can't be saved."""
    errors = validate_mappings(mappings, detected_names)
    if errors:
        raise MappingValidationFailed(errors)
