"""Tests for output_parser module."""

import pytest

from planalign_api.services.simulation.output_parser import (
    SimulationOutputParser,
    STAGE_PATTERNS,
)


@pytest.mark.fast
class TestSimulationOutputParser:
    """Test SimulationOutputParser."""

    def test_initial_state(self):
        """Parser starts at start_year with INITIALIZATION stage."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)
        assert parser.current_year == 2025
        assert parser.current_stage == "INITIALIZATION"
        assert parser.events_generated == 0
        assert parser.recent_events == []

    def test_detects_year_change(self):
        """Should detect year transitions from output lines."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)

        changes = parser.parse_line("Processing Year: 2026")

        assert changes["year_changed"] is True
        assert parser.current_year == 2026
        assert len(parser.recent_events) == 1
        assert parser.recent_events[0]["event_type"] == "INFO"

    def test_no_year_change_for_same_year(self):
        """Should not flag year_changed when year is the same."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)

        changes = parser.parse_line("Year: 2025 starting")

        assert changes["year_changed"] is False

    def test_detects_stage_transitions(self):
        """Should detect stage changes from keywords."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)

        changes = parser.parse_line("Building foundation models")

        assert changes["stage_changed"] is True
        assert parser.current_stage == "FOUNDATION"

    def test_all_stages_detected(self):
        """Each stage pattern should be detectable."""
        test_lines = {
            "INITIALIZATION": "Initializing simulation",
            "FOUNDATION": "Building baseline workforce",
            "EVENT_GENERATION": "Generating events",
            "STATE_ACCUMULATION": "Building state accumulator",
            "VALIDATION": "Running validation checks",
            "REPORTING": "Completed all models",
        }
        for expected_stage, line in test_lines.items():
            parser = SimulationOutputParser(start_year=2025, total_years=3)
            # Reset to a different stage so we detect the change
            parser.current_stage = "NONE"
            parser.parse_line(line)
            assert parser.current_stage == expected_stage, (
                f"Expected {expected_stage} for '{line}', got {parser.current_stage}"
            )

    def test_parses_event_count(self):
        """Should extract event counts from output."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)

        parser.parse_line("Generated 450 events for year 2025")

        assert parser.events_generated == 450

    def test_parses_individual_event(self):
        """Should extract individual event entries."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)

        changes = parser.parse_line("HIRE: EMP_2025_001 added to Engineering")

        assert changes["new_event"] is not None
        assert changes["new_event"]["event_type"] == "HIRE"
        assert changes["new_event"]["employee_id"] == "EMP_2025_001"

    def test_recent_events_capped(self):
        """Should cap recent_events to MAX_RECENT_EVENTS."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)

        for i in range(30):
            parser.parse_line(f"HIRE: EMP_{i:03d} hired")

        assert len(parser.recent_events) == 20  # MAX_RECENT_EVENTS

    def test_calculate_progress(self):
        """Should return progress based on current year position."""
        parser = SimulationOutputParser(start_year=2025, total_years=3)
        assert parser.calculate_progress() == 10  # 0/3 * 100 + 10

        parser.current_year = 2026
        assert parser.calculate_progress() == 43  # 1/3 * 100 + 10 ≈ 43

        parser.current_year = 2027
        assert parser.calculate_progress() == 76  # 2/3 * 100 + 10 ≈ 76

    def test_progress_never_exceeds_99(self):
        """Progress should cap at 99 during execution."""
        parser = SimulationOutputParser(start_year=2025, total_years=1)
        # Even at 100% + 10 offset, should cap at 99
        parser.current_year = 2026  # One beyond end
        assert parser.calculate_progress() == 99


@pytest.mark.fast
class TestClassifyLine:
    """Test the static classify_line method."""

    def test_error_lines(self):
        assert SimulationOutputParser.classify_line("ERROR: something broke") == "error"
        assert SimulationOutputParser.classify_line("Traceback (most recent)") == "error"
        assert SimulationOutputParser.classify_line("dbt run failed") == "error"

    def test_warning_lines(self):
        assert SimulationOutputParser.classify_line("WARNING: low memory") == "warning"

    def test_debug_lines(self):
        assert SimulationOutputParser.classify_line("Running model int_hire_events") == "debug"
        assert SimulationOutputParser.classify_line("") == "debug"
