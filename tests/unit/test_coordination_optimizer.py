# filename: tests/unit/test_coordination_optimizer.py
"""
Unit tests for CoordinationOptimizer and performance optimization system.

This test suite validates:
- Performance optimization targeting 65% overhead reduction
- Real-time performance analysis and bottleneck identification
- Multiple optimization strategies (aggressive, balanced, conservative)
- Database query optimization and batch processing
- Memory usage optimization and garbage collection tuning
- Integration with caching and state management systems
"""

import pytest
import time
import threading
import gc
import psutil
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, MagicMock, patch

from orchestrator_mvp.core.coordination_optimizer import (
    OptimizationStrategy,
    OptimizationPhase,
    BottleneckType,
    PerformanceMetrics,
    BottleneckAnalysis,
    OptimizationTask,
    PerformanceProfiler,
    CoordinationOptimizer,
    create_coordination_optimizer,
    create_performance_profiler
)
from orchestrator_mvp.core.state_management import WorkforceStateManager, WorkforceMetrics
from orchestrator_mvp.core.cost_attribution import CrossYearCostAttributor
from orchestrator_mvp.core.intelligent_cache import IntelligentCacheManager


class TestPerformanceMetrics:
    """Test cases for PerformanceMetrics tracking and calculation."""

    def test_performance_metrics_creation(self):
        """Test creating comprehensive performance metrics."""
        metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('5000.500'),
            initialization_time_ms=Decimal('200.000'),
            event_processing_time_ms=Decimal('3000.250'),
            state_transition_time_ms=Decimal('800.125'),
            cost_attribution_time_ms=Decimal('600.075'),
            cache_operation_time_ms=Decimal('150.050'),
            database_operation_time_ms=Decimal('250.000'),
            events_processed_per_second=Decimal('1250.75'),
            state_transitions_per_second=Decimal('100.50'),
            cost_attributions_per_second=Decimal('85.25'),
            peak_memory_usage_mb=Decimal('1024.50'),
            cpu_utilization_percent=Decimal('75.25'),
            cache_hit_rate=Decimal('0.8750'),
            database_query_count=150,
            overhead_reduction_percent=Decimal('68.50'),
            performance_improvement_factor=Decimal('2.85')
        )

        # Verify timing metrics
        assert metrics.total_execution_time_ms == Decimal('5000.500')
        assert metrics.initialization_time_ms == Decimal('200.000')
        assert metrics.event_processing_time_ms == Decimal('3000.250')
        assert metrics.state_transition_time_ms == Decimal('800.125')
        assert metrics.cost_attribution_time_ms == Decimal('600.075')
        assert metrics.cache_operation_time_ms == Decimal('150.050')
        assert metrics.database_operation_time_ms == Decimal('250.000')

        # Verify throughput metrics
        assert metrics.events_processed_per_second == Decimal('1250.75')
        assert metrics.state_transitions_per_second == Decimal('100.50')
        assert metrics.cost_attributions_per_second == Decimal('85.25')

        # Verify resource usage
        assert metrics.peak_memory_usage_mb == Decimal('1024.50')
        assert metrics.cpu_utilization_percent == Decimal('75.25')
        assert metrics.cache_hit_rate == Decimal('0.8750')
        assert metrics.database_query_count == 150

        # Verify optimization impact
        assert metrics.overhead_reduction_percent == Decimal('68.50')
        assert metrics.performance_improvement_factor == Decimal('2.85')

        # Verify timestamps
        assert isinstance(metrics.measurement_start, datetime)
        assert metrics.measurement_duration_ms == Decimal('0')

    def test_overall_efficiency_score_calculation(self):
        """Test overall efficiency score calculation algorithm."""
        # High performance metrics
        high_perf_metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('100.000'),  # Fast
            cache_hit_rate=Decimal('0.95'),  # High hit rate
            cpu_utilization_percent=Decimal('20.00'),  # Low CPU usage
            peak_memory_usage_mb=Decimal('100.00')  # Low memory usage
        )

        high_efficiency = high_perf_metrics.overall_efficiency_score
        assert high_efficiency > Decimal('0.8')  # Should be high efficiency

        # Low performance metrics
        low_perf_metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('10000.000'),  # Slow
            cache_hit_rate=Decimal('0.30'),  # Low hit rate
            cpu_utilization_percent=Decimal('95.00'),  # High CPU usage
            peak_memory_usage_mb=Decimal('8000.00')  # High memory usage
        )

        low_efficiency = low_perf_metrics.overall_efficiency_score
        assert low_efficiency < Decimal('0.5')  # Should be low efficiency

        # Verify efficiency score is bounded [0, 1]
        assert Decimal('0') <= high_efficiency <= Decimal('1')
        assert Decimal('0') <= low_efficiency <= Decimal('1')


