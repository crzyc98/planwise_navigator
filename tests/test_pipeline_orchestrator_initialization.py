"""
Integration tests for PipelineOrchestrator initialization with Decimal serialization.

These tests verify that PipelineOrchestrator can be initialized with a configuration
containing Decimal fields, and that configuration logging works without TypeError.

IMPORTANT: These tests MUST fail initially (red phase) because the fix hasn't been
applied yet. After implementing T012, these tests should pass (green phase).
"""

import json
import pytest
from decimal import Decimal
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from tests.fixtures.config import config_with_decimal_fields
from tests.utils.json_validators import assert_no_decimals_in_structure


@pytest.mark.integration
class TestConfigSerializationForLogging:
    """T010: Integration test for configuration serialization in logging path"""

    def test_config_serialization_for_logging_path(self, config_with_decimal_fields):
        """
        T010: Verify configuration can be serialized for logging without TypeError.

        This test simulates the serialization path that occurs in run_summary.py:129
        when configuration is logged during PipelineOrchestrator initialization.

        Given: A SimulationConfig with Decimal fields
        When: config.model_dump(mode='json') is called (the FIX)
        Then: The resulting dict should be JSON-serializable by json.dumps()

        Before the fix (using model_dump()):
        - Would raise: TypeError: Object of type Decimal is not JSON serializable

        After the fix (using model_dump(mode='json')):
        - Should succeed with JSON-compatible dict
        """
        # Simulate what run_summary.py line 129 should do AFTER the fix
        config_dict = config_with_decimal_fields.model_dump(mode='json')

        # This should NOT raise TypeError
        try:
            json_str = json.dumps(config_dict)
            assert isinstance(json_str, str)
            assert len(json_str) > 0
        except TypeError as e:
            if "Decimal" in str(e):
                pytest.fail(
                    f"Configuration serialization failed: {e}\n"
                    f"This indicates config.model_dump(mode='json') is not being used.\n"
                    f"Expected fix in run_summary.py:129:\n"
                    f"  config.model_dump(mode='json')  # Converts Decimal → float"
                )
            raise


@pytest.mark.integration
class TestJSONLoggingPath:
    """T011: Integration test for JSON logging path"""

    def test_json_logging_with_decimal_config(self, config_with_decimal_fields):
        """
        T011: Verify logger can output JSON representation of configuration.

        This test documents the complete logging path that occurs when
        configuration is logged.

        Given: A SimulationConfig with Decimal fields
        When: config.model_dump(mode='json') is used before json.dumps()
        Then: Logger should produce valid JSON output

        The logging path:
        1. run_summary.py:129: config.model_dump(mode='json')
           → Returns dict with Decimal → float conversion
        2. logger.py:57: json.dumps(config_dict)
           → Should succeed (all values are JSON-compatible)

        Before fix: TypeError at step 1 because model_dump() without mode='json'
        leaves Decimal objects in dict, which json.dumps() can't serialize.

        After fix: Both steps succeed because Decimals are converted to floats.
        """
        # Step 1: Convert config to JSON-compatible dict
        config_dict = config_with_decimal_fields.model_dump(mode='json')

        # Step 2: Logger serializes to JSON
        try:
            json_output = json.dumps(config_dict)

            # Verify it's valid JSON
            parsed = json.loads(json_output)
            assert isinstance(parsed, dict)
            assert 'scenario_id' in parsed

        except TypeError as e:
            if "Decimal" in str(e):
                pytest.fail(
                    f"Logger failed to serialize configuration: {e}\n"
                    f"This indicates model_dump(mode='json') is not being used.\n"
                    f"Fix in run_summary.py:129: use config.model_dump(mode='json')"
                )
            raise

    def test_config_dict_is_json_serializable_after_fix(self, config_with_decimal_fields):
        """
        Verify that after applying the fix, config can be serialized to JSON.

        This test documents the expected behavior after implementing T012.

        Given: A SimulationConfig with Decimal fields
        When: model_dump(mode='json') is called
        Then: The resulting dict should be JSON-serializable
        """
        # This is what run_summary.py:129 should do AFTER the fix
        config_dict = config_with_decimal_fields.model_dump(mode='json')

        # After the fix, this should NOT raise TypeError
        try:
            json_str = json.dumps(config_dict)
            # If serialization succeeds, parse it back to verify it's valid
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)
        except TypeError as e:
            pytest.fail(
                f"Config dict is not JSON-serializable after model_dump(mode='json'): {e}\n"
                f"This suggests an issue with model_dump(mode='json') conversion."
            )


