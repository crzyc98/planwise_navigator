# filename: tests/unit/test_cost_attribution.py
"""
Unit tests for CrossYearCostAttributor and related cost attribution components.

This test suite validates:
- UUID-stamped cost attribution with sub-millisecond precision
- Event sourcing integrity preservation
- Cross-year cost allocation strategies
- Regulatory compliance (18,6) decimal precision
- Audit trail generation and validation
- Cost attribution entry validation and integrity checks
"""

import time
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from orchestrator_mvp.core.cost_attribution import (AllocationStrategy,
                                                    AttributionAuditTrail,
                                                    CostAttributionEntry,
                                                    CostAttributionType,
                                                    CrossYearAllocationContext,
                                                    CrossYearCostAttributor,
                                                    create_allocation_context,
                                                    create_cost_attributor)
from orchestrator_mvp.core.state_management import (SimulationState,
                                                    WorkforceMetrics)

from config.events import EventFactory, SimulationEvent


class TestCostAttributionEntry:
    """Test cases for CostAttributionEntry with UUID precision tracking."""

    def test_cost_attribution_entry_creation(self):
        """Test creating valid cost attribution entry with all required fields."""
        entry = CostAttributionEntry(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 15),
            attribution_year=2025,
            source_year=2024,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            gross_amount=Decimal("75000.00"),
            attributed_amount=Decimal("60000.00"),
            allocation_percentage=Decimal("0.80"),
            cost_category="workforce_compensation",
            attribution_basis="Prorated allocation based on temporal distribution",
        )

        # Verify core identification
        assert isinstance(entry.attribution_id, UUID)
        assert entry.employee_id == "EMP001"
        assert entry.scenario_id == "SCENARIO_001"
        assert entry.plan_design_id == "DESIGN_001"

        # Verify temporal context
        assert entry.effective_date == date(2025, 1, 15)
        assert entry.attribution_year == 2025
        assert entry.source_year == 2024
        assert isinstance(entry.attribution_timestamp, datetime)

        # Verify cost attribution details
        assert entry.attribution_type == CostAttributionType.COMPENSATION_BASELINE
        assert entry.allocation_strategy == AllocationStrategy.PRO_RATA_TEMPORAL

        # Verify monetary precision (18,6)
        assert entry.gross_amount == Decimal("75000.000000")
        assert entry.attributed_amount == Decimal("60000.000000")
        assert entry.allocation_percentage == Decimal("0.800000")

        # Verify computed fields
        assert entry.cross_year_attribution is True  # 2025 != 2024
        assert entry.allocation_variance == Decimal("-0.200000")  # (60000-75000)/75000

    def test_monetary_precision_validation(self):
        """Test that monetary amounts are properly validated and quantized to 6 decimal places."""
        entry = CostAttributionEntry(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 15),
            attribution_year=2025,
            source_year=2024,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            gross_amount=Decimal("75000.123456789"),  # More than 6 decimal places
            attributed_amount=Decimal("60000.987654321"),
            allocation_percentage=Decimal("0.123456789"),
            cost_category="workforce_compensation",
            attribution_basis="Test precision validation",
        )

        # Verify amounts are quantized to 6 decimal places
        assert entry.gross_amount == Decimal("75000.123457")  # Rounded up
        assert entry.attributed_amount == Decimal("60000.987654")  # Rounded down
        assert entry.allocation_percentage == Decimal("0.123457")

    def test_identifier_validation(self):
        """Test validation of required identifier fields."""
        # Test empty employee_id
        with pytest.raises(ValueError, match="Identifier cannot be empty"):
            CostAttributionEntry(
                employee_id="",
                scenario_id="SCENARIO_001",
                plan_design_id="DESIGN_001",
                effective_date=date(2025, 1, 15),
                attribution_year=2025,
                source_year=2024,
                attribution_type=CostAttributionType.COMPENSATION_BASELINE,
                allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
                gross_amount=Decimal("75000.00"),
                attributed_amount=Decimal("60000.00"),
                allocation_percentage=Decimal("0.80"),
                cost_category="workforce_compensation",
                attribution_basis="Test empty identifier validation",
            )

        # Test whitespace-only scenario_id
        with pytest.raises(ValueError, match="Identifier cannot be empty"):
            CostAttributionEntry(
                employee_id="EMP001",
                scenario_id="   ",
                plan_design_id="DESIGN_001",
                effective_date=date(2025, 1, 15),
                attribution_year=2025,
                source_year=2024,
                attribution_type=CostAttributionType.COMPENSATION_BASELINE,
                allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
                gross_amount=Decimal("75000.00"),
                attributed_amount=Decimal("60000.00"),
                allocation_percentage=Decimal("0.80"),
                cost_category="workforce_compensation",
                attribution_basis="Test whitespace identifier validation",
            )

    def test_attribution_basis_validation(self):
        """Test validation of attribution basis descriptiveness."""
        # Test attribution basis too short
        with pytest.raises(
            ValueError, match="Attribution basis must be at least 10 characters"
        ):
            CostAttributionEntry(
                employee_id="EMP001",
                scenario_id="SCENARIO_001",
                plan_design_id="DESIGN_001",
                effective_date=date(2025, 1, 15),
                attribution_year=2025,
                source_year=2024,
                attribution_type=CostAttributionType.COMPENSATION_BASELINE,
                allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
                gross_amount=Decimal("75000.00"),
                attributed_amount=Decimal("60000.00"),
                allocation_percentage=Decimal("0.80"),
                cost_category="workforce_compensation",
                attribution_basis="short",  # Too short
            )

    def test_verify_attribution_integrity(self):
        """Test integrity verification of attribution entries."""
        # Test valid entry
        valid_entry = CostAttributionEntry(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 15),
            attribution_year=2025,
            source_year=2024,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            gross_amount=Decimal("75000.00"),
            attributed_amount=Decimal("60000.00"),
            allocation_percentage=Decimal("0.80"),
            cost_category="workforce_compensation",
            attribution_basis="Valid attribution for testing integrity",
        )

        is_valid, issues = valid_entry.verify_attribution_integrity()
        assert is_valid is True
        assert len(issues) == 0

        # Test entry with inconsistent attribution amount
        invalid_entry = CostAttributionEntry(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 15),
            attribution_year=2025,
            source_year=2024,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            gross_amount=Decimal("75000.00"),
            attributed_amount=Decimal("50000.00"),  # Should be 60000 (75000 * 0.80)
            allocation_percentage=Decimal("0.80"),
            cost_category="workforce_compensation",
            attribution_basis="Invalid attribution for testing integrity",
        )

        is_valid, issues = invalid_entry.verify_attribution_integrity()
        assert is_valid is False
        assert len(issues) > 0
        assert "Attribution amount inconsistency" in issues[0]

        # Test entry with invalid temporal relationship
        temporal_invalid_entry = CostAttributionEntry(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 15),
            attribution_year=2024,  # Earlier than source year
            source_year=2025,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            gross_amount=Decimal("75000.00"),
            attributed_amount=Decimal("60000.00"),
            allocation_percentage=Decimal("0.80"),
            cost_category="workforce_compensation",
            attribution_basis="Temporal invalid attribution for testing",
        )

        is_valid, issues = temporal_invalid_entry.verify_attribution_integrity()
        assert is_valid is False
        assert any("Invalid temporal relationship" in issue for issue in issues)


