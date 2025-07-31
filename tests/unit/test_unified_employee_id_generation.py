#!/usr/bin/env python3
"""
Test suite for unified employee ID generation functionality.

Validates that the new UnifiedIDGenerator produces consistent, reproducible results
across multiple runs while maintaining uniqueness within reasonable simulation parameters.
Tests both baseline employee IDs and new hire employee IDs.
"""

import pytest
from orchestrator_mvp.core.id_generator import (
    UnifiedIDGenerator,
    validate_employee_id_batch_uniqueness,
    create_id_generator_from_config
)


class TestUnifiedEmployeeIdGeneration:
    """Test suite for unified employee ID generation."""

    def test_baseline_employee_deterministic_generation(self):
        """Test that same inputs produce identical baseline employee IDs."""
        # Test parameters
        base_year = 2024
        sequence = 1
        random_seed = 42

        # Create multiple generators with same parameters
        gen1 = UnifiedIDGenerator(random_seed, base_year)
        gen2 = UnifiedIDGenerator(random_seed, base_year)
        gen3 = UnifiedIDGenerator(random_seed, base_year)

        # Generate IDs with same parameters
        id1 = gen1.generate_employee_id(sequence, is_baseline=True)
        id2 = gen2.generate_employee_id(sequence, is_baseline=True)
        id3 = gen3.generate_employee_id(sequence, is_baseline=True)

        # All should be identical
        assert id1 == id2 == id3

        # Verify baseline format: EMP_YYYY_NNNNNN
        assert id1.startswith('EMP_2024_')
        assert len(id1) == 15  # EMP_2024_000001
        assert id1.endswith('_000001')

    def test_new_hire_deterministic_generation(self):
        """Test that same inputs produce identical new hire employee IDs."""
        # Test parameters
        hire_year = 2025
        sequence = 1
        random_seed = 42

        # Create multiple generators with same parameters
        gen1 = UnifiedIDGenerator(random_seed, hire_year)
        gen2 = UnifiedIDGenerator(random_seed, hire_year)
        gen3 = UnifiedIDGenerator(random_seed, hire_year)

        # Generate new hire IDs with same parameters
        id1 = gen1.generate_employee_id(sequence, is_baseline=False, hire_year=hire_year)
        id2 = gen2.generate_employee_id(sequence, is_baseline=False, hire_year=hire_year)
        id3 = gen3.generate_employee_id(sequence, is_baseline=False, hire_year=hire_year)

        # All should be identical
        assert id1 == id2 == id3

        # Verify new hire format: NH_YYYY_XXXXXXXX_NNNNNN
        assert id1.startswith('NH_2025_')
        assert len(id1) == 23  # NH_2025_XXXXXXXX_000001
        assert id1.endswith('_000001')

    def test_different_seeds_produce_different_ids(self):
        """Test that different seeds produce different employee IDs."""
        hire_year = 2025
        sequence = 1

        # Create generators with different seeds
        gen_42 = UnifiedIDGenerator(42, hire_year)
        gen_123 = UnifiedIDGenerator(123, hire_year)
        gen_999 = UnifiedIDGenerator(999, hire_year)

        # Generate new hire IDs with different seeds
        id_seed_42 = gen_42.generate_employee_id(sequence, is_baseline=False, hire_year=hire_year)
        id_seed_123 = gen_123.generate_employee_id(sequence, is_baseline=False, hire_year=hire_year)
        id_seed_999 = gen_999.generate_employee_id(sequence, is_baseline=False, hire_year=hire_year)

        # All should be different
        assert id_seed_42 != id_seed_123
        assert id_seed_42 != id_seed_999
        assert id_seed_123 != id_seed_999

        # But all should have same format structure
        for emp_id in [id_seed_42, id_seed_123, id_seed_999]:
            assert emp_id.startswith('NH_2025_')
            assert emp_id.endswith('_000001')
            assert len(emp_id) == 23

    def test_different_years_produce_different_ids(self):
        """Test that different years produce different employee IDs."""
        sequence = 1
        random_seed = 42

        # Generate IDs for different years
        gen_2025 = UnifiedIDGenerator(random_seed, 2025)
        gen_2026 = UnifiedIDGenerator(random_seed, 2026)
        gen_2027 = UnifiedIDGenerator(random_seed, 2027)

        id_2025 = gen_2025.generate_employee_id(sequence, is_baseline=False, hire_year=2025)
        id_2026 = gen_2026.generate_employee_id(sequence, is_baseline=False, hire_year=2026)
        id_2027 = gen_2027.generate_employee_id(sequence, is_baseline=False, hire_year=2027)

        # All should be different
        assert id_2025 != id_2026
        assert id_2025 != id_2027
        assert id_2026 != id_2027

        # Verify year in ID
        assert id_2025.startswith('NH_2025_')
        assert id_2026.startswith('NH_2026_')
        assert id_2027.startswith('NH_2027_')

    def test_different_sequences_produce_different_ids(self):
        """Test that different sequence numbers produce different employee IDs."""
        hire_year = 2025
        random_seed = 42

        # Generate IDs for different sequence numbers
        generator = UnifiedIDGenerator(random_seed, hire_year)
        id_seq_1 = generator.generate_employee_id(1, is_baseline=False, hire_year=hire_year)

        # Reset generator to avoid duplicate tracking
        generator.reset_generation_tracking()
        id_seq_100 = generator.generate_employee_id(100, is_baseline=False, hire_year=hire_year)

        generator.reset_generation_tracking()
        id_seq_999 = generator.generate_employee_id(999, is_baseline=False, hire_year=hire_year)

        # All should be different
        assert id_seq_1 != id_seq_100
        assert id_seq_1 != id_seq_999
        assert id_seq_100 != id_seq_999

        # Verify sequence numbers in ID
        assert id_seq_1.endswith('_000001')
        assert id_seq_100.endswith('_000100')
        assert id_seq_999.endswith('_000999')

    def test_baseline_vs_new_hire_format_differences(self):
        """Test that baseline and new hire IDs have different but consistent formats."""
        year = 2025
        sequence = 1
        random_seed = 42

        generator = UnifiedIDGenerator(random_seed, year)

        # Generate both types
        baseline_id = generator.generate_employee_id(sequence, is_baseline=True)
        generator.reset_generation_tracking()
        new_hire_id = generator.generate_employee_id(sequence, is_baseline=False, hire_year=year)

        # Should be different
        assert baseline_id != new_hire_id

        # Verify format differences
        assert baseline_id.startswith('EMP_')
        assert new_hire_id.startswith('NH_')
        assert len(baseline_id) == 15  # EMP_YYYY_NNNNNN
        assert len(new_hire_id) == 23  # NH_YYYY_XXXXXXXX_NNNNNN

    def test_uniqueness_within_realistic_simulation(self):
        """Test that IDs remain unique within a realistic simulation size."""
        hire_year = 2025
        random_seed = 42
        num_hires = 1000  # Realistic number of hires for one year

        generator = UnifiedIDGenerator(random_seed, hire_year)

        # Generate many employee IDs
        generated_ids = []
        for i in range(1, num_hires + 1):
            emp_id = generator.generate_employee_id(i, is_baseline=False, hire_year=hire_year)
            generated_ids.append(emp_id)

        # Verify all are unique
        unique_ids = set(generated_ids)
        assert len(generated_ids) == len(unique_ids), f"Expected {len(generated_ids)} unique IDs, got {len(unique_ids)}"

        # Verify all have correct format
        for emp_id in generated_ids:
            assert emp_id.startswith('NH_2025_')
            assert len(emp_id) == 23

    def test_batch_generation(self):
        """Test batch ID generation functionality."""
        hire_year = 2025
        random_seed = 42
        start_sequence = 1
        count = 100

        generator = UnifiedIDGenerator(random_seed, hire_year)

        # Generate batch of new hire IDs
        batch_ids = generator.generate_batch_employee_ids(
            start_sequence=start_sequence,
            count=count,
            is_baseline=False,
            hire_year=hire_year
        )

        # Verify batch properties
        assert len(batch_ids) == count
        assert all(emp_id.startswith('NH_2025_') for emp_id in batch_ids)
        assert len(set(batch_ids)) == count  # All unique

        # Verify sequence numbers are correct
        for i, emp_id in enumerate(batch_ids):
            expected_seq = f'{start_sequence + i:06d}'
            assert emp_id.endswith(f'_{expected_seq}')

    def test_input_validation(self):
        """Test that invalid inputs raise appropriate errors."""
        # Test invalid years in constructor
        with pytest.raises(ValueError, match="Invalid year"):
            generator = UnifiedIDGenerator(42, 2019)  # Too early
            generator.generate_employee_id(1, is_baseline=True)

        with pytest.raises(ValueError, match="Invalid year"):
            generator = UnifiedIDGenerator(42, 2051)  # Too late
            generator.generate_employee_id(1, is_baseline=True)

        # Test invalid sequence numbers
        generator = UnifiedIDGenerator(42, 2025)
        with pytest.raises(ValueError, match="Invalid sequence"):
            generator.generate_employee_id(0, is_baseline=True)  # Too low

        with pytest.raises(ValueError, match="Invalid sequence"):
            generator.generate_employee_id(1000000, is_baseline=True)  # Too high

    def test_format_validation_methods(self):
        """Test the ID format validation helper methods."""
        generator = UnifiedIDGenerator(42, 2025)

        # Generate test IDs
        baseline_id = generator.generate_employee_id(1, is_baseline=True)
        generator.reset_generation_tracking()
        new_hire_id = generator.generate_employee_id(1, is_baseline=False, hire_year=2025)

        # Test format validation
        assert generator.validate_employee_id_format(baseline_id)
        assert generator.validate_employee_id_format(new_hire_id)
        assert not generator.validate_employee_id_format("INVALID_ID")

        # Test type detection
        assert generator.is_baseline_employee(baseline_id)
        assert not generator.is_baseline_employee(new_hire_id)
        assert generator.is_new_hire_employee(new_hire_id)
        assert not generator.is_new_hire_employee(baseline_id)

        # Test year extraction
        assert generator.extract_year_from_id(baseline_id) == 2025
        assert generator.extract_year_from_id(new_hire_id) == 2025
        assert generator.extract_year_from_id("INVALID_ID") is None

        # Test sequence extraction
        assert generator.extract_sequence_from_id(baseline_id) == 1
        assert generator.extract_sequence_from_id(new_hire_id) == 1
        assert generator.extract_sequence_from_id("INVALID_ID") is None

    def test_generation_stats(self):
        """Test generation statistics tracking."""
        generator = UnifiedIDGenerator(42, 2025)

        # Generate some IDs
        generator.generate_employee_id(1, is_baseline=True)
        generator.reset_generation_tracking()
        generator.generate_employee_id(1, is_baseline=False, hire_year=2025)
        generator.reset_generation_tracking()
        generator.generate_employee_id(2, is_baseline=True)

        # Get stats (only last ID tracked due to resets)
        stats = generator.get_generation_stats()
        assert stats['total_generated'] == 1
        assert stats['baseline_count'] == 1
        assert stats['new_hire_count'] == 0
        assert stats['random_seed'] == 42
        assert stats['base_year'] == 2025

    def test_config_factory_function(self):
        """Test creating generator from configuration."""
        config = {
            'random_seed': 123,
            'base_year': 2024
        }

        generator = create_id_generator_from_config(config)

        # Test that generator works with config
        emp_id = generator.generate_employee_id(1, is_baseline=True)
        assert emp_id.startswith('EMP_2024_')
        assert generator.random_seed == 123
        assert generator.base_year == 2024


