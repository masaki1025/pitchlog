"""同期の 9 表の operation 登録とテナント境界を検査する。"""

from __future__ import annotations

import os
from collections import Counter
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.selectable import Select
from test_authz_tenant_context import make_tenant_context

from pitchlog.db.engine import create_database_engine
from pitchlog.db.sync_protocol.models import InvalidationIntent
from pitchlog.repositories import transaction
from pitchlog.repositories.base import (
    _OPERATION_REGISTRY,
    _validate_prepared_statement,
)
from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationTrigger,
    CacheScope,
)
from pitchlog.repositories.invalidation_intents import InvalidationIntentInsertToken
from pitchlog.repositories.sync_apply import SYNC_APPLY_OPERATIONS
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync import tokens
from pitchlog.sync.intent_ids import derive_sync_intent_id, is_sync_intent_id
from pitchlog.sync.port_guard import validate_port_modules


def test_all_sync_operations_use_canonical_single_table_registry() -> None:
    """全登録が構築時検査を通り、型そのもので registry から引ける。"""
    assert len(SYNC_APPLY_OPERATIONS) == 26
    assert type(_OPERATION_REGISTRY) is MappingProxyType
    assert len({spec.token_type for spec in SYNC_APPLY_OPERATIONS}) == 26
    assert Counter(spec.tenant_column.table.name for spec in SYNC_APPLY_OPERATIONS) == {
        "games": 2,
        "recording_generations": 3,
        "event_slots": 3,
        "operation_events": 5,
        "temporary_player_id_mappings": 2,
        "idempotency_ledger": 2,
        "rejected_event_originals": 2,
        "invalidation_intents": 5,
        "evacuated_event_originals": 2,
    }
    for spec in SYNC_APPLY_OPERATIONS:
        assert _OPERATION_REGISTRY[spec.token_type] is spec
        assert spec.capability_id == spec.token_type._capability_id
        _validate_prepared_statement(spec, spec.statement)
        spec.statement.compile(dialect=postgresql.dialect())


def test_lock_order_is_game_then_recording_generation() -> None:
    """共通ロック順を作る 2 token は主キー全列の通常ロックである。"""
    specs = [
        _OPERATION_REGISTRY[tokens.GameLockToken],
        _OPERATION_REGISTRY[tokens.RecordingGenerationLockToken],
    ]
    assert [spec.tenant_column.table.name for spec in specs] == [
        "games",
        "recording_generations",
    ]
    for spec in specs:
        assert spec.for_update
        assert isinstance(spec.statement, Select)
        assert spec.statement._for_update_arg is not None
        assert {binding.column.key for binding in spec.primary_key_bindings} == {
            column.key for column in spec.tenant_column.table.primary_key.columns
        }
    assert not _OPERATION_REGISTRY[tokens.GameReadToken].for_update
    assert not _OPERATION_REGISTRY[tokens.RecordingGenerationReadToken].for_update


def test_sync_intent_insert_is_distinct_from_trigger_14() -> None:
    """同一 capability 内でも同期経路とトリガー 14 の token は別型である。"""
    first = _OPERATION_REGISTRY[tokens.SyncInvalidationIntentInsertToken]
    second = _OPERATION_REGISTRY[InvalidationIntentInsertToken]
    assert (
        first.capability_id == second.capability_id == "CAP:invalidation_intents:insert"
    )
    assert first.token_type is not second.token_type
    assert first.statement is not second.statement


def test_sync_intent_scope_shapes_and_context_target() -> None:
    """①〜⑤の選択子を限定し、④の対象を文脈 bind に固定する。"""
    game_id, other_tenant = uuid4(), uuid4()
    event = str(uuid4())
    game = tokens.SyncInvalidationIntentInsertToken(event, "game", game_id)
    assert game.intent_id == derive_sync_intent_id(event, "game")
    for scope in ("player_total", "team_total", "chart"):
        token = tokens.SyncInvalidationIntentInsertToken(event, scope)
        assert token.intent_id == derive_sync_intent_id(event, scope)
        with pytest.raises(ValueError):
            tokens.SyncInvalidationIntentInsertToken(event, scope, game_id)
    with pytest.raises(ValueError):
        tokens.SyncInvalidationIntentInsertToken(event, "game")
    with pytest.raises(ValueError):
        tokens.SyncInvalidationIntentInsertToken(event, "shared_total")
    with pytest.raises(ValueError):
        tokens.SyncInvalidationIntentInsertToken(event, "unknown")
    with pytest.raises(ValueError):
        tokens.SyncSharedInvalidationIntentInsertToken("")

    shared = tokens.SyncSharedInvalidationIntentInsertToken(event)
    spec = _OPERATION_REGISTRY[type(shared)]
    statement, values = spec.prepare(shared)
    assert isinstance(statement, Insert)
    assert statement._values is not None
    target = statement._values["target_tenant_id"]
    assert isinstance(target, BindParameter)
    assert target.key == "tenant_id"
    assert "target_tenant_id" not in values
    assert values["scope_kind"] == "shared_total"
    with pytest.raises(TypeError):
        tokens.SyncSharedInvalidationIntentInsertToken(
            event, **{"target_tenant_id": other_tenant}
        )
    object.__setattr__(shared, "event_identity", "")
    with pytest.raises(ValueError):
        spec.prepare(shared)


