"""試合ライフサイクルspikeの内容検証・投影。

製品ポートではない。既存 `POST /games/{id}/sync/events` の P2 経路へ
`game_end_declaration` の閉じた spike payload を接続する。終了確定版は
イベント列の上で単調増加し、再開は直前の確定版だけを失効させる。

`games.status` は本spikeでは更新しない。DB schema・認可 catalog・共有
operation registry を変更せず、既存の operation_events と D5 台帳だけを
監査の正とする。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, final
from uuid import UUID

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import PortWriter
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    GameReadToken,
    OperationEventReadToken,
    RecordingGenerationReadToken,
)

LIFECYCLE_FORMAT = "game-lifecycle-spike-v1"
END_ACTION = "end"
REOPEN_ACTION = "reopen"
EVENT_KIND = "game_end_declaration"
MAX_LIFECYCLE_SCAN = 512

# Game.__table__.c.keys() と同じ順序。モデル import はポートの静的検査で
# 禁止されるため、列順を値として固定し、 backend 試験で一致を照合する。
GAME_COLUMNS = (
    "id",
    "scheduled_at",
    "game_type_key",
    "game_type_category",
    "tournament_key",
    "away_team_record_id",
    "home_team_record_id",
    "plate_umpire",
    "section_label",
    "week_label",
    "day_label",
    "game_number_label",
    "started_at",
    "status",
    "applied_rules",
    "rule_override",
    "trashed_at",
    "hidden_at",
    "tenant_id",
    "import_batch_id",
)

# operation_events の読取列順。モデル import は同じ理由で禁止する。
EVENT_COLUMNS = (
    "id",
    "game_id",
    "generation",
    "d1",
    "d2",
    "d5",
    "ledger_kind",
    "event_kind",
    "payload",
    "state_diff",
    "is_tombstone",
    "replaced_at",
    "target_generation",
    "target_d1",
    "expected_version",
    "change_order",
    "legacy_row_identifier",
    "migration_unverified",
    "tenant_id",
    "import_batch_id",
    "retired_at",
)

_STATE_FIELDS = frozenset(
    {
        "state.half",
        "state.count.strikes",
        "state.count.balls",
        "state.outs",
        "state.runners",
        "state.battingOrder",
        "state.tiebreakActive",
        "state.gameEnded",
        "state.inning",
        "state.score",
    }
)
_BOARD_FIELDS = frozenset(
    {"inningScores", "hits", "errors", "strikeouts", "walks"}
)
_RUNNERS = frozenset(
    {
        "empty",
        "first",
        "second",
        "third",
        "first-second",
        "first-third",
        "second-third",
        "loaded",
    }
)
_ERROR = "試合ライフサイクルspikeを確認できません"


class SpikeEndReopenRejected(RuntimeError):
    """利用者入力・版競合によるspikeの拒否。内部破損と区別する。"""
# spike の故障注入だけが設定する。通常の製品実行では常に None。
_FAULT: dict[UUID, str] = {}


def set_fault(game_id: UUID, point: str | None) -> None:
    """Spike の故障注入点を試合単位で設定する。固定成功へは置き換えない。"""
    if type(game_id) is not UUID:
        raise ValueError("故障注入の試合 ID が不正")
    if point is None:
        _FAULT.pop(game_id, None)
        return
    if point not in {"after_lifecycle_projection"}:
        raise ValueError("未知のライフサイクル故障点")
    _FAULT[game_id] = point


def _cell(row: tuple[object, ...], columns: tuple[str, ...], name: str) -> object:
    """同期核と同じ列順規約で 1 値を読む。"""
    if len(row) != len(columns):
        raise RuntimeError(_ERROR)
    return row[columns.index(name)]


def _one(result: TenantOperationResult) -> tuple[object, ...]:
    """一意であるべき行の欠落・重複を拒否する。"""
    if type(result) is not TenantOperationResult or len(result.rows) != 1:
        raise RuntimeError(_ERROR)
    return result.rows[0]


def _mapping(value: object) -> Mapping[str, object] | None:
    """JSON object だけを返す。"""
    return value if isinstance(value, Mapping) else None


def _same(left: object, right: object) -> bool:
    """JSON 値の同一性を再帰的に比較する。"""
    if left is None or right is None:
        return left is None and right is None
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left == right
    if type(left) in (int, str) or type(right) in (int, str):
        return type(left) is type(right) and left == right
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False
        return all(_same(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    return False


def _plain(value: object) -> object:
    """Immutable な JSON 値を素の値へ戻す。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _as_int(value: object) -> int | None:
    """整数型の値だけを返す。"""
    return value if type(value) is int else None


