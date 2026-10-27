"""同期適用の単一表 operation を登録する。文は token から選ばせない。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, cast

from sqlalchemy import Table, bindparam, insert, null, select, update
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from pitchlog.db.game_state.models import Game
from pitchlog.db.recording_rights.models import (
    EvacuatedEventOriginal,
    RecordingGeneration,
)
from pitchlog.db.sync_protocol.models import (
    EventSlot,
    IdempotencyLedger,
    InvalidationIntent,
    OperationEvent,
    RejectedEventOriginal,
    TemporaryPlayerIdMapping,
)
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
    PrimaryKeyBinding,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationToken
from pitchlog.sync import tokens as sync_tokens

_GAMES = cast(Table, Game.__table__)
_GENERATIONS = cast(Table, RecordingGeneration.__table__)
# 初期権の保護証拠列を既存appの同期読取へ自動投影しない。
_GENERATION_READ_COLUMNS = sync_tokens.RECORDING_GENERATION_READ_COLUMNS
_SLOTS = cast(Table, EventSlot.__table__)
_EVENTS = cast(Table, OperationEvent.__table__)
_MAPPINGS = cast(Table, TemporaryPlayerIdMapping.__table__)
_LEDGER = cast(Table, IdempotencyLedger.__table__)
_REJECTIONS = cast(Table, RejectedEventOriginal.__table__)
_INTENTS = cast(Table, InvalidationIntent.__table__)
_EVACUATIONS = cast(Table, EvacuatedEventOriginal.__table__)


def _json_object(value: str) -> dict[str, object]:
    """不変 token の JSON 文字列を実行直前に新しい object へ戻す。"""
    parsed = json.loads(value)
    if type(parsed) is not dict or any(type(key) is not str for key in parsed):
        raise ValueError("JSONB の値は文字列キーの object が必要")
    return cast(dict[str, object], parsed)


def _build_sync_statement(
    kind: str,
    table: Table,
    columns: tuple[str, ...] = (),
    keys: tuple[str, ...] = (),
    values: tuple[str, ...] = (),
) -> Select[Any] | Insert | Update:
    """固定表の read・lock・insert・update だけを構築する SQL API 窓口。"""
    if kind in {"read", "lock"}:
        projection = (
            tuple(table.c[name] for name in _GENERATION_READ_COLUMNS)
            if table is _GENERATIONS
            else tuple(table.c)
        )
        statement = select(*projection).where(
            table.c.tenant_id == bindparam("tenant_id")
        )
        for name in columns:
            parameter = f"where_{name}" if kind == "lock" else name
            statement = statement.where(table.c[name] == bindparam(parameter))
        return statement.with_for_update() if kind == "lock" else statement
    if kind == "insert":
        return insert(table).values(
            {"tenant_id": bindparam("tenant_id")}
            | {name: bindparam(name) for name in columns}
        )
    if kind == "sync_shared_intent_insert":
        return insert(table).values(
            tenant_id=bindparam("tenant_id"),
            intent_id=bindparam("intent_id"),
            scope_kind=bindparam("scope_kind"),
            target_tenant_id=bindparam("tenant_id"),
        )
    if kind == "update":
        changed = update(table).where(table.c.tenant_id == bindparam("where_tenant_id"))
        for name in keys:
            changed = changed.where(table.c[name] == bindparam(f"where_{name}"))
        return changed.values({name: bindparam(f"set_{name}") for name in values})
    raise ValueError(f"未知の同期 operation 種別: {kind}")


def _read(table: Table, *columns: str) -> Select[Any]:
    """必ずテナント列を含む単一表の読み取りを作る。"""
    return cast(Select[Any], _build_sync_statement("read", table, columns))


def _lock(table: Table, *columns: str) -> Select[Any]:
    """正本主キー全列の bind で対象行だけをロックする。"""
    return cast(Select[Any], _build_sync_statement("lock", table, columns))


def _insert(table: Table, *columns: str) -> Insert:
    """文脈テナントと宣言済み列だけへ書く。"""
    return cast(Insert, _build_sync_statement("insert", table, columns))


def _update(table: Table, keys: tuple[str, ...], values: tuple[str, ...]) -> Update:
    """正本主キー全列と SET 値に異なる bind 名を使う。"""
    return cast(
        Update, _build_sync_statement("update", table, keys=keys, values=values)
    )


def _primary_key_bindings(
    table: Table, *, locked: bool
) -> tuple[PrimaryKeyBinding, ...]:
    """正本表の複合主キーを一列も省かず宣言する。"""
    return tuple(
        PrimaryKeyBinding(
            column,
            (
                "tenant_id"
                if locked and column.key == "tenant_id"
                else f"where_{column.key}"
            ),
        )
        for column in table.primary_key.columns
    )


def _register(
    token_type: type[TenantOperationToken],
    table: Table,
    operation: str,
    statement: Select[Any] | Insert | Update,
    parameters: Mapping[str, str],
    *,
    json_parameters: frozenset[str] = frozenset(),
    sql_null_json_parameter: str | None = None,
    constants: Mapping[str, object] | None = None,
    locked: bool = False,
    update_columns: frozenset[str] | None = None,
    limit_max: int | None = None,
    required_bindings: tuple[RequiredBinding, ...] = (),
    validate: Callable[[TenantOperationToken], None] | None = None,
) -> OperationRegistration:
    """登録時に固定した文と token の値の対応だけを準備する。"""
    fixed = dict(constants or {})
    if sql_null_json_parameter is not None:
        if (
            not isinstance(statement, Insert)
            or sql_null_json_parameter not in json_parameters
        ):
            raise ValueError("SQL NULL へ切り替える JSON 列の宣言が不正")
        null_statement = statement.values({sql_null_json_parameter: null()})
    else:
        null_statement = None

    def prepare(token: TenantOperationToken) -> PreparedOperation:
        """Token にない列や文を実行時に追加しない。"""
        if type(token) is not token_type:
            raise TypeError("登録型と異なる同期 operation token")
        if validate is not None:
            validate(token)
        values: dict[str, object] = {
            bind: getattr(token, attribute) for bind, attribute in parameters.items()
        }
        prepared_statement = statement
        for name in json_parameters:
            raw = values[name]
            if raw is None and name == sql_null_json_parameter:
                if null_statement is None:
                    raise RuntimeError("SQL NULL の登録文がない")
                prepared_statement = null_statement
                del values[name]
            else:
                values[name] = None if raw is None else _json_object(cast(str, raw))
        values.update(fixed)
        return prepared_statement, values

    return OperationRegistration(
        token_type,
        f"CAP:{table.name}:{operation}",
        statement,
        table.c.tenant_id,
        prepare,
        required_bindings=required_bindings,
        required_limit_parameter="limit" if limit_max is not None else None,
        required_limit_max=limit_max,
        allowed_update_columns=update_columns,
        primary_key_bindings=(
            _primary_key_bindings(table, locked=locked)
            if isinstance(statement, Update) or locked
            else ()
        ),
        for_update=locked,
    )


_game_read = _read(_GAMES, "id")
_generation_read = _read(_GENERATIONS, "game_id").where(
    _GENERATIONS.c.kind == bindparam("kind"),
    _GENERATIONS.c.revoked_at.is_(None),
    _GENERATIONS.c.retired_at.is_(None),
)
_generation_lock = _lock(_GENERATIONS, "game_id", "generation")
_generation_by_number_read = _read(_GENERATIONS, "game_id", "generation").where(
    _GENERATIONS.c.kind == bindparam("kind")
)
_slot_read = _read(_SLOTS, "game_id", "generation", "d1")
_event_read = _read(_EVENTS, "game_id", "generation", "d1").where(
    _EVENTS.c.replaced_at.is_(None)
)
_event_order_read = (
    _read(_EVENTS, "game_id")
    .where(_EVENTS.c.d2 > bindparam("after_d2"))
    .where(_EVENTS.c.replaced_at.is_(None), _EVENTS.c.retired_at.is_(None))
    .order_by(_EVENTS.c.d2, _EVENTS.c.id)
    .limit(bindparam("limit"))
)
_pending_intents = (
    _read(_INTENTS)
    .where(_INTENTS.c.delivery_status == bindparam("delivery_status"))
    .where(_INTENTS.c.intent_id > bindparam("after_intent_id"))
    .order_by(_INTENTS.c.intent_id)
    .limit(bindparam("limit"))
)


def _validate_sync_intent_token(token: TenantOperationToken) -> None:
    """同期意図の範囲と選択子を準備時に再検査する。"""
    cast(sync_tokens.SyncInvalidationIntentInsertToken, token).validate()


def _validate_sync_shared_intent_token(token: TenantOperationToken) -> None:
    """共有集計の対象を文脈 bind に固定する前提を再検査する。"""
    cast(sync_tokens.SyncSharedInvalidationIntentInsertToken, token).validate()


SYNC_APPLY_OPERATIONS: tuple[OperationRegistration, ...] = (
    _register(sync_tokens.GameReadToken, _GAMES, "read", _game_read, {"id": "game_id"}),
    _register(
        sync_tokens.GameLockToken,
        _GAMES,
        "read",
        _lock(_GAMES, "id"),
        {"where_id": "game_id"},
        locked=True,
    ),
    _register(
        sync_tokens.RecordingGenerationReadToken,
        _GENERATIONS,
        "read",
        _generation_read,
        {"game_id": "game_id"},
        constants={"kind": "normal"},
        required_bindings=(RequiredBinding(_GENERATIONS.c.kind, "kind", "normal"),),
    ),
    _register(
        sync_tokens.RecordingGenerationByNumberReadToken,
        _GENERATIONS,
        "read",
        _generation_by_number_read,
        {"game_id": "game_id", "generation": "generation"},
        constants={"kind": "normal"},
        required_bindings=(RequiredBinding(_GENERATIONS.c.kind, "kind", "normal"),),
    ),
    _register(
        sync_tokens.RecordingGenerationLockToken,
        _GENERATIONS,
        "read",
        _generation_lock,
        {"where_game_id": "game_id", "where_generation": "generation"},
        locked=True,
    ),
    _register(
        sync_tokens.RecordingPrefixUpdateToken,
        _GENERATIONS,
        "update",
        _update(
            _GENERATIONS,
            ("game_id", "generation"),
            ("confirmed_watermark", "applied_prefix"),
        ),
        {
            "where_game_id": "game_id",
            "where_generation": "generation",
            "set_confirmed_watermark": "confirmed_watermark",
            "set_applied_prefix": "applied_prefix",
        },
        update_columns=frozenset({"confirmed_watermark", "applied_prefix"}),
    ),
    _register(
        sync_tokens.EventSlotReadToken,
        _SLOTS,
        "read",
        _slot_read,
        {"game_id": "game_id", "generation": "generation", "d1": "d1"},
    ),
    _register(
        sync_tokens.EventSlotInsertToken,
        _SLOTS,
        "insert",
        _insert(_SLOTS, "game_id", "generation", "d1"),
        {"game_id": "game_id", "generation": "generation", "d1": "d1"},
    ),
    _register(
        sync_tokens.EventSlotVersionUpdateToken,
        _SLOTS,
        "update",
        _update(_SLOTS, ("game_id", "generation", "d1"), ("confirmed_version",)).where(
            _SLOTS.c.confirmed_version == bindparam("expected_version")
        ),
        {
            "where_game_id": "game_id",
            "where_generation": "generation",
            "where_d1": "d1",
            "expected_version": "expected_version",
            "set_confirmed_version": "confirmed_version",
        },
        update_columns=frozenset({"confirmed_version"}),
    ),
    _register(
        sync_tokens.OperationEventReadToken,
        _EVENTS,
        "read",
        _event_read,
        {"game_id": "game_id", "generation": "generation", "d1": "d1"},
    ),
    _register(
        sync_tokens.OperationEventOrderReadToken,
        _EVENTS,
        "read",
        _event_order_read,
        {"game_id": "game_id", "after_d2": "after_d2", "limit": "limit"},
        limit_max=256,
    ),
    _register(
        sync_tokens.OperationEventInsertToken,
        _EVENTS,
        "insert",
        _insert(
            _EVENTS,
            "id",
            "game_id",
            "d5",
            "event_kind",
            "payload",
            "generation",
            "d1",
            "d2",
            "state_diff",
            "is_tombstone",
            "target_generation",
            "target_d1",
            "expected_version",
            "change_order",
        ),
        {
            "id": "id",
            "game_id": "game_id",
            "d5": "d5",
            "event_kind": "event_kind",
            "payload": "payload_json",
            "generation": "generation",
            "d1": "d1",
            "d2": "d2",
            "state_diff": "state_diff_json",
            "is_tombstone": "is_tombstone",
            "target_generation": "target_generation",
            "target_d1": "target_d1",
            "expected_version": "expected_version",
            "change_order": "change_order",
        },
        json_parameters=frozenset({"payload", "state_diff"}),
        sql_null_json_parameter="state_diff",
    ),
    _register(
        sync_tokens.OperationEventOrderUpdateToken,
        _EVENTS,
        "update",
        _update(_EVENTS, ("id",), ("d2",)),
        {"where_id": "id", "set_d2": "d2"},
        update_columns=frozenset({"d2"}),
    ),
    _register(
        sync_tokens.OperationEventReplaceToken,
        _EVENTS,
        "update",
        _update(_EVENTS, ("id",), ("replaced_at",)).where(
            _EVENTS.c.replaced_at.is_(None)
        ),
        {"where_id": "id", "set_replaced_at": "replaced_at"},
        update_columns=frozenset({"replaced_at"}),
    ),
    _register(
        sync_tokens.TemporaryPlayerMappingReadToken,
        _MAPPINGS,
        "read",
        _read(_MAPPINGS, "temporary_id"),
        {"temporary_id": "temporary_id"},
    ),
    _register(
        sync_tokens.TemporaryPlayerMappingInsertToken,
        _MAPPINGS,
        "insert",
        _insert(_MAPPINGS, "id", "temporary_id", "player_id"),
        {"id": "id", "temporary_id": "temporary_id", "player_id": "player_id"},
    ),
    _register(
        sync_tokens.IdempotencyLedgerReadToken,
        _LEDGER,
        "read",
        _read(_LEDGER, "d5"),
        {"d5": "d5"},
    ),
    _register(
        sync_tokens.IdempotencyLedgerInsertToken,
        _LEDGER,
        "insert",
        _insert(_LEDGER, "d5", "kind", "source_fingerprint", "result", "reason"),
        {
            "d5": "d5",
            "kind": "kind",
            "source_fingerprint": "source_fingerprint",
            "result": "result_json",
            "reason": "reason",
        },
        json_parameters=frozenset({"result"}),
    ),
    _register(
        sync_tokens.RejectedOriginalReadToken,
        _REJECTIONS,
        "read",
        _read(_REJECTIONS, "d5"),
        {"d5": "d5"},
    ),
    _register(
        sync_tokens.RejectedOriginalInsertToken,
        _REJECTIONS,
        "insert",
        _insert(_REJECTIONS, "id", "d5", "payload"),
        {"id": "id", "d5": "d5", "payload": "payload_json"},
        json_parameters=frozenset({"payload"}),
    ),
    _register(
        sync_tokens.InvalidationIntentReadToken,
        _INTENTS,
        "read",
        _read(_INTENTS, "intent_id"),
        {"intent_id": "intent_id"},
    ),
    _register(
        sync_tokens.InvalidationIntentPendingToken,
        _INTENTS,
        "read",
        _pending_intents,
        {"limit": "limit", "after_intent_id": "after_intent_id"},
        constants={"delivery_status": "pending"},
        limit_max=100,
        required_bindings=(
            RequiredBinding(_INTENTS.c.delivery_status, "delivery_status", "pending"),
        ),
    ),
    _register(
        sync_tokens.SyncInvalidationIntentInsertToken,
        _INTENTS,
        "insert",
        _insert(_INTENTS, "intent_id", "scope_kind", "game_id"),
        {
            "intent_id": "intent_id",
            "scope_kind": "scope_kind",
            "game_id": "game_id",
        },
        validate=_validate_sync_intent_token,
    ),
    _register(
        sync_tokens.SyncSharedInvalidationIntentInsertToken,
        _INTENTS,
        "insert",
        cast(Insert, _build_sync_statement("sync_shared_intent_insert", _INTENTS)),
        {"intent_id": "intent_id"},
        constants={"scope_kind": "shared_total"},
        required_bindings=(
            RequiredBinding(_INTENTS.c.scope_kind, "scope_kind", "shared_total"),
        ),
        validate=_validate_sync_shared_intent_token,
    ),
    _register(
        sync_tokens.InvalidationIntentDeliveredToken,
        _INTENTS,
        "update",
        _update(_INTENTS, ("intent_id",), ("delivery_status", "delivered_at")).where(
            _INTENTS.c.delivery_status == bindparam("pending_status")
        ),
        {"where_intent_id": "intent_id", "set_delivered_at": "delivered_at"},
        constants={"set_delivery_status": "delivered", "pending_status": "pending"},
        update_columns=frozenset({"delivery_status", "delivered_at"}),
        required_bindings=(
            RequiredBinding(_INTENTS.c.delivery_status, "pending_status", "pending"),
        ),
    ),
    _register(
        sync_tokens.EvacuatedOriginalReadToken,
        _EVACUATIONS,
        "read",
        _read(_EVACUATIONS, "d5"),
        {"d5": "d5"},
    ),
    _register(
        sync_tokens.EvacuatedOriginalInsertToken,
        _EVACUATIONS,
        "insert",
        _insert(
            _EVACUATIONS,
            "id",
            "game_id",
            "old_generation",
            "original_d1",
            "d5",
            "origin",
            "payload",
        ),
        {
            "id": "id",
            "game_id": "game_id",
            "old_generation": "old_generation",
            "original_d1": "original_d1",
            "d5": "d5",
            "payload": "payload_json",
        },
        constants={"origin": "authority_mismatch"},
        json_parameters=frozenset({"payload"}),
    ),
)