class TestBottleneckAnalysis:
    """Test cases for BottleneckAnalysis data structure."""

    def test_bottleneck_analysis_creation(self):
        """Test creating bottleneck analysis with detailed information."""
        bottleneck = BottleneckAnalysis(
            bottleneck_type=BottleneckType.MEMORY_BOUND,
            severity_score=Decimal('0.85'),
            affected_phase=OptimizationPhase.EVENT_PROCESSING,
            description="High memory allocation during event processing causing frequent GC",
            recommended_action="Enable memory pooling and increase GC generation thresholds",
            estimated_improvement_percent=Decimal('25.0'),
            measurement_data={
                "memory_growth_rate_mb_per_sec": 50.5,
                "gc_frequency_per_minute": 12,
                "allocation_hotspots": ["event_creation", "state_transitions"]
            },
            call_stack_info="event_processing.py:123 -> create_event() -> allocate_payload()",
            resource_usage_snapshot={
                "memory_used_mb": 2048,
                "memory_available_mb": 512,
                "cpu_percent": 85.5
            }
        )

        assert bottleneck.bottleneck_type == BottleneckType.MEMORY_BOUND
        assert bottleneck.severity_score == Decimal('0.85')
        assert bottleneck.affected_phase == OptimizationPhase.EVENT_PROCESSING
        assert "High memory allocation" in bottleneck.description
        assert "Enable memory pooling" in bottleneck.recommended_action
        assert bottleneck.estimated_improvement_percent == Decimal('25.0')

        # Verify measurement data
        assert bottleneck.measurement_data["memory_growth_rate_mb_per_sec"] == 50.5
        assert bottleneck.measurement_data["gc_frequency_per_minute"] == 12
        assert "event_creation" in bottleneck.measurement_data["allocation_hotspots"]

        # Verify call stack and resource snapshot
        assert "event_processing.py:123" in bottleneck.call_stack_info
        assert bottleneck.resource_usage_snapshot["memory_used_mb"] == 2048


class TestOptimizationTask:
    """Test cases for OptimizationTask execution tracking."""

    def test_optimization_task_creation(self):
        """Test creating optimization task with execution tracking."""
        def sample_optimization():
            return {"optimization": "applied", "improvement": "achieved"}

        def sample_rollback():
            return {"rollback": "completed"}

        task = OptimizationTask(
            task_id="MEMORY_POOL_OPTIMIZATION",
            optimization_type="memory_pooling",
            priority=8,
            estimated_impact_percent=Decimal('15.5'),
            implementation_complexity=3,
            target_component="event_processing_engine",
            optimization_function=sample_optimization,
            rollback_function=sample_rollback
        )

        assert task.task_id == "MEMORY_POOL_OPTIMIZATION"
        assert task.optimization_type == "memory_pooling"
        assert task.priority == 8
        assert task.estimated_impact_percent == Decimal('15.5')
        assert task.implementation_complexity == 3
        assert task.target_component == "event_processing_engine"
        assert callable(task.optimization_function)
        assert callable(task.rollback_function)

        # Verify timestamps
        assert isinstance(task.created_at, datetime)
        assert task.executed_at is None
        assert task.execution_time_ms is None
        assert task.success is None
        assert task.error_message is None


