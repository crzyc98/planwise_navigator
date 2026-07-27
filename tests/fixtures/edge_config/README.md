# Edge-case fixture conventions

Each CSV preserves the production census columns and adds only `boundary_group`,
which is harness metadata. Every declared catalog group must have at least one
row. YAML files use the existing `SimulationConfig` shape and state the override
that makes the boundary observable. Fixture populations stay small and contain
stable employee IDs; no runtime DuckDB or census output belongs in this folder.