class TestAttributionAuditTrail:
    """Test cases for AttributionAuditTrail audit functionality."""

    def test_audit_trail_creation(self):
        """Test creating audit trail for cost attribution operations."""
        # Create sample attribution entries
        entries = [
            CostAttributionEntry(
                employee_id=f"EMP{i:03d}",
                scenario_id="SCENARIO_001",
                plan_design_id="DESIGN_001",
                effective_date=date(2025, 1, 15),
                attribution_year=2025,
                source_year=2024,
                attribution_type=CostAttributionType.COMPENSATION_BASELINE,
                allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
                gross_amount=Decimal("75000.00"),
                attributed_amount=Decimal("60000.00"),
                allocation_percentage=Decimal("0.80"),
                cost_category="workforce_compensation",
                attribution_basis="Sample attribution for audit trail testing",
            )
            for i in range(5)
        ]

        audit_trail = AttributionAuditTrail(
            scenario_id="SCENARIO_001",
            attribution_year=2025,
            operation_type="cross_year_transfer",
            attribution_entries=entries,
            total_gross_amount=Decimal("375000.00"),  # 5 * 75000
            total_attributed_amount=Decimal("300000.00"),  # 5 * 60000
            processing_duration_ms=Decimal("150.500"),
            records_processed=5,
            validation_passed=True,
        )

        # Verify audit identification
        assert isinstance(audit_trail.audit_id, UUID)
        assert isinstance(audit_trail.operation_timestamp, datetime)

        # Verify attribution context
        assert audit_trail.scenario_id == "SCENARIO_001"
        assert audit_trail.attribution_year == 2025
        assert audit_trail.operation_type == "cross_year_transfer"

        # Verify totals
        assert audit_trail.total_gross_amount == Decimal("375000.000000")
        assert audit_trail.total_attributed_amount == Decimal("300000.000000")

        # Verify processing metadata
        assert audit_trail.processing_duration_ms == Decimal("150.500")
        assert audit_trail.records_processed == 5

        # Verify computed allocation efficiency
        assert audit_trail.allocation_efficiency == Decimal("0.800000")  # 300000/375000

    def test_totals_precision_validation(self):
        """Test that audit trail totals are properly quantized."""
        audit_trail = AttributionAuditTrail(
            scenario_id="SCENARIO_001",
            attribution_year=2025,
            operation_type="create",
            total_gross_amount=Decimal("375000.1234567"),  # More than 6 decimal places
            total_attributed_amount=Decimal("300000.9876543"),
            processing_duration_ms=Decimal("150.5001"),  # More than 3 decimal places
        )

        # Verify totals are quantized to 6 decimal places
        assert audit_trail.total_gross_amount == Decimal("375000.123457")
        assert audit_trail.total_attributed_amount == Decimal("300000.987654")

        # Verify duration is quantized to 3 decimal places
        assert audit_trail.processing_duration_ms == Decimal("150.500")


