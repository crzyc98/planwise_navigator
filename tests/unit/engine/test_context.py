"""#470 T011: canonical render-context identity behavior."""

import duckdb
import pytest

from planalign_orchestrator.engine.context import (
    canonical_digest,
    inspect_relations,
    relation_state_digest,
    vars_digest,
)

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def test_canonical_digest_is_order_insensitive_for_dicts():
    assert canonical_digest({"a": 1, "b": 2}) == canonical_digest({"b": 2, "a": 1})


def test_vars_digest_distinguishes_values_and_extra_keys():
    base = vars_digest({"simulation_year": 2025, "seed": 42})
    assert base != vars_digest({"simulation_year": 2026, "seed": 42})
    assert base != vars_digest({"simulation_year": 2025, "seed": 42, "shard": 1})


def test_inspect_relations_missing_database(tmp_path):
    states = inspect_relations(tmp_path / "absent.duckdb", [("d", "main", "t")])
    assert states[0].relation_type == "missing"
    assert states[0].columns == ()


def test_relation_state_digest_tracks_schema_and_existence(tmp_path):
    db = tmp_path / "x.duckdb"
    with duckdb.connect(str(db)) as conn:
        conn.execute("CREATE TABLE t (a INTEGER)")
    before = relation_state_digest(inspect_relations(db, [("d", "main", "t")]))
    with duckdb.connect(str(db)) as conn:
        conn.execute("ALTER TABLE t ADD COLUMN b VARCHAR")
    after = relation_state_digest(inspect_relations(db, [("d", "main", "t")]))
    assert before != after
    missing = relation_state_digest(inspect_relations(db, [("d", "main", "nope")]))
    assert missing not in (before, after)


def test_relation_state_row_content_does_not_change_digest(tmp_path):
    """Relation-state identity is structural (existence/type/schema), not data."""
    db = tmp_path / "x.duckdb"
    with duckdb.connect(str(db)) as conn:
        conn.execute("CREATE TABLE t (a INTEGER)")
    before = relation_state_digest(inspect_relations(db, [("d", "main", "t")]))
    with duckdb.connect(str(db)) as conn:
        conn.execute("INSERT INTO t VALUES (1), (2)")
    after = relation_state_digest(inspect_relations(db, [("d", "main", "t")]))
    assert before == after
