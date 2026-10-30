"""E1受付参照の同一HTTP要求束縛と寿命失効を固定する。"""

from uuid import uuid4

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.sync.model import SyncRequest
from pitchlog.sync.source_binding import (
    SourceBindingError,
    _e1_receipt_scope,
    _receipt_for_entry,
)
from pitchlog.sync.wire_source import freeze_wire_source


def _context():
    """許可済みの試験専用発行経路だけを使う。実認証の代替ではない。"""
    return make_tenant_context(uuid4())


def _payload(game: str, d5: str) -> dict[str, object]:
    """S-1 の外形に合う要求本文を作る。"""
    return {
        "recording_right_proof": "d4.1.example",
        "events": [
            {
                "d5": d5,
                "d1": 1,
                "d4": "d4.1.example",
                "game_id": game,
                "event_kind": "first-ball-play-v1",
                "d2": 1,
                "payload": {},
                "state_diff": {},
            }
        ],
    }


def _source(payload: dict[str, object], game: str):
    """同じ原wire列から不変の索引付き値を作る。"""
    raw = dict(payload["events"][0])  # type: ignore[index]
    return freeze_wire_source(game_id=game, d4=str(raw["d4"]), raw_events=(raw,))


def _issued():
    """同一要求のtokenで発行した受付とtokenを返す。"""
    game, d5 = str(uuid4()), str(uuid4())
    payload = _payload(game, d5)
    request = SyncRequest.from_payload("P2", game, payload)
    token = object()
    return (
        make_tenant_context(uuid4()),
        request,
        _source(payload, game),
        token,
    )


@pytest.fixture()
def issued():
    """寿命中の受付と、発行時に渡したtokenを返す。"""
    context, request, source, token = _issued()
    with _e1_receipt_scope(
        context=context,
        request=request,
        source=source,
        entry_token=token,
    ) as receipt:
        yield receipt, token


def _scope(**overrides):
    context, request, source, token = _issued()
    values = {
        "context": context,
        "request": request,
        "source": source,
        "entry_token": token,
    }
    values.update(overrides)
    return _e1_receipt_scope(**values)


def test_same_request_token_is_accepted(issued) -> None:
    """発行した同一要求のtokenだけが受付へ到達する。"""
    receipt, token = issued
    assert _receipt_for_entry(receipt, token) is not None


def _current_token(receipt):
    """受付へ登録されたtokenを検査から取得する。"""
    from pitchlog.sync.source_binding import _RECEIPTS

    return _RECEIPTS[receipt].entry_token


def test_other_request_token_is_rejected(issued) -> None:
    """別HTTP要求のtokenでは受付を再利用できない。"""
    receipt, _token = issued
    with pytest.raises(ValueError):
        _receipt_for_entry(receipt, object())
    with pytest.raises(ValueError):
        _receipt_for_entry(receipt, None)


def test_receipt_cannot_be_used_after_lifetime() -> None:
    """寿命終了後の受付は同じtokenでも拒否される。"""
    with _scope() as receipt:
        token = _current_token(receipt)
    with pytest.raises(ValueError):
        _receipt_for_entry(receipt, token)


def test_missing_entry_token_is_rejected_at_issue() -> None:
    """token無しの発行を閉拒否する。"""
    with pytest.raises(SourceBindingError):
        with _scope(entry_token=None):
            pass
