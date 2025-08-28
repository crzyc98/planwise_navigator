#!/usr/bin/env python3
"""
Memory Monitor CLI Tool

Story S063-08: Command-line interface for monitoring and analyzing
adaptive memory management in PlanWise Navigator simulations.

Usage:
    python scripts/memory_monitor_cli.py --help
    python scripts/memory_monitor_cli.py monitor --config config/simulation_config.yaml
    python scripts/memory_monitor_cli.py analyze reports/memory/memory_profile_*.json
    python scripts/memory_monitor_cli.py recommendations --config config/simulation_config.yaml
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from navigator_orchestrator.adaptive_memory_manager import (
    AdaptiveConfig,
    create_adaptive_memory_manager,
    MemoryPressureLevel,
    OptimizationLevel
)
from navigator_orchestrator.config import load_simulation_config
from navigator_orchestrator.logger import ProductionLogger


def setup_logging() -> ProductionLogger:
    """Setup logging for CLI operations"""
    return ProductionLogger("MemoryMonitorCLI")


def load_adaptive_config(config_path: Path) -> AdaptiveConfig:
    """Load adaptive memory configuration from simulation config"""
    try:
        sim_config = load_simulation_config(config_path)

        # Extract adaptive memory config if present
        if hasattr(sim_config, 'optimization') and sim_config.optimization:
            opt_config = sim_config.optimization
            if hasattr(opt_config, 'adaptive_memory'):
                adaptive_config = opt_config.adaptive_memory

                from navigator_orchestrator.adaptive_memory_manager import MemoryThresholds, BatchSizeConfig

                return AdaptiveConfig(
                    enabled=adaptive_config.enabled,
                    monitoring_interval_seconds=adaptive_config.monitoring_interval_seconds,
                    history_size=adaptive_config.history_size,
                    thresholds=MemoryThresholds(
                        moderate_mb=adaptive_config.thresholds.moderate_mb,
                        high_mb=adaptive_config.thresholds.high_mb,
                        critical_mb=adaptive_config.thresholds.critical_mb,
                        gc_trigger_mb=adaptive_config.thresholds.gc_trigger_mb,
                        fallback_trigger_mb=adaptive_config.thresholds.fallback_trigger_mb
                    ),
                    batch_sizes=BatchSizeConfig(
                        low=adaptive_config.batch_sizes.low,
                        medium=adaptive_config.batch_sizes.medium,
                        high=adaptive_config.batch_sizes.high,
                        fallback=adaptive_config.batch_sizes.fallback
                    ),
                    auto_gc_enabled=adaptive_config.auto_gc_enabled,
                    fallback_enabled=adaptive_config.fallback_enabled,
                    profiling_enabled=adaptive_config.profiling_enabled,
                    recommendation_window_minutes=adaptive_config.recommendation_window_minutes,
                    min_samples_for_recommendation=adaptive_config.min_samples_for_recommendation,
                    leak_detection_enabled=adaptive_config.leak_detection_enabled,
                    leak_threshold_mb=adaptive_config.leak_threshold_mb,
                    leak_window_minutes=adaptive_config.leak_window_minutes
                )

        # Return default config if not found
        return AdaptiveConfig()

    except Exception as e:
        print(f"Warning: Failed to load adaptive config: {e}")
        return AdaptiveConfig()


def monitor_command(args) -> int:
    """Real-time memory monitoring command"""
    logger = setup_logging()

    print("🧠 PlanWise Navigator - Adaptive Memory Monitor")
    print("=" * 60)

    try:
        # Load configuration
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Configuration file not found: {config_path}")
            return 1

        adaptive_config = load_adaptive_config(config_path)

        # Create memory manager
        memory_manager = create_adaptive_memory_manager(
            optimization_level=OptimizationLevel.MEDIUM,
            memory_limit_gb=args.memory_limit,
        )

        print(f"Configuration loaded from: {config_path}")
        print(f"Memory limit: {args.memory_limit}GB")
        print(f"Monitoring interval: {adaptive_config.monitoring_interval_seconds}s")
        print(f"History size: {adaptive_config.history_size} samples")
        print()

        # Display thresholds
        thresholds = adaptive_config.thresholds
        print("Memory Pressure Thresholds:")
        print(f"  Moderate: {thresholds.moderate_mb:.0f}MB")
        print(f"  High:     {thresholds.high_mb:.0f}MB")
        print(f"  Critical: {thresholds.critical_mb:.0f}MB")
        print(f"  GC Trigger: {thresholds.gc_trigger_mb:.0f}MB")
        print(f"  Fallback:   {thresholds.fallback_trigger_mb:.0f}MB")
        print()

        # Start monitoring
        print("Starting real-time memory monitoring...")
        print("Press Ctrl+C to stop")
        print()
        print("Time     | Memory | Pressure | Batch | GC | Recommendations")
        print("-" * 65)

        with memory_manager:
            try:
                iteration = 0
                while True:
                    snapshot = memory_manager.force_memory_check("cli_monitor")
                    stats = memory_manager.get_memory_statistics()
                    recommendations = memory_manager.get_recommendations(recent_only=True)

                    # Format timestamp
                    timestamp = snapshot.timestamp.strftime("%H:%M:%S")

                    # Format pressure level with color coding
                    pressure_color = {
                        MemoryPressureLevel.LOW: "🟢",
                        MemoryPressureLevel.MODERATE: "🟡",
                        MemoryPressureLevel.HIGH: "🟠",
                        MemoryPressureLevel.CRITICAL: "🔴"
                    }.get(snapshot.pressure_level, "⚪")

                    pressure_display = f"{pressure_color} {snapshot.pressure_level.value:8s}"

                    # Format display
                    rec_count = len(recommendations)
                    rec_display = f"{rec_count} new" if rec_count > 0 else ""

                    print(f"{timestamp} | {snapshot.rss_mb:6.1f}MB | {pressure_display} | "
                          f"{snapshot.batch_size:4d} | {stats['stats'].get('total_gc_collections', 0):2d} | {rec_display}")

                    # Show recent recommendations
                    if rec_count > 0 and iteration % 5 == 0:  # Show every 5 iterations when there are recommendations
                        print("  Recent recommendations:")
                        for rec in recommendations[-2:]:  # Show last 2
                            print(f"    • {rec['type']}: {rec['description'][:50]}...")

                    iteration += 1
                    time.sleep(args.interval)

            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")

                # Final statistics
                final_stats = memory_manager.get_memory_statistics()
                print("\nFinal Statistics:")
                print(f"  Peak Memory: {final_stats['trends']['peak_memory_mb']:.1f}MB")
                print(f"  GC Collections: {final_stats['stats']['total_gc_collections']}")
                print(f"  Batch Adjustments: {final_stats['stats']['batch_size_adjustments']}")
                print(f"  Fallback Events: {final_stats['stats']['automatic_fallbacks']}")

                # Export profile
                if args.export:
                    profile_path = memory_manager.export_memory_profile()
                    print(f"  Memory profile exported: {profile_path}")

                return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def analyze_command(args) -> int:
    """Analyze memory profile files"""
    logger = setup_logging()

    print("🧠 PlanWise Navigator - Memory Profile Analysis")
    print("=" * 60)

    try:
        profile_files = []

        # Collect profile files
        for pattern in args.profiles:
            path = Path(pattern)
            if path.is_file():
                profile_files.append(path)
            elif path.is_dir():
                # Find all JSON files in directory
                profile_files.extend(path.glob("memory_profile_*.json"))
            else:
                # Try as glob pattern
                profile_files.extend(Path(".").glob(pattern))

        if not profile_files:
            print("Error: No memory profile files found")
            return 1

        print(f"Analyzing {len(profile_files)} profile file(s)...")
        print()

        # Analyze each profile
        for profile_path in sorted(profile_files):
            print(f"Profile: {profile_path.name}")
            print("-" * 40)

            try:
                with open(profile_path) as f:
                    profile_data = json.load(f)

                # Extract key metrics
                metadata = profile_data.get("metadata", {})
                statistics = profile_data.get("statistics", {})
                history = profile_data.get("history", [])
                recommendations = profile_data.get("recommendations", [])

                # Display summary
                export_time = metadata.get("export_time", "Unknown")
                print(f"  Export Time: {export_time}")
                print(f"  History Samples: {len(history)}")
                print(f"  Recommendations: {len(recommendations)}")

                if statistics:
                    current = statistics.get("current", {})
                    trends = statistics.get("trends", {})
                    stats = statistics.get("stats", {})

                    print(f"  Final Memory: {current.get('memory_mb', 'N/A')}MB")
                    print(f"  Peak Memory: {trends.get('peak_memory_mb', 'N/A')}MB")
                    print(f"  Average Memory: {trends.get('avg_memory_mb', 'N/A')}MB")
                    print(f"  GC Collections: {stats.get('total_gc_collections', 0)}")
                    print(f"  Batch Adjustments: {stats.get('batch_size_adjustments', 0)}")
                    print(f"  Fallback Events: {stats.get('automatic_fallbacks', 0)}")

                # Show memory trend
                if len(history) > 1:
                    start_memory = history[0].get("rss_mb", 0)
                    end_memory = history[-1].get("rss_mb", 0)
                    memory_trend = end_memory - start_memory
                    trend_symbol = "📈" if memory_trend > 0 else "📉" if memory_trend < 0 else "➡️"
                    print(f"  Memory Trend: {trend_symbol} {memory_trend:+.1f}MB")

                # Show top recommendations by priority
                if recommendations:
                    print("  Top Recommendations:")
                    high_priority = [r for r in recommendations if r.get("priority") == "high"]
                    medium_priority = [r for r in recommendations if r.get("priority") == "medium"]

                    for rec in (high_priority + medium_priority)[:3]:
                        priority_symbol = "🔴" if rec.get("priority") == "high" else "🟡"
                        print(f"    {priority_symbol} {rec.get('type', 'unknown')}: {rec.get('description', '')[:60]}...")

                print()

            except Exception as e:
                print(f"  Error reading profile: {e}")
                print()
                continue

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def recommendations_command(args) -> int:
    """Generate optimization recommendations"""
    logger = setup_logging()

    print("🧠 PlanWise Navigator - Memory Optimization Recommendations")
    print("=" * 60)

    try:
        # Load configuration
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Configuration file not found: {config_path}")
            return 1

        adaptive_config = load_adaptive_config(config_path)

        # Analyze current configuration
        print("Current Configuration Analysis:")
        print("-" * 30)

        thresholds = adaptive_config.thresholds
        batch_sizes = adaptive_config.batch_sizes

        # Check for potential issues
        issues = []
        recommendations = []

        # Memory threshold analysis
        if thresholds.critical_mb <= thresholds.high_mb:
            issues.append("Critical threshold should be higher than high threshold")

        if thresholds.gc_trigger_mb >= thresholds.high_mb:
            issues.append("GC trigger should be below high threshold for proactive collection")

        if thresholds.moderate_mb < 1000:
            recommendations.append({
                "type": "threshold_adjustment",
                "priority": "medium",
                "description": f"Moderate threshold ({thresholds.moderate_mb}MB) may be too low for modern workloads",
                "action": "Consider increasing to at least 1500MB"
            })

        # Batch size analysis
        if batch_sizes.high > 2000:
            recommendations.append({
                "type": "batch_size_adjustment",
                "priority": "medium",
                "description": f"High batch size ({batch_sizes.high}) may cause memory spikes",
                "action": "Consider reducing to 1000-1500 for single-threaded workloads"
            })

        if batch_sizes.fallback < 50:
            recommendations.append({
                "type": "fallback_adjustment",
                "priority": "low",
                "description": f"Fallback batch size ({batch_sizes.fallback}) may be too small",
                "action": "Consider increasing to 100-200 for better performance"
            })

        # Feature analysis
        if not adaptive_config.auto_gc_enabled:
            recommendations.append({
                "type": "feature_recommendation",
                "priority": "high",
                "description": "Automatic garbage collection is disabled",
                "action": "Enable auto_gc_enabled for better memory management"
            })

        if not adaptive_config.fallback_enabled:
            recommendations.append({
                "type": "feature_recommendation",
                "priority": "medium",
                "description": "Automatic fallback is disabled",
                "action": "Enable fallback_enabled for critical memory situations"
            })

        # System analysis
        import psutil
        system_memory = psutil.virtual_memory()
        total_gb = system_memory.total / (1024**3)
        available_gb = system_memory.available / (1024**3)

        print(f"System Memory: {total_gb:.1f}GB total, {available_gb:.1f}GB available")
        print(f"Memory Usage: {system_memory.percent:.1f}%")
        print()

        # Memory limit recommendations based on system
        if total_gb < 8:
            recommendations.append({
                "type": "system_optimization",
                "priority": "high",
                "description": f"System has limited memory ({total_gb:.1f}GB)",
                "action": "Consider using lower thresholds and enabling aggressive fallback"
            })

        # Display issues
        if issues:
            print("Configuration Issues:")
            for issue in issues:
                print(f"  🔴 {issue}")
            print()

        # Display recommendations
        if recommendations:
            print("Optimization Recommendations:")

            # Group by priority
            high_priority = [r for r in recommendations if r["priority"] == "high"]
            medium_priority = [r for r in recommendations if r["priority"] == "medium"]
            low_priority = [r for r in recommendations if r["priority"] == "low"]

            for priority, recs in [("High Priority", high_priority),
                                 ("Medium Priority", medium_priority),
                                 ("Low Priority", low_priority)]:
                if recs:
                    print(f"\n{priority}:")
                    for rec in recs:
                        priority_symbol = {"high": "🔴", "medium": "🟡", "low": "🟢"}[rec["priority"]]
                        print(f"  {priority_symbol} {rec['type']}")
                        print(f"    Issue: {rec['description']}")
                        print(f"    Action: {rec['action']}")
                        print()
        else:
            print("✅ No optimization recommendations - configuration looks good!")

        # Suggested configuration
        if recommendations or issues:
            print("Suggested Configuration Updates:")
            print("-" * 30)

            # Generate optimized config based on system
            if total_gb <= 4:
                # Work laptop optimization
                print("# Optimized for 4GB work laptops")
                print("optimization:")
                print("  adaptive_memory:")
                print("    thresholds:")
                print("      moderate_mb: 1500.0")
                print("      high_mb: 2500.0")
                print("      critical_mb: 3000.0")
                print("      gc_trigger_mb: 2000.0")
                print("      fallback_trigger_mb: 2800.0")
                print("    batch_sizes:")
                print("      low: 200")
                print("      medium: 400")
                print("      high: 800")
                print("      fallback: 100")
                print("    auto_gc_enabled: true")
                print("    fallback_enabled: true")
            elif total_gb <= 8:
                # Standard laptop optimization
                print("# Optimized for 8GB systems")
                print("optimization:")
                print("  adaptive_memory:")
                print("    thresholds:")
                print("      moderate_mb: 2000.0")
                print("      high_mb: 4000.0")
                print("      critical_mb: 5500.0")
                print("      gc_trigger_mb: 3000.0")
                print("      fallback_trigger_mb: 5000.0")
            else:
                print("# Optimized for high-memory systems")
                print("optimization:")
                print("  adaptive_memory:")
                print("    thresholds:")
                print("      moderate_mb: 3000.0")
                print("      high_mb: 6000.0")
                print("      critical_mb: 8000.0")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Memory Monitor CLI for PlanWise Navigator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Real-time monitoring
  python scripts/memory_monitor_cli.py monitor --config config/simulation_config.yaml

  # Analyze saved profiles
  python scripts/memory_monitor_cli.py analyze reports/memory/memory_profile_*.json

  # Get configuration recommendations
  python scripts/memory_monitor_cli.py recommendations --config config/simulation_config.yaml
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Real-time memory monitoring')
    monitor_parser.add_argument(
        '--config', '-c',
        type=str,
        default='config/simulation_config.yaml',
        help='Path to simulation configuration file'
    )
    monitor_parser.add_argument(
        '--interval', '-i',
        type=float,
        default=1.0,
        help='Monitoring interval in seconds (default: 1.0)'
    )
    monitor_parser.add_argument(
        '--memory-limit',
        type=float,
        default=4.0,
        help='Memory limit in GB for threshold calculation (default: 4.0)'
    )
    monitor_parser.add_argument(
        '--export',
        action='store_true',
        help='Export memory profile on exit'
    )

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze memory profile files')
    analyze_parser.add_argument(
        'profiles',
        nargs='+',
        help='Memory profile files or patterns to analyze'
    )

    # Recommendations command
    rec_parser = subparsers.add_parser('recommendations', help='Generate optimization recommendations')
    rec_parser.add_argument(
        '--config', '-c',
        type=str,
        default='config/simulation_config.yaml',
        help='Path to simulation configuration file'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    if args.command == 'monitor':
        return monitor_command(args)
    elif args.command == 'analyze':
        return analyze_command(args)
    elif args.command == 'recommendations':
        return recommendations_command(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
