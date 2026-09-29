"""製品適用の故障注入点資産と単一 transaction 境界を静的検査する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from pitchlog.authz import product_provisioning
from pitchlog.authz.product_provisioning import ProductOperation

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ASSET_PATH = _REPOSITORY_ROOT / "contracts/authz/product/failure-injection-points.json"
_APPLICATION_STEPS_PATH = (
    _REPOSITORY_ROOT / "contracts/authz/product/application-steps.json"
)
_PROVISIONING_SOURCE_PATH = (
    _REPOSITORY_ROOT / "backend/src/pitchlog/authz/product_provisioning.py"
)
_POINT_KEYS = {
    "injection_point_id",
    "operation",
    "step_id",
    "sequence",
    "operation_kind",
    "checkpoint_id",
    "position_rule",
    "comparison_targets",
}
_EXPECTED_POINTS = (
    ("apply", 1),
    ("apply", 3),
    ("apply", 4),
    ("apply", 5),
    ("apply", 6),
    ("unapply", 3),
    ("unapply", 5),
)


def _json_object(path: Path) -> dict[str, object]:
    """JSON ファイルを文字列 key の object として読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _object_rows(value: object, label: str) -> tuple[dict[str, object], ...]:
    """値を object 配列として検証する。"""
    assert isinstance(value, list), f"{label} は配列でなければならない"
    assert all(isinstance(row, dict) for row in value), (
        f"{label} は object 配列でなければならない"
    )
    return tuple(row for row in value if isinstance(row, dict))


def _text(value: object, label: str) -> str:
    """値を空でない文字列として検証する。"""
    assert isinstance(value, str) and value, f"{label} は空でない文字列が必要"
    return value


def _positive_int(value: object, label: str) -> int:
    """値を正の整数として検証する。"""
    assert type(value) is int and value > 0, f"{label} は正の整数が必要"
    return value


def _git_blob_digest(data: bytes) -> str:
    """Git blob と同じ SHA-1 digest を計算する。"""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _actual_operation_checkpoints(
    operation: ProductOperation,
) -> tuple[tuple[int, str], ...]:
    """正規の操作計画に対して適用器が返す全記録点を列挙する。"""
    _, statements = product_provisioning._build_operation_statements(operation)
    checkpoints: list[tuple[int, str]] = []
    for sequence in range(1, 8):
        statement_count = sum(
            statement.sequence == sequence for statement in statements
        )
        for statement_number in range(1, statement_count + 1):
            checkpoint_id = product_provisioning._checkpoint_id(
                operation,
                sequence,
                statement_number,
                statement_count,
            )
            if checkpoint_id is not None:
                checkpoints.append((sequence, checkpoint_id))
    return tuple(checkpoints)


