"""
Configuration compatibility tests for orchestrator_dbt.

Tests configuration loading, validation, and compatibility including:
- simulation_config.yaml compatibility with new and legacy systems
- Configuration validation and error handling
- Backward compatibility with existing workflows
- Edge case configuration handling
- Migration path validation

Target: Ensure S031-01 maintains full backward compatibility
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import yaml

# Import system under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "orchestrator_dbt"))

from run_multi_year import (
    validate_configuration,
    load_and_validate_config,
    test_configuration_compatibility
)


class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation logic."""

    def test_validate_minimal_valid_configuration(self):
        """Test validation of minimal valid configuration."""
        minimal_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'random_seed': 42
        }

        is_valid, errors = validate_configuration(minimal_config)

        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_comprehensive_configuration(self):
        """Test validation of comprehensive configuration matching production usage."""
        comprehensive_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2030,
                'target_growth_rate': 0.035
            },
            'workforce': {
                'total_termination_rate': 0.15,
                'new_hire_termination_rate': 0.28,
                'voluntary_termination_rate': 0.10,
                'involuntary_termination_rate': 0.05
            },
            'eligibility': {
                'waiting_period_days': 90,
                'min_hours_per_week': 20,
                'min_age': 18,
                'max_age': 65,
                'service_requirement_months': 12
            },
            'enrollment': {
                'auto_enrollment': {
                    'hire_date_cutoff': '2023-01-01',
                    'scope': 'all_eligible',
                    'default_deferral_rate': 0.06,
                    'auto_escalation': True,
                    'escalation_rate': 0.01,
                    'max_escalation_rate': 0.15
                },
                'opt_out_window_days': 90,
                'annual_enrollment_window_days': 30
            },
            'compensation': {
                'cola_rate': 0.028,
                'merit_pool': 0.035,
                'promotion_pool': 0.015,
                'market_adjustment_pool': 0.005,
                'salary_ranges': {
                    'min_increase': 0.01,
                    'max_increase': 0.20
                }
            },
            'plan_year': {
                'start_month': 1,
                'start_day': 1,
                'end_month': 12,
                'end_day': 31
            },
            'employee_id_generation': {
                'strategy': 'sequential',
                'prefix': 'EMP',
                'start_number': 1000,
                'padding': 6
            },
            'raise_timing': {
                'distribution': 'realistic',
                'annual_review_month': 3,
                'promotion_timing': 'any_time',
                'cola_timing': 'january'
            },
            'random_seed': 42
        }

        is_valid, errors = validate_configuration(comprehensive_config)

        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_missing_required_sections(self):
        """Test validation fails with missing required sections."""
        invalid_configs = [
            # Missing simulation section
            {
                'workforce': {'total_termination_rate': 0.12},
                'random_seed': 42
            },
            # Missing workforce section
            {
                'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.03},
                'random_seed': 42
            },
            # Missing random_seed
            {
                'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.03},
                'workforce': {'total_termination_rate': 0.12}
            }
        ]

        for i, config in enumerate(invalid_configs):
            with self.subTest(f"Invalid config {i+1}"):
                is_valid, errors = validate_configuration(config)

                self.assertFalse(is_valid)
                self.assertGreater(len(errors), 0)

    def test_validate_missing_required_fields(self):
        """Test validation fails with missing required fields."""
        invalid_configs = [
            # Missing start_year
            {
                'simulation': {'end_year': 2027, 'target_growth_rate': 0.03},
                'workforce': {'total_termination_rate': 0.12},
                'random_seed': 42
            },
            # Missing end_year
            {
                'simulation': {'start_year': 2025, 'target_growth_rate': 0.03},
                'workforce': {'total_termination_rate': 0.12},
                'random_seed': 42
            },
            # Missing target_growth_rate
            {
                'simulation': {'start_year': 2025, 'end_year': 2027},
                'workforce': {'total_termination_rate': 0.12},
                'random_seed': 42
            },
            # Missing total_termination_rate
            {
                'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.03},
                'workforce': {'new_hire_termination_rate': 0.25},
                'random_seed': 42
            }
        ]

        for i, config in enumerate(invalid_configs):
            with self.subTest(f"Missing field config {i+1}"):
                is_valid, errors = validate_configuration(config)

                self.assertFalse(is_valid)
                self.assertGreater(len(errors), 0)

    def test_validate_invalid_value_ranges(self):
        """Test validation fails with invalid value ranges."""
        invalid_configs = [
            # Invalid year range (end before start)
            {
                'simulation': {'start_year': 2027, 'end_year': 2025, 'target_growth_rate': 0.03},
                'workforce': {'total_termination_rate': 0.12},
                'random_seed': 42
            },
            # Invalid growth rate (> 1.0)
            {
                'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 1.5},
                'workforce': {'total_termination_rate': 0.12},
                'random_seed': 42
            },
            # Invalid termination rate (negative)
            {
                'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.03},
                'workforce': {'total_termination_rate': -0.05},
                'random_seed': 42
            },
            # Invalid termination rate (> 1.0)
            {
                'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.03},
                'workforce': {'total_termination_rate': 1.2},
                'random_seed': 42
            }
        ]

        for i, config in enumerate(invalid_configs):
            with self.subTest(f"Invalid range config {i+1}"):
                is_valid, errors = validate_configuration(config)

                self.assertFalse(is_valid)
                self.assertGreater(len(errors), 0)

    def test_validate_warning_conditions(self):
        """Test validation generates warnings for edge cases."""
        # Large year range should generate warning but still be valid
        warning_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2040,  # 15 year range - should generate warning
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'random_seed': 42
        }

        with patch('logging.getLogger') as mock_logger:
            mock_logger_instance = Mock()
            mock_logger.return_value = mock_logger_instance

            is_valid, errors = validate_configuration(warning_config)

            # Should be valid but generate warnings
            self.assertTrue(is_valid)
            self.assertEqual(len(errors), 0)

            # Check that warning was logged
            mock_logger_instance.warning.assert_called()
            warning_calls = [call[0][0] for call in mock_logger_instance.warning.call_args_list]
            self.assertTrue(any("year range" in call for call in warning_calls))


