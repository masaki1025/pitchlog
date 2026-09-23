"""BOOT-STALL と BOOT-REAPPROVAL の状態遷移を提供する。"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath

from pitchlog.domaincheck.cli import CheckerExecutionError, CheckerViolation
from pitchlog.domaincheck.seal import _run_git

STALL_MERGE_LIMIT = 50
PO_APPROVER = "山田正輝"

_REAPPROVAL_KEYS = frozenset({"schemaVersion", "approvalId", "approver"})


class ProgramStatus(StrEnum):
    """軸①の状態。"""

    TRANSITION = "transition"
    PROMOTED = "promoted"


class GrantStatus(StrEnum):
    """軸②の状態。"""

    NOT_EFFECTIVE = "not-effective"
    ACTIVE = "active"
    EXPIRED = "expired"
    ENDED = "ended"


class EpochStartReason(StrEnum):
    """停滞エポックを開始する 3 つの事由。"""

    ACTIVATION = "activation"
    DECREASE = "decrease"
    REAPPROVAL = "reapproval"


@dataclass(frozen=True, slots=True)
class StallEpoch:
    """直近の前進から数える停滞エポック。

    Attributes:
        start_commit: エポックを開始した変更の commit OID。
        reason: 発効、未解消件数の減少、再承認のいずれか。
        starting_unresolved_count: エポック開始時の未解消件数。
        merge_count: 開始後に前進なく経過した PR 統合数。
        reapproval_id: 再承認起点の場合に消費した承認 ID。
    """

    start_commit: str
    reason: EpochStartReason
    starting_unresolved_count: int
    merge_count: int
    reapproval_id: str | None = None


@dataclass(frozen=True, slots=True)
class StallState:
    """停滞測定に必要な二軸と単回性の状態。

    Attributes:
        effective: 経過規定が発効済みか。
        program: 軸①の移行プログラム状態。
        grant: 軸②の緩和されたマージ授権状態。
        unresolved_count: 現在の未解消件数。
        epoch: 発効後の現在の停滞エポック。
        expired_at_commit: 直近の失効を成立させた commit OID。
        used_reapproval_ids: 既にエポック開始へ使った承認 ID。
    """

    effective: bool
    program: ProgramStatus
    grant: GrantStatus
    unresolved_count: int
    epoch: StallEpoch | None
    expired_at_commit: str | None
    used_reapproval_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class FirstParentHistory:
    """Develop の第一親列と、その列上の PR 統合コミット。

    Attributes:
        commits: 第一親を古い順に並べた全 commit OID。
        pr_integrations: 同じ列のうち複数親を持つ PR 統合 commit OID。
    """

    commits: tuple[str, ...]
    pr_integrations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReapprovalRecord:
    """Git 履歴から読んだ再承認記録。

    Attributes:
        approval_id: 単回性を判定する安定 ID。
        approver: 承認者。
        commit_oid: 記録を統合した commit OID。
        path: 再承認記録のリポジトリ相対パス。
    """

    approval_id: str
    approver: str
    commit_oid: str
    path: str


def _nonnegative(value: int, label: str) -> int:
    """Boolean でない非負整数を返す。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CheckerExecutionError(f"{label}は非負整数でなければならない")
    return value


