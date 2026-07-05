"""Core domain package for Fidelity PlanAlign Engine.

Holds domain code shared across the orchestrator, CLI, and API:
event models (planalign_core.events), simulation config schema,
constants, and network configuration. Moved out of the top-level
config/ directory (issue #390) so config/ holds only YAML settings.
"""
