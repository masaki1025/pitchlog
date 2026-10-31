"""P1 の局所分岐と行ロック順を DB なしで検査する。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.sql.dml import Insert
from sqlalchemy.sql.elements import Null
from test_authz_tenant_context import make_tenant_context
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)

from pitchlog.db.sync_protocol.event_kinds import (
    C12_REQUIREMENT_MATRIX,
    EVENT_KIND_LITERALS,
    OPERATION_EVENT_PARTICIPATIONS,
    C12Requirement,
    C12Value,
    OperationEventParticipation,
)
from pitchlog.repositories.base import _operation_spec, _validate_prepared_statement
from pitchlog.repositories.roster import PlayerReadToken
from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import ports, prefix_path
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import ABSENT, SyncEvent
from pitchlog.sync.ports import RecordingRightsPort
from pitchlog.sync.prefix_path import (
    P1ContentRejection,
    P1PreconditionError,
    P1Target,
    _apply_locked,
    _candidate_result,
    _event_insert_token,
    _projection_event,
    _replacement_state,
    _replacement_target,
    _require_rejected_original,
    apply_p1_event,
)
from pitchlog.sync.tokens import (
    RECORDING_GENERATION_READ_COLUMNS,
    EventSlotInsertToken,
    EventSlotReadToken,
    GameLockToken,
    GameReadToken,
    IdempotencyLedgerInsertToken,
    IdempotencyLedgerReadToken,
    InvalidationIntentReadToken,
    OperationEventInsertToken,
    OperationEventReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
    RecordingPrefixUpdateToken,
    SyncInvalidationIntentInsertToken,
    SyncSharedInvalidationIntentInsertToken,
    TemporaryPlayerMappingReadToken,
)

GAME = "123e4567-e89b-12d3-a456-426614174000"
D5 = "123e4567-e89b-12d3-a456-426614174001"
_GENERATION_COLUMNS = RECORDING_GENERATION_READ_COLUMNS
_P1_PARTICIPATIONS = tuple(
    participation
    for participation in OPERATION_EVENT_PARTICIPATIONS
    if participation.event_kind_literal
    in {
        "play_input",
        "undo",
        "substitution",
        "tiebreak_start",
        "game_end_declaration",
        "player_registration",
        "state_correction",
    }
    and participation.event_kind_literal in EVENT_KIND_LITERALS
)


@pytest.mark.parametrize(
    "participation", _P1_PARTICIPATIONS, ids=lambda item: item.canonical_name
)
def test_p1_insert_columns_follow_c12_kind_matrix(
    participation: OperationEventParticipation,
) -> None:
    """実際に発行する token の列と JSONB の SQL NULL を C12 表と照合する。"""
    number = participation.participation_number
    kind = participation.event_kind_literal
    assert kind is not None
    v6_rule = C12_REQUIREMENT_MATRIX[(number, C12Value.V6)].requirement
    v8_rule = C12_REQUIREMENT_MATRIX[(number, C12Value.V8)].requirement
    v10_rule = C12_REQUIREMENT_MATRIX[(number, C12Value.V10)].requirement
    v11_rule = C12_REQUIREMENT_MATRIX[(number, C12Value.V11)].requirement
    v6 = 10 if v6_rule is C12Requirement.REQUIRED else ABSENT
    v8 = {"outs": 1} if v8_rule is C12Requirement.REQUIRED else ABSENT
    target = P1Target(UUID(GAME), 1, 1) if kind == "undo" else None
    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5=kind,
        v6=v6,
        v7={},
        v8=v8,
        v10={"game": GAME, "d4": "epoch", "d1": 1} if target else ABSENT,
    )
    token = _event_insert_token(event, UUID(GAME), 1, "none", "{}", target)
    assert token.generation == token.d1 == 1
    assert token.d2 == (10 if v6_rule is C12Requirement.REQUIRED else None)
    assert (token.state_diff_json is not None) == (v8_rule is C12Requirement.REQUIRED)
    assert not token.is_tombstone
    assert (token.target_generation, token.target_d1) == (
        (1, 1) if v10_rule is C12Requirement.REQUIRED else (None, None)
    )
    assert v11_rule is C12Requirement.FORBIDDEN
    assert token.expected_version is None

    spec = _operation_spec(token)
    statement, parameters = spec.prepare(token)
    _validate_prepared_statement(spec, statement)
    assert isinstance(statement, Insert)
    assert statement._values is not None
    if v8_rule is C12Requirement.REQUIRED:
        assert parameters["state_diff"] == {"outs": 1}
        assert not isinstance(statement._values["state_diff"], Null)
    else:
        assert "state_diff" not in parameters
        assert isinstance(statement._values["state_diff"], Null)


@pytest.mark.parametrize(
    "participation", _P1_PARTICIPATIONS, ids=lambda item: item.canonical_name
)
def test_p1_rejects_c12_v6_v8_mismatch_before_db(
    participation: OperationEventParticipation,
) -> None:
    """種別別の D2・V8 禁止と必須を DB CHECK より先に拒否する。"""
    number = participation.participation_number
    kind = participation.event_kind_literal
    assert kind is not None
    v6_rule = C12_REQUIREMENT_MATRIX[(number, C12Value.V6)].requirement
    v8_rule = C12_REQUIREMENT_MATRIX[(number, C12Value.V8)].requirement
    target = P1Target(UUID(GAME), 1, 1) if kind == "undo" else None

    def make_event(*, v6: object, v8: object) -> SyncEvent:
        """同じ種別の D2・状態差分だけを変異させる。"""
        return SyncEvent(
            D5,
            GAME,
            1,
            "epoch",
            v5=kind,
            v6=v6,
            v7={},
            v8=v8,
            v10={"game": GAME, "d4": "epoch", "d1": 1} if target else ABSENT,
        )

    valid_v6 = 10 if v6_rule is C12Requirement.REQUIRED else ABSENT
    valid_v8 = {} if v8_rule is C12Requirement.REQUIRED else ABSENT
    with pytest.raises(P1PreconditionError, match="V11"):
        _event_insert_token(
            SyncEvent(
                D5,
                GAME,
                1,
                "epoch",
                v5=kind,
                v6=valid_v6,
                v7={},
                v8=valid_v8,
                v10={"game": GAME, "d4": "epoch", "d1": 1} if target else ABSENT,
                v11=7,
            ),
            UUID(GAME),
            1,
            "none",
            "{}",
            target,
        )
    if v6_rule in {C12Requirement.REQUIRED, C12Requirement.FORBIDDEN}:
        invalid_v6 = ABSENT if v6_rule is C12Requirement.REQUIRED else 10
        with pytest.raises(P1PreconditionError, match="D2"):
            _event_insert_token(
                make_event(v6=invalid_v6, v8=valid_v8),
                UUID(GAME),
                1,
                "none",
                "{}",
                target,
            )
    invalid_v8 = ABSENT if v8_rule is C12Requirement.REQUIRED else {}
    with pytest.raises(P1PreconditionError, match="V8"):
        _event_insert_token(
            make_event(v6=valid_v6, v8=invalid_v8),
            UUID(GAME),
            1,
            "none",
            "{}",
            target,
        )


def test_p1_tombstone_insert_columns_follow_c12_matrix() -> None:
    """元が D2・V8 必須の種別でも、墓標行は両列を SQL NULL にする。"""
    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="play_input",
        v7={},
        v10={"game": GAME, "d4": "epoch", "d1": 1},
    )
    token = _event_insert_token(event, UUID(GAME), 1, "tombstone", "{}", None)
    assert token.is_tombstone
    assert token.d2 is token.state_diff_json is token.expected_version is None
    assert token.target_generation is token.target_d1 is None
    for value in (C12Value.V6, C12Value.V8, C12Value.V11):
        assert (
            C12_REQUIREMENT_MATRIX[(8, value)].requirement is C12Requirement.FORBIDDEN
        )


def test_p1_does_not_discard_forbidden_v10() -> None:
    """通常種別の V10 と undo の別対象を黙って保存しない。"""
    unexpected = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="game_end_declaration",
        v6=10,
        v7={},
        v10={"game": GAME, "d4": "epoch", "d1": 1},
    )
    with pytest.raises(P1PreconditionError, match="V10"):
        _event_insert_token(unexpected, UUID(GAME), 1, "none", "{}", None)
    mismatched = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="undo",
        v7={},
        v10={"game": GAME, "d4": "epoch", "d1": 2},
    )
    with pytest.raises(P1PreconditionError, match="V10"):
        _event_insert_token(
            mismatched, UUID(GAME), 1, "none", "{}", P1Target(UUID(GAME), 1, 1)
        )


class _LockObservation:
    """P1 が発行する token の順を記録し、D3=0 と空台帳を返す。"""

    def __init__(self) -> None:
        """空の観測列を作る。"""
        self.tokens: list[type[TenantOperationToken]] = []

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """必要最小限の行を返して B2 まで進める。"""
        self.tokens.append(type(token))
        if type(token) in (GameReadToken, GameLockToken):
            return TenantOperationResult(((UUID(GAME),),))
        if type(token) in {
            RecordingGenerationReadToken,
            RecordingGenerationLockToken,
        }:
            row = tuple(
                1
                if name == "generation"
                else 0
                if name == "confirmed_watermark"
                else None
                for name in _GENERATION_COLUMNS
            )
            return TenantOperationResult((row,))
        if type(token) is IdempotencyLedgerReadToken:
            return TenantOperationResult(())
        raise AssertionError(f"想定しない token: {type(token).__name__}")


class _AcceptedObservation(_LockObservation):
    """P1 の公開局所入口が発行した確定イベント token を記録する。"""

    def __init__(self) -> None:
        """親のロック観測に確定イベントの列を加える。"""
        super().__init__()
        self.events: list[OperationEventInsertToken] = []

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """空スロット・未使用 D5 を返し、書き込み token を捕捉する。"""
        if type(token) in {
            GameLockToken,
            GameReadToken,
            RecordingGenerationReadToken,
            RecordingGenerationLockToken,
            IdempotencyLedgerReadToken,
        }:
            return super().run(token)
        self.tokens.append(type(token))
        if type(token) is OperationEventInsertToken:
            self.events.append(token)
        if type(token) is RecordingPrefixUpdateToken:
            return TenantOperationResult(((1,),))
        assert type(token) in {
            EventSlotReadToken,
            OperationEventReadToken,
            EventSlotInsertToken,
            OperationEventInsertToken,
            RecordingPrefixUpdateToken,
            InvalidationIntentReadToken,
        }
        return TenantOperationResult(())

    def run_in_savepoint(self, token: TenantOperationToken) -> TenantOperationResult:
        """台帳・意図の SAVEPOINT INSERT を同じ偽スコープで受ける。"""
        assert type(token) in {
            IdempotencyLedgerInsertToken,
            SyncInvalidationIntentInsertToken,
            SyncSharedInvalidationIntentInsertToken,
        }
        self.tokens.append(type(token))
        return TenantOperationResult(((1,),))


def _apply_with_observation(
    monkeypatch: pytest.MonkeyPatch, event: SyncEvent
) -> tuple[_AcceptedObservation, PrefixProjection]:
    """DB だけを偽スコープへ替え、P1 の実入口から 1 件進める。"""
    observation = _AcceptedObservation()
    _register_ports(monkeypatch)

    @contextmanager
    def fake_scope(_context: object) -> Iterator[_TenantTransaction]:
        """製品の局所入口に観測用の同一スコープを渡す。"""
        yield cast(_TenantTransaction, observation)

    monkeypatch.setattr(prefix_path, "tenant_transaction_scope", fake_scope)
    projection = PrefixProjection()
    result = apply_p1_event(
        make_tenant_context(UUID(GAME)),
        event,
        PrefixRights(),
        projection,
        PrefixValidator(),
        None,
    )
    assert result.accepted
    return observation, projection


def test_p1_entry_keeps_required_v8_in_insert_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実入口の投影と保存 token の両方が毎球入力の必須 V8 を保持する。"""
    state_diff = {"before": {"outs": 0}, "after": {"outs": 1}}
    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="play_input",
        v6=10,
        v7={},
        v8=state_diff,
    )
    observation, projection = _apply_with_observation(monkeypatch, event)
    assert len(observation.events) == 1
    assert observation.events[0].event_kind == "play_input"
    assert json.loads(observation.events[0].state_diff_json or "null") == state_diff
    assert len(projection.events) == 1
    assert projection.events[0].v8 == state_diff


