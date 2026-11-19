"""Response models for the Studio census guide (read-only census schema)."""

from __future__ import annotations

from typing import List

from .base import APIModel


class CensusGuideField(APIModel):
    field_name: str
    label: str
    required: bool
    data_type: str
    description: str
    aliases: List[str]
    group: str
    example: str
    when_missing: str


class CensusGuideGroup(APIModel):
    key: str
    label: str


class CensusFileRules(APIModel):
    import_file_types: List[str]
    import_max_mb: int
    parquet_max_mb: int
    date_formats: List[str]
    true_values: List[str]
    false_values: List[str]


class CensusGuideResponse(APIModel):
    fields: List[CensusGuideField]
    groups: List[CensusGuideGroup]
    file_rules: CensusFileRules