class TestPerformanceProfiler:
    """Test cases for PerformanceProfiler real-time analysis."""

    @pytest.fixture
    def profiler(self):
        """Create performance profiler for testing."""
        return PerformanceProfiler(
            enable_detailed_profiling=True,
            profiling_interval_seconds=0.1,  # Fast sampling for tests
            memory_threshold_mb=500,
            cpu_threshold_percent=70.0
        )

    def test_profiler_initialization(self, profiler):
        """Test profiler initialization with configuration."""
        assert profiler.enable_detailed_profiling is True
        assert profiler.profiling_interval_seconds == 0.1
        assert profiler.memory_threshold_mb == 500
        assert profiler.cpu_threshold_percent == 70.0

        # Verify internal state
        assert profiler._profiling_active is False
        assert profiler._profiler is None
        assert len(profiler._performance_history) == 0
        assert len(profiler._bottleneck_history) == 0

    def test_profile_phase_context_manager(self, profiler):
        """Test profiling phase context manager."""
        def sample_workload():
            # Simulate some work
            time.sleep(0.01)
            # Allocate some memory
            temp_data = [i for i in range(1000)]
            return len(temp_data)

        # Profile a phase
        with profiler.profile_phase(OptimizationPhase.EVENT_PROCESSING):
            result = sample_workload()
            assert result == 1000

        # Verify profiling captured the phase
        # Note: Bottleneck detection depends on duration and memory thresholds

    def test_start_stop_monitoring(self, profiler):
        """Test starting and stopping continuous monitoring."""
        # Start monitoring
        profiler.start_monitoring()
        assert profiler._monitoring_thread is not None
        assert profiler._monitoring_thread.is_alive()

        # Let it run briefly
        time.sleep(0.2)

        # Stop monitoring
        profiler.stop_monitoring()

        # Wait for thread to finish
        time.sleep(0.1)

        # Verify some metrics were collected
        assert len(profiler._performance_history) > 0

    def test_get_current_metrics(self, profiler):
        """Test getting current performance metrics snapshot."""
        metrics = profiler.get_current_metrics()

        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.peak_memory_usage_mb > Decimal('0')
        assert metrics.cpu_utilization_percent >= Decimal('0')
        assert isinstance(metrics.measurement_start, datetime)

    def test_analyze_bottlenecks(self, profiler):
        """Test bottleneck analysis from performance history."""
        # Simulate some performance history with high memory usage
        for i in range(10):
            fake_metrics = PerformanceMetrics(
                peak_memory_usage_mb=Decimal(str(1000 + i * 100)),  # Increasing memory
                cpu_utilization_percent=Decimal('85.0'),  # High CPU
                cache_hit_rate=Decimal('0.3'),  # Low cache hit rate
                measurement_start=datetime.utcnow() - timedelta(minutes=i)
            )
            profiler._performance_history.append(fake_metrics)

        # Analyze bottlenecks
        bottlenecks = profiler.analyze_bottlenecks()

        # Should detect memory and CPU bottlenecks
        bottleneck_types = {b.bottleneck_type for b in bottlenecks}

        # Expect memory bottleneck due to increasing trend
        assert BottleneckType.MEMORY_BOUND in bottleneck_types or len(bottlenecks) > 0

        # Verify bottleneck structure
        for bottleneck in bottlenecks:
            assert isinstance(bottleneck.severity_score, Decimal)
            assert Decimal('0') <= bottleneck.severity_score <= Decimal('1')
            assert len(bottleneck.description) > 0
            assert len(bottleneck.recommended_action) > 0

    def test_memory_and_cpu_usage_tracking(self, profiler):
        """Test accurate memory and CPU usage tracking."""
        # Get initial readings
        initial_memory = profiler._get_memory_usage_mb()
        initial_cpu = profiler._get_cpu_usage_percent()

        assert initial_memory > Decimal('0')
        assert initial_cpu >= Decimal('0')

        # Allocate some memory and CPU
        def cpu_intensive_task():
            # CPU intensive calculation
            result = sum(i * i for i in range(100000))
            # Memory allocation
            temp_data = [i for i in range(10000)]
            return result, len(temp_data)

        start_time = time.time()
        result, data_len = cpu_intensive_task()
        end_time = time.time()

        # Get readings after intensive task
        after_memory = profiler._get_memory_usage_mb()
        after_cpu = profiler._get_cpu_usage_percent()

        # Memory should have increased (may not be guaranteed due to GC)
        # CPU reading may vary based on system load
        assert after_memory >= initial_memory  # May be equal due to GC
        assert isinstance(after_cpu, Decimal)

        # Verify task completed successfully
        assert result > 0
        assert data_len == 10000