def test_p1_entry_rejects_unadopted_state_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-040 が未採用の間は DB CHECK より先に状態補正を拒否する。"""
    assert "state_correction" not in EVENT_KIND_LITERALS
    observation = _AcceptedObservation()
    _register_ports(monkeypatch)

    @contextmanager
    def fake_scope(_context: object) -> Iterator[_TenantTransaction]:
        """DB に書く前の種別拒否を観測する。"""
        yield cast(_TenantTransaction, observation)

    monkeypatch.setattr(prefix_path, "tenant_transaction_scope", fake_scope)
    event = SyncEvent(
        D5, GAME, 1, "epoch", v5="state_correction", v7={}, v8={"outs": 1}
    )
    with pytest.raises(P1PreconditionError, match="V5"):
        apply_p1_event(
            make_tenant_context(UUID(GAME)),
            event,
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            None,
        )
    assert not observation.events
    assert EventSlotInsertToken not in observation.tokens


def test_p1_entry_rejects_forbidden_v11_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V11 がある通常種別はスロット・台帳を書き始める前に拒否する。"""
    observation = _AcceptedObservation()
    _register_ports(monkeypatch)

    @contextmanager
    def fake_scope(_context: object) -> Iterator[_TenantTransaction]:
        """拒否までに発行した token を観測する。"""
        yield cast(_TenantTransaction, observation)

    monkeypatch.setattr(prefix_path, "tenant_transaction_scope", fake_scope)
    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="game_end_declaration",
        v6=10,
        v7={},
        v11=7,
    )
    with pytest.raises(P1PreconditionError, match="V11"):
        apply_p1_event(
            make_tenant_context(UUID(GAME)),
            event,
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            None,
        )
    assert not observation.events
    assert IdempotencyLedgerInsertToken not in observation.tokens
    assert EventSlotInsertToken not in observation.tokens


