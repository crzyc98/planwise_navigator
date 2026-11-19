"""Read-only census schema for the Studio census guide.

Everything here comes from ``census_schema.FIELDS`` and the upload limits, so a
field added there shows up in the guide, template and copied column list.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..models.census_guide import (
    CensusFileRules,
    CensusGuideField,
    CensusGuideGroup,
    CensusGuideResponse,
)
from ..services.census_schema import (
    BOOLEAN_FALSE_ALIASES,
    BOOLEAN_TRUE_ALIASES,
    CENSUS_DATE_FORMATS,
    CENSUS_FIELD_GROUPS,
    FIELDS,
    guide_when_missing,
)
from .files import MAX_UPLOAD_SIZE as PARQUET_MAX_UPLOAD_BYTES
from .imports import IMPORT_FILE_TYPES
from .imports import MAX_UPLOAD_BYTES as IMPORT_MAX_UPLOAD_BYTES

router = APIRouter()

_KNOWN_GROUPS = {key for key, _ in CENSUS_FIELD_GROUPS}
_MB = 1024 * 1024


def _display_date_format(fmt: str) -> str:
    return fmt.replace("%Y", "YYYY").replace("%m", "MM").replace("%d", "DD")


@router.get(
    "/census/schema",
    response_model=CensusGuideResponse,
    summary="Census columns and file rules for the Studio census guide",
)
def get_census_schema() -> CensusGuideResponse:
    fields = [
        CensusGuideField(
            field_name=f.field_name,
            label=f.display_label,
            required=f.required,
            data_type=f.data_type,
            description=f.description,
            aliases=list(f.aliases),
            group=f.group if f.group in _KNOWN_GROUPS else "other",
            example=f.example_value,
            when_missing=guide_when_missing(f),
        )
        for f in FIELDS
    ]
    return CensusGuideResponse(
        fields=fields,
        groups=[CensusGuideGroup(key=k, label=v) for k, v in CENSUS_FIELD_GROUPS],
        file_rules=CensusFileRules(
            import_file_types=list(IMPORT_FILE_TYPES),
            import_max_mb=IMPORT_MAX_UPLOAD_BYTES // _MB,
            parquet_max_mb=PARQUET_MAX_UPLOAD_BYTES // _MB,
            date_formats=[_display_date_format(f) for f in CENSUS_DATE_FORMATS],
            true_values=sorted(BOOLEAN_TRUE_ALIASES),
            false_values=sorted(BOOLEAN_FALSE_ALIASES),
        ),
    )
