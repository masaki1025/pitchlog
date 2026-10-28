"""記録後read宣言の純境界試験。runtime登録/実DB/復元の成功ではない。"""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Integer, Select, Table, bindparam, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import BindParameter
from test_authz_tenant_context import make_tenant_context
from test_started_snapshot import CASES, Bundle

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import EventSlot, OperationEvent
from pitchlog.repositories import base, transaction
from pitchlog.repositories import recorded_snapshot as recorded
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
from pitchlog.sync.tokens import IdempotencyLedgerReadToken

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


# R2-Aは実runだけを合成し、独立開始原本と正式artifactの再評価を確認する。


class RecordedBundle(Bundle):
    """golden入力/保存期待値を持つ純row群。実DB成功ではない。"""

    tx: SimpleNamespace

    def __init__(self):
        """保存blobと独立開始原本を別objectで構成する。"""
        super().__init__()
        self.generation.update(confirmed_watermark=1, applied_prefix=1)
        self.generation["generation"] = 2**40
        self.event_id, self.d5, self.row_id = uuid4(), uuid4(), uuid4()
        away, home = self.lineups

        def player(side, *, batting=None, position=None):
            entries = side["entries_with_uniform_number_snapshot"]
            matches = [
                e["player_id"]
                for e in entries
                if (batting is not None and e["batting_order"] == batting)
                or (
                    position is not None
                    and e["fielding_position"]
                    == {"kind": "fielding", "position": position}
                )
            ]
            assert len(matches) == 1
            return matches[0]

        participants = {
            "batterId": player(away, batting=1),
            "pitcherId": player(home, position=1),
            "catcherId": player(home, position=2),
            "battingOrder": "1",
        }
        artifact = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "frontend/public/domain/pitchlog-domain.json"
            ).read_text()
        )["sha256"]
        self.saved_payload = {
            "formatVersion": "first-ball-play-v1",
            "observations": {
                "pitchTypeKey": "synthetic-only",
                "course": {"unit": "1/263", "x": "132", "y": "131"},
                "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                "stance": None,
                "battingSide": None,
            },
            "participants": participants,
            "calculation": {
                "formatVersion": "first-ball-calculation-v1",
                "artifactSha256": artifact,
                "request": copy.deepcopy(CASES[0]["request"]),
                "response": copy.deepcopy(CASES[0]["expected"]),
            },
        }
        self.events = [dict.fromkeys(recorded.RECORDED_EVENT_COLUMNS)]
        self.events[0].update(
            tenant_id=self.tenant,
            game_id=self.game_id,
            id=self.event_id,
            d5=self.d5,
            generation=self.generation["generation"],
            d1=1,
            d2=1024,
            ledger_kind="accepted",
            event_kind="play_input",
            is_tombstone=False,
            migration_unverified=False,
            payload=self.saved_payload,
            state_diff=copy.deepcopy(
                CASES[0]["expected"]["value"]["t1"]["historyContext"][0]["difference"]
            ),
        )
        self.slots = [
            dict(
                tenant_id=self.tenant,
                game_id=self.game_id,
                generation=self.generation["generation"],
                d1=1,
                confirmed_version=1,
            )
        ]
        self.plays = [dict.fromkeys(recorded.RECORDED_PLAY_ROW_COLUMNS)]
        self.plays[0].update(
            tenant_id=self.tenant,
            game_id=self.game_id,
            id=self.row_id,
            source_event_id=self.event_id,
            play_number=1,
            batting_order=1,
            event_kind="pitch",
            version=1,
            migration_unverified=False,
        )
        self.ledger = dict.fromkeys(recorded.IdempotencyLedger.__table__.c.keys())
        self.ledger.update(
            tenant_id=self.tenant,
            d5=self.d5,
            kind="accepted",
            source_fingerprint="wire-v1:" + "a" * 64,
            result={"state": "受理", "d3": 1, "temporary_id_mapping": {}},
        )

    def run(self, handle, token):
        """未登録readのpure応答だけを同handleへ供給する。"""
        groups = {
            RecordedEventRowsReadToken: (recorded.RECORDED_EVENT_COLUMNS, self.events),
            RecordedEventSlotsReadToken: (recorded.RECORDED_SLOT_COLUMNS, self.slots),
            RecordedPlayRowsReadToken: (recorded.RECORDED_PLAY_ROW_COLUMNS, self.plays),
            IdempotencyLedgerReadToken: (
                tuple(recorded.IdempotencyLedger.__table__.c.keys()),
                [self.ledger],
            ),
        }
        if type(token) in groups:
            assert handle is self.handle
            self.calls.append(token)
            if type(token) in self.override:
                return self.override[type(token)]
            return self._result(*groups[type(token)])
        return super().run(handle, token)


