"""Comparisons for ``validate_acquisition_minimum_wage.py`` (#1232).

Each group of runs shares a config family and a seed. Its four databases are
attached read-only as ``base``, ``acq``, ``wage`` and ``mix`` and compared in
SQL. Every result is a count, a sum or a difference.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import duckdb
import yaml

if TYPE_CHECKING:
    from validate_acquisition_minimum_wage import Plan, Run

ALIASES = {
    "baseline": "base",
    "acquisition": "acq",
    "minimum_wage": "wage",
    "both": "mix",
}
NO_RATES = "no_rate_columns"
CENT = 0.011
# After the first join year, leavers are drawn from a pool that now holds the
# members, so a few existing staff swap places. Set before the runs.
STAFF_DRIFT_LIMIT = 0.01
# Under a raise budget, how far the pay of people the floor did not raise may move.
RAISE_BUDGET_DRIFT_LIMIT = 0.0001

EVENTS = """
  (SELECT simulation_year AS y, event_type AS t, employee_id AS e, effective_date AS d,
     ROW_NUMBER() OVER (
       PARTITION BY simulation_year, event_type, employee_id, effective_date
       ORDER BY compensation_amount, employee_deferral_rate, event_details) AS k,
     compensation_amount AS pay, level_id AS lvl, employee_deferral_rate AS rate
   FROM {db}.fct_yearly_events WHERE {where})
"""
# Rows present on one side only, or whose pay, level or deferral rate moved.
EVENT_DIFF = """
  SELECT COUNT(*) FROM {left} l FULL JOIN {right} r USING (y, t, e, d, k)
  WHERE l.e IS NULL OR r.e IS NULL
     OR ABS(COALESCE(l.pay, 0) - COALESCE(r.pay, 0)) > {cent}
     OR l.lvl IS DISTINCT FROM r.lvl
     OR ABS(COALESCE(l.rate, 0) - COALESCE(r.rate, 0)) > 1e-9
"""
MEMBER = "starts_with(employee_id, 'ACQ_')"
# Census staff with a rate, and members who took a rate from the person they
# were sampled from: the pay a minimum wage of $1 an hour would give each.
PAY_PER_DOLLAR = """
  (SELECT employee_id, census_hourly_rate AS census_rate,
     current_compensation / census_hourly_rate AS pay_per_dollar
   FROM {db}.int_baseline_workforce
   WHERE census_hourly_rate IS NOT NULL AND current_compensation > 0
   UNION ALL
   SELECT employee_id, census_hourly_rate, census_annual_pay / census_hourly_rate
   FROM {db}.int_acquired_member_hourly_rates)