def test_p1_locks_game_before_recording_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-16 の先頭二つの FOR UPDATE が試合行、世代行の順になる。"""
    observation = _LockObservation()
    _register_ports(monkeypatch)
    rights = PrefixRights()
    event = SyncEvent(
        D5, GAME, d1=3, d4="epoch", v5="game_end_declaration", v6=30, v7={}
    )
    result = _apply_locked(
        cast(_TenantTransaction, observation),
        event,
        rights,
        PrefixProjection(),
        PrefixValidator(),
        None,
        None,
        None,
    )
    assert result.boundary == "B2"
    assert rights.calls == [GAME]
    assert observation.tokens[:3] == [
        GameLockToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
    ]
    assert _operation_spec(GameLockToken(UUID(GAME))).for_update
    assert not _operation_spec(RecordingGenerationReadToken(UUID(GAME))).for_update
    assert _operation_spec(RecordingGenerationLockToken(UUID(GAME), 1)).for_update


def _register_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """合成実装だけを登録し、製品の登録表は変えない。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset(
            (cls.__module__, cls.__name__)
            for cls in (
                PrefixRights,
                DenyPrefixRights,
                PrefixProjection,
                PrefixValidator,
            )
        ),
    )


def test_p1_checks_rights_before_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """④ D5 後の未使用イベントは⑤記録権が⑥連番より先。"""
    _register_ports(monkeypatch)
    observation = _LockObservation()
    rights = DenyPrefixRights()
    event = SyncEvent(
        D5, GAME, d1=3, d4="epoch", v5="game_end_declaration", v6=30, v7={}
    )
    with pytest.raises(P1PreconditionError, match="記録権不一致") as error:
        _apply_locked(
            cast(_TenantTransaction, observation),
            event,
            cast(RecordingRightsPort, rights),
            PrefixProjection(),
            PrefixValidator(),
            None,
            None,
            None,
        )
    assert rights.calls == [GAME]
    assert error.value.category == "recording_rights"