@pytest.fixture
def recorded_bundle(monkeypatch):
    """scope/Sessionはpure、hostは正式製品artifactを実行する。"""
    bundle = RecordedBundle()
    context = make_tenant_context(bundle.tenant)
    bundle.handle._context = context
    bundle.handle._bound_integrity_proof = context._integrity_proof
    bundle.tx = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        get_transaction=lambda: bundle.tx, in_nested_transaction=lambda: False
    )
    monkeypatch.setitem(
        transaction._TRANSACTION_RUNTIMES, bundle.handle._state_key, (session, object())
    )
    monkeypatch.setattr(
        transaction._TenantTransaction, "run", lambda h, t: bundle.run(h, t)
    )
    return bundle


def test_r2_independent_start_and_real_same_host_full_payload(
    recorded_bundle, monkeypatch
):
    """保存beforeを期待にせず実開始原典/実hostから全値一致する。"""
    calls = []
    original = recorded.NodeDomainHost.call

    def observe(self, operation, value):
        calls.append((id(self), operation))
        return original(self, operation, value)

    monkeypatch.setattr(recorded.NodeDomainHost, "call", observe)
    b = recorded_bundle
    result = recorded._read_recorded_calculation(b.handle, b.game_id)
    assert result.request.model_dump(mode="json", by_alias=True) == CASES[0]["request"]
    assert (
        result.response.model_dump(mode="json", by_alias=True) == CASES[0]["expected"]
    )
    assert result.payload.v7.model_dump(mode="json", by_alias=True) == b.saved_payload
    assert result.generation == 2**40
    assert result.lineups[0].entries[0].uniform_number_snapshot is None
    assert result.lineups[0].entries[1].uniform_number_snapshot == "1"
    assert [name for _, name in calls] == [
        "validateInitialGameRoster",
        "deriveFirstPitchWithContinuation",
    ]
    assert calls[0][0] == calls[1][0]
    assert len(result.unverified_play_row) == 41
    assert not hasattr(result, "read_kind") and not hasattr(result, "physical_verified")


@pytest.mark.parametrize(
    "path,value",
    [
        (
            (
                "calculation",
                "request",
                "t1",
                "before",
                "stateFields",
                "state.count.balls",
            ),
            "1",
        ),
        (
            (
                "calculation",
                "response",
                "value",
                "t1",
                "after",
                "stateFields",
                "state.count.balls",
            ),
            "2",
        ),
        (("calculation", "response", "value", "t1", "statFlags", "打点"), True),
        (("calculation", "response", "value", "t1", "historyContext"), []),
        (
            ("calculation", "response", "value", "t1", "after", "scoreboard", "hits"),
            "1",
        ),
        (("calculation", "response", "value", "t2", "kind"), "not-evaluated"),
        (("calculation", "artifactSha256"), "b" * 64),
        (("participants", "batterId"), "10000000-0000-4000-8000-000000000099"),
    ],
)
def test_r2_saved_value_one_field_change_fails(recorded_bundle, path, value):
    """保存before/after/flags/history/T2を自己承認しない。"""
    b = recorded_bundle
    target = b.saved_payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)


@pytest.mark.parametrize("name", ["events", "slots", "plays"])
@pytest.mark.parametrize("count", [0, 2, 3])
def test_r2_zero_or_extra_history_never_becomes_one(recorded_bundle, name, count):
    """旧/追加行を隠して一球として復元しない。"""
    b = recorded_bundle
    row = getattr(b, name)[0]
    setattr(b, name, [copy.deepcopy(row) for _ in range(count)])
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)


@pytest.mark.parametrize(
    "group,key,bad",
    [
        ("event", "tenant_id", UUID(int=999)),
        ("event", "game_id", UUID(int=999)),
        ("event", "generation", 1),
        ("event", "generation", True),
        ("event", "d1", True),
        ("event", "d1", 2),
        ("event", "d2", None),
        ("event", "d2", True),
        ("event", "d2", -1),
        ("event", "replaced_at", "old"),
        ("event", "retired_at", "old"),
        ("event", "import_batch_id", UUID(int=999)),
        ("event", "legacy_row_identifier", "old"),
        ("event", "migration_unverified", True),
        ("event", "is_tombstone", True),
        ("event", "event_kind", "undo"),
        ("event", "ledger_kind", "rejected"),
        ("slot", "generation", 1),
        ("slot", "confirmed_version", True),
        ("play", "source_event_id", UUID(int=999)),
        ("play", "version", 2),
        ("play", "play_number", True),
        ("play", "hidden_at", "hidden"),
        ("play", "migration_unverified", True),
        ("play", "import_batch_id", UUID(int=999)),
        ("generation", "confirmed_watermark", 0),
        ("generation", "applied_prefix", 2),
        ("generation", "kind", "migration"),
        ("generation", "retired_at", "old"),
        ("ledger", "d5", UUID(int=999)),
        ("ledger", "kind", "rejected"),
        ("ledger", "source_fingerprint", "not-a-hash"),
    ],
)
def test_r2_identity_watermark_lifecycle_is_strict(recorded_bundle, group, key, bad):
    """型と全履歴のidentity/native条件を明示拒否する。"""
    b = recorded_bundle
    row = {
        "event": b.events[0],
        "slot": b.slots[0],
        "play": b.plays[0],
        "generation": b.generation,
        "ledger": b.ledger,
    }[group]
    row[key] = bad
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)