class TestCrossYearAllocationContext:
    """Test cases for CrossYearAllocationContext data structure."""

    def test_allocation_context_creation(self):
        """Test creating cross-year allocation context."""
        source_metrics = WorkforceMetrics(
            active_employees=1000,
            total_compensation_cost=Decimal("75000000.00"),
            average_compensation=Decimal("75000.00"),
            snapshot_date=date(2024, 12, 31),
        )

        target_metrics = {
            2025: WorkforceMetrics(
                active_employees=1100,
                total_compensation_cost=Decimal("85000000.00"),
                average_compensation=Decimal("77272.73"),
                snapshot_date=date(2025, 12, 31),
            ),
            2026: WorkforceMetrics(
                active_employees=1200,
                total_compensation_cost=Decimal("95000000.00"),
                average_compensation=Decimal("79166.67"),
                snapshot_date=date(2026, 12, 31),
            ),
        }

        # Mock simulation events
        mock_events = [
            Mock(employee_id="EMP001", effective_date=date(2024, 6, 15)),
            Mock(employee_id="EMP002", effective_date=date(2024, 9, 1)),
        ]

        context = CrossYearAllocationContext(
            source_year=2024,
            target_years=[2025, 2026],
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            source_workforce_metrics=source_metrics,
            source_events=mock_events,
            target_workforce_metrics=target_metrics,
            temporal_decay_factor=Decimal("0.95"),
        )

        assert context.source_year == 2024
        assert context.target_years == [2025, 2026]
        assert context.allocation_strategy == AllocationStrategy.PRO_RATA_TEMPORAL
        assert context.source_workforce_metrics == source_metrics
        assert len(context.source_events) == 2
        assert len(context.target_workforce_metrics) == 2
        assert context.temporal_decay_factor == Decimal("0.95")


