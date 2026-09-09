"""失敗注入点資産の checkpoint が適用器の実行ログに実在することを検証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import ProvisionedCatalog

pytestmark = pytest.mark.requires_db

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FAILURE_INJECTION_POINTS_PATH = (
    REPOSITORY_ROOT / "contracts/authz/failure-injection-points.json"
)


def _injection_points() -> tuple[dict[str, object], ...]:
    """失敗注入点資産の行を型確認して返す。"""
    raw = json.loads(FAILURE_INJECTION_POINTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    points = raw.get("injection_points")
    assert isinstance(points, list)
    assert all(isinstance(point, dict) for point in points)
    return tuple(point for point in points if isinstance(point, dict))


def _string(value: object) -> str:
    """資産値が空でない文字列であることを確認する。"""
    assert isinstance(value, str) and value
    return value


def _positive_int(value: object) -> int:
    """資産値が正の整数であることを確認する。"""
    assert type(value) is int and value > 0
    return value


def test_failure_injection_checkpoints_exist_in_provisioning_log(
    provisioned_catalog: ProvisionedCatalog,
) -> None:
    """資産の checkpoint 全件が要素内位置を保って実行ログに含まれる。"""
    points = _injection_points()
    checkpoints = provisioned_catalog.provisioning_result.checkpoints
    checkpoint_by_id = {
        checkpoint.checkpoint_id: checkpoint for checkpoint in checkpoints
    }
    expected_ids = {_string(point["checkpoint_id"]) for point in points}

    # 適用器の全ログは失敗注入点より広い。資産の全点が含まれることだけを要求する。
    assert expected_ids <= set(checkpoint_by_id)

    for point in points:
        checkpoint = checkpoint_by_id[_string(point["checkpoint_id"])]
        assert checkpoint.step_id == _string(point["step_id"])
        assert checkpoint.operation_kind == _string(point["operation_kind"])
        assert checkpoint.element_type == _string(point["element_type"])

        position_rule = point["position_rule"]
        assert isinstance(position_rule, dict)
        expected_element_ordinal = _positive_int(
            position_rule["command_ordinal_within_element"]
        )
        same_element_checkpoints = tuple(
            candidate
            for candidate in checkpoints
            if candidate.step_id == checkpoint.step_id
            and candidate.element_type == checkpoint.element_type
            and candidate.element_id == checkpoint.element_id
        )
        assert same_element_checkpoints[expected_element_ordinal - 1] == checkpoint
