"""凍結基準の版付き履歴を判別する。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

ASPECT_NAMES = frozenset({"declaration", "movement_policy", "external_snapshots"})
REQUIRED_MOVEMENT_TRIGGERS = frozenset(
    {
        "baseline_set",
        "baseline_value",
        "declaration_location",
        "frozen_target_mapping",
        "identity_granularity",
        "identifier_interpretation",
    }
)
SNAPSHOT_REF_PREFIX = "contracts/tenant_boundary/history-snapshots/"
RESERVED_APPROVAL_TOKENS = frozenset(
    {"PENDING", "TODO", "TBD", "未承認", "未定", "レビュー待ち"}
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ACCEPTANCE_ID_RE = re.compile(r"[^/#\s]+/[^/#\s]+#[1-9][0-9]*")
_REPOSITORY_FULL_NAME_RE = re.compile(r"[^/#\s]+/[^/#\s]+")


class ContractError(ValueError):
    """凍結履歴契約の不整合を表す。"""


@dataclass(frozen=True)
class HistoryRecord:
    """schema 版を確定した履歴 record を表す。

    Attributes:
        schema_version: record の schema 版。
        value: JSON から読んだ record の生の値。
    """

    schema_version: int
    value: Mapping[str, Any]


@dataclass(frozen=True)
class V2Transition:
    """v2 record と照合する受理前後の実内容を表す。

    Attributes:
        before: 比較元から得た受理前の実内容。
        after: HEAD から得た受理後の実内容。
        base_snapshot_root: 比較元の snapshot ディレクトリ。
        head_snapshot_root: HEAD の snapshot ディレクトリ。
    """

    before: Mapping[str, Any]
    after: Mapping[str, Any]
    base_snapshot_root: Path
    head_snapshot_root: Path


@dataclass(frozen=True)
class EvaluationSide:
    """一方の revision にある宣言・定義・実装を表す。

    Attributes:
        declaration: 当該 revision の基準宣言の内容。
        movement_policy: 当該 revision の movement policy の内容。
        implementations: 外部実装のパスから内容へのマップ。
        snapshot_root: 当該 revision の snapshot ディレクトリ。
    """

    declaration: Mapping[str, Any]
    movement_policy: Mapping[str, Any]
    implementations: Mapping[str, bytes]
    snapshot_root: Path


@dataclass(frozen=True)
class RoleSeparatedEvaluation:
    """比較元の宣言を決定元として導出した遷移を表す。

    Attributes:
        targets: 比較元の宣言から得た検査対象。
        transition: 比較元から before、HEAD から after を作った実遷移。
        moved: 実遷移が基準移動を含むか。
    """

    targets: tuple[str, ...]
    transition: V2Transition
    moved: bool


@dataclass(frozen=True)
class FrozenAssetState:
    """movement 判定に使う 1 資産の実状態を表す。

    Attributes:
        declaration_location: 基準宣言が置かれている安定した位置。
        declaration: 当該位置にある基準宣言の実内容。
    """

    declaration_location: str
    declaration: Mapping[str, Any]


@dataclass(frozen=True)
class RepositoryMovementEvaluation:
    """比較元と HEAD の資産集合から導出した movement を表す。

    Attributes:
        scanned_assets: 比較元側と HEAD 側の和集合として走査した資産名。
        declared_triggers: 比較元が宣言した trigger。下限外の値も保持する。
        triggered_tokens: 実状態の差分から発火した普遍下限 token。
    """

    scanned_assets: tuple[str, ...]
    declared_triggers: frozenset[str]
    triggered_tokens: frozenset[str]

    @property
    def moved(self) -> bool:
        """実状態に movement があるかを返す。"""
        return bool(self.triggered_tokens)


class EvaluationMode(StrEnum):
    """凍結履歴の評価モードを表す。"""

    INVARIANT = "invariant"
    PR_ACCEPTANCE = "pr_acceptance"


@dataclass(frozen=True)
class PullRequestEvent:
    """PR 受理モードに必要な GitHub event 情報を表す。"""

    repository_full_name: str
    number: int
    base_ref: str
    base_sha: str
    head_sha: str

    @property
    def acceptance_id(self) -> str:
        """event から安定した受理 ID を導出する。"""
        return derive_acceptance_id(self.repository_full_name, self.number)


@dataclass(frozen=True)
class EvaluationContext:
    """環境から強制した評価モードと PR event を表す。"""

    mode: EvaluationMode
    pull_request: PullRequestEvent | None


def parse_history(
    base_history: object,
    head_history: object,
    *,
    v2_transitions: Sequence[V2Transition] = (),
    location: str = "baseline_control.history",
) -> tuple[HistoryRecord, ...]:
    """比較元 prefix を保護し、HEAD の履歴 record の版を確定する。

    比較元の履歴はその時点の信頼根として扱い、HEAD の同じ位置にある生 JSON
    値との同一性だけを検査する。比較元 prefix より後ろでは、明示的な v2
    record だけを受理し、対応する実内容と snapshot に照らして内容を検査する。

    Args:
        base_history: 比較元資産の history。
        head_history: HEAD 資産の history。
        v2_transitions: 追記された v2 record と同じ順序の実遷移。
        location: エラー表示用の位置。

    Returns:
        schema 版を確定した HEAD の履歴 record。

    Raises:
        ContractError: 履歴、prefix、v2 の版または内容が不正な場合。
    """
    base_records = _history_array(base_history, f"比較元.{location}")
    head_records = _history_array(head_history, f"HEAD.{location}")
    prefix_length = len(base_records)

    if len(head_records) < prefix_length or not _json_deep_equal(
        head_records[:prefix_length], base_records
    ):
        raise ContractError(f"{location}: 比較元の履歴 prefix は変更・削除できない")

    parsed: list[HistoryRecord] = []
    for index, raw_record in enumerate(head_records[:prefix_length]):
        record = _record_object(raw_record, f"{location}[{index}]")
        parsed.append(HistoryRecord(schema_version=1, value=record))

    appended_records: list[tuple[int, Mapping[str, Any]]] = []
    for index, raw_record in enumerate(head_records[prefix_length:], start=prefix_length):
        record_location = f"{location}[{index}]"
        record = _record_object(raw_record, record_location)
        if "record_schema_version" not in record:
            raise ContractError(f"{record_location}: record_schema_version が必要")
        version = record["record_schema_version"]
        if type(version) is not int or version != 2:
            raise ContractError(
                f"{record_location}: prefix 以後は record_schema_version 2 が必要"
            )
        appended_records.append((index, record))

    if len(v2_transitions) != len(appended_records):
        raise ContractError(
            f"{location}: v2 record と実遷移の件数が不一致: "
            f"records={len(appended_records)}, transitions={len(v2_transitions)}"
        )
    for (index, record), transition in zip(
        appended_records,
        v2_transitions,
        strict=True,
    ):
        _validate_v2_record(record, transition, f"{location}[{index}]")
        parsed.append(HistoryRecord(schema_version=2, value=record))

    return tuple(parsed)


def derive_role_separated_evaluation(
    base: EvaluationSide,
    head: EvaluationSide,
) -> RoleSeparatedEvaluation:
    """比較元と HEAD の役割を混ぜずに実遷移を導出する。

    対象集合は比較元の宣言だけから決める。before は比較元の定義と実装、
    after は HEAD の定義と実装から作り、HEAD の宣言による対象縮小を拒否する。

    Args:
        base: 比較元の宣言・定義・実装。
        head: HEAD の宣言・定義・実装。

    Returns:
        役割を分離して導出した評価結果。

    Raises:
        ContractError: 対象宣言が不正、HEAD が対象を縮小した、または対象実装が
            解決できない場合。
    """
    _declared_movement_triggers(
        base.movement_policy,
        "比較元.movement_policy",
    )
    base_targets = _declared_target_paths(base.declaration, "比較元.declaration")
    head_targets = _declared_target_paths(head.declaration, "HEAD.declaration")
    removed = sorted(set(base_targets) - set(head_targets))
    if removed:
        raise ContractError(f"HEAD の宣言で比較元の対象集合を縮小できない: {removed}")

    before = {
        "declaration": copy.deepcopy(dict(base.declaration)),
        "movement_policy": copy.deepcopy(dict(base.movement_policy)),
        "external_snapshots": _implementation_snapshots(
            base_targets,
            base.implementations,
            "比較元.implementations",
        ),
    }
    after = {
        "declaration": copy.deepcopy(dict(head.declaration)),
        "movement_policy": copy.deepcopy(dict(head.movement_policy)),
        # HEAD が対象を自己縮小できないよう、ここでも比較元の対象集合を使う。
        "external_snapshots": _implementation_snapshots(
            base_targets,
            head.implementations,
            "HEAD.implementations",
        ),
    }
    transition = V2Transition(
        before=before,
        after=after,
        base_snapshot_root=base.snapshot_root,
        head_snapshot_root=head.snapshot_root,
    )
    return RoleSeparatedEvaluation(
        targets=base_targets,
        transition=transition,
        moved=bool(derive_aspects(before, after)),
    )


def evaluate_repository_movement(
    base_assets: Mapping[str, FrozenAssetState],
    head_assets: Mapping[str, FrozenAssetState],
    base_movement_policy: Mapping[str, Any],
) -> RepositoryMovementEvaluation:
    """比較元の trigger 宣言を決定元として資産の実状態を比較する。

    走査対象は比較元側と HEAD 側の資産集合の和集合とする。比較元にあった
    資産の削除は、その記録形式を決めずに不合格とする。HEAD に追加された
    資産も構造を検査し、資産集合の movement として扱う。

    Args:
        base_assets: 比較元の資産名から実状態へのマップ。
        head_assets: HEAD の資産名から実状態へのマップ。
        base_movement_policy: 比較元が宣言した movement policy。

    Returns:
        和集合の走査結果と実差分から導出した movement。

    Raises:
        ContractError: 比較元の trigger 宣言または資産の実状態が不正か、
            比較元にあった資産が HEAD から削除された場合。
    """
    declared_triggers = _declared_movement_triggers(
        base_movement_policy,
        "比較元.movement_policy",
    )
    base_names = set(base_assets)
    head_names = set(head_assets)
    scanned_assets = tuple(sorted(base_names | head_names))
    deleted_assets = sorted(base_names - head_names)
    if deleted_assets:
        raise ContractError(f"比較元に存在した資産を削除できない: {deleted_assets}")

    triggered_tokens: set[str] = set()
    if base_names != head_names:
        triggered_tokens.add("baseline_set")

    for asset_name in scanned_assets:
        head_axes = _movement_axis_values(
            head_assets[asset_name],
            f"HEAD.{asset_name}",
        )
        if asset_name not in base_assets:
            continue
        base_axes = _movement_axis_values(
            base_assets[asset_name],
            f"比較元.{asset_name}",
        )
        triggered_tokens.update(
            token
            for token in REQUIRED_MOVEMENT_TRIGGERS - {"baseline_set"}
            if not _json_deep_equal(base_axes[token], head_axes[token])
        )

    return RepositoryMovementEvaluation(
        scanned_assets=scanned_assets,
        declared_triggers=declared_triggers,
        triggered_tokens=frozenset(triggered_tokens),
    )


def validate_movement_record_requirement(
    evaluation: RepositoryMovementEvaluation,
    appended_record_count: int,
) -> None:
    """movement の有無と追記 record 件数が一致することを検査する。

    Args:
        evaluation: 資産の実状態から導出した movement。
        appended_record_count: 比較元 prefix より後ろの record 件数。

    Raises:
        ContractError: movement に対して record が不足または過剰な場合。
    """
    _validate_movement_record_count(
        evaluation.moved,
        appended_record_count,
        "repository.history",
    )


def _validate_movement_record_count(
    moved: bool,
    appended_record_count: int,
    location: str,
) -> None:
    """movement と追記 record 件数の対応を一箇所で検査する。"""
    if type(appended_record_count) is not int or appended_record_count < 0:
        raise ContractError("追記 record 件数は 0 以上の整数が必要")
    expected_count = 1 if moved else 0
    if appended_record_count != expected_count:
        raise ContractError(
            f"{location}: movement と追記 record 件数が不一致: "
            f"moved={moved}, records={appended_record_count}"
        )


def resolve_evaluation_context() -> EvaluationContext:
    """環境変数から評価モードを強制し、必要なら PR event を読む。

    `GITHUB_EVENT_NAME` が `pull_request` の場合は、event 情報の不足を理由に
    不変量モードへ落とさず必ず例外にする。それ以外は不変量モードとする。

    Returns:
        強制された評価コンテキスト。

    Raises:
        ContractError: PR コンテキストで event 情報を完全に読めない場合。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return EvaluationContext(EvaluationMode.INVARIANT, None)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path is None or not event_path.strip():
        raise ContractError("PR コンテキストでは GITHUB_EVENT_PATH が必要")
    return EvaluationContext(
        EvaluationMode.PR_ACCEPTANCE,
        _read_pull_request_event(Path(event_path)),
    )


