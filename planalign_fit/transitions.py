"""Cohort-linked diffs between consecutive census snapshots.

Employees are linked across a snapshot pair by ``employee_id`` and each link is
classified as continued / terminated / hired / promoted / comp-changed /
enrolled / deferral-changed. Everything downstream fits rates off this one
table, so the transition semantics live here and nowhere else.

Exposure convention: the denominator for a year-``t`` rate is the population
*active at the end of year t-1* (for experienced employees) or *hired during
year t* (for new hires), placed in its year t-1 (respectively, hire-time) band.
That matches how the simulator applies a hazard: the band is known before the
event resolves.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from planalign_fit.bands import BandDefinitions
from planalign_fit.snapshots import Snapshot, SnapshotSet, register_snapshots

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb

TRANSITIONS_TABLE = "fit_transitions"
NEW_HIRES_TABLE = "fit_new_hires"

# An employee is enrolled when the census carries an enrollment date or a
# non-zero deferral rate. Either column alone is enough.
ENROLLMENT_COLUMNS = ("employee_enrollment_date", "employee_deferral_rate")


class TransitionError(ValueError):
    """The linked transition table could not be built or counted."""


@dataclass(frozen=True)
class Observability:
    """Which fits the supplied snapshots can actually support."""

    has_termination_rows: bool
    has_enrollment: bool
    has_deferral_rate: bool
    # Share of linked transitions carrying an explicit job level at *both* ends
    # — a promotion is only directly observable across a pair. Deliberately a
    # coverage measure rather than a column-presence flag: the level projection
    # falls back to compensation banding per row, so a column populated for a
    # handful of employees would otherwise let a fit call itself authoritative
    # while band-deriving everyone else (#511).
    level_coverage: float

    def reasons(self) -> dict[str, str]:
        """Human-readable blockers, keyed by the fit they block."""
        blockers: dict[str, str] = {}
        if not self.has_termination_rows:
            blockers["new_hire_termination"] = (
                "no snapshot retains terminated rows (every row is active), so "
                "employees hired and terminated inside the same year are invisible"
            )
        if not self.has_enrollment:
            blockers["enrollment"] = (
                "snapshots carry neither employee_enrollment_date nor "
                "employee_deferral_rate, so participation cannot be observed"
            )
        if not self.has_deferral_rate:
            blockers["deferral"] = (
                "snapshots carry no employee_deferral_rate column, so deferral "
                "levels and escalation adoption cannot be observed"
            )
        return blockers


@dataclass(frozen=True)
class TransitionSet:
    """Materialized transitions plus the observability of the source data."""

    conn: "duckdb.DuckDBPyConnection"
    snapshot_set: SnapshotSet
    bands: BandDefinitions
    observability: Observability
    unmatched_reappearances: int
    linked_pairs: int

    @property
    def table(self) -> str:
        return TRANSITIONS_TABLE

    @property
    def new_hires_table(self) -> str:
        return NEW_HIRES_TABLE


def _optional(snapshot: Snapshot, column: str, cast: str) -> str:
    """Reference a column when present, otherwise a typed NULL."""
    return column if snapshot.has(column) else f"CAST(NULL AS {cast})"


def _active_predicate(snapshot: Snapshot) -> str:
    """True when the employee is on the books at the end of the snapshot year."""
    year = snapshot.year
    clauses = []
    if snapshot.has("active"):
        clauses.append("COALESCE(active, TRUE)")
    if snapshot.has("employee_termination_date"):
        clauses.append(
            "(TRY_CAST(employee_termination_date AS DATE) IS NULL "
            f"OR EXTRACT(YEAR FROM TRY_CAST(employee_termination_date AS DATE)) > {year})"
        )
    return " AND ".join(clauses) if clauses else "TRUE"


def _snapshot_projection(snapshot: Snapshot) -> str:
    """One normalized row per employee in a snapshot, before band assignment."""
    year = snapshot.year
    as_of = f"DATE '{year}-12-31'"
    deferral = _optional(snapshot, "employee_deferral_rate", "DOUBLE")
    enrollment_date = _optional(snapshot, "employee_enrollment_date", "DATE")
    termination_date = _optional(snapshot, "employee_termination_date", "DATE")
    return f"""
SELECT
  CAST(employee_id AS VARCHAR) AS employee_id,
  {year} AS snapshot_year,
  TRY_CAST(employee_birth_date AS DATE) AS birth_date,
  TRY_CAST(employee_hire_date AS DATE) AS hire_date,
  TRY_CAST({termination_date} AS DATE) AS termination_date,
  TRY_CAST(employee_gross_compensation AS DOUBLE) AS compensation,
  {year} - EXTRACT(YEAR FROM TRY_CAST(employee_birth_date AS DATE)) AS age,
  CASE
    WHEN TRY_CAST(employee_hire_date AS DATE) IS NULL THEN 0
    WHEN TRY_CAST(employee_hire_date AS DATE) > {as_of} THEN 0
    ELSE CAST(FLOOR(DATEDIFF('day', TRY_CAST(employee_hire_date AS DATE), {as_of}) / 365.25) AS INTEGER)
  END AS tenure,
  {_active_predicate(snapshot)} AS is_active,
  TRY_CAST({deferral} AS DOUBLE) AS deferral_rate,
  TRY_CAST({enrollment_date} AS DATE) AS enrollment_date,
  TRY_CAST({_optional(snapshot, "level_id", "INTEGER")} AS INTEGER) AS source_level_id