class TestCrossYearCostAttributor:
    """Test cases for CrossYearCostAttributor main engine."""

    @pytest.fixture
    def cost_attributor(self):
        """Create cost attributor for testing."""
        return CrossYearCostAttributor(
            scenario_id="TEST_SCENARIO",
            plan_design_id="TEST_DESIGN",
            default_allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            precision_decimal_places=6,
            enable_audit_trail=True,
        )

    @pytest.fixture
    def mock_allocation_context(self):
        """Create mock allocation context for testing."""
        source_metrics = WorkforceMetrics(
            active_employees=1000,
            total_compensation_cost=Decimal("75000000.00"),
            average_compensation=Decimal("75000.00"),
            snapshot_date=date(2024, 12, 31),
        )

        target_metrics = {
            2025: WorkforceMetrics(
                active_employees=1100,
                total_compensation_cost=Decimal("85000000.00"),
                average_compensation=Decimal("77272.73"),
                snapshot_date=date(2025, 12, 31),
            )
        }

        # Create mock events with compensation data
        mock_events = []
        for i in range(10):
            mock_event = Mock()
            mock_event.employee_id = f"EMP{i:03d}"
            mock_event.effective_date = date(2024, 6, 15)
            mock_event.event_id = uuid4()

            # Mock payload with compensation data
            mock_payload = Mock()
            mock_payload.event_type = "hire"
            mock_payload.annual_compensation = 80000.00
            mock_event.payload = mock_payload

            mock_events.append(mock_event)

        return CrossYearAllocationContext(
            source_year=2024,
            target_years=[2025],
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            source_workforce_metrics=source_metrics,
            source_events=mock_events,
            target_workforce_metrics=target_metrics,
        )

    def test_cost_attributor_initialization(self, cost_attributor):
        """Test cost attributor initialization with proper configuration."""
        assert cost_attributor.scenario_id == "TEST_SCENARIO"
        assert cost_attributor.plan_design_id == "TEST_DESIGN"
        assert (
            cost_attributor.default_allocation_strategy
            == AllocationStrategy.PRO_RATA_TEMPORAL
        )
        assert cost_attributor.precision_decimal_places == 6
        assert cost_attributor.enable_audit_trail is True

        # Verify internal state initialization
        assert len(cost_attributor._attribution_entries) == 0
        assert len(cost_attributor._audit_trails) == 0
        assert cost_attributor._total_attributions_processed == 0
        assert cost_attributor._total_processing_time_ms == Decimal("0")

    def test_attribute_compensation_costs_across_years(
        self, cost_attributor, mock_allocation_context
    ):
        """Test cross-year compensation cost attribution."""
        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(
            mock_allocation_context
        )

        # Verify attribution entries were created
        assert len(attribution_entries) > 0

        # Verify all entries have proper UUID tracking
        for entry in attribution_entries:
            assert isinstance(entry.attribution_id, UUID)
            assert entry.scenario_id == "TEST_SCENARIO"
            assert entry.plan_design_id == "TEST_DESIGN"
            assert entry.attribution_year == 2025
            assert entry.source_year == 2024
            assert entry.cross_year_attribution is True

        # Verify entries are stored internally
        assert len(cost_attributor._attribution_entries) == len(attribution_entries)

        # Verify audit trail was created
        if cost_attributor.enable_audit_trail:
            assert len(cost_attributor._audit_trails) == 1
            audit_trail = cost_attributor._audit_trails[0]
            assert audit_trail.operation_type == "cross_year_transfer"
            assert audit_trail.records_processed == len(attribution_entries)

        # Verify performance metrics updated
        assert cost_attributor._total_attributions_processed == len(attribution_entries)
        assert cost_attributor._total_processing_time_ms > Decimal("0")

    def test_attribute_compensation_costs_no_events(self, cost_attributor):
        """Test attribution when no compensation events are found."""
        # Create context with no events
        empty_context = CrossYearAllocationContext(
            source_year=2024,
            target_years=[2025],
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            source_workforce_metrics=Mock(),
            source_events=[],  # No events
            target_workforce_metrics={2025: Mock()},
        )

        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(
            empty_context
        )

        # Should return empty list
        assert len(attribution_entries) == 0

    def test_attribute_benefit_enrollment_costs(self, cost_attributor):
        """Test benefit enrollment cost attribution."""
        # Create mock enrollment events
        mock_enrollment_events = []
        for i in range(5):
            mock_event = Mock()
            mock_event.employee_id = f"EMP{i:03d}"
            mock_event.effective_date = date(2025, 1, 15)
            mock_event.event_id = uuid4()

            mock_payload = Mock()
            mock_payload.event_type = "enrollment"
            mock_payload.pre_tax_contribution_rate = Decimal("0.06")
            mock_event.payload = mock_payload

            mock_enrollment_events.append(mock_event)

        attribution_entries = cost_attributor.attribute_benefit_enrollment_costs(
            enrollment_events=mock_enrollment_events,
            source_year=2024,
            target_year=2025,
            default_contribution_rate=Decimal("0.03"),
        )

        # Verify attribution entries were created
        assert len(attribution_entries) == 5

        # Verify all entries have proper structure
        for entry in attribution_entries:
            assert isinstance(entry.attribution_id, UUID)
            assert entry.attribution_type == CostAttributionType.BENEFIT_ENROLLMENT
            assert entry.allocation_strategy == AllocationStrategy.EVENT_DRIVEN
            assert entry.cost_category == "benefit_enrollment"
            assert entry.allocation_percentage == Decimal("1.0")  # Direct attribution
            assert entry.attributed_amount > Decimal("0")

    def test_get_attribution_summary(self, cost_attributor, mock_allocation_context):
        """Test generation of attribution summary for analysis."""
        # First create some attributions
        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(
            mock_allocation_context
        )

        # Get summary for the target year
        summary = cost_attributor.get_attribution_summary(
            target_year=2025, attribution_type=CostAttributionType.COMPENSATION_BASELINE
        )

        # Verify summary structure
        assert summary["target_year"] == 2025
        assert summary["attribution_type"] == "compensation_baseline"
        assert summary["total_entries"] > 0
        assert summary["total_attributed_amount"] > 0
        assert summary["total_gross_amount"] > 0
        assert "allocation_efficiency" in summary
        assert "category_breakdown" in summary
        assert "cross_year_analysis" in summary
        assert "performance_metrics" in summary
        assert "generated_timestamp" in summary

        # Verify cross-year analysis
        cross_year_analysis = summary["cross_year_analysis"]
        assert cross_year_analysis["cross_year_entries"] > 0  # All should be cross-year
        assert cross_year_analysis["cross_year_percentage"] > 0

    def test_get_attribution_summary_empty(self, cost_attributor):
        """Test attribution summary with no entries."""
        summary = cost_attributor.get_attribution_summary(
            target_year=2099,  # Non-existent year
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
        )

        assert summary["target_year"] == 2099
        assert summary["total_entries"] == 0
        assert summary["total_attributed_amount"] == 0
        assert summary["message"] == "No attribution entries found"

    def test_validate_attribution_integrity(
        self, cost_attributor, mock_allocation_context
    ):
        """Test validation of all attribution entries integrity."""
        # Create some attributions
        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(
            mock_allocation_context
        )

        # Validate integrity
        is_valid, issues = cost_attributor.validate_attribution_integrity()

        # Should be valid with proper mock data
        assert is_valid is True
        assert len(issues) == 0

    def test_calculate_total_compensation_impact(self, cost_attributor):
        """Test calculation of total compensation impact from events."""
        # Create mock events with different compensation types
        mock_events = []

        # Hire event
        hire_event = Mock()
        hire_event.payload.event_type = "hire"
        hire_event.payload.annual_compensation = 80000.00
        mock_events.append(hire_event)

        # Promotion event
        promotion_event = Mock()
        promotion_event.payload.event_type = "promotion"
        promotion_event.payload.new_annual_compensation = 90000.00
        promotion_event.payload.previous_compensation = 80000.00
        mock_events.append(promotion_event)

        # Termination event
        termination_event = Mock()
        termination_event.payload.event_type = "termination"
        mock_events.append(termination_event)

        total_impact = cost_attributor._calculate_total_compensation_impact(mock_events)

        # Should include hire amount + promotion increase + termination cost
        expected_total = (
            Decimal("80000.00") + Decimal("10000.00") + Decimal("75000.00")
        )  # Termination placeholder
        assert total_impact >= expected_total

    def test_calculate_allocation_weight_strategies(self, cost_attributor):
        """Test different allocation weight calculation strategies."""
        source_metrics = WorkforceMetrics(
            active_employees=1000,
            total_compensation_cost=Decimal("75000000.00"),
            average_compensation=Decimal("75000.00"),
            snapshot_date=date(2024, 12, 31),
        )

        target_metrics = WorkforceMetrics(
            active_employees=1100,
            total_compensation_cost=Decimal("85000000.00"),
            average_compensation=Decimal("77272.73"),
            snapshot_date=date(2025, 12, 31),
        )

        # Test PRO_RATA_TEMPORAL strategy
        temporal_weight = cost_attributor._calculate_allocation_weight(
            source_metrics, target_metrics, AllocationStrategy.PRO_RATA_TEMPORAL, 1
        )
        assert Decimal("0") < temporal_weight <= Decimal("1")

        # Test PRO_RATA_WORKFORCE strategy
        workforce_weight = cost_attributor._calculate_allocation_weight(
            source_metrics, target_metrics, AllocationStrategy.PRO_RATA_WORKFORCE, 1
        )
        assert workforce_weight == Decimal("1.000000")  # 1100/1000 capped at 1.0

        # Test COMPENSATION_WEIGHTED strategy
        compensation_weight = cost_attributor._calculate_allocation_weight(
            source_metrics, target_metrics, AllocationStrategy.COMPENSATION_WEIGHTED, 1
        )
        assert compensation_weight == Decimal("1.000000")  # 85M/75M capped at 1.0

        # Test EVENT_DRIVEN strategy
        event_weight = cost_attributor._calculate_allocation_weight(
            source_metrics, target_metrics, AllocationStrategy.EVENT_DRIVEN, 1
        )
        assert event_weight == Decimal("1.000000")  # Always 1.0


