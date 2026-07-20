"""#470 T012: dbt-owned selection semantics against the real project.

These parse the actual dbt project once per session (in-process, isolated
workspace target), so they are deliberately not in the fast suite.
"""


import pytest

from planalign_orchestrator.engine.plan_cache import (
    PlanCache,
    SelectorResolutionError,
)
from planalign_orchestrator.engine.workspace import RunArtifactWorkspace
from tests.fixtures.compiled_execution import FakeDbManager

pytestmark = [pytest.mark.orchestrator]

VARS = {
    "simulation_year": 2025,
    "census_parquet_path": "/tmp/nonexistent-census.parquet",  # parse-time string only
}


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("plan-cache")
    ws = RunArtifactWorkspace.create(
        db_manager=FakeDbManager(root / "cache_test.duckdb"), artifact_root=root / "ws"
    )
    return PlanCache(workspace=ws, db_manager=None)


def test_fqn_wildcard_matches_dbt_semantics(cache):
    ids = cache.resolve_selection(["staging.*"], [], VARS)
    names = {uid.split(".")[-1] for uid in ids}
    assert "stg_census_data" in names
    assert all(n.startswith("stg_") or "staging" in n for n in names)
    assert "int_hiring_events" not in names


def test_tag_selector_with_exclusion(cache):
    ids = cache.resolve_selection(
        ["tag:EVENT_GENERATION"], ["int_employee_contributions"], VARS
    )
    names = {uid.split(".")[-1] for uid in ids}
    assert "int_hiring_events" in names
    assert "int_employee_contributions" not in names


def test_explicit_names_and_topological_order(cache):
    ids = cache.resolve_selection(["fct_yearly_events", "int_hiring_events"], [], VARS)
    names = [uid.split(".")[-1] for uid in ids]
    assert set(names) == {"fct_yearly_events", "int_hiring_events"}
    assert names.index("int_hiring_events") < names.index("fct_yearly_events")


def test_selection_memoized_per_vars(cache, monkeypatch):
    cache.resolve_selection(["staging.*"], [], VARS)

    def boom(*a, **k):
        raise AssertionError("dbt re-invoked despite memoization")

    monkeypatch.setattr(cache, "_invoke", boom)
    cache.resolve_selection(["staging.*"], [], VARS)


def test_invalid_selector_raises_not_empty_success(cache):
    with pytest.raises(SelectorResolutionError):
        cache.resolve_selection(["state:modified"], [], VARS)


def test_unknown_name_resolves_empty(cache):
    ids = cache.resolve_selection(["definitely_not_a_model_xyz"], [], VARS)
    assert ids == ()