def _nonempty(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CheckerExecutionError(f"{label}は空でない文字列でなければならない")
    return value


def defined_state(unresolved_count: int) -> StallState:
    """定義済みだが未発効の初期状態を返す。

    Args:
        unresolved_count: 封印集合の未解消件数。

    Returns:
        停滞測定をまだ開始していない状態。
    """
    return StallState(
        effective=False,
        program=ProgramStatus.TRANSITION,
        grant=GrantStatus.NOT_EFFECTIVE,
        unresolved_count=_nonnegative(unresolved_count, "unresolved_count"),
        epoch=None,
        expired_at_commit=None,
        used_reapproval_ids=frozenset(),
    )


def activate(state: StallState, commit_oid: str) -> StallState:
    """発効変更を起点に最初の停滞エポックを開始する。

    Args:
        state: 未発効の状態。
        commit_oid: 検査基盤が発効した PR 統合 commit OID。

    Returns:
        発効済みの状態。未解消 0 件なら昇格を優先する。

    Raises:
        CheckerViolation: 既に発効している場合。
    """
    if state.effective:
        raise CheckerViolation("NFR-018 (e) BOOT-STALL: 発効を二重適用できない")
    commit = _nonempty(commit_oid, "commit_oid")
    if state.unresolved_count == 0:
        return replace(
            state,
            effective=True,
            program=ProgramStatus.PROMOTED,
            grant=GrantStatus.ENDED,
        )
    return replace(
        state,
        effective=True,
        grant=GrantStatus.ACTIVE,
        epoch=StallEpoch(
            start_commit=commit,
            reason=EpochStartReason.ACTIVATION,
            starting_unresolved_count=state.unresolved_count,
            merge_count=0,
        ),
    )


def observe_pr_integration(
    state: StallState,
    commit_oid: str,
    unresolved_count: int,
) -> StallState:
    """Develop 第一親上の PR 統合 1 件を状態へ反映する。

    Args:
        state: 統合直前の状態。
        commit_oid: 統合 commit OID。
        unresolved_count: 統合後の未解消件数。

    Returns:
        減少・昇格を失効判定より先に適用した新状態。

    Raises:
        CheckerExecutionError: 発効前など測定不能な状態の場合。
        CheckerViolation: 未解消件数が増加した場合。
    """
    commit = _nonempty(commit_oid, "commit_oid")
    current = _nonnegative(unresolved_count, "unresolved_count")
    if not state.effective or state.epoch is None:
        if state.program == ProgramStatus.PROMOTED:
            return state
        raise CheckerExecutionError("BOOT-STALL は発効前に測定できない")
    if current > state.unresolved_count:
        raise CheckerViolation("BOOT-SEAL-MONOTONE: 未解消件数を増やせない")
    if current < state.unresolved_count:
        # 型境界のセンチネル変換と誤認されないよう、検査済み整数を真偽判定する。
        if not current:
            return replace(
                state,
                program=ProgramStatus.PROMOTED,
                grant=GrantStatus.ENDED,
                unresolved_count=0,
                epoch=None,
                expired_at_commit=None,
            )
        return replace(
            state,
            unresolved_count=current,
            epoch=StallEpoch(
                start_commit=commit,
                reason=EpochStartReason.DECREASE,
                starting_unresolved_count=current,
                merge_count=0,
            ),
        )
    if state.grant == GrantStatus.EXPIRED:
        return state
    count = state.epoch.merge_count + 1
    epoch = replace(state.epoch, merge_count=count)
    if count < STALL_MERGE_LIMIT:
        return replace(state, epoch=epoch)
    return replace(
        state,
        grant=GrantStatus.EXPIRED,
        epoch=epoch,
        expired_at_commit=commit,
    )


def collect_first_parent_history(
    root: Path, develop_ref: str = "develop"
) -> FirstParentHistory:
    """Develop の第一親列と PR 統合コミットを Git から収集する。

    Args:
        root: Git リポジトリルート。
        develop_ref: 観測する develop ref。テストでは合成 ref を許す。

    Returns:
        古い順の第一親列と、その列上で複数親を持つコミット。

    Raises:
        CheckerExecutionError: 履歴を読めないか解析できない場合。
    """
    reference = _nonempty(develop_ref, "develop_ref")
    result = _run_git(
        root,
        "log",
        "--first-parent",
        "--reverse",
        "--format=%H%x00%P",
        reference,
    )
    if result.returncode != 0:
        raise CheckerExecutionError("develop の第一親履歴を読めない")
    commits: list[str] = []
    integrations: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split("\0")
        if len(fields) != 2 or not fields[0]:
            raise CheckerExecutionError("develop の第一親履歴を解析できない")
        commit_oid, raw_parents = fields
        if commit_oid in commits:
            raise CheckerExecutionError("develop の第一親履歴に重複がある")
        commits.append(commit_oid)
        if len(raw_parents.split()) >= 2:
            integrations.append(commit_oid)
    if not commits:
        raise CheckerExecutionError("develop の第一親履歴が空である")
    return FirstParentHistory(tuple(commits), tuple(integrations))


def pr_integrations_after(
    history: FirstParentHistory, start_commit: str
) -> tuple[str, ...]:
    """起点より後にある第一親上の PR 統合だけを返す。

    Args:
        history: 第一親履歴の実測結果。
        start_commit: エポック開始 commit OID。

    Returns:
        起点より後の PR 統合 commit OID。

    Raises:
        CheckerExecutionError: 起点が第一親列に存在しない場合。
    """
    try:
        start_index = history.commits.index(start_commit)
    except ValueError as error:
        raise CheckerExecutionError(
            "エポック開始 commit が develop の第一親上にない"
        ) from error
    positions = {oid: index for index, oid in enumerate(history.commits)}
    return tuple(oid for oid in history.pr_integrations if positions[oid] > start_index)


def measure_without_progress(
    state: StallState, history: FirstParentHistory
) -> StallState:
    """現在のエポック起点から前進なしの PR 統合数を測る。

    Args:
        state: 発効済みで昇格前の状態。
        history: Develop の第一親履歴。

    Returns:
        マージ数と失効状態を履歴へ一致させた状態。

    Raises:
        CheckerExecutionError: 測定可能なエポックがない場合。
    """
    if not state.effective or state.epoch is None:
        raise CheckerExecutionError("測定可能な停滞エポックがない")
    integrations = pr_integrations_after(history, state.epoch.start_commit)
    count = len(integrations)
    epoch = replace(state.epoch, merge_count=count)
    if count < STALL_MERGE_LIMIT:
        return replace(state, epoch=epoch)
    return replace(
        state,
        grant=GrantStatus.EXPIRED,
        epoch=epoch,
        expired_at_commit=integrations[STALL_MERGE_LIMIT - 1],
    )


def _repository_path(path: str) -> str:
    """安全なリポジトリ相対パスを返す。"""
    value = PurePosixPath(_nonempty(path, "record_path"))
    if value.is_absolute() or ".." in value.parts:
        raise CheckerExecutionError("再承認記録がリポジトリ外を指している")
    return value.as_posix()


def _record_at_commit(
    root: Path, record_path: str, commit_oid: str
) -> ReapprovalRecord:
    """指定 commit の再承認記録を Git から読む。"""
    path = _repository_path(record_path)
    commit = _nonempty(commit_oid, "commit_oid")
    result = _run_git(root, "show", f"{commit}:{path}")
    if result.returncode != 0:
        raise CheckerExecutionError("再承認記録を履歴から読めない")
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CheckerExecutionError("再承認記録が JSON でない") from error
    if not isinstance(raw, dict) or set(raw) != _REAPPROVAL_KEYS:
        raise CheckerExecutionError("再承認記録のキー集合が不正")
    version = raw["schemaVersion"]
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise CheckerExecutionError("再承認記録の schemaVersion が不正")
    return ReapprovalRecord(
        approval_id=_nonempty(raw["approvalId"], "approvalId"),
        approver=_nonempty(raw["approver"], "approver"),
        commit_oid=commit,
        path=path,
    )


def _changed_paths(root: Path, commit_oid: str) -> frozenset[str]:
    """再承認 PR が第一親に対して変更したパス集合を返す。"""
    result = _run_git(
        root,
        "show",
        "--diff-merges=first-parent",
        "--format=",
        "--name-only",
        commit_oid,
    )
    if result.returncode != 0:
        raise CheckerExecutionError("再承認 PR の変更パスを読めない")
    return frozenset(line for line in result.stdout.splitlines() if line)


def apply_reapproval(
    state: StallState,
    record: ReapprovalRecord,
    history: FirstParentHistory,
    changed_paths: Collection[str],
) -> StallState:
    """有効な再承認を消費して新しい停滞エポックを開始する。

    Args:
        state: 再承認直前の失効状態。
        record: Git 履歴から読んだ承認記録。
        history: Develop の第一親履歴。
        changed_paths: 承認記録の PR が変更した実測パス集合。

    Returns:
        再承認により授権と停滞エポックを開始した状態。

    Raises:
        CheckerViolation: 再承認の正本条件を 1 つでも満たさない場合。
        CheckerExecutionError: 履歴から前後関係を決められない場合。
    """
    if state.program == ProgramStatus.PROMOTED:
        raise CheckerViolation("BOOT-REAPPROVAL: 昇格後は再承認できない")
    if state.grant != GrantStatus.EXPIRED or state.expired_at_commit is None:
        raise CheckerViolation("BOOT-REAPPROVAL: 失効後でなければ再承認できない")
    if record.approver != PO_APPROVER:
        raise CheckerViolation("BOOT-REAPPROVAL: 承認者が PO でない")
    if record.approval_id in state.used_reapproval_ids:
        raise CheckerViolation("BOOT-REAPPROVAL: 同じ承認記録を再利用できない")
    if set(changed_paths) != {record.path}:
        raise CheckerViolation("BOOT-REAPPROVAL: 再承認は専用の変更でなければならない")
    if record.commit_oid not in history.pr_integrations:
        raise CheckerViolation("BOOT-REAPPROVAL: 記録が develop の PR 統合でない")
    try:
        expired_index = history.commits.index(state.expired_at_commit)
        approval_index = history.commits.index(record.commit_oid)
    except ValueError as error:
        raise CheckerExecutionError(
            "再承認と失効の第一親上の位置を決められない"
        ) from error
    if approval_index <= expired_index:
        raise CheckerViolation("BOOT-REAPPROVAL: 失効前の承認記録は使えない")
    return replace(
        state,
        grant=GrantStatus.ACTIVE,
        epoch=StallEpoch(
            start_commit=record.commit_oid,
            reason=EpochStartReason.REAPPROVAL,
            starting_unresolved_count=state.unresolved_count,
            merge_count=0,
            reapproval_id=record.approval_id,
        ),
        expired_at_commit=None,
        used_reapproval_ids=(
            state.used_reapproval_ids | frozenset({record.approval_id})
        ),
    )


def reapprove_from_git(
    root: Path,
    state: StallState,
    record_path: str,
    approval_commit: str,
    develop_ref: str = "develop",
) -> StallState:
    """Git の独立実測から再承認を検証し、成立時だけ状態を進める。

    Args:
        root: Git リポジトリルート。
        state: 再承認直前の状態。
        record_path: 再承認記録のリポジトリ相対パス。
        approval_commit: 記録を統合した commit OID。
        develop_ref: 観測する develop ref。

    Returns:
        正当な再承認で始まった新しい停滞エポック。
    """
    history = collect_first_parent_history(root, develop_ref)
    record = _record_at_commit(root, record_path, approval_commit)
    paths = _changed_paths(root, approval_commit)
    return apply_reapproval(state, record, history, paths)