@pytest.mark.parametrize(
    "fault", ["host-source", "expired", "rebound-tx", "host-failure"]
)
def test_r2_host_or_lifetime_change_fails_closed(recorded_bundle, monkeypatch, fault):
    """同host/source/lifetimeが変わった後の既結果を返さない。"""
    original = recorded.NodeDomainHost.call
    b = recorded_bundle

    def damage(self, operation, value):
        if fault == "host-failure":
            raise RuntimeError("synthetic private-value")
        result = original(self, operation, value)
        if operation == "validateInitialGameRoster":
            if fault == "host-source":
                self._source += "\n"
            elif fault == "expired":
                b.handle._state_key = None
            else:
                b.tx = SimpleNamespace(is_active=True)
        return result

    monkeypatch.setattr(recorded.NodeDomainHost, "call", damage)
    with pytest.raises(recorded.RecordedSnapshotUnavailable) as error:
        recorded._read_recorded_calculation(b.handle, b.game_id)
    assert str(error.value) == "保存した初球の計算値を確認できません"
    assert error.value.__cause__ is None


def test_r2_v8_or_started_original_change_is_not_accepted(recorded_bundle):
    """独立した履歴差分の改変も全値比較で拒否する。"""
    b = recorded_bundle
    b.events[0]["state_diff"]["stateFields"]["state.count.balls"]["after"] = "2"
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)


@pytest.mark.parametrize("fault", ["rules", "lineup", "player-team", "missing-player"])
def test_r2_actual_start_sources_are_independent(recorded_bundle, fault):
    """保存された開始rules/名簿をclient計算値で置き換えない。"""
    b = recorded_bundle
    if fault == "rules":
        b.game["applied_rules"]["regulationInnings"] = 7
    elif fault == "lineup":
        entry = next(
            e
            for e in b.lineups[0]["entries_with_uniform_number_snapshot"]
            if e["batting_order"] == 1
        )
        entry["batting_order"] = None
    else:
        identifier = next(iter(b.players))
        if fault == "player-team":
            b.players[identifier]["team_record_id"] = uuid4()
        else:
            del b.players[identifier]
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)


@pytest.mark.parametrize("fault", ["context", "runtime", "closed-tx", "nested"])
def test_r2_scope_cannot_be_reused(recorded_bundle, monkeypatch, fault):
    """真正context/実runtime/top-level寿命を保たないscopeは閉じる。"""
    b = recorded_bundle
    if fault == "context":
        b.handle._context = make_tenant_context(uuid4())
    elif fault == "runtime":
        monkeypatch.delitem(transaction._TRANSACTION_RUNTIMES, b.handle._state_key)
    elif fault == "closed-tx":
        b.tx.is_active = False
    else:
        runtime = transaction._TRANSACTION_RUNTIMES[b.handle._state_key]
        cast(SimpleNamespace, runtime[0]).in_nested_transaction = lambda: True
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)
    assert b.calls == []


def test_r2_locked_generation_must_match_type_and_value(recorded_bundle):
    """bool/int等値でもlock後の行差替えを見逃さない。"""
    b = recorded_bundle
    changed = copy.deepcopy(b.generation)
    changed["confirmed_watermark"] = True
    b.override[recorded.RecordingGenerationLockToken] = b._result(
        tuple(changed), [changed]
    )
    with pytest.raises(recorded.RecordedSnapshotUnavailable):
        recorded._read_recorded_calculation(b.handle, b.game_id)


def test_r2_physical_fields_remain_explicitly_unverified(recorded_bundle):
    """R2-A計算候補を物理41列合格やrecorded DTOへ読み替えない。"""
    b = recorded_bundle
    b.plays[0]["course_x"] = 0.123
    result = recorded._read_recorded_calculation(b.handle, b.game_id)
    assert (
        result.unverified_play_row[RECORDED_PLAY_ROW_COLUMNS.index("course_x")] == 0.123
    )
    assert type(result) is recorded.RecordedCalculationCandidate
    assert not hasattr(result, "read_kind")
