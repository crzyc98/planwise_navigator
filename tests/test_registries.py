from pathlib import Path

import duckdb

from navigator_orchestrator.utils import DatabaseConnectionManager
from navigator_orchestrator.registries import (
    EnrollmentRegistry,
    DeferralEscalationRegistry,
    RegistryManager,
    SQLTemplateManager,
)


def _setup_db(db_path: Path):
    conn = duckdb.connect(str(db_path))
    # baseline workforce table
    conn.execute(
        """
        CREATE TABLE int_baseline_workforce (
            employee_id VARCHAR,
            employment_status VARCHAR,
            employee_enrollment_date DATE
        )
        """
    )
    # yearly events table
    conn.execute(
        """
        CREATE TABLE fct_yearly_events (
            employee_id VARCHAR,
            event_type VARCHAR,
            simulation_year INTEGER,
            event_date DATE
        )
        """
    )
    conn.close()


def test_enrollment_registry_create_for_first_year(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    _setup_db(db_path)
    conn = duckdb.connect(str(db_path))
    conn.execute("INSERT INTO int_baseline_workforce VALUES ('E1','active','2024-02-01'), ('E2','inactive',NULL)")
    conn.close()

    mgr = DatabaseConnectionManager(db_path=db_path)
    reg = EnrollmentRegistry(mgr)
    assert reg.create_for_year(2025)
    # Verify rows
    with mgr.get_connection() as c:
        rows = c.execute("SELECT employee_id, first_enrollment_year FROM enrollment_registry ORDER BY employee_id").fetchall()
        assert rows == [("E1", 2025)]


def test_enrollment_registry_update_post_year(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    _setup_db(db_path)
    conn = duckdb.connect(str(db_path))
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E3','enrollment',2026,'2026-03-01')")
    conn.close()

    mgr = DatabaseConnectionManager(db_path=db_path)
    reg = EnrollmentRegistry(mgr)
    reg.create_table()
    assert reg.update_post_year(2026)
    assert reg.is_employee_enrolled("E3", 2026) is True


def test_deferral_registry_escalation_tracking(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    _setup_db(db_path)
    conn = duckdb.connect(str(db_path))
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E5','DEFERRAL_ESCALATION',2025,'2025-04-01')")
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E5','DEFERRAL_ESCALATION',2026,'2026-04-01')")
    conn.close()

    mgr = DatabaseConnectionManager(db_path=db_path)
    reg = DeferralEscalationRegistry(mgr)
    reg.create_table()
    assert reg.update_post_year(2025)
    assert reg.update_post_year(2026)
    assert reg.get_escalation_count("E5") == 2


def test_registry_integrity_validation(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    _setup_db(db_path)
    mgr = DatabaseConnectionManager(db_path=db_path)
    enr = EnrollmentRegistry(mgr)
    assert enr.create_for_year(2025)
    # No enrollment events => likely orphaned warnings
    result = enr.validate_integrity()
    assert result.is_valid is False
    assert any("orphaned" in e for e in result.errors)


def test_cross_year_state_consistency(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    _setup_db(db_path)
    conn = duckdb.connect(str(db_path))
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E6','enrollment',2025,'2025-01-15')")
    conn.execute("INSERT INTO fct_yearly_events VALUES ('E7','enrollment',2027,'2027-05-01')")
    conn.close()

    mgr = DatabaseConnectionManager(db_path=db_path)
    reg = EnrollmentRegistry(mgr)
    reg.create_table()
    reg.update_post_year(2025)
    reg.update_post_year(2027)
    assert reg.is_employee_enrolled("E6", 2025) is True
    assert reg.is_employee_enrolled("E7", 2026) is False
    assert reg.is_employee_enrolled("E7", 2027) is True


def test_registry_sql_generation():
    stm = SQLTemplateManager()
    sql = stm.render_template(SQLTemplateManager.ENROLLMENT_REGISTRY_FROM_EVENTS, year=2030)
    assert "2030" in sql


def test_concurrent_registry_access(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    _setup_db(db_path)

    mgr = DatabaseConnectionManager(db_path=db_path)
    reg1 = EnrollmentRegistry(mgr)
    reg2 = EnrollmentRegistry(mgr)

    assert reg1.create_table()
    assert reg2.create_for_year(2025)
