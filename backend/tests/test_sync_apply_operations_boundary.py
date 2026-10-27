"""同期の 9 表の operation 登録とテナント境界を検査する。"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.selectable import Select

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
from pitchlog.sync import tokens
from pitchlog.sync.intent_ids import derive_sync_intent_id, is_sync_intent_id
from pitchlog.sync.port_guard import validate_port_modules


def test_all_sync_operations_use_canonical_single_table_registry() -> None:
    """全登録が構築時検査を通り、型そのもので registry から引ける。"""
    assert len(SYNC_APPLY_OPERATIONS) == 27
    assert type(_OPERATION_REGISTRY) is MappingProxyType
    assert len({spec.token_type for spec in SYNC_APPLY_OPERATIONS}) == 27
    assert Counter(spec.tenant_column.table.name for spec in SYNC_APPLY_OPERATIONS) == {
        "games": 2,
        "recording_generations": 4,
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


def test_generation_read_operations_share_safe_projection() -> None:
    """世代の読取・指定読取・ロックは証拠列を含めず同一順序で返す。"""
    expected = (
        "tenant_id",
        "game_id",
        "generation",
        "kind",
        "issuance_order",
        "holder_device",
        "confirmed_watermark",
        "applied_prefix",
        "granted_at",
        "revoked_at",
        "import_batch_id",
        "retired_at",
    )
    assert tokens.RECORDING_GENERATION_READ_COLUMNS == expected
    for token_type in (
        tokens.RecordingGenerationReadToken,
        tokens.RecordingGenerationByNumberReadToken,
        tokens.RecordingGenerationLockToken,
    ):
        spec = _OPERATION_REGISTRY[token_type]
        assert isinstance(spec.statement, Select)
        assert tuple(c.key for c in spec.statement.selected_columns) == expected
        assert spec.for_update is (token_type is tokens.RecordingGenerationLockToken)


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
