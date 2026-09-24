"""凍結基準の版付き履歴 parser を検証する。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "frozen_history.py"


def _load_parser() -> ModuleType:
    """parser をリポジトリの import 設定に依存せず読む。"""
    spec = importlib.util.spec_from_file_location("frozen_history_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parser = _load_parser()


def _v1_record(name: str) -> dict[str, Any]:
    """prefix の同一性検査に使う合成 v1 record を作る。"""
    return {
        "source_commit": f"commit-{name}",
        "change": {
            "subject": name,
            "before": {"state": "NO_BASELINE", "identifiers": []},
            "after": {"state": "PRESENT", "identifiers": [name]},
        },
        "reason": f"reason-{name}",
    }


def _snapshot_entry(root: Path, external_path: str, content: bytes) -> dict[str, str]:
    """合成 snapshot を作り、履歴へ記録する参照を返す。"""
    digest = hashlib.sha256(content).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    (root / digest).write_bytes(content)
    return {
        "path": external_path,
        "sha256": digest,
        "snapshot_ref": f"contracts/tenant_boundary/history-snapshots/{digest}",
    }


def _v2_case(tmp_path: Path) -> tuple[dict[str, Any], Any]:
    """実内容と content-addressed snapshot を持つ合成 v2 遷移を作る。"""
    base_root = tmp_path / "base-snapshots"
    head_root = tmp_path / "head-snapshots"
    external_snapshots: list[dict[str, str]] = []
    for external_path, content in (
        ("scripts/a.py", b"alpha\n"),
        ("scripts/b.py", b"beta\n"),
    ):
        external_snapshots.append(_snapshot_entry(base_root, external_path, content))
        _snapshot_entry(head_root, external_path, content)

    before: dict[str, Any] = {
        "declaration": {"identity": {"scheme": "revision_field", "revision": 1}},
        "movement_policy": {"history_append_only": True},
        "external_snapshots": copy.deepcopy(external_snapshots),
    }
    after: dict[str, Any] = copy.deepcopy(before)
    after["declaration"]["identity"]["revision"] = 2
    record = {
        "record_schema_version": 2,
        "acceptance_id": "openai/pitchlog#431",
        "new_baseline_identifiers": ["asset-a:2", "asset-b:2"],
        "previous_baseline_identifiers": ["asset-a:1", "asset-b:1"],
        "change": {
            "subject": "tenant_boundary frozen baselines",
            "aspect": ["declaration"],
            "before": copy.deepcopy(before),
            "after": copy.deepcopy(after),
        },
        "movement_fact": "基準宣言の revision を更新した",
        "reason": "新しい許可対象を受理するため",
        "approved_by": "reviewer@example.com",
        "approved_on": "2026-09-24",
    }
    transition = parser.V2Transition(
        before=before,
        after=after,
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    return record, transition


def _base_history() -> list[dict[str, Any]]:
    """順序の異なる 2 件からなる合成 prefix を作る。"""
    return [_v1_record("first"), _v1_record("second")]


def _asset_map() -> dict[str, dict[str, dict[str, bool]]]:
    """authority 宣言を持つ 7 資産の合成マップを作る。"""
    return {
        f"asset-{index}.json": {
            "baseline_control": {"history_authority": index == 0}
        }
        for index in range(7)
    }


def test_v1_only_history_is_parsed() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    head[0] = {
        "reason": "reason-first",
        "change": {
            "after": {"identifiers": ["first"], "state": "PRESENT"},
            "before": {"identifiers": [], "state": "NO_BASELINE"},
            "subject": "first",
        },
        "source_commit": "commit-first",
    }

    records = parser.parse_history(base, head)

    assert tuple(record.schema_version for record in records) == (1, 1)
    assert records[0].value == base[0]


def test_v1_prefix_and_v2_append_are_parsed(tmp_path: Path) -> None:
    base = _base_history()
    v2_record, transition = _v2_case(tmp_path)
    head = copy.deepcopy(base)
    head.append(v2_record)

    records = parser.parse_history(base, head, v2_transitions=[transition])

    assert tuple(record.schema_version for record in records) == (1, 1, 2)
    assert records[-1].value == v2_record


def test_changed_prefix_record_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0]["reason"] = "changed"

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_deleted_prefix_record_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head.pop()

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_reordered_prefix_records_are_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head.reverse()

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_replaced_prefix_record_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0] = _v1_record("replacement")

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_prefix_integer_replaced_with_equal_float_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    base[0]["contract_revision"] = 13
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0]["contract_revision"] = 13.0

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_prefix_float_replaced_with_equal_integer_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    base[0]["contract_revision"] = 13.0
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0]["contract_revision"] = 13

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_versionless_append_is_rejected_after_valid_baseline(tmp_path: Path) -> None:
    base = _base_history()
    v2_record, transition = _v2_case(tmp_path)
    head = [*copy.deepcopy(base), v2_record]
    assert parser.parse_history(base, head, v2_transitions=[transition])
    del head[-1]["record_schema_version"]

    with pytest.raises(parser.ContractError, match="record_schema_version"):
        parser.parse_history(base, head, v2_transitions=[transition])


def test_explicit_v1_append_is_rejected_after_valid_baseline(tmp_path: Path) -> None:
    base = _base_history()
    v2_record, transition = _v2_case(tmp_path)
    head = [*copy.deepcopy(base), v2_record]
    assert parser.parse_history(base, head, v2_transitions=[transition])
    head[-1]["record_schema_version"] = 1

    with pytest.raises(parser.ContractError, match="record_schema_version 2"):
        parser.parse_history(base, head, v2_transitions=[transition])


@pytest.mark.parametrize("unknown_version", [3, 0, -1, 2.0, True, "2"])
def test_unknown_version_is_rejected_after_valid_baseline(
    unknown_version: object,
    tmp_path: Path,
) -> None:
    base = _base_history()
    v2_record, transition = _v2_case(tmp_path)
    head = [*copy.deepcopy(base), v2_record]
    assert parser.parse_history(base, head, v2_transitions=[transition])
    head[-1]["record_schema_version"] = unknown_version

    with pytest.raises(parser.ContractError, match="record_schema_version 2"):
        parser.parse_history(base, head, v2_transitions=[transition])


def _parse_v2(record: dict[str, Any], transition: Any) -> tuple[Any, ...]:
    """単一の合成 v2 record を prefix に追記して検査する。"""
    base = _base_history()
    head = [*copy.deepcopy(base), record]
    return parser.parse_history(base, head, v2_transitions=[transition])


def _delete_nested(value: dict[str, Any], path: tuple[str, ...]) -> None:
    """合成 record の指定位置にあるキーを削除する。"""
    target: dict[str, Any] = value
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]


def test_acceptance_id_is_derived_from_repository_and_pull_request() -> None:
    assert parser.derive_acceptance_id("openai/pitchlog", 431) == "openai/pitchlog#431"


def test_all_aspects_are_derived_from_actual_state_components(tmp_path: Path) -> None:
    _, transition = _v2_case(tmp_path)
    before = copy.deepcopy(transition.before)

    after = copy.deepcopy(before)
    after["declaration"]["revision"] = 2
    assert parser.derive_aspects(before, after) == frozenset({"declaration"})

    after = copy.deepcopy(before)
    after["movement_policy"]["history_append_only"] = False
    assert parser.derive_aspects(before, after) == frozenset({"movement_policy"})

    after = copy.deepcopy(before)
    after["external_snapshots"].reverse()
    assert parser.derive_aspects(before, after) == frozenset({"external_snapshots"})


def test_unresolvable_snapshot_ref_is_rejected_after_valid_baseline(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    missing_digest = "0" * 64
    for state in (record["change"]["after"], transition.after):
        snapshot = state["external_snapshots"][0]
        snapshot["sha256"] = missing_digest
        snapshot["snapshot_ref"] = (
            f"contracts/tenant_boundary/history-snapshots/{missing_digest}"
        )

    with pytest.raises(parser.ContractError, match="snapshot を解決できない"):
        _parse_v2(record, transition)


def test_changed_existing_snapshot_is_rejected_after_valid_baseline(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    digest = record["change"]["before"]["external_snapshots"][0]["sha256"]
    (transition.head_snapshot_root / digest).write_bytes(b"tampered\n")

    with pytest.raises(parser.ContractError, match="内容とファイル名が不一致"):
        _parse_v2(record, transition)


def test_deleted_existing_snapshot_is_rejected_after_valid_baseline(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    digest = record["change"]["before"]["external_snapshots"][0]["sha256"]
    (transition.head_snapshot_root / digest).unlink()

    with pytest.raises(parser.ContractError, match="既存 snapshot を削除できない"):
        _parse_v2(record, transition)


def test_snapshot_ref_digest_mismatch_is_rejected_after_valid_baseline(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["change"]["after"]["external_snapshots"][0]["snapshot_ref"] = (
        f"contracts/tenant_boundary/history-snapshots/{'0' * 64}"
    )

    with pytest.raises(parser.ContractError, match="末尾セグメントが不一致"):
        _parse_v2(record, transition)


@pytest.mark.parametrize(
    "declared_aspects",
    [
        pytest.param([], id="missing"),
        pytest.param(["declaration", "movement_policy"], id="excess"),
        pytest.param(["movement_policy"], id="replaced"),
    ],
)
def test_mismatched_aspect_is_rejected_after_valid_baseline(
    declared_aspects: list[str],
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["change"]["aspect"] = declared_aspects

    with pytest.raises(parser.ContractError, match="実差分と不一致"):
        _parse_v2(record, transition)


@pytest.mark.parametrize(
    "field_path",
    [
        pytest.param(("movement_fact",), id="movement-fact"),
        pytest.param(("reason",), id="reason"),
        pytest.param(("new_baseline_identifiers",), id="new-identifiers"),
        pytest.param(("previous_baseline_identifiers",), id="previous-identifiers"),
        pytest.param(("change", "after", "declaration"), id="declaration"),
        pytest.param(("change", "after", "movement_policy"), id="movement-policy"),
        pytest.param(("change", "after", "external_snapshots"), id="external-snapshots"),
    ],
)
def test_missing_required_v2_field_is_rejected_after_valid_baseline(
    field_path: tuple[str, ...],
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    _delete_nested(record, field_path)

    with pytest.raises(parser.ContractError, match="キー集合が不一致"):
        _parse_v2(record, transition)


def test_reordered_external_snapshots_are_rejected_after_valid_baseline(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["change"]["after"]["external_snapshots"].reverse()

    with pytest.raises(parser.ContractError, match="HEAD の実内容と不一致"):
        _parse_v2(record, transition)


@pytest.mark.parametrize(
    ("field", "marker"),
    [
        pytest.param(
            "approved_by",
            "未承認(PR #78 のレビュー待ち)",
            id="copied-unapproved-marker",
        ),
        pytest.param("approved_by", "TODO: 後で", id="todo-with-description"),
        pytest.param("approved_by", "pending review", id="lowercase-pending"),
        pytest.param("approved_on", "承認日 TBD", id="tbd-approval-date"),
    ],
)
def test_reserved_approval_marker_is_rejected_after_valid_baseline(
    field: str,
    marker: str,
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record[field] = marker

    with pytest.raises(parser.ContractError, match="予約 marker"):
        _parse_v2(record, transition)


def test_real_approver_and_valid_date_are_not_reserved_markers(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["approved_by"] = "山田正輝"
    record["approved_on"] = "2026-09-24"

    assert _parse_v2(record, transition)


@pytest.mark.parametrize("invalid_approver", ["", " ", "\t\n"])
def test_empty_approver_is_rejected_after_valid_baseline(
    invalid_approver: str,
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["approved_by"] = invalid_approver

    with pytest.raises(parser.ContractError, match="空白だけでない文字列"):
        _parse_v2(record, transition)


@pytest.mark.parametrize("invalid_date", ["2026-02-30", "2026-2-3", "not-a-date"])
def test_invalid_approval_date_is_rejected_after_valid_baseline(
    invalid_date: str,
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["approved_on"] = invalid_date

    with pytest.raises(parser.ContractError, match="日付|YYYY-MM-DD"):
        _parse_v2(record, transition)


@pytest.mark.parametrize(
    "invalid_acceptance_id",
    ["openai/pitchlog", "openai/pitchlog#0", "openai#431", "openai/pitch/log#431"],
)
def test_invalid_acceptance_id_is_rejected_after_valid_baseline(
    invalid_acceptance_id: str,
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["acceptance_id"] = invalid_acceptance_id

    with pytest.raises(parser.ContractError, match="owner/repository"):
        _parse_v2(record, transition)


def test_source_commit_is_rejected_in_v2_after_valid_baseline(tmp_path: Path) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["source_commit"] = "PENDING_ACCEPTANCE"

    with pytest.raises(parser.ContractError, match="キー集合が不一致"):
        _parse_v2(record, transition)


def test_no_history_authority_is_rejected_after_valid_baseline() -> None:
    assets = _asset_map()
    assert parser.validate_history_authority(assets) == "asset-0.json"
    assets["asset-0.json"]["baseline_control"]["history_authority"] = False

    with pytest.raises(parser.ContractError, match="ちょうど 1 件"):
        parser.validate_history_authority(assets)


def test_multiple_history_authorities_are_rejected_after_valid_baseline() -> None:
    assets = _asset_map()
    assert parser.validate_history_authority(assets) == "asset-0.json"
    assets["asset-1.json"]["baseline_control"]["history_authority"] = True

    with pytest.raises(parser.ContractError, match="ちょうど 1 件"):
        parser.validate_history_authority(assets)