FROM {snapshot.relation_name}
WHERE employee_id IS NOT NULL
"""


def _banded_projection(snapshot: Snapshot, bands: BandDefinitions) -> str:
    # Where a census supplies level_id it wins; where it does not (or leaves a
    # row blank) level is derived from compensation banding, exactly as
    # int_baseline_workforce does. `source_level_id` is carried through
    # unresolved so a caller can tell the two apart per row and measure how much
    # of the population the column actually covers.
    level_expr = (
        f"COALESCE(source_level_id, {bands.level_case('compensation')})"
        if snapshot.has("level_id")
        else bands.level_case("compensation")
    )
    enrolled_expr = _enrolled_expression(snapshot)
    return f"""
SELECT
  employee_id,
  snapshot_year,
  birth_date,
  hire_date,
  termination_date,
  compensation,
  age,
  tenure,
  is_active,
  deferral_rate,
  enrollment_date,
  source_level_id,
  {level_expr} AS level_id,
  {bands.age_band_case('age')} AS age_band,
  {bands.tenure_band_case('tenure')} AS tenure_band,
  {bands.age_segment_case('age')} AS age_segment,
  {bands.income_segment_case('compensation')} AS income_segment,
  {enrolled_expr} AS is_enrolled
FROM ({_snapshot_projection(snapshot)})
"""


def _enrolled_expression(snapshot: Snapshot) -> str:
    clauses = []
    if snapshot.has("employee_enrollment_date"):
        clauses.append("enrollment_date IS NOT NULL")
    if snapshot.has("employee_deferral_rate"):
        clauses.append("COALESCE(deferral_rate, 0) > 0")
    if not clauses:
        return "CAST(NULL AS BOOLEAN)"
    return "(" + " OR ".join(clauses) + ")"


def _observe(
    conn: "duckdb.DuckDBPyConnection", snapshot_set: SnapshotSet
) -> Observability:
    common = snapshot_set.common_columns()
    has_inactive = False
    if "active" in common or "employee_termination_date" in common:
        for snapshot in snapshot_set:
            row = conn.execute(
                f"SELECT COUNT(*) FROM ({_snapshot_projection(snapshot)}) "
                "WHERE NOT is_active"
            ).fetchone()
            if row is None:
                raise TransitionError(
                    f"Could not count inactive rows in snapshot {snapshot.year}."
                )
            if row[0]:
                has_inactive = True
                break
    return Observability(
        has_termination_rows=has_inactive,
        has_enrollment=any(c in common for c in ENROLLMENT_COLUMNS),
        has_deferral_rate="employee_deferral_rate" in common,
        # Filled in once the transition table exists — coverage is a property
        # of linked pairs, not of the column list.
        level_coverage=0.0,
    )


def build_transitions(
    conn: "duckdb.DuckDBPyConnection",
    snapshot_set: SnapshotSet,
    bands: BandDefinitions,
) -> TransitionSet:
    """Materialize the cohort-linked transition and new-hire tables.

    ``fit_transitions`` holds one row per employee active at the end of year
    ``from_year`` — the experienced-cohort exposure. ``fit_new_hires`` holds one
    row per employee first observed in year ``to_year`` with a hire date in that
    year — the new-hire cohort.
    """
    register_snapshots(conn, snapshot_set)

    for snapshot in snapshot_set:
        conn.execute(
            f"CREATE OR REPLACE VIEW banded_{snapshot.year} AS "
            f"{_banded_projection(snapshot, bands)}"
        )

    observability = _observe(conn, snapshot_set)

    conn.execute(f"DROP TABLE IF EXISTS {TRANSITIONS_TABLE}")
    conn.execute(f"DROP TABLE IF EXISTS {NEW_HIRES_TABLE}")

    pairs = list(zip(snapshot_set.snapshots, snapshot_set.snapshots[1:]))
    transition_selects = [_pair_transition_sql(prior, later) for prior, later in pairs]
    new_hire_selects = [_pair_new_hire_sql(prior, later) for prior, later in pairs]

    conn.execute(
        f"CREATE TABLE {TRANSITIONS_TABLE} AS "
        + "\nUNION ALL\n".join(transition_selects)
    )
    conn.execute(
        f"CREATE TABLE {NEW_HIRES_TABLE} AS " + "\nUNION ALL\n".join(new_hire_selects)
    )

    linked_row = conn.execute(f"SELECT COUNT(*) FROM {TRANSITIONS_TABLE}").fetchone()
    if linked_row is None:
        raise TransitionError("Could not count linked snapshot pairs.")
    linked_pairs = int(linked_row[0])
    unmatched = _count_reappearances(conn, snapshot_set)
    observability = replace(
        observability, level_coverage=_level_coverage(conn, linked_pairs)
    )

    return TransitionSet(
        conn=conn,
        snapshot_set=snapshot_set,
        bands=bands,
        observability=observability,
        unmatched_reappearances=unmatched,
        linked_pairs=linked_pairs,
    )


def _level_coverage(conn: "duckdb.DuckDBPyConnection", linked_pairs: int) -> float:
    """Share of transitions with a census-supplied job level at both ends.

    A promotion is a *move* between levels, so a transition is only directly
    observable when both snapshots name the employee's level. Rows missing
    either end fall back to compensation banding, which is precisely the
    substitution that cannot be trusted to signal a promotion.
    """
    if linked_pairs <= 0:
        return 0.0
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM {TRANSITIONS_TABLE}
        WHERE has_source_level
        """
    ).fetchone()
    if row is None:
        raise TransitionError("Could not measure job-level coverage.")
    return float(row[0]) / float(linked_pairs)