def validate_current_history(
    base_history: object,
    head_history: object,
    *,
    evaluation: RoleSeparatedEvaluation | None = None,
    head_parents: Sequence[str] = (),
    location: str = "baseline_control.history",
) -> tuple[HistoryRecord, ...]:
    """強制されたモードで履歴の不変量または PR 受理を検査する。

    Args:
        base_history: 比較元資産の history。
        head_history: HEAD 資産の history。
        evaluation: 役割分担に従って導出した実遷移。
        head_parents: PR 受理対象 HEAD の親 SHA。第一親、第二親の順。
        location: エラー表示用の位置。

    Returns:
        検証済みの履歴 record。

    Raises:
        ContractError: PR event、merge 親、遷移、記録、または acceptance ID が
            不正な場合。
    """
    context = resolve_evaluation_context()
    if context.mode is EvaluationMode.INVARIANT:
        return parse_history(base_history, head_history, location=location)

    event = context.pull_request
    if event is None:
        raise ContractError("PR 受理モードの event 情報が無い")
    _validate_pull_request_merge(event, head_parents)
    if evaluation is None:
        raise ContractError("PR 受理モードでは実遷移の評価結果が必要")

    base_records = _history_array(base_history, f"比較元.{location}")
    head_records = _history_array(head_history, f"HEAD.{location}")
    appended_count = len(head_records) - len(base_records)
    _validate_movement_record_count(
        evaluation.moved,
        appended_count,
        location,
    )

    transitions = (evaluation.transition,) if evaluation.moved else ()
    records = parse_history(
        base_history,
        head_history,
        v2_transitions=transitions,
        location=location,
    )
    if evaluation.moved:
        record = records[-1].value
        actual_acceptance_id = _validate_acceptance_id(
            record.get("acceptance_id"),
            f"{location}[-1].acceptance_id",
        )
        if actual_acceptance_id != event.acceptance_id:
            raise ContractError(
                f"{location}[-1].acceptance_id: GitHub event からの導出値と不一致"
            )
    return records


