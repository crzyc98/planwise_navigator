"""Template models for pre-configured scenarios."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class Template(BaseModel):
    """A pre-configured scenario template."""

    id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Template description")
    category: str = Field(..., description="Template category (e.g., general, growth, cost)")
    config: Dict[str, Any] = Field(..., description="Configuration overrides to apply")


class TemplateListResponse(BaseModel):
    """Response containing list of available templates."""

    templates: List[Template] = Field(..., description="Available templates")
