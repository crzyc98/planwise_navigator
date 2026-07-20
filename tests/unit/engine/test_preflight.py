"""#470 regressions 1 & 2: hook classification and fail-closed selection.

RED against the prototype: `render_hook` raises on `log()` (forcing
delegation for informational hooks), and the hand selector maps unknown
selectors to an empty list that becomes a successful zero-node invocation.
"""

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


# --------------------------------------------------------------------- #
# Regression 1: informational log() hooks are supported, not delegated  #
# --------------------------------------------------------------------- #

LOG_HOOK = '{{ log("Starting dbt run for Fidelity PlanAlign Engine", info=True) }}'
PRAGMA_HOOK = "PRAGMA threads=16"
GUARDED_DELETE_HOOK = (
    "{% if is_incremental() %}DELETE FROM {{ this }} "
    "WHERE simulation_year = {{ var('simulation_year') }}{% endif %}"
)
SIDE_EFFECT_HOOK = "{{ run_query('DROP TABLE oops') }}"


def test_pure_log_hook_is_informational_not_delegation():
    from planalign_orchestrator.engine.preflight import classify_hook

    plan = classify_hook(
        LOG_HOOK, scope="project_start", dbt_vars={}, incremental=False
    )
    assert plan.kind == "informational_log"
    assert plan.rendered_sql is None
    assert "Starting dbt run" in (plan.message or "")


def test_pragma_hook_is_connection_sql():
    from planalign_orchestrator.engine.preflight import classify_hook

    plan = classify_hook(
        PRAGMA_HOOK, scope="project_start", dbt_vars={}, incremental=False
    )
    assert plan.kind == "connection_sql"
    assert plan.rendered_sql == "PRAGMA threads=16"


def test_guarded_delete_hook_is_transactional_sql():
    from planalign_orchestrator.engine.preflight import classify_hook

    plan = classify_hook(
        GUARDED_DELETE_HOOK,
        scope="node_pre",
        dbt_vars={"simulation_year": 2025},
        incremental=True,
        this='"db"."main"."t"',
    )
    assert plan.kind == "transactional_sql"
    assert 'DELETE FROM "db"."main"."t"' in plan.rendered_sql


def test_side_effect_hook_is_typed_unsupported():
    from planalign_orchestrator.engine.preflight import (
        KnownUnsupportedSemantics,
        classify_hook,
    )

    with pytest.raises(KnownUnsupportedSemantics) as excinfo:
        classify_hook(SIDE_EFFECT_HOOK, scope="node_pre", dbt_vars={}, incremental=True)
    assert excinfo.value.code == "hook"


# --------------------------------------------------------------------- #
# Regression 2: unsupported/empty selection never becomes zero-node OK  #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "select_tokens,expected_code",
    [
        (["state:modified"], "selector_context"),
        (["@int_hiring_events"], "selector_context"),
        (["definitely_not_a_model_xyz"], "empty_selection"),
    ],
)
def test_unproven_selection_is_typed_unsupported(select_tokens, expected_code):
    from planalign_orchestrator.engine.preflight import (
        KnownUnsupportedSemantics,
        classify_selection_failure,
    )

    outcome = classify_selection_failure(select_tokens, resolved_count=0)
    assert isinstance(outcome, KnownUnsupportedSemantics)
    assert outcome.code == expected_code


def test_zero_node_resolution_never_direct_success(tmp_path):
    """End-to-end guard: a run invocation resolving zero nodes must not
    report direct compiled success (contract §2: SUCCEEDED requires >=1 node)."""
    from planalign_orchestrator.engine.compiled_runner import CompiledRunner

    runner = CompiledRunner(working_dir=tmp_path, threads=1)
    outcome = runner.classify_direct_result(planned_nodes=())
    assert outcome != "SUCCEEDED"