def derive_acceptance_id(repository_full_name: str, pull_request_number: int) -> str:
    """リポジトリ名と PR 番号から受理 ID を導出する。

    Args:
        repository_full_name: `owner/repository` 形式のリポジトリ完全名。
        pull_request_number: 正の PR 番号。

    Returns:
        `{repository.full_name}#{pull_request.number}` 形式の受理 ID。

    Raises:
        ContractError: リポジトリ名または PR 番号が不正な場合。
    """
    if _REPOSITORY_FULL_NAME_RE.fullmatch(repository_full_name) is None:
        raise ContractError("repository.full_name は owner/repository 形式が必要")
    if type(pull_request_number) is not int or pull_request_number <= 0:
        raise ContractError("pull_request.number は正の整数が必要")
    return f"{repository_full_name}#{pull_request_number}"


def derive_aspects(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> frozenset[str]:
    """受理前後の実内容から変更された aspect を導出する。

    Args:
        before: 比較元から得た受理前の実内容。
        after: HEAD から得た受理後の実内容。

    Returns:
        実際に変更された aspect の集合。

    Raises:
        ContractError: 実内容のキー集合が不正な場合。
    """
    _strict_keys(before, ASPECT_NAMES, "before")
    _strict_keys(after, ASPECT_NAMES, "after")
    return frozenset(
        aspect
        for aspect in ASPECT_NAMES
        if not _json_deep_equal(before[aspect], after[aspect])
    )


def _declared_movement_triggers(
    movement_policy: Mapping[str, Any],
    location: str,
) -> frozenset[str]:
    """比較元宣言から trigger を取得し、普遍下限を検査する。"""
    raw_triggers = _array(
        movement_policy.get("movement_triggers"),
        f"{location}.movement_triggers",
    )
    triggers = frozenset(
        _nonempty_string(trigger, f"{location}.movement_triggers[]")
        for trigger in raw_triggers
    )
    if len(triggers) != len(raw_triggers):
        raise ContractError(f"{location}.movement_triggers: 値を重複できない")
    missing = REQUIRED_MOVEMENT_TRIGGERS - triggers
    if missing:
        raise ContractError(
            f"{location}.movement_triggers: 普遍下限が不足: {sorted(missing)}"
        )
    return triggers


def _movement_axis_values(
    asset: FrozenAssetState,
    location: str,
) -> dict[str, object]:
    """資産の実内容から普遍下限 5 軸の比較値を取り出す。"""
    if not isinstance(asset, FrozenAssetState):
        raise ContractError(f"{location}: FrozenAssetState が必要")
    declaration_location = _nonempty_string(
        asset.declaration_location,
        f"{location}.declaration_location",
    )
    declaration = _mapping(asset.declaration, f"{location}.declaration")
    identity = _mapping(
        declaration.get("identity"),
        f"{location}.declaration.identity",
    )
    current_identifiers = _nonempty_string_array(
        identity.get("current_identifiers"),
        f"{location}.declaration.identity.current_identifiers",
    )
    scheme = _nonempty_string(
        identity.get("scheme"),
        f"{location}.declaration.identity.scheme",
    )
    field = _nonempty_string(
        identity.get("field"),
        f"{location}.declaration.identity.field",
    )
    no_baseline_marker = _nonempty_string(
        identity.get("no_baseline_marker"),
        f"{location}.declaration.identity.no_baseline_marker",
    )
    projection = _mapping(
        identity.get("frozen_projection"),
        f"{location}.declaration.identity.frozen_projection",
    )
    external_files = tuple(
        _nonempty_string(
            path,
            f"{location}.declaration.identity.frozen_projection.external_files[]",
        )
        for path in _array(
            projection.get("external_files"),
            f"{location}.declaration.identity.frozen_projection.external_files",
        )
    )
    if not external_files:
        raise ContractError(
            f"{location}.declaration.identity.frozen_projection.external_files: "
            "空にできない"
        )
    if len(external_files) != len(set(external_files)):
        raise ContractError(
            f"{location}.declaration.identity.frozen_projection.external_files: "
            "値を重複できない"
        )
    return {
        "baseline_value": current_identifiers,
        "declaration_location": declaration_location,
        "frozen_target_mapping": external_files,
        "identity_granularity": (scheme, field),
        "identifier_interpretation": no_baseline_marker,
    }


def _declared_target_paths(
    declaration: Mapping[str, Any],
    location: str,
) -> tuple[str, ...]:
    """基準宣言から順序付き外部実装対象を取得する。"""
    identity = _mapping(declaration.get("identity"), f"{location}.identity")
    projection = _mapping(
        identity.get("frozen_projection"),
        f"{location}.identity.frozen_projection",
    )
    raw_targets = _array(
        projection.get("external_files"),
        f"{location}.identity.frozen_projection.external_files",
    )
    targets = tuple(
        _nonempty_string(
            item,
            f"{location}.identity.frozen_projection.external_files[]",
        )
        for item in raw_targets
    )
    if not targets:
        raise ContractError(f"{location}: external_files は空にできない")
    if len(targets) != len(set(targets)):
        raise ContractError(f"{location}: external_files を重複できない")
    return targets


def _implementation_snapshots(
    targets: Sequence[str],
    implementations: Mapping[str, bytes],
    location: str,
) -> list[dict[str, str]]:
    """決定済み対象集合について実装内容から snapshot 参照を導出する。"""
    snapshots: list[dict[str, str]] = []
    for path in targets:
        try:
            content = implementations[path]
        except KeyError as error:
            raise ContractError(f"{location}: 対象実装を解決できない: {path}") from error
        if not isinstance(content, bytes):
            raise ContractError(f"{location}: 実装内容は bytes が必要: {path}")
        digest = hashlib.sha256(content).hexdigest()
        snapshots.append(
            {
                "path": path,
                "sha256": digest,
                "snapshot_ref": f"{SNAPSHOT_REF_PREFIX}{digest}",
            }
        )
    return snapshots


def _read_pull_request_event(path: Path) -> PullRequestEvent:
    """GitHub の pull_request event を fail-closed で読む。"""
    try:
        raw_event = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"PR event を読めない: {path}: {error}") from error
    event = _mapping(raw_event, "github_event")
    repository = _mapping(event.get("repository"), "github_event.repository")
    pull_request = _mapping(event.get("pull_request"), "github_event.pull_request")
    base = _mapping(pull_request.get("base"), "github_event.pull_request.base")
    head = _mapping(pull_request.get("head"), "github_event.pull_request.head")
    repository_full_name = _nonempty_string(
        repository.get("full_name"),
        "github_event.repository.full_name",
    )
    number = pull_request.get("number")
    # 導出関数へ渡す前にも bool を整数として受けない。
    if type(number) is not int or number <= 0:
        raise ContractError("github_event.pull_request.number: 正の整数が必要")
    derive_acceptance_id(repository_full_name, number)
    return PullRequestEvent(
        repository_full_name=repository_full_name,
        number=number,
        base_ref=_nonempty_string(base.get("ref"), "github_event.pull_request.base.ref"),
        base_sha=_nonempty_string(base.get("sha"), "github_event.pull_request.base.sha"),
        head_sha=_nonempty_string(head.get("sha"), "github_event.pull_request.head.sha"),
    )


