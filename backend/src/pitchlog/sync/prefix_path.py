"""P1 の D1 付きイベントを一件ずつ原子的に確定する。

呼び出し側は S-1 の要求を渡す。内容拒否と記録権不一致の保存経路は
ステップ 12、要求全体の ACK 合成はステップ 15 が所有する。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from pitchlog.db.recording_rights.models import RecordingGeneration
from pitchlog.db.sync_protocol.models import (
    IdempotencyLedger,
    RejectedEventOriginal,
    TemporaryPlayerIdMapping,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.roster import PlayerCreateToken, PlayerReadToken
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult
from pitchlog.repositories.transaction import (
    _sync_apply_active,
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.idempotency import (
    D5Candidate,
    _json_value,
    classify_d5,
    event_source_fingerprint,
    recheck_and_insert_result,
    source_fingerprint,
)
from pitchlog.sync.invalidation import record_d1_intents
from pitchlog.sync.model import ABSENT, SyncEvent
from pitchlog.sync.ports import (
    ContentValidationPort,
    ProjectionPort,
    RecordingRightsPort,
    _issue_port_writer,
)
from pitchlog.sync.tokens import (
    EventSlotInsertToken,
    EventSlotReadToken,
    GameLockToken,
    IdempotencyLedgerInsertToken,
    IdempotencyLedgerReadToken,
    OperationEventInsertToken,
    OperationEventReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
    RecordingPrefixUpdateToken,
    RejectedOriginalReadToken,
    TemporaryPlayerMappingInsertToken,
    TemporaryPlayerMappingReadToken,
)

type ReplacementKind = Literal["none", "tombstone", "revision"]
type P1Boundary = Literal["B2", "B3b", "B6"] | None
type P1PreconditionCategory = Literal["w2_violation", "recording_rights", "other"]

_GENERATION_COLUMNS = tuple(RecordingGeneration.__table__.c.keys())
_MAPPING_COLUMNS = tuple(TemporaryPlayerIdMapping.__table__.c.keys())
_REJECTION_COLUMNS = tuple(RejectedEventOriginal.__table__.c.keys())
_LEDGER_COLUMNS = tuple(IdempotencyLedger.__table__.c.keys())

# V7 の選手参照名は種別ごとに列挙する。未知の選手参照名は保存前に拒否する。
_PLAYER_REFERENCE_FIELDS: dict[str, frozenset[str]] = {
    "play_input": frozenset({"player_id", "batter_id", "pitcher_id", "runner_id"}),
    "undo": frozenset(),
    "substitution": frozenset(
        {"player_id", "outgoing_player_id", "incoming_player_id"}
    ),
    "tiebreak_start": frozenset({"player_id", "runner_id"}),
    "game_end_declaration": frozenset({"player_id"}),
    "player_registration": frozenset({"player_id"}),
    "state_correction": frozenset(
        {"player_id", "batter_id", "pitcher_id", "runner_id"}
    ),
}
_PLAYER_REFERENCE_NAMES = frozenset().union(*_PLAYER_REFERENCE_FIELDS.values())


@dataclass(frozen=True, slots=True)
class PlayerRegistration:
    """その場登録の選手作成に必要な U-M1 operation の入力。"""

    temporary_id: UUID
    team_record_id: UUID
    name: str
    roster_status_key: str


@dataclass(frozen=True, slots=True)
class P1Target:
    """U-R1 が V10 を解決した undo の対象スロット。"""

    game_id: UUID
    generation: int
    d1: int


@dataclass(frozen=True, slots=True)
class P1Result:
    """イベントの局所結果。要求全体の ACK はここでは作らない。"""

    boundary: P1Boundary
    d3: int
    accepted: bool
    replayed: bool = False
    temporary_id_mapping: tuple[tuple[str, str], ...] = ()


class P1PreconditionError(ValueError):
    """後段が所有する拒否・退避経路へ渡す区分付き前提違反。"""

    def __init__(
        self, message: str, category: P1PreconditionCategory = "other"
    ) -> None:
        """局所処理では ACK に写さず、呼び出し側へ区分を保持する。"""
        super().__init__(message)
        self.category = category


class _D5Race(RuntimeError):
    """ポートが台帳 INSERT 前に書いた可能性を取り消して再掲する印。"""

    def __init__(self, result: P1Result) -> None:
        """再照合済みの局所結果をロールバック後へ運ぶ。"""
        self.result = result


def _cell(
    row: tuple[ImmutableValue, ...], columns: tuple[str, ...], name: str
) -> ImmutableValue:
    """正本 Table の列順に従って実体化済みの値を読む。"""
    if len(row) != len(columns):
        raise RuntimeError("同期表の読み取り列数が正本と異なる")
    return row[columns.index(name)]


def _one_row(result: TenantOperationResult, table: str) -> tuple[ImmutableValue, ...]:
    """一意であるべき行の欠落・重複を拒否する。"""
    if len(result.rows) != 1:
        raise RuntimeError(f"{table} の対象行が一件ではない")
    return result.rows[0]


def _json_object(value: object) -> str:
    """不変な JSON object を token の JSON 文字列へ移す。"""
    if not isinstance(value, Mapping):
        raise P1PreconditionError("P1 の V7 は JSON object が必要")
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True)


def _contains_reference(value: object, identifier: str) -> bool:
    """登録イベントの V7 が対象の一時 ID を実際に参照するかを確かめる。"""
    if isinstance(value, Mapping):
        return any(_contains_reference(item, identifier) for item in value.values())
    if isinstance(value, tuple):
        return any(_contains_reference(item, identifier) for item in value)
    return type(value) is str and value == identifier


def _replacement_state(event: SyncEvent) -> tuple[ReplacementKind, UUID | None]:
    """V9 の一意な種別と、T9 で保存された拒否原本の D5 を読む。"""
    if event.v9 is ABSENT:
        return "none", None
    if not isinstance(event.v9, Mapping) or set(event.v9) not in (
        {"tombstone", "rejected_d5"},
        {"revision", "rejected_d5"},
    ):
        raise P1PreconditionError("V9 の置換種別と拒否原本 D5 が不正")
    kind: ReplacementKind = "tombstone" if "tombstone" in event.v9 else "revision"
    if event.v9[kind] is not True:
        raise P1PreconditionError("V9 の置換種別が不正")
    raw_d5 = event.v9["rejected_d5"]
    try:
        original_d5 = UUID(raw_d5) if type(raw_d5) is str else None
    except ValueError as error:
        raise P1PreconditionError("V9 の拒否原本 D5 が不正") from error
    if (
        original_d5 is None
        or str(original_d5) != raw_d5
        or str(original_d5) == event.d5
    ):
        raise P1PreconditionError("V9 の拒否原本 D5 が不正")
    return kind, original_d5


def _event_kind(event: SyncEvent) -> str:
    """V5 を DB の D1 付き参加区分へ結び付ける。"""
    if type(event.v5) is not str or event.v5 not in _PLAYER_REFERENCE_FIELDS:
        raise P1PreconditionError("P1 の V5 は D1 付きイベント種別が必要")
    return event.v5


def _replacement_target(event: SyncEvent) -> tuple[str, str, int]:
    """墓標・改訂の V10 が現在の拒否位置を名指す形かを読む。"""
    reference = event.v10
    if not isinstance(reference, Mapping) or set(reference) != {"game", "d4", "d1"}:
        raise P1PreconditionError("墓標・改訂には V10 の対象参照が必要", "w2_violation")
    game, d4, d1 = reference["game"], reference["d4"], reference["d1"]
    if (
        type(game) is not str
        or type(d4) is not str
        or type(d1) is not int
        or d1 <= 0
        or (game, d4, d1) != (event.game_id, event.d4, event.d1)
    ):
        raise P1PreconditionError("V10 が置換する D1 と一致しない", "w2_violation")
    return game, d4, d1


def _require_rejected_original(
    scope: _TenantTransaction, event: SyncEvent, original_d5: UUID
) -> None:
    """W2: 同じ試合・D4・D1 の内容拒否原本だけを再開対象とする。"""
    target = _replacement_target(event)
    ledger_rows = scope.run(IdempotencyLedgerReadToken(original_d5)).rows
    if (
        len(ledger_rows) != 1
        or _cell(ledger_rows[0], _LEDGER_COLUMNS, "kind") != "rejected"
    ):
        raise P1PreconditionError("対応する内容拒否の D5 がない", "w2_violation")
    rows = scope.run(RejectedOriginalReadToken(original_d5)).rows
    if len(rows) != 1:
        raise P1PreconditionError("対応する内容拒否原本がない", "w2_violation")
    original = _cell(rows[0], _REJECTION_COLUMNS, "payload")
    if not isinstance(original, Mapping) or any(
        original.get(field) != value
        for field, value in (
            ("d5", str(original_d5)),
            ("game_id", event.game_id),
            ("d4", event.d4),
            ("d1", event.d1),
        )
    ):
        raise P1PreconditionError(
            "内容拒否原本の D1 が置換対象と一致しない", "w2_violation"
        )
    if target != (
        original.get("game_id"),
        original.get("d4"),
        original.get("d1"),
    ):
        raise P1PreconditionError("V10 が内容拒否原本と一致しない", "w2_violation")
    if original.get("event_kind") != event.v5:
        raise P1PreconditionError(
            "改訂版は拒否原本の参加区分を継承する", "w2_violation"
        )
    if isinstance(event.v9, Mapping) and "revision" in event.v9:
        if original.get("d2", ABSENT) != event.v6:
            raise P1PreconditionError(
                "改訂版は拒否原本の D2 を継承する", "w2_violation"
            )
    if source_fingerprint(original) != _cell(
        ledger_rows[0], _LEDGER_COLUMNS, "source_fingerprint"
    ):
        raise P1PreconditionError(
            "内容拒否原本と D5 台帳の指紋が一致しない", "w2_violation"
        )


def _d2(event: SyncEvent, replacement: ReplacementKind) -> int | None:
    """T5 の再採番を伴わない P1 の D2 だけを受ける。"""
    if replacement == "tombstone":
        if event.v6 is not ABSENT:
            raise P1PreconditionError("墓標は D2 を持たない")
        return None
    if event.v6 is ABSENT:
        return None
    if type(event.v6) is not int or event.v6 < 0:
        raise P1PreconditionError("P1 の D2 が不正")
    return event.v6


def _state_diff(event: SyncEvent, replacement: ReplacementKind) -> str | None:
    """墓標では差分を持たず、他では V8 の object を保存する。"""
    if event.v8 is ABSENT:
        return None
    if replacement == "tombstone":
        raise P1PreconditionError("墓標は V8 を持たない")
    return _json_object(event.v8)


def _stored_result(candidate: D5Candidate) -> P1Result:
    """T1 と同じ INSERT に入れた T6 の結果を再掲する。"""
    stored = candidate.stored
    if stored is None or stored.kind != "accepted":
        raise RuntimeError("P1 の保存済み結果が受理ではない")
    result = stored.result
    d3 = result.get("d3")
    raw_mapping = result.get("temporary_id_mapping")
    if (
        result.get("state") != "受理"
        or type(d3) is not int
        or d3 < 0
        or not isinstance(raw_mapping, Mapping)
    ):
        raise RuntimeError("P1 の保存済み結果の形が不正")
    mapping: list[tuple[str, str]] = []
    for key, value in raw_mapping.items():
        if type(key) is not str or type(value) is not str:
            raise RuntimeError("P1 の保存済み写像の形が不正")
        mapping.append((key, value))
    return P1Result(None, d3, True, True, tuple(sorted(mapping)))


def _candidate_result(candidate: D5Candidate, d3: int) -> P1Result | None:
    """未使用だけを新しい T 要素へ進める。"""
    if candidate.kind == "stored_result":
        return _stored_result(candidate)
    if candidate.kind == "conflict":
        return P1Result("B3b", d3, False)
    return None


def _resolve_player_reference(
    scope: _TenantTransaction,
    value: object,
    own_mapping: Mapping[str, str],
    cache: dict[str, str | None],
) -> str:
    """C2: 一時 ID を写像で解決し、未解決の選手 ID を拒否する。"""
    if type(value) is not str:
        raise P1PreconditionError("選手参照は UUID 文字列が必要")
    try:
        identifier = UUID(value)
    except ValueError as error:
        raise P1PreconditionError("選手参照は UUID 文字列が必要") from error
    if str(identifier) != value:
        raise P1PreconditionError("選手参照は正規 UUID が必要")
    if value in own_mapping:
        return own_mapping[value]
    if value not in cache:
        rows = scope.run(TemporaryPlayerMappingReadToken(identifier)).rows
        if rows:
            row = _one_row(TenantOperationResult(rows), "temporary_player_id_mappings")
            player_id = _cell(row, _MAPPING_COLUMNS, "player_id")
            if type(player_id) is not UUID:
                raise RuntimeError("正式選手 ID の型が不正")
            cache[value] = str(player_id)
        else:
            cache[value] = None
    resolved = cache[value]
    if resolved is None:
        # 正式 ID は写像を持たない。自テナントの選手行であることを確認する。
        if scope.run(
            PlayerReadToken(1, record_id=identifier, include_hidden=True)
        ).rows:
            return value
        raise P1PreconditionError("一時選手 ID の確定写像がない")
    return resolved


def _resolve_payload(
    scope: _TenantTransaction,
    value: object,
    kind: str,
    own_mapping: Mapping[str, str],
    cache: dict[str, str | None],
) -> object:
    """V5 ごとの選手参照位置をたどり、参照値を確定 ID に移す。"""
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key in _PLAYER_REFERENCE_FIELDS[kind]:
                if isinstance(item, tuple):
                    result[key] = tuple(
                        _resolve_player_reference(scope, entry, own_mapping, cache)
                        for entry in item
                    )
                else:
                    result[key] = _resolve_player_reference(
                        scope, item, own_mapping, cache
                    )
            elif key in _PLAYER_REFERENCE_NAMES or key.endswith("_player_id"):
                raise P1PreconditionError("V5 で定義されない選手参照位置")
            else:
                result[key] = _resolve_payload(scope, item, kind, own_mapping, cache)
        return result
    if isinstance(value, tuple):
        return tuple(
            _resolve_payload(scope, item, kind, own_mapping, cache) for item in value
        )
    return value


def _projection_event(
    scope: _TenantTransaction,
    event: SyncEvent,
    own_mapping: Mapping[str, str],
) -> SyncEvent:
    """投影へ渡す参照を C2 の確定済み写像で解決する。"""
    cache: dict[str, str | None] = {}
    kind = _event_kind(event)
    return SyncEvent(
        event.d5,
        event.game_id,
        event.d1,
        event.d4,
        event.v5,
        event.v6,
        _resolve_payload(scope, event.v7, kind, own_mapping, cache),
        _resolve_payload(scope, event.v8, kind, own_mapping, cache),
        event.v9,
        _resolve_payload(scope, event.v10, kind, own_mapping, cache),
        event.v11,
    )


def _apply_locked(
    scope: _TenantTransaction,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    v12: object,
    registration: PlayerRegistration | None,
    target: P1Target | None,
) -> P1Result:
    """試合行の後に世代行をロックし、P1 の T 要素を一境界に束ねる。"""
    game_id, d5 = UUID(event.game_id), UUID(event.d5)
    if not scope.run(GameLockToken(game_id)).rows:
        return P1Result("B6", 0, False)
    generation_row = _one_row(
        scope.run(RecordingGenerationReadToken(game_id)), "recording_generations"
    )
    generation_value = _cell(generation_row, _GENERATION_COLUMNS, "generation")
    if type(generation_value) is not int:
        raise RuntimeError("記録権世代の型が不正")
    generation = generation_value
    locked = _one_row(
        scope.run(RecordingGenerationLockToken(game_id, generation)),
        "recording_generations",
    )
    d3_value = _cell(locked, _GENERATION_COLUMNS, "confirmed_watermark")
    if type(d3_value) is not int:
        raise RuntimeError("D3 の型が不正")
    d3 = d3_value
    replacement, original_d5 = _replacement_state(event)
    fingerprint = source_fingerprint(
        {
            "event_fingerprint": event_source_fingerprint(event),
            "path": "P1",
            "registration": (
                None
                if registration is None
                else {
                    "temporary_id": str(registration.temporary_id),
                    "team_record_id": str(registration.team_record_id),
                    "name": registration.name,
                    "roster_status_key": registration.roster_status_key,
                }
            ),
        }
    )

    candidate = classify_d5(scope, d5, fingerprint, "P1")
    previous = _candidate_result(candidate, d3)
    if previous is not None:
        return previous
    if event.d1 is None:
        raise P1PreconditionError("P1 には D1 が必要")
    kind = _event_kind(event)
    d2 = _d2(event, replacement)
    payload_json = _json_object(event.v7)
    state_diff_json = _state_diff(event, replacement)
    if replacement == "tombstone" and payload_json != "{}":
        raise P1PreconditionError("墓標の payload は空 object が必要")
    if kind == "player_registration" and registration is None:
        raise P1PreconditionError("その場登録には選手作成値が必要")
    if kind != "player_registration" and registration is not None:
        raise P1PreconditionError("選手作成値はその場登録だけに使える")
    if registration is not None and not _contains_reference(
        event.v7, str(registration.temporary_id)
    ):
        raise P1PreconditionError("その場登録の V7 に一時選手 ID がない")
    if kind == "undo":
        if (
            event.v10 is ABSENT
            or target is None
            or target.game_id != game_id
            or target.generation <= 0
            or target.d1 <= 0
        ):
            raise P1PreconditionError("undo には照合済みの V10 対象が必要")
    elif target is not None:
        raise P1PreconditionError("V10 対象は undo だけに指定できる")

    # 登録表の検査は三つのポートのいずれを呼ぶよりも前に完了する。
    for port in (rights, projection, validator):
        port_guard.require_registered_port(port)
    writer = _issue_port_writer(scope.run)
    try:
        if not rights.holds_recording_right(event.game_id, event.d4, v12, writer):
            raise P1PreconditionError(
                "P1 の記録権不一致は退避経路へ渡す", "recording_rights"
            )
        if event.d1 > d3 + 1:
            return P1Result("B2", d3, False)
        if event.d1 <= d3:
            raise P1PreconditionError(
                "確定済み D1 は墓標・改訂で置換できない",
                "w2_violation" if original_d5 is not None else "other",
            )
        if original_d5 is not None:
            _require_rejected_original(scope, event, original_d5)
        valid, reason = validator.validate(event, writer)
        if not valid:
            raise P1PreconditionError(reason or "P1 の内容拒否は T9 へ渡す")

        slot_rows = scope.run(EventSlotReadToken(game_id, generation, event.d1)).rows
        old_event_rows = scope.run(
            OperationEventReadToken(game_id, generation, event.d1)
        ).rows
        if len(slot_rows) > 1 or len(old_event_rows) > 1:
            raise RuntimeError("D1 に複数の現行行がある")
        if old_event_rows and not slot_rows:
            raise RuntimeError("現行イベントのスロットがない")
        if slot_rows or old_event_rows:
            raise P1PreconditionError(
                "確定済みイベントは墓標・改訂で置換できない",
                "w2_violation" if original_d5 is not None else "other",
            )

        new_d3 = max(d3, event.d1)
        new_mapping: dict[str, str] = {}
        player_token: PlayerCreateToken | None = None
        if registration is not None:
            prior = scope.run(
                TemporaryPlayerMappingReadToken(registration.temporary_id)
            ).rows
            if prior:
                raise P1PreconditionError("一時 ID は別の確定写像に使用済み")
            player_id = uuid4()
            new_mapping[str(registration.temporary_id)] = str(player_id)
            player_token = PlayerCreateToken(
                player_id,
                registration.team_record_id,
                registration.name,
                registration.roster_status_key,
            )
        projected_event = _projection_event(scope, event, new_mapping)
        payload_json = _json_object(projected_event.v7)
        state_diff_json = _state_diff(projected_event, replacement)
        result_json = json.dumps(
            {
                "state": "受理",
                "d3": new_d3,
                "temporary_id_mapping": new_mapping,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        token = IdempotencyLedgerInsertToken(d5, "accepted", fingerprint, result_json)
        raced = recheck_and_insert_result(scope, token, "P1")
        if raced is not None:
            outcome = _candidate_result(raced, d3)
            if outcome is None:
                raise RuntimeError("D5 再照合が未使用に戻った")
            raise _D5Race(outcome)

        if player_token is not None:
            scope.run(player_token)
        scope.run(EventSlotInsertToken(game_id, generation, event.d1))
        scope.run(
            OperationEventInsertToken(
                uuid4(),
                game_id,
                d5,
                kind,
                payload_json,
                generation,
                event.d1,
                d2,
                state_diff_json,
                replacement == "tombstone",
                None if target is None else target.generation,
                None if target is None else target.d1,
            )
        )
        if new_d3 > d3:
            updated = scope.run(
                RecordingPrefixUpdateToken(game_id, generation, new_d3, new_d3)
            )
            if updated.rows != ((1,),):
                raise RuntimeError("D3 の前進に失敗")
        projection.apply(projected_event, writer)
        if registration is not None:
            scope.run(
                TemporaryPlayerMappingInsertToken(
                    uuid4(),
                    registration.temporary_id,
                    UUID(new_mapping[str(registration.temporary_id)]),
                )
            )
        if new_d3 > d3:
            record_d1_intents(scope, game_id, d5)
        return P1Result(None, new_d3, True, False, tuple(new_mapping.items()))
    finally:
        writer._close()


def apply_p1_event(
    context: TenantContext,
    event: SyncEvent,
    rights: RecordingRightsPort,
    projection: ProjectionPort,
    validator: ContentValidationPort,
    v12: object,
    *,
    registration: PlayerRegistration | None = None,
    target: P1Target | None = None,
) -> P1Result:
    """P1 の一イベントを一トランザクションとして適用する。

    Args:
        context: API 層で発行済みのテナント文脈。
        event: S-1 を満たす D1 付きイベント。
        rights: U-R1 が所有する記録権判定ポート。
        projection: T4 の投影ポート。
        validator: ⑦ の内容検証ポート。
        v12: 要求レベルの記録権証明。
        registration: その場登録で U-M1 の選手行に渡す値。
        target: undo の V10 を世代・D1 に解決した対象。

    Returns:
        一イベントの局所結果。ACK 全体は呼び出し元が組み立てる。

    例外時はスコープ全体をロールバックし、ポート書き手も失効させる。
    """
    if (
        type(event.d1) is not int
        or event.d1 <= 0
        or type(event.d4) is not str
        or not event.d4
    ):
        raise P1PreconditionError("P1 には D1 と D4 が必要")
    try:
        with tenant_transaction_scope(context) as scope:
            with _sync_apply_active():
                return _apply_locked(
                    scope,
                    event,
                    rights,
                    projection,
                    validator,
                    v12,
                    registration,
                    target,
                )
    except _D5Race as race:
        return race.result
