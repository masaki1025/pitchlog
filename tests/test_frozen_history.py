"""凍結基準の版付き履歴 parser を検証する。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
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
    asset_snapshots = [
        _snapshot_entry(base_root, "contracts/asset-a.json", b'{"asset":"a"}')
    ]
    _snapshot_entry(head_root, "contracts/asset-a.json", b'{"asset":"a"}')

    before: dict[str, Any] = {
        "declaration": {
            "identity": {
                "scheme": "revision_field",
                "revision": 1,
                "frozen_projection": {
                    "external_files": ["scripts/a.py", "scripts/b.py"]
                },
            }
        },
        "movement_policy": {
            "history_append_only": True,
            "movement_triggers": sorted(parser.REQUIRED_MOVEMENT_TRIGGERS),
        },
        "external_snapshots": copy.deepcopy(external_snapshots),
        "asset_snapshots": copy.deepcopy(asset_snapshots),
    }
    after: dict[str, Any] = copy.deepcopy(before)
    after["declaration"]["identity"]["revision"] = 2
    record = {
        "record_schema_version": 2,
        "acceptance_id": "openai/pitchlog#431",
        "new_baseline_identifiers": {
            "contracts/asset-a.json": ["contract_revision:2"],
            "contracts/asset-b.json": ["contract_revision:2"],
        },
        "previous_baseline_identifiers": {
            "contracts/asset-a.json": ["contract_revision:1"],
            "contracts/asset-b.json": ["contract_revision:1"],
        },
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


def _evaluation_case(tmp_path: Path) -> tuple[dict[str, Any], Any]:
    """PR受理の履歴検査に使う導出済み遷移を作る。"""
    record, transition = _v2_case(tmp_path)
    evaluation = parser.RoleSeparatedEvaluation(
        targets=tuple(
            item["path"] for item in transition.before["external_snapshots"]
        ),
        transition=transition,
        moved=bool(parser.derive_aspects(transition.before, transition.after)),
    )
    return record, evaluation


def _frozen_asset(
    name: str,
    *,
    declaration_location: str | None = None,
) -> Any:
    """普遍下限 5 軸の実状態を持つ合成資産を作る。"""
    return parser.FrozenAssetState(
        declaration_location=(
            declaration_location
            or f"contracts/tenant_boundary/{name}.json#/baseline_declaration"
        ),
        declaration={
            "identity": {
                "scheme": "revision_field",
                "field": "contract_revision",
                "current_identifiers": [f"{name}:13"],
                "no_baseline_marker": "NO_BASELINE",
                "frozen_projection": {
                    "external_files": [f"scripts/{name}.py"],
                },
            }
        },
    )


def _repository_movement_case() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """movement のない比較元・HEAD 資産と比較元 policy を作る。"""
    base_assets = {"asset-a": _frozen_asset("asset-a")}
    head_assets = copy.deepcopy(base_assets)
    movement_policy = {
        "movement_triggers": sorted(parser.REQUIRED_MOVEMENT_TRIGGERS),
    }
    return base_assets, head_assets, movement_policy


def _mutate_movement_axis(head_assets: dict[str, Any], token: str) -> None:
    """指定 token に対応する実状態だけを変異させる。"""
    if token == "baseline_set":
        head_assets["asset-b"] = _frozen_asset("asset-b")
        return
    asset = head_assets["asset-a"]
    if token == "declaration_location":
        head_assets["asset-a"] = parser.FrozenAssetState(
            declaration_location=(
                "contracts/tenant_boundary/moved/asset-a.json#/baseline_declaration"
            ),
            declaration=asset.declaration,
        )
        return
    identity = asset.declaration["identity"]
    if token == "baseline_value":
        identity["current_identifiers"] = ["asset-a:14"]
    elif token == "frozen_target_mapping":
        identity["frozen_projection"]["external_files"] = ["scripts/moved-a.py"]
    elif token == "identity_granularity":
        identity["scheme"] = "compound_key"
    elif token == "identifier_interpretation":
        identity["no_baseline_marker"] = "BASELINE_ABSENT"
    else:
        raise AssertionError(f"未知のテスト用 token: {token}")


def _write_pull_request_event(
    path: Path,
    *,
    number: int = 431,
    base_ref: str = "develop",
    base_sha: str = "base-sha",
    head_sha: str = "head-sha",
    action: str = "synchronize",
) -> None:
    """合成 GitHub pull_request event を書く。"""
    path.write_text(
        json.dumps(
            {
                "action": action,
                "repository": {"full_name": "openai/pitchlog"},
                "pull_request": {
                    "number": number,
                    "base": {"ref": base_ref, "sha": base_sha},
                    "head": {"sha": head_sha},
                },
            }
        ),
        encoding="utf-8",
    )


def _enable_pull_request_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    **event_overrides: Any,
) -> Path:
    """monkeypatch で合成 PR コンテキストを有効にする。"""
    event_path = tmp_path / "event.json"
    _write_pull_request_event(event_path, **event_overrides)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    return event_path


def _validate_pr_case(record: dict[str, Any], evaluation: Any) -> tuple[Any, ...]:
    """合成 PR の正常な二親 merge と履歴を検査する。"""
    base_history = _base_history()
    head_history = [*copy.deepcopy(base_history), record]
    return parser.validate_current_history(
        base_history,
        head_history,
        evaluation=evaluation,
        head_parents=("base-sha", "head-sha"),
    )


def _delete_nested(value: dict[str, Any], path: tuple[str, ...]) -> None:
    """合成 record の指定位置にあるキーを削除する。"""
    target: dict[str, Any] = value
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]


def _transition_request(transition: Any) -> dict[str, Any]:
    """V2Transition を CLI request の JSON 値へ変換する。"""
    return {
        "before": copy.deepcopy(transition.before),
        "after": copy.deepcopy(transition.after),
        "base_snapshot_root": str(transition.base_snapshot_root),
        "head_snapshot_root": str(transition.head_snapshot_root),
    }


def _evaluation_request(evaluation: Any) -> dict[str, Any]:
    """RoleSeparatedEvaluation を CLI request の JSON 値へ変換する。"""
    return {
        "targets": list(evaluation.targets),
        "transition": _transition_request(evaluation.transition),
        "moved": evaluation.moved,
    }


def _write_cli_request(path: Path, request: dict[str, Any]) -> None:
    """合成 CLI request を JSON ファイルへ書く。"""
    path.write_text(json.dumps(request), encoding="utf-8")


def _v2_cli_request(tmp_path: Path) -> dict[str, Any]:
    """正常な v2 履歴検査の CLI request を作る。"""
    record, transition = _v2_case(tmp_path / "v2")
    base_history = _base_history()
    return {
        "check": "history",
        "base_history": base_history,
        "head_history": [*copy.deepcopy(base_history), record],
        "v2_transitions": [_transition_request(transition)],
    }


def _current_history_cli_request(tmp_path: Path) -> dict[str, Any]:
    """正常な PR 受理履歴検査の CLI request を作る。"""
    record, evaluation = _evaluation_case(tmp_path / "current")
    base_history = _base_history()
    return {
        "check": "current_history",
        "base_history": base_history,
        "head_history": [*copy.deepcopy(base_history), record],
        "evaluation": _evaluation_request(evaluation),
        "head_parents": ["base-sha", "head-sha"],
    }


def _repository_cli_request() -> dict[str, Any]:
    """正常な資産集合 movement 検査の CLI request を作る。"""
    base_assets, head_assets, movement_policy = _repository_movement_case()

    def encode(assets: dict[str, Any]) -> dict[str, Any]:
        return {
            name: {
                "declaration_location": state.declaration_location,
                "declaration": copy.deepcopy(state.declaration),
            }
            for name, state in assets.items()
        }

    return {
        "check": "repository_movement",
        "base_assets": encode(base_assets),
        "head_assets": encode(head_assets),
        "base_movement_policy": movement_policy,
        "appended_record_count": 0,
    }


def _prepare_fail_closed_cli_case(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Callable[[], None]]:
    """設計書 7 節の各失敗点について正常入力と変異操作を作る。"""
    request_path = tmp_path / "request.json"

    def rewrite(request: dict[str, Any]) -> Callable[[], None]:
        def apply() -> None:
            _write_cli_request(request_path, request)

        return apply

    if case in {"02-pr-event", "10-acceptance-id", "11-pr-merge-shape"}:
        _enable_pull_request_mode(monkeypatch, tmp_path)
        request = _current_history_cli_request(tmp_path)
        if case == "02-pr-event":

            def mutate() -> None:
                monkeypatch.delenv("GITHUB_EVENT_PATH")

        elif case == "10-acceptance-id":
            request["head_history"][-1]["acceptance_id"] = "openai/pitchlog#999"
            mutate = rewrite(request)
        else:
            request["head_parents"] = ["base-sha"]
            mutate = rewrite(request)
    elif case in {
        "03-unknown-version",
        "04-version-required",
        "05-prefix-deep-equal",
        "07-snapshot",
        "08-aspect",
        "09-v2-approval",
    }:
        request = _v2_cli_request(tmp_path)
        record = request["head_history"][-1]
        if case == "03-unknown-version":
            record["record_schema_version"] = 3
        elif case == "04-version-required":
            del record["record_schema_version"]
        elif case == "05-prefix-deep-equal":
            request["head_history"][0]["reason"] = "changed"
        elif case == "07-snapshot":
            missing_digest = "0" * 64
            for state in (
                record["change"]["after"],
                request["v2_transitions"][0]["after"],
            ):
                snapshot = state["external_snapshots"][0]
                snapshot["sha256"] = missing_digest
                snapshot["snapshot_ref"] = (
                    "contracts/tenant_boundary/history-snapshots/"
                    f"{missing_digest}"
                )
        elif case == "08-aspect":
            record["change"]["aspect"] = []
        else:
            record["approved_by"] = "TODO: 後で"
        mutate = rewrite(request)
    elif case == "06-history-authority":
        assets = _asset_map()
        request = {"check": "history_authority", "assets": assets}
        assets["asset-0.json"]["baseline_control"]["history_authority"] = False
        mutate = rewrite(request)
    elif case == "12-deleted-base-asset":
        request = _repository_cli_request()
        del request["head_assets"]["asset-a"]
        mutate = rewrite(request)
    else:
        raise AssertionError(f"未知の fail-closed case: {case}")

    # 変異前の request を正常系として固定し、変異は呼び出し後にだけ反映する。
    if request_path.exists():
        raise AssertionError(f"request が先に作成されている: {request_path}")
    if case in {
        "03-unknown-version",
        "04-version-required",
        "05-prefix-deep-equal",
        "06-history-authority",
        "07-snapshot",
        "08-aspect",
        "09-v2-approval",
        "10-acceptance-id",
        "11-pr-merge-shape",
        "12-deleted-base-asset",
    }:
        # 上記 case は request object を先に変異したため、正常系を作り直す。
        if case in {
            "03-unknown-version",
            "04-version-required",
            "05-prefix-deep-equal",
            "07-snapshot",
            "08-aspect",
            "09-v2-approval",
        }:
            good_request = _v2_cli_request(tmp_path / "good")
        elif case == "06-history-authority":
            good_request = {"check": "history_authority", "assets": _asset_map()}
        elif case in {"10-acceptance-id", "11-pr-merge-shape"}:
            good_request = _current_history_cli_request(tmp_path / "good")
        else:
            good_request = _repository_cli_request()
    else:
        good_request = request
    _write_cli_request(request_path, good_request)
    return request_path, mutate


def _run_frozen_history_cli(request_path: Path) -> subprocess.CompletedProcess[str]:
    """実プロセスとして frozen_history.py の CLI を実行する。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(request_path)],
        check=False,
        capture_output=True,
        text=True,
    )


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
        pytest.param(("change", "after", "asset_snapshots"), id="asset-snapshots"),
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
        pytest.param("movement_fact", "PENDING", id="pending-movement-fact"),
        pytest.param("reason", "TODO: 後で", id="todo-reason"),
    ],
)
def test_reserved_v2_marker_is_rejected_after_valid_baseline(
    field: str,
    marker: str,
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record[field] = marker

    with pytest.raises(parser.ContractError, match="予約 marker"):
        _parse_v2(record, transition)


def test_real_v2_descriptions_approver_and_date_are_not_reserved_markers(
    tmp_path: Path,
) -> None:
    record, transition = _v2_case(tmp_path)
    assert _parse_v2(record, transition)
    record["approved_by"] = "山田正輝"
    record["approved_on"] = "2026-09-24"
    record["movement_fact"] = "外部実装の内容が受理前から変更された。"
    record["reason"] = "テナント境界の新しい判定規則を反映するため。"

    assert _parse_v2(record, transition)


def test_future_v2_string_field_is_checked_for_reserved_marker_by_default(
    tmp_path: Path,
) -> None:
    """将来追加される文字列欄も明示除外しない限り予約markerを拒否する。"""
    record, _ = _v2_case(tmp_path)
    record["future_description"] = "TODO: schema 拡張時に記述する"

    with pytest.raises(parser.ContractError, match="future_description.*予約 marker"):
        parser._reject_v2_reserved_markers(record, "history[0]")


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


def test_head_definition_change_cannot_skip_movement_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record, evaluation = _evaluation_case(tmp_path)
    _enable_pull_request_mode(monkeypatch, tmp_path)
    assert evaluation.moved is True
    assert _validate_pr_case(record, evaluation)
    base_history = _base_history()
    head_without_record = copy.deepcopy(base_history)

    with pytest.raises(parser.ContractError, match="movement と追記 record 件数が不一致"):
        parser.validate_current_history(
            base_history,
            head_without_record,
            evaluation=evaluation,
            head_parents=("base-sha", "head-sha"),
        )


def test_pr_context_without_event_path_does_not_fallback_to_invariant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_pull_request_mode(monkeypatch, tmp_path)
    assert parser.resolve_evaluation_context().mode is parser.EvaluationMode.PR_ACCEPTANCE
    monkeypatch.delenv("GITHUB_EVENT_PATH")

    with pytest.raises(parser.ContractError, match="GITHUB_EVENT_PATH"):
        parser.resolve_evaluation_context()


@pytest.mark.parametrize(
    "broken_condition",
    ["base-ref", "single-parent", "first-parent", "second-parent"],
)
def test_broken_pr_merge_condition_is_rejected_after_valid_baseline(
    broken_condition: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record, evaluation = _evaluation_case(tmp_path)
    event_path = _enable_pull_request_mode(monkeypatch, tmp_path)
    assert _validate_pr_case(record, evaluation)
    parents = ("base-sha", "head-sha")
    if broken_condition == "base-ref":
        _write_pull_request_event(event_path, base_ref="main")
    elif broken_condition == "single-parent":
        parents = ("base-sha",)
    elif broken_condition == "first-parent":
        parents = ("other-base", "head-sha")
    else:
        parents = ("base-sha", "other-head")
    base_history = _base_history()
    head_history = [*copy.deepcopy(base_history), record]

    with pytest.raises(parser.ContractError):
        parser.validate_current_history(
            base_history,
            head_history,
            evaluation=evaluation,
            head_parents=parents,
        )


def test_event_acceptance_id_mismatch_is_rejected_after_valid_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record, evaluation = _evaluation_case(tmp_path)
    _enable_pull_request_mode(monkeypatch, tmp_path)
    assert _validate_pr_case(record, evaluation)
    record["acceptance_id"] = "openai/pitchlog#432"

    with pytest.raises(parser.ContractError, match="GitHub event からの導出値と不一致"):
        _validate_pr_case(record, evaluation)


@pytest.mark.parametrize("event_name", ["push", "workflow_dispatch", None])
def test_non_pr_context_forces_invariant_mode(
    event_name: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    if event_name is not None:
        monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)

    context = parser.resolve_evaluation_context()

    assert context.mode is parser.EvaluationMode.INVARIANT
    assert context.pull_request is None


def test_same_pr_rerun_and_reopen_keep_acceptance_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    event_path = _enable_pull_request_mode(monkeypatch, tmp_path, action="synchronize")
    first = parser.resolve_evaluation_context().pull_request
    assert first is not None
    _write_pull_request_event(event_path, action="reopened")
    reopened = parser.resolve_evaluation_context().pull_request
    assert reopened is not None

    assert first.acceptance_id == reopened.acceptance_id == "openai/pitchlog#431"


def test_different_pr_has_different_acceptance_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    event_path = _enable_pull_request_mode(monkeypatch, tmp_path, number=431)
    first = parser.resolve_evaluation_context().pull_request
    assert first is not None
    _write_pull_request_event(event_path, number=432)
    second = parser.resolve_evaluation_context().pull_request
    assert second is not None

    assert first.acceptance_id != second.acceptance_id


@pytest.mark.parametrize(
    "token",
    [
        "baseline_set",
        "baseline_value",
        "declaration_location",
        "frozen_target_mapping",
        "identity_granularity",
        "identifier_interpretation",
    ],
)
def test_actual_axis_change_requires_movement_record(token: str) -> None:
    base_assets, head_assets, movement_policy = _repository_movement_case()
    unchanged = parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    )
    assert unchanged.moved is False
    parser.validate_movement_record_requirement(unchanged, 0)
    _mutate_movement_axis(head_assets, token)

    changed = parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    )

    assert changed.triggered_tokens == frozenset({token})
    assert changed.moved is True
    with pytest.raises(parser.ContractError, match="movement と追記 record 件数が不一致"):
        parser.validate_movement_record_requirement(changed, 0)
    parser.validate_movement_record_requirement(changed, 1)