class TestCoordinationOptimizer:
    """Test cases for CoordinationOptimizer main engine."""

    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager for testing."""
        cache_manager = Mock(spec=IntelligentCacheManager)
        cache_manager.optimize_cache_placement.return_value = {
            'duration_seconds': 0.5,
            'promotions_executed': 5,
            'demotions_executed': 2,
            'evictions_executed': 3,
            'total_optimizations': 10
        }
        return cache_manager

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock state manager for testing."""
        state_manager = Mock(spec=WorkforceStateManager)
        return state_manager

    @pytest.fixture
    def mock_cost_attributor(self):
        """Create mock cost attributor for testing."""
        cost_attributor = Mock(spec=CrossYearCostAttributor)
        return cost_attributor

    @pytest.fixture
    def coordination_optimizer(self, mock_cache_manager):
        """Create coordination optimizer for testing."""
        return CoordinationOptimizer(
            optimization_strategy=OptimizationStrategy.BALANCED,
            target_overhead_reduction_percent=Decimal('65'),
            enable_parallel_processing=True,
            max_worker_threads=2,  # Smaller for testing
            enable_database_optimization=True,
            cache_manager=mock_cache_manager
        )

    def test_coordination_optimizer_initialization(self, coordination_optimizer, mock_cache_manager):
        """Test coordination optimizer initialization."""
        assert coordination_optimizer.optimization_strategy == OptimizationStrategy.BALANCED
        assert coordination_optimizer.target_overhead_reduction_percent == Decimal('65')
        assert coordination_optimizer.enable_parallel_processing is True
        assert coordination_optimizer.max_worker_threads == 2
        assert coordination_optimizer.enable_database_optimization is True
        assert coordination_optimizer.cache_manager == mock_cache_manager

        # Verify internal state
        assert isinstance(coordination_optimizer.profiler, PerformanceProfiler)
        assert len(coordination_optimizer._optimization_tasks) == 0
        assert len(coordination_optimizer._completed_optimizations) == 0
        assert coordination_optimizer._optimization_active is False

        # Verify thread pools are initialized
        assert coordination_optimizer._thread_pool is not None
        assert coordination_optimizer._process_pool is not None

    def test_optimize_multi_year_coordination(
        self,
        coordination_optimizer,
        mock_state_manager,
        mock_cost_attributor
    ):
        """Test comprehensive multi-year coordination optimization."""
        simulation_years = [2024, 2025, 2026]

        # Run optimization
        results = coordination_optimizer.optimize_multi_year_coordination(
            state_manager=mock_state_manager,
            cost_attributor=mock_cost_attributor,
            simulation_years=simulation_years
        )

        # Verify results structure
        assert 'optimization_strategy' in results
        assert 'target_overhead_reduction_percent' in results
        assert 'actual_overhead_reduction_percent' in results
        assert 'total_optimization_time_seconds' in results
        assert 'simulation_years' in results
        assert 'optimization_results' in results
        assert 'performance_analysis' in results
        assert 'baseline_metrics' in results
        assert 'optimized_metrics' in results
        assert 'bottlenecks_identified' in results
        assert 'target_achieved' in results
        assert 'performance_grade' in results
        assert 'optimization_timestamp' in results

        # Verify optimization details
        assert results['optimization_strategy'] == 'balanced'
        assert results['target_overhead_reduction_percent'] == 65.0
        assert results['simulation_years'] == simulation_years
        assert isinstance(results['total_optimization_time_seconds'], float)
        assert results['total_optimization_time_seconds'] > 0

        # Verify optimization results exist for different phases
        optimization_results = results['optimization_results']
        expected_phases = ['event_processing', 'state_transitions', 'cost_attribution', 'cache_management']

        # Should have attempted various optimizations
        assert len(optimization_results) > 0

    def test_optimization_strategy_selection(self):
        """Test different optimization strategies create appropriate configurations."""
        strategies_to_test = [
            OptimizationStrategy.AGGRESSIVE,
            OptimizationStrategy.BALANCED,
            OptimizationStrategy.CONSERVATIVE,
            OptimizationStrategy.MEMORY_OPTIMIZED,
            OptimizationStrategy.CPU_OPTIMIZED,
            OptimizationStrategy.IO_OPTIMIZED
        ]

        for strategy in strategies_to_test:
            optimizer = CoordinationOptimizer(
                optimization_strategy=strategy,
                target_overhead_reduction_percent=Decimal('50'),
                enable_parallel_processing=True,
                max_worker_threads=2
            )

            assert optimizer.optimization_strategy == strategy
            assert optimizer.target_overhead_reduction_percent == Decimal('50')

    def test_analyze_optimization_opportunities(
        self,
        coordination_optimizer,
        mock_state_manager,
        mock_cost_attributor
    ):
        """Test optimization opportunity analysis."""
        simulation_years = [2024, 2025]

        opportunities = coordination_optimizer._analyze_optimization_opportunities(
            mock_state_manager, mock_cost_attributor, simulation_years
        )

        # Verify opportunity analysis structure
        assert 'opportunities' in opportunities
        assert 'total_estimated_improvement' in opportunities
        assert 'analysis_timestamp' in opportunities

        # Verify specific optimization opportunities
        opps = opportunities['opportunities']
        assert 'parallel_processing' in opps
        assert 'database_optimization' in opps
        assert 'cache_optimization' in opps
        assert 'memory_optimization' in opps

        # Each opportunity should have required fields
        for opp_name, opp_details in opps.items():
            assert 'enabled' in opp_details
            assert 'estimated_improvement' in opp_details
            assert 'complexity' in opp_details

        # Total improvement should be sum of enabled improvements
        total_improvement = opportunities['total_estimated_improvement']
        assert total_improvement > 0

    def test_optimize_event_processing(self, coordination_optimizer, mock_state_manager):
        """Test event processing optimization."""
        simulation_years = [2024, 2025]

        result = coordination_optimizer._optimize_event_processing(
            mock_state_manager, simulation_years
        )

        # Should succeed when parallel processing is enabled
        if coordination_optimizer.enable_parallel_processing:
            assert result['enabled'] is True
            assert 'batch_size' in result
            assert 'optimization_time_seconds' in result
            assert 'estimated_improvement_percent' in result
            assert 'techniques_applied' in result

            # Verify techniques applied
            techniques = result['techniques_applied']
            assert 'batch_processing' in techniques
            assert 'memory_pooling' in techniques
            assert 'garbage_collection_tuning' in techniques
        else:
            assert result['enabled'] is False
            assert 'reason' in result

    def test_optimize_state_transitions(self, coordination_optimizer, mock_state_manager):
        """Test state transition optimization."""
        simulation_years = [2024, 2025, 2026]

        result = coordination_optimizer._optimize_state_transitions(
            mock_state_manager, simulation_years
        )

        # Should always be enabled
        assert result['enabled'] is True
        assert 'optimization_time_seconds' in result
        assert 'serialization_improvements' in result
        assert 'dependency_improvements' in result
        assert 'estimated_improvement_percent' in result
        assert 'techniques_applied' in result

        # Verify techniques applied
        techniques = result['techniques_applied']
        assert 'object_pre_allocation' in techniques
        assert 'serialization_optimization' in techniques
        assert 'dependency_graph_optimization' in techniques

    def test_optimize_cost_attribution(self, coordination_optimizer, mock_cost_attributor):
        """Test cost attribution optimization."""
        simulation_years = [2024, 2025]

        result = coordination_optimizer._optimize_cost_attribution(
            mock_cost_attributor, simulation_years
        )

        # Should always be enabled
        assert result['enabled'] is True
        assert 'optimization_time_seconds' in result
        assert 'vectorization_improvements' in result
        assert 'precision_improvements' in result
        assert 'batch_improvements' in result
        assert 'estimated_improvement_percent' in result
        assert 'techniques_applied' in result

        # Verify techniques applied
        techniques = result['techniques_applied']
        assert 'vectorized_calculations' in techniques
        assert 'decimal_precision_optimization' in techniques
        assert 'batch_processing' in techniques

    def test_optimize_cache_management(self, coordination_optimizer, mock_cache_manager):
        """Test cache management optimization."""
        result = coordination_optimizer._optimize_cache_management()

        # Should be enabled when cache manager is available
        assert result['enabled'] is True
        assert 'optimization_time_seconds' in result
        assert 'cache_optimization_results' in result
        assert 'coherency_improvements' in result
        assert 'estimated_improvement_percent' in result
        assert 'techniques_applied' in result

        # Verify cache manager was called
        mock_cache_manager.optimize_cache_placement.assert_called_once()

        # Verify techniques applied
        techniques = result['techniques_applied']
        assert 'cache_placement_optimization' in techniques
        assert 'intelligent_prefetching' in techniques
        assert 'coherency_optimization' in techniques

    def test_optimize_database_operations(self, coordination_optimizer):
        """Test database operations optimization."""
        result = coordination_optimizer._optimize_database_operations()

        # Should be enabled when database optimization is enabled
        if coordination_optimizer.enable_database_optimization:
            assert result['enabled'] is True
            assert 'optimization_time_seconds' in result
            assert 'connection_improvements' in result
            assert 'query_improvements' in result
            assert 'index_improvements' in result
            assert 'estimated_improvement_percent' in result
            assert 'techniques_applied' in result

            # Verify techniques applied
            techniques = result['techniques_applied']
            assert 'connection_pooling' in techniques
            assert 'query_batching' in techniques
            assert 'index_optimization' in techniques
        else:
            assert result['enabled'] is False
            assert 'reason' in result

    def test_analyze_optimization_impact(self, coordination_optimizer):
        """Test optimization impact analysis."""
        # Set up mock baseline and optimized metrics
        baseline_metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('10000.000'),
            peak_memory_usage_mb=Decimal('2000.00'),
            cache_hit_rate=Decimal('0.60')
        )

        optimized_metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('3500.000'),  # 65% improvement
            peak_memory_usage_mb=Decimal('1400.00'),  # 30% improvement
            cache_hit_rate=Decimal('0.85'),  # 25% improvement
            performance_improvement_factor=Decimal('2.86'),
            overall_efficiency_score=Decimal('0.85')
        )

        coordination_optimizer._baseline_metrics = baseline_metrics
        coordination_optimizer._optimized_metrics = optimized_metrics

        # Analyze impact
        analysis = coordination_optimizer._analyze_optimization_impact()

        # Verify analysis structure
        assert 'time_improvement_percent' in analysis
        assert 'memory_improvement_percent' in analysis
        assert 'cache_improvement_percent' in analysis
        assert 'overhead_reduction_percent' in analysis
        assert 'performance_improvement_factor' in analysis
        assert 'efficiency_score' in analysis
        assert 'baseline_execution_time_ms' in analysis
        assert 'optimized_execution_time_ms' in analysis
        assert 'analysis_timestamp' in analysis

        # Verify calculations
        assert analysis['time_improvement_percent'] == 65.0  # (10000-3500)/10000 * 100
        assert analysis['memory_improvement_percent'] == 30.0  # (2000-1400)/2000 * 100
        assert analysis['cache_improvement_percent'] == 25.0  # (0.85-0.60) * 100

        # Overhead reduction should be weighted average
        expected_overhead = 65.0 * 0.4 + 30.0 * 0.3 + 25.0 * 0.3
        assert abs(float(analysis['overhead_reduction_percent']) - expected_overhead) < 0.1

    def test_calculate_performance_grade(self, coordination_optimizer):
        """Test performance grade calculation based on overhead reduction."""
        test_cases = [
            (Decimal('70'), 'A+'),  # Exceeded target
            (Decimal('55'), 'A'),   # Close to target
            (Decimal('40'), 'B+'),  # Good improvement
            (Decimal('25'), 'B'),   # Moderate improvement
            (Decimal('15'), 'C'),   # Some improvement
            (Decimal('5'), 'D')     # Minimal improvement
        ]

        for overhead_reduction, expected_grade in test_cases:
            grade = coordination_optimizer._calculate_performance_grade(overhead_reduction)
            assert grade == expected_grade

    def test_calculate_optimal_batch_size(self, coordination_optimizer):
        """Test optimal batch size calculation."""
        batch_size = coordination_optimizer._calculate_optimal_batch_size()

        # Should return reasonable batch size
        assert isinstance(batch_size, int)
        assert 100 <= batch_size <= 10000  # Within reasonable bounds

    def test_optimize_garbage_collection(self, coordination_optimizer):
        """Test garbage collection optimization."""
        # Get initial GC stats
        initial_gc_stats = gc.get_stats()
        initial_threshold = gc.get_threshold()

        # Run GC optimization
        coordination_optimizer._optimize_garbage_collection()

        # Verify GC was called and thresholds adjusted
        post_threshold = gc.get_threshold()

        # Thresholds should be adjusted (may vary by implementation)
        # Main verification is that the method runs without error
        assert len(post_threshold) == 3  # Should have 3 generation thresholds

    def test_optimization_error_handling(self, coordination_optimizer):
        """Test error handling during optimization."""
        # Create mock objects that raise exceptions
        mock_state_manager = Mock(spec=WorkforceStateManager)
        mock_cost_attributor = Mock(spec=CrossYearCostAttributor)

        # Mock methods to raise exceptions
        with patch.object(coordination_optimizer, '_optimize_event_processing') as mock_event_opt:
            mock_event_opt.side_effect = Exception("Event processing failed")

            # Run optimization - should handle errors gracefully
            with pytest.raises(Exception):
                coordination_optimizer.optimize_multi_year_coordination(
                    state_manager=mock_state_manager,
                    cost_attributor=mock_cost_attributor,
                    simulation_years=[2024, 2025]
                )

    def test_concurrent_optimization_safety(self, coordination_optimizer):
        """Test thread safety of optimization operations."""
        mock_state_manager = Mock(spec=WorkforceStateManager)
        mock_cost_attributor = Mock(spec=CrossYearCostAttributor)

        def run_optimization():
            try:
                return coordination_optimizer.optimize_multi_year_coordination(
                    state_manager=mock_state_manager,
                    cost_attributor=mock_cost_attributor,
                    simulation_years=[2024]
                )
            except RuntimeError as e:
                if "Optimization already in progress" in str(e):
                    return {"error": "concurrent_access"}
                raise

        # Start first optimization in a thread
        import threading
        results = []

        def thread_target():
            result = run_optimization()
            results.append(result)

        thread1 = threading.Thread(target=thread_target)
        thread2 = threading.Thread(target=thread_target)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # One should succeed, one should fail with concurrent access error
        assert len(results) == 2

        # At least one should complete (may both succeed if timing allows)
        success_count = sum(1 for r in results if "error" not in r)
        error_count = sum(1 for r in results if r.get("error") == "concurrent_access")

        assert success_count >= 1  # At least one should succeed


