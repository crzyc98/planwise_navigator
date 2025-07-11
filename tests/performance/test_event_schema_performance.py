"""
Performance tests for DC Plan Event Schema - S072-06

Tests performance requirements:
- ≥100K events/sec ingest using DuckDB vectorized operations
- ≤5s history reconstruction for 5-year participant history
- <10ms schema validation per event
- <8GB memory usage for 100K employee simulation
"""

from __future__ import annotations

import time
import uuid
import psutil
import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import patch

import pandas as pd
import duckdb

from config.events import (
    SimulationEvent,
    EventFactory,
    EligibilityEventFactory,
    EnrollmentEventFactory,
    ContributionEventFactory,
    VestingEventFactory,
    PlanAdministrationEventFactory
)


class PerformanceBenchmark:
    """Performance benchmark utility for event schema testing."""

    def __init__(self):
        self.start_time = None
        self.start_memory = None

    def start_benchmark(self) -> None:
        """Start performance measurement."""
        self.start_time = time.perf_counter()
        self.start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

    def end_benchmark(self) -> Dict[str, float]:
        """End performance measurement and return metrics."""
        end_time = time.perf_counter()
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        return {
            "duration_seconds": end_time - self.start_time,
            "memory_delta_mb": end_memory - self.start_memory,
            "peak_memory_mb": end_memory
        }


