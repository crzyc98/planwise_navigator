"""Unit tests for SimulationLogWriter."""


from planalign_api.services.simulation.log_writer import SimulationLogWriter


def test_creates_log_file(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("debug", "hello")
    finally:
        writer.close()
    assert (tmp_path / "simulation.log").exists()


def test_line_format_contains_severity_and_message(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("error", "something broke")
    finally:
        writer.close()
    content = (tmp_path / "simulation.log").read_text()
    assert "[ERROR]" in content
    assert "something broke" in content


def test_severity_mapping_debug_becomes_info(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("debug", "verbose detail")
    finally:
        writer.close()
    content = (tmp_path / "simulation.log").read_text()
    assert "[INFO]" in content


def test_severity_mapping_warning(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("warning", "watch out")
    finally:
        writer.close()
    content = (tmp_path / "simulation.log").read_text()
    assert "[WARNING]" in content


def test_severity_mapping_error(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("error", "bad thing")
    finally:
        writer.close()
    content = (tmp_path / "simulation.log").read_text()
    assert "[ERROR]" in content


def test_multiple_lines_written_in_order(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("debug", "first")
        writer.write_line("warning", "second")
        writer.write_line("error", "third")
    finally:
        writer.close()
    lines = (tmp_path / "simulation.log").read_text().splitlines()
    assert len(lines) == 3
    assert "first" in lines[0]
    assert "second" in lines[1]
    assert "third" in lines[2]


def test_line_ends_with_newline(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("debug", "msg")
    finally:
        writer.close()
    raw = (tmp_path / "simulation.log").read_bytes()
    assert raw.endswith(b"\n")


def test_timestamp_format_in_line(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("debug", "ts check")
    finally:
        writer.close()
    content = (tmp_path / "simulation.log").read_text()
    # ISO UTC format: 2025-01-15T10:30:00.123456Z
    assert "T" in content and "Z [" in content


def test_close_is_idempotent(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    writer.write_line("debug", "once")
    writer.close()
    writer.close()  # Must not raise


def test_write_after_close_is_silent(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    writer.close()
    writer.write_line("debug", "after close")  # Must not raise
    content = (tmp_path / "simulation.log").read_text()
    assert "after close" not in content


def test_creates_parent_directory_if_missing(tmp_path):
    run_dir = tmp_path / "runs" / "some-run-id"
    assert not run_dir.exists()
    writer = SimulationLogWriter(run_dir)
    try:
        writer.write_line("debug", "created dir")
    finally:
        writer.close()
    assert run_dir.exists()
    assert (run_dir / "simulation.log").exists()


def test_unknown_severity_defaults_to_info(tmp_path):
    writer = SimulationLogWriter(tmp_path)
    try:
        writer.write_line("unknown_level", "fallback")
    finally:
        writer.close()
    content = (tmp_path / "simulation.log").read_text()
    assert "[INFO]" in content
    assert "fallback" in content
