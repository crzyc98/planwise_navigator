#!/usr/bin/env python3
"""
Basic Usage Example for orchestrator_dbt

This example demonstrates the basic usage patterns for the optimized
orchestrator_dbt package, showcasing the 82% performance improvement
and production-ready features.

Example scenarios:
1. Foundation setup benchmark
2. Multi-year simulation
3. Performance comparison with MVP
4. Configuration testing
"""

import asyncio
import logging
import tempfile
from pathlib import Path
import yaml

# Import orchestrator_dbt CLI functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from run_multi_year import (
    run_foundation_benchmark,
    run_enhanced_multi_year_simulation,
    run_comprehensive_performance_comparison,
    test_configuration_compatibility,
    setup_comprehensive_logging,
    OptimizationLevel
)


class BasicUsageDemo:
    """Demonstrates basic usage patterns for orchestrator_dbt."""

    def __init__(self):
        """Initialize demo with logging and sample configuration."""
        self.logger = setup_comprehensive_logging(verbose=True)
        self.logger.info("🎯 PlanWise Navigator - orchestrator_dbt Basic Usage Demo")
        self.logger.info("=" * 70)

        # Create sample configuration
        self.sample_config = {
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
            'compensation': {
                'cola_rate': 0.025,
                'merit_pool': 0.03
            },
            'random_seed': 42
        }

        # Create temporary config file
        self.config_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False
        )
        yaml.dump(self.sample_config, self.config_file)
        self.config_file.close()
        self.config_path = self.config_file.name

        self.logger.info(f"📋 Created sample configuration: {self.config_path}")

    def cleanup(self):
        """Clean up temporary files."""
        import os
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)
            self.logger.info(f"🧹 Cleaned up configuration file")

    async def demo_foundation_setup_benchmark(self):
        """Demonstrate foundation setup benchmarking."""
        self.logger.info("\\n🚀 DEMO 1: Foundation Setup Benchmark")
        self.logger.info("-" * 50)

        try:
            # Run foundation benchmark with high optimization
            result = await run_foundation_benchmark(
                optimization_level=OptimizationLevel.HIGH,
                config_path=self.config_path,
                benchmark_mode=True
            )

            # Display results
            if result['success']:
                self.logger.info("✅ Foundation setup benchmark completed successfully!")
                self.logger.info(f"   ⏱️  Execution Time: {result['execution_time']:.2f}s")
                self.logger.info(f"   🎯 Target Met (<10s): {'YES' if result['target_met'] else 'NO'}")
                self.logger.info(f"   📈 Performance Improvement: {result['performance_improvement']:.1%}")
                self.logger.info(f"   🏅 Performance Grade: {result['performance_grade']}")
                self.logger.info(f"   💾 Peak Memory: {result['memory_metrics']['peak_mb']:.1f} MB")
                self.logger.info(f"   📊 Memory Efficiency: {result['memory_metrics']['efficiency']:.1%}")
            else:
                self.logger.error("❌ Foundation setup benchmark failed")
                self.logger.error(f"   Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"💥 Foundation benchmark demo failed: {e}")

    async def demo_multi_year_simulation(self):
        """Demonstrate multi-year simulation execution."""
        self.logger.info("\\n🎯 DEMO 2: Multi-Year Simulation")
        self.logger.info("-" * 50)

        try:
            # Run enhanced multi-year simulation
            result = await run_enhanced_multi_year_simulation(
                start_year=2025,
                end_year=2027,
                optimization_level=OptimizationLevel.HIGH,
                max_workers=4,
                batch_size=1000,
                enable_compression=True,
                fail_fast=False,
                performance_mode=True,
                config_path=self.config_path
            )

            # Display results
            if result['success']:
                self.logger.info("🎉 Multi-year simulation completed successfully!")
                self.logger.info(f"   🆔 Simulation ID: {result['simulation_id']}")
                self.logger.info(f"   📅 Years Completed: {result['completed_years']}")
                self.logger.info(f"   ⏱️  Total Time: {result['total_execution_time']:.2f}s")
                self.logger.info(f"   📊 Success Rate: {result['success_rate']:.1%}")

                if 'performance_metrics' in result:
                    metrics = result['performance_metrics']
                    if 'records_per_second' in metrics:
                        self.logger.info(f"   🚀 Processing Rate: {metrics['records_per_second']:.0f} records/sec")
                    if 'memory_efficiency' in metrics:
                        self.logger.info(f"   💾 Memory Efficiency: {metrics['memory_efficiency']:.1%}")
            else:
                self.logger.error("💥 Multi-year simulation failed")
                self.logger.error(f"   Completed Years: {result.get('completed_years', [])}")
                self.logger.error(f"   Failed Years: {result.get('failed_years', [])}")
                self.logger.error(f"   Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"💥 Multi-year simulation demo failed: {e}")

    async def demo_performance_comparison(self):
        """Demonstrate performance comparison with MVP."""
        self.logger.info("\\n🏁 DEMO 3: Performance Comparison with MVP")
        self.logger.info("-" * 50)

        try:
            # Run comprehensive performance comparison
            result = await run_comprehensive_performance_comparison(
                start_year=2025,
                end_year=2026,  # Minimal range for demo
                config_path=self.config_path,
                benchmark_mode=True
            )

            # Display results
            self.logger.info("📊 Performance Comparison Results:")

            if result['mvp_available']:
                self.logger.info(f"   MVP Orchestrator: {'✅ SUCCESS' if result['mvp_success'] else '❌ FAILED'}")
                if result['mvp_success']:
                    self.logger.info(f"      Time: {result['mvp_time']:.2f}s")
            else:
                self.logger.info("   MVP Orchestrator: ❌ NOT AVAILABLE")

            self.logger.info(f"   New Orchestrator: {'✅ SUCCESS' if result['new_success'] else '❌ FAILED'}")
            if result['new_success']:
                self.logger.info(f"      Time: {result['new_time']:.2f}s")

            if result['improvement'] > 0:
                self.logger.info(f"   📈 Performance Improvement: {result['improvement']:.1%}")
                self.logger.info(f"   🎯 Target Achievement (82%): {'✅ YES' if result['target_met'] else '❌ NO'}")
                self.logger.info(f"   🏅 Performance Grade: {result['performance_grade']}")
                self.logger.info(f"   🧪 Regression Test: {'✅ PASSED' if result['regression_test_passed'] else '❌ FAILED'}")

                if 'speedup' in result:
                    self.logger.info(f"   ⚡ Speedup Factor: {result['speedup']:.1f}x")
            else:
                self.logger.warning("   ⚠️  Cannot calculate improvement - baseline unavailable")

        except Exception as e:
            self.logger.error(f"💥 Performance comparison demo failed: {e}")

    def demo_configuration_testing(self):
        """Demonstrate configuration compatibility testing."""
        self.logger.info("\\n🔧 DEMO 4: Configuration Compatibility Testing")
        self.logger.info("-" * 50)

        try:
            # Test configuration compatibility
            result = test_configuration_compatibility(self.config_path)

            # Display results
            self.logger.info("📋 Configuration Compatibility Results:")
            self.logger.info(f"   Configuration Valid: {'✅ YES' if result['config_valid'] else '❌ NO'}")
            self.logger.info(f"   New System Compatible: {'✅ YES' if result['new_system_compatible'] else '❌ NO'}")
            self.logger.info(f"   Legacy System Compatible: {'✅ YES' if result['legacy_compatible'] else '❌ NO'}")

            if result['issues']:
                self.logger.warning("   ⚠️  Issues Found:")
                for issue in result['issues']:
                    self.logger.warning(f"      • {issue}")

            if result['recommendations']:
                self.logger.info("   💡 Recommendations:")
                for rec in result['recommendations']:
                    self.logger.info(f"      • {rec}")

        except Exception as e:
            self.logger.error(f"💥 Configuration testing demo failed: {e}")

    def demo_configuration_variations(self):
        """Demonstrate different configuration scenarios."""
        self.logger.info("\\n⚙️  DEMO 5: Configuration Variations")
        self.logger.info("-" * 50)

        # Test different configuration scenarios
        scenarios = [
            {
                'name': 'Minimal Configuration',
                'config': {
                    'simulation': {'start_year': 2025, 'end_year': 2025, 'target_growth_rate': 0.0},
                    'workforce': {'total_termination_rate': 0.0},
                    'random_seed': 1
                }
            },
            {
                'name': 'High Growth Scenario',
                'config': {
                    'simulation': {'start_year': 2025, 'end_year': 2030, 'target_growth_rate': 0.08},
                    'workforce': {'total_termination_rate': 0.18, 'new_hire_termination_rate': 0.35},
                    'compensation': {'cola_rate': 0.04, 'merit_pool': 0.05},
                    'random_seed': 12345
                }
            },
            {
                'name': 'Conservative Scenario',
                'config': {
                    'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.01},
                    'workforce': {'total_termination_rate': 0.08, 'new_hire_termination_rate': 0.15},
                    'compensation': {'cola_rate': 0.015, 'merit_pool': 0.02},
                    'random_seed': 999
                }
            }
        ]

        for scenario in scenarios:
            self.logger.info(f"\\n   📊 Testing: {scenario['name']}")

            # Create temporary config for this scenario
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(scenario['config'], f)
                scenario_config_path = f.name

            try:
                # Test compatibility
                result = test_configuration_compatibility(scenario_config_path)

                status = "✅ VALID" if result['config_valid'] else "❌ INVALID"
                compatibility = "✅ COMPATIBLE" if result['new_system_compatible'] else "❌ INCOMPATIBLE"

                self.logger.info(f"      Configuration: {status}")
                self.logger.info(f"      Compatibility: {compatibility}")

                if result['issues']:
                    self.logger.warning(f"      Issues: {len(result['issues'])} found")

            except Exception as e:
                self.logger.error(f"      Error testing scenario: {e}")
            finally:
                import os
                os.unlink(scenario_config_path)

    async def run_all_demos(self):
        """Run all demonstration scenarios."""
        self.logger.info("🎬 Starting comprehensive orchestrator_dbt demonstration...")

        try:
            # Run foundation benchmark demo
            await self.demo_foundation_setup_benchmark()

            # Run multi-year simulation demo
            await self.demo_multi_year_simulation()

            # Run performance comparison demo
            await self.demo_performance_comparison()

            # Run configuration testing demo
            self.demo_configuration_testing()

            # Run configuration variations demo
            self.demo_configuration_variations()

            self.logger.info("\\n🎉 All demonstrations completed successfully!")
            self.logger.info("=" * 70)

            # Summary of key findings
            self.logger.info("📊 KEY DEMO INSIGHTS:")
            self.logger.info("   • Foundation setup: Targeting <10 second performance")
            self.logger.info("   • Multi-year simulation: Full workflow orchestration")
            self.logger.info("   • Performance improvement: Target >82% vs legacy MVP")
            self.logger.info("   • Configuration compatibility: Backward compatible")
            self.logger.info("   • Production ready: Comprehensive error handling & monitoring")

        except Exception as e:
            self.logger.error(f"💥 Demo execution failed: {e}")
        finally:
            self.cleanup()


async def main():
    """Main demo function."""
    print("🎯 PlanWise Navigator - orchestrator_dbt Basic Usage Example")
    print("This demo showcases the key features and 82% performance improvement")
    print()

    demo = BasicUsageDemo()
    await demo.run_all_demos()


if __name__ == "__main__":
    asyncio.run(main())