def _validate_pull_request_merge(
    event: PullRequestEvent,
    head_parents: Sequence[str],
) -> None:
    """PR 受理対象の base と二親 merge の形を検査する。"""
    if event.base_ref != "develop":
        raise ContractError("PR 受理モードでは base.ref == develop が必要")
    if len(head_parents) != 2:
        raise ContractError("PR 受理モードの HEAD は 2 親が必要")
    if head_parents[0] != event.base_sha:
        raise ContractError("PR 受理モードの第一親は base.sha と一致する必要がある")
    if head_parents[1] != event.head_sha:
        raise ContractError("PR 受理モードの第二親は head.sha と一致する必要がある")


def validate_history_authority(assets: Mapping[str, object]) -> str:
    """履歴 authority を宣言した資産がちょうど 1 件であることを検査する。

    Args:
        assets: 資産名から JSON object へのマップ。

    Returns:
        唯一の履歴 authority である資産名。

    Raises:
        ContractError: 資産構造または宣言が不正か、authority がちょうど 1 件で
            ない場合。
    """
    authorities: list[str] = []
    for asset_name, raw_asset in assets.items():
        asset = _mapping(raw_asset, asset_name)
        control = _mapping(asset.get("baseline_control"), f"{asset_name}.baseline_control")
        authority = control.get("history_authority")
        if type(authority) is not bool:
            raise ContractError(
                f"{asset_name}.baseline_control.history_authority: bool が必要"
            )
        if authority:
            authorities.append(asset_name)

    if len(authorities) != 1:
        raise ContractError(
            "history_authority: true の資産はちょうど 1 件必要: "
            f"actual={len(authorities)}"
        )
    return authorities[0]


