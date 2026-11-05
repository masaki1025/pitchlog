"""試合ライフサイクルspikeの純粋な payload/畳み込み検査。"""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult
from pitchlog.sync.game_lifecycle_ports import (
    EVENT_COLUMNS,
    fold_lifecycle,
    payload,
    state_from_row,
)
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tokens import OperationEventReadToken


def state(score: tuple[str, str] = ("1", "0")) -> dict[str, object]:
    """閉じた開始済み状態を返す。"""
    home, away = score
    return {
        "stateFields": {
            "state.half": "top",
            "state.count.strikes": "0",
            "state.count.balls": "0",
            "state.outs": "0",
            "state.runners": "empty",
            "state.battingOrder": "1",
            "state.tiebreakActive": False,
            "state.gameEnded": False,
            "state.inning": "1",
            "state.score": {"home": home, "away": away},
        },
        "scoreboard": {
            "inningScores": {"home": home, "away": away},
            "hits": "1",
            "errors": "0",
            "strikeouts": "0",
            "walks": "0",
        },
        "battingOrderBySide": {"away": "2", "home": "1"},
    }


def event(v7: object) -> SyncEvent:
    """D1 付き game_end_declaration の外形を作る。"""
    return SyncEvent(
        str(uuid4()),
        str(uuid4()),
        d1=1,
        d4="d4",
        v5="game_end_declaration",
        v6=1,
        v7=v7,
    )


def end_payload(
    version: int = 1,
    previous: object = None,
    value: object | None = None,
) -> dict[str, object]:
    """終了 payload を返す。"""
    return {
        "formatVersion": "game-lifecycle-spike-v1",
        "action": "end",
        "finalization": {
            "version": version,
            "previous": previous,
            "state": state() if value is None else value,
        },
    }


def reopen_payload(
    version: int = 1,
    target: object = None,
    value: object | None = None,
) -> dict[str, object]:
    """再開 payload を返す。"""
    return {
        "formatVersion": "game-lifecycle-spike-v1",
        "action": "reopen",
        "finalization": {
            "version": version,
            "target": {"version": 1, "d1": 2} if target is None else target,
            "state": state() if value is None else value,
        },
    }


def test_end_and_reopen_payloads_are_closed_and_chained() -> None:
    """初回終了・再終了・再開の版連鎖を受理する。"""
    first = payload(event(end_payload()))
    assert first is not None
    assert first.action == "end" and first.version == 1
    assert first.previous is None and first.target is None

    second = payload(
        event(
            end_payload(
                version=2,
                previous={"version": 1, "d1": 2},
            )
        )
    )
    assert second is not None
    assert second.version == 2
    assert second.previous == {"version": 1, "d1": 2}

    reopened = payload(event(reopen_payload()))
    assert reopened is not None
    assert reopened.action == "reopen"
    assert reopened.target == {"version": 1, "d1": 2}


@pytest.mark.parametrize(
    "value",
    [
        {**end_payload(), "unknown": True},
        {**end_payload(), "formatVersion": "other"},
        end_payload(version=2),
        end_payload(version=1, previous={"version": 1, "d1": 2}),
        end_payload(value={**state(), "unknown": True}),
        reopen_payload(version=2),
        reopen_payload(target={"version": 1}),
    ],
)
def test_invalid_payloads_are_rejected(value: object) -> None:
    """未知キー・版不一致・壊れた状態を拒否する。"""
    assert payload(event(value)) is None


def test_state_from_saved_play_and_lifecycle() -> None:
    """保存済み play と lifecycle の状態を payload から読む。"""
    play = {
        "event_kind": "play_input",
        "payload": {
            "formatVersion": "play-prefix-play-v3",
            "calculation": {
                "response": {
                    "value": {
                        "t1": {"after": state()},
                    }
                }
            },
        },
    }
    assert state_from_row(play) == state()
    lifecycle = {
        "event_kind": "game_end_declaration",
        "d1": 2,
        "d5": uuid4(),
        "payload": end_payload(),
    }
    assert state_from_row(lifecycle) == state()
    assert state_from_row({"event_kind": "substitution"}) is None


class _FakeRunner:
    """D1 ごとの event row を返す同一 TX の代用。"""

    def __init__(self, rows: dict[int, dict[str, object]]) -> None:
        self.rows = rows

    def run(self, operation: object) -> TenantOperationResult:
        assert type(operation) is OperationEventReadToken
        values = {
            "id": uuid4(),
            "game_id": uuid4(),
            "generation": 1,
            "d1": operation.d1,
            "d2": None,
            "d5": uuid4(),
            "ledger_kind": "accepted",
            "event_kind": "substitution",
            "payload": {},
            "state_diff": None,
            "is_tombstone": False,
            "replaced_at": None,
            "target_generation": None,
            "target_d1": None,
            "expected_version": None,
            "change_order": None,
            "legacy_row_identifier": None,
            "migration_unverified": False,
            "tenant_id": uuid4(),
            "import_batch_id": None,
            "retired_at": None,
        }
        values.update(self.rows.get(operation.d1, {}))
        values["d1"] = operation.d1
        row = cast(
            tuple[ImmutableValue, ...],
            tuple(values[name] for name in EVENT_COLUMNS),
        )
        return TenantOperationResult((row,))


def test_fold_marks_reopen_invalidation_and_reend_version() -> None:
    """再開が旧版を失効させ、再終了が新しい版になることを畳み込む。"""
    rows: dict[int, dict[str, object]] = {
        1: {
            "d2": 1,
            "d5": uuid4(),
            "event_kind": "play_input",
            "payload": {
                "formatVersion": "play-prefix-play-v3",
                "calculation": {
                    "response": {"value": {"t1": {"after": state()}}}
                },
            },
        },
        2: {
            "d2": 1001,
            "d5": uuid4(),
            "event_kind": "game_end_declaration",
            "payload": end_payload(),
        },
        3: {
            "d2": 2001,
            "d5": uuid4(),
            "event_kind": "game_end_declaration",
            "payload": reopen_payload(),
        },
        4: {
            "d2": 3001,
            "d5": uuid4(),
            "event_kind": "game_end_declaration",
            "payload": end_payload(version=2, previous={"version": 1, "d1": 2}),
        },
    }
    status, current, finalizations, next_d2, truncated = fold_lifecycle(
        _FakeRunner(rows), UUID(int=1), 1, 4
    )
    assert status == "finished"
    assert current == state()
    assert next_d2 == 4001
    assert truncated is False
    assert [item["version"] for item in finalizations] == [1, 2]
    invalidated = finalizations[0]["invalidatedBy"]
    assert isinstance(invalidated, dict)
    assert invalidated["d1"] == 3
    assert finalizations[1]["invalidatedBy"] is None


def test_fold_rejects_reopen_without_end() -> None:
    """終了していない再開を畳み込みで拒否する。"""
    rows: dict[int, dict[str, object]] = {
        1: {
            "d2": 1,
            "d5": uuid4(),
            "event_kind": "game_end_declaration",
            "payload": reopen_payload(),
        }
    }
    with pytest.raises(RuntimeError):
        fold_lifecycle(_FakeRunner(rows), UUID(int=1), 1, 1)
