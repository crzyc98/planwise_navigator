"""Named multi-year invariants exposed as an append-only test contract."""

from __future__ import annotations

from dataclasses import dataclass

from tests.invariants import queries


@dataclass(frozen=True, slots=True)
class Invariant:
    """A query whose returned rows are invariant violations."""

    name: str
    description: str
    guarded_issue: str | None
    violation_sql: str
    sample_limit: int = 20


CATALOG = (
    Invariant(
        "event-uniqueness",
        "Event identifiers are globally unique.",
        None,
        queries.EVENT_UNIQUENESS,
    ),
    Invariant(
        "enrollment-no-duplicate",
        "Enrollments alternate with opt-outs.",
        None,
        queries.ENROLLMENT_NO_DUPLICATE,
    ),
    Invariant(
        "enrollment-census-persistence",
        "Census enrollment persists absent opt-out.",
        "#418",
        queries.ENROLLMENT_CENSUS_PERSISTENCE,
    ),
    Invariant(
        "continuity-headcount",
        "Ending actives equal next-year starting actives.",
        "#419",
        queries.CONTINUITY_HEADCOUNT,
    ),
    Invariant(
        "continuity-no-zombie",
        "Terminated employees are not active without rehire.",
        None,
        queries.CONTINUITY_NO_ZOMBIE,
    ),
    Invariant(
        "snapshot-explained-by-events",
        "Enrollment and deferral snapshot state replays from events.",
        "#419",
        queries.SNAPSHOT_EXPLAINED_BY_EVENTS,
    ),
    Invariant(
        "snapshot-no-foreign-rows",
        "Run output contains only configured years and identities.",
        "#419",
        queries.SNAPSHOT_NO_FOREIGN_ROWS,
    ),
    Invariant(
        "growth-exactness",
        "Ending headcount matches E077 single-rounding output.",
        None,
        queries.GROWTH_EXACTNESS,
    ),
    Invariant(
        "deferral-explained-changes",
        "Yearly deferral changes have explaining events.",
        None,
        queries.DEFERRAL_EXPLAINED_CHANGES,
    ),
    Invariant(
        "deferral-cap-respected",
        "Escalation events never exceed the configured cap.",
        None,
        queries.DEFERRAL_CAP_RESPECTED,
    ),
    Invariant(
        "deferral-optout-not-escalated",
        "Census escalation opt-outs never receive escalation events.",
        None,
        queries.DEFERRAL_OPTOUT_NOT_ESCALATED,
    ),
)