def _validate_failure_injection_asset(
    asset: dict[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    """資産・適用手順・実記録点を exact-set で照合する。"""
    document = _json_object(_ASSET_PATH) if asset is None else asset
    assert set(document) == {
        "schema_version",
        "asset_kind",
        "source_asset",
        "injection_points",
    }
    assert document["schema_version"] == 1
    assert document["asset_kind"] == "authz_product_failure_injection_points"

    source_asset = document["source_asset"]
    assert isinstance(source_asset, dict)
    assert set(source_asset) == {"path", "git_blob_digest"}
    assert source_asset["path"] == ("contracts/authz/product/application-steps.json")
    assert source_asset["git_blob_digest"] == _git_blob_digest(
        _APPLICATION_STEPS_PATH.read_bytes()
    ), "application-steps.json の Git blob digest が一致しない"

    application_steps = _json_object(_APPLICATION_STEPS_PATH)
    steps_by_operation: dict[str, dict[int, dict[str, object]]] = {}
    for operation, section_name in (
        ("apply", "application_steps"),
        ("unapply", "unapplication_steps"),
    ):
        step_rows = _object_rows(application_steps.get(section_name), section_name)
        step_by_sequence = {
            _positive_int(row.get("sequence"), f"{section_name}.sequence"): row
            for row in step_rows
        }
        assert len(step_by_sequence) == len(step_rows)
        steps_by_operation[operation] = step_by_sequence

    points = _object_rows(document.get("injection_points"), "injection_points")
    assert len(points) == 7
    assert (
        tuple(
            (
                _text(point.get("operation"), "injection_points.operation"),
                _positive_int(point.get("sequence"), "injection_points.sequence"),
            )
            for point in points
        )
        == _EXPECTED_POINTS
    )
    assert len(
        {
            _text(point.get("injection_point_id"), "injection_point_id")
            for point in points
        }
    ) == len(points)
    assert len(
        {_text(point.get("checkpoint_id"), "checkpoint_id") for point in points}
    ) == len(points)

    for point in points:
        assert set(point) == _POINT_KEYS
        operation = _text(point["operation"], "injection_points.operation")
        assert operation in {"apply", "unapply"}
        sequence = _positive_int(point["sequence"], "injection_points.sequence")
        step = steps_by_operation[operation][sequence]
        assert point["step_id"] == step.get("step_id")
        assert point["operation_kind"] == step.get("operation_kind")
        assert point["comparison_targets"] == ["product_catalog"]

        position_rule = point["position_rule"]
        assert isinstance(position_rule, dict)
        expected_position = (
            "after_statement"
            if operation == "apply" and sequence == 6
            else "after_step"
        )
        expected_keys = {"position", "failure_boundary"}
        if operation == "apply" and sequence == 6:
            expected_keys.add("statement_ordinal_within_step")
            assert position_rule["statement_ordinal_within_step"] == 1
        assert set(position_rule) == expected_keys
        assert position_rule["position"] == expected_position
        assert position_rule["failure_boundary"] == "after_current_transaction_rollback"

    for operation in ProductOperation:
        operation_points = tuple(
            point for point in points if point["operation"] == operation.value
        )
        expected_checkpoints = tuple(
            (
                _positive_int(point["sequence"], "injection_points.sequence"),
                _text(point["checkpoint_id"], "checkpoint_id"),
            )
            for point in operation_points
        )
        assert _actual_operation_checkpoints(operation) == expected_checkpoints, (
            "故障注入点の記録点が適用器と一致しない"
        )
    return points


def _validate_single_transaction_source(source: str) -> None:
    """適用末端の commit が全手順後の 1 回だけであることを検査する。"""
    tree = ast.parse(source, filename=str(_PROVISIONING_SOURCE_PATH))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_product_operation"
    ]
    assert len(functions) == 1
    function = functions[0]
    parents = {
        child: parent
        for parent in ast.walk(function)
        for child in ast.iter_child_nodes(parent)
    }
    commits = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "connection"
    ]
    assert len(commits) == 1, "製品適用は commit を 1 回だけ行わなければならない"
    ancestor = parents.get(commits[0])
    while ancestor is not None and ancestor is not function:
        assert not isinstance(ancestor, (ast.For, ast.AsyncFor, ast.While)), (
            "製品適用の commit を手順の途中に置けない"
        )
        ancestor = parents.get(ancestor)


def test_failure_injection_asset_matches_steps_digest_and_checkpoints() -> None:
    """適用5点・取り外し2点が手順資産と実記録点へ一致する。"""
    points = _validate_failure_injection_asset()

    assert sum(point["operation"] == "apply" for point in points) == 5
    assert sum(point["operation"] == "unapply" for point in points) == 2


def test_changed_application_steps_digest_is_red() -> None:
    """参照する適用手順の blob digest を変える変異を拒否する。"""
    asset = copy.deepcopy(_json_object(_ASSET_PATH))
    source_asset = asset["source_asset"]
    assert isinstance(source_asset, dict)
    source_asset["git_blob_digest"] = "0" * 40

    with pytest.raises(AssertionError, match="Git blob digest"):
        _validate_failure_injection_asset(asset)


@pytest.mark.parametrize(
    "removed_checkpoint",
    (
        "product:3:after_helper_function_creation",
        "product:3:after_policy_drop",
    ),
)
def test_removing_one_real_checkpoint_is_red(
    monkeypatch: pytest.MonkeyPatch,
    removed_checkpoint: str,
) -> None:
    """適用または取り外しの実記録点を 1 つ消す変異を拒否する。"""
    original = product_provisioning._checkpoint_id

    def without_one_checkpoint(
        operation: ProductOperation,
        sequence: int,
        statement_number: int,
        statement_count: int,
    ) -> str | None:
        checkpoint_id = original(
            operation,
            sequence,
            statement_number,
            statement_count,
        )
        return None if checkpoint_id == removed_checkpoint else checkpoint_id

    monkeypatch.setattr(
        product_provisioning,
        "_checkpoint_id",
        without_one_checkpoint,
    )
    with pytest.raises(AssertionError, match="記録点"):
        _validate_failure_injection_asset()


def test_product_apply_has_one_commit_after_all_steps() -> None:
    """正規の適用末端は全7手順を単一 transaction に閉じる。"""
    _validate_single_transaction_source(
        _PROVISIONING_SOURCE_PATH.read_text(encoding="utf-8")
    )


def test_adding_commit_inside_a_step_is_red() -> None:
    """文の実行直後へ commit を足す変異を拒否する。"""
    source = _PROVISIONING_SOURCE_PATH.read_text(encoding="utf-8")
    needle = '                    cursor.execute(statement.sql.encode("utf-8"))'
    assert source.count(needle) == 1
    mutated = source.replace(
        needle,
        f"{needle}\n                    connection.commit()",
        1,
    )

    with pytest.raises(AssertionError, match="commit を 1 回"):
        _validate_single_transaction_source(mutated)
