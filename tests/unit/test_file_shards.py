"""The CI shard split must run every test file exactly once."""

import json
from pathlib import Path

import pytest

from tests import file_shards

ROOT = Path(__file__).resolve().parents[2]


def test_every_file_lands_in_exactly_one_shard_and_loads_balance() -> None:
    weights = {"heavy.py": 600.0, "medium.py": 300.0, "other.py": 290.0}
    files = set(weights) | {f"quick_{index}.py" for index in range(10)}
    shards = file_shards.assign_shards(files, weights, 3)
    assert shards.keys() == files
    assert set(shards.values()) == {1, 2, 3}
    assert shards["heavy.py"] != shards["medium.py"] != shards["other.py"]
    assert shards == file_shards.assign_shards(files, weights, 3)


@pytest.mark.parametrize("value", ["0/8", "9/8", "3", "a/b"])
def test_bad_shard_is_rejected(value: str) -> None:
    with pytest.raises(pytest.UsageError):
        file_shards.parse_shard(value)


def test_shards_partition_a_real_run(pytester: pytest.Pytester) -> None:
    pytester.makeconftest('pytest_plugins = ["tests.file_shards"]')
    for name in ("a", "b", "c"):
        pytester.makepyfile(
            **{f"test_{name}": "def test_1(): pass\ndef test_2(): pass"}
        )
    ran: list[str] = []
    for index in (1, 2):
        out = pytester.path / f"durations_{index}.json"
        result = pytester.runpytest_inprocess(
            f"--file-shard={index}/2", f"--store-file-durations={out}"
        )
        files = list(json.loads(out.read_text()))
        result.assert_outcomes(passed=len(files) * 2, deselected=6 - len(files) * 2)
        ran += files
    assert sorted(ran) == ["test_a.py", "test_b.py", "test_c.py"]


def test_committed_weights_name_real_test_files() -> None:
    weights = json.loads(file_shards.WEIGHTS_PATH.read_text())
    assert weights and all(seconds >= 0 for seconds in weights.values())
    missing = [name for name in weights if not (ROOT / name).is_file()]
    assert len(missing) < len(weights) / 10, missing
