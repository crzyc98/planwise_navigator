#!/usr/bin/env python3
"""
Test Hybrid Pipeline Integration (E068G)

Comprehensive tests for the hybrid pipeline that supports both SQL and Polars
event generation modes with seamless switching and performance monitoring.
"""

import json
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Import the modules we're testing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from navigator_orchestrator.config import SimulationConfig, EventGenerationSettings, PolarsEventSettings
from navigator_orchestrator.hybrid_performance_monitor import HybridPerformanceMonitor, EventGenerationMetrics
from navigator_orchestrator.pipeline_orchestrator import PipelineOrchestrator


class TestHybridPipelineConfiguration:
    """Test hybrid pipeline configuration and validation."""

    def test_event_generation_settings_creation(self):
        """Test creation of event generation settings."""
        settings = EventGenerationSettings(
            mode="polars",
            polars=PolarsEventSettings(
                enabled=True,
                max_threads=16,
                batch_size=5000,
                output_path="test/output"
            )
        )

        assert settings.mode == "polars"
        assert settings.polars.enabled is True
        assert settings.polars.max_threads == 16
        assert settings.polars.batch_size == 5000

    def test_event_generation_mode_validation(self):
        """Test event generation mode validation."""
        # Valid configuration
        settings = EventGenerationSettings(mode="sql")
        settings.validate_mode()  # Should not raise

        # Invalid mode
        with pytest.raises(ValueError, match="Invalid event generation mode"):
            invalid_settings = EventGenerationSettings(mode="invalid_mode")
            invalid_settings.validate_mode()

        # Polars mode but not enabled
        with pytest.raises(ValueError, match="Polars mode selected but polars.enabled is False"):
            polars_disabled = EventGenerationSettings(
                mode="polars",
                polars=PolarsEventSettings(enabled=False)
            )
            polars_disabled.validate_mode()

    def test_polars_event_settings_defaults(self):
        """Test Polars event settings default values."""
        settings = PolarsEventSettings()

        assert settings.enabled is False
        assert settings.max_threads == 16
        assert settings.batch_size == 10000
        assert settings.output_path == "data/parquet/events"
        assert settings.enable_compression is True
        assert settings.compression_level == 6
        assert settings.fallback_on_error is True

    def test_simulation_config_event_generation_methods(self):
        """Test SimulationConfig event generation helper methods."""
        # Create minimal config for testing
        config_data = {
            "simulation": {"start_year": 2025, "end_year": 2026},
            "compensation": {"cola_rate": 0.02, "merit_budget": 0.03},
            "optimization": {
                "event_generation": {
                    "mode": "polars",
                    "polars": {"enabled": True, "max_threads": 8}
                }
            }
        }

        config = SimulationConfig(**config_data)

        assert config.get_event_generation_mode() == "polars"
        assert config.is_polars_mode_enabled() is True

        polars_settings = config.get_polars_settings()
        assert polars_settings.enabled is True
        assert polars_settings.max_threads == 8

    def test_simulation_config_sql_mode(self):
        """Test SimulationConfig with SQL mode."""
        config_data = {
            "simulation": {"start_year": 2025, "end_year": 2026},
            "compensation": {"cola_rate": 0.02, "merit_budget": 0.03}
        }

        config = SimulationConfig(**config_data)

        # Should default to SQL mode
        assert config.get_event_generation_mode() == "sql"
        assert config.is_polars_mode_enabled() is False


