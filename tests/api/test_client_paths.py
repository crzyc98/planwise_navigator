"""Server paths stay out of API responses, job errors and run logs (#1311)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from planalign_api.config import get_settings
from planalign_api.models.ensemble_job import EnsembleOutput
from planalign_api.models.imports import ParquetFile
from planalign_api.routers.simulations import _parse_log_file
from planalign_api.services.client_paths import (
    PROJECT_ROOT,
    redact_server_paths,
    relative_to_root,
    relative_to_roots,
)
from planalign_api.services.file_service import FileService
from planalign_api.services.import_service import ImportService
from planalign_api.services.path_guard import PathGuardError, resolve_within_roots
from planalign_api.services.simulation.log_writer import SimulationLogWriter

pytestmark = [pytest.mark.fast]

WORKSPACE_ID = "ws-1"


def test_relative_to_root_inside_and_outside(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "data").mkdir(parents=True)

    assert relative_to_root(root / "data" / "census.parquet", root) == (
        "data/census.parquet"
    )
    # Outside the root: only the file name, never the directory.
    assert relative_to_root(tmp_path / "elsewhere" / "x.parquet", root) == "x.parquet"
    assert relative_to_root(r"C:\Users\someone\data\x.parquet", root) == "x.parquet"
    # ".." never yields a relative path that climbs out of the root.
    climbing = root / "data" / ".." / ".." / "other" / "x.parquet"
    assert relative_to_root(climbing, root) == "x.parquet"


def test_relative_to_roots_uses_the_containing_root(tmp_path: Path) -> None:
    first, second = tmp_path / "ensembles", tmp_path / "workspaces"
    database = second / "ws" / "ensembles" / "job" / "ensemble.duckdb"

    assert relative_to_roots(database, [first, second]) == (
        "ws/ensembles/job/ensemble.duckdb"
    )
    assert relative_to_roots(tmp_path / "other" / "e.duckdb", [first, second]) is None


def test_redact_labels_each_server_directory() -> None:
    workspaces = get_settings().workspaces_root.resolve()
    message = (
        f"cannot open {workspaces}/ws/scenarios/s/run.duckdb; "
        f'File "{PROJECT_ROOT}/planalign_orchestrator/x.py", line 3; '
        f"{sys.prefix}/lib/python3.12/site-packages/dbt/main.py; "
        f"{tempfile.gettempdir()}/job-1/config.yaml"
    )

    redacted = redact_server_paths(message)

    assert str(PROJECT_ROOT) not in redacted
    assert str(workspaces) not in redacted
    assert sys.prefix not in redacted
    assert tempfile.gettempdir() not in redacted
    # What is below each directory survives, so the message stays useful.
    assert "<workspaces>/ws/scenarios/s/run.duckdb" in redacted
    assert '"<app>/planalign_orchestrator/x.py", line 3' in redacted
    assert "<python>/lib/python3.12/site-packages/dbt/main.py" in redacted
    assert "<tmp>/job-1/config.yaml" in redacted


def test_redact_prefers_the_callers_label_and_whole_directories() -> None:
    job_dir = PROJECT_ROOT / "var" / "jobs" / "j1"

    assert redact_server_paths(f"{job_dir}/work/x", ((job_dir, "<job>"),)) == (
        "<job>/work/x"
    )
    # A sibling whose name merely starts the same is not the directory.
    sibling = f"{PROJECT_ROOT}-old/file.py"
    assert redact_server_paths(sibling).endswith("-old/file.py")
    assert "<app>" not in redact_server_paths(sibling)


def test_redact_handles_sentence_ends_and_leaves_other_paths_whole() -> None:
    home = Path.home()

    assert redact_server_paths(f"Permission denied: {home}. Check it.") == (
        "Permission denied: <home>. Check it."
    )
    tmp = tempfile.gettempdir()
    # The temp directory's name inside another path is not the temp directory.
    assert (
        redact_server_paths(f"/data/elsewhere{tmp}/job") == f"/data/elsewhere{tmp}/job"
    )
    assert redact_server_paths(f"{PROJECT_ROOT}{tmp}/x") == f"<app>{tmp}/x"


def test_overlong_path_is_refused_not_an_error(tmp_path: Path) -> None:
    with pytest.raises(PathGuardError):
        resolve_within_roots("x" * 300, [tmp_path / "a", tmp_path / "b"])


def test_imported_file_is_listed_by_workspace_relative_path(tmp_path: Path) -> None:
    parquet = tmp_path / WORKSPACE_ID / "data" / "imports" / "census.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"PAR1")
    service = ImportService(workspaces_root=tmp_path)
    record = ParquetFile(
        workspace_id=WORKSPACE_ID,
        import_id="i",
        filename=parquet.name,
        storage_path=str(parquet.resolve()),
        original_filename="census.csv",
    )

    shown = service.client_view(WORKSPACE_ID, record)

    assert shown.storage_path == "data/imports/census.parquet"
    # The relative path selects the same record when a client sends it back.
    service.register_external_parquet(
        workspace_id=WORKSPACE_ID,
        storage_path=str(parquet.resolve()),
        original_filename="census.csv",
        row_count=1,
        columns=["employee_id"],
        file_size_bytes=4,
    )
    found = service.find_parquet_by_path(WORKSPACE_ID, shown.storage_path)
    assert found is not None
    assert service.resolve_parquet_path(WORKSPACE_ID, found) == parquet.resolve()


def test_run_log_lines_are_redacted_when_read(tmp_path: Path) -> None:
    log = tmp_path / "simulation.log"
    log.write_text(
        "2025-01-15T10:30:00.123456Z [ERROR] "
        f'File "{PROJECT_ROOT}/planalign_cli/main.py", line 9\n',
        encoding="utf-8",
    )

    (line,) = _parse_log_file(log)

    assert line.severity == "ERROR"
    assert line.message == 'File "<app>/planalign_cli/main.py", line 9'


def test_run_log_is_written_without_server_directories(tmp_path: Path) -> None:
    writer = SimulationLogWriter(tmp_path)
    writer.write_line("error", f"dbt failed in {PROJECT_ROOT}/dbt/models/x.sql")
    writer.close()

    written = (tmp_path / SimulationLogWriter.FILENAME).read_text(encoding="utf-8")

    assert str(PROJECT_ROOT) not in written
    assert written.rstrip().endswith("[ERROR] dbt failed in <app>/dbt/models/x.sql")


def test_relative_database_resolves_under_any_allowed_root(tmp_path: Path) -> None:
    ensembles, workspaces = tmp_path / "ensembles", tmp_path / "workspaces"
    database = workspaces / "ws" / "ensembles" / "job" / "ensemble.duckdb"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"")
    ensembles.mkdir()
    roots = [ensembles, workspaces]
    output = EnsembleOutput(
        database_path=relative_to_roots(database, roots),
        ensemble_id="e",
        ensemble_scenario_id="s",
    )

    resolved = resolve_within_roots(output.database_path, roots, anchor=ensembles)

    assert resolved == database.resolve()
    with pytest.raises(PathGuardError):
        resolve_within_roots("../outside.duckdb", roots, anchor=ensembles)


@pytest.mark.parametrize(
    ("column", "bad", "expected"),
    [
        ("employee_gross_compensation", "SECRET-PAY", "cannot be parsed as a number"),
        ("active", "SECRET-FLAG", "unsupported boolean value(s)"),
    ],
)
def test_census_upload_errors_name_rows_not_values(
    tmp_path: Path, column: str, bad: str, expected: str
) -> None:
    good = "50000" if column == "employee_gross_compensation" else "true"
    rows = [good, good, bad, good, bad]
    csv = "employee_id,employee_hire_date," + column + "\n"
    csv += "".join(f"E{i},2020-01-0{i + 1},{value}\n" for i, value in enumerate(rows))
    (tmp_path / WORKSPACE_ID).mkdir()
    service = FileService(workspaces_root=tmp_path)

    with pytest.raises(ValueError) as error:
        service.save_uploaded_file(
            workspace_id=WORKSPACE_ID,
            file_content=csv.encode(),
            filename="census.csv",
        )

    message = str(error.value)
    assert expected in message
    assert "rows 3, 5" in message
    assert bad not in message
    assert str(tmp_path) not in message


def test_census_upload_error_survives_a_rowid_column(tmp_path: Path) -> None:
    csv = (
        "employee_id,employee_hire_date,employee_gross_compensation,RowID\n"
        "E1,2020-01-01,50000,A-1\nE2,2020-01-02,SECRET-PAY,C-9\n"
    )
    (tmp_path / WORKSPACE_ID).mkdir()

    with pytest.raises(ValueError) as error:
        FileService(workspaces_root=tmp_path).save_uploaded_file(
            workspace_id=WORKSPACE_ID, file_content=csv.encode(), filename="c.csv"
        )

    message = str(error.value)
    assert "cannot be parsed as a number" in message
    assert "row numbers unavailable" in message
    assert "SECRET-PAY" not in message and "C-9" not in message
