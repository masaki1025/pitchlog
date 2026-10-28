"""記録後read宣言の純境界試験。runtime登録/実DB/復元の成功ではない。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Integer, Select, Table, bindparam, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import BindParameter
from test_authz_tenant_context import make_tenant_context

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import EventSlot, OperationEvent
from pitchlog.repositories import base, transaction
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
from pitchlog.repositories.recorded_snapshot_operations import (
    _UNREGISTERED_DECLARATIONS,
    RECORDED_EVENT_COLUMNS,
    RECORDED_PLAY_ROW_COLUMNS,
    RECORDED_SLOT_COLUMNS,
    RecordedEventRowsReadToken,
    RecordedEventSlotsReadToken,
    RecordedPlayRowsReadToken,
)

_EXPECTED = (
    (
        RecordedEventRowsReadToken,
        OperationEvent,
        "CAP:operation_events:read",
        (
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
        ),
        ("generation", "d1", "d2", "id"),
    ),
    (
        RecordedEventSlotsReadToken,
        EventSlot,
        "CAP:event_slots:read",
        ("game_id", "generation", "d1", "confirmed_version", "tenant_id"),
        ("generation", "d1"),
    ),
    (
        RecordedPlayRowsReadToken,
        PlayRow,
        "CAP:play_rows:read",
        (
            "id",
            "game_id",
            "source_event_id",
            "play_number",
            "batting_order",
            "batter_id",
            "batting_side",
            "strategy_key",
            "strategy_detail_key",
            "strategy_result_key",
            "pitcher_id",
            "catcher_id",
            "batter_status",
            "event_kind",
            "stance",
            "course_x",
            "course_y",
            "pitch_type_key",
            "batting_result_key",
            "secondary_batting_result_key",
            "raw_fielder_position",
            "resolved_fielder_id",
            "batted_ball_type",
            "batted_ball_strength",
            "hit_x",
            "hit_y",
            "pickoff_type",
            "pickoff_detail",
            "error_type",
            "raw_error_position",
            "resolved_error_player_id",
            "pitch_speed",
            "press",
            "fake_run",
            "comment",
            "version",
            "hidden_at",
            "legacy_row_identifier",
            "migration_unverified",
            "tenant_id",
            "import_batch_id",
        ),
        ("play_number", "id"),
    ),
)


def test_exact_three_declared_tables_columns_capabilities_and_bounded_sql() -> None:
    """全21/5/41列と全世代/lifecycleを隠さないSQLを固定する。"""
    assert len(_UNREGISTERED_DECLARATIONS) == len(_EXPECTED) == 3
    assert (
        RECORDED_EVENT_COLUMNS,
        RECORDED_SLOT_COLUMNS,
        RECORDED_PLAY_ROW_COLUMNS,
    ) == tuple(expected[3] for expected in _EXPECTED)
    for spec, (token_type, model, capability, columns, order) in zip(
        _UNREGISTERED_DECLARATIONS, _EXPECTED, strict=True
    ):
        game = uuid4()
        token = token_type(game)
        statement, parameters = spec.prepare(token)
        assert isinstance(statement, Select)
        table = cast(Table, model.__table__)
        assert spec.token_type is token_type and token.capability_id == capability
        assert spec.capability_id == capability
        assert spec.tenant_column is table.c.tenant_id
        assert statement is spec.statement and statement.get_final_froms() == [table]
        assert tuple(statement.selected_columns.keys()) == columns
        assert all(statement.selected_columns[key] is table.c[key] for key in columns)
        assert parameters == {"game_id": game, "limit": 2}
        assert parameters["game_id"] is game
        assert [field.name for field in fields(token)] == ["game_id"]
        assert spec.required_limit_parameter == "limit" and spec.required_limit_max == 2
        assert isinstance(statement._limit_clause, BindParameter)
        assert type(statement._limit_clause.type) is Integer
        assert statement._limit_clause.key == "limit"
        assert statement._for_update_arg is None
        assert not spec.required_bindings and not spec.primary_key_bindings
        assert spec.preflight is spec.allowed_update_columns is None
        assert spec.for_update is spec.use_capability_lock_shape is False
        compiled = statement.compile(dialect=postgresql.dialect())
        assert set(compiled.params) == {"tenant_id", "game_id", "limit"}
        sql = str(compiled)
        where = sql.split("WHERE ", 1)[1].split(" ORDER BY ", 1)[0]
        assert where == (
            f"{table.name}.tenant_id = %(tenant_id)s::UUID AND "
            f"{table.name}.game_id = %(game_id)s::UUID"
        )
        assert sql.split("ORDER BY ", 1)[1].split(" \n LIMIT ", 1)[0] == ", ".join(
            f"{table.name}.{name} ASC NULLS LAST" for name in order
        )
        # Lifecycle/世代はSELECT列に含めるがWHEREから除外しない。二件目を隠さない。
        assert len(statement._where_criteria) == 2
        assert statement._distinct is False and not statement._group_by_clauses
        base._validate_prepared_statement(
            spec, statement, parameters | {"tenant_id": uuid4()}
        )


class UUIDSubtype(UUID):
    """UUID派生型もexactなUUIDとして認定しない。"""


@pytest.mark.parametrize("spec", _UNREGISTERED_DECLARATIONS)
@pytest.mark.parametrize(
    "bad", [None, True, 1, "00000000-0000-4000-8000-000000000001", UUIDSubtype(int=1)]
)
def test_invalid_uuid_rejected_at_construction_and_after_forced_change(
    spec: Any, bad: Any
) -> None:
    """文字列/boolをUUIDに変換せず、prepareでも再検査する。"""
    with pytest.raises(ValueError):
        spec.token_type(bad)
    token = spec.token_type(uuid4())
    object.__setattr__(token, "game_id", bad)
    with pytest.raises(ValueError):
        spec.prepare(token)


@pytest.mark.parametrize("spec", _UNREGISTERED_DECLARATIONS)
def test_frozen_original_game_and_no_free_tenant_limit_or_sql(
    spec: Any,
) -> None:
    """自由な絞込み/上限を入力させず、通常の後書き変更を拒否する。"""
    token = spec.token_type(uuid4())
    with pytest.raises(FrozenInstanceError):
        setattr(token, "game_id", uuid4())
    for name in ("tenant_id", "limit", "sql", "table", "generation", "hidden_at"):
        with pytest.raises(TypeError):
            spec.token_type(uuid4(), **{name: None})
    for other in _UNREGISTERED_DECLARATIONS:
        if other is not spec:
            with pytest.raises(ValueError):
                spec.prepare(cast(Any, other.token_type)(uuid4()))
    subtype = type("UnregisteredRecordedSubtype", (spec.token_type,), {})
    with pytest.raises(ValueError):
        spec.prepare(subtype(uuid4()))


@pytest.mark.parametrize("spec", _UNREGISTERED_DECLARATIONS)
@pytest.mark.parametrize("subtype", [False, True])
def test_unregistered_exact_or_derived_type_cannot_reach_real_executor(
    spec: Any, subtype: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未登録本型/派生型は真正handleでもSQL実行以前に拒否される。"""
    kind = (
        type("UnknownRecorded", (spec.token_type,), {}) if subtype else spec.token_type
    )
    token = kind(uuid4())
    assert all(row.token_type is not kind for row in PRODUCT_OPERATIONS)
    assert kind not in base._OPERATION_REGISTRY
    calls = []

    class NoExecute:
        """SQLが来たら試験を失敗させる。実DB成功のdoubleではない。"""

        def execute(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))
            raise AssertionError("未登録readのSQL到達")

    context = make_tenant_context(uuid4())
    key = object()
    monkeypatch.setitem(transaction._TRANSACTION_RUNTIMES, key, (NoExecute(), object()))
    handle = transaction._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    try:
        with pytest.raises(base._TenantOperationError, match="未登録"):
            base._operation_spec(token)
        with pytest.raises(base._TenantOperationError, match="未登録"):
            handle.run(token)
    finally:
        handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run(token)
    assert calls == []