@pytest.mark.parametrize(
    "missing_token",
    [
        "baseline_set",
        "baseline_value",
        "declaration_location",
        "frozen_target_mapping",
        "identity_granularity",
        "identifier_interpretation",
    ],
)
def test_missing_required_trigger_is_rejected_after_valid_baseline(
    missing_token: str,
) -> None:
    base_assets, head_assets, movement_policy = _repository_movement_case()
    assert not parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    ).moved
    movement_policy["movement_triggers"].remove(missing_token)

    with pytest.raises(parser.ContractError, match="普遍下限が不足"):
        parser.evaluate_repository_movement(
            base_assets,
            head_assets,
            movement_policy,
        )


def test_extra_base_declared_trigger_does_not_restrict_transition() -> None:
    base_assets, head_assets, movement_policy = _repository_movement_case()
    movement_policy["movement_triggers"].append("pass_fail_mapping")
    unchanged = parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    )
    assert unchanged.declared_triggers > parser.REQUIRED_MOVEMENT_TRIGGERS
    _mutate_movement_axis(head_assets, "baseline_value")

    changed = parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    )

    assert changed.triggered_tokens == frozenset({"baseline_value"})
    parser.validate_movement_record_requirement(changed, 1)


def test_required_movement_trigger_constant_has_exact_universal_lower_bound() -> None:
    assert parser.REQUIRED_MOVEMENT_TRIGGERS == frozenset(
        {
            "baseline_set",
            "baseline_value",
            "declaration_location",
            "frozen_target_mapping",
            "identity_granularity",
            "identifier_interpretation",
        }
    )


