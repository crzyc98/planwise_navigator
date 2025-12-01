"""Templates router for pre-configured scenario templates."""

from fastapi import APIRouter, HTTPException, status

from ..models.templates import Template, TemplateListResponse
from ..services.template_service import TemplateService

router = APIRouter()

# Singleton service instance
_service = TemplateService()


@router.get(
    "",
    response_model=TemplateListResponse,
    summary="List templates",
    description="List all available pre-configured scenario templates",
)
async def list_templates() -> TemplateListResponse:
    """List all available templates."""
    return TemplateListResponse(templates=_service.list_templates())


@router.get(
    "/{template_id}",
    response_model=Template,
    summary="Get template",
    description="Get a specific template by ID",
)
async def get_template(template_id: str) -> Template:
    """Get a specific template by ID."""
    template = _service.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {template_id}",
        )
    return template
