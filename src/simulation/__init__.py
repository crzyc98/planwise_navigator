"""
PlanWise Navigator - Simulation Business Logic Package

This package contains the core simulation business logic for workforce modeling,
validation, and optimization. All modules in this package are independent of the
Dagster orchestration framework.

Modules:
- validation: Simulation validation and testing functions
- optimization: Optimization algorithms and parameter adjustment logic

Design Principles:
- Pure Business Logic: No orchestration framework dependencies
- Domain-Focused: Simulation-specific functionality only
- Testable: Clear inputs/outputs with minimal side effects
- Reusable: Can be imported and used in different contexts

Version: 1.0.0 (Epic E028 - Modular Refactoring)
"""

__version__ = "1.0.0"