def _pair_transition_sql(prior: Snapshot, later: Snapshot) -> str:
    """Experienced-cohort transitions from ``prior`` year-end to ``later`` year-end."""
    return f"""
SELECT
  {prior.year} AS from_year,
  {later.year} AS to_year,
  p.employee_id,
  p.age_band,
  p.tenure_band,
  p.level_id,
  p.age_segment,
  p.income_segment,
  p.age,
  p.tenure,
  p.compensation AS from_compensation,
  n.compensation AS to_compensation,
  p.is_enrolled AS from_enrolled,
  n.is_enrolled AS to_enrolled,
  p.deferral_rate AS from_deferral_rate,
  n.deferral_rate AS to_deferral_rate,
  (p.source_level_id IS NOT NULL AND n.source_level_id IS NOT NULL)
    AS has_source_level,
  (n.employee_id IS NOT NULL AND n.is_active) AS continued,
  NOT (n.employee_id IS NOT NULL AND n.is_active) AS terminated,
  (n.employee_id IS NULL) AS vanished,
  CASE
    WHEN n.employee_id IS NOT NULL AND n.is_active AND n.level_id > p.level_id THEN TRUE
    ELSE FALSE
  END AS promoted,
  -- How likely this transition was a promotion rather than an ordinary raise.
  -- Seeded with the observed flag, which is the right answer whenever the
  -- census supplies job levels. When it does not, `planalign_fit.promotion`
  -- overwrites this with a fitted probability (#511). Downstream, summing it
  -- gives promotion events and its complement weights the merit median, so
  -- both estimates read the same quantity.
  CASE
    WHEN n.employee_id IS NOT NULL AND n.is_active AND n.level_id > p.level_id
      THEN 1.0
    ELSE 0.0
  END AS promotion_weight,
  CASE
    WHEN n.employee_id IS NOT NULL AND n.is_active
         AND p.compensation IS NOT NULL AND p.compensation > 0
         AND n.compensation IS NOT NULL
    THEN n.compensation / p.compensation - 1.0
    ELSE NULL
  END AS compensation_growth
FROM banded_{prior.year} p
LEFT JOIN banded_{later.year} n USING (employee_id)
WHERE p.is_active
"""


def _pair_new_hire_sql(prior: Snapshot, later: Snapshot) -> str:
    """New hires observed in ``later``: hired during that year, absent before."""
    return f"""
SELECT
  {prior.year} AS from_year,
  {later.year} AS to_year,
  n.employee_id,
  n.age_band,
  n.tenure_band,
  n.level_id,
  n.age_segment,
  n.income_segment,
  n.age,
  n.compensation,
  n.is_active,
  NOT n.is_active AS terminated,
  n.is_enrolled,
  n.deferral_rate
FROM banded_{later.year} n
LEFT JOIN banded_{prior.year} p USING (employee_id)
WHERE p.employee_id IS NULL
  AND n.hire_date IS NOT NULL
  AND EXTRACT(YEAR FROM n.hire_date) = {later.year}
"""


def _count_reappearances(
    conn: "duckdb.DuckDBPyConnection", snapshot_set: SnapshotSet
) -> int:
    """Rows that appear in a later snapshot with a pre-existing hire date.

    These are rehires or ID-reuse anomalies: they are excluded from both the
    experienced exposure (absent from the prior snapshot) and the new-hire
    cohort (hire date predates the year), so the fit report surfaces the count
    rather than dropping them silently.
    """
    total = 0
    for prior, later in zip(snapshot_set.snapshots, snapshot_set.snapshots[1:]):
        row = conn.execute(
            f"""
                SELECT COUNT(*)
                FROM banded_{later.year} n
                LEFT JOIN banded_{prior.year} p USING (employee_id)
                WHERE p.employee_id IS NULL
                  AND (n.hire_date IS NULL
                       OR EXTRACT(YEAR FROM n.hire_date) < {later.year})
                """
        ).fetchone()
        if row is None:
            raise TransitionError(
                f"Could not count reappearances between {prior.year} and {later.year}."
            )
        total += int(row[0])
    return total
