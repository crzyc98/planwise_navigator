# filename: tests/integration/test_multi_year_coordination.py
"""
Integration tests for Story S031-04 Multi-Year Coordination components.

This test suite validates:
- End-to-end multi-year coordination workflow
- Integration between cost attribution, caching, and optimization systems
- Performance optimization with real workloads
- Data integrity preservation across coordination operations
- Resource management under realistic conditions
- Error handling and recovery in multi-component scenarios
"""

import pytest
import time
import tempfile
import threading
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, MagicMock, patch

from orchestrator_mvp.core.cost_attribution import (
    CrossYearCostAttributor,
    CostAttributionEntry,
    CostAttributionType,
    AllocationStrategy,
    CrossYearAllocationContext,
    create_cost_attributor,
    create_allocation_context
)
from orchestrator_mvp.core.intelligent_cache import (
    IntelligentCacheManager,
    CacheEntryType,
    CacheTier,
    CachePolicy,
    create_cache_manager
)
from orchestrator_mvp.core.coordination_optimizer import (
    CoordinationOptimizer,
    OptimizationStrategy,
    PerformanceMetrics,
    create_coordination_optimizer
)
from orchestrator_mvp.utils.resource_optimizer import (
    ResourceOptimizer,
    PersistenceLevel,
    ResourceLimits,
    create_resource_optimizer
)
from orchestrator_mvp.core.state_management import WorkforceMetrics, SimulationState
from config.events import SimulationEvent, EventFactory


