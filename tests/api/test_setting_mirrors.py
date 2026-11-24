"""Mirrored settings count once in the evidence pack's cited differences (#1320)."""

import pytest

from planalign_api.models.comparison import ConfigDelta
from planalign_api.services.setting_mirrors import fold_mirrored

pytestmark = pytest.mark.fast


def _changed(path: str, a: object, b: object) -> ConfigDelta:
    return ConfigDelta(path=path, a=a, b=b, status="changed")


def _paths(differences: list[ConfigDelta]) -> list[str]:
    return [delta.path for delta in fold_mirrored(differences)]


def test_folds_copies_that_agree_after_scaling() -> None:
    assert _paths(
        [
            _changed("compensation.cola_rate", 0.03, 0.07),
            _changed("compensation.cola_rate_percent", 3, 7),
            _changed("dc_plan.deferral_match_response.enabled", False, True),
            _changed("deferral_match_response.enabled", False, True),
            _changed("dc_plan.core_contribution_rate_percent", 2, 3.5),
            _changed("employer_core_contribution.contribution_rate", 0.02, 0.035),
            _changed("dc_plan.core_min_tenure_years", 0, 1),
            _changed(
                "employer_core_contribution.eligibility.minimum_tenure_years", 0, 1
            ),
            _changed("dc_plan.match_cap_percent", 0.04, 0.06),
        ]
    ) == [
        "compensation.cola_rate",
        "dc_plan.deferral_match_response.enabled",
        "dc_plan.core_contribution_rate_percent",
        "dc_plan.core_min_tenure_years",
        "dc_plan.match_cap_percent",
    ]


def test_keeps_copies_that_disagree() -> None:
    disagree = [
        _changed("compensation.cola_rate", 0.03, 0.04),
        _changed("compensation.cola_rate_percent", 3, 5),
        _changed("dc_plan.core_enabled", False, True),
        _changed("employer_core_contribution.enabled", True, False),
    ]
    assert fold_mirrored(disagree) == disagree


def test_keeps_a_copy_only_one_run_recorded() -> None:
    one_sided = [
        _changed("employer_core_contribution.enabled", False, True),
        ConfigDelta(path="dc_plan.core_enabled", a=None, b=True, status="only_b"),
    ]
    assert fold_mirrored(one_sided) == one_sided


def test_does_not_read_a_flag_as_a_number() -> None:
    mixed = [
        _changed("dc_plan.core_min_tenure_years", 0, 1),
        _changed(
            "employer_core_contribution.eligibility.minimum_tenure_years", False, True
        ),
    ]
    assert fold_mirrored(mixed) == mixed