def _validate_v2_record(
    record: Mapping[str, Any],
    transition: V2Transition,
    location: str,
) -> None:
    """v2 record を実遷移と content-addressed snapshot に照らして検査する。"""
    _strict_keys(
        record,
        {
            "record_schema_version",
            "acceptance_id",
            "new_baseline_identifiers",
            "previous_baseline_identifiers",
            "change",
            "movement_fact",
            "reason",
            "approved_by",
            "approved_on",
        },
        location,
    )
    _validate_acceptance_id(record["acceptance_id"], f"{location}.acceptance_id")
    _nonempty_string_array(
        record["new_baseline_identifiers"],
        f"{location}.new_baseline_identifiers",
    )
    _nonempty_string_array(
        record["previous_baseline_identifiers"],
        f"{location}.previous_baseline_identifiers",
    )
    _nonempty_string(record["movement_fact"], f"{location}.movement_fact")
    _nonempty_string(record["reason"], f"{location}.reason")
    approved_by = _nonempty_string(record["approved_by"], f"{location}.approved_by")
    approved_on = _nonempty_string(record["approved_on"], f"{location}.approved_on")
    _reject_reserved_marker(approved_by, f"{location}.approved_by")
    _reject_reserved_marker(approved_on, f"{location}.approved_on")
    _validate_iso_date(approved_on, f"{location}.approved_on")

    base_snapshots = _read_snapshot_directory(
        transition.base_snapshot_root,
        f"{location}.base_snapshots",
    )
    head_snapshots = _read_snapshot_directory(
        transition.head_snapshot_root,
        f"{location}.head_snapshots",
    )
    _validate_snapshot_append_only(base_snapshots, head_snapshots, location)

    change = _mapping(record["change"], f"{location}.change")
    _strict_keys(change, {"subject", "aspect", "before", "after"}, f"{location}.change")
    _nonempty_string(change["subject"], f"{location}.change.subject")
    recorded_before = _snapshot_state(
        change["before"],
        base_snapshots,
        f"{location}.change.before",
    )
    recorded_after = _snapshot_state(
        change["after"],
        head_snapshots,
        f"{location}.change.after",
    )
    actual_before = _snapshot_state(
        transition.before,
        base_snapshots,
        f"{location}.actual.before",
    )
    actual_after = _snapshot_state(
        transition.after,
        head_snapshots,
        f"{location}.actual.after",
    )
    if not _json_deep_equal(recorded_before, actual_before):
        raise ContractError(f"{location}.change.before: 比較元の実内容と不一致")
    if not _json_deep_equal(recorded_after, actual_after):
        raise ContractError(f"{location}.change.after: HEAD の実内容と不一致")

    declared_aspects = _aspect_set(change["aspect"], f"{location}.change.aspect")
    actual_aspects = derive_aspects(actual_before, actual_after)
    if declared_aspects != actual_aspects:
        raise ContractError(
            f"{location}.change.aspect: 実差分と不一致: "
            f"declared={sorted(declared_aspects)}, actual={sorted(actual_aspects)}"
        )