class TestHybridPerformanceMonitor:
    """Test hybrid performance monitoring functionality."""

    @pytest.fixture
    def temp_reports_dir(self):
        """Create temporary directory for reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_performance_monitor_initialization(self, temp_reports_dir):
        """Test performance monitor initialization."""
        monitor = HybridPerformanceMonitor(reports_dir=temp_reports_dir)

        assert monitor.reports_dir == temp_reports_dir
        assert monitor.metrics_history == []
        assert monitor.comparisons_history == []

    def test_event_generation_metrics_creation(self):
        """Test creation of event generation metrics."""
        start_time = time.time()
        end_time = start_time + 10.5

        metrics = EventGenerationMetrics(
            mode="polars",
            start_time=start_time,
            end_time=end_time,
            execution_time=10.5,
            total_events=50000,
            years_processed=[2025, 2026],
            memory_usage_mb=1024.0,
            cpu_usage_percent=75.0,
            events_per_second=4761.9,
            peak_memory_mb=1200.0,
            fallback_used=False,
            success=True
        )

        assert metrics.mode == "polars"
        assert metrics.execution_time == 10.5
        assert metrics.total_events == 50000
        assert metrics.events_per_second == pytest.approx(4761.9)
        assert metrics.fallback_used is False
        assert metrics.success is True

    def test_metrics_to_dict_serialization(self):
        """Test metrics serialization to dictionary."""
        metrics = EventGenerationMetrics(
            mode="sql",
            start_time=1640000000.0,
            end_time=1640000060.0,
            execution_time=60.0,
            total_events=25000,
            years_processed=[2025],
            memory_usage_mb=512.0,
            cpu_usage_percent=50.0,
            events_per_second=416.7,
            peak_memory_mb=600.0
        )

        data = metrics.to_dict()

        assert data['mode'] == "sql"
        assert data['execution_time'] == 60.0
        assert data['total_events'] == 25000
        assert data['success'] is True
        assert 'timestamp' in data

    def test_performance_monitoring_session(self, temp_reports_dir):
        """Test performance monitoring session lifecycle."""
        monitor = HybridPerformanceMonitor(reports_dir=temp_reports_dir)

        # Start monitoring session
        monitor.start_monitoring_session()
        assert monitor._current_session_start is not None
        assert monitor._baseline_memory_mb is not None

        # Start event generation monitoring
        context = monitor.start_event_generation_monitoring("polars", [2025, 2026])
        assert context['mode'] == "polars"
        assert context['years'] == [2025, 2026]
        assert 'start_time' in context

        # Simulate processing time
        time.sleep(0.1)

        # End monitoring
        metrics = monitor.end_event_generation_monitoring(
            context, total_events=10000, success=True
        )

        assert metrics.mode == "polars"
        assert metrics.total_events == 10000
        assert metrics.success is True
        assert metrics.execution_time > 0
        assert len(monitor.metrics_history) == 1

    def test_performance_comparison(self, temp_reports_dir):
        """Test performance comparison between modes."""
        monitor = HybridPerformanceMonitor(reports_dir=temp_reports_dir)

        # Create SQL metrics (slower)
        sql_metrics = EventGenerationMetrics(
            mode="sql",
            start_time=time.time(),
            end_time=time.time() + 120,
            execution_time=120.0,
            total_events=10000,
            years_processed=[2025],
            memory_usage_mb=800.0,
            cpu_usage_percent=60.0,
            events_per_second=83.3,
            peak_memory_mb=1000.0
        )

        # Create Polars metrics (faster)
        polars_metrics = EventGenerationMetrics(
            mode="polars",
            start_time=time.time(),
            end_time=time.time() + 45,
            execution_time=45.0,
            total_events=10000,
            years_processed=[2025],
            memory_usage_mb=600.0,
            cpu_usage_percent=80.0,
            events_per_second=222.2,
            peak_memory_mb=700.0
        )

        comparison = monitor.compare_modes(sql_metrics, polars_metrics)

        assert comparison.speedup_factor == pytest.approx(120.0 / 45.0, rel=0.1)
        assert comparison.memory_efficiency == pytest.approx(1000.0 / 700.0, rel=0.1)
        assert "faster" in comparison.recommendation.lower()

    def test_performance_report_generation(self, temp_reports_dir):
        """Test performance report generation and saving."""
        monitor = HybridPerformanceMonitor(reports_dir=temp_reports_dir)
        monitor.start_monitoring_session()

        # Add some dummy metrics
        sql_metrics = EventGenerationMetrics(
            mode="sql", start_time=time.time(), end_time=time.time() + 60,
            execution_time=60.0, total_events=5000, years_processed=[2025],
            memory_usage_mb=400.0, cpu_usage_percent=50.0,
            events_per_second=83.3, peak_memory_mb=500.0
        )
        monitor.metrics_history.append(sql_metrics)

        # Generate report
        report = monitor.generate_performance_report()

        assert 'session_info' in report
        assert 'metrics_history' in report
        assert 'summary' in report
        assert 'recommendations' in report
        assert report['session_info']['total_runs'] == 1

        # Save report
        report_path = monitor.save_performance_report("test_report.json")
        assert report_path.exists()

        # Verify saved content
        with open(report_path) as f:
            saved_report = json.load(f)
        assert saved_report['session_info']['total_runs'] == 1


class TestHybridPipelineIntegration:
    """Test hybrid pipeline integration in PipelineOrchestrator."""

    @pytest.fixture
    def mock_config(self):
        """Create mock SimulationConfig for testing."""
        config = Mock(spec=SimulationConfig)
        config.simulation = Mock()
        config.simulation.start_year = 2025
        config.simulation.end_year = 2026
        config.simulation.random_seed = 12345

        config.get_event_generation_mode.return_value = "polars"
        config.is_polars_mode_enabled.return_value = True

        polars_settings = Mock(spec=PolarsEventSettings)
        polars_settings.enabled = True
        polars_settings.max_threads = 8
        polars_settings.batch_size = 5000
        polars_settings.output_path = "test/output"
        polars_settings.fallback_on_error = True
        config.get_polars_settings.return_value = polars_settings

        return config

    @pytest.fixture
    def mock_orchestrator_components(self):
        """Create mock components for PipelineOrchestrator."""
        components = {
            'db_manager': Mock(),
            'dbt_runner': Mock(),
            'registry_manager': Mock(),
            'validator': Mock()
        }
        return components

    def test_orchestrator_hybrid_configuration_extraction(self, mock_config, mock_orchestrator_components):
        """Test that orchestrator correctly extracts hybrid configuration."""
        with patch('navigator_orchestrator.pipeline.HybridPerformanceMonitor'):
            orchestrator = PipelineOrchestrator(
                config=mock_config,
                verbose=True,
                **mock_orchestrator_components
            )

            assert orchestrator.event_generation_mode == "polars"
            assert orchestrator.is_polars_enabled is True
            assert orchestrator.polars_settings.enabled is True

    @patch('navigator_orchestrator.pipeline.PolarsEventGenerator')
    @patch('navigator_orchestrator.pipeline.EventFactoryConfig')
    def test_polars_event_generation_execution(self, mock_factory_config, mock_generator,
                                             mock_config, mock_orchestrator_components):
        """Test Polars event generation execution."""
        # Setup mocks
        mock_generator_instance = Mock()
        mock_generator_instance.stats = {'total_events_generated': 15000}
        mock_generator.return_value = mock_generator_instance

        with patch('navigator_orchestrator.pipeline.HybridPerformanceMonitor'):
            orchestrator = PipelineOrchestrator(
                config=mock_config,
                verbose=True,
                **mock_orchestrator_components
            )

            # Execute Polars event generation
            result = orchestrator._execute_polars_event_generation([2025], time.time())

            assert result['mode'] == 'polars'
            assert result['success'] is True
            assert result['total_events'] == 15000
            assert 'execution_time' in result
            assert 'performance_target_met' in result

    def test_sql_event_generation_fallback(self, mock_config, mock_orchestrator_components):
        """Test SQL event generation as fallback."""
        # Configure for SQL mode
        mock_config.get_event_generation_mode.return_value = "sql"
        mock_config.is_polars_mode_enabled.return_value = False

        # Mock dbt runner for SQL execution
        mock_dbt_result = Mock()
        mock_dbt_result.success = True
        mock_orchestrator_components['dbt_runner'].execute_command.return_value = mock_dbt_result
        mock_orchestrator_components['db_manager'].execute_with_retry.return_value = 5000

        with patch('navigator_orchestrator.pipeline.HybridPerformanceMonitor'):
            orchestrator = PipelineOrchestrator(
                config=mock_config,
                verbose=True,
                **mock_orchestrator_components
            )

            # Execute SQL event generation
            result = orchestrator._execute_sql_event_generation([2025], time.time())

            assert result['mode'] == 'sql'
            assert result['success'] is True
            assert result['total_events'] == 5000
            assert 'execution_time' in result

    def test_hybrid_event_generation_mode_switching(self, mock_config, mock_orchestrator_components):
        """Test hybrid event generation with mode switching."""
        with patch('navigator_orchestrator.pipeline.HybridPerformanceMonitor') as mock_monitor_class:
            mock_monitor = Mock()
            mock_monitor_class.return_value = mock_monitor

            orchestrator = PipelineOrchestrator(
                config=mock_config,
                verbose=True,
                **mock_orchestrator_components
            )

            # Mock the actual generation methods
            with patch.object(orchestrator, '_execute_polars_event_generation') as mock_polars:
                mock_polars.return_value = {
                    'mode': 'polars',
                    'success': True,
                    'total_events': 20000,
                    'execution_time': 45.0
                }

                result = orchestrator._execute_hybrid_event_generation([2025])

                assert result['mode'] == 'polars'
                assert result['success'] is True
                assert mock_monitor.start_monitoring_session.called
                assert mock_monitor.display_performance_summary.called

    def test_error_handling_and_fallback(self, mock_config, mock_orchestrator_components):
        """Test error handling and automatic fallback from Polars to SQL."""
        with patch('navigator_orchestrator.pipeline.HybridPerformanceMonitor'):
            orchestrator = PipelineOrchestrator(
                config=mock_config,
                verbose=True,
                **mock_orchestrator_components
            )

            # Mock Polars generation to fail
            with patch.object(orchestrator, '_execute_polars_event_generation') as mock_polars:
                with patch.object(orchestrator, '_execute_sql_event_generation') as mock_sql:

                    mock_polars.side_effect = Exception("Polars generation failed")
                    mock_sql.return_value = {
                        'mode': 'sql',
                        'success': True,
                        'total_events': 10000,
                        'execution_time': 90.0,
                        'fallback_used': True
                    }

                    result = orchestrator._execute_hybrid_event_generation([2025])

                    assert result['mode'] == 'sql'
                    assert result['success'] is True
                    assert result['fallback_used'] is True
                    assert mock_sql.called


class TestHybridPipelineEndToEnd:
    """End-to-end integration tests."""

    def test_configuration_loading_and_validation(self, tmp_path):
        """Test loading and validating hybrid configuration."""
        # Create test configuration
        config_content = """
simulation:
  start_year: 2025
  end_year: 2026
  random_seed: 42

compensation:
  cola_rate: 0.02
  merit_budget: 0.03

optimization:
  event_generation:
    mode: polars
    polars:
      enabled: true
      max_threads: 4
      batch_size: 1000
      output_path: test_output
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        from navigator_orchestrator.config import load_simulation_config

        config = load_simulation_config(config_path)

        assert config.get_event_generation_mode() == "polars"
        assert config.is_polars_mode_enabled() is True

        polars_settings = config.get_polars_settings()
        assert polars_settings.max_threads == 4
        assert polars_settings.batch_size == 1000
        assert polars_settings.output_path == "test_output"

        # Validate configuration
        config.validate_threading_configuration()  # Should not raise


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