def test_sync_intent_ids_exclude_trigger_14_and_other_triggers() -> None:
    """B06 の全トリガー値と同期用接頭辞が衝突しない。"""
    event = str(uuid4())
    assert all(
        not trigger.value.startswith("sync") for trigger in CacheInvalidationTrigger
    )
    assert is_sync_intent_id(derive_sync_intent_id(event, "shared_total"))
    assert is_sync_intent_id(derive_sync_intent_id(f"{event}:3", "game"))
    old = InvalidationIntentInsertToken(
        CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
        uuid4(),
        CacheScope.SHARED_AGGREGATE,
    )
    assert not is_sync_intent_id(old.intent_id)
    assert not is_sync_intent_id("sync::shared_total")
    assert not is_sync_intent_id("unrelated")


def test_pending_intents_use_bounded_keyset_without_sql_owner_filter() -> None:
    """混在行を飛ばしながら後続ページを取得できる SQL 形を保つ。"""
    spec = _OPERATION_REGISTRY[tokens.InvalidationIntentPendingToken]
    first = tokens.InvalidationIntentPendingToken(2)
    second = tokens.InvalidationIntentPendingToken(2, "roster_status_change:cursor")
    statement, first_values = spec.prepare(first)
    assert isinstance(statement, Select)
    assert first_values["after_intent_id"] == ""
    assert spec.prepare(second)[1]["after_intent_id"] == second.after_intent_id
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "invalidation_intents.intent_id > %(after_intent_id)s" in sql
    assert "ORDER BY invalidation_intents.intent_id" in sql
    assert "LIMIT %(limit)s" in sql
    assert "LIKE" not in sql
    assert spec.required_limit_max == 100


def test_sync_tokens_are_importable_from_restricted_ports() -> None:
    """Token 型のモジュールと推移先には SQL 構築依存を含めない。"""
    validate_port_modules(("pitchlog.sync.tokens",))


def test_composite_updates_bind_exact_primary_keys() -> None:
    """複合主キー表の UPDATE で不足した列や共用 bind がない。"""
    for token_type in (
        tokens.RecordingPrefixUpdateToken,
        tokens.EventSlotVersionUpdateToken,
    ):
        spec = _OPERATION_REGISTRY[token_type]
        assert isinstance(spec.statement, Update)
        assert {binding.column.key for binding in spec.primary_key_bindings} == {
            column.key for column in spec.tenant_column.table.primary_key.columns
        }
        _validate_prepared_statement(spec, spec.statement)


@pytest.mark.requires_db
def test_sync_intent_two_tenant_read_and_write_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """共有 DB の外側トランザクションで越境を拒否し、最後に巻き戻す。"""
    if "PITCHLOG_DATABASE_URL" not in os.environ:
        pytest.skip("共有 DB の PITCHLOG_DATABASE_URL が未設定")
    first_tenant, second_tenant = uuid4(), uuid4()
    event_identity = str(uuid4())
    intent_id = derive_sync_intent_id(event_identity, "shared_total")
    tenant_index = list(InvalidationIntent.__table__.c.keys()).index("tenant_id")
    target_index = list(InvalidationIntent.__table__.c.keys()).index("target_tenant_id")
    intent_index = list(InvalidationIntent.__table__.c.keys()).index("intent_id")
    engine = create_database_engine()
    with engine.connect() as connection:
        outer = connection.begin()
        monkeypatch.setattr(transaction, "create_database_engine", lambda: connection)
        try:
            with tenant_transaction_scope(make_tenant_context(first_tenant)) as scope:
                with pytest.raises(TypeError):
                    tokens.SyncSharedInvalidationIntentInsertToken(
                        event_identity, **{"target_tenant_id": second_tenant}
                    )
                scope.run(
                    tokens.SyncSharedInvalidationIntentInsertToken(event_identity)
                )
                old = InvalidationIntentInsertToken(
                    CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
                    uuid4(),
                    CacheScope.SHARED_AGGREGATE,
                )
                scope.run(old)
                own = scope.run(tokens.InvalidationIntentReadToken(intent_id))
                assert len(own.rows) == 1
                assert own.rows[0][tenant_index] == first_tenant
                assert own.rows[0][target_index] == first_tenant
                cursor = ""
                observed: list[str] = []
                selected: list[str] = []
                for _ in range(3):
                    page = scope.run(tokens.InvalidationIntentPendingToken(1, cursor))
                    if not page.rows:
                        break
                    cursor = page.rows[0][intent_index]
                    assert type(cursor) is str
                    observed.append(cursor)
                    if is_sync_intent_id(cursor):
                        selected.append(cursor)
                assert observed == sorted((old.intent_id, intent_id))
                assert selected == [intent_id]

            with tenant_transaction_scope(make_tenant_context(second_tenant)) as scope:
                assert (
                    scope.run(tokens.InvalidationIntentReadToken(intent_id)).rows == ()
                )
                changed = scope.run(
                    tokens.InvalidationIntentDeliveredToken(
                        intent_id, datetime.now(UTC)
                    )
                )
                assert changed.rows == ((0,),)
                scope.run(
                    tokens.SyncSharedInvalidationIntentInsertToken(event_identity)
                )
                other = scope.run(tokens.InvalidationIntentReadToken(intent_id))
                assert len(other.rows) == 1
                assert other.rows[0][tenant_index] == second_tenant
                assert other.rows[0][target_index] == second_tenant

            with tenant_transaction_scope(make_tenant_context(first_tenant)) as scope:
                original = scope.run(tokens.InvalidationIntentReadToken(intent_id))
                assert len(original.rows) == 1
                assert original.rows[0][tenant_index] == first_tenant
        finally:
            outer.rollback()