@pytest.mark.parametrize("spec", _UNREGISTERED_DECLARATIONS)
def test_real_preparer_injects_context_tenant_under_explicit_lookup_double(
    spec: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """解決だけdoubleに限定し既実preparerのtenant注入/厳密validatorを検査する。"""
    # 正式registry/実handleへ候補を登録しない。これはDB/認可成功の証拠ではない。
    token = spec.token_type(uuid4())
    tenant = uuid4()
    monkeypatch.setattr(base, "_operation_spec", lambda _: spec)
    statement, parameters = base._prepare_operation(token, tenant)
    assert statement is spec.statement
    assert parameters == {"tenant_id": tenant, "game_id": token.game_id, "limit": 2}


@pytest.mark.parametrize("spec", _UNREGISTERED_DECLARATIONS)
@pytest.mark.parametrize("bad_limit", [None, True, -1, 0, 3, "2"])
def test_real_statement_validator_rejects_limit_parameter_substitution(
    spec: Any, bad_limit: Any
) -> None:
    """上限の欠落/型偽装/超過を既実validatorで拒否する。"""
    statement, parameters = spec.prepare(spec.token_type(uuid4()))
    with pytest.raises(base._TenantOperationError):
        base._validate_prepared_statement(
            spec, statement, parameters | {"tenant_id": uuid4(), "limit": bad_limit}
        )


@pytest.mark.parametrize("spec", _UNREGISTERED_DECLARATIONS)
def test_real_validator_rejects_missing_tenant_and_changed_limit_bind(
    spec: Any,
) -> None:
    """任意tenantの条件や未限定SELECTへ置き換えられない。"""
    statement, parameters = spec.prepare(spec.token_type(uuid4()))
    assert isinstance(statement, Select)
    table = spec.tenant_column.table
    attacker = (
        select(*table.c)
        .where(table.c.tenant_id == bindparam("attacker_tenant"))
        .where(table.c.game_id == bindparam("game_id"))
        .limit(bindparam("limit", type_=Integer))
    )
    for invalid in (
        attacker,
        statement.limit(None),
        statement.limit(bindparam("free_limit")),
    ):
        with pytest.raises(base._TenantOperationError):
            base._TenantScopedOperation(spec.capability_id, invalid, spec.tenant_column)
            base._validate_prepared_statement(
                spec, invalid, parameters | {"tenant_id": uuid4()}
            )