def test_p1_gap_stops_before_invalid_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑥で欠番なら、未使用 D5 の不正な V5 を⑦として先に返さない。"""
    _register_ports(monkeypatch)
    observation = _LockObservation()
    event = SyncEvent(D5, GAME, d1=3, d4="epoch", v5="unknown", v7={})
    result = _apply_locked(
        cast(_TenantTransaction, observation),
        event,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        None,
        None,
        None,
    )
    assert result.boundary == "B2"
    assert IdempotencyLedgerInsertToken not in observation.tokens


def test_p1_contiguous_invalid_content_reaches_p5_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⑥を通過した不正 V5 は T9 へ渡せる内容拒否として区別する。"""
    _register_ports(monkeypatch)
    observation = _LockObservation()
    event = SyncEvent(D5, GAME, d1=1, d4="epoch", v5="unknown", v7={})
    with pytest.raises(P1ContentRejection, match="V5"):
        _apply_locked(
            cast(_TenantTransaction, observation),
            event,
            PrefixRights(),
            PrefixProjection(),
            PrefixValidator(),
            None,
            None,
            None,
        )
    assert IdempotencyLedgerInsertToken not in observation.tokens


@pytest.mark.parametrize("path", ["P1", "P2"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("d1", None),
        ("d4", None),
        ("v5", "unknown_kind"),
        ("v6", "invalid"),
        ("v7", []),
        ("v8", []),
        ("v9", {"tombstone": False}),
        ("v10", {"unexpected": 1}),
        ("v11", 7),
    ],
)
def test_reused_d5_is_classified_before_event_content(
    monkeypatch: pytest.MonkeyPatch, path: str, field: str, value: object
) -> None:
    """同じ D5 の異内容は各 V と D1・D4 の検査より先に B3b へ進む。"""
    fields: dict[str, object] = {
        "d1": 1,
        "d4": "epoch",
        "v5": "play_input",
        "v6": 10,
        "v7": {},
        "v8": {},
        "v9": ABSENT,
        "v10": ABSENT,
        "v11": ABSENT,
    }
    fields[field] = value
    event = SyncEvent(
        D5,
        GAME,
        cast(int | None, fields["d1"]),
        cast(str | None, fields["d4"]),
        fields["v5"],
        fields["v6"],
        fields["v7"],
        fields["v8"],
        fields["v9"],
        fields["v10"],
        fields["v11"],
    )
    observation = _LockObservation()
    classified: list[str] = []

    def conflict(
        _scope: _TenantTransaction, _d5: UUID, _fingerprint: str, selected: str
    ) -> D5Candidate:
        """異内容の D5 台帳候補を返す。"""
        classified.append(selected)
        return D5Candidate("conflict", boundary="B3b")

    monkeypatch.setattr(prefix_path, "classify_d5", conflict)
    result = _apply_locked(
        cast(_TenantTransaction, observation),
        event,
        PrefixRights(),
        PrefixProjection(),
        PrefixValidator(),
        None,
        None,
        None,
        path=cast(Literal["P1", "P2"], path),
    )
    assert result.boundary == "B3b"
    assert classified == [path]
    assert observation.tokens == [
        GameLockToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
    ]