class TestEmployeeIdBatchValidation:
    """Test suite for batch employee ID validation."""

    def test_validation_passes_with_unique_ids(self):
        """Test that validation passes when all IDs are unique."""
        employee_ids = [
            'EMP_2024_000001',
            'NH_2025_abc12345_000002',
            'EMP_2024_000003'
        ]

        # Should not raise any exception
        validate_employee_id_batch_uniqueness(employee_ids)

    def test_validation_fails_with_duplicate_ids(self):
        """Test that validation fails when duplicate IDs are found."""
        employee_ids = [
            'EMP_2024_000001',
            'NH_2025_abc12345_000002',
            'EMP_2024_000001'  # Duplicate
        ]

        with pytest.raises(ValueError, match="Duplicate employee IDs found"):
            validate_employee_id_batch_uniqueness(employee_ids)

    def test_validation_handles_empty_list(self):
        """Test that validation handles empty lists gracefully."""
        validate_employee_id_batch_uniqueness([])

    def test_cross_format_uniqueness(self):
        """Test that validation works across different ID formats."""
        # Generate IDs with different generators to ensure no conflicts
        gen_baseline = UnifiedIDGenerator(42, 2024)
        gen_new_hire = UnifiedIDGenerator(42, 2025)

        baseline_ids = gen_baseline.generate_batch_employee_ids(1, 10, is_baseline=True)
        new_hire_ids = gen_new_hire.generate_batch_employee_ids(1, 10, is_baseline=False, hire_year=2025)

        # Combine and validate
        all_ids = baseline_ids + new_hire_ids
        validate_employee_id_batch_uniqueness(all_ids)  # Should pass


if __name__ == "__main__":
    # Run tests if called directly
    pytest.main([__file__, "-v"])