def _snapshot_state(
    value: object,
    snapshots: Mapping[str, bytes],
    location: str,
) -> Mapping[str, Any]:
    """変更前後の実内容と snapshot 参照を検査する。"""
    state = _mapping(value, location)
    _strict_keys(state, ASPECT_NAMES, location)
    _mapping(state["declaration"], f"{location}.declaration")
    _mapping(state["movement_policy"], f"{location}.movement_policy")
    _external_snapshots(
        state["external_snapshots"],
        snapshots,
        f"{location}.external_snapshots",
    )
    return state


def _external_snapshots(
    value: object,
    snapshots: Mapping[str, bytes],
    location: str,
) -> tuple[Mapping[str, Any], ...]:
    """順序付き外部 snapshot 列の形式と参照先を検査する。"""
    items = _array(value, location)
    parsed: list[Mapping[str, Any]] = []
    paths: set[str] = set()
    for index, raw_item in enumerate(items):
        item_location = f"{location}[{index}]"
        item = _mapping(raw_item, item_location)
        _strict_keys(item, {"path", "sha256", "snapshot_ref"}, item_location)
        path = _nonempty_string(item["path"], f"{item_location}.path")
        digest = _nonempty_string(item["sha256"], f"{item_location}.sha256")
        snapshot_ref = _nonempty_string(
            item["snapshot_ref"],
            f"{item_location}.snapshot_ref",
        )
        if _SHA256_RE.fullmatch(digest) is None:
            raise ContractError(f"{item_location}.sha256: SHA-256 が不正")
        expected_ref = f"{SNAPSHOT_REF_PREFIX}{digest}"
        if snapshot_ref != expected_ref:
            raise ContractError(
                f"{item_location}.snapshot_ref: sha256 と末尾セグメントが不一致"
            )
        if digest not in snapshots:
            raise ContractError(f"{item_location}.snapshot_ref: snapshot を解決できない")
        if path in paths:
            raise ContractError(f"{location}: path を重複できない: {path}")
        paths.add(path)
        parsed.append(item)
    return tuple(parsed)


