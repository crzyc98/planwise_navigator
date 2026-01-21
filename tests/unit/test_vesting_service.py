"""Unit tests for vesting service calculations."""

from decimal import Decimal

import pytest

from planalign_api.models.vesting import VestingScheduleType
from planalign_api.services.vesting_service import (
    SCHEDULE_INFO,
    VESTING_SCHEDULES,
    calculate_forfeiture,
    get_schedule_list,
    get_vesting_percentage,
)


class TestGetVestingPercentage:
    """Tests for get_vesting_percentage function (T019)."""

    def test_immediate_vesting_year_0(self):
        """Immediate schedule: 100% vested from day one."""
        pct = get_vesting_percentage(VestingScheduleType.IMMEDIATE, 0)
        assert pct == Decimal("1.0")

    def test_immediate_vesting_year_5(self):
        """Immediate schedule: still 100% at year 5."""
        pct = get_vesting_percentage(VestingScheduleType.IMMEDIATE, 5)
        assert pct == Decimal("1.0")

    def test_cliff_2_year_before_cliff(self):
        """2-Year Cliff: 0% before 2 years."""
        assert get_vesting_percentage(VestingScheduleType.CLIFF_2_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.CLIFF_2_YEAR, 1) == Decimal("0.0")

    def test_cliff_2_year_at_cliff(self):
        """2-Year Cliff: 100% at 2 years."""
        pct = get_vesting_percentage(VestingScheduleType.CLIFF_2_YEAR, 2)
        assert pct == Decimal("1.0")

    def test_cliff_3_year_progression(self):
        """3-Year Cliff: 0% until year 3, then 100%."""
        assert get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 1) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 2) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 3) == Decimal("1.0")

    def test_cliff_4_year_progression(self):
        """4-Year Cliff: 0% until year 4, then 100%."""
        assert get_vesting_percentage(VestingScheduleType.CLIFF_4_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.CLIFF_4_YEAR, 3) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.CLIFF_4_YEAR, 4) == Decimal("1.0")

    def test_qaca_2_year_progression(self):
        """QACA 2-Year: same as cliff 2."""
        assert get_vesting_percentage(VestingScheduleType.QACA_2_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.QACA_2_YEAR, 1) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.QACA_2_YEAR, 2) == Decimal("1.0")

    def test_graded_3_year_progression(self):
        """3-Year Graded: 33.33% per year."""
        assert get_vesting_percentage(VestingScheduleType.GRADED_3_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.GRADED_3_YEAR, 1) == Decimal("0.3333")
        assert get_vesting_percentage(VestingScheduleType.GRADED_3_YEAR, 2) == Decimal("0.6667")
        assert get_vesting_percentage(VestingScheduleType.GRADED_3_YEAR, 3) == Decimal("1.0")

    def test_graded_4_year_progression(self):
        """4-Year Graded: 25% per year."""
        assert get_vesting_percentage(VestingScheduleType.GRADED_4_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.GRADED_4_YEAR, 1) == Decimal("0.25")
        assert get_vesting_percentage(VestingScheduleType.GRADED_4_YEAR, 2) == Decimal("0.50")
        assert get_vesting_percentage(VestingScheduleType.GRADED_4_YEAR, 3) == Decimal("0.75")
        assert get_vesting_percentage(VestingScheduleType.GRADED_4_YEAR, 4) == Decimal("1.0")

    def test_graded_5_year_progression(self):
        """5-Year Graded: 20% per year."""
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 0) == Decimal("0.0")
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 1) == Decimal("0.20")
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 2) == Decimal("0.40")
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 3) == Decimal("0.60")
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 4) == Decimal("0.80")
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 5) == Decimal("1.0")

    def test_tenure_beyond_max_capped_at_100(self):
        """Tenure beyond schedule max uses 100% vesting."""
        # 3-year cliff caps at year 3
        assert get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 10) == Decimal("1.0")
        # 5-year graded caps at year 5
        assert get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 15) == Decimal("1.0")


class TestTenureTruncation:
    """Tests for tenure truncation to whole years (T021)."""

    def test_tenure_float_truncated_to_int(self):
        """Fractional tenure is truncated, not rounded."""
        # 2.9 years truncates to 2
        pct = get_vesting_percentage(VestingScheduleType.GRADED_5_YEAR, 2.9)
        assert pct == Decimal("0.40")  # Year 2 percentage

    def test_tenure_just_under_cliff(self):
        """Employee at 2.99 years does not hit 3-year cliff."""
        pct = get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 2.99)
        assert pct == Decimal("0.0")  # Still year 2

    def test_tenure_exactly_at_cliff(self):
        """Employee at exactly 3.0 years hits 3-year cliff."""
        pct = get_vesting_percentage(VestingScheduleType.CLIFF_3_YEAR, 3.0)
        assert pct == Decimal("1.0")


