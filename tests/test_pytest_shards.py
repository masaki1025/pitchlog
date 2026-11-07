"""pytest シャードの重み付き割当と被覆契約を検査する。"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import pytest_shard_plan as shard_plan  # noqa: E402
from scripts import pytest_shards  # noqa: E402

UUID_A = "11111111-1111-1111-1111-111111111111"
UUID_B = "22222222-2222-2222-2222-222222222222"


def test_assignments_cover_every_node_exactly_once() -> None:
    """全 node が 1 つのシャードへ割り当てられ、件数和が全件と一致する。"""
    node_ids = [f"tests/test_{index}.py::test_{index}" for index in range(23)]
    assignments = shard_plan.assign_shards(node_ids, count=8)
    assert len(assignments) == len(node_ids)
    assert all(0 <= shard < 8 for shard in assignments)
    assert sum(Counter(assignments).values()) == len(node_ids)
    assert all(count > 0 for count in Counter(assignments).values())


def test_new_test_not_in_weights_is_still_assigned() -> None:
    """重みに無い新規テストも既定重みで必ず 1 回だけ割り当てる。"""
    node_ids = ["tests/old.py::test_old", "tests/new.py::test_new"]
    assignments = shard_plan.assign_shards(
        node_ids,
        count=8,
        weights={"tests/old.py::test_old": 10.0},
        default_weight=0.5,
    )
    assert len(assignments) == 2
    loads = shard_plan.estimated_loads(
        node_ids,
        assignments,
        count=8,
        weights={"tests/old.py::test_old": 10.0},
        default_weight=0.5,
    )
    assert math.isclose(sum(loads), 10.5)


def test_heavy_tests_are_spread_across_shards() -> None:
    """重いテストは同じシャードへ集めず、空いているシャードへ分散する。"""
    node_ids = [f"tests/heavy.py::test_{index}" for index in range(4)]
    weights = {node_id: 100.0 for node_id in node_ids}
    assignments = shard_plan.assign_shards(node_ids, count=8, weights=weights, default_weight=0.1)
    assert len(set(assignments)) == 4
    loads = shard_plan.estimated_loads(
        node_ids,
        assignments,
        count=8,
        weights=weights,
        default_weight=0.1,
    )
    assert max(loads) - min(loads) <= 100.0


def test_assignment_is_independent_of_collection_order() -> None:
    """同じ全件集合なら収集順が変わっても node ごとの割当は変わらない。"""
    node_ids = [f"tests/test_{index}.py::test_{index}" for index in range(40)]
    weights = {
        "tests/test_3.py::test_3": 30.0,
        "tests/test_17.py::test_17": 20.0,
        "tests/test_31.py::test_31": 10.0,
    }
    first = dict(
        zip(
            node_ids,
            shard_plan.assign_shards(node_ids, count=8, weights=weights, default_weight=0.2),
            strict=True,
        )
    )
    reversed_ids = list(reversed(node_ids))
    second = dict(
        zip(
            reversed_ids,
            shard_plan.assign_shards(reversed_ids, count=8, weights=weights, default_weight=0.2),
            strict=True,
        )
    )
    assert first == second


def test_uuid_is_normalized_for_weight_lookup() -> None:
    """乱数 UUID だけが異なる node id は同じ重みへ照合する。"""
    node_ids = [
        f"tests/test_uuid.py::test_case[{UUID_A}]",
        f"tests/test_uuid.py::test_case[{UUID_B}]",
    ]
    weights = {"tests/test_uuid.py::test_case[<uuid>]": 5.0}
    assignments = shard_plan.assign_shards(node_ids, count=8, weights=weights, default_weight=0.1)
    loads = shard_plan.estimated_loads(
        node_ids,
        assignments,
        count=8,
        weights=weights,
        default_weight=0.1,
    )
    normalized = shard_plan.normalize_identifier
    assert normalized(node_ids[0]) == normalized(node_ids[1])
    assert math.isclose(sum(loads), 10.0)


@pytest.mark.parametrize(
    "raw",
    (
        [],
        "not-a-mapping",
        {"": 1.0},
        {"tests/test.py::test": True},
        {"tests/test.py::test": 0},
        {"tests/test.py::test": -1.0},
        {"tests/test.py::test": float("nan")},
        {"tests/test.py::test": float("inf")},
    ),
)
def test_invalid_weights_are_rejected(raw: object) -> None:
    """空キー・非数値・非正値・非有限値の重みを拒否する。"""
    with pytest.raises(shard_plan.InvalidShardWeight):
        shard_plan.validated_weights(raw)


@pytest.mark.parametrize("raw", (True, 0, -1.0, float("nan"), float("inf"), "1"))
def test_invalid_default_weight_is_rejected(raw: object) -> None:
    """既定重みも有限の正数だけを受理する。"""
    with pytest.raises(shard_plan.InvalidShardWeight):
        shard_plan.validated_default_weight(raw)


def test_estimated_loads_rejects_inconsistent_assignment() -> None:
    """長さ不一致・範囲外の割当を拒否する。"""
    with pytest.raises(ValueError):
        shard_plan.estimated_loads(["tests/a.py::test_a"], [], count=8)
    with pytest.raises(ValueError):
        shard_plan.estimated_loads(["tests/a.py::test_a"], [8], count=8)


def test_repository_shard_config_is_eight_way_with_weights() -> None:
    """リポジトリの分割定義が 8 分割で、重みと既定重みを持つ。"""
    suites = pytest_shards.load_suites(ROOT)
    for name in ("harness", "backend"):
        suite = suites[name]
        assert suite.shards == 8
        assert suite.weights
        assert suite.default_weight_seconds > 0
        assert all(weight > 0 for weight in suite.weights.values())
        assert all(key.startswith("tests/") for key in suite.weights)