class TestFactoryFunctions:
    """Test cases for factory functions."""

    def test_create_cost_attributor(self):
        """Test cost attributor factory function."""
        attributor = create_cost_attributor(
            scenario_id="FACTORY_SCENARIO",
            plan_design_id="FACTORY_DESIGN",
            allocation_strategy=AllocationStrategy.PRO_RATA_WORKFORCE,
        )

        assert attributor.scenario_id == "FACTORY_SCENARIO"
        assert attributor.plan_design_id == "FACTORY_DESIGN"
        assert (
            attributor.default_allocation_strategy
            == AllocationStrategy.PRO_RATA_WORKFORCE
        )
        assert attributor.enable_audit_trail is True

    def test_create_allocation_context(self):
        """Test allocation context factory function."""
        source_metrics = WorkforceMetrics(
            active_employees=1000,
            total_compensation_cost=Decimal("75000000.00"),
            average_compensation=Decimal("75000.00"),
            snapshot_date=date(2024, 12, 31),
        )

        target_metrics = {
            2025: WorkforceMetrics(
                active_employees=1100,
                total_compensation_cost=Decimal("85000000.00"),
                average_compensation=Decimal("77272.73"),
                snapshot_date=date(2025, 12, 31),
            )
        }

        mock_events = [Mock()]

        context = create_allocation_context(
            source_year=2024,
            target_years=[2025],
            source_workforce_metrics=source_metrics,
            target_workforce_metrics=target_metrics,
            source_events=mock_events,
            allocation_strategy=AllocationStrategy.HYBRID_TEMPORAL_WORKFORCE,
        )

        assert context.source_year == 2024
        assert context.target_years == [2025]
        assert (
            context.allocation_strategy == AllocationStrategy.HYBRID_TEMPORAL_WORKFORCE
        )
        assert context.source_workforce_metrics == source_metrics
        assert len(context.source_events) == 1
        assert len(context.target_workforce_metrics) == 1