def _canonical_decimal(value: object) -> int | None:
    """正準十進文字列だけを整数へ変換する。"""
    if type(value) is not str or value.strip() != value:
        return None
    if not value.isdecimal():
        return None
    if len(value) > 1 and value.startswith("0"):
        return None
    return int(value)


def _state(value: object) -> Mapping[str, object] | None:
    """開始済み状態の閉じた形だけを返す。"""
    state = _mapping(value)
    if state is None:
        return None
    keys = set(state)
    if keys not in (
        {"stateFields", "scoreboard"},
        {"stateFields", "scoreboard", "battingOrderBySide"},
    ):
        return None
    fields = _mapping(state.get("stateFields"))
    board = _mapping(state.get("scoreboard"))
    if fields is None or board is None:
        return None
    if set(fields) != _STATE_FIELDS or set(board) != _BOARD_FIELDS:
        return None
    if fields.get("state.half") not in ("top", "bottom"):
        return None
    if fields.get("state.runners") not in _RUNNERS:
        return None
    if type(fields.get("state.tiebreakActive")) is not bool:
        return None
    if type(fields.get("state.gameEnded")) is not bool:
        return None
    score = _mapping(fields.get("state.score"))
    if score is None or set(score) != {"home", "away"}:
        return None
    home = _canonical_decimal(score.get("home"))
    away = _canonical_decimal(score.get("away"))
    if home is None or away is None:
        return None
    inning_score = _mapping(board.get("inningScores"))
    if inning_score is None or set(inning_score) != {"home", "away"}:
        return None
    if _canonical_decimal(inning_score.get("home")) != home:
        return None
    if _canonical_decimal(inning_score.get("away")) != away:
        return None
    for key in (
        "state.count.strikes",
        "state.count.balls",
        "state.outs",
        "state.battingOrder",
        "state.inning",
    ):
        if _canonical_decimal(fields.get(key)) is None:
            return None
    for key in ("hits", "errors", "strikeouts", "walks"):
        if _canonical_decimal(board.get(key)) is None:
            return None
    cursors = state.get("battingOrderBySide")
    if cursors is not None:
        value = _mapping(cursors)
        if value is None or set(value) != {"away", "home"}:
            return None
        if _canonical_decimal(value.get("away")) is None:
            return None
        if _canonical_decimal(value.get("home")) is None:
            return None
    return state


def _score(state: Mapping[str, object]) -> tuple[int, int]:
    """状態の最終スコアを返す。"""
    fields = _mapping(state.get("stateFields"))
    if fields is None:
        raise RuntimeError(_ERROR)
    score = _mapping(fields.get("state.score"))
    if score is None:
        raise RuntimeError(_ERROR)
    home = _canonical_decimal(score.get("home"))
    away = _canonical_decimal(score.get("away"))
    if home is None or away is None:
        raise RuntimeError(_ERROR)
    return home, away


@dataclass(frozen=True, slots=True)
class LifecyclePayload:
    """spike payload の検証済み値。"""

    action: str
    version: int
    state: Mapping[str, object]
    previous: Mapping[str, object] | None = None
    target: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class LifecycleRow:
    """イベント列から読んだ 1 件のライフサイクル行。"""

    d1: int
    d5: str
    action: str
    version: int
    state: Mapping[str, object] | None
    previous: Mapping[str, object] | None = None
    target: Mapping[str, object] | None = None


def _reference(value: object) -> Mapping[str, object] | None:
    """版と D1 の参照だけを返す。"""
    ref = _mapping(value)
    if ref is None or set(ref) != {"version", "d1"}:
        return None
    version = ref.get("version")
    d1 = ref.get("d1")
    if type(version) is not int or version <= 0:
        return None
    if type(d1) is not int or d1 <= 0:
        return None
    return ref


