"""Cross-field census plausibility rules (#1260).

The rules live in ``planalign_core.census_plausibility`` so the engine can run
them too (#1262); this module keeps the API import path working.
"""

from planalign_core.census_plausibility import (
    DATE_COLUMNS,
    IRS_LIMITS_SEED,
    RULES,
    DeferralLimits,
    FlaggedRow,
    PlausibilityRule,
    RuleCount,
    Severity,
    applicable_rules,
    census_year_from_hires,
    count_violations,
    deferral_limits_for_year,
    flagged_rows,
)

__all__ = [
    "DATE_COLUMNS",
    "IRS_LIMITS_SEED",
    "RULES",
    "DeferralLimits",
    "FlaggedRow",
    "PlausibilityRule",
    "RuleCount",
    "Severity",
    "applicable_rules",
    "census_year_from_hires",
    "count_violations",
    "deferral_limits_for_year",
    "flagged_rows",
]