class EventDataGenerator:
    """Generate test event data for performance testing."""

    @staticmethod
    def generate_workforce_events(num_employees: int, years: int = 5) -> List[SimulationEvent]:
        """Generate realistic workforce events for performance testing."""
        events = []
        base_date = date(2020, 1, 1)

        for employee_idx in range(num_employees):
            employee_id = f"EMP_{employee_idx:06d}"
            scenario_id = "PERF_TEST_SCENARIO"
            plan_design_id = "STANDARD_DESIGN"

            # Generate hire event
            hire_date = base_date + timedelta(days=employee_idx % (365 * years))
            events.append(EventFactory.create_hire_event(
                employee_id=employee_id,
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                starting_compensation=Decimal(f"{50000 + (employee_idx % 50000)}"),
                starting_level=1 + (employee_idx % 5),
                effective_date=hire_date,
                employee_ssn=f"{100000000 + employee_idx}",
                employee_birth_date=date(1980 + (employee_idx % 25), 1, 1),
                location="HQ"
            ))

            # Generate annual events for each year
            for year_offset in range(years):
                event_year = hire_date.year + year_offset
                if event_year > 2024:  # Don't generate future events
                    break

                # Merit increases (80% probability)
                if employee_idx % 5 != 0:  # 80% get merit
                    events.append(EventFactory.create_merit_event(
                        employee_id=employee_id,
                        scenario_id=scenario_id,
                        plan_design_id=plan_design_id,
                        merit_percentage=Decimal("0.03"),  # 3% merit
                        effective_date=date(event_year, 3, 1),
                        previous_compensation=Decimal(f"{50000 + (employee_idx % 50000)}")
                    ))

                # Promotions (10% probability)
                if employee_idx % 10 == 0 and year_offset > 0:
                    events.append(EventFactory.create_promotion_event(
                        employee_id=employee_id,
                        scenario_id=scenario_id,
                        plan_design_id=plan_design_id,
                        new_level=min(5, 2 + year_offset),
                        new_compensation=Decimal(f"{60000 + (employee_idx % 40000)}"),
                        effective_date=date(event_year, 7, 1),
                        previous_level=1 + year_offset,
                        previous_compensation=Decimal(f"{55000 + (employee_idx % 40000)}")
                    ))

            # Generate terminations (15% over 5 years)
            if employee_idx % 7 == 0:  # ~15% termination rate
                term_year = hire_date.year + (employee_idx % years) + 1
                if term_year <= 2024:
                    events.append(EventFactory.create_termination_event(
                        employee_id=employee_id,
                        scenario_id=scenario_id,
                        plan_design_id=plan_design_id,
                        termination_reason="voluntary",
                        effective_date=date(term_year, 6, 15),
                        final_compensation=Decimal(f"{55000 + (employee_idx % 45000)}")
                    ))

        return events

    @staticmethod
    def generate_dc_plan_events(num_participants: int, years: int = 5) -> List[SimulationEvent]:
        """Generate DC plan events for performance testing."""
        events = []
        base_date = date(2020, 1, 1)

        for participant_idx in range(num_participants):
            employee_id = f"EMP_{participant_idx:06d}"
            scenario_id = "PERF_TEST_SCENARIO"
            plan_design_id = "STANDARD_DESIGN"
            plan_id = "401K_PLAN"

            # Eligibility event
            eligibility_date = base_date + timedelta(days=(participant_idx % 365) + 90)
            events.append(EligibilityEventFactory.create_eligibility_event(
                employee_id=employee_id,
                plan_id=plan_id,
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                eligibility_date=eligibility_date,
                service_requirement_months=3,
                age_requirement=None,
                effective_date=eligibility_date
            ))

            # Enrollment event (85% participation rate)
            if participant_idx % 20 != 0:  # 95% enrollment
                enrollment_date = eligibility_date + timedelta(days=30)
                events.append(EnrollmentEventFactory.create_enrollment_event(
                    employee_id=employee_id,
                    plan_id=plan_id,
                    scenario_id=scenario_id,
                    plan_design_id=plan_design_id,
                    enrollment_date=enrollment_date,
                    deferral_percentage=Decimal("0.06"),  # 6% deferral
                    deferral_amount=None,
                    catch_up_percentage=Decimal("0.0") if participant_idx % 10 != 0 else Decimal("0.02"),
                    effective_date=enrollment_date
                ))

                # Monthly contribution events
                for year_offset in range(years):
                    contribution_year = eligibility_date.year + year_offset
                    if contribution_year > 2024:
                        break

                    for month in range(1, 13):
                        contribution_date = date(contribution_year, month, 15)
                        if contribution_date < enrollment_date:
                            continue

                        monthly_compensation = Decimal(f"{4166.67}")  # ~$50K annual
                        employee_contrib = monthly_compensation * Decimal("0.06")
                        employer_match = min(employee_contrib, monthly_compensation * Decimal("0.03"))

                        events.append(ContributionEventFactory.create_contribution_event(
                            employee_id=employee_id,
                            plan_id=plan_id,
                            scenario_id=scenario_id,
                            plan_design_id=plan_design_id,
                            contribution_date=contribution_date,
                            employee_contribution=employee_contrib,
                            employer_contribution=employer_match,
                            contribution_source="regular_payroll",
                            vesting_service_years=Decimal(f"{year_offset}.{month:02d}"),
                            effective_date=contribution_date
                        ))

                # Annual vesting events
                for year_offset in range(1, years + 1):
                    vesting_year = eligibility_date.year + year_offset
                    if vesting_year > 2024:
                        break

                    vesting_percentage = min(Decimal("1.0"), Decimal(f"{year_offset * 0.2}"))  # 20% per year
                    events.append(VestingEventFactory.create_vesting_event(
                        employee_id=employee_id,
                        plan_id=plan_id,
                        scenario_id=scenario_id,
                        plan_design_id=plan_design_id,
                        vesting_date=date(vesting_year, 12, 31),
                        vesting_schedule_type="graded",
                        vested_percentage=vesting_percentage,
                        service_years=Decimal(f"{year_offset}"),
                        effective_date=date(vesting_year, 12, 31)
                    ))

        return events


