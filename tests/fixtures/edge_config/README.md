# Edge-case fixture conventions

Each CSV preserves the production census columns and adds only `boundary_group`,
which is harness metadata. Every declared catalog group must have at least one
row. YAML files use the existing `SimulationConfig` shape and state the override
that makes the boundary observable. Fixture populations stay small and contain
stable employee IDs; no runtime DuckDB or census output belongs in this folder.

Small does not mean smaller than the boundary. A rate-driven boundary -- growth
solving, a percentage dial -- needs a population large enough that the rate
resolves to whole employees, or the case passes without ever reaching the
behaviour it names (#498, #499). Confirm the flows the case depends on are
non-zero, and assert that they are, so the case cannot silently go trivial
later.