@pytest.mark.parametrize(
    "state",
    [
        {"revision": True},
        {"revision": True, "tombstone": True, "rejected_d5": D5},
        {"revision": False, "rejected_d5": D5},
    ],
)
def test_p1_v9_must_identify_one_kind_and_rejected_d5(
    state: dict[str, object],
) -> None:
    """V9 の存在だけで置換種別を決めず、値の矛盾を拒否する。"""
    event = SyncEvent(
        str(uuid4()), GAME, 1, "epoch", v5="game_end_declaration", v9=state
    )
    with pytest.raises(P1PreconditionError, match="V9") as error:
        _replacement_state(event)
    assert error.value.category == "other"


def test_replacement_target_failure_has_w2_category() -> None:
    """公開入口へ渡す W2 区分を V10 欠落で固定する。"""
    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="game_end_declaration",
        v7={},
        v9={"tombstone": True, "rejected_d5": str(uuid4())},
    )
    with pytest.raises(P1PreconditionError, match="V10 の対象参照") as error:
        _replacement_target(event)
    assert error.value.category == "w2_violation"


def test_missing_rejected_original_has_w2_category() -> None:
    """T9 原本がない拒否を、通常の形式エラーと区別する。"""

    class MissingOriginal:
        """自テナントの D5 台帳に拒否原本が存在しない。"""

        def run(self, token: TenantOperationToken) -> TenantOperationResult:
            """最初の台帳読み取りだけを空で返す。"""
            assert type(token) is IdempotencyLedgerReadToken
            return TenantOperationResult(())

    original_d5 = uuid4()
    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="game_end_declaration",
        v7={},
        v9={"tombstone": True, "rejected_d5": str(original_d5)},
        v10={"game": GAME, "d4": "epoch", "d1": 1},
    )
    with pytest.raises(P1PreconditionError, match="対応する内容拒否") as error:
        _require_rejected_original(
            cast(_TenantTransaction, MissingOriginal()), event, original_d5
        )
    assert error.value.category == "w2_violation"