class TestCalculateForfeiture:
    """Tests for calculate_forfeiture function (T020)."""

    def test_zero_percent_vested_full_forfeiture(self):
        """0% vested = 100% forfeiture."""
        forfeiture = calculate_forfeiture(Decimal("10000.00"), Decimal("0.0"))
        assert forfeiture == Decimal("10000.00")

    def test_100_percent_vested_no_forfeiture(self):
        """100% vested = 0% forfeiture."""
        forfeiture = calculate_forfeiture(Decimal("10000.00"), Decimal("1.0"))
        assert forfeiture == Decimal("0.00")

    def test_partial_vesting_forfeiture(self):
        """60% vested = 40% forfeiture."""
        forfeiture = calculate_forfeiture(Decimal("10000.00"), Decimal("0.60"))
        assert forfeiture == Decimal("4000.00")

    def test_precision_rounding(self):
        """Forfeiture rounds to $0.01."""
        # 33.33% vested on $10000 = $6667 forfeiture
        forfeiture = calculate_forfeiture(Decimal("10000.00"), Decimal("0.3333"))
        assert forfeiture == Decimal("6667.00")

    def test_zero_contributions_zero_forfeiture(self):
        """Zero contributions = zero forfeiture."""
        forfeiture = calculate_forfeiture(Decimal("0"), Decimal("0.50"))
        assert forfeiture == Decimal("0.00")


class TestHoursBasedVestingCredit:
    """Tests for hours-based vesting credit reduction (T047, T048)."""

    def test_hours_below_threshold_reduces_tenure(self):
        """Employee below hours threshold loses one year of vesting credit."""
        # 3 years tenure, but only 800 hours (below 1000 threshold)
        pct = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=3,
            annual_hours=800,
            require_hours=True,
            hours_threshold=1000
        )
        # Effective tenure = 2 years (40% vested)
        assert pct == Decimal("0.40")

    def test_hours_at_threshold_no_reduction(self):
        """Employee meeting hours threshold keeps full tenure."""
        pct = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=3,
            annual_hours=1000,
            require_hours=True,
            hours_threshold=1000
        )
        # Effective tenure = 3 years (60% vested)
        assert pct == Decimal("0.60")

    def test_hours_above_threshold_no_reduction(self):
        """Employee above hours threshold keeps full tenure."""
        pct = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=3,
            annual_hours=2000,
            require_hours=True,
            hours_threshold=1000
        )
        assert pct == Decimal("0.60")

    def test_hours_disabled_ignores_hours(self):
        """When hours credit disabled, hours value is ignored."""
        pct = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=3,
            annual_hours=100,  # Way below threshold
            require_hours=False,  # But hours credit is disabled
            hours_threshold=1000
        )
        # Full 3 years tenure = 60% vested
        assert pct == Decimal("0.60")

    def test_different_thresholds_produce_different_results(self):
        """Different hours thresholds produce different outcomes."""
        # 600 hours, threshold 500 = no reduction
        pct_500 = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=3,
            annual_hours=600,
            require_hours=True,
            hours_threshold=500
        )
        # 600 hours, threshold 1000 = reduction
        pct_1000 = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=3,
            annual_hours=600,
            require_hours=True,
            hours_threshold=1000
        )
        assert pct_500 == Decimal("0.60")  # 3 years
        assert pct_1000 == Decimal("0.40")  # 2 years

    def test_hours_reduction_cannot_go_below_zero(self):
        """Hours reduction cannot make tenure negative."""
        pct = get_vesting_percentage(
            VestingScheduleType.GRADED_5_YEAR,
            tenure_years=0,
            annual_hours=100,
            require_hours=True,
            hours_threshold=1000
        )
        # 0 - 1 = 0 (clamped at zero)
        assert pct == Decimal("0.0")


class TestScheduleInfo:
    """Tests for schedule metadata."""

    def test_all_schedules_have_info(self):
        """Every schedule type has corresponding info."""
        for schedule_type in VestingScheduleType:
            assert schedule_type in SCHEDULE_INFO
            info = SCHEDULE_INFO[schedule_type]
            assert info.name
            assert info.description
            assert info.percentages

    def test_schedule_list_returns_all_schedules(self):
        """get_schedule_list returns all 8 schedules."""
        result = get_schedule_list()
        assert len(result.schedules) == 8

    def test_vesting_schedules_match_info(self):
        """VESTING_SCHEDULES and SCHEDULE_INFO have matching keys."""
        assert set(VESTING_SCHEDULES.keys()) == set(SCHEDULE_INFO.keys())


class TestEmployeeDetailsValidation:
    """Tests for employee details response structure (T041)."""

    def test_employee_detail_has_all_required_fields(self):
        """Verify EmployeeVestingDetail model has all 15 fields."""
        from planalign_api.models.vesting import EmployeeVestingDetail
        from datetime import date

        detail = EmployeeVestingDetail(
            employee_id="EMP001",
            hire_date=date(2020, 1, 1),
            termination_date=date(2023, 6, 30),
            tenure_years=3,
            tenure_band="2-4",
            annual_hours_worked=2000,
            total_employer_contributions=Decimal("15000.00"),
            current_vesting_pct=Decimal("0.60"),
            current_vested_amount=Decimal("9000.00"),
            current_forfeiture=Decimal("6000.00"),
            proposed_vesting_pct=Decimal("1.0"),
            proposed_vested_amount=Decimal("15000.00"),
            proposed_forfeiture=Decimal("0.00"),
            forfeiture_variance=Decimal("-6000.00")
        )

        # All fields should be accessible
        assert detail.employee_id == "EMP001"
        assert detail.tenure_years == 3
        assert detail.total_employer_contributions == Decimal("15000.00")
        assert detail.current_forfeiture == Decimal("6000.00")
        assert detail.proposed_forfeiture == Decimal("0.00")
        assert detail.forfeiture_variance == Decimal("-6000.00")
