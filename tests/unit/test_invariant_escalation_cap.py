"""Keep both escalation cap checks strict with Easy Enroll enabled by default."""

import duckdb

from tests.invariants.queries import DEFERRAL_CAP_RESPECTED


def test_escalation_cap_checks_package_membership_year_and_scenario() -> None:
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE fct_yearly_events (
            employee_id VARCHAR, scenario_id VARCHAR, simulation_year INTEGER,
            event_type VARCHAR, event_category VARCHAR, employee_deferral_rate DOUBLE
        )""")
        connection.execute("""INSERT INTO fct_yearly_events VALUES
            ('ordinary_ok', 'a', 2026, 'deferral_escalation', NULL, 0.06),
            ('ordinary_bad', 'a', 2026, 'deferral_escalation', NULL, 0.07),
            ('package_ok', 'a', 2025, 'enrollment', 'easy_enroll', 0.08),
            ('package_ok', 'a', 2026, 'deferral_escalation', NULL, 0.10),
            ('package_bad', 'a', 2025, 'enrollment', 'easy_enroll', 0.08),
            ('package_bad', 'a', 2026, 'deferral_escalation', NULL, 0.11),
            ('other_scenario', 'b', 2025, 'enrollment', 'easy_enroll', 0.08),
            ('other_scenario', 'a', 2026, 'deferral_escalation', NULL, 0.07),
            ('future_package', 'a', 2027, 'enrollment', 'easy_enroll', 0.08),
            ('future_package', 'a', 2026, 'deferral_escalation', NULL, 0.07)
        """)
        violations = connection.execute(DEFERRAL_CAP_RESPECTED).fetchall()
    assert {row[0] for row in violations} == {
        "ordinary_bad",
        "package_bad",
        "other_scenario",
        "future_package",
    }