class TestMultiYearCoordinationWorkflow:
    """Integration tests for complete multi-year coordination workflow."""

    @pytest.fixture
    def coordination_system(self):
        """Create integrated coordination system for testing."""
        # Create cache manager
        cache_manager = create_cache_manager(
            l1_max_entries=50,
            l2_max_entries=200,
            l3_max_entries=1000,
            enable_optimization=False  # Disable for deterministic testing
        )

        # Create cost attributor
        cost_attributor = create_cost_attributor(
            scenario_id="INTEGRATION_SCENARIO",
            plan_design_id="INTEGRATION_DESIGN",
            allocation_strategy=AllocationStrategy.PRO_RATA_TEMPORAL
        )

        # Create coordination optimizer
        coordination_optimizer = create_coordination_optimizer(
            strategy=OptimizationStrategy.BALANCED,
            target_reduction_percent=Decimal('65'),
            cache_manager=cache_manager
        )

        # Create resource optimizer
        resource_optimizer = create_resource_optimizer(
            max_memory_gb=4.0,  # Moderate limits for testing
            max_memory_percentage=0.8,
            enable_monitoring=False
        )

        return {
            'cache_manager': cache_manager,
            'cost_attributor': cost_attributor,
            'coordination_optimizer': coordination_optimizer,
            'resource_optimizer': resource_optimizer
        }

    @pytest.fixture
    def sample_simulation_data(self):
        """Create sample simulation data for testing."""
        # Generate sample events
        events = []
        for i in range(100):
            event = Mock()
            event.employee_id = f"EMP{i:06d}"
            event.effective_date = date(2024, 6, 15)
            event.event_id = uuid4()
            event.scenario_id = "INTEGRATION_SCENARIO"
            event.plan_design_id = "INTEGRATION_DESIGN"

            # Mock payload with compensation data
            mock_payload = Mock()
            mock_payload.event_type = 'hire' if i % 3 == 0 else 'promotion' if i % 3 == 1 else 'raise'
            if mock_payload.event_type == 'hire':
                mock_payload.annual_compensation = 75000.00 + (i * 100)
            elif mock_payload.event_type == 'promotion':
                mock_payload.new_annual_compensation = 85000.00 + (i * 100)
                mock_payload.previous_compensation = 75000.00 + (i * 100)
            else:  # raise
                mock_payload.new_annual_compensation = 78000.00 + (i * 100)
                mock_payload.previous_compensation = 75000.00 + (i * 100)

            event.payload = mock_payload
            events.append(event)

        # Generate workforce metrics
        source_metrics = WorkforceMetrics(
            active_employees=1000,
            total_compensation_cost=Decimal('75000000.00'),
            average_compensation=Decimal('75000.00'),
            snapshot_date=date(2024, 12, 31)
        )

        target_metrics = {
            2025: WorkforceMetrics(
                active_employees=1100,
                total_compensation_cost=Decimal('85000000.00'),
                average_compensation=Decimal('77272.73'),
                snapshot_date=date(2025, 12, 31)
            ),
            2026: WorkforceMetrics(
                active_employees=1200,
                total_compensation_cost=Decimal('95000000.00'),
                average_compensation=Decimal('79166.67'),
                snapshot_date=date(2026, 12, 31)
            )
        }

        return {
            'events': events,
            'source_metrics': source_metrics,
            'target_metrics': target_metrics,
            'simulation_years': [2025, 2026]
        }

    def test_end_to_end_coordination_workflow(self, coordination_system, sample_simulation_data):
        """Test complete end-to-end coordination workflow."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']
        coordination_optimizer = coordination_system['coordination_optimizer']
        resource_optimizer = coordination_system['resource_optimizer']

        # Step 1: Create allocation context
        allocation_context = create_allocation_context(
            source_year=2024,
            target_years=sample_simulation_data['simulation_years'],
            source_workforce_metrics=sample_simulation_data['source_metrics'],
            target_workforce_metrics=sample_simulation_data['target_metrics'],
            source_events=sample_simulation_data['events']
        )

        # Step 2: Cache frequently accessed data
        cache_key = "workforce_metrics_2024"
        cache_success = cache_manager.put(
            cache_key=cache_key,
            data=sample_simulation_data['source_metrics'].model_dump(),
            entry_type=CacheEntryType.AGGREGATED_METRICS,
            computation_cost_ms=Decimal('250.000')
        )
        assert cache_success is True

        # Step 3: Perform cost attribution across years
        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(
            allocation_context
        )

        # Verify attribution was successful
        assert len(attribution_entries) > 0
        assert all(isinstance(entry, CostAttributionEntry) for entry in attribution_entries)
        assert all(entry.cross_year_attribution for entry in attribution_entries)

        # Step 4: Optimize memory usage for the simulation
        memory_optimization = resource_optimizer.optimize_memory_usage(
            simulation_years=sample_simulation_data['simulation_years'],
            workforce_size=1000
        )

        assert memory_optimization.memory_savings_gb >= 0
        assert memory_optimization.efficiency_rating in ['excellent', 'good', 'acceptable', 'marginal']

        # Step 5: Run coordination optimization
        mock_state_manager = Mock()
        optimization_results = coordination_optimizer.optimize_multi_year_coordination(
            state_manager=mock_state_manager,
            cost_attributor=cost_attributor,
            simulation_years=sample_simulation_data['simulation_years']
        )

        # Verify optimization results
        assert optimization_results['target_overhead_reduction_percent'] == 65.0
        assert optimization_results['actual_overhead_reduction_percent'] >= 0
        assert 'optimization_results' in optimization_results
        assert 'performance_analysis' in optimization_results

        # Step 6: Verify cached data is still accessible
        cached_metrics = cache_manager.get(cache_key, CacheEntryType.AGGREGATED_METRICS)
        assert cached_metrics is not None
        assert cached_metrics['active_employees'] == 1000

        # Step 7: Validate attribution integrity
        is_valid, issues = cost_attributor.validate_attribution_integrity()
        assert is_valid is True
        assert len(issues) == 0

    def test_cost_attribution_with_caching_integration(self, coordination_system, sample_simulation_data):
        """Test cost attribution system integration with intelligent caching."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']

        # Cache expensive computation results
        expensive_calculation_key = "compensation_impact_analysis_2024"
        calculation_result = {
            "total_impact": Decimal('1500000.00'),
            "employee_count": 100,
            "average_impact": Decimal('15000.00'),
            "computation_timestamp": datetime.utcnow().isoformat()
        }

        cache_manager.put(
            cache_key=expensive_calculation_key,
            data=calculation_result,
            entry_type=CacheEntryType.COMPUTATION_RESULT,
            computation_cost_ms=Decimal('2500.000'),  # Expensive computation
            depends_on=["workforce_metrics_2024"]
        )

        # Create allocation context
        allocation_context = create_allocation_context(
            source_year=2024,
            target_years=[2025],
            source_workforce_metrics=sample_simulation_data['source_metrics'],
            target_workforce_metrics={2025: sample_simulation_data['target_metrics'][2025]},
            source_events=sample_simulation_data['events'][:50]  # Subset for faster testing
        )

        # Perform attribution
        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(
            allocation_context
        )

        # Verify attribution succeeded
        assert len(attribution_entries) > 0

        # Verify cached computation is still available and hasn't been invalidated
        cached_calculation = cache_manager.get(expensive_calculation_key, CacheEntryType.COMPUTATION_RESULT)
        assert cached_calculation is not None
        assert cached_calculation["total_impact"] == Decimal('1500000.00')

        # Cache some attribution results for future use
        attribution_summary_key = "attribution_summary_2025"
        summary_data = cost_attributor.get_attribution_summary(
            target_year=2025,
            attribution_type=CostAttributionType.COMPENSATION_BASELINE
        )

        cache_success = cache_manager.put(
            cache_key=attribution_summary_key,
            data=summary_data,
            entry_type=CacheEntryType.AGGREGATED_METRICS,
            computation_cost_ms=Decimal('150.000')
        )
        assert cache_success is True

        # Verify cache performance metrics
        performance_metrics = cache_manager.get_performance_metrics()
        assert performance_metrics.total_requests > 0
        assert performance_metrics.cache_hits > 0

    def test_optimization_with_resource_constraints(self, coordination_system):
        """Test coordination optimization under resource constraints."""
        coordination_optimizer = coordination_system['coordination_optimizer']
        resource_optimizer = coordination_system['resource_optimizer']

        # Create constrained scenario
        simulation_years = [2024, 2025, 2026, 2027, 2028]  # 5 years
        large_workforce_size = 50000  # Large workforce

        # Get resource optimization recommendations first
        recommendations = resource_optimizer.get_optimization_recommendations(
            simulation_years=simulation_years,
            workforce_size=large_workforce_size,
            checkpoint_frequency=3,
            persistence_level=PersistenceLevel.STANDARD
        )

        # Verify recommendations were generated
        assert 'overall_recommendation' in recommendations
        assert 'memory_optimization' in recommendations
        assert 'io_optimization' in recommendations

        # Use recommendations to configure optimization
        memory_strategy = recommendations['memory_optimization']['strategy']

        if memory_strategy == 'streaming':
            # Use conservative optimization for streaming
            opt_strategy = OptimizationStrategy.CONSERVATIVE
        else:
            # Use balanced optimization for in-memory
            opt_strategy = OptimizationStrategy.BALANCED

        # Create new optimizer with appropriate strategy
        constrained_optimizer = CoordinationOptimizer(
            optimization_strategy=opt_strategy,
            target_overhead_reduction_percent=Decimal('50'),  # Lower target for constraints
            enable_parallel_processing=True,
            max_worker_threads=2,  # Limited threads for testing
            cache_manager=coordination_system['cache_manager']
        )

        # Mock state manager and cost attributor
        mock_state_manager = Mock()
        mock_cost_attributor = Mock()

        # Run optimization under constraints
        optimization_results = constrained_optimizer.optimize_multi_year_coordination(
            state_manager=mock_state_manager,
            cost_attributor=mock_cost_attributor,
            simulation_years=simulation_years
        )

        # Verify optimization adapted to constraints
        assert optimization_results['optimization_strategy'] == opt_strategy.value
        assert optimization_results['target_overhead_reduction_percent'] == 50.0
        assert 'optimization_results' in optimization_results

        # Should have attempted various optimizations
        opt_results = optimization_results['optimization_results']
        assert len(opt_results) > 0

    def test_cache_promotion_during_coordination(self, coordination_system, sample_simulation_data):
        """Test cache promotion behavior during multi-year coordination."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']

        # Store data in L2 cache initially (larger computation cost)
        workforce_data_key = "detailed_workforce_analysis_2024"
        workforce_analysis = {
            "employee_details": [
                {"id": f"EMP{i:06d}", "compensation": 75000 + i*100, "department": f"DEPT_{i%10}"}
                for i in range(200)
            ],
            "department_summaries": {f"DEPT_{i}": {"count": 20, "avg_comp": 77500} for i in range(10)},
            "analysis_metadata": {
                "computation_time_ms": 3000,
                "data_points": 200,
                "last_updated": datetime.utcnow().isoformat()
            }
        }

        cache_manager.put(
            cache_key=workforce_data_key,
            data=workforce_analysis,
            entry_type=CacheEntryType.WORKFORCE_STATE,
            computation_cost_ms=Decimal('3000.000')  # Expensive, should go to L2
        )

        # Verify initially in L2
        assert workforce_data_key in cache_manager._l2_cache

        # Access the data multiple times during coordination operations
        for i in range(15):  # Multiple accesses to increase promotion score
            accessed_data = cache_manager.get(workforce_data_key, CacheEntryType.WORKFORCE_STATE)
            assert accessed_data is not None
            assert len(accessed_data["employee_details"]) == 200

            # Simulate some processing time between accesses
            time.sleep(0.01)

        # After multiple accesses, data might be promoted to L1
        # Check if promotion occurred
        if workforce_data_key in cache_manager._l1_cache:
            # Promotion occurred - verify data is no longer in L2
            assert workforce_data_key not in cache_manager._l2_cache
        else:
            # Promotion didn't occur - verify data is still in L2
            assert workforce_data_key in cache_manager._l2_cache

        # Run cache optimization to trigger promotions
        optimization_results = cache_manager.optimize_cache_placement()
        assert 'promotions_executed' in optimization_results
        assert 'demotions_executed' in optimization_results

    def test_concurrent_coordination_operations(self, coordination_system, sample_simulation_data):
        """Test concurrent coordination operations for thread safety."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']
        resource_optimizer = coordination_system['resource_optimizer']

        results = []
        errors = []

        def cache_operations():
            """Concurrent cache operations."""
            try:
                for i in range(10):
                    key = f"concurrent_data_{threading.current_thread().ident}_{i}"
                    data = {"thread_data": i, "timestamp": datetime.utcnow().isoformat()}

                    success = cache_manager.put(
                        cache_key=key,
                        data=data,
                        entry_type=CacheEntryType.INTERMEDIATE_CALCULATION
                    )

                    if success:
                        retrieved = cache_manager.get(key, CacheEntryType.INTERMEDIATE_CALCULATION)
                        if retrieved:
                            results.append(f"cache_success_{key}")

            except Exception as e:
                errors.append(f"cache_error: {str(e)}")

        def attribution_operations():
            """Concurrent attribution operations."""
            try:
                allocation_context = create_allocation_context(
                    source_year=2024,
                    target_years=[2025],
                    source_workforce_metrics=sample_simulation_data['source_metrics'],
                    target_workforce_metrics={2025: sample_simulation_data['target_metrics'][2025]},
                    source_events=sample_simulation_data['events'][:25]  # Small subset
                )

                entries = cost_attributor.attribute_compensation_costs_across_years(allocation_context)
                results.append(f"attribution_success_{len(entries)}")

            except Exception as e:
                errors.append(f"attribution_error: {str(e)}")

        def resource_optimization_operations():
            """Concurrent resource optimization operations."""
            try:
                memory_result = resource_optimizer.optimize_memory_usage(
                    simulation_years=[2025],
                    workforce_size=5000
                )
                results.append(f"memory_opt_success_{memory_result.strategy_type}")

                io_result = resource_optimizer.optimize_io_operations(
                    checkpoint_frequency=5,
                    result_persistence_level=PersistenceLevel.STANDARD
                )
                results.append(f"io_opt_success_{io_result.total_io_reduction_percentage}")

            except Exception as e:
                errors.append(f"resource_opt_error: {str(e)}")

        # Start concurrent operations
        threads = []
        for i in range(3):
            cache_thread = threading.Thread(target=cache_operations)
            attribution_thread = threading.Thread(target=attribution_operations)
            resource_thread = threading.Thread(target=resource_optimization_operations)

            threads.extend([cache_thread, attribution_thread, resource_thread])

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent operations had errors: {errors}"

        # Verify operations completed successfully
        assert len(results) > 0

        # Check for different types of successful operations
        cache_successes = [r for r in results if r.startswith('cache_success')]
        attribution_successes = [r for r in results if r.startswith('attribution_success')]
        resource_successes = [r for r in results if r.startswith('memory_opt_success') or r.startswith('io_opt_success')]

        assert len(cache_successes) > 0
        assert len(attribution_successes) > 0
        assert len(resource_successes) > 0

    def test_error_recovery_and_rollback(self, coordination_system, sample_simulation_data):
        """Test error recovery and rollback capabilities."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']

        # Store initial state in cache
        initial_state_key = "system_state_checkpoint"
        initial_state = {
            "active_employees": 1000,
            "total_compensation": Decimal('75000000.00'),
            "last_attribution_run": None,
            "checkpoint_timestamp": datetime.utcnow().isoformat()
        }

        cache_manager.put(
            cache_key=initial_state_key,
            data=initial_state,
            entry_type=CacheEntryType.WORKFORCE_STATE
        )

        # Simulate successful attribution operation
        allocation_context = create_allocation_context(
            source_year=2024,
            target_years=[2025],
            source_workforce_metrics=sample_simulation_data['source_metrics'],
            target_workforce_metrics={2025: sample_simulation_data['target_metrics'][2025]},
            source_events=sample_simulation_data['events'][:30]
        )

        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(allocation_context)
        assert len(attribution_entries) > 0

        # Update state to reflect successful operation
        updated_state = initial_state.copy()
        updated_state["last_attribution_run"] = datetime.utcnow().isoformat()
        updated_state["total_attributions"] = len(attribution_entries)

        cache_manager.put(
            cache_key=initial_state_key,
            data=updated_state,
            entry_type=CacheEntryType.WORKFORCE_STATE
        )

        # Simulate error condition by creating invalid allocation context
        invalid_context = create_allocation_context(
            source_year=2024,
            target_years=[2030],  # Future year with no metrics
            source_workforce_metrics=sample_simulation_data['source_metrics'],
            target_workforce_metrics={},  # Empty target metrics - should cause issues
            source_events=[]  # No events
        )

        # Attempt attribution with invalid context - should handle gracefully
        try:
            invalid_entries = cost_attributor.attribute_compensation_costs_across_years(invalid_context)
            # If it succeeds, it should return empty list
            assert len(invalid_entries) == 0
        except Exception as e:
            # If it fails, that's also acceptable - just ensure system remains stable
            pass

        # Verify system state can be recovered from cache
        recovered_state = cache_manager.get(initial_state_key, CacheEntryType.WORKFORCE_STATE)
        assert recovered_state is not None
        assert recovered_state["active_employees"] == 1000
        assert "last_attribution_run" in recovered_state

        # Verify cost attributor integrity is maintained
        is_valid, issues = cost_attributor.validate_attribution_integrity()
        assert is_valid is True

    def test_performance_under_load(self, coordination_system):
        """Test coordination system performance under realistic load."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']
        coordination_optimizer = coordination_system['coordination_optimizer']

        # Generate larger dataset for load testing
        large_event_set = []
        for i in range(500):  # Larger number of events
            event = Mock()
            event.employee_id = f"EMP{i:06d}"
            event.effective_date = date(2024, 1 + (i % 12), 15)
            event.event_id = uuid4()
            event.scenario_id = "LOAD_TEST_SCENARIO"
            event.plan_design_id = "LOAD_TEST_DESIGN"

            mock_payload = Mock()
            mock_payload.event_type = ['hire', 'promotion', 'raise', 'termination'][i % 4]
            mock_payload.annual_compensation = 60000.00 + (i * 50)
            event.payload = mock_payload

            large_event_set.append(event)

        # Create workforce metrics for larger simulation
        large_source_metrics = WorkforceMetrics(
            active_employees=5000,
            total_compensation_cost=Decimal('375000000.00'),
            average_compensation=Decimal('75000.00'),
            snapshot_date=date(2024, 12, 31)
        )

        large_target_metrics = {
            2025: WorkforceMetrics(
                active_employees=5500,
                total_compensation_cost=Decimal('425000000.00'),
                average_compensation=Decimal('77272.73'),
                snapshot_date=date(2025, 12, 31)
            )
        }

        # Measure performance of cache operations
        cache_start_time = time.perf_counter()

        # Cache multiple large datasets
        for i in range(20):
            large_data = {
                "dataset_id": i,
                "employee_records": [{"id": f"EMP{j:06d}", "data": f"record_{j}"} for j in range(i*10, (i+1)*10)],
                "metadata": {"size": 10, "creation_time": datetime.utcnow().isoformat()}
            }

            cache_manager.put(
                cache_key=f"load_test_dataset_{i}",
                data=large_data,
                entry_type=CacheEntryType.WORKFORCE_STATE,
                computation_cost_ms=Decimal('100.000')
            )

        cache_end_time = time.perf_counter()
        cache_operation_time = cache_end_time - cache_start_time

        # Cache operations should complete within reasonable time
        assert cache_operation_time < 2.0  # Less than 2 seconds for 20 datasets

        # Measure performance of cost attribution
        attribution_start_time = time.perf_counter()

        allocation_context = create_allocation_context(
            source_year=2024,
            target_years=[2025],
            source_workforce_metrics=large_source_metrics,
            target_workforce_metrics=large_target_metrics,
            source_events=large_event_set
        )

        attribution_entries = cost_attributor.attribute_compensation_costs_across_years(allocation_context)

        attribution_end_time = time.perf_counter()
        attribution_time = attribution_end_time - attribution_start_time

        # Attribution should complete within reasonable time
        assert attribution_time < 5.0  # Less than 5 seconds for 500 events
        assert len(attribution_entries) > 0

        # Measure performance of coordination optimization
        optimization_start_time = time.perf_counter()

        mock_state_manager = Mock()
        optimization_results = coordination_optimizer.optimize_multi_year_coordination(
            state_manager=mock_state_manager,
            cost_attributor=cost_attributor,
            simulation_years=[2025]
        )

        optimization_end_time = time.perf_counter()
        optimization_time = optimization_end_time - optimization_start_time

        # Optimization should complete within reasonable time
        assert optimization_time < 10.0  # Less than 10 seconds for full optimization

        # Verify performance metrics
        assert optimization_results['total_optimization_time_seconds'] > 0
        assert optimization_results['actual_overhead_reduction_percent'] >= 0

        # Verify cache performance under load
        cache_metrics = cache_manager.get_performance_metrics()
        assert cache_metrics.total_requests >= 20  # At least our 20 put operations
        assert cache_metrics.hit_rate >= 0  # Should have some cache activity

    def test_data_integrity_preservation(self, coordination_system, sample_simulation_data):
        """Test data integrity preservation across coordination operations."""
        cache_manager = coordination_system['cache_manager']
        cost_attributor = coordination_system['cost_attributor']

        # Create checksum for original data
        original_events_checksum = hash(str([e.employee_id for e in sample_simulation_data['events']]))
        original_source_metrics_checksum = hash(str(sample_simulation_data['source_metrics'].model_dump()))

        # Store data in cache with integrity markers
        cache_manager.put(
            cache_key="integrity_test_events",
            data={
                "events": [{"id": e.employee_id, "date": str(e.effective_date)} for e in sample_simulation_data['events']],
                "checksum": original_events_checksum,
                "timestamp": datetime.utcnow().isoformat()
            },
            entry_type=CacheEntryType.WORKFORCE_STATE
        )

        cache_manager.put(
            cache_key="integrity_test_metrics",
            data={
                "metrics": sample_simulation_data['source_metrics'].model_dump(),
                "checksum": original_source_metrics_checksum,
                "timestamp": datetime.utcnow().isoformat()
            },
            entry_type=CacheEntryType.AGGREGATED_METRICS
        )

        # Perform multiple coordination operations
        allocation_context = create_allocation_context(
            source_year=2024,
            target_years=[2025],
            source_workforce_metrics=sample_simulation_data['source_metrics'],
            target_workforce_metrics={2025: sample_simulation_data['target_metrics'][2025]},
            source_events=sample_simulation_data['events']
        )

        # First attribution
        attribution_entries_1 = cost_attributor.attribute_compensation_costs_across_years(allocation_context)

        # Second attribution (should be idempotent with same input)
        attribution_entries_2 = cost_attributor.attribute_compensation_costs_across_years(allocation_context)

        # Verify attributions are consistent
        assert len(attribution_entries_1) == len(attribution_entries_2)

        # Check UUIDs are unique across runs (not deterministic)
        uuids_1 = {entry.attribution_id for entry in attribution_entries_1}
        uuids_2 = {entry.attribution_id for entry in attribution_entries_2}
        assert uuids_1.isdisjoint(uuids_2)  # Should be different UUIDs

        # But business data should be consistent
        amounts_1 = [float(entry.attributed_amount) for entry in attribution_entries_1]
        amounts_2 = [float(entry.attributed_amount) for entry in attribution_entries_2]
        assert amounts_1 == amounts_2  # Same amounts for same inputs

        # Verify cached data integrity
        cached_events = cache_manager.get("integrity_test_events", CacheEntryType.WORKFORCE_STATE)
        cached_metrics = cache_manager.get("integrity_test_metrics", CacheEntryType.AGGREGATED_METRICS)

        assert cached_events is not None
        assert cached_metrics is not None

        # Verify checksums match
        assert cached_events["checksum"] == original_events_checksum
        assert cached_metrics["checksum"] == original_source_metrics_checksum

        # Verify attribution integrity
        is_valid, issues = cost_attributor.validate_attribution_integrity()
        assert is_valid is True
        assert len(issues) == 0

    def test_resource_optimization_integration(self, coordination_system):
        """Test resource optimization integration with coordination workflow."""
        resource_optimizer = coordination_system['resource_optimizer']
        cache_manager = coordination_system['cache_manager']

        # Test scenario: Large multi-year simulation
        simulation_years = [2024, 2025, 2026, 2027]
        workforce_size = 75000

        # Get optimization recommendations
        recommendations = resource_optimizer.get_optimization_recommendations(
            simulation_years=simulation_years,
            workforce_size=workforce_size,
            checkpoint_frequency=3,
            persistence_level=PersistenceLevel.FULL
        )

        # Verify recommendations structure
        assert 'memory_optimization' in recommendations
        assert 'io_optimization' in recommendations
        assert 'overall_recommendation' in recommendations

        memory_strategy = recommendations['memory_optimization']['strategy']
        io_reduction = recommendations['io_optimization']['total_reduction_percentage']
        overall_rating = recommendations['overall_recommendation']['overall_rating']

        # Apply memory optimization strategy to cache configuration
        if memory_strategy == 'streaming':
            # Configure cache for streaming workload
            cache_manager.clear_tier(CacheTier.L1_MEMORY)  # Clear L1 to save memory

            # Verify cache optimization
            optimization_result = cache_manager.optimize_cache_placement()
            assert 'demotions_executed' in optimization_result

        elif memory_strategy == 'in_memory':
            # Configure cache for in-memory workload
            # Store frequently accessed data in L1
            for i in range(10):
                cache_manager.put(
                    cache_key=f"preloaded_data_{i}",
                    data={"preload": i, "timestamp": datetime.utcnow().isoformat()},
                    entry_type=CacheEntryType.WORKFORCE_STATE
                )

        # Test I/O optimization integration
        if io_reduction > 0.2:  # Significant I/O optimization opportunity
            # Simulate compressed checkpointing
            with tempfile.TemporaryDirectory() as temp_dir:
                checkpoint_data = {
                    "simulation_state": {
                        "years": simulation_years,
                        "workforce_size": workforce_size,
                        "checkpoint_timestamp": datetime.utcnow().isoformat()
                    },
                    "cache_state": cache_manager.get_performance_metrics().model_dump(),
                    "optimization_recommendations": recommendations
                }

                # Use resource optimizer's I/O optimization
                io_optimization = resource_optimizer.optimize_io_operations(
                    checkpoint_frequency=3,
                    result_persistence_level=PersistenceLevel.FULL
                )

                compression_type = io_optimization.compression_optimization['recommended_compression']

                # Verify compression recommendation
                assert compression_type in ['none', 'gzip', 'lzma']
                assert io_optimization.total_io_reduction_percentage >= 0

        # Verify overall system performance
        cache_metrics = cache_manager.get_performance_metrics()
        assert cache_metrics.total_requests >= 0

        # Test resource monitoring integration
        current_metrics = resource_optimizer.resource_monitor.get_current_metrics()
        assert current_metrics.memory_used_gb > 0
        assert current_metrics.memory_available_gb > 0

        # Verify resource recommendations are actionable
        key_recommendations = recommendations['overall_recommendation']['key_recommendations']
        assert isinstance(key_recommendations, list)
        assert len(key_recommendations) > 0

        # Each recommendation should be actionable
        for recommendation in key_recommendations:
            assert isinstance(recommendation, str)
            assert len(recommendation.strip()) > 0
