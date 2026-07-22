"""Batched-failure attribution (Feature 121, FR-012) — deferred integration scaffold.

Goal: prove that when a model fails *inside a batched dbt selection*, the surfaced
error still names the failing **model**, **stage**, and **year**.

Tier A's hazard-cache batch is already covered at the unit level in
``tests/unit/test_hazard_cache_batching.py::test_batched_failure_still_names_failing_model``
(a failed batched build routes through ``_build_rebuild_error`` +
``extract_dbt_failure_detail``, which reads per-node ``run_results.json`` and names
the failing model).

This module is the integration home for the same guarantee once Tiers B and C add
their own batched selections (T021, and the STATE_ACCUMULATION collapse). Each case
injects a deliberately broken model into an isolated DB build and asserts the
attribution. They are skipped until wired to an isolated-DB fixture so CI stays green.
"""

import pytest


@pytest.mark.skip(
    reason="Tier A attribution covered by unit test; B/C cases pending isolated-DB fixture."
)
def test_batched_hazard_failure_names_model():
    """Placeholder — Tier A covered in test_hazard_cache_batching.py (unit)."""


@pytest.mark.skip(
    reason="Tier B: merged INIT+FOUNDATION selection — implement with T019/T021."
)
def test_merged_foundation_failure_names_model_stage_year():
    """A failure in the merged INITIALIZATION+FOUNDATION selection names model+stage+year."""


@pytest.mark.skip(
    reason="Tier C: collapsed STATE_ACCUMULATION selection — implement with T027."
)
def test_collapsed_state_accumulation_failure_names_model_stage_year():
    """A failure in the collapsed STATE_ACCUMULATION selection names model+stage+year."""
