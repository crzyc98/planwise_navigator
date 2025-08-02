"""
CLI Package for Multi-Year Simulation Orchestration

Command-line interface for running multi-year workforce simulations using the
optimized orchestrator_dbt package. Provides easy access to high-performance
simulation capabilities with 82% performance improvement over baseline.

Available Commands:
- run_multi_year: Main CLI for multi-year simulations
- foundation_test: Test foundation setup performance
- mvp_compare: Compare performance with existing MVP orchestrator

Usage:
    python -m orchestrator_dbt.cli.run_multi_year --help
"""

__version__ = "1.0.0"
__author__ = "PlanWise Navigator Team"

# CLI entry points
from .run_multi_year import main as run_multi_year_main

__all__ = [
    "run_multi_year_main"
]
