"""
PlanWise Navigator - Core Business Logic Layer

This package contains the core business logic for PlanWise Navigator's workforce
simulation system. All modules in this package are independent of the Dagster
orchestration framework, enabling better testing, reusability, and maintainability.

Package Structure:
- dbt_utils: dbt command execution and project management utilities
- data_cleaning: Data preparation and quality validation functions
- simulation/: Simulation-specific business logic
  - validation: Simulation validation and testing functions
  - optimization: Optimization algorithms and parameter adjustment

Design Principles:
- Framework Independence: No direct Dagster dependencies
- Single Responsibility: Each module has a focused purpose
- Testability: Pure functions with clear inputs/outputs
- Reusability: Business logic can be used across different contexts

Version: 1.0.0 (Epic E028 - Modular Refactoring)
"""

__version__ = "1.0.0"
__author__ = "PlanWise Navigator Team"
