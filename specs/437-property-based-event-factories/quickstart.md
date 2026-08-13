# Quickstart: Validate Property-Based Event Factory Contracts

**Feature**: 437-property-based-event-factories
**Date**: 2026-08-12

## Prerequisites

- Python 3.11 environment already created at `.venv`
- Project development dependencies installed from `.[dev]`
- Run commands from the repository root

These are pure unit tests. They do not open DuckDB and do not require or modify `dbt/simulation.duckdb`; an isolated database run is therefore not applicable.

## 1. Run the new properties

```bash
source .venv/bin/activate
pytest tests/unit/events/test_event_factory_properties.py -q --hypothesis-show-statistics
```

Expected outcome:

- Every generated-valid factory case round-trips unchanged.
- Decimal, date, rejection, and JSON contract properties pass.
- Hypothesis reports no property above 100 generated examples.
- The focused workforce regression proves sub-quantum positive compensation is rejected before an invalid normalized event can be returned.

## 2. Run the complete event unit selection

```bash
source .venv/bin/activate
pytest -m "fast and events" tests/unit/events -q
```

Expected outcome:

- Existing example tests and the new property tests pass together.
- Tests are selected automatically through the `unit`, `fast`, and `events` markers.
- No database fixture is created.

Measured on 2026-08-12:

- Before implementation: 68 existing event tests in approximately 1 second.
- After implementation: 162 event tests in 10.39 seconds (11.15 seconds wall time), with every open-ended property capped at 100 examples; the finite leap-day domain exhausted after 25 examples.
- Issue 437 therefore adds 94 collected checks and approximately 9.4 seconds of pytest time to the focused event loop while retaining every example-based test.

The repository-wide `fast` suite is already documented as a multi-minute suite, so issue 437 is responsible for bounded incremental cost rather than repairing that inherited constitution drift.

The final repository-wide check collected 2,344 fast tests (plus 796 deselected) and passed in 282.54 seconds, or 283.71 seconds wall time. The approximately 9.4-second focused event-suite increment remains bounded within that inherited multi-minute baseline.

## 3. Check style and dependency metadata

```bash
source .venv/bin/activate
ruff check tests/fixtures/event_factory_strategies.py tests/unit/events/test_event_factory_properties.py
uv lock --check
```

Expected outcome:

- Both new modules pass Ruff.
- The lockfile agrees with `pyproject.toml` after Hypothesis moves to the development extra.
- `hypothesis` is absent from runtime dependencies/`requirements.txt` and present in the `dev` extra/`requirements-dev.txt`.

## 4. Review the guarded wire shape

Compare property metadata with [contracts/event-serialization.md](contracts/event-serialization.md). The implementation is complete only when all nine factory payload key sets and JSON type families are represented exactly once in the shared cases.

## Failure Interpretation

- A native round-trip failure indicates a Pydantic envelope or payload reconstruction defect.
- A Decimal failure indicates float coercion, bounds drift, or a six-place/four-place scale regression.
- A date failure indicates incorrect factory effective-date mapping or a lifecycle strategy/ordering defect.
- A rejection failure indicates that malformed data constructed an event instead of raising `ValidationError`.
- A serialization failure indicates an audit-ingestion contract change that requires explicit review, not an automatic snapshot update.

If a property exposes an explicit contract violation in production code, first preserve the minimized Hypothesis counterexample as a focused example test, then make the smallest validator/factory correction and rerun all commands above.
