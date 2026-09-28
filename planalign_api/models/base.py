"""Shared base for API request/response models."""

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for every API schema model.

    Responses always serialize every field, so fields with defaults are marked
    required in response (serialization-mode) schemas. FastAPI then emits
    separate ``-Input``/``-Output`` schemas where the two differ, and the Studio
    types generated from OpenAPI (#661) see always-present fields as
    non-optional instead of ``field?: T``.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