def payload(event: SyncEvent) -> LifecyclePayload | None:
    """V7 の閉じた spike payload を返す。"""
    envelope = _mapping(event.v7)
    if envelope is None or set(envelope) != {
        "formatVersion",
        "action",
        "finalization",
    }:
        return None
    if envelope.get("formatVersion") != LIFECYCLE_FORMAT:
        return None
    action = envelope.get("action")
    finalization = _mapping(envelope.get("finalization"))
    if finalization is None or action not in (END_ACTION, REOPEN_ACTION):
        return None
    if action == END_ACTION:
        if set(finalization) != {"version", "previous", "state"}:
            return None
        previous_raw = finalization.get("previous")
        previous = None if previous_raw is None else _reference(previous_raw)
        if previous_raw is not None and previous is None:
            return None
    else:
        if set(finalization) != {"version", "target", "state"}:
            return None
        target = _reference(finalization.get("target"))
        if target is None:
            return None
        previous = None
    version = finalization.get("version")
    state = _state(finalization.get("state"))
    if type(version) is not int or version <= 0 or state is None:
        return None
    if action == END_ACTION and previous is not None:
        previous_version = _as_int(previous["version"])
        if previous_version is None or version != previous_version + 1:
            return None
    if action == END_ACTION and previous is None and version != 1:
        return None
    if action == REOPEN_ACTION:
        target_version = _as_int(target["version"])
        if target_version is None or version != target_version:
            return None
    return LifecyclePayload(
        action=str(action),
        version=version,
        state=state,
        previous=previous,
        target=None if action == END_ACTION else target,
    )


