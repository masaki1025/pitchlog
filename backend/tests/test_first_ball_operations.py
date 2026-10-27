"""未登録初球SQLの全列と原イベントpreflightをpure doubleで確認する。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from types import MappingProxyType
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.repositories import base
from pitchlog.repositories.first_ball_operations import (
    _UNREGISTERED_DECLARATIONS,
    PLAY_ROW_COLUMNS,
    FirstBallOperationError,
)
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.first_ball_tokens import (
    FirstBallPlayRowInsertToken,
    FirstBallPlayRowReadToken,
)
from pitchlog.sync.tokens import IdempotencyLedgerReadToken, OperationEventReadToken

_INSERT, _READ = _UNREGISTERED_DECLARATIONS
_TENANT = UUID(int=100)
_OTHER = UUID(int=999)
_ERROR = "初球PlayRowの投影値又は原イベントが一致しません"


def _token(**changes: object) -> FirstBallPlayRowInsertToken:
    return replace(
        FirstBallPlayRowInsertToken(
            id=UUID(int=1),
            game_id=UUID(int=2),
            source_event_id=UUID(int=3),
            generation=2,
            d1=1,
            d2=1024,
            d5=UUID(int=4),
            source_fingerprint="wire-v1:" + "a" * 64,
            batter_id=UUID(int=5),
            pitcher_id=UUID(int=6),
            catcher_id=UUID(int=7),
            pitch_type_key="fastball",
            course_x=0.0,
            course_y=1.0,
        ),
        **changes,
    )


def _parameters(token: FirstBallPlayRowInsertToken) -> dict[str, object]:
    return _INSERT.prepare(token)[1] | {"tenant_id": _TENANT}


def _row(model: type, values: dict[str, object]) -> TenantOperationResult:
    return TenantOperationResult((tuple(values.get(c.key) for c in model.__table__.c),))


def _results(token: FirstBallPlayRowInsertToken) -> tuple[TenantOperationResult, ...]:
    event = {
        "tenant_id": _TENANT,
        "id": token.source_event_id,
        "game_id": token.game_id,
        "generation": token.generation,
        "d1": token.d1,
        "d2": token.d2,
        "d5": token.d5,
        "ledger_kind": "accepted",
        "event_kind": "play_input",
        "migration_unverified": False,
        "is_tombstone": False,
        "payload": MappingProxyType({}),
        "state_diff": MappingProxyType({}),
    }
    ledger = {
        "tenant_id": _TENANT,
        "d5": token.d5,
        "kind": "accepted",
        "source_fingerprint": token.source_fingerprint,
    }
    return (
        _row(OperationEvent, event),
        _row(IdempotencyLedger, ledger),
        TenantOperationResult(()),
    )


def _preflight(token: FirstBallPlayRowInsertToken):
    assert _INSERT.preflight is not None
    return _INSERT.preflight(token, _parameters(token))


def test_canonical_table_full41_columns_and_bind_names() -> None:
    """独自Tableを作らず全41列を明示し、検証用値を新列にしない。"""
    token = _token()
    statement, parameters = _INSERT.prepare(token)
    assert statement.table is PlayRow.__table__
    assert _INSERT.tenant_column is PlayRow.__table__.c.tenant_id
    assert PLAY_ROW_COLUMNS == tuple(PlayRow.__table__.c.keys())
    assert len(PLAY_ROW_COLUMNS) == 41
    assert set(statement._values) == set(PLAY_ROW_COLUMNS)
    assert set(parameters) == set(PLAY_ROW_COLUMNS) - {"tenant_id"}
    assert tuple(c.key for c in statement._returning) == PLAY_ROW_COLUMNS
    assert set(statement.compile(dialect=postgresql.dialect()).params) == set(
        PLAY_ROW_COLUMNS
    )
    for name, value in statement._values.items():
        assert value.key == name
    assert {"d1", "d2", "d5", "generation", "source_fingerprint"}.isdisjoint(parameters)
    assert parameters["play_number"] == 1 and parameters["play_number"] != token.d2
    assert parameters["batting_order"] == parameters["version"] == 1
    assert parameters["event_kind"] == "pitch"
    assert parameters["batting_result_key"] == "batting-result.ball"
    assert parameters["migration_unverified"] is False
    supplied = {
        "id",
        "game_id",
        "source_event_id",
        "batter_id",
        "pitcher_id",
        "catcher_id",
        "pitch_type_key",
        "course_x",
        "course_y",
        "pitch_speed",
        "stance",
        "batting_side",
    }
    constants = {
        "play_number",
        "batting_order",
        "event_kind",
        "batting_result_key",
        "version",
        "migration_unverified",
    }
    for name in set(parameters) - supplied - constants:
        assert parameters[name] is None


@pytest.mark.parametrize("speed", [None, -10.0, 0.0, 135.5, 500.0])
@pytest.mark.parametrize("stance,side", [(None, None), ("1", "右"), ("25", "左")])
def test_nullable_observations_and_physical_values_unchanged(
    speed, stance, side
) -> None:
    """有限負値や0と欠損を区別し、範囲外を丸めたり硬拒否しない。"""
    token = _token(pitch_speed=speed, stance=stance, batting_side=side)
    _, parameters = _INSERT.prepare(token)
    assert parameters["pitch_speed"] == speed
    assert type(parameters["pitch_speed"]) is type(speed)
    assert parameters["stance"] == stance
    assert parameters["batting_side"] == side
    assert parameters["course_x"] == token.course_x
    assert parameters["course_y"] == token.course_y
    _preflight(token).validate(_results(token))


@pytest.mark.parametrize(
    "member,bad",
    [
        ("id", "secret"),
        ("game_id", None),
        ("source_event_id", "secret"),
        ("d5", True),
        ("batter_id", None),
        ("pitcher_id", "bad"),
        ("catcher_id", "bad"),
        ("generation", True),
        ("generation", 0),
        ("generation", 2**63),
        ("d1", True),
        ("d1", 2),
        ("d2", True),
        ("d2", 2**63),
        ("d2", -(2**63) - 1),
        ("source_fingerprint", ""),
        ("source_fingerprint", "wire-request-v1:" + "a" * 64),
        ("source_fingerprint", "wire-v1:" + "A" * 64),
        ("source_fingerprint", False),
        ("pitch_type_key", ""),
        ("pitch_type_key", 1),
        ("course_x", None),
        ("course_x", True),
        ("course_x", 0),
        ("course_x", float("nan")),
        ("course_x", -0.1),
        ("course_y", 1.1),
        ("course_y", float("inf")),
        ("pitch_speed", True),
        ("pitch_speed", float("nan")),
        ("pitch_speed", float("inf")),
        ("stance", "0"),
        ("stance", "01"),
        ("stance", 1),
        ("stance", "26"),
        ("batting_side", "両"),
        ("batting_side", True),
    ],
)
def test_invalid_token_values_are_fixed_rejection(member, bad) -> None:
    """型違い・非有限・未対応観測を保存値に補完しない。"""
    token = _token(**{member: bad})
    with pytest.raises(FirstBallOperationError) as error:
        _INSERT.prepare(token)
    assert str(error.value) == _ERROR
    assert "secret" not in str(error.value)


def test_protected_fields_not_caller_inputs_and_frozen_token() -> None:
    """tenantや固定scope列をcallerの自由値へしない。"""
    names = {f.name for f in fields(FirstBallPlayRowInsertToken)}
    assert {
        "tenant_id",
        "play_number",
        "batting_order",
        "event_kind",
        "version",
        "hidden_at",
        "migration_unverified",
        "import_batch_id",
        "legacy_row_identifier",
        "sql",
        "table",
    }.isdisjoint(names)
    with pytest.raises(FrozenInstanceError):
        _token().course_x = 0.5
    assert "wire-v1" not in repr(_token())


def test_preflight_uses_existing_same_event_and_ledger_reads() -> None:
    """既tokenを同handleへ渡し、同game/sourceの重複投影も拒否する。"""
    token = _token()
    check = _preflight(token)
    assert check.operations == (
        OperationEventReadToken(token.game_id, token.generation, token.d1),
        IdempotencyLedgerReadToken(token.d5),
        FirstBallPlayRowReadToken(token.game_id, token.source_event_id),
    )
    check.validate(_results(token))


@pytest.mark.parametrize(
    "table,field,bad",
    [
        ("event", "tenant_id", _OTHER),
        ("event", "game_id", _OTHER),
        ("event", "id", _OTHER),
        ("event", "generation", 1),
        ("event", "generation", True),
        ("event", "d1", True),
        ("event", "d2", 1),
        ("event", "d5", _OTHER),
        ("event", "event_kind", "1"),
        ("event", "ledger_kind", "rejected"),
        ("event", "retired_at", "old"),
        ("event", "replaced_at", "old"),
        ("event", "import_batch_id", _OTHER),
        ("event", "legacy_row_identifier", "old"),
        ("event", "migration_unverified", True),
        ("event", "is_tombstone", True),
        ("event", "target_generation", 1),
        ("event", "target_d1", 1),
        ("event", "expected_version", 1),
        ("event", "change_order", 1),
        ("ledger", "tenant_id", _OTHER),
        ("ledger", "d5", _OTHER),
        ("ledger", "kind", "evacuated"),
        ("ledger", "source_fingerprint", "other"),
        ("ledger", "retired_at", "old"),
    ],
)
def test_preflight_foreign_stale_or_different_original_rejected(
    table, field, bad
) -> None:
    """FKだけでは守れない同game/D5と現行native原本を照合する。"""
    token = _token()
    results = list(_results(token))
    index, model = (0, OperationEvent) if table == "event" else (1, IdempotencyLedger)
    columns = tuple(model.__table__.c.keys())
    row = list(results[index].rows[0])
    row[columns.index(field)] = bad
    results[index] = TenantOperationResult((tuple(row),))
    with pytest.raises(FirstBallOperationError, match=_ERROR):
        _preflight(token).validate(tuple(results))


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("shape", ["zero", "two", "partial", "list"])
def test_preflight_zero_multiple_partial_rows_rejected(index, shape) -> None:
    """原本0/2行や不正な列集合を部分一致で通さない。"""
    token = _token()
    results = list(_results(token))
    row = results[index].rows[0]
    rows = {"zero": (), "two": (row, row), "partial": (row[:-1],), "list": [row]}[shape]
    results[index] = TenantOperationResult(rows)
    with pytest.raises(FirstBallOperationError):
        _preflight(token).validate(tuple(results))


def test_preflight_rejects_prior_projection_and_changed_sql_bindings() -> None:
    """再投影と検証後の別tenant/別行へのbind混入を拒否する。"""
    token = _token()
    results = list(_results(token))
    results[2] = TenantOperationResult(((UUID(int=88),),))
    with pytest.raises(FirstBallOperationError):
        _preflight(token).validate(tuple(results))
    for changed in (
        {"tenant_id": "bad"},
        {"game_id": _OTHER},
        {"play_number": 1024},
        {"hidden_at": "old"},
        {"extra": "secret"},
    ):
        with pytest.raises(FirstBallOperationError):
            _INSERT.preflight(token, _parameters(token) | changed)


def test_read_sql_is_same_tenant_game_source_bounded_native() -> None:
    """readの全列と同源条件/上限2を固定する。"""
    token = FirstBallPlayRowReadToken(UUID(int=2), UUID(int=3))
    statement, parameters = _READ.prepare(token)
    assert tuple(c.key for c in statement.selected_columns) == PLAY_ROW_COLUMNS
    assert statement.get_final_froms() == [PlayRow.__table__]
    assert parameters == {
        "game_id": token.game_id,
        "source_event_id": token.source_event_id,
        "limit": 2,
        "migration_unverified": False,
    }
    assert _READ.required_limit_parameter == "limit" and _READ.required_limit_max == 2
    sql = str(statement.compile(dialect=postgresql.dialect()))
    for fragment in (
        "tenant_id =",
        "game_id =",
        "source_event_id =",
        "hidden_at IS NULL",
        "import_batch_id IS NULL",
        "legacy_row_identifier IS NULL",
        "migration_unverified =",
        "LIMIT",
    ):
        assert fragment in sql
    assert "FOR UPDATE" not in sql
    with pytest.raises(FirstBallOperationError):
        _READ.prepare(FirstBallPlayRowReadToken("bad", UUID(int=3)))


def test_unregistered_tokens_never_enter_production_sql() -> None:
    """正式registry未登録なので実行器は文準備以前に拒否する。"""
    for token in (_token(), FirstBallPlayRowReadToken(UUID(int=2), UUID(int=3))):
        assert all(r.token_type is not type(token) for r in PRODUCT_OPERATIONS)
        with pytest.raises(base._TenantOperationError, match="未登録または偽造"):
            base._operation_spec(token)
    with pytest.raises(FirstBallOperationError):
        _INSERT.prepare(FirstBallPlayRowReadToken(UUID(int=2), UUID(int=3)))


@pytest.mark.parametrize(
    "name", ["tenant_id", "sql", "table", "play_number", "event_kind", "hidden_at"]
)
def test_unknown_and_protected_constructor_input_rejected(name: str) -> None:
    """未対応/保護入力を受け捨てる可変dict tokenにしない。"""
    with pytest.raises(TypeError):
        FirstBallPlayRowInsertToken(**{name: "secret"})


def test_uninitialized_tokens_rejected_and_preflight_snapshot_stable() -> None:
    """偽tokenとpreflight発行後の原token強制変更を隔離する。"""
    with pytest.raises(FirstBallOperationError):
        _INSERT.prepare(object.__new__(FirstBallPlayRowInsertToken))
    with pytest.raises(FirstBallOperationError):
        _READ.prepare(object.__new__(FirstBallPlayRowReadToken))
    token = _token()
    expected_results = _results(token)
    check = _preflight(token)
    object.__setattr__(token, "source_event_id", _OTHER)
    check.validate(expected_results)
