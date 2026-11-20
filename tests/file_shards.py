"""Split the suite across CI runners by file, so shared fixtures are built once.

The integration suite is dominated by a few files whose tests share one
simulation fixture that takes about ten minutes to build. Splitting by single
test spread those files over most shards, and every shard rebuilt the fixture.
Splitting by file builds each once.

Weights come from ``.test_durations``: seconds per test file, fixtures included,
as measured by ``--store-file-durations`` on CI (docs/guides/ci_measurements.md).
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

import pytest

WEIGHTS_PATH = Path(__file__).resolve().parents[1] / ".test_durations"
# A file with no measurement yet is assumed quick, like most of the suite.
UNKNOWN_FILE_SECONDS = 1.0


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("file shards")
    group.addoption(
        "--file-shard",
        metavar="INDEX/COUNT",
        help="Run only the test files assigned to this shard, e.g. 3/8.",
    )
    group.addoption(
        "--store-file-durations",
        type=Path,
        metavar="PATH",
        help="Write seconds per test file, fixtures included, as JSON.",
    )


def assign_shards(
    files: set[str], weights: dict[str, float], count: int
) -> dict[str, int]:
    """Give each file a shard from 1 to count: heaviest first, to the lightest."""
    loads = [0.0] * count
    shards: dict[str, int] = {}
    weigh = {name: weights.get(name, UNKNOWN_FILE_SECONDS) for name in files}
    for name in sorted(files, key=lambda name: (-weigh[name], name)):
        lightest = loads.index(min(loads))
        shards[name] = lightest + 1
        loads[lightest] += weigh[name]
    return shards


def parse_shard(value: str) -> tuple[int, int]:
    try:
        index, count = (int(part) for part in value.split("/"))
    except ValueError as error:
        raise pytest.UsageError(
            f"--file-shard takes INDEX/COUNT, got {value!r}"
        ) from error
    if not 1 <= index <= count:
        raise pytest.UsageError(f"--file-shard index out of range: {value!r}")
    return index, count


def file_of(nodeid: str) -> str:
    return nodeid.split("::")[0]


# Runs last so the split only sees tests that -m and -k left selected.
@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    value = config.getoption("--file-shard")
    if not value:
        return
    index, count = parse_shard(value)
    weights = json.loads(WEIGHTS_PATH.read_text())
    shards = assign_shards({file_of(item.nodeid) for item in items}, weights, count)
    kept = [item for item in items if shards[file_of(item.nodeid)] == index]
    dropped = [item for item in items if shards[file_of(item.nodeid)] != index]
    config.hook.pytest_deselected(items=dropped)
    items[:] = kept


class FileDurationRecorder:
    """Sum each test file's time; one instance per session."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.seconds: defaultdict[str, float] = defaultdict(float)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Setup and teardown count: that is where the shared fixtures are built.
        self.seconds[file_of(report.nodeid)] += report.duration

    def pytest_sessionfinish(self) -> None:
        totals = {name: round(value, 2) for name, value in sorted(self.seconds.items())}
        self.path.write_text(json.dumps(totals, indent=4) + "\n")


def pytest_configure(config: pytest.Config) -> None:
    if path := config.getoption("--store-file-durations"):
        config.pluginmanager.register(FileDurationRecorder(path))
