"""同期適用が必要とするリポジトリ基底の境界を DB なしで検査する。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, bindparam, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select
from test_authz_tenant_context import make_tenant_context

from pitchlog.db.base import Base
from pitchlog.db.game_state.models import Game
from pitchlog.db.recording_rights.models import RecordingGeneration
from pitchlog.db.sync_protocol.models import EventSlot, IdempotencyLedger
from pitchlog.db.tenant_isolation.models import Player
from pitchlog.repositories import transaction
from pitchlog.repositories.base import (
    _materialize_rows,
    _TenantOperationError,
    _validate_prepared_statement,
)
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PrimaryKeyBinding,
)
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True)
class _ProbeToken(TenantOperationToken):
    """登録文の検査にだけ使う token。"""

    @property
    def capability_id(self) -> str:
        """合成登録の既知 capability を返す。"""
        return "CAP:games:read"


def _update_registration(
    table: Table,
    *,
    columns: tuple[str, ...],
    set_column: str,
) -> tuple[OperationRegistration, Update]:
    """実際の複合主キー表を使って登録文を作る。"""
    statement = (
        update(table)
        .where(*(table.c[name] == bindparam(f"where_{name}") for name in columns))
        .values({set_column: bindparam(f"set_{set_column}")})
    )
    bindings = tuple(
        PrimaryKeyBinding(table.c[name], f"where_{name}")
        for name in table.primary_key.columns.keys()
    )
    registration = OperationRegistration(
        _ProbeToken,
        f"CAP:{table.name}:update",
        statement,
        table.c.tenant_id,
        lambda _token: (statement, {}),
        allowed_update_columns=frozenset({set_column}),
        primary_key_bindings=bindings,
    )
    return registration, statement


@pytest.mark.parametrize(
    ("model", "key_columns", "set_column"),
    (
        (RecordingGeneration, ("tenant_id", "game_id", "generation"), "applied_prefix"),
        (EventSlot, ("tenant_id", "game_id", "generation", "d1"), "confirmed_version"),
    ),
)
def test_composite_primary_key_update_requires_all_equalities(
    model: type[Any], key_columns: tuple[str, ...], set_column: str
) -> None:
    """D3 とスロット版の UPDATE は主キー全列の等値だけで行を識別する。"""
    table = cast(Table, model.__table__)
    registration, statement = _update_registration(
        table, columns=key_columns, set_column=set_column
    )
    _validate_prepared_statement(registration, statement)
    statement.compile(dialect=postgresql.dialect())

    for missing in key_columns:
        incomplete, incomplete_statement = _update_registration(
            table,
            columns=tuple(name for name in key_columns if name != missing),
            set_column=set_column,
        )
        with pytest.raises(_TenantOperationError, match="主キー全列の等値条件"):
            _validate_prepared_statement(incomplete, incomplete_statement)

    with pytest.raises(_TenantOperationError, match="主キー全列の宣言"):
        _validate_prepared_statement(
            replace(
                registration,
                primary_key_bindings=registration.primary_key_bindings[:-1],
            ),
            statement,
        )


def test_composite_update_rejects_column_named_bind() -> None:
    """主キーの bind 名が列名と重なる文をコンパイル前に拒否する。"""
    table = cast(Table, RecordingGeneration.__table__)
    registration, statement = _update_registration(
        table,
        columns=("tenant_id", "game_id", "generation"),
        set_column="applied_prefix",
    )
    overlapping = replace(
        registration,
        primary_key_bindings=(
            *registration.primary_key_bindings[:-1],
            PrimaryKeyBinding(table.c.generation, "generation"),
        ),
    )
    with pytest.raises(_TenantOperationError, match="bind 名は列名と重複"):
        _validate_prepared_statement(overlapping, statement)


def test_undeclared_update_cannot_omit_part_of_actual_primary_key() -> None:
    """旧形式の id 条件があっても、第三の主キー列を省いた UPDATE を拒否する。"""
    table = Table(
        "segmented_rows",
        Base.metadata,
        Column("tenant_id", Integer, primary_key=True),
        Column("id", Integer, primary_key=True),
        Column("segment", Integer, primary_key=True),
        Column("payload", Integer),
    )
    statement = (
        update(table)
        .where(table.c.tenant_id == bindparam("where_tenant_id"))
        .where(table.c.id == bindparam("where_id"))
        .values(payload=bindparam("set_payload"))
    )
    registration = OperationRegistration(
        _ProbeToken,
        "CAP:segmented_rows:update",
        statement,
        table.c.tenant_id,
        lambda _token: (statement, {}),
        allowed_update_columns=frozenset({"payload"}),
    )
    try:
        with pytest.raises(_TenantOperationError, match="主キー全列の等値条件"):
            _validate_prepared_statement(registration, statement)

        complete = statement.where(table.c.segment == bindparam("where_segment"))
        _validate_prepared_statement(
            replace(registration, statement=complete), complete
        )
    finally:
        Base.metadata.remove(table)


def test_shadow_table_with_reduced_primary_key_is_rejected() -> None:
    """event_slots と同名でも別 Table の 2 列主キー登録を拒否する。"""
    canonical = cast(Table, EventSlot.__table__)
    assert Base.metadata.tables[canonical.key] is canonical
    shadow = Table(
        canonical.name,
        MetaData(),
        Column("tenant_id", Integer, primary_key=True),
        Column("game_id", Integer, primary_key=True),
        Column("confirmed_version", Integer),
    )
    registration, statement = _update_registration(
        shadow,
        columns=("tenant_id", "game_id"),
        set_column="confirmed_version",
    )
    with pytest.raises(_TenantOperationError, match="正本 ORM の Table"):
        _validate_prepared_statement(registration, statement)

    canonical_registration, _ = _update_registration(
        canonical,
        columns=("tenant_id", "game_id", "generation", "d1"),
        set_column="confirmed_version",
    )
    with pytest.raises(_TenantOperationError, match="登録文の対象表は正本 ORM"):
        _validate_prepared_statement(canonical_registration, statement)


def test_existing_product_updates_bind_every_actual_primary_key_column() -> None:
    """Roster と lineup の旧登録も実表の主キー全列を束縛する。"""
    updates = [
        spec
        for spec in PRODUCT_OPERATIONS
        if isinstance(spec.statement, Update)
        and spec.token_type.__module__.startswith("pitchlog.repositories.")
    ]
    assert {spec.capability_id for spec in updates} == {
        "CAP:players:update",
        "CAP:team_records:update",
        "CAP:lineup_memories:update",
    }
    for spec in updates:
        _validate_prepared_statement(spec, spec.statement)
    assert not any(
        spec.capability_id == "CAP:invalidation_intents:update" for spec in updates
    )


def test_existing_product_registrations_use_canonical_orm_tables() -> None:
    """Roster・意図・lineup の登録文が正本 metadata の Table を使う。"""
    for spec in PRODUCT_OPERATIONS:
        table = cast(Table, spec.tenant_column.table)
        assert Base.metadata.tables[table.key] is table
        if isinstance(spec.statement, Select):
            froms = spec.statement.get_final_froms()
            assert len(froms) == 1 and froms[0] is table
        else:
            assert spec.statement.table is table


def test_primary_key_and_set_cannot_share_bind() -> None:
    """行識別の generation と SET が同じ bind を使う変異を拒否する。"""
    table = cast(Table, RecordingGeneration.__table__)
    registration, _ = _update_registration(
        table,
        columns=("tenant_id", "game_id", "generation"),
        set_column="applied_prefix",
    )
    statement = (
        update(table)
        .where(table.c.tenant_id == bindparam("where_tenant_id"))
        .where(table.c.game_id == bindparam("where_game_id"))
        .where(table.c.generation == bindparam("set_applied_prefix"))
        .values(applied_prefix=bindparam("set_applied_prefix"))
    )
    shared = replace(
        registration,
        statement=statement,
        primary_key_bindings=(
            *registration.primary_key_bindings[:-1],
            PrimaryKeyBinding(table.c.generation, "set_applied_prefix"),
        ),
    )
    with pytest.raises(_TenantOperationError, match="主キー bind と UPDATE SET bind"):
        _validate_prepared_statement(shared, statement)


def test_legacy_update_cannot_reuse_where_id_for_set() -> None:
    """宣言なしの旧登録でも WHERE 主キーと SET の bind 共用を拒否する。"""
    registration = next(
        spec
        for spec in PRODUCT_OPERATIONS
        if spec.token_type.__name__ == "PlayerUpdateToken"
    )
    assert isinstance(registration.statement, Update)
    statement = registration.statement.values(name=bindparam("where_id"))
    with pytest.raises(_TenantOperationError, match="主キー bind と UPDATE SET bind"):
        _validate_prepared_statement(registration, statement)


def test_tenant_primary_key_cannot_declare_another_bind() -> None:
    """文脈が入れる where_tenant_id 以外をテナント主キーに宣言できない。"""
    table = cast(Table, RecordingGeneration.__table__)
    registration, statement = _update_registration(
        table,
        columns=("tenant_id", "game_id", "generation"),
        set_column="applied_prefix",
    )
    contradictory = replace(
        registration,
        primary_key_bindings=(
            PrimaryKeyBinding(table.c.tenant_id, "other_tenant_id"),
            *registration.primary_key_bindings[1:],
        ),
    )
    with pytest.raises(_TenantOperationError, match="テナント主キーには文脈の bind 名"):
        _validate_prepared_statement(contradictory, statement)


def test_row_lock_tenant_primary_key_uses_context_bind() -> None:
    """SELECT の行ロックでもテナント主キーには文脈の bind を要求する。"""
    registration, statement = _game_lock()
    table = cast(Table, Game.__table__)
    contradictory = replace(
        registration,
        primary_key_bindings=(
            PrimaryKeyBinding(table.c.tenant_id, "other_tenant_id"),
            *registration.primary_key_bindings[1:],
        ),
    )
    with pytest.raises(_TenantOperationError, match="テナント主キーには文脈の bind 名"):
        _validate_prepared_statement(contradictory, statement)


def _game_lock() -> tuple[OperationRegistration, Select[Any]]:
    """試合行を通常の FOR UPDATE で取得する登録文を作る。"""
    table = cast(Table, Game.__table__)
    statement = (
        select(table.c.id)
        .where(table.c.tenant_id == bindparam("tenant_id"))
        .where(table.c.id == bindparam("game_id"))
        .with_for_update()
    )
    registration = OperationRegistration(
        _ProbeToken,
        "CAP:games:read",
        statement,
        table.c.tenant_id,
        lambda _token: (statement, {}),
        primary_key_bindings=(
            PrimaryKeyBinding(table.c.tenant_id, "tenant_id"),
            PrimaryKeyBinding(table.c.id, "game_id"),
        ),
        for_update=True,
    )
    return registration, statement


def test_declared_game_row_lock_and_unlocked_read() -> None:
    """試合行の明示ロックを許可し、宣言なしの読取文にロックを付けない。"""
    registration, statement = _game_lock()
    _validate_prepared_statement(registration, statement)
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))

    unlocked = statement._generate()
    unlocked._for_update_arg = None
    ordinary = replace(
        registration, statement=unlocked, primary_key_bindings=(), for_update=False
    )
    _validate_prepared_statement(ordinary, unlocked)
    assert "FOR UPDATE" not in str(unlocked.compile(dialect=postgresql.dialect()))


def test_declared_generation_row_lock_is_accepted() -> None:
    """試合行の次に取る記録権世代行も通常ロックで登録できる。"""
    table = cast(Table, RecordingGeneration.__table__)
    statement = (
        select(table.c.generation)
        .where(table.c.tenant_id == bindparam("tenant_id"))
        .where(table.c.game_id == bindparam("game_id"))
        .where(table.c.generation == bindparam("generation_key"))
        .with_for_update()
    )
    registration = OperationRegistration(
        _ProbeToken,
        "CAP:recording_generations:read",
        statement,
        table.c.tenant_id,
        lambda _token: (statement, {}),
        primary_key_bindings=(
            PrimaryKeyBinding(table.c.tenant_id, "tenant_id"),
            PrimaryKeyBinding(table.c.game_id, "game_id"),
            PrimaryKeyBinding(table.c.generation, "generation_key"),
        ),
        for_update=True,
    )
    _validate_prepared_statement(registration, statement)
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))


def test_general_player_row_lock_does_not_need_lineup_shape() -> None:
    """Players の通常ロックにも共通の主キー検査を使う。"""
    table = cast(Table, Player.__table__)
    statement = (
        select(table.c.id)
        .where(table.c.tenant_id == bindparam("tenant_id"))
        .where(table.c.id == bindparam("player_id"))
        .with_for_update()
    )
    registration = OperationRegistration(
        _ProbeToken,
        "CAP:players:read",
        statement,
        table.c.tenant_id,
        lambda _token: (statement, {}),
        primary_key_bindings=(
            PrimaryKeyBinding(table.c.tenant_id, "tenant_id"),
            PrimaryKeyBinding(table.c.id, "player_id"),
        ),
        for_update=True,
    )
    _validate_prepared_statement(registration, statement)
    assert not registration.use_capability_lock_shape


def test_lineup_locks_explicitly_request_specialized_validation() -> None:
    """U-M2 の限定形だけは既存の capability 検査器へ元の文を渡す。"""
    specialized = [
        spec for spec in PRODUCT_OPERATIONS if spec.use_capability_lock_shape
    ]
    assert {spec.token_type.__name__ for spec in specialized} == {
        "_SelfTeamLockToken",
        "_ActiveLineupPlayerLockToken",
    }
    for spec in specialized:
        _validate_prepared_statement(spec, spec.statement)


def test_specialized_lock_declaration_rejects_missing_lock() -> None:
    """限定形の検査宣言だけを残して FOR UPDATE を消す変異を拒否する。"""
    specialized = next(
        spec for spec in PRODUCT_OPERATIONS if spec.use_capability_lock_shape
    )
    assert isinstance(specialized.statement, Select)
    statement = specialized.statement._generate()
    statement._for_update_arg = None
    with pytest.raises(_TenantOperationError, match="宣言と登録文が不一致"):
        _validate_prepared_statement(specialized, statement)


def test_specialized_lineup_lock_rejects_missing_visibility_condition() -> None:
    """限定ロックの宣言を残し、非表示条件を落とす変異を拒否する。"""
    specialized = next(
        spec
        for spec in PRODUCT_OPERATIONS
        if spec.token_type.__name__ == "_SelfTeamLockToken"
    )
    table = cast(Table, specialized.tenant_column.table)
    statement = (
        select(table.c.id)
        .where(table.c.tenant_id == bindparam("tenant_id"))
        .where(table.c.id == bindparam("team_record_id"))
        .where(table.c.kind == bindparam("kind"))
        .with_for_update()
    )
    with pytest.raises(_TenantOperationError, match="FOR UPDATE"):
        _validate_prepared_statement(specialized, statement)


@pytest.mark.parametrize("variant", ("nowait", "skip_locked", "read", "key_share"))
def test_row_lock_variants_are_rejected(variant: str) -> None:
    """U-M2 と同じく通常ロック以外を登録しない。"""
    registration, statement = _game_lock()
    if variant == "nowait":
        changed = statement.with_for_update(nowait=True)
    elif variant == "skip_locked":
        changed = statement.with_for_update(skip_locked=True)
    elif variant == "read":
        changed = statement.with_for_update(read=True)
    else:
        changed = statement.with_for_update(key_share=True)
    with pytest.raises(_TenantOperationError, match="通常の行ロック"):
        _validate_prepared_statement(registration, changed)


def test_undeclared_or_missing_row_lock_is_rejected() -> None:
    """宣言と文の FOR UPDATE 状態が異なる場合は登録時に拒否する。"""
    registration, statement = _game_lock()
    with pytest.raises(_TenantOperationError, match="宣言と登録文が不一致"):
        _validate_prepared_statement(replace(registration, for_update=False), statement)
    unlocked = statement._generate()
    unlocked._for_update_arg = None
    with pytest.raises(_TenantOperationError, match="宣言と登録文が不一致"):
        _validate_prepared_statement(registration, unlocked)


def test_declared_row_lock_requires_complete_primary_key() -> None:
    """試合行ロックの対象 ID が欠ける文は登録時に拒否する。"""
    registration, _ = _game_lock()
    table = cast(Table, Game.__table__)
    incomplete = (
        select(table.c.id)
        .where(table.c.tenant_id == bindparam("tenant_id"))
        .with_for_update()
    )
    with pytest.raises(_TenantOperationError, match="主キー全列の等値条件"):
        _validate_prepared_statement(registration, incomplete)


def test_ledger_jsonb_result_is_deeply_immutable() -> None:
    """台帳 result に相当する入れ子の JSONB 値を不変の行へ実体化する。"""
    table = cast(Table, IdempotencyLedger.__table__)
    assert isinstance(table.c.result.type, JSONB)
    source = {"accepted": [{"d1": 1, "status": "applied"}]}
    result = _materialize_rows(((source,),))
    value = result.rows[0][0]
    assert isinstance(value, MappingProxyType)
    assert isinstance(value["accepted"], tuple)
    source["accepted"] = []
    assert value["accepted"] == (MappingProxyType({"d1": 1, "status": "applied"}),)
    with pytest.raises(TypeError):
        cast(Any, value)["new"] = True


def test_sync_apply_mark_rejects_new_scope_before_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主スコープ内の適用印は別スコープを Session 生成前に拒否する。"""
    context = make_tenant_context(uuid4())
    prepared_scope = transaction.tenant_transaction_scope(context)
    monkeypatch.setattr(
        transaction,
        "Session",
        lambda _engine: pytest.fail("新しい Session へ到達した"),
    )
    with transaction._sync_apply_active():
        with pytest.raises(RuntimeError, match="同期適用中"):
            with prepared_scope:
                pytest.fail("別スコープへ入った")
    assert not transaction._SYNC_APPLY_ACTIVE.get()


def test_sync_apply_mark_is_reset_after_failure() -> None:
    """適用側の例外でも印を下ろして次の要求へ漏らさない。"""
    with pytest.raises(ValueError, match="適用失敗"):
        with transaction._sync_apply_active():
            raise ValueError("適用失敗")
    assert not transaction._SYNC_APPLY_ACTIVE.get()