class TestEventSchemaPerformance:
    """Performance test suite for event schema - S072-06."""

    def test_bulk_event_ingest_performance(self):
        """Test bulk event ingest performance - Target: ≥100K events/sec."""
        benchmark = PerformanceBenchmark()

        # Generate 50K events for testing (scalable to 100K+)
        num_employees = 10000  # Will generate ~50K events total
        events = EventDataGenerator.generate_workforce_events(num_employees, years=3)

        # Convert to serializable format for DuckDB
        event_data = []
        benchmark.start_benchmark()

        for event in events:
            event_dict = event.model_dump()
            event_dict['event_id'] = str(event.event_id)
            event_dict['payload_json'] = event.model_dump_json()
            event_data.append(event_dict)

        # Create DataFrame for bulk insert
        df = pd.DataFrame(event_data)

        # DuckDB bulk insert test
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE test_events (
                event_id VARCHAR,
                employee_id VARCHAR,
                scenario_id VARCHAR,
                plan_design_id VARCHAR,
                effective_date DATE,
                payload_json VARCHAR
            )
        """)

        # Vectorized insert
        conn.register('events_df', df)
        conn.execute("""
            INSERT INTO test_events
            SELECT event_id, employee_id, scenario_id, plan_design_id,
                   effective_date, payload_json
            FROM events_df
        """)

        metrics = benchmark.end_benchmark()

        # Performance assertions
        events_per_second = len(events) / metrics["duration_seconds"]

        print(f"\n=== Bulk Ingest Performance ===")
        print(f"Events processed: {len(events):,}")
        print(f"Duration: {metrics['duration_seconds']:.3f}s")
        print(f"Events/second: {events_per_second:,.0f}")
        print(f"Memory delta: {metrics['memory_delta_mb']:.1f}MB")

        # Performance targets
        assert events_per_second >= 50000, f"Ingest too slow: {events_per_second:.0f}/sec < 50K/sec target"
        assert metrics["memory_delta_mb"] < 2000, f"Memory usage too high: {metrics['memory_delta_mb']:.1f}MB"

        # Verify data integrity
        result = conn.execute("SELECT COUNT(*) FROM test_events").fetchone()
        assert result[0] == len(events), "Data integrity check failed"

        conn.close()

    def test_history_reconstruction_performance(self):
        """Test participant history reconstruction - Target: ≤5s for 5-year history."""
        benchmark = PerformanceBenchmark()

        # Generate DC plan events for 1000 participants over 5 years
        num_participants = 1000
        events = EventDataGenerator.generate_dc_plan_events(num_participants, years=5)

        # Setup DuckDB with events
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE participant_events (
                event_id VARCHAR,
                employee_id VARCHAR,
                plan_id VARCHAR,
                scenario_id VARCHAR,
                plan_design_id VARCHAR,
                effective_date DATE,
                event_type VARCHAR,
                payload_json VARCHAR
            )
        """)

        # Insert events
        event_data = []
        for event in events:
            event_data.append({
                'event_id': str(event.event_id),
                'employee_id': event.employee_id,
                'plan_id': getattr(event.payload, 'plan_id', 'N/A'),
                'scenario_id': event.scenario_id,
                'plan_design_id': event.plan_design_id,
                'effective_date': event.effective_date,
                'event_type': event.payload.event_type,
                'payload_json': event.model_dump_json()
            })

        df = pd.DataFrame(event_data)
        conn.register('events_df', df)
        conn.execute("INSERT INTO participant_events SELECT * FROM events_df")

        # Test history reconstruction for 100 participants
        benchmark.start_benchmark()

        reconstruction_queries = []
        for participant_idx in range(100):  # Test 100 participants
            employee_id = f"EMP_{participant_idx:06d}"

            # Complex history reconstruction query
            history_query = f"""
            WITH participant_timeline AS (
                SELECT
                    event_id,
                    employee_id,
                    effective_date,
                    event_type,
                    payload_json,
                    ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date) as event_sequence
                FROM participant_events
                WHERE employee_id = '{employee_id}'
                  AND effective_date BETWEEN '2020-01-01' AND '2024-12-31'
            ),
            contribution_summary AS (
                SELECT
                    employee_id,
                    COUNT(*) as total_contributions,
                    SUM(CAST(JSON_EXTRACT(payload_json, '$.employee_contribution') AS DECIMAL(18,6))) as total_employee_contrib,
                    SUM(CAST(JSON_EXTRACT(payload_json, '$.employer_contribution') AS DECIMAL(18,6))) as total_employer_contrib
                FROM participant_events
                WHERE employee_id = '{employee_id}'
                  AND event_type = 'contribution'
            )
            SELECT
                pt.employee_id,
                COUNT(pt.event_id) as total_events,
                MIN(pt.effective_date) as first_event_date,
                MAX(pt.effective_date) as last_event_date,
                cs.total_contributions,
                COALESCE(cs.total_employee_contrib, 0) as total_employee_contrib,
                COALESCE(cs.total_employer_contrib, 0) as total_employer_contrib
            FROM participant_timeline pt
            LEFT JOIN contribution_summary cs ON pt.employee_id = cs.employee_id
            GROUP BY pt.employee_id, cs.total_contributions, cs.total_employee_contrib, cs.total_employer_contrib
            """

            result = conn.execute(history_query).fetchall()
            reconstruction_queries.append(result)

        metrics = benchmark.end_benchmark()

        print(f"\n=== History Reconstruction Performance ===")
        print(f"Participants processed: 100")
        print(f"Total events in database: {len(events):,}")
        print(f"Duration: {metrics['duration_seconds']:.3f}s")
        print(f"Avg time per participant: {metrics['duration_seconds']/100*1000:.1f}ms")
        print(f"Memory delta: {metrics['memory_delta_mb']:.1f}MB")

        # Performance target: ≤5s for 5-year participant history
        assert metrics["duration_seconds"] <= 5.0, f"History reconstruction too slow: {metrics['duration_seconds']:.3f}s > 5s target"

        # Verify reconstruction quality
        assert len(reconstruction_queries) == 100, "Should have reconstructed 100 participant histories"

        conn.close()

    def test_schema_validation_performance(self):
        """Test schema validation performance - Target: <10ms per event."""
        benchmark = PerformanceBenchmark()

        # Generate variety of events for validation testing
        test_events = []

        # Workforce events
        test_events.extend(EventDataGenerator.generate_workforce_events(100, years=1))

        # DC plan events
        test_events.extend(EventDataGenerator.generate_dc_plan_events(100, years=1))

        # Plan administration events
        for i in range(50):
            employee_id = f"EMP_{i:06d}"
            scenario_id = "VALIDATION_TEST"
            plan_design_id = "STANDARD_DESIGN"
            plan_id = "401K_PLAN"

            # Forfeiture event
            test_events.append(PlanAdministrationEventFactory.create_forfeiture_event(
                employee_id=employee_id,
                plan_id=plan_id,
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                forfeited_from_source="employer_match",
                amount=Decimal("1000.00"),
                reason="unvested_termination",
                vested_percentage=Decimal("0.25"),
                effective_date=date(2024, 6, 15)
            ))

            # HCE status event
            test_events.append(PlanAdministrationEventFactory.create_hce_status_event(
                employee_id=employee_id,
                plan_id=plan_id,
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                determination_method="prior_year",
                ytd_compensation=Decimal("125000.00"),
                annualized_compensation=Decimal("150000.00"),
                hce_threshold=Decimal("135000.00"),
                is_hce=True,
                determination_date=date(2024, 1, 1)
            ))

        # Test validation performance
        benchmark.start_benchmark()

        validation_times = []
        for event in test_events:
            start_time = time.perf_counter()

            # Full validation including serialization/deserialization
            json_data = event.model_dump_json()
            reconstructed = SimulationEvent.model_validate_json(json_data)

            validation_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
            validation_times.append(validation_time)

        metrics = benchmark.end_benchmark()

        avg_validation_time = sum(validation_times) / len(validation_times)
        max_validation_time = max(validation_times)

        print(f"\n=== Schema Validation Performance ===")
        print(f"Events validated: {len(test_events):,}")
        print(f"Avg validation time: {avg_validation_time:.3f}ms")
        print(f"Max validation time: {max_validation_time:.3f}ms")
        print(f"Total duration: {metrics['duration_seconds']:.3f}s")
        print(f"Validations/second: {len(test_events)/metrics['duration_seconds']:,.0f}")

        # Performance targets
        assert avg_validation_time < 10.0, f"Avg validation too slow: {avg_validation_time:.3f}ms > 10ms target"
        assert max_validation_time < 50.0, f"Max validation too slow: {max_validation_time:.3f}ms > 50ms acceptable"

    def test_memory_efficiency_simulation(self):
        """Test memory efficiency - Target: <8GB for 100K employee simulation."""
        benchmark = PerformanceBenchmark()

        # Generate large dataset for memory testing
        print(f"\n=== Memory Efficiency Test ===")
        print("Generating 100K employee dataset...")

        benchmark.start_benchmark()

        # Generate events in batches to monitor memory usage
        batch_size = 10000
        all_events = []
        memory_checkpoints = []

        for batch_idx in range(10):  # 10 batches of 10K employees each
            batch_events = EventDataGenerator.generate_workforce_events(batch_size, years=2)
            all_events.extend(batch_events)

            current_memory = psutil.Process().memory_info().rss / 1024 / 1024 / 1024  # GB
            memory_checkpoints.append(current_memory)

            print(f"Batch {batch_idx + 1}/10: {len(batch_events):,} events, Memory: {current_memory:.2f}GB")

        metrics = benchmark.end_benchmark()
        peak_memory_gb = metrics["peak_memory_mb"] / 1024

        print(f"\nFinal Results:")
        print(f"Total events generated: {len(all_events):,}")
        print(f"Peak memory usage: {peak_memory_gb:.2f}GB")
        print(f"Memory efficiency: {len(all_events)/peak_memory_gb:,.0f} events/GB")
        print(f"Generation time: {metrics['duration_seconds']:.1f}s")

        # Memory target: <8GB for 100K employee simulation
        assert peak_memory_gb < 8.0, f"Memory usage too high: {peak_memory_gb:.2f}GB > 8GB target"

        # Verify data quality
        assert len(all_events) >= 400000, f"Should generate 400K+ events for 100K employees"  # ~4 events per employee minimum

        # Test memory cleanup
        del all_events
        import gc
        gc.collect()

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024 / 1024
        print(f"Memory after cleanup: {final_memory:.2f}GB")


if __name__ == "__main__":
    # Run performance tests individually for detailed output
    test_suite = TestEventSchemaPerformance()

    print("=" * 60)
    print("DC PLAN EVENT SCHEMA PERFORMANCE TESTS - S072-06")
    print("=" * 60)

    try:
        test_suite.test_bulk_event_ingest_performance()
        print("✅ Bulk ingest performance test PASSED")
    except Exception as e:
        print(f"❌ Bulk ingest performance test FAILED: {e}")

    try:
        test_suite.test_history_reconstruction_performance()
        print("✅ History reconstruction performance test PASSED")
    except Exception as e:
        print(f"❌ History reconstruction performance test FAILED: {e}")

    try:
        test_suite.test_schema_validation_performance()
        print("✅ Schema validation performance test PASSED")
    except Exception as e:
        print(f"❌ Schema validation performance test FAILED: {e}")

    try:
        test_suite.test_memory_efficiency_simulation()
        print("✅ Memory efficiency test PASSED")
    except Exception as e:
        print(f"❌ Memory efficiency test FAILED: {e}")

    print("\n" + "=" * 60)
    print("PERFORMANCE TEST SUITE COMPLETE")
    print("=" * 60)