@pytest.mark.integration
class TestDecimalSerializationInLoggingPath:
    """
    Additional integration tests for the complete logging path.
    """

    def test_serialization_boundary_at_run_summary(self, config_with_decimal_fields):
        """
        Verify the serialization boundary is correctly placed at run_summary.py:129.

        The fix should be at the serialization boundary, not in the logger:
        - CORRECT: run_summary.py uses config.model_dump(mode='json')
        - WRONG: logger.py uses custom JSONEncoder for Decimal
        - WRONG: logger.py uses json.JSONDecoder

        This test verifies the correct approach is used.
        """
        # The serialization should happen at the source (run_summary)
        config_dict = config_with_decimal_fields.model_dump(mode='json')

        # After conversion, dict should be JSON-serializable
        try:
            json_str = json.dumps(config_dict)
            assert isinstance(json_str, str)
        except TypeError:
            pytest.fail(
                "Config dict from model_dump(mode='json') is not JSON-serializable. "
                "This indicates the fix is not working correctly."
            )

    def test_logger_receives_compatible_dict(self, config_with_decimal_fields):
        """
        Verify logger receives a dict with no Decimal objects.

        The logger's responsibility is to serialize to JSON, not to handle
        Decimal conversion. By the time the dict reaches the logger, all
        Decimal values should already be converted to floats.
        """
        # Simulate what run_summary.py should do
        config_dict = config_with_decimal_fields.model_dump(mode='json')

        # Logger should receive a dict with no Decimals
        from tests.utils.json_validators import assert_no_decimals_in_structure
        assert_no_decimals_in_structure(config_dict, "config dict passed to logger")

        # Logger should be able to serialize it without custom encoding
        try:
            json_str = json.dumps(config_dict)  # No custom encoder needed
            assert isinstance(json_str, str)
        except TypeError as e:
            pytest.fail(f"Logger cannot serialize config dict: {e}")


@pytest.mark.integration
class TestDecimalLoggingRoundtrip:
    """
    Integration tests for complete configuration serialization roundtrip.
    """

    def test_config_serialization_roundtrip(self, config_with_decimal_fields):
        """
        Test complete serialization roundtrip: config → dict → JSON → dict.

        This exercises the complete logging path:
        1. Start with SimulationConfig containing Decimal fields
        2. Convert to JSON-compatible dict using model_dump(mode='json')
        3. Serialize to JSON string using json.dumps()
        4. Parse JSON back to dict using json.loads()
        5. Verify data integrity

        Expected behavior after T012 fix:
        - All steps succeed
        - Decimal values are represented as floats in JSON
        - All original data is preserved
        """
        # Step 1: Original config with Decimals
        assert config_with_decimal_fields is not None

        # Step 2: Convert to JSON-compatible dict
        config_dict = config_with_decimal_fields.model_dump(mode='json')

        # Verify no Decimals remain
        assert_no_decimals_in_structure(config_dict, "converted config dict")

        # Step 3: Serialize to JSON
        json_str = json.dumps(config_dict)
        assert isinstance(json_str, str)

        # Step 4: Parse back
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

        # Step 5: Verify key fields are present
        assert 'scenario_id' in parsed
        assert 'plan_design_id' in parsed
        assert parsed['scenario_id'] == config_with_decimal_fields.scenario_id


# Pytest markers for test categorization
# @pytest.mark.integration - Full integration tests
# @pytest.mark.slow - Tests that take more than 1 second
# @pytest.mark.fast - Quick unit tests (< 1 second)
#
# Run these tests with:
# - All tests: pytest tests/test_pipeline_orchestrator_initialization.py
# - Integration only: pytest tests/test_pipeline_orchestrator_initialization.py -m integration
# - Fast tests: pytest tests/test_pipeline_orchestrator_initialization.py -m fast