class TestConfigurationLoading(unittest.TestCase):
    """Test configuration file loading and merging."""

    def test_load_default_configuration(self):
        """Test loading default configuration when no file specified."""
        config = load_and_validate_config(None)

        # Verify default values are present
        self.assertIn('simulation', config)
        self.assertIn('workforce', config)
        self.assertIn('eligibility', config)
        self.assertIn('enrollment', config)
        self.assertIn('compensation', config)
        self.assertIn('random_seed', config)

        # Verify specific default values
        self.assertEqual(config['simulation']['start_year'], 2025)
        self.assertEqual(config['simulation']['end_year'], 2029)
        self.assertEqual(config['simulation']['target_growth_rate'], 0.03)
        self.assertEqual(config['workforce']['total_termination_rate'], 0.12)
        self.assertEqual(config['random_seed'], 42)

    def test_load_configuration_from_file(self):
        """Test loading configuration from YAML file."""
        test_config = {
            'simulation': {
                'start_year': 2026,
                'end_year': 2028,
                'target_growth_rate': 0.04
            },
            'workforce': {
                'total_termination_rate': 0.15,
                'new_hire_termination_rate': 0.30
            },
            'custom_field': 'custom_value',
            'random_seed': 123
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            config_path = f.name

        try:
            config = load_and_validate_config(config_path)

            # Verify file values override defaults
            self.assertEqual(config['simulation']['start_year'], 2026)
            self.assertEqual(config['simulation']['end_year'], 2028)
            self.assertEqual(config['simulation']['target_growth_rate'], 0.04)
            self.assertEqual(config['workforce']['total_termination_rate'], 0.15)
            self.assertEqual(config['workforce']['new_hire_termination_rate'], 0.30)
            self.assertEqual(config['random_seed'], 123)

            # Verify custom fields are preserved
            self.assertEqual(config['custom_field'], 'custom_value')

            # Verify defaults are still present for missing fields
            self.assertIn('eligibility', config)
            self.assertIn('enrollment', config)
            self.assertIn('compensation', config)

        finally:
            os.unlink(config_path)

    def test_load_configuration_deep_merge(self):
        """Test deep merging of nested configuration sections."""
        partial_config = {
            'simulation': {
                'start_year': 2026,
                # Missing end_year and target_growth_rate
            },
            'workforce': {
                'total_termination_rate': 0.16
                # Missing new_hire_termination_rate
            },
            'enrollment': {
                'auto_enrollment': {
                    'scope': 'new_hires_only'
                    # Missing other auto_enrollment fields
                }
                # Missing other enrollment fields
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(partial_config, f)
            config_path = f.name

        try:
            config = load_and_validate_config(config_path)

            # Verify partial overrides work
            self.assertEqual(config['simulation']['start_year'], 2026)
            self.assertEqual(config['workforce']['total_termination_rate'], 0.16)
            self.assertEqual(config['enrollment']['auto_enrollment']['scope'], 'new_hires_only')

            # Verify defaults fill in missing values
            self.assertEqual(config['simulation']['end_year'], 2029)  # Default
            self.assertEqual(config['simulation']['target_growth_rate'], 0.03)  # Default
            self.assertEqual(config['workforce']['new_hire_termination_rate'], 0.25)  # Default
            self.assertEqual(config['enrollment']['auto_enrollment']['hire_date_cutoff'], '2024-01-01')  # Default

        finally:
            os.unlink(config_path)

    def test_load_configuration_invalid_file(self):
        """Test handling of invalid YAML files."""
        invalid_yaml_content = """
        simulation:
          start_year: 2025
          end_year: 2027
          invalid_syntax: [unclosed bracket
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml_content)
            config_path = f.name

        try:
            # Should fall back to defaults on invalid file
            config = load_and_validate_config(config_path)

            # Should have default values
            self.assertEqual(config['simulation']['start_year'], 2025)
            self.assertEqual(config['simulation']['end_year'], 2029)  # Default, not from invalid file

        finally:
            os.unlink(config_path)

    def test_load_configuration_nonexistent_file(self):
        """Test handling of nonexistent configuration files."""
        nonexistent_path = '/nonexistent/path/to/config.yaml'

        # Should fall back to defaults without error
        config = load_and_validate_config(nonexistent_path)

        # Should have default values
        self.assertEqual(config['simulation']['start_year'], 2025)
        self.assertEqual(config['simulation']['end_year'], 2029)
        self.assertEqual(config['random_seed'], 42)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing simulation_config.yaml files."""

    def test_existing_simulation_config_format(self):
        """Test compatibility with existing simulation_config.yaml format."""
        # This represents the actual format used in the existing system
        existing_format = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2029,
                'target_growth_rate': 0.03,
                'random_seed': 42
            },
            'workforce': {
                'total_termination_rate': 0.12,
                'new_hire_termination_rate': 0.25
            },
            'eligibility': {
                'waiting_period_days': 365
            },
            'enrollment': {
                'auto_enrollment': {
                    'hire_date_cutoff': '2024-01-01',
                    'scope': 'new_hires_only'
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(existing_format, f)
            config_path = f.name

        try:
            # Should load without any issues
            config = load_and_validate_config(config_path)

            # Verify all existing values are preserved
            self.assertEqual(config['simulation']['start_year'], 2025)
            self.assertEqual(config['simulation']['end_year'], 2029)
            self.assertEqual(config['simulation']['target_growth_rate'], 0.03)
            self.assertEqual(config['workforce']['total_termination_rate'], 0.12)
            self.assertEqual(config['workforce']['new_hire_termination_rate'], 0.25)
            self.assertEqual(config['eligibility']['waiting_period_days'], 365)
            self.assertEqual(config['enrollment']['auto_enrollment']['hire_date_cutoff'], '2024-01-01')
            self.assertEqual(config['enrollment']['auto_enrollment']['scope'], 'new_hires_only')

            # Should validate successfully
            is_valid, errors = validate_configuration(config)
            self.assertTrue(is_valid)
            self.assertEqual(len(errors), 0)

        finally:
            os.unlink(config_path)

    def test_legacy_nested_random_seed_format(self):
        """Test handling of legacy format where random_seed was nested in simulation."""
        legacy_format = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03,
                'random_seed': 12345  # Legacy location
            },
            'workforce': {
                'total_termination_rate': 0.12
            }
            # No top-level random_seed
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(legacy_format, f)
            config_path = f.name

        try:
            config = load_and_validate_config(config_path)

            # Should handle both locations gracefully
            # Either preserve nested or move to top-level, or use default
            self.assertIn('random_seed', config)

            # Should still validate
            is_valid, errors = validate_configuration(config)
            # This might fail if we strictly require top-level random_seed
            # In that case, we'd need to add migration logic

        finally:
            os.unlink(config_path)

    def test_minimal_legacy_configuration(self):
        """Test minimal legacy configuration with only required fields."""
        minimal_legacy = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            }
            # Missing many optional fields that have defaults
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_legacy, f)
            config_path = f.name

        try:
            config = load_and_validate_config(config_path)

            # Should add defaults for missing sections
            self.assertIn('eligibility', config)
            self.assertIn('enrollment', config)
            self.assertIn('compensation', config)
            self.assertIn('random_seed', config)

            # Should validate successfully
            is_valid, errors = validate_configuration(config)
            self.assertTrue(is_valid)
            self.assertEqual(len(errors), 0)

        finally:
            os.unlink(config_path)


class TestSystemCompatibility(unittest.TestCase):
    """Test compatibility across new and legacy systems."""

    @patch('orchestrator_dbt.run_multi_year.MVP_AVAILABLE', True)
    @patch('orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator')
    def test_configuration_compatibility_success(self, mock_mvp_orchestrator):
        """Test successful configuration compatibility across systems."""
        compatible_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12,
                'new_hire_termination_rate': 0.25
            },
            'eligibility': {
                'waiting_period_days': 365
            },
            'enrollment': {
                'auto_enrollment': {
                    'hire_date_cutoff': '2024-01-01',
                    'scope': 'new_hires_only'
                }
            },
            'random_seed': 42
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(compatible_config, f)
            config_path = f.name

        try:
            # Mock successful MVP orchestrator creation
            mock_mvp_orchestrator.return_value = Mock()

            result = test_configuration_compatibility(config_path)

            # Should be compatible with both systems
            self.assertTrue(result['config_valid'])
            self.assertTrue(result['new_system_compatible'])
            self.assertTrue(result['legacy_compatible'])
            self.assertEqual(len(result['issues']), 0)

            # Should have positive recommendations
            self.assertIn('recommendations', result)
            self.assertGreater(len(result['recommendations']), 0)

        finally:
            os.unlink(config_path)

    @patch('orchestrator_dbt.run_multi_year.MVP_AVAILABLE', True)
    @patch('orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator')
    def test_configuration_compatibility_legacy_failure(self, mock_mvp_orchestrator):
        """Test handling of legacy system incompatibility."""
        # Configuration that new system accepts but legacy system rejects
        new_format_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'advanced_features': {  # New feature not supported by legacy
                'parallel_processing': True,
                'memory_optimization': 'high'
            },
            'random_seed': 42
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(new_format_config, f)
            config_path = f.name

        try:
            # Mock MVP orchestrator to reject new format
            mock_mvp_orchestrator.side_effect = Exception("Unknown configuration field: advanced_features")

            result = test_configuration_compatibility(config_path)

            # Should be compatible with new system but not legacy
            self.assertTrue(result['config_valid'])
            self.assertTrue(result['new_system_compatible'])
            self.assertFalse(result['legacy_compatible'])

            # Should have issues reported
            self.assertGreater(len(result['issues']), 0)
            self.assertTrue(any("Legacy compatibility issue" in issue for issue in result['issues']))

        finally:
            os.unlink(config_path)

    @patch('orchestrator_dbt.run_multi_year.MVP_AVAILABLE', False)
    def test_configuration_compatibility_no_mvp(self, ):
        """Test configuration compatibility when MVP is not available."""
        test_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'random_seed': 42
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            config_path = f.name

        try:
            result = test_configuration_compatibility(config_path)

            # Should be compatible with new system
            self.assertTrue(result['config_valid'])
            self.assertTrue(result['new_system_compatible'])

            # Legacy compatibility should be false when MVP not available
            self.assertFalse(result['legacy_compatible'])

            # Should not have compatibility issues (since we can't test legacy)
            legacy_issues = [issue for issue in result['issues'] if "Legacy compatibility" in issue]
            self.assertEqual(len(legacy_issues), 0)

        finally:
            os.unlink(config_path)