def _read_snapshot_directory(root: Path, location: str) -> dict[str, bytes]:
    """snapshot ディレクトリを読み、各ファイル名と内容ハッシュを照合する。"""
    if not root.exists():
        return {}
    if not root.is_dir():
        raise ContractError(f"{location}: snapshot の置き場はディレクトリが必要")
    snapshots: dict[str, bytes] = {}
    try:
        entries = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as error:
        raise ContractError(f"{location}: snapshot ディレクトリを読めない: {error}") from error
    for path in entries:
        if path.is_symlink() or not path.is_file():
            raise ContractError(f"{location}: snapshot には通常ファイルだけを置ける: {path.name}")
        if _SHA256_RE.fullmatch(path.name) is None:
            raise ContractError(f"{location}: snapshot ファイル名が SHA-256 でない: {path.name}")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ContractError(f"{location}: snapshot を読めない: {path.name}: {error}") from error
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != path.name:
            raise ContractError(f"{location}: snapshot の内容とファイル名が不一致: {path.name}")
        snapshots[path.name] = content
    return snapshots


def _validate_snapshot_append_only(
    base_snapshots: Mapping[str, bytes],
    head_snapshots: Mapping[str, bytes],
    location: str,
) -> None:
    """比較元の snapshot が HEAD で変更・削除されていないことを検査する。"""
    deleted = sorted(set(base_snapshots) - set(head_snapshots))
    if deleted:
        raise ContractError(f"{location}: 既存 snapshot を削除できない: {deleted}")
    changed = sorted(
        digest
        for digest, content in base_snapshots.items()
        if head_snapshots[digest] != content
    )
    if changed:
        raise ContractError(f"{location}: 既存 snapshot を変更できない: {changed}")