"""


@dataclass(frozen=True)
class Check:
    """One comparison. ``passed`` is None for a number that is only reported."""

    group: str
    name: str
    passed: Optional[bool]
    detail: str


class Group:
    """The four runs of one config family and seed, attached side by side."""

    def __init__(self, plan: "Plan", family: str, seed: int) -> None:
        self.plan = plan
        self.label = f"{family} / seed {seed}"
        self.connection = duckdb.connect()
        self.checks: List[Check] = []
        runs = plan.out / "runs"
        for variant, alias in ALIASES.items():
            self._attach(runs / f"{family}-{variant}-{seed}", alias)
        self.has_no_rates = (runs / f"{NO_RATES}-baseline-{seed}" / "done").exists()
        if family == "default" and self.has_no_rates:
            self._attach(runs / f"{NO_RATES}-baseline-{seed}", "bare")
        config = yaml.safe_load(
            (runs / f"{family}-baseline-{seed}/config.yaml").read_text()
        )
        self.growth = float(config["simulation"].get("target_growth_rate", 0.0))
        # A raise budget is a share of all eligible pay, so lifting some people
        # rescales everyone's later raises by a hair.
        self.raise_budget = (
            config.get("compensation", {}).get("raise_budget") is not None
        )

    def _attach(self, directory: Path, alias: str) -> None:
        if not (directory / "done").exists():
            raise FileNotFoundError(f"run did not finish: {directory}")
        self.connection.execute(
            f"ATTACH '{directory / 'sim.duckdb'}' AS {alias} (READ_ONLY)"
        )

    def rows(self, sql: str) -> List[Tuple[Any, ...]]:
        return self.connection.execute(sql).fetchall()

    def value(self, sql: str) -> Any:
        return self.rows(sql)[0][0]

    def event_diff(self, left: str, right: str, where: str = "TRUE") -> int:
        """How many events differ between two runs, among ``where``."""
        return int(
            self.value(
                EVENT_DIFF.format(
                    left=EVENTS.format(db=left, where=where),
                    right=EVENTS.format(db=right, where=where),
                    cent=CENT,
                )
            )
        )

    def add(self, name: str, passed: Optional[bool], detail: str) -> None:
        self.checks.append(Check(self.label, name, passed, detail))

    def expect_zero(self, name: str, count: int, what: str) -> None:
        self.add(name, count == 0, f"{count:,} {what}")


def check_off(group: Group) -> None:
    """Neither change configured: nothing of either appears."""
    stray = group.value(
        f"SELECT COUNT(*) FROM base.fct_yearly_events "
        f"WHERE event_type = 'minimum_wage' OR acquisition_id IS NOT NULL OR {MEMBER}"
    )
    steps = group.value("SELECT COUNT(*) FROM base.fct_minimum_wage_steps")
    group.expect_zero("Off: no members, no floor events", stray + steps, "rows")
    if "bare" in {
        row[0] for row in group.rows("SELECT database_name FROM duckdb_databases()")
    }:
        group.expect_zero(
            "Off: rate columns on the census change nothing",
            group.event_diff("base", "bare"),
            "events differ from the same census without rate columns",
        )


def check_members_join(group: Group, run: str) -> None:
    """Each group arrives whole, on its date, and is left alone that year."""
    for item in group.plan.acquisitions():
        joined = group.value(
            f"SELECT COUNT(*) FROM {run}.fct_yearly_events WHERE event_type = 'hire' "
            f"AND acquisition_id = '{item['id']}' "
            f"AND effective_date = DATE '{item['effective_date']}' "
            f"AND starts_with(employee_id, 'ACQ_{item['id']}_')"
        )
        group.add(
            f"Acquisition ({run}): group '{item['id']}' joins on {item['effective_date']}",
            joined == item["headcount"],
            f"{joined:,} of {item['headcount']:,} joined",
        )
    touched = group.value(f"""SELECT COUNT(*) FROM {run}.fct_yearly_events e
        JOIN {run}.fct_yearly_events h
          ON h.employee_id = e.employee_id AND h.event_type = 'hire'
        WHERE h.acquisition_id IS NOT NULL
          AND e.event_type IN ('termination', 'raise', 'promotion')
          AND (e.simulation_year = h.simulation_year
            OR e.event_category = 'new_hire_termination')""")
    group.expect_zero(
        f"Acquisition ({run}): no join-year raise, promotion or exit; no new-hire turnover",
        touched,
        "such events",
    )


def check_headcount(group: Group, run: str, against: str) -> None:
    """Year-end headcount is the comparison run plus each group, grown since."""
    counts = (
        "SELECT simulation_year, COUNT(*) FROM {}.fct_workforce_snapshot "
        "WHERE employment_status = 'active' GROUP BY 1"
    )
    ours = dict(group.rows(counts.format(run)))
    theirs = dict(group.rows(counts.format(against)))
    worst, parts = 0.0, []
    for year in sorted(ours):
        expected = float(theirs[year])
        for item in group.plan.acquisitions():
            since = year - int(item["effective_date"][:4])
            if since >= 0:
                expected += item["headcount"] * (1 + group.growth) ** since
        worst = max(worst, abs(ours[year] - expected))
        parts.append(f"{year}: {ours[year]:,} vs {expected:,.1f}")
    limit = 1 + len(group.plan.acquisitions())
    group.add(
        f"Acquisition ({run}): headcount is {against} plus the groups, grown at "
        f"{group.growth:.1%} a year",
        worst <= limit,
        "; ".join(parts),
    )


def check_existing_staff(group: Group) -> None:
    """Existing staff: exact through the first join year, close after it."""
    first = group.plan.start_year
    group.expect_zero(
        f"Acquisition: everyone else's events match the baseline in {first}",
        group.event_diff("base", "acq", f"NOT {MEMBER} AND simulation_year <= {first}"),
        "events differ",
    )
    staff = """
      SELECT simulation_year, COUNT(*) FILTER (WHERE employment_status = 'active'),
        SUM(prorated_annual_compensation), SUM(total_employer_contributions)
      FROM {db}.fct_workforce_snapshot
      WHERE employee_id IN (SELECT employee_id FROM base.int_baseline_workforce)
      GROUP BY 1 ORDER BY 1
    """
    base = group.rows(staff.format(db="base"))
    acq = group.rows(staff.format(db="acq"))
    worst, parts = 0.0, []
    for before, after in zip(base, acq):
        drift = [abs(a / b - 1) if b else 0.0 for b, a in zip(before[1:], after[1:])]
        worst = max(worst, *drift)
        parts.append(
            f"{before[0]}: headcount {drift[0]:.2%}, pay {drift[1]:.2%}, "
            f"employer cost {drift[2]:.2%}"
        )
    group.add(
        f"Acquisition: census staff stay within {STAFF_DRIFT_LIMIT:.0%} of the baseline",
        worst <= STAFF_DRIFT_LIMIT,
        "; ".join(parts),
    )


def check_floor(group: Group, run: str) -> None:
    """Every floor event lands on the right date at the right pay; no one is missed."""
    step, floor = group.plan.step_date, group.plan.minimum_wage
    rates = PAY_PER_DOLLAR.format(db=run)
    wrong = group.value(f"""SELECT COUNT(*) FROM {run}.fct_yearly_events e
        LEFT JOIN {rates} r USING (employee_id)
        LEFT JOIN {run}.fct_yearly_events h
          ON h.employee_id = e.employee_id AND h.event_type = 'hire'
         AND h.acquisition_id IS NOT NULL
        WHERE e.event_type = 'minimum_wage'
          AND (r.employee_id IS NULL
            OR e.effective_date <> GREATEST(DATE '{step}', COALESCE(h.effective_date, DATE '{step}'))
            OR e.compensation_amount <= e.previous_compensation
            OR ABS(e.compensation_amount - {floor} * r.pay_per_dollar) > {CENT})""")
    group.expect_zero(
        f"Minimum wage ({run}): each raise is dated the step or the later join date, "
        "and lifts pay to the minimum at unchanged hours",
        wrong,
        "floor events fail",
    )
    repeats = group.value(
        f"SELECT COUNT(*) FROM (SELECT employee_id FROM {run}.fct_yearly_events "
        "WHERE event_type = 'minimum_wage' GROUP BY 1 HAVING COUNT(*) > 1)"
    )
    group.expect_zero(f"Minimum wage ({run}): one raise per person", repeats, "repeats")
    missed = group.value(f"""SELECT COUNT(*) FROM {run}.fct_workforce_snapshot s
        JOIN {rates} r USING (employee_id)
        WHERE s.employment_status = 'active' AND s.simulation_year >= {step.year}
          AND (s.simulation_year > {step.year} OR s.employee_hire_date <= DATE '{step}'
            OR s.acquisition_id IS NOT NULL)
          AND s.current_compensation / r.pay_per_dollar < {floor} - 0.005""")
    group.expect_zero(
        f"Minimum wage ({run}): nobody with a rate ends a year below the minimum",
        missed,
        "people below it at a year end",
    )


def check_floor_totals(group: Group, run: str) -> None:
    """The step summary agrees with the events, and says who it left out."""
    step = group.plan.step_date
    events = group.rows(
        f"SELECT COUNT(*), COALESCE(SUM(compensation_amount - previous_compensation), 0), "
        f"COUNT(*) FILTER (WHERE {MEMBER}) FROM {run}.fct_yearly_events "
        f"WHERE event_type = 'minimum_wage' AND simulation_year = {step.year}"
    )[0]
    summary = group.rows(
        f"SELECT people_raised, added_annual_pay, people_with_rate, people_without_rate, "
        f"people_not_covered FROM {run}.fct_minimum_wage_steps"
    )
    agrees = (
        len(summary) == 1
        and summary[0][0] == events[0]
        and (abs(summary[0][1] - events[1]) <= 0.01 * max(1, events[0]))
    )
    later = group.value(
        f"SELECT COUNT(*) FROM {run}.fct_yearly_events "
        f"WHERE event_type = 'minimum_wage' AND simulation_year > {step.year}"
    )
    detail = (
        f"{events[0]:,} raised ({events[2]:,} members), ${events[1]:,.0f} of annual pay"
    )
    if summary:
        detail += (
            f"; {summary[0][2]:,} with a rate, {summary[0][3]:,} without, "
            f"{summary[0][4]:,} not covered (simulated hires); {later:,} raised on joining later"
        )
    group.add(f"Minimum wage ({run}): step summary matches the events", agrees, detail)


def check_floor_confined(group: Group) -> None:
    """The floor changes only the people it raised."""
    raised = "(SELECT employee_id FROM wage.fct_yearly_events WHERE event_type = 'minimum_wage')"
    differing = group.event_diff("base", "wage", f"employee_id NOT IN {raised}")
    group.add(
        "Minimum wage: everyone not raised matches the baseline in every year",
        None if group.raise_budget else differing == 0,
        f"{differing:,} events differ"
        + (" (a raise budget rescales later raises)" if group.raise_budget else ""),
    )
    step_year = group.plan.step_date.year
    group.expect_zero(
        "Minimum wage: raises and promotions in the step year are priced without it",
        group.event_diff(
            "base",
            "wage",
            f"simulation_year = {step_year} AND event_type IN ('raise', 'promotion')",
        ),
        "events differ",
    )
    group.expect_zero(
        "Minimum wage: hires match the baseline",
        group.event_diff("base", "wage", "event_type = 'hire'"),
        "hire events differ",
    )
    pay, moved, rows = group.rows(f"""SELECT SUM(b.prorated_annual_compensation),
          SUM(ABS(b.prorated_annual_compensation - w.prorated_annual_compensation))
            + SUM(ABS(b.total_employer_contributions - w.total_employer_contributions)),
          COUNT(*) FILTER (WHERE b.employment_status <> w.employment_status
            OR ABS(b.prorated_annual_compensation - w.prorated_annual_compensation) > {CENT}
            OR ABS(b.total_employer_contributions - w.total_employer_contributions) > {CENT})
        FROM base.fct_workforce_snapshot b
        JOIN wage.fct_workforce_snapshot w USING (employee_id, simulation_year)
        WHERE employee_id NOT IN {raised}""")[0]
    share = float(moved or 0) / float(pay)
    group.add(
        "Minimum wage: pay and employer cost of everyone not raised match the baseline",
        share <= RAISE_BUDGET_DRIFT_LIMIT if group.raise_budget else rows == 0,
        f"{rows:,} snapshot rows differ, {share:.4%} of their pay",
    )


def check_both(group: Group) -> None:
    """Together: members are held to the floor, and the two do not interfere."""
    dated = group.rows(f"""SELECT h.acquisition_id, COUNT(*),
          COUNT(*) FILTER (WHERE e.effective_date
            = GREATEST(h.effective_date, DATE '{group.plan.step_date}'))
        FROM mix.fct_yearly_events e
        JOIN mix.fct_yearly_events h
          ON h.employee_id = e.employee_id AND h.event_type = 'hire'
        WHERE e.event_type = 'minimum_wage' AND h.acquisition_id IS NOT NULL
        GROUP BY 1 ORDER BY 1""")
    group.add(
        "Both: members below the minimum are raised on the step date or on joining, "
        "whichever is later",
        bool(dated) and all(total == on_date for _, total, on_date in dated),
        "; ".join(
            f"'{name}': {on_date:,} of {total:,}" for name, total, on_date in dated
        )
        or "no member was raised",
    )
    unrated = group.value(f"""SELECT COUNT(*) FROM mix.fct_yearly_events e
        WHERE e.event_type = 'minimum_wage' AND {MEMBER}
          AND e.employee_id NOT IN
            (SELECT employee_id FROM mix.int_acquired_member_hourly_rates)""")
    group.expect_zero(
        "Both: no member without a rate is raised", unrated, "such raises"
    )
    first = group.plan.start_year
    group.expect_zero(
        f"Both: everyone else's events match the minimum wage run in {first}",
        group.event_diff("wage", "mix", f"NOT {MEMBER} AND simulation_year <= {first}"),
        "events differ",
    )


def cost_table(group: Group) -> List[Dict[str, Any]]:
    """Year-end headcount, pay and employer cost of each run."""
    table: List[Dict[str, Any]] = []
    for variant, alias in ALIASES.items():
        for year, heads, pay, match, core in group.rows(f"""SELECT simulation_year,
              COUNT(*) FILTER (WHERE employment_status = 'active'),
              SUM(prorated_annual_compensation), SUM(employer_match_amount),
              SUM(employer_core_amount)
            FROM {alias}.fct_workforce_snapshot GROUP BY 1 ORDER BY 1"""):
            table.append(
                {
                    "group": group.label,
                    "run": variant,
                    "year": year,
                    "headcount": heads,
                    "pay": float(pay or 0),
                    "match": float(match or 0),
                    "core": float(core or 0),
                }
            )
    return table


def check_group(group: Group) -> None:
    check_off(group)
    check_members_join(group, "acq")
    check_headcount(group, "acq", "base")
    check_existing_staff(group)
    check_floor(group, "wage")
    check_floor_totals(group, "wage")
    check_floor_confined(group)
    check_members_join(group, "mix")
    check_headcount(group, "mix", "wage")
    check_floor(group, "mix")
    check_floor_totals(group, "mix")
    check_both(group)


def _markdown(checks: Sequence[Check], costs: Sequence[Dict[str, Any]]) -> str:
    mark = {True: "pass", False: "FAIL", None: "info"}
    lines = [
        "| Config / seed | Check | Result | Numbers |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| {c.group} | {c.name} | {mark[c.passed]} | {c.detail} |" for c in checks
    ]
    lines += [
        "",
        "| Config / seed | Run | Year | Headcount | Pay | Match | Core |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines += [
        f"| {r['group']} | {r['run']} | {r['year']} | {r['headcount']:,} | "
        f"{r['pay']:,.0f} | {r['match']:,.0f} | {r['core']:,.0f} |"
        for r in costs
    ]
    return "\n".join(lines) + "\n"


def write_report(plan: "Plan", runs: Sequence["Run"]) -> int:
    """Compare every finished group; return 1 when a check fails."""
    checks: List[Check] = []
    costs: List[Dict[str, Any]] = []
    pairs = sorted({(run.family, run.seed) for run in runs if run.family != NO_RATES})
    for family, seed in pairs:
        group = Group(plan, family, seed)
        check_group(group)
        checks += group.checks
        costs += cost_table(group)
        group.connection.close()
    failed = [check for check in checks if check.passed is False]
    (plan.out / "results.json").write_text(
        json.dumps({"checks": [asdict(c) for c in checks], "costs": costs}, indent=2)
    )
    (plan.out / "report.md").write_text(_markdown(checks, costs))
    print(
        f"{len(checks) - len(failed)} of {len(checks)} checks pass; report: {plan.out / 'report.md'}"
    )
    for check in failed:
        print(f"FAIL {check.group}: {check.name}: {check.detail}")
    return 1 if failed else 0
