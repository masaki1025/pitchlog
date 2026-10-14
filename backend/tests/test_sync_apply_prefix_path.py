"""P1 の局所分岐と行ロック順を DB なしで検査する。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID, uuid4

import pytest
from test_sync_apply_port_prefix import (
    DenyPrefixRights,
    PrefixProjection,
    PrefixRights,
    PrefixValidator,
)

from pitchlog.db.recording_rights.models import RecordingGeneration
from pitchlog.repositories.base import _operation_spec
from pitchlog.repositories.roster import PlayerReadToken
from pitchlog.repositories.tokens import (
    ImmutableValue,
    TenantOperationResult,
    TenantOperationToken,
)
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import ports
from pitchlog.sync.idempotency import D5Candidate, StoredResult
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ports import RecordingRightsPort
from pitchlog.sync.prefix_path import (
    P1PreconditionError,
    _apply_locked,
    _candidate_result,
    _projection_event,
    _replacement_state,
    _replacement_target,
    _require_rejected_original,
)
from pitchlog.sync.tokens import (
    GameLockToken,
    IdempotencyLedgerReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
    TemporaryPlayerMappingReadToken,
)

GAME = "123e4567-e89b-12d3-a456-426614174000"
D5 = "123e4567-e89b-12d3-a456-426614174001"
_GENERATION_COLUMNS = tuple(RecordingGeneration.__table__.c.keys())


class _LockObservation:
    """P1 が発行する token の順を記録し、D3=0 と空台帳を返す。"""

    def __init__(self) -> None:
        """空の観測列を作る。"""
        self.tokens: list[type[TenantOperationToken]] = []

    def run(self, token: TenantOperationToken) -> TenantOperationResult:
        """必要最小限の行を返して B2 まで進める。"""
        self.tokens.append(type(token))
        if type(token) is GameLockToken:
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


def test_p1_locks_game_before_recording_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-16 の先頭二つの FOR UPDATE が試合行、世代行の順になる。"""
    observation = _LockObservation()
    _register_ports(monkeypatch)
    rights = PrefixRights()
    event = SyncEvent(D5, GAME, d1=3, d4="epoch", v5="game_end_declaration", v7={})
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
    event = SyncEvent(D5, GAME, d1=3, d4="epoch", v5="game_end_declaration", v7={})
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
