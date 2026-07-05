"""Integration tests for config serialization and deserialization roundtrip.

This module tests that configs survive the complete serialization cycle:
creation → serialization → archiving → deserialization
"""

from planalign_core.schema import SimulationConfig


class TestConfigSerializationRoundtrip:
    """Test complete serialization→deserialization cycle."""

    def test_config_roundtrip_with_model_dump_json(self):
        """Test that config survives serialization roundtrip with model_dump(mode='json').

        This is the core fix for US3: Decimals are converted to floats during
        serialization, preventing type errors during deserialization.
        """
        # Create original config with all fields
        original_config = SimulationConfig(
            start_year=2025,
            end_year=2026,
            random_seed=42,
            target_growth_rate=0.03,
            total_termination_rate=0.12,
            new_hire_termination_rate=0.25,
            cola_rate=0.025,
            merit_budget_pct=0.04,
            promotion_increase_pct=0.15,
        )

        # Serialize using model_dump(mode='json') - converts Decimals/complex types to JSON-safe
        serialized_dict = original_config.model_dump(mode="json")

        # Verify serialized dict contains JSON-safe types
        assert isinstance(serialized_dict["start_year"], int)
        assert isinstance(serialized_dict["cola_rate"], float)

        # Deserialize using from_dict() - should succeed without type errors
        reconstructed_config = SimulationConfig.from_dict(serialized_dict)

        # Verify reconstructed config matches original
        assert reconstructed_config.start_year == original_config.start_year
        assert reconstructed_config.end_year == original_config.end_year
        assert reconstructed_config.random_seed == original_config.random_seed
        assert reconstructed_config.cola_rate == original_config.cola_rate
        assert reconstructed_config.merit_budget_pct == original_config.merit_budget_pct

    def test_config_roundtrip_with_scenario_overrides(self):
        """Test roundtrip with scenario-specific overrides (Studio merge).

        Simulates the realistic case where Studio merges scenario overrides
        with base config before archiving.
        """
        # Original config
        original_config = SimulationConfig(
            start_year=2025,
            end_year=2026,
            target_growth_rate=0.03,
        )

        # Serialize original
        serialized = original_config.model_dump(mode="json")

        # Simulate Studio scenario override
        scenario_override = {
            "target_growth_rate": 0.05,  # Override value
            "random_seed": 123,
            "scenario_name": "high_growth",  # Extra field from Studio
            "ui_settings": {"key": "value"},  # Extra field from Studio
        }

        # Merge (simulating result_handlers.py config merging)
        merged = {**serialized, **scenario_override}

        # Deserialize with from_dict() - should handle extra keys and overrides
        reconstructed = SimulationConfig.from_dict(merged)

        # Original values preserved
        assert reconstructed.start_year == 2025
        assert reconstructed.end_year == 2026

        # Override applied
        assert reconstructed.target_growth_rate == 0.05
        assert reconstructed.random_seed == 123

        # Extra keys filtered silently
        assert not hasattr(reconstructed, "scenario_name")
        assert not hasattr(reconstructed, "ui_settings")

    def test_model_dump_json_vs_model_dump(self):
        """Test the difference between model_dump() and model_dump(mode='json').

        Demonstrates why model_dump(mode='json') is necessary for serialization.
        """
        config = SimulationConfig(
            start_year=2025,
            end_year=2026,
            cola_rate=0.025,
        )

        # Standard model_dump()
        standard_dump = config.model_dump()
        # Should contain types suitable for Python (may include Decimal, date, etc.)
        assert isinstance(standard_dump, dict)

        # JSON mode model_dump()
        json_dump = config.model_dump(mode="json")
        # Should contain only JSON-serializable types
        assert isinstance(json_dump, dict)
        assert all(
            isinstance(v, (int, float, str, bool, type(None), list, dict))
            for v in json_dump.values()
            if v is not None
        )

    def test_roundtrip_preserves_field_types_and_values(self):
        """Test that all field types and values are preserved through roundtrip."""
        config = SimulationConfig(
            start_year=2024,
            end_year=2028,
            random_seed=999,
            target_growth_rate=0.015,
            total_termination_rate=0.10,
            new_hire_termination_rate=0.20,
            promotion_budget_pct=0.10,
            promotion_level_caps={1: 0.25, 2: 0.15},
            cola_rate=0.02,
            merit_budget_pct=0.03,
            promotion_increase_pct=0.10,
        )

        # Roundtrip
        serialized = config.model_dump(mode="json")
        reconstructed = SimulationConfig.from_dict(serialized)

        # All scalar fields preserved
        assert reconstructed.start_year == 2024
        assert reconstructed.end_year == 2028
        assert reconstructed.random_seed == 999
        assert reconstructed.target_growth_rate == 0.015
        assert reconstructed.total_termination_rate == 0.10
        assert reconstructed.new_hire_termination_rate == 0.20
        assert reconstructed.promotion_budget_pct == 0.10
        assert reconstructed.cola_rate == 0.02
        assert reconstructed.merit_budget_pct == 0.03
        assert reconstructed.promotion_increase_pct == 0.10

        # Complex field (dict) preserved
        assert reconstructed.promotion_level_caps == {1: 0.25, 2: 0.15}

    def test_roundtrip_with_default_values(self):
        """Test that default values are preserved when not explicitly set."""
        # Create config with minimal required fields
        config = SimulationConfig(
            start_year=2025,
            end_year=2026,
            # All other fields use defaults
        )

        # Roundtrip
        serialized = config.model_dump(mode="json")
        reconstructed = SimulationConfig.from_dict(serialized)

        # Default values preserved
        assert reconstructed.random_seed == 42
        assert reconstructed.target_growth_rate == 0.03
        assert reconstructed.total_termination_rate == 0.12
        assert reconstructed.new_hire_termination_rate == 0.25
        assert reconstructed.promotion_budget_pct == 0.15
        assert reconstructed.cola_rate == 0.025
        assert reconstructed.merit_budget_pct == 0.04
        assert reconstructed.promotion_increase_pct == 0.15

    def test_archiver_archivee_simulation_context(self):
        """Test realistic archiver scenario: save and restore config.

        Simulates the complete flow:
        1. Run completes
        2. Archiver saves config with model_dump(mode='json')
        3. Result handler loads and deserializes config
        """
        # Create config for a simulation
        simulation_config = SimulationConfig(
            start_year=2025,
            end_year=2027,
            target_growth_rate=0.04,
        )

        # Simulate archiver: serialize config for storage
        archived_config_dict = simulation_config.model_dump(mode="json")

        # Simulate result handler: load archived config
        loaded_config = SimulationConfig.from_dict(archived_config_dict)

        # Verify loaded config matches original
        assert loaded_config.start_year == 2025
        assert loaded_config.end_year == 2027
        assert loaded_config.target_growth_rate == 0.04