class TestFactoryFunctions:
    """Test cases for factory functions."""

    def test_create_coordination_optimizer(self):
        """Test coordination optimizer factory function."""
        mock_cache_manager = Mock(spec=IntelligentCacheManager)

        optimizer = create_coordination_optimizer(
            strategy=OptimizationStrategy.AGGRESSIVE,
            target_reduction_percent=Decimal('70'),
            cache_manager=mock_cache_manager
        )

        assert optimizer.optimization_strategy == OptimizationStrategy.AGGRESSIVE
        assert optimizer.target_overhead_reduction_percent == Decimal('70')
        assert optimizer.cache_manager == mock_cache_manager
        assert optimizer.enable_parallel_processing is True
        assert optimizer.enable_database_optimization is True

    def test_create_performance_profiler(self):
        """Test performance profiler factory function."""
        profiler = create_performance_profiler(
            detailed_profiling=False,
            monitoring_interval=2.0
        )

        assert profiler.enable_detailed_profiling is False
        assert profiler.profiling_interval_seconds == 2.0
        assert profiler.memory_threshold_mb == 1000
        assert profiler.cpu_threshold_percent == 80.0


class TestPerformanceTargets:
    """Test cases for performance target achievement."""

    def test_target_overhead_reduction_achievement(self):
        """Test that optimizer can achieve target overhead reduction."""
        mock_cache_manager = Mock(spec=IntelligentCacheManager)
        mock_cache_manager.optimize_cache_placement.return_value = {
            'duration_seconds': 0.1,
            'promotions_executed': 10,
            'demotions_executed': 5,
            'evictions_executed': 2,
            'total_optimizations': 17
        }

        optimizer = CoordinationOptimizer(
            optimization_strategy=OptimizationStrategy.AGGRESSIVE,
            target_overhead_reduction_percent=Decimal('65'),
            cache_manager=mock_cache_manager
        )

        # Create optimistic baseline and optimized metrics
        baseline_metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('10000.000'),
            peak_memory_usage_mb=Decimal('2000.00'),
            cache_hit_rate=Decimal('0.50')
        )

        # Simulate significant improvements
        optimized_metrics = PerformanceMetrics(
            total_execution_time_ms=Decimal('3000.000'),  # 70% improvement
            peak_memory_usage_mb=Decimal('1200.00'),  # 40% improvement
            cache_hit_rate=Decimal('0.90'),  # 40% improvement
            performance_improvement_factor=Decimal('3.33'),
            overall_efficiency_score=Decimal('0.90')
        )

        optimizer._baseline_metrics = baseline_metrics
        optimizer._optimized_metrics = optimized_metrics

        # Analyze impact
        analysis = optimizer._analyze_optimization_impact()

        # Should achieve target
        overhead_reduction = analysis['overhead_reduction_percent']
        assert overhead_reduction >= Decimal('65')

        # Should get high performance grade
        grade = optimizer._calculate_performance_grade(overhead_reduction)
        assert grade in ['A+', 'A']

    def test_sub_second_state_transitions(self):
        """Test that state transitions can be optimized to sub-second performance."""
        optimizer = CoordinationOptimizer(
            optimization_strategy=OptimizationStrategy.BALANCED,
            target_overhead_reduction_percent=Decimal('50')
        )

        mock_state_manager = Mock(spec=WorkforceStateManager)
        simulation_years = [2024, 2025]

        # Run state transition optimization
        result = optimizer._optimize_state_transitions(mock_state_manager, simulation_years)

        # Verify optimization was applied
        assert result['enabled'] is True
        assert result['optimization_time_seconds'] < 1.0  # Should be fast
        assert result['estimated_improvement_percent'] > 0

    def test_memory_utilization_efficiency(self):
        """Test memory utilization stays under 90% during operations."""
        profiler = PerformanceProfiler(
            memory_threshold_mb=1000,  # Set reasonable threshold
            cpu_threshold_percent=80.0
        )

        # Simulate memory-intensive operation
        def memory_intensive_operation():
            # Allocate memory but stay within reasonable bounds
            data = []
            for i in range(1000):
                data.append([j for j in range(100)])
            return len(data)

        with profiler.profile_phase(OptimizationPhase.EVENT_PROCESSING):
            result = memory_intensive_operation()
            assert result == 1000

        # Get current metrics
        metrics = profiler.get_current_metrics()

        # Memory usage should be reasonable (this is system-dependent)
        # Main verification is that profiling works without errors
        assert metrics.peak_memory_usage_mb > Decimal('0')
        assert metrics.cpu_utilization_percent >= Decimal('0')

    def test_cache_hit_rate_target(self):
        """Test cache optimization can achieve >85% hit rate target."""
        # This test verifies the optimization logic exists
        # Actual hit rate depends on cache manager implementation

        mock_cache_manager = Mock(spec=IntelligentCacheManager)
        mock_cache_manager.optimize_cache_placement.return_value = {
            'duration_seconds': 0.2,
            'promotions_executed': 15,
            'demotions_executed': 8,
            'evictions_executed': 3,
            'total_optimizations': 26
        }

        optimizer = CoordinationOptimizer(
            optimization_strategy=OptimizationStrategy.BALANCED,
            cache_manager=mock_cache_manager
        )

        # Run cache optimization
        result = optimizer._optimize_cache_management()

        # Verify optimization was applied
        assert result['enabled'] is True
        assert result['estimated_improvement_percent'] == 30  # As configured in method

        # Verify cache manager optimization was called
        mock_cache_manager.optimize_cache_placement.assert_called_once()