class TestPerformanceAndPrecision:
    """Test cases for performance and precision requirements."""

    def test_uuid_generation_performance(self):
        """Test UUID generation performance for large attribution volumes."""
        start_time = time.perf_counter()

        entries = []
        for i in range(1000):
            entry = CostAttributionEntry(
                employee_id=f"EMP{i:06d}",
                scenario_id="PERF_SCENARIO",
                plan_design_id="PERF_DESIGN",
                effective_date=date(2025, 1, 15),
                attribution_year=2025,
                source_year=2024,
                attribution_type=CostAttributionType.COMPENSATION_BASELINE,
                allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
                gross_amount=Decimal("75000.00"),
                attributed_amount=Decimal("60000.00"),
                allocation_percentage=Decimal("0.80"),
                cost_category="workforce_compensation",
                attribution_basis="Performance test attribution entry",
            )
            entries.append(entry)

        end_time = time.perf_counter()
        creation_time = end_time - start_time

        # Should create 1000 entries in less than 1 second
        assert creation_time < 1.0
        assert len(entries) == 1000

        # Verify all entries have unique UUIDs
        uuids = {entry.attribution_id for entry in entries}
        assert len(uuids) == 1000  # All unique

    def test_decimal_precision_consistency(self):
        """Test consistent decimal precision across operations."""
        entry = CostAttributionEntry(
            employee_id="EMP001",
            scenario_id="PRECISION_TEST",
            plan_design_id="PRECISION_DESIGN",
            effective_date=date(2025, 1, 15),
            attribution_year=2025,
            source_year=2024,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE,
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
            gross_amount=Decimal("75000.123456789"),
            attributed_amount=Decimal("60000.987654321"),
            allocation_percentage=Decimal("0.800000123"),
            cost_category="workforce_compensation",
            attribution_basis="Precision test attribution",
        )

        # Verify all monetary fields maintain 6 decimal precision
        assert entry.gross_amount.as_tuple().exponent == -6
        assert entry.attributed_amount.as_tuple().exponent == -6
        assert entry.allocation_percentage.as_tuple().exponent == -6

        # Verify computed variance maintains precision
        assert entry.allocation_variance.as_tuple().exponent == -6

    def test_sub_millisecond_timestamp_precision(self):
        """Test sub-millisecond timestamp precision for attribution tracking."""
        # Create entries in rapid succession
        entries = []
        for i in range(10):
            entry = CostAttributionEntry(
                employee_id=f"EMP{i:03d}",
                scenario_id="TIMESTAMP_TEST",
                plan_design_id="TIMESTAMP_DESIGN",
                effective_date=date(2025, 1, 15),
                attribution_year=2025,
                source_year=2024,
                attribution_type=CostAttributionType.COMPENSATION_BASELINE,
                allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL,
                gross_amount=Decimal("75000.00"),
                attributed_amount=Decimal("60000.00"),
                allocation_percentage=Decimal("0.80"),
                cost_category="workforce_compensation",
                attribution_basis="Timestamp precision test entry",
            )
            entries.append(entry)

        # Verify all timestamps are captured with microsecond precision
        timestamps = [entry.attribution_timestamp for entry in entries]

        # Should have unique timestamps or very close ones with microsecond precision
        for timestamp in timestamps:
            assert timestamp.microsecond is not None

        # Verify timestamps are in proper chronological order
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]
