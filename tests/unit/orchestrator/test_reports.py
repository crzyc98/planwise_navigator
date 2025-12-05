from pathlib import Path

import duckdb

from planalign_orchestrator.reports import (EXECUTIVE_SUMMARY_TEMPLATE,
                                            ConsoleReporter, MultiYearReporter,
                                            ReportTemplate, YearAuditor)
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.validation import (DataValidator,
                                               HireTerminationRatioRule)


def _seed_year(
    conn, year: int, active: int, hires: int, terms: int, participating: int
):
    # workforce snapshot
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot(
            simulation_year INTEGER,
            employment_status VARCHAR,
            detailed_status_code VARCHAR,
            participation_status VARCHAR
        )
        """
    )
    rows = []
    # New hires (detailed_status_code='new_hire_active') - some participating, some not
    hire_participating = min(hires, participating)
    hire_non_participating = hires - hire_participating
    rows += [(year, "active", "new_hire_active", "participating")] * hire_participating
    rows += [(year, "active", "new_hire_active", "non_participating")] * hire_non_participating
    # Terminations (employment_status='terminated')
    rows += [(year, "terminated", "terminated", "non_participating")] * terms
    # Remaining active employees
    remaining_active = active - hires
    remaining_participating = max(0, participating - hire_participating)
    remaining_non_participating = remaining_active - remaining_participating
    rows += [(year, "active", "active", "participating")] * remaining_participating
    rows += [(year, "active", "active", "non_participating")] * remaining_non_participating
    conn.executemany("INSERT INTO fct_workforce_snapshot VALUES (?,?,?,?)", rows)

    # events
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fct_yearly_events(
            employee_id VARCHAR,
            event_type VARCHAR,
            simulation_year INTEGER,
            event_date DATE
        )
        """
    )
    conn.executemany(
        "INSERT INTO fct_yearly_events VALUES (?,?,?, DATE '" + str(year) + "-01-01')",
        [(f"E{i}", "hire", year) for i in range(hires)],
    )
    conn.executemany(
        "INSERT INTO fct_yearly_events VALUES (?,?,?, DATE '" + str(year) + "-12-31')",
        [(f"T{i}", "termination", year) for i in range(terms)],
    )


def test_year_auditor_workforce_breakdown(tmp_path: Path):
    dbp = tmp_path / "r.duckdb"
    conn = duckdb.connect(str(dbp))
    _seed_year(conn, 2025, active=10, hires=3, terms=2, participating=6)
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    dv = DataValidator(mgr)
    dv.register_rule(HireTerminationRatioRule())
    auditor = YearAuditor(mgr, dv)
    report = auditor.generate_report(2025)
    wb = report.workforce_breakdown
    assert wb.active_employees == 10
    assert 0.59 < wb.participation_rate < 0.61


def test_year_auditor_event_summary(tmp_path: Path):
    dbp = tmp_path / "r.duckdb"
    conn = duckdb.connect(str(dbp))
    _seed_year(conn, 2026, active=8, hires=4, terms=1, participating=4)
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    dv = DataValidator(mgr)
    auditor = YearAuditor(mgr, dv)
    report = auditor.generate_report(2026)
    es = report.event_summary
    assert es.events_by_type.get("hire") == 4
    assert es.hire_termination_ratio == 4 / 1


def test_multi_year_reporter_progression_analysis(tmp_path: Path):
    dbp = tmp_path / "r.duckdb"
    conn = duckdb.connect(str(dbp))
    _seed_year(conn, 2025, active=10, hires=3, terms=2, participating=6)
    _seed_year(conn, 2026, active=15, hires=5, terms=2, participating=9)
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    myr = MultiYearReporter(mgr)
    summary = myr.generate_summary([2025, 2026])
    assert summary.workforce_progression[0].active_employees == 10
    assert summary.workforce_progression[1].active_employees == 15
    assert summary.growth_analysis["start_active"] == 10
    assert summary.growth_analysis["end_active"] == 15


def test_report_export_json_and_csv(tmp_path: Path):
    dbp = tmp_path / "r.duckdb"
    conn = duckdb.connect(str(dbp))
    _seed_year(conn, 2027, active=12, hires=2, terms=1, participating=3)
    conn.close()

    mgr = DatabaseConnectionManager(db_path=dbp)
    dv = DataValidator(mgr)
    auditor = YearAuditor(mgr, dv)
    report = auditor.generate_report(2027)

    json_path = tmp_path / "report.json"
    report.export_json(json_path)
    assert json_path.exists() and json_path.read_text().startswith("{")

    myr = MultiYearReporter(mgr)
    summary = (
        myr.generate_summary([2027, 2027])
        if False
        else myr.generate_summary([2026, 2027])
    )
    csv_path = tmp_path / "summary.csv"
    summary.export_csv(csv_path)
    data = csv_path.read_text().splitlines()
    assert data[0].startswith(
        "Year,Total Employees,Active Employees,Participation Rate"
    )


def test_configurable_report_templates():
    tmpl = ReportTemplate(EXECUTIVE_SUMMARY_TEMPLATE)
    fake = {
        "workforce_breakdown": {"x": 1},
        "growth_analysis": {"y": 2},
        "event_summary": {"z": 3},
        "data_quality_results": [],
    }
    applied = tmpl.apply_template(fake)
    assert "workforce_breakdown" in applied and "growth_analysis" in applied
    assert "event_summary" not in applied