def _validate_acceptance_id(value: object, location: str) -> str:
    """受理 ID が owner/repository#正の整数形式であることを検査する。"""
    acceptance_id = _nonempty_string(value, location)
    if _ACCEPTANCE_ID_RE.fullmatch(acceptance_id) is None:
        raise ContractError(f"{location}: owner/repository#正の整数 形式が必要")
    return acceptance_id


def _validate_iso_date(value: str, location: str) -> None:
    """値が実在する拡張 ISO 8601 日付であることを検査する。"""
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ContractError(f"{location}: YYYY-MM-DD 形式が必要")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ContractError(f"{location}: 実在する ISO 8601 日付が必要") from error


def _reject_reserved_marker(value: str, location: str) -> None:
    """受理前の予約 marker を拒否する。"""
    comparable = value.strip().upper()
    if any(token in comparable for token in RESERVED_APPROVAL_TOKENS):
        raise ContractError(f"{location}: 予約 marker を使用できない")


def _aspect_set(value: object, location: str) -> frozenset[str]:
    """重複のない既知 aspect の集合を取得する。"""
    items = _array(value, location)
    aspects = frozenset(
        _nonempty_string(item, f"{location}[]") for item in items
    )
    if len(aspects) != len(items):
        raise ContractError(f"{location}: aspect を重複できない")
    if not aspects <= ASPECT_NAMES:
        raise ContractError(f"{location}: 未知の aspect がある: {sorted(aspects - ASPECT_NAMES)}")
    return aspects


def _strict_keys(
    value: Mapping[str, Any],
    expected: set[str] | frozenset[str],
    location: str,
) -> None:
    """object のキー集合を exact-set で検査する。"""
    actual = set(value)
    if actual != set(expected):
        raise ContractError(
            f"{location}: キー集合が不一致: "
            f"missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}"
        )


def _nonempty_string(value: object, location: str) -> str:
    """空白だけでない文字列を取得する。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{location}: 空白だけでない文字列が必要")
    return value


def _nonempty_string_array(value: object, location: str) -> tuple[str, ...]:
    """空でなく重複のない文字列配列を取得する。"""
    items = tuple(
        _nonempty_string(item, f"{location}[]") for item in _array(value, location)
    )
    if not items:
        raise ContractError(f"{location}: 空にできない")
    if len(items) != len(set(items)):
        raise ContractError(f"{location}: 値を重複できない")
    return items


def _array(value: object, location: str) -> list[object]:
    """配列を取得する。"""
    if not isinstance(value, list):
        raise ContractError(f"{location}: 配列が必要")
    return value


def _history_array(value: object, location: str) -> list[object]:
    """履歴配列を取得する。"""
    if not isinstance(value, list):
        raise ContractError(f"{location}: 配列が必要")
    return value


def _record_object(value: object, location: str) -> Mapping[str, Any]:
    """履歴 record の JSON object を取得する。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{location}: 文字列キーの object が必要")
    return value


def _mapping(value: object, location: str) -> Mapping[str, Any]:
    """文字列キーのマップを取得する。"""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{location}: 文字列キーの object が必要")
    return value


def _json_deep_equal(left: object, right: object) -> bool:
    """object のキー順を無視し、配列の順序を保って JSON 値を比較する。"""
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False
        return all(_json_deep_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_deep_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return type(left) is type(right) and left == right
    return type(left) is type(right) and left == right
