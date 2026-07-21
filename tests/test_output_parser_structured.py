"""Fast tests for structured stdout parsing in SimulationOutputParser (feature 094).

Contract: specs/094-live-run-dashboard/contracts/telemetry-stdout-protocol.md
"""

import json

import pytest

from planalign_api.services.simulation.output_parser import (
    STRUCTURED_SENTINEL,
    SimulationOutputParser,
)

pytestmark = [pytest.mark.fast]


def sentinel_line(record: dict) -> str:
    return STRUCTURED_SENTINEL + json.dumps(record)


@pytest.fixture
def parser():
    return SimulationOutputParser(start_year=2025, total_years=3)


class TestSentinelFastPath:
    def test_stage_started_updates_stage_and_year(self, parser):
        changes = parser.parse_line(
            sentinel_line(
                {
                    "v": 1,
                    "record": "stage_started",
                    "ts": "2026-06-10T00:00:00Z",
                    "year": 2026,
                    "stage": "STATE_ACCUMULATION",
                }
            )
        )
        assert changes["structured_record"]["record"] == "stage_started"
        assert parser.current_stage == "STATE_ACCUMULATION"
        assert parser.current_year == 2026
        assert changes["stage_changed"] is True
        assert changes["year_changed"] is True

    def test_year_completed_exposes_counts(self, parser):
        changes = parser.parse_line(
            sentinel_line(
                {
                    "v": 1,
                    "record": "year_completed",
                    "ts": "t",
                    "year": 2025,
                    "duration_seconds": 48.2,
                    "event_counts": {"HIRE": 142, "TERMINATION": 98},
                    "cumulative_counts": {"HIRE": 142, "TERMINATION": 98},
                }
            )
        )
        rec = changes["structured_record"]
        assert rec["event_counts"] == {"HIRE": 142, "TERMINATION": 98}
        assert parser.events_generated == 240  # sum of cumulative counts

    def test_unknown_record_type_is_passed_through(self, parser):
        changes = parser.parse_line(
            sentinel_line({"v": 1, "record": "future_thing", "ts": "t"})
        )
        assert changes["structured_record"]["record"] == "future_thing"

    def test_malformed_sentinel_does_not_raise(self, parser):
        changes = parser.parse_line(STRUCTURED_SENTINEL + "{not json")
        assert changes["structured_record"] is None
        assert parser.current_stage == "INITIALIZATION"


class TestRegexSuppression:
    def test_regex_fallback_active_before_any_structured_record(self, parser):
        parser.parse_line("Generating events for workforce")
        assert parser.current_stage == "EVENT_GENERATION"

    def test_regex_stage_suppressed_after_structured_record(self, parser):
        parser.parse_line(
            sentinel_line(
                {
                    "v": 1,
                    "record": "stage_started",
                    "ts": "t",
                    "year": 2025,
                    "stage": "FOUNDATION",
                }
            )
        )
        # A noisy log line that the old regex would misread as a stage change
        parser.parse_line("dbt completed model int_validation_rules")
        assert parser.current_stage == "FOUNDATION"

    def test_regex_event_count_suppressed_after_structured_record(self, parser):
        parser.parse_line(
            sentinel_line(
                {
                    "v": 1,
                    "record": "year_completed",
                    "ts": "t",
                    "year": 2025,
                    "duration_seconds": 1.0,
                    "event_counts": {"HIRE": 10},
                    "cumulative_counts": {"HIRE": 10},
                }
            )
        )
        parser.parse_line("processed 99999 events in batch")
        assert parser.events_generated == 10

    def test_plain_lines_still_classified_for_severity(self, parser):
        assert SimulationOutputParser.classify_line("ERROR: boom") == "error"
        assert SimulationOutputParser.classify_line("Warning: check") == "warning"
        assert SimulationOutputParser.classify_line("building model") == "debug"

    def test_structured_validation_uses_disposition_not_rule_severity(self):
        passed = sentinel_line(
            {
                "record": "validation_results",
                "disposition": "passed",
                "results": [{"severity": "error", "passed": True}],
            }
        )
        failed = sentinel_line(
            {
                "record": "validation_results",
                "disposition": "failed",
                "results": [{"severity": "error", "passed": False}],
            }
        )

        assert SimulationOutputParser.classify_line(passed) == "debug"
        assert SimulationOutputParser.classify_line(failed) == "error"
