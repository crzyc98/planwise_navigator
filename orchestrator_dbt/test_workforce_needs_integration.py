#!/usr/bin/env python3
"""
Test script for workforce needs integration MVP.

This script tests the integration of dbt workforce needs models
with the orchestrator_dbt multi-year simulation pipeline.
"""

import sys
import logging
from pathlib import Path

# Add orchestrator_dbt to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import OrchestrationConfig
from core.database_manager import DatabaseManager
from core.dbt_executor import DbtExecutor
from core.workforce_needs_interface import DbtWorkforceNeedsInterface
from simulation.workforce_calculator import WorkforceCalculator
from simulation.event_generator import BatchEventGenerator

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_workforce_needs_interface():
    """Test basic workforce needs interface functionality."""
    logger.info("🧪 Testing DbtWorkforceNeedsInterface...")

    try:
        # Initialize components
        config = OrchestrationConfig()
        db_manager = DatabaseManager(config)
        dbt_executor = DbtExecutor(config)

        # Create workforce needs interface
        workforce_needs_interface = DbtWorkforceNeedsInterface(config, db_manager, dbt_executor)

        # Test validation
        is_valid = workforce_needs_interface.validate_workforce_needs_models(2025, "default")
        logger.info(f"Model validation result: {is_valid}")

        if is_valid:
            # Test getting workforce requirements
            requirements = workforce_needs_interface.get_workforce_requirements(2025, "default")
            if requirements:
                logger.info(f"✅ Successfully retrieved workforce requirements: {requirements.total_hires_needed} hires needed")

                # Test getting level breakdown
                level_breakdown = workforce_needs_interface.get_level_breakdown(2025, "default")
                logger.info(f"✅ Successfully retrieved level breakdown: {len(level_breakdown)} levels")

                return True
            else:
                logger.warning("❌ No workforce requirements found")
                return False
        else:
            logger.warning("❌ Model validation failed")
            return False

    except Exception as e:
        logger.error(f"❌ Workforce needs interface test failed: {e}")
        return False


def test_workforce_calculator_integration():
    """Test workforce calculator with dbt integration."""
    logger.info("🧪 Testing WorkforceCalculator with dbt integration...")

    try:
        # Initialize components
        config = OrchestrationConfig()
        db_manager = DatabaseManager(config)
        dbt_executor = DbtExecutor(config)

        # Create workforce calculator
        workforce_calculator = WorkforceCalculator(db_manager, config, dbt_executor)

        # Test workforce requirements calculation
        requirements = workforce_calculator.calculate_workforce_requirements(
            simulation_year=2025,
            custom_parameters={
                'scenario_id': 'default',
                'target_growth_rate': 0.03,
                'total_termination_rate': 0.12,
                'new_hire_termination_rate': 0.25
            }
        )

        logger.info(f"✅ Workforce requirements calculated: "
                   f"Current workforce: {requirements.current_workforce}, "
                   f"Hires needed: {requirements.total_hires_needed}, "
                   f"Terminations: {requirements.experienced_terminations}")

        # Check if requirements are using dbt models (should have 'dbt_models' in formula_details)
        using_dbt = 'dbt_models' in str(requirements.formula_details.get('source', ''))
        logger.info(f"Using dbt models: {using_dbt}")

        return True

    except Exception as e:
        logger.error(f"❌ Workforce calculator test failed: {e}")
        return False


def test_event_generator_integration():
    """Test event generator with dbt workforce needs."""
    logger.info("🧪 Testing BatchEventGenerator with dbt integration...")

    try:
        # Initialize components
        config = OrchestrationConfig()
        db_manager = DatabaseManager(config)
        dbt_executor = DbtExecutor(config)

        # Create event generator
        event_generator = BatchEventGenerator(db_manager, config, dbt_executor)

        # Test workforce requirements (mock for this test)
        mock_workforce_requirements = {
            'experienced_terminations': 120,
            'total_hires_needed': 150,
            'expected_new_hire_terminations': 37,
            'new_hire_termination_rate': 0.25
        }

        # Generate events
        logger.info("Generating events with dbt integration...")
        metrics = event_generator.generate_all_events(
            simulation_year=2025,
            workforce_requirements=mock_workforce_requirements,
            random_seed=42,
            scenario_id="default"
        )

        logger.info(f"✅ Event generation completed: "
                   f"Total events: {metrics.total_events}, "
                   f"Hire events: {metrics.hire_events}, "
                   f"Termination events: {metrics.termination_events}, "
                   f"Generation time: {metrics.generation_time:.2f}s")

        return True

    except Exception as e:
        logger.error(f"❌ Event generator test failed: {e}")
        return False


