"""Settings a run's saved config records under two paths (#1178, #1320).

Keep in step with ``MIRRORS`` in
``planalign_studio/components/comparisonIntegrity.ts``, which Scenario Diff's
table uses, so the table and the evidence pack count the same differences;
``tests/api/test_setting_mirrors.py`` fails if the two lists differ.
"""

from __future__ import annotations

import json
from typing import Any

from ..models.comparison import ConfigDelta

# The engine reads compensation.<name> (decimal); Studio saves <name>_percent.
COMPENSATION_PERCENT_FIELDS = (
    "cola_rate",
    "merit_budget",
    "raise_budget",
    "raise_coverage",
    "promotion_increase",
    "promotion_budget",
    "promotion_distribution_range",
)

# Studio's dc_plan.core_* settings and the employer_core_contribution keys the
# archived config derives from them: Studio key -> (engine path, scale).
CORE_COPIES: dict[str, tuple[str, float | None]] = {
    "core_enabled": ("enabled", None),
    "core_status": ("status", None),
    "core_contribution_rate_percent": ("contribution_rate", 0.01),
    "core_graded_schedule": ("graded_schedule", None),
    "core_points_schedule": ("points_schedule", None),
    "core_points_min_service_years": ("points_min_service_years", None),
    "core_points_pre_service_rate": ("points_pre_service_rate", None),
    "core_age_schedule": ("age_schedule", None),
    "core_min_tenure_years": ("eligibility.minimum_tenure_years", None),
    "core_min_hours_annual": ("eligibility.minimum_hours_annual", None),
    "core_require_year_end_active": ("eligibility.require_active_at_year_end", None),
    "core_allow_new_hires": ("eligibility.allow_new_hires", None),
    "core_allow_terminated_new_hires": ("eligibility.allow_terminated_new_hires", None),
    "core_allow_experienced_terminations": (
        "eligibility.allow_experienced_terminations",
        None,
    ),
    "core_integration_enabled": ("integration.enabled", None),
    "core_integration_level_mode": ("integration.level_mode", None),
    "core_integration_level_value": ("integration.level_value", None),
    "core_integration_disparity_rate": ("integration.disparity_rate", None),
}

_MATCH_RESPONSE_COPY = "dc_plan.deferral_match_response."


def _mirror(path: str) -> tuple[str, float | None] | None:
    """The canonical path and unit scale for a path a mirror rule rewrites."""
    section, _, key = path.partition(".")
    if section == "compensation" and key in COMPENSATION_PERCENT_FIELDS:
        return f"{path}_percent", 100.0
    if path.startswith(_MATCH_RESPONSE_COPY):
        return path.removeprefix("dc_plan."), None
    if section == "dc_plan" and key in CORE_COPIES:
        engine_path, scale = CORE_COPIES[key]
        return f"employer_core_contribution.{engine_path}", scale
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _comparable(value: Any, scale: float | None) -> str:
    """A value in canonical units; scaling can leave float noise (0.07 * 100)."""
    if _is_number(value):
        value = float(f"{value * (scale or 1.0):.12g}")
    # Key order counts, as in the table's JSON.stringify.
    return json.dumps(value, default=str)


def _same_setting(
    copy: ConfigDelta, canonical: ConfigDelta, scale: float | None
) -> bool:
    if copy.status != canonical.status:
        return False
    return all(
        _comparable(getattr(copy, side), scale)
        == _comparable(getattr(canonical, side), None)
        for side in ("a", "b")
    )


def fold_mirrored(differences: list[ConfigDelta]) -> list[ConfigDelta]:
    """One difference per setting recorded under two paths that agree.

    The copy a mirror rule rewrites stays, as in Scenario Diff's table; copies
    that disagree both stay, so the conflict shows.
    """
    by_path = {delta.path: delta for delta in differences}
    copies: dict[str, list[tuple[ConfigDelta, float | None]]] = {}
    for delta in differences:
        mirror = _mirror(delta.path)
        if mirror is not None:
            copies.setdefault(mirror[0], []).append((delta, mirror[1]))
    folded = {
        canonical_path
        for canonical_path, group in copies.items()
        if len(group) == 1
        and canonical_path in by_path
        and _same_setting(group[0][0], by_path[canonical_path], group[0][1])
    }
    return [delta for delta in differences if delta.path not in folded]
