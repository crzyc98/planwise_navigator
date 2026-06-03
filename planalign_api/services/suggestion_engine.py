"""SuggestionEngine — auto-suggests canonical census field mappings from uploaded column names.

Uses stdlib difflib for name-similarity scoring; no external ML dependencies required.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd

from ..models.imports import (
    ColumnSuggestion,
    DataQualityResult,
    FormatDetectionResult,
    ImportSession,
)
from ..models.imports import DetectedColumn
from .census_schema import FIELDS, CensusFieldDefinition, get_required_fields

# Confidence thresholds (clarified in spec)
_HIGH_THRESHOLD = 0.85
_MEDIUM_THRESHOLD = 0.50

# Ranked date format strings to try (most unambiguous first)
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%Y%m%d",
]

# Boolean alias tables (lowercase)
_TRUTHY = frozenset({"y", "yes", "true", "1", "active", "enrolled", "eligible", "employed"})
_FALSY = frozenset({"n", "no", "false", "0", "inactive", "terminated", "separated", "ineligible"})

# Currency pattern for decimal stripping detection
_CURRENCY_RE = re.compile(r"[$€£,\s]")
_PAREN_NEG_RE = re.compile(r"^\((.+)\)$")


def _normalize(name: str) -> str:
    """Lowercase and collapse non-alphanumeric chars to underscore."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _score_against_field(normalized_input: str, field: CensusFieldDefinition) -> tuple[float, str]:
    """Return (best_score, reason) across field_name and all aliases."""
    best = _similarity(normalized_input, _normalize(field.field_name))
    reason = "name_match"
    for alias in field.aliases:
        score = _similarity(normalized_input, _normalize(alias))
        if score > best:
            best = score
            reason = "alias_match"
    return best, reason


def _confidence_from_score(score: float) -> str:
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