def test_end_to_end_integration():
    """Test complete end-to-end integration."""
    logger.info("🧪 Testing end-to-end dbt workforce needs integration...")

    try:
        # Initialize components
        config = OrchestrationConfig()
        db_manager = DatabaseManager(config)
        dbt_executor = DbtExecutor(config)

        # Create workforce needs interface
        workforce_needs_interface = DbtWorkforceNeedsInterface(config, db_manager, dbt_executor)

        # Step 1: Execute workforce needs models
        logger.info("Step 1: Executing dbt workforce needs models...")
        execution_success = workforce_needs_interface.execute_workforce_needs_models(2025, "default")

        if not execution_success:
            logger.warning("❌ dbt model execution failed")
            return False

        # Step 2: Get workforce requirements
        logger.info("Step 2: Getting workforce requirements...")
        requirements = workforce_needs_interface.get_workforce_requirements(2025, "default")

        if not requirements:
            logger.warning("❌ No workforce requirements found")
            return False

        # Step 3: Get level breakdown
        logger.info("Step 3: Getting level breakdown...")
        level_breakdown = workforce_needs_interface.get_level_breakdown(2025, "default")

        # Step 4: Generate events using requirements
        logger.info("Step 4: Generating events using dbt requirements...")
        event_generator = BatchEventGenerator(db_manager, config, dbt_executor)

        workforce_dict = {
            'experienced_terminations': requirements.expected_experienced_terminations,
            'total_hires_needed': requirements.total_hires_needed,
            'expected_new_hire_terminations': requirements.expected_new_hire_terminations,
            'new_hire_termination_rate': requirements.new_hire_termination_rate
        }

        metrics = event_generator.generate_all_events(
            simulation_year=2025,
            workforce_requirements=workforce_dict,
            random_seed=42,
            scenario_id="default"
        )

        # Step 5: Validate results
        logger.info("Step 5: Validating results...")
        total_expected_hires = sum(level_req.hires_needed for level_req in level_breakdown)
        actual_hires = metrics.hire_events

        logger.info(f"Expected hires (from dbt): {total_expected_hires}")
        logger.info(f"Actual hires generated: {actual_hires}")
        logger.info(f"Expected terminations (from dbt): {requirements.expected_experienced_terminations}")
        logger.info(f"Actual terminations generated: {metrics.termination_events}")

        # Check if numbers match within reasonable tolerance
        hire_variance = abs(total_expected_hires - actual_hires)
        hire_tolerance = max(1, total_expected_hires * 0.05)  # 5% tolerance

        if hire_variance <= hire_tolerance:
            logger.info("✅ End-to-end integration test passed!")
            logger.info(f"📊 Integration Summary:")
            logger.info(f"   - dbt models executed successfully")
            logger.info(f"   - Workforce requirements retrieved: {requirements.total_hires_needed} hires")
            logger.info(f"   - Level breakdown retrieved: {len(level_breakdown)} levels")
            logger.info(f"   - Events generated: {metrics.total_events} total")
            logger.info(f"   - Event generation time: {metrics.generation_time:.2f}s")
            logger.info(f"   - Performance: {metrics.events_per_second:.0f} events/sec")
            return True
        else:
            logger.warning(f"❌ Hire count mismatch: expected {total_expected_hires}, got {actual_hires}")
            return False

    except Exception as e:
        logger.error(f"❌ End-to-end integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    logger.info("🚀 Starting workforce needs integration tests...")

    tests = [
        ("Workforce Needs Interface", test_workforce_needs_interface),
        ("Workforce Calculator Integration", test_workforce_calculator_integration),
        ("Event Generator Integration", test_event_generator_integration),
        ("End-to-End Integration", test_end_to_end_integration),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*60}")

        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name} PASSED")
            else:
                logger.warning(f"❌ {test_name} FAILED")
        except Exception as e:
            logger.error(f"💥 {test_name} CRASHED: {e}")
            results.append((test_name, False))

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*60}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {test_name}")

    logger.info(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All integration tests passed! dbt workforce needs integration is working.")
        return 0
    else:
        logger.warning(f"⚠️  {total - passed} test(s) failed. Check logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