class _Runner(Protocol):
    """同一 TX の operation token 実行面。"""

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み operation を 1 件実行する。"""
        ...


def _generation(runner: _Runner, game_id: UUID) -> tuple[int, int]:
    """現行世代番号と確定水位を返す。"""
    row = _one(runner.run(RecordingGenerationReadToken(game_id)))
    generation = _cell(row, RECORDING_GENERATION_READ_COLUMNS, "generation")
    watermark = _cell(row, RECORDING_GENERATION_READ_COLUMNS, "confirmed_watermark")
    if type(generation) is not int or type(watermark) is not int:
        raise RuntimeError(_ERROR)
    return generation, watermark


def event_row(
    runner: _Runner, game_id: UUID, generation: int, d1: int
) -> dict[str, object] | None:
    """現行世代の D1 行を 1 件だけ読む。"""
    rows = runner.run(OperationEventReadToken(game_id, generation, d1)).rows
    if len(rows) != 1:
        return None
    row = rows[0]
    return {name: _cell(row, EVENT_COLUMNS, name) for name in EVENT_COLUMNS}


def _play_state(row: Mapping[str, object]) -> Mapping[str, object] | None:
    """保存済み play の after を payload から読む。再計算しない。"""
    raw = _mapping(row.get("payload"))
    if raw is None:
        return None
    version = raw.get("formatVersion")
    calculation = _mapping(raw.get("calculation"))
    if calculation is None:
        return None
    response = _mapping(calculation.get("response"))
    if response is None:
        return None
    value = _mapping(response.get("value"))
    if value is None:
        return None
    if version == "first-ball-play-v1":
        return _state(value.get("after"))
    if version in {
        "ordinary-pitch-play-v1",
        "play-prefix-play-v2",
        "play-prefix-play-v3",
    }:
        t1 = _mapping(value.get("t1"))
        return None if t1 is None else _state(t1.get("after"))
    return None


def _undo_state(row: Mapping[str, object]) -> Mapping[str, object] | None:
    """Undo 接続spikeの保存結果から after を読む。"""
    raw = _mapping(row.get("payload"))
    if raw is None or raw.get("formatVersion") != "undo-connection-spike-v1":
        return None
    result = _mapping(raw.get("result"))
    return None if result is None else _state(result.get("after"))


def _lifecycle_payload_from_row(
    row: Mapping[str, object],
) -> LifecyclePayload | None:
    """保存済み V7 が spike payload なら検証して返す。"""
    event_kind = row.get("event_kind")
    if event_kind != EVENT_KIND:
        return None
    raw = _mapping(row.get("payload"))
    if raw is None or raw.get("formatVersion") != LIFECYCLE_FORMAT:
        raise RuntimeError(_ERROR)
    # SyncEvent を作らず、同じ閉キー検査を payload 値へ適用する。
    envelope = raw
    if set(envelope) != {"formatVersion", "action", "finalization"}:
        raise RuntimeError(_ERROR)
    action = envelope.get("action")
    finalization = _mapping(envelope.get("finalization"))
    if action not in (END_ACTION, REOPEN_ACTION) or finalization is None:
        raise RuntimeError(_ERROR)
    if action == END_ACTION:
        if set(finalization) != {"version", "previous", "state"}:
            raise RuntimeError(_ERROR)
        previous_raw = finalization.get("previous")
        previous = None if previous_raw is None else _reference(previous_raw)
        if previous_raw is not None and previous is None:
            raise RuntimeError(_ERROR)
        target = None
    else:
        if set(finalization) != {"version", "target", "state"}:
            raise RuntimeError(_ERROR)
        target = _reference(finalization.get("target"))
        if target is None:
            raise RuntimeError(_ERROR)
        previous = None
    version = finalization.get("version")
    state = _state(finalization.get("state"))
    if type(version) is not int or version <= 0 or state is None:
        raise RuntimeError(_ERROR)
    d1 = row.get("d1")
    d5 = row.get("d5")
    if type(d1) is not int or type(d5) is not UUID:
        raise RuntimeError(_ERROR)
    return LifecyclePayload(
        action=str(action),
        version=version,
        state=state,
        previous=previous,
        target=target,
    )


def state_from_row(row: Mapping[str, object]) -> Mapping[str, object] | None:
    """1 イベントが表す状態を返す。状態を持たない種別は None。"""
    kind = row.get("event_kind")
    if kind == "play_input":
        return _play_state(row)
    if kind == "undo":
        return _undo_state(row)
    if kind == EVENT_KIND:
        value = _lifecycle_payload_from_row(row)
        return None if value is None else value.state
    return None


def _latest_lifecycle(
    runner: _Runner, game_id: UUID, generation: int, before_d1: int
) -> LifecycleRow | None:
    """指定 D1 より前の最新ライフサイクル行を返す。"""
    scanned = 0
    d1 = before_d1
    while d1 >= 1:
        scanned += 1
        if scanned > MAX_LIFECYCLE_SCAN:
            raise RuntimeError("ライフサイクル履歴がspikeの走査上限を超えました")
        row = event_row(runner, game_id, generation, d1)
        if row is not None:
            value = _lifecycle_payload_from_row(row)
            if value is not None:
                return LifecycleRow(
                    d1=d1,
                    d5=str(row["d5"]),
                    action=value.action,
                    version=value.version,
                    state=value.state,
                    previous=value.previous,
                    target=value.target,
                )
        d1 -= 1
    return None


def _state_before(
    runner: _Runner, game_id: UUID, generation: int, before_d1: int
) -> Mapping[str, object] | None:
    """指定 D1 以前で最後に観測できる状態を返す。"""
    scanned = 0
    d1 = before_d1
    while d1 >= 1:
        scanned += 1
        if scanned > MAX_LIFECYCLE_SCAN:
            raise RuntimeError("確定状態の走査がspikeの上限を超えました")
        row = event_row(runner, game_id, generation, d1)
        if row is not None:
            state = state_from_row(row)
            if state is not None:
                return state
        d1 -= 1
    return None


def _game_row(runner: _Runner, game_id: UUID) -> dict[str, object]:
    """対象試合の現在行を読む。"""
    row = _one(runner.run(GameReadToken(game_id)))
    return {name: _cell(row, GAME_COLUMNS, name) for name in GAME_COLUMNS}


def _content_reason(event: SyncEvent, writer: PortWriter) -> str | None:
    """内容検証の拒否理由を返す。成功は None。"""
    if event.v5 != EVENT_KIND:
        return "試合終了宣言のイベント種別ではありません"
    if type(event.d1) is not int or event.d1 <= 0:
        return "試合終了宣言の D1 が不正です"
    if type(event.v6) is not int or event.v6 < 0:
        return "試合終了宣言の D2 が不正です"
    value = payload(event)
    if value is None:
        return "試合ライフサイクルの payload が不正です"
    game_id = UUID(event.game_id)
    game = _game_row(writer, game_id)
    if game.get("id") != game_id:
        return "試合の識別を確認できません"
    if game.get("status") != "in_progress" or game.get("started_at") is None:
        return "進行中の開始済み試合ではありません"
    if any(
        game.get(key) is not None
        for key in ("trashed_at", "hidden_at", "import_batch_id")
    ):
        return "対象試合を操作できません"
    rules = _mapping(game.get("applied_rules"))
    if rules is None or rules.get("regulationInnings") != 9:
        return "9回制の試合だけを対象にします"
    home, away = _score(value.state)
    if home == away:
        return "同点の試合はこのspikeの対象外です"
    return None


@final
class SpikeEndReopenContentValidationPort:
    """spike payload と 9回制・非同時点だけを内容段階で検査する。"""

    def validate(
        self, event: SyncEvent, writer: PortWriter
    ) -> tuple[bool, str | None]:
        """Payload の閉形・試合の前提・非同時点を検査する。"""
        try:
            reason = _content_reason(event, writer)
        except (ValueError, TypeError, KeyError, RuntimeError):
            return False, "試合ライフサイクルの内容を確認できません"
        if reason is None:
            return True, None
        return False, reason


def _inserted_row(
    writer: PortWriter, event: SyncEvent
) -> tuple[int, int, dict[str, object]]:
    """投影時点の世代・水位・挿入済み行を返す。"""
    game_id = UUID(event.game_id)
    generation, watermark = _generation(writer, game_id)
    if type(event.d1) is not int or event.d1 != watermark:
        raise RuntimeError("試合ライフサイクルイベントの水位が一致しません")
    row = event_row(writer, game_id, generation, event.d1)
    if row is None:
        raise RuntimeError("試合ライフサイクルイベントが保存されていません")
    if (
        row.get("event_kind") != EVENT_KIND
        or row.get("is_tombstone") is not False
        or row.get("replaced_at") is not None
        or row.get("retired_at") is not None
        or row.get("import_batch_id") is not None
        or type(row.get("d2")) is not int
    ):
        raise RuntimeError("試合ライフサイクルイベントの保存形が不正です")
    return generation, watermark, row


def _project(event: SyncEvent, writer: PortWriter) -> None:
    """イベント列の版連鎖と状態一致を同じ TX で検査する。"""
    value = payload(event)
    if value is None:
        raise RuntimeError("試合ライフサイクルの payload が不正です")
    generation, _, inserted = _inserted_row(writer, event)
    stored = _lifecycle_payload_from_row(inserted)
    if (
        stored is None
        or stored.action != value.action
        or stored.version != value.version
    ):
        raise RuntimeError("保存済みライフサイクルが要求と一致しません")
    game_id = UUID(event.game_id)
    d1 = _as_int(event.d1)
    if d1 is None:
        raise RuntimeError("試合ライフサイクルイベントの D1 が不正です")
    latest = _latest_lifecycle(writer, game_id, generation, d1 - 1)
    if value.action == END_ACTION:
        if latest is not None and latest.action == END_ACTION:
            raise SpikeEndReopenRejected("終了済みの試合は再開せずに再終了できません")
        if latest is None:
            if value.previous is not None or value.version != 1:
                raise SpikeEndReopenRejected("初回終了の版または前版参照が不正です")
        else:
            target = latest.target
            if target is None:
                raise SpikeEndReopenRejected("再開の失効対象がありません")
            target_d1 = _as_int(target["d1"])
            target_version = _as_int(target["version"])
            if target_d1 is None or target_version is None:
                raise RuntimeError("再開の失効対象が不正です")
            end = event_row(writer, game_id, generation, target_d1)
            if end is None:
                raise SpikeEndReopenRejected("失効対象の終了確定版がありません")
            end_value = _lifecycle_payload_from_row(end)
            if (
                end_value is None
                or end_value.action != END_ACTION
                or end_value.version != target_version
            ):
                raise SpikeEndReopenRejected("失効対象の終了確定版が一致しません")
            if value.previous is None or not _same(value.previous, target):
                raise SpikeEndReopenRejected(
                    "再終了の前版参照が最新の失効対象と一致しません"
                )
            if value.version != end_value.version + 1:
                raise SpikeEndReopenRejected("再終了の版が直前の版の次ではありません")
        before = _state_before(writer, game_id, generation, d1 - 1)
        if before is None:
            raise SpikeEndReopenRejected("終了確定版の直前状態がありません")
        if not _same(value.state, before):
            raise SpikeEndReopenRejected(
                "終了確定版の状態が直前の確定状態と一致しません"
            )
        return
    # reopen
    if latest is None or latest.action != END_ACTION:
        raise SpikeEndReopenRejected("終了していない試合は再開できません")
    if value.target is None or not _same(
        value.target, {"version": latest.version, "d1": latest.d1}
    ):
        raise SpikeEndReopenRejected("再開の失効対象が最新の終了確定版と一致しません")
    if value.version != latest.version:
        raise SpikeEndReopenRejected("再開の版が失効対象と一致しません")
    if latest.state is None or not _same(value.state, latest.state):
        raise SpikeEndReopenRejected("再開時の状態が終了確定版と一致しません")


def _inject_fault(game_id: UUID) -> None:
    """検証後の保存境界でだけ、対象試合の spike 故障を送出する。"""
    if _FAULT.get(game_id) == "after_lifecycle_projection":
        raise RuntimeError("注入されたライフサイクル投影故障")


@final
class SpikeEndReopenProjectionPort:
    """lifecycle イベントの版連鎖を検査する。DB の status は更新しない。"""

    def apply(self, event: SyncEvent, writer: PortWriter) -> None:
        """同じ TX の挿入済み行と直前イベントだけを検査する。"""
        _project(event, writer)
        _inject_fault(UUID(event.game_id))


def fold_lifecycle(
    runner: _Runner,
    game_id: UUID,
    generation: int,
    watermark: int,
    *,
    limit: int = MAX_LIFECYCLE_SCAN,
) -> tuple[
    str,
    Mapping[str, object] | None,
    tuple[dict[str, object], ...],
    int,
    bool,
]:
    """保存済みイベントを D1 順に畳み、状態・確定版・次の D1/D2 を返す。

    Returns:
        (status, current_state, finalizations, next_d2, truncated)
    """
    if type(watermark) is not int or watermark < 0:
        raise RuntimeError(_ERROR)
    truncated = watermark > limit
    finalizations: list[dict[str, object]] = []
    by_d1: dict[int, dict[str, object]] = {}
    current: Mapping[str, object] | None = None
    status = "in_progress"
    last_d2: int | None = None
    upper = min(watermark, limit)
    for d1 in range(1, upper + 1):
        row = event_row(runner, game_id, generation, d1)
        if row is None:
            continue
        d2 = _as_int(row.get("d2"))
        if d2 is not None:
            last_d2 = d2
        state = state_from_row(row)
        if state is not None:
            current = state
        if row.get("event_kind") != EVENT_KIND:
            continue
        value = _lifecycle_payload_from_row(row)
        if value is None:
            continue
        if value.action == END_ACTION:
            record = {
                "version": value.version,
                "d1": d1,
                "d5": str(row["d5"]),
                "state": _plain(value.state),
                "invalidatedBy": None,
            }
            finalizations.append(record)
            by_d1[d1] = record
            status = "finished"
        else:
            target = value.target
            if target is None:
                raise RuntimeError(_ERROR)
            target_d1 = _as_int(target["d1"])
            target_version = _as_int(target["version"])
            if target_d1 is None or target_version is None:
                raise RuntimeError(_ERROR)
            end = by_d1.get(target_d1)
            if end is None or end.get("version") != target_version:
                raise RuntimeError(_ERROR)
            end["invalidatedBy"] = {"d1": d1, "d5": str(row["d5"])}
            status = "in_progress"
    next_d2 = 1 if last_d2 is None else last_d2 + 1000
    if next_d2 >= 2**63:
        raise RuntimeError(_ERROR)
    return status, current, tuple(finalizations), next_d2, truncated


__all__ = (
    "EVENT_COLUMNS",
    "GAME_COLUMNS",
    "END_ACTION",
    "LIFECYCLE_FORMAT",
    "MAX_LIFECYCLE_SCAN",
    "REOPEN_ACTION",
    "SpikeEndReopenContentValidationPort",
    "SpikeEndReopenProjectionPort",
    "SpikeEndReopenRejected",
    "LifecyclePayload",
    "LifecycleRow",
    "event_row",
    "fold_lifecycle",
    "payload",
    "set_fault",
    "state_from_row",
)
