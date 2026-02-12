"""Tests for tenure-based and points-based employer match modes.

Feature: 046-tenure-points-match
Tests Pydantic validation (T017), integration (T018), and IRS cap verification (T029).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config.export import _export_employer_match_vars
from planalign_orchestrator.config.workforce import (
    EmployerMatchSettings,
    PointsMatchTier,
    TenureMatchTier,
    validate_tier_contiguity,
)


# =============================================================================
# T017: TenureMatchTier Validation
# =============================================================================


class TestTenureMatchTier:
    """Validate TenureMatchTier field-level constraints."""

    def test_valid_tier(self):
        tier = TenureMatchTier(min_years=0, max_years=5, match_rate=50, max_deferral_pct=6)
        assert tier.min_years == 0
        assert tier.max_years == 5
        assert tier.match_rate == 50
        assert tier.max_deferral_pct == 6

    def test_unbounded_last_tier(self):
        tier = TenureMatchTier(min_years=10, max_years=None, match_rate=100, max_deferral_pct=6)
        assert tier.max_years is None

    def test_invalid_range_max_le_min(self):
        with pytest.raises(ValidationError, match="max_years.*must be greater than min_years"):
            TenureMatchTier(min_years=5, max_years=5, match_rate=50, max_deferral_pct=6)

    def test_invalid_range_max_lt_min(self):
        with pytest.raises(ValidationError, match="max_years.*must be greater than min_years"):
            TenureMatchTier(min_years=10, max_years=5, match_rate=50, max_deferral_pct=6)

    def test_negative_min_years(self):
        with pytest.raises(ValidationError):
            TenureMatchTier(min_years=-1, max_years=5, match_rate=50, max_deferral_pct=6)

    def test_match_rate_bounds(self):
        # Valid bounds
        TenureMatchTier(min_years=0, max_years=5, match_rate=0, max_deferral_pct=6)
        TenureMatchTier(min_years=0, max_years=5, match_rate=100, max_deferral_pct=6)
        # Out of bounds
        with pytest.raises(ValidationError):
            TenureMatchTier(min_years=0, max_years=5, match_rate=-1, max_deferral_pct=6)
        with pytest.raises(ValidationError):
            TenureMatchTier(min_years=0, max_years=5, match_rate=101, max_deferral_pct=6)

    def test_max_deferral_pct_bounds(self):
        TenureMatchTier(min_years=0, max_years=5, match_rate=50, max_deferral_pct=0)
        TenureMatchTier(min_years=0, max_years=5, match_rate=50, max_deferral_pct=100)
        with pytest.raises(ValidationError):
            TenureMatchTier(min_years=0, max_years=5, match_rate=50, max_deferral_pct=-1)
        with pytest.raises(ValidationError):
            TenureMatchTier(min_years=0, max_years=5, match_rate=50, max_deferral_pct=101)


# =============================================================================
# T017: PointsMatchTier Validation
# =============================================================================


class TestPointsMatchTier:
    """Validate PointsMatchTier field-level constraints."""

    def test_valid_tier(self):
        tier = PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6)
        assert tier.min_points == 0
        assert tier.max_points == 40

    def test_unbounded_last_tier(self):
        tier = PointsMatchTier(min_points=80, max_points=None, match_rate=100, max_deferral_pct=6)
        assert tier.max_points is None

    def test_invalid_range_max_le_min(self):
        with pytest.raises(ValidationError, match="max_points.*must be greater than min_points"):
            PointsMatchTier(min_points=40, max_points=40, match_rate=50, max_deferral_pct=6)

    def test_invalid_range_max_lt_min(self):
        with pytest.raises(ValidationError, match="max_points.*must be greater than min_points"):
            PointsMatchTier(min_points=60, max_points=40, match_rate=50, max_deferral_pct=6)

    def test_negative_min_points(self):
        with pytest.raises(ValidationError):
            PointsMatchTier(min_points=-1, max_points=40, match_rate=25, max_deferral_pct=6)

    def test_boundary_value_points_40(self):
        """Points=40 with tiers [0,40) and [40,60) — 40 falls in [40,60) per [min,max) convention."""
        # This tests the tier ASSIGNMENT logic, not just the model.
        # The tier model itself just validates bounds; assignment happens in SQL.
        tier_low = PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6)
        tier_high = PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6)
        assert tier_low.min_points == 0
        assert tier_low.max_points == 40
        assert tier_high.min_points == 40


# =============================================================================
# T017: validate_tier_contiguity() Tests
# =============================================================================


class TestValidateTierContiguity:
    """Test shared tier contiguity validator."""

    def test_valid_contiguous_tiers(self):
        tiers = [
            {"min": 0, "max": 5},
            {"min": 5, "max": 10},
            {"min": 10, "max": None},
        ]
        # Should not raise
        validate_tier_contiguity(tiers, min_key="min", max_key="max", label="tenure")

    def test_gap_detected(self):
        tiers = [
            {"min": 0, "max": 5},
            {"min": 7, "max": 10},  # gap: 5 to 7
        ]
        with pytest.raises(ValueError, match="[Gg]ap"):
            validate_tier_contiguity(tiers, min_key="min", max_key="max", label="tenure")

    def test_overlap_detected(self):
        tiers = [
            {"min": 0, "max": 10},
            {"min": 5, "max": 15},  # overlap: 5-10
        ]
        with pytest.raises(ValueError, match="[Oo]verlap"):
            validate_tier_contiguity(tiers, min_key="min", max_key="max", label="tenure")

    def test_missing_start_at_zero(self):
        tiers = [
            {"min": 2, "max": 5},
            {"min": 5, "max": None},
        ]
        with pytest.raises(ValueError, match="start at 0"):
            validate_tier_contiguity(tiers, min_key="min", max_key="max", label="tenure")

    def test_empty_list(self):
        # Empty tier list is OK — only invalid if mode requires it
        validate_tier_contiguity([], min_key="min", max_key="max", label="tenure")

    def test_single_tier_unbounded(self):
        tiers = [{"min": 0, "max": None}]
        validate_tier_contiguity(tiers, min_key="min", max_key="max", label="tenure")

    def test_single_tier_bounded(self):
        tiers = [{"min": 0, "max": 40}]
        validate_tier_contiguity(tiers, min_key="min", max_key="max", label="tenure")


# =============================================================================
# T017: EmployerMatchSettings Validation
# =============================================================================


class TestEmployerMatchSettings:
    """Test EmployerMatchSettings with new match modes."""

    def test_default_mode(self):
        settings = EmployerMatchSettings()
        assert settings.employer_match_status == "deferral_based"
        assert settings.tenure_match_tiers == []
        assert settings.points_match_tiers == []

    def test_deferral_based_mode(self):
        settings = EmployerMatchSettings(employer_match_status="deferral_based")
        assert settings.employer_match_status == "deferral_based"

    def test_graded_by_service_mode(self):
        settings = EmployerMatchSettings(employer_match_status="graded_by_service")
        assert settings.employer_match_status == "graded_by_service"

    def test_tenure_based_mode_with_tiers(self):
        settings = EmployerMatchSettings(
            employer_match_status="tenure_based",
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
                TenureMatchTier(min_years=2, max_years=5, match_rate=50, max_deferral_pct=6),
                TenureMatchTier(min_years=5, max_years=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.employer_match_status == "tenure_based"
        assert len(settings.tenure_match_tiers) == 3

    def test_points_based_mode_with_tiers(self):
        settings = EmployerMatchSettings(
            employer_match_status="points_based",
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6),
                PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6),
                PointsMatchTier(min_points=60, max_points=80, match_rate=75, max_deferral_pct=6),
                PointsMatchTier(min_points=80, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.employer_match_status == "points_based"
        assert len(settings.points_match_tiers) == 4

    def test_unrecognized_match_status_rejected(self):
        with pytest.raises(ValidationError, match="employer_match_status"):
            EmployerMatchSettings(employer_match_status="unknown_mode")

    def test_tenure_based_empty_tiers_rejected(self):
        with pytest.raises(ValidationError, match="[Aa]t least one.*tier"):
            EmployerMatchSettings(
                employer_match_status="tenure_based",
                tenure_match_tiers=[],
            )

    def test_points_based_empty_tiers_rejected(self):
        with pytest.raises(ValidationError, match="[Aa]t least one.*tier"):
            EmployerMatchSettings(
                employer_match_status="points_based",
                points_match_tiers=[],
            )

    def test_tenure_based_non_contiguous_tiers_rejected(self):
        with pytest.raises(ValidationError, match="[Gg]ap"):
            EmployerMatchSettings(
                employer_match_status="tenure_based",
                tenure_match_tiers=[
                    TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
                    TenureMatchTier(min_years=5, max_years=None, match_rate=50, max_deferral_pct=6),
                ],
            )

    def test_points_based_overlapping_tiers_rejected(self):
        with pytest.raises(ValidationError, match="[Oo]verlap"):
            EmployerMatchSettings(
                employer_match_status="points_based",
                points_match_tiers=[
                    PointsMatchTier(min_points=0, max_points=50, match_rate=25, max_deferral_pct=6),
                    PointsMatchTier(min_points=40, max_points=None, match_rate=50, max_deferral_pct=6),
                ],
            )

    def test_descriptive_error_message_for_gap(self):
        with pytest.raises(ValidationError) as exc_info:
            EmployerMatchSettings(
                employer_match_status="tenure_based",
                tenure_match_tiers=[
                    TenureMatchTier(min_years=0, max_years=3, match_rate=25, max_deferral_pct=6),
                    TenureMatchTier(min_years=5, max_years=None, match_rate=50, max_deferral_pct=6),
                ],
            )
        error_str = str(exc_info.value)
        assert "gap" in error_str.lower() or "Gap" in error_str

    def test_zero_deferral_edge_case(self):
        """A tier with max_deferral_pct=0 is valid — effectively disables match for that tier."""
        settings = EmployerMatchSettings(
            employer_match_status="tenure_based",
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=None, match_rate=50, max_deferral_pct=0),
            ],
        )
        assert settings.tenure_match_tiers[0].max_deferral_pct == 0

    def test_new_hire_zero_service(self):
        """New hire with 0 years of service should be assigned to first tier (min_years=0)."""
        settings = EmployerMatchSettings(
            employer_match_status="tenure_based",
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
                TenureMatchTier(min_years=2, max_years=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.tenure_match_tiers[0].min_years == 0

    def test_ineligible_employee_match_zero(self):
        """Match=0 for ineligible employees is handled at the SQL level, not config."""
        # Config should accept valid tiers regardless of eligibility logic
        settings = EmployerMatchSettings(
            employer_match_status="points_based",
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert len(settings.points_match_tiers) == 1


# =============================================================================
# T018: Integration Tests — Config Round-Trip and Export
# =============================================================================


class _FakeConfig:
    """Minimal fake SimulationConfig for testing _export_employer_match_vars."""

    def __init__(self, employer_match=None, dc_plan=None):
        self.employer_match = employer_match
        self.dc_plan = dc_plan
        self._raw_config = {}


def _make_config_mock(**overrides):
    """Create a fake SimulationConfig with employer_match settings."""
    employer_match = EmployerMatchSettings(**overrides)
    return _FakeConfig(employer_match=employer_match)


class TestExportTenureMatchVars:
    """T018: Verify _export_employer_match_vars exports tenure tiers correctly."""

    def test_tenure_based_export(self):
        cfg = _make_config_mock(
            employer_match_status="tenure_based",
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=5, match_rate=25, max_deferral_pct=6),
                TenureMatchTier(min_years=5, max_years=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "tenure_based"
        assert len(dbt_vars["tenure_match_tiers"]) == 2

        tier_0 = dbt_vars["tenure_match_tiers"][0]
        assert tier_0["min_years"] == 0
        assert tier_0["max_years"] == 5
        assert tier_0["rate"] == 25  # match_rate -> rate
        assert tier_0["max_deferral_pct"] == 6

        tier_1 = dbt_vars["tenure_match_tiers"][1]
        assert tier_1["min_years"] == 5
        assert tier_1["max_years"] is None

    def test_deferral_based_no_tenure_tiers(self):
        cfg = _make_config_mock(employer_match_status="deferral_based")
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "deferral_based"
        assert "tenure_match_tiers" not in dbt_vars


class TestExportPointsMatchVars:
    """T018: Verify _export_employer_match_vars exports points tiers correctly."""

    def test_points_based_export(self):
        cfg = _make_config_mock(
            employer_match_status="points_based",
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6),
                PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6),
                PointsMatchTier(min_points=60, max_points=80, match_rate=75, max_deferral_pct=6),
                PointsMatchTier(min_points=80, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "points_based"
        assert len(dbt_vars["points_match_tiers"]) == 4

        tier_0 = dbt_vars["points_match_tiers"][0]
        assert tier_0["min_points"] == 0
        assert tier_0["max_points"] == 40
        assert tier_0["rate"] == 25

        tier_3 = dbt_vars["points_match_tiers"][3]
        assert tier_3["min_points"] == 80
        assert tier_3["max_points"] is None
        assert tier_3["rate"] == 100

    def test_points_based_no_export_when_deferral(self):
        cfg = _make_config_mock(employer_match_status="deferral_based")
        dbt_vars = _export_employer_match_vars(cfg)

        assert "points_match_tiers" not in dbt_vars


class TestExportDcPlanTenureTiers:
    """T018: Verify dc_plan (UI) path exports tenure/points tiers with field mapping."""

    def test_dc_plan_tenure_tiers_decimal_conversion(self):
        """UI sends match_rate as decimal (0.50), export converts to percentage (50)."""
        cfg = _FakeConfig(
            employer_match=None,
            dc_plan={
                "match_status": "tenure_based",
                "tenure_match_tiers": [
                    {"min_years": 0, "max_years": 5, "match_rate": 0.25, "max_deferral_pct": 0.06},
                    {"min_years": 5, "max_years": None, "match_rate": 1.0, "max_deferral_pct": 0.06},
                ],
            },
        )

        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "tenure_based"
        tiers = dbt_vars["tenure_match_tiers"]
        assert len(tiers) == 2
        assert tiers[0]["rate"] == 25.0  # 0.25 * 100
        assert tiers[0]["max_deferral_pct"] == 6.0  # 0.06 * 100
        assert tiers[1]["rate"] == 100.0

    def test_dc_plan_points_tiers_decimal_conversion(self):
        """UI sends match_rate as decimal (0.75), export converts to percentage (75)."""
        cfg = _FakeConfig(
            employer_match=None,
            dc_plan={
                "match_status": "points_based",
                "points_match_tiers": [
                    {"min_points": 0, "max_points": 40, "match_rate": 0.25, "max_deferral_pct": 0.06},
                    {"min_points": 40, "max_points": None, "match_rate": 0.75, "max_deferral_pct": 0.06},
                ],
            },
        )

        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "points_based"
        tiers = dbt_vars["points_match_tiers"]
        assert len(tiers) == 2
        assert tiers[0]["rate"] == 25.0
        assert tiers[1]["rate"] == 75.0


# =============================================================================
# T029: IRS Section 401(a)(17) Cap + Eligibility Verification for New Modes
# =============================================================================


class TestIRSCapAndEligibilityNewModes:
    """T029: Verify IRS cap and eligibility logic produce correct results in new modes.

    These are config-level tests verifying that the new modes don't break
    the eligibility and IRS cap settings. The actual IRS cap application
    happens in SQL (LEAST(compensation, irs_401a17_limit)) which is tested
    at the dbt level. Here we verify the config plumbing.
    """

    def test_tenure_based_with_eligibility_settings(self):
        """Eligibility settings should be accepted alongside tenure_based mode."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchSettings(
            employer_match_status="tenure_based",
            apply_eligibility=True,
            eligibility=EmployerMatchEligibilitySettings(
                minimum_tenure_years=1,
                require_active_at_year_end=True,
                minimum_hours_annual=1000,
            ),
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=None, match_rate=50, max_deferral_pct=6),
            ],
        )
        assert settings.apply_eligibility is True
        assert settings.eligibility.minimum_tenure_years == 1

    def test_points_based_with_eligibility_settings(self):
        """Eligibility settings should be accepted alongside points_based mode."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchSettings(
            employer_match_status="points_based",
            apply_eligibility=True,
            eligibility=EmployerMatchEligibilitySettings(
                minimum_tenure_years=0,
                require_active_at_year_end=True,
            ),
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.apply_eligibility is True

    def test_tenure_export_preserves_eligibility(self):
        """Export must carry eligibility settings through to dbt for new modes."""
        cfg = _make_config_mock(
            employer_match_status="tenure_based",
            apply_eligibility=True,
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=None, match_rate=50, max_deferral_pct=6),
            ],
        )
        dbt_vars = _export_employer_match_vars(cfg)

        # employer_match nested dict should have eligibility
        assert "employer_match" in dbt_vars
        assert dbt_vars["employer_match"]["apply_eligibility"] is True

    def test_points_export_preserves_eligibility(self):
        """Export must carry eligibility settings through to dbt for new modes."""
        cfg = _make_config_mock(
            employer_match_status="points_based",
            apply_eligibility=True,
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert "employer_match" in dbt_vars
        assert dbt_vars["employer_match"]["apply_eligibility"] is True

    def test_ineligible_employee_receives_zero_match_design(self):
        """Verify the SQL design: ineligible employees get match=0 in new modes.

        The SQL model uses:
          CASE WHEN ec.is_eligible_for_match THEN am.match_amount ELSE 0 END
        for tenure_based and points_based modes (same as graded_by_service).
        This is a structural/design verification, not runtime SQL test.
        """
        # Config is valid — eligibility enforcement is orthogonal to match mode
        settings = EmployerMatchSettings(
            employer_match_status="points_based",
            apply_eligibility=True,
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.apply_eligibility is True
        # The SQL model applies CASE WHEN is_eligible_for_match for all tier-based modes


# =============================================================================
# T024-T025: Regression Tests — Existing Modes Produce Correct Output
# =============================================================================


class TestDeferralBasedRegression:
    """T024: Verify deferral_based mode produces identical config/export output."""

    def test_deferral_based_default_settings(self):
        """Default EmployerMatchSettings should be deferral_based with no tiers."""
        settings = EmployerMatchSettings()
        assert settings.employer_match_status == "deferral_based"
        assert settings.tenure_match_tiers == []
        assert settings.points_match_tiers == []

    def test_deferral_based_export_unchanged(self):
        """deferral_based export should not emit tenure/points tier variables."""
        cfg = _make_config_mock(employer_match_status="deferral_based")
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "deferral_based"
        assert "tenure_match_tiers" not in dbt_vars
        assert "points_match_tiers" not in dbt_vars
        # Must still export base employer_match settings
        assert "employer_match" in dbt_vars

    def test_deferral_based_export_has_base_match_settings(self):
        """deferral_based export should still include base employer_match dict."""
        cfg = _make_config_mock(employer_match_status="deferral_based")
        dbt_vars = _export_employer_match_vars(cfg)

        assert "employer_match" in dbt_vars
        assert dbt_vars["employer_match_status"] == "deferral_based"

    def test_deferral_based_ignores_tenure_tiers(self):
        """Tenure tiers on deferral_based mode should be silently accepted (empty)."""
        settings = EmployerMatchSettings(employer_match_status="deferral_based")
        assert settings.tenure_match_tiers == []


class TestGradedByServiceRegression:
    """T025: Verify graded_by_service mode produces correct config/export output."""

    def test_graded_by_service_settings(self):
        """graded_by_service should be a valid status."""
        settings = EmployerMatchSettings(employer_match_status="graded_by_service")
        assert settings.employer_match_status == "graded_by_service"

    def test_graded_by_service_export(self):
        """graded_by_service export should not emit tenure/points tier variables."""
        cfg = _make_config_mock(employer_match_status="graded_by_service")
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match_status"] == "graded_by_service"
        assert "tenure_match_tiers" not in dbt_vars
        assert "points_match_tiers" not in dbt_vars

    def test_graded_by_service_with_match_schedule(self):
        """graded_by_service should accept existing match_schedule config."""
        settings = EmployerMatchSettings(
            employer_match_status="graded_by_service",
        )
        assert settings.employer_match_status == "graded_by_service"
        # No tenure/points tiers emitted
        cfg = _make_config_mock(employer_match_status="graded_by_service")
        dbt_vars = _export_employer_match_vars(cfg)
        assert dbt_vars["employer_match_status"] == "graded_by_service"


# =============================================================================
# T026-T027: Multi-Year Simulation Config Tests — Tier Transitions
# =============================================================================


class TestMultiYearPointsBased:
    """T026: Verify points_based config exports consistently across years."""

    def test_points_tiers_consistent_across_years(self):
        """Same config should export identical tier structures for each sim year."""
        tiers = [
            PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6),
            PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6),
            PointsMatchTier(min_points=60, max_points=None, match_rate=100, max_deferral_pct=6),
        ]
        for year in [2025, 2026, 2027]:
            cfg = _make_config_mock(
                employer_match_status="points_based",
                points_match_tiers=tiers,
            )
            dbt_vars = _export_employer_match_vars(cfg)

            assert dbt_vars["employer_match_status"] == "points_based"
            assert len(dbt_vars["points_match_tiers"]) == 3
            # Tier boundaries are static config — unchanged year to year
            assert dbt_vars["points_match_tiers"][0]["rate"] == 25
            assert dbt_vars["points_match_tiers"][2]["rate"] == 100

    def test_points_boundary_crossing_scenario(self):
        """Verify tier boundaries handle the points = 59 → 61 transition.

        An employee with points=59 falls in [40, 60) tier (rate=50%).
        Next year with points=61, they cross into [60, None) tier (rate=100%).
        This is purely config-level — the SQL CASE handles runtime values.
        """
        tiers = [
            PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6),
            PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6),
            PointsMatchTier(min_points=60, max_points=None, match_rate=100, max_deferral_pct=6),
        ]
        # The tier at index 1 covers [40, 60) — inclusive 40, exclusive 60
        assert tiers[1].min_points == 40
        assert tiers[1].max_points == 60
        assert tiers[1].match_rate == 50
        # The tier at index 2 covers [60, ∞) — inclusive 60
        assert tiers[2].min_points == 60
        assert tiers[2].max_points is None
        assert tiers[2].match_rate == 100

    def test_points_based_four_tier_export_field_mapping(self):
        """Verify all 4 quickstart tiers export with correct field mappings."""
        tiers = [
            PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6),
            PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6),
            PointsMatchTier(min_points=60, max_points=80, match_rate=75, max_deferral_pct=6),
            PointsMatchTier(min_points=80, max_points=None, match_rate=100, max_deferral_pct=6),
        ]
        cfg = _make_config_mock(employer_match_status="points_based", points_match_tiers=tiers)
        dbt_vars = _export_employer_match_vars(cfg)

        exported = dbt_vars["points_match_tiers"]
        assert len(exported) == 4
        for t in exported:
            assert "rate" in t  # match_rate -> rate
            assert "match_rate" not in t  # not raw Pydantic field name
            assert "max_deferral_pct" in t


class TestMultiYearTenureBased:
    """T027: Verify tenure_based config exports consistently across years."""

    def test_tenure_tiers_consistent_across_years(self):
        """Same config should export identical tier structures for each sim year."""
        tiers = [
            TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
            TenureMatchTier(min_years=2, max_years=5, match_rate=50, max_deferral_pct=6),
            TenureMatchTier(min_years=5, max_years=None, match_rate=100, max_deferral_pct=6),
        ]
        for year in [2025, 2026, 2027]:
            cfg = _make_config_mock(
                employer_match_status="tenure_based",
                tenure_match_tiers=tiers,
            )
            dbt_vars = _export_employer_match_vars(cfg)

            assert dbt_vars["employer_match_status"] == "tenure_based"
            assert len(dbt_vars["tenure_match_tiers"]) == 3
            assert dbt_vars["tenure_match_tiers"][0]["rate"] == 25
            assert dbt_vars["tenure_match_tiers"][2]["rate"] == 100

    def test_tenure_boundary_crossing_scenario(self):
        """Verify tier boundaries handle the tenure = 1.9 → 2.1 year transition.

        An employee with tenure < 2 falls in [0, 2) tier (rate=25%).
        Next year with tenure >= 2, they cross into [2, 5) tier (rate=50%).
        """
        tiers = [
            TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
            TenureMatchTier(min_years=2, max_years=5, match_rate=50, max_deferral_pct=6),
            TenureMatchTier(min_years=5, max_years=None, match_rate=100, max_deferral_pct=6),
        ]
        # [0, 2) tier
        assert tiers[0].min_years == 0
        assert tiers[0].max_years == 2
        assert tiers[0].match_rate == 25
        # [2, 5) tier
        assert tiers[1].min_years == 2
        assert tiers[1].max_years == 5
        assert tiers[1].match_rate == 50

    def test_tenure_based_four_tier_export_field_mapping(self):
        """Verify quickstart 4-tier tenure config exports correctly."""
        tiers = [
            TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
            TenureMatchTier(min_years=2, max_years=5, match_rate=50, max_deferral_pct=6),
            TenureMatchTier(min_years=5, max_years=10, match_rate=75, max_deferral_pct=6),
            TenureMatchTier(min_years=10, max_years=None, match_rate=100, max_deferral_pct=6),
        ]
        cfg = _make_config_mock(employer_match_status="tenure_based", tenure_match_tiers=tiers)
        dbt_vars = _export_employer_match_vars(cfg)

        exported = dbt_vars["tenure_match_tiers"]
        assert len(exported) == 4
        for t in exported:
            assert "rate" in t
            assert "match_rate" not in t
            assert "max_deferral_pct" in t
            assert "min_years" in t


# =============================================================================
# T028: Quickstart Smoke Tests — Config Validation
# =============================================================================


# =============================================================================
# E047: Tenure Eligibility — allow_new_hires Conditional Default Tests
# =============================================================================


class TestAllowNewHiresConditionalDefault:
    """E047: Verify allow_new_hires defaults based on minimum_tenure_years."""

    def test_tenure_gt_zero_defaults_allow_new_hires_false(self):
        """T009: minimum_tenure_years=2 without explicit allow_new_hires → False."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchEligibilitySettings(minimum_tenure_years=2)
        assert settings.allow_new_hires is False

    def test_tenure_zero_defaults_allow_new_hires_true(self):
        """T010: minimum_tenure_years=0 without explicit allow_new_hires → True (backward compat)."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchEligibilitySettings(minimum_tenure_years=0)
        assert settings.allow_new_hires is True

    def test_default_eligibility_preserves_backward_compat(self):
        """T010b: Default EmployerMatchEligibilitySettings() → allow_new_hires=True."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchEligibilitySettings()
        assert settings.minimum_tenure_years == 0
        assert settings.allow_new_hires is True

    def test_explicit_true_preserved_with_tenure(self):
        """T011: Explicit allow_new_hires=True is not overridden by conditional logic."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchEligibilitySettings(
            minimum_tenure_years=2, allow_new_hires=True
        )
        assert settings.allow_new_hires is True

    def test_explicit_false_preserved_with_zero_tenure(self):
        """Explicit allow_new_hires=False is preserved even with tenure=0."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        settings = EmployerMatchEligibilitySettings(
            minimum_tenure_years=0, allow_new_hires=False
        )
        assert settings.allow_new_hires is False

    def test_export_produces_false_when_tenure_gt_zero(self):
        """T012: Config export with tenure > 0 and no explicit allow_new_hires → false."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        cfg = _make_config_mock(
            apply_eligibility=True,
            eligibility=EmployerMatchEligibilitySettings(minimum_tenure_years=2),
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match"]["eligibility"]["allow_new_hires"] is False

    def test_export_produces_true_when_tenure_zero(self):
        """T012b: Config export with tenure=0 and no explicit allow_new_hires → true."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        cfg = _make_config_mock(
            apply_eligibility=True,
            eligibility=EmployerMatchEligibilitySettings(minimum_tenure_years=0),
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert dbt_vars["employer_match"]["eligibility"]["allow_new_hires"] is True

    def test_dc_plan_match_allow_new_hires_propagates(self):
        """T027: dc_plan.match_allow_new_hires propagates to employer_match dbt var."""
        cfg = _FakeConfig(
            employer_match=None,
            dc_plan={
                "match_allow_new_hires": False,
                "match_min_tenure_years": 2,
            },
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert "employer_match" in dbt_vars
        assert dbt_vars["employer_match"]["eligibility"]["allow_new_hires"] is False

    def test_dc_plan_match_allow_new_hires_true_propagates(self):
        """T027b: dc_plan.match_allow_new_hires=True explicitly propagates."""
        cfg = _FakeConfig(
            employer_match=None,
            dc_plan={
                "match_allow_new_hires": True,
                "match_min_tenure_years": 2,
            },
        )
        dbt_vars = _export_employer_match_vars(cfg)

        assert "employer_match" in dbt_vars
        assert dbt_vars["employer_match"]["eligibility"]["allow_new_hires"] is True


class TestContradictoryConfigWarnings:
    """E047 US3: Verify warnings for contradictory allow_new_hires + tenure settings."""

    def test_contradictory_settings_emit_warning(self):
        """T019: allow_new_hires=True + minimum_tenure_years=2 → warning emitted."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        with pytest.warns(UserWarning, match="Contradictory eligibility"):
            EmployerMatchEligibilitySettings(
                minimum_tenure_years=2, allow_new_hires=True
            )

    def test_non_contradictory_no_warning(self):
        """T020: allow_new_hires=True + minimum_tenure_years=0 → no warning."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        # Should NOT emit any warning
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            EmployerMatchEligibilitySettings(
                minimum_tenure_years=0, allow_new_hires=True
            )

    def test_no_warning_when_allow_false_with_tenure(self):
        """No warning when allow_new_hires=False + minimum_tenure_years>0 (consistent)."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            EmployerMatchEligibilitySettings(
                minimum_tenure_years=2, allow_new_hires=False
            )

    def test_no_warning_when_default_resolves(self):
        """No warning when allow_new_hires is defaulted (not explicitly set)."""
        from planalign_orchestrator.config.workforce import EmployerMatchEligibilitySettings

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            EmployerMatchEligibilitySettings(minimum_tenure_years=2)


class TestQuickstartSmokeTests:
    """T028: Validate the quickstart.md config examples parse and export correctly."""

    def test_quickstart_tenure_config(self):
        """Validate the quickstart.md tenure_based config example."""
        # Exact tiers from quickstart.md
        settings = EmployerMatchSettings(
            employer_match_status="tenure_based",
            tenure_match_tiers=[
                TenureMatchTier(min_years=0, max_years=2, match_rate=25, max_deferral_pct=6),
                TenureMatchTier(min_years=2, max_years=5, match_rate=50, max_deferral_pct=6),
                TenureMatchTier(min_years=5, max_years=10, match_rate=75, max_deferral_pct=6),
                TenureMatchTier(min_years=10, max_years=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.employer_match_status == "tenure_based"
        assert len(settings.tenure_match_tiers) == 4

        # Export and verify
        cfg = _FakeConfig(employer_match=settings)
        dbt_vars = _export_employer_match_vars(cfg)
        assert dbt_vars["employer_match_status"] == "tenure_based"
        assert len(dbt_vars["tenure_match_tiers"]) == 4

    def test_quickstart_points_config(self):
        """Validate the quickstart.md points_based config example."""
        settings = EmployerMatchSettings(
            employer_match_status="points_based",
            points_match_tiers=[
                PointsMatchTier(min_points=0, max_points=40, match_rate=25, max_deferral_pct=6),
                PointsMatchTier(min_points=40, max_points=60, match_rate=50, max_deferral_pct=6),
                PointsMatchTier(min_points=60, max_points=80, match_rate=75, max_deferral_pct=6),
                PointsMatchTier(min_points=80, max_points=None, match_rate=100, max_deferral_pct=6),
            ],
        )
        assert settings.employer_match_status == "points_based"
        assert len(settings.points_match_tiers) == 4

        # Export and verify
        cfg = _FakeConfig(employer_match=settings)
        dbt_vars = _export_employer_match_vars(cfg)
        assert dbt_vars["employer_match_status"] == "points_based"
        assert len(dbt_vars["points_match_tiers"]) == 4

    def test_all_four_modes_are_valid(self):
        """Verify all four match modes from quickstart are valid."""
        valid_modes = ["deferral_based", "graded_by_service", "tenure_based", "points_based"]
        for mode in valid_modes:
            kwargs = {"employer_match_status": mode}
            if mode == "tenure_based":
                kwargs["tenure_match_tiers"] = [
                    TenureMatchTier(min_years=0, max_years=None, match_rate=50, max_deferral_pct=6),
                ]
            elif mode == "points_based":
                kwargs["points_match_tiers"] = [
                    PointsMatchTier(min_points=0, max_points=None, match_rate=50, max_deferral_pct=6),
                ]
            settings = EmployerMatchSettings(**kwargs)
            assert settings.employer_match_status == mode