def test_deleted_base_asset_is_rejected_after_valid_baseline() -> None:
    base_assets, head_assets, movement_policy = _repository_movement_case()
    assert not parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    ).moved
    del head_assets["asset-a"]

    with pytest.raises(parser.ContractError, match="比較元に存在した資産を削除できない"):
        parser.evaluate_repository_movement(
            base_assets,
            head_assets,
            movement_policy,
        )


def test_scan_targets_are_union_of_base_and_head_assets() -> None:
    base_assets, head_assets, movement_policy = _repository_movement_case()
    unchanged = parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    )
    assert unchanged.scanned_assets == ("asset-a",)
    head_assets["asset-b"] = _frozen_asset("asset-b")

    changed = parser.evaluate_repository_movement(
        base_assets,
        head_assets,
        movement_policy,
    )

    assert changed.scanned_assets == ("asset-a", "asset-b")
    assert changed.triggered_tokens == frozenset({"baseline_set"})


def test_cli_returns_zero_for_valid_input(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    history = _base_history()
    _write_cli_request(
        request_path,
        {
            "check": "history",
            "base_history": history,
            "head_history": copy.deepcopy(history),
        },
    )

    result = _run_frozen_history_cli(request_path)

    assert result.returncode == 0, result.stderr
    assert "frozen-history: ok" in result.stdout


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("02-pr-event", id="02-pr-event-unavailable"),
        pytest.param("03-unknown-version", id="03-record-schema-version-unknown"),
        pytest.param("04-version-required", id="04-version-missing-or-v1"),
        pytest.param("05-prefix-deep-equal", id="05-prefix-not-deep-equal"),
        pytest.param("06-history-authority", id="06-history-authority-not-unique"),
        pytest.param("07-snapshot", id="07-snapshot-unresolvable-or-mutated"),
        pytest.param("08-aspect", id="08-aspect-not-exact-set"),
        pytest.param("09-v2-approval", id="09-v2-approval-invalid"),
        pytest.param("10-acceptance-id", id="10-acceptance-id-mismatch"),
        pytest.param("11-pr-merge-shape", id="11-pr-merge-condition-mismatch"),
        pytest.param("12-deleted-base-asset", id="12-base-asset-deleted"),
    ],
)
def test_reachable_cli_failures_exit_nonzero_and_differ_from_success(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """単体 CLI から到達可能な失敗を個別の非 zero 終了値へ写す。"""
    request_path, mutate = _prepare_fail_closed_cli_case(
        case,
        tmp_path,
        monkeypatch,
    )
    accepted = _run_frozen_history_cli(request_path)
    assert accepted.returncode == 0, accepted.stderr
    mutate()

    rejected = _run_frozen_history_cli(request_path)

    assert rejected.returncode != 0
    assert rejected.returncode != accepted.returncode
    assert "frozen-history:" in rejected.stderr

def test_unexpected_exception_is_mapped_to_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "request.json"
    _write_cli_request(
        request_path,
        {"check": "history", "base_history": [], "head_history": []},
    )

    def raise_unexpected(_: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(parser, "_execute_cli_request", raise_unexpected)

    assert parser.main([str(request_path)]) == 2
    assert "unexpected error" in capsys.readouterr().err


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