def test_player_reference_never_depends_on_caller_supplied_list() -> None:
    """C2: V5 の参照位置は一覧引数なしで解決を要求する。"""

    class MissingPlayer:
        """正式 ID と一時 ID のどちらにも該当しない。"""

        def run(self, token: TenantOperationToken) -> TenantOperationResult:
            """選手参照の二つの read だけを許す。"""
            assert type(token) in (TemporaryPlayerMappingReadToken, PlayerReadToken)
            return TenantOperationResult(())

    event = SyncEvent(
        D5,
        GAME,
        1,
        "epoch",
        v5="game_end_declaration",
        v7={"player_id": str(uuid4())},
    )
    with pytest.raises(P1PreconditionError, match="確定写像がない"):
        _projection_event(cast(_TenantTransaction, MissingPlayer()), event, {})


def test_d5_stored_result_and_conflict_do_not_start_new_writes() -> None:
    """再掲の写像を返し、異内容なら B3b に切り替える。"""
    stored = D5Candidate(
        "stored_result",
        stored=StoredResult(
            "accepted",
            "fingerprint",
            cast(
                Mapping[str, ImmutableValue],
                {
                    "state": "受理",
                    "d3": 1,
                    "temporary_id_mapping": {"temporary": "official"},
                },
            ),
            None,
        ),
    )
    replay = _candidate_result(stored, 4)
    assert replay is not None
    assert replay.replayed
    assert replay.d3 == 1
    assert replay.temporary_id_mapping == (("temporary", "official"),)
    conflict = _candidate_result(D5Candidate("conflict", boundary="B3b"), 4)
    assert conflict is not None
    assert conflict.boundary == "B3b"
    assert not conflict.accepted
