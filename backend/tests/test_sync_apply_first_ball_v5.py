"""初球V5の有限対応と、原値/D5指紋を保持する境界を検査する。"""

from __future__ import annotations

from types import MappingProxyType
from uuid import UUID

import pytest
from test_sync_apply_idempotency import _saved_result

from pitchlog.db.sync_protocol.event_kinds import (
    OPERATION_EVENT_PARTICIPATIONS,
    PLAY_INPUT_EVENT_KIND,
    ParticipationBinding,
)
from pitchlog.sync.first_ball_v5 import FirstBallV5Error, first_ball_database_kind
from pitchlog.sync.idempotency import (
    classify_result,
    event_source,
    event_source_fingerprint,
    operation_fingerprint,
)
from pitchlog.sync.model import SyncEvent, SyncRequest


class _StringSubclass(str):
    """値だけ同じ派生型をexact strへ黙って変えない対向。"""


class _UntrustedObject:
    """非文字列の比較やreprを呼ばないことを確認する。"""

    def __eq__(self, other: object) -> bool:
        """比較に達した場合は型拒否を迂回したことを表す。"""
        raise AssertionError("入力の比較を呼んではならない")

    def __repr__(self) -> str:
        """入力のreprに達した場合は固定エラー違反を表す。"""
        raise AssertionError("入力のreprを呼んではならない")


def _event(v5: object = "1", *, balls: str = "1") -> SyncEvent:
    """DB不要の原イベントを作り、保存成功や認可を模擬しない。"""
    return SyncEvent(
        d5="00000000-0000-4000-8000-000000000001",
        game_id="00000000-0000-4000-8000-000000000002",
        d1=1,
        d4="issued-opaque-d4",
        v5=v5,
        v6=0,
        v7={"resultId": "batting-result.ball"},
        v8={"stateFields": {"state.count.balls": {"before": "0", "after": balls}}},
    )


def test_stable_id_one_uses_the_existing_primary_correspondence() -> None:
    """一次表の番号/正本名/V5/DBliteralを全て固定して再利用する。"""
    rows = [
        row for row in OPERATION_EVENT_PARTICIPATIONS if row.participation_number == 1
    ]
    assert len(rows) == 1
    row = rows[0]
    assert (
        row.participation_number,
        row.canonical_name,
        row.binding,
        row.event_kind_literal,
    ) == (1, "毎球入力", ParticipationBinding.EVENT_KIND, "play_input")
    assert PLAY_INPUT_EVENT_KIND == row.event_kind_literal
    assert first_ball_database_kind("1") == row.event_kind_literal


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        1,
        0,
        1.0,
        b"1",
        bytearray(b"1"),
        ["1"],
        {"value": "1"},
        "",
        "0",
        "2",
        "3",
        "9",
        "10",
        "01",
        "+1",
        "-1",
        "1.0",
        " 1",
        "1 ",
        "1\n",
        "1\x00",
        "１",
        "١",
        "play_input",
        "毎球入力",
        "CANARY_UNTRUSTED_INPUT",
        _StringSubclass("1"),
    ],
)
def test_unadvertised_values_are_rejected_without_echo(value: object) -> None:
    """型変換・文字正規化・DBliteral別名受理・値の例外露出を行わない。"""
    with pytest.raises(FirstBallV5Error) as error:
        first_ball_database_kind(value)
    assert error.value.args == ("初球V5は安定ID1だけに対応しています",)


def test_untrusted_object_comparison_and_repr_are_never_called() -> None:
    """非文字列は比較やreprより先に固定拒否する。"""
    with pytest.raises(FirstBallV5Error) as error:
        first_ball_database_kind(_UntrustedObject())
    assert str(error.value) == "初球V5は安定ID1だけに対応しています"


def test_resolution_keeps_the_original_event_request_and_all_fingerprints() -> None:
    """原wire1の全event値とP2のD5指紋を一切書き換えない。"""
    event = _event()
    request = SyncRequest("P2", event.game_id, (event,), d4=event.d4, v12="opaque")
    source_before = event_source(event)
    event_fingerprint_before = event_source_fingerprint(event)
    d5_fingerprint_before = operation_fingerprint(event, "P2", None)
    assert first_ball_database_kind(event.v5) == "play_input"
    assert request.events == (event,)
    assert request.events[0] is event
    assert event.v5 == "1"
    assert event_source(event) == source_before
    assert event_source_fingerprint(event) == event_fingerprint_before
    assert operation_fingerprint(event, "P2", None) == d5_fingerprint_before
    assert isinstance(event.v7, MappingProxyType)
    assert isinstance(event.v8, MappingProxyType)
    assert UUID(event.d5).version == 4


def test_replay_and_different_content_keep_the_existing_classifier() -> None:
    """既分類器で同内容再掲と異内容B3bを保持する。保存成功試験ではない。"""
    event = _event()
    fingerprint = operation_fingerprint(event, "P2", None)
    saved = _saved_result(fingerprint)
    first_ball_database_kind(event.v5)
    replay = classify_result(saved, operation_fingerprint(event, "P2", None), "P2")
    assert replay.kind == "stored_result"
    assert replay.boundary is None
    changed = _event(balls="2")
    first_ball_database_kind(changed.v5)
    conflict = classify_result(saved, operation_fingerprint(changed, "P2", None), "P2")
    assert conflict.kind == "conflict"
    assert conflict.boundary == "B3b"


def test_early_v5_replacement_would_change_both_existing_fingerprints() -> None:
    """原値をDBliteralで上書きする案が既D5内容同一性を変えると実証する。"""
    raw, overwritten = _event(), _event("play_input")
    assert event_source_fingerprint(raw) != event_source_fingerprint(overwritten)
    assert operation_fingerprint(raw, "P2", None) != operation_fingerprint(
        overwritten, "P2", None
    )