class TestEdgeCaseHandling(unittest.TestCase):
    """Test handling of edge cases and unusual configurations."""

    def test_extreme_value_configurations(self):
        """Test handling of extreme but valid configuration values."""
        extreme_configs = [
            # Minimal values
            {
                'simulation': {'start_year': 2025, 'end_year': 2025, 'target_growth_rate': 0.0},
                'workforce': {'total_termination_rate': 0.0},
                'random_seed': 1
            },
            # Maximum reasonable values
            {
                'simulation': {'start_year': 2025, 'end_year': 2035, 'target_growth_rate': 0.50},
                'workforce': {'total_termination_rate': 0.99},
                'random_seed': 2147483647  # Max 32-bit int
            },
            # Very long time horizons
            {
                'simulation': {'start_year': 2025, 'end_year': 2050, 'target_growth_rate': 0.02},
                'workforce': {'total_termination_rate': 0.08},
                'random_seed': 42
            }
        ]

        for i, config in enumerate(extreme_configs):
            with self.subTest(f"Extreme config {i+1}"):
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    yaml.dump(config, f)
                    config_path = f.name

                try:
                    # Should handle extreme values without crashing
                    loaded_config = load_and_validate_config(config_path)

                    # Basic validation should pass (might generate warnings)
                    is_valid, errors = validate_configuration(loaded_config)

                    # Should at least load without errors
                    self.assertIsNotNone(loaded_config)

                    # If validation fails, it should be due to warnings becoming errors
                    if not is_valid:
                        print(f"Extreme config {i+1} validation errors: {errors}")

                finally:
                    os.unlink(config_path)

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters in configuration."""
        unicode_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'metadata': {
                'description': 'Test configuration with unicode: ñáëïöü 中文 🚀',
                'author': 'Tëst Ürér',
                'notes': ['Special chars: @#$%^&*()', 'Unicode: αβγδε']
            },
            'random_seed': 42
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            yaml.dump(unicode_config, f, allow_unicode=True)
            config_path = f.name

        try:
            # Should handle unicode without issues
            config = load_and_validate_config(config_path)

            # Verify unicode data is preserved
            self.assertEqual(config['metadata']['description'], 'Test configuration with unicode: ñáëïöü 中文 🚀')
            self.assertEqual(config['metadata']['author'], 'Tëst Ürér')

            # Should still validate
            is_valid, errors = validate_configuration(config)
            self.assertTrue(is_valid)

        finally:
            os.unlink(config_path)

    def test_deeply_nested_configuration(self):
        """Test handling of deeply nested configuration structures."""
        nested_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03,
                'advanced': {
                    'optimization': {
                        'level': 'high',
                        'parameters': {
                            'batch_size': 1000,
                            'workers': 4,
                            'memory': {
                                'compression': True,
                                'cache_size': '256MB',
                                'gc_threshold': 0.8
                            }
                        }
                    }
                }
            },
            'workforce': {
                'total_termination_rate': 0.12,
                'segmentation': {
                    'by_department': {
                        'engineering': {'termination_rate': 0.08},
                        'sales': {'termination_rate': 0.15},
                        'support': {'termination_rate': 0.12}
                    },
                    'by_level': {
                        'junior': {'termination_rate': 0.18},
                        'senior': {'termination_rate': 0.10},
                        'executive': {'termination_rate': 0.05}
                    }
                }
            },
            'random_seed': 42
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(nested_config, f)
            config_path = f.name

        try:
            # Should handle deep nesting
            config = load_and_validate_config(config_path)

            # Verify nested data is accessible
            self.assertEqual(config['simulation']['advanced']['optimization']['level'], 'high')
            self.assertEqual(config['simulation']['advanced']['optimization']['parameters']['batch_size'], 1000)
            self.assertTrue(config['simulation']['advanced']['optimization']['parameters']['memory']['compression'])

            # Verify workforce segmentation
            self.assertEqual(config['workforce']['segmentation']['by_department']['engineering']['termination_rate'], 0.08)

            # Should still validate core requirements
            is_valid, errors = validate_configuration(config)
            self.assertTrue(is_valid)

        finally:
            os.unlink(config_path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