class SuggestionEngine:
    """Stateless service for generating canonical field mapping suggestions."""

    def suggest(self, detected_columns: list[DetectedColumn]) -> list[ColumnSuggestion]:
        """Auto-suggest canonical field for each detected input column."""
        # First pass: score all columns against all fields
        raw: list[tuple[int, float, str, str, str]] = []  # (col_idx, score, canonical, reason, input)
        for idx, col in enumerate(detected_columns):
            norm = _normalize(col.name)
            best_score = 0.0
            best_field = ""
            best_reason = "no_match"
            for field in FIELDS:
                score, reason = _score_against_field(norm, field)
                if score > best_score:
                    best_score = score
                    best_field = field.field_name
                    best_reason = reason
            raw.append((idx, best_score, best_field, best_reason, col.name))

        # Second pass: resolve duplicate canonical targets — keep highest scorer
        claimed: dict[str, int] = {}  # canonical_field → col_idx with best score
        for idx, score, canonical, reason, _ in raw:
            if score < _MEDIUM_THRESHOLD or not canonical:
                continue
            if canonical not in claimed or score > raw[claimed[canonical]][1]:
                claimed[canonical] = idx

        suggestions: list[ColumnSuggestion] = []
        for idx, score, canonical, reason, input_col in raw:
            if score < _MEDIUM_THRESHOLD or not canonical or claimed.get(canonical) != idx:
                suggestions.append(ColumnSuggestion(
                    input_column=input_col,
                    suggested_canonical_field=None,
                    confidence="low",
                    confidence_score=round(score, 4),
                    reason="no_match",
                ))
            else:
                suggestions.append(ColumnSuggestion(
                    input_column=input_col,
                    suggested_canonical_field=canonical,
                    confidence=_confidence_from_score(score),  # type: ignore[arg-type]
                    confidence_score=round(score, 4),
                    reason=reason,  # type: ignore[arg-type]
                ))

        return suggestions

    def detect_format(
        self, column: DetectedColumn, canonical_field: CensusFieldDefinition
    ) -> Optional[FormatDetectionResult]:
        """Detect date format, currency pattern, or boolean alias map from sample values."""
        samples = [v for v in column.sample_values if v and v.strip()][:20]
        if not samples:
            return None

        if canonical_field.data_type == "date":
            return self._detect_date_format(samples)
        if canonical_field.data_type == "decimal":
            return self._detect_currency(samples)
        if canonical_field.data_type == "boolean":
            return self._detect_boolean(samples)
        return None

    def _detect_date_format(self, samples: list[str]) -> Optional[FormatDetectionResult]:
        # Try each format; count how many samples parse successfully
        results: list[tuple[str, int, list[str]]] = []
        for fmt in _DATE_FORMATS:
            parsed = pd.to_datetime(samples, format=fmt, errors="coerce")
            success_count = int(parsed.notna().sum())
            if success_count == 0:
                continue
            iso_samples = [d.strftime("%Y-%m-%d") for d in parsed.dropna()[:3]]
            results.append((fmt, success_count, iso_samples))

        if not results:
            return None

        max_success = max(r[1] for r in results)
        best = [r for r in results if r[1] == max_success]

        if len(best) == 1:
            return FormatDetectionResult(
                detected_format=best[0][0],
                parsed_sample_values=best[0][2],
                is_ambiguous=False,
                format_options=None,
            )

        # Ambiguous — return all tied formats
        format_options = [r[0] for r in best]
        return FormatDetectionResult(
            detected_format=None,
            parsed_sample_values=best[0][2],
            is_ambiguous=True,
            format_options=format_options,
        )

    def _detect_currency(self, samples: list[str]) -> Optional[FormatDetectionResult]:
        has_currency = any(_CURRENCY_RE.search(v) for v in samples)
        has_paren = any(_PAREN_NEG_RE.match(v) for v in samples)
        if not has_currency and not has_paren:
            return None

        stripped: list[str] = []
        for v in samples[:3]:
            cleaned = _CURRENCY_RE.sub("", v)
            m = _PAREN_NEG_RE.match(cleaned)
            if m:
                cleaned = f"-{m.group(1)}"
            stripped.append(cleaned)

        return FormatDetectionResult(
            detected_format="currency_string",
            parsed_sample_values=stripped,
            is_ambiguous=False,
            format_options=None,
        )

    def _detect_boolean(self, samples: list[str]) -> Optional[FormatDetectionResult]:
        lowered = [v.lower().strip() for v in samples if v.strip()]
        if not lowered:
            return None

        all_known = all(v in _TRUTHY or v in _FALSY for v in lowered)
        match_count = sum(1 for v in lowered if v in _TRUTHY or v in _FALSY)
        ratio = match_count / len(lowered) if lowered else 0

        if ratio < 0.95:
            return None

        unique_truthy = sorted({v for v in lowered if v in _TRUTHY})
        unique_falsy = sorted({v for v in lowered if v in _FALSY})
        alias_display = ", ".join(f"{t} → true" for t in unique_truthy)
        alias_display += "; " + ", ".join(f"{f} → false" for f in unique_falsy)
        return FormatDetectionResult(
            detected_format="boolean_alias",
            parsed_sample_values=[alias_display],
            is_ambiguous=False,
            format_options=None,
        )

    def scan_data_quality(
        self,
        session: ImportSession,
        suggestions: list[ColumnSuggestion],
    ) -> DataQualityResult:
        """Scan session preview rows and detected columns for data quality issues."""
        suggestion_map = {s.input_column: s.suggested_canonical_field for s in suggestions}
        canonical_to_input = {v: k for k, v in suggestion_map.items() if v}

        # Duplicate employee_id count (from preview rows — sample of up to 100)
        duplicate_count = 0
        emp_id_col = canonical_to_input.get("employee_id")
        if emp_id_col and session.preview_rows:
            ids = [row.get(emp_id_col) for row in session.preview_rows if row.get(emp_id_col)]
            seen: set = set()
            dupes: set = set()
            for v in ids:
                if v in seen:
                    dupes.add(v)
                seen.add(v)
            duplicate_count = len(dupes)

        # Null counts for required fields (full-file count from DetectedColumn.null_count)
        col_null_map = {c.name: c.null_count for c in session.detected_columns}
        null_required: dict[str, int] = {}
        for req_field in get_required_fields():
            input_col = canonical_to_input.get(req_field)
            if input_col is not None:
                null_count = col_null_map.get(input_col, 0)
                if null_count > 0:
                    null_required[req_field] = null_count
            else:
                # Required field has no mapping — entire column missing
                null_required[req_field] = session.row_count

        # Compensation outliers (from preview rows)
        outlier_count = 0
        comp_col = canonical_to_input.get("employee_gross_compensation")
        if comp_col and session.preview_rows:
            for row in session.preview_rows:
                raw = row.get(comp_col)
                if raw is None:
                    continue
                try:
                    cleaned = _CURRENCY_RE.sub("", str(raw))
                    m = _PAREN_NEG_RE.match(cleaned)
                    cleaned = f"-{m.group(1)}" if m else cleaned
                    val = float(cleaned)
                    if val < 1_000 or val > 10_000_000:
                        outlier_count += 1
                except (ValueError, TypeError):
                    pass

        return DataQualityResult(
            duplicate_employee_id_count=duplicate_count,
            null_required_field_counts=null_required,
            compensation_outlier_count=outlier_count,
        )

    @staticmethod
    def get_auto_fingerprint(column_names: list[str]) -> str:
        """SHA-256 fingerprint of sorted input column headers for repeat-upload detection."""
        joined = ",".join(sorted(column_names))
        return hashlib.sha256(joined.encode()).hexdigest()
