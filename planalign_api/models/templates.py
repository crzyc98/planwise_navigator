"""Template models for pre-configured scenarios."""

from typing import List

from pydantic import Field
from .base import APIModel
from .studio_config import StudioConfigDict


class Template(APIModel):
    """A pre-configured scenario template."""

    id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Template description")
    category: str = Field(
        ..., description="Template category (e.g., general, growth, cost)"
    )
    config: StudioConfigDict = Field(
        ..., description="Configuration overrides to apply"
    )


class TemplateListResponse(APIModel):
    """Response containing list of available templates."""

    templates: List[Template] = Field(..., description="Available templates")
