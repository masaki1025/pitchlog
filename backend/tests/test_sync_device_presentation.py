"""同一HTTP受付に結ぶ実端末提示の発行・失効・重複拒否を固定する。

実認証・実DB・実brokerの成立をここで主張しない。受付と提示の閉包だけを見る。
"""

from typing import Any, cast
from uuid import uuid4

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.sync.control_provider.writer_binding import (
    _DEVICE_PRESENTATIONS,
    WriterBindingUnavailable,
    _DevicePresentationState,
    _drop_device_presentations,
    _issue_device_presentation,
)
from pitchlog.sync.model import SyncRequest
from pitchlog.sync.source_binding import _RECEIPTS, _e1_receipt_scope
from pitchlog.sync.wire_source import freeze_wire_source

_DIGEST = bytes(range(32))


def _issued():
    """S-1外形に合う同一要求の受付とtokenを作る。"""
    game, d5 = str(uuid4()), str(uuid4())
    payload = {
        "recording_right_proof": "d4.1.example",
        "events": [
            {
                "d5": d5,
                "d1": 1,
                "d4": "d4.1.example",
                "game_id": game,
                "event_kind": "play_input",
                "d2": 1,
                "payload": {},
                "state_diff": {},
            }
        ],
    }
    request = SyncRequest.from_payload("P2", game, payload)
    source = freeze_wire_source(
        game_id=game,
        d4="d4.1.example",
        raw_events=(dict(payload["events"][0]),),  # type: ignore[index]
    )
    return make_tenant_context(uuid4()), request, source, object(), uuid4()


@pytest.fixture()
def scope():
    """寿命中の受付・token・要求端末を返す。"""
    context, request, source, token, device = _issued()
    with _e1_receipt_scope(
        context=context, request=request, source=source, entry_token=token
    ) as receipt:
        yield receipt, token, device


def test_issued_presentation_is_closed_to_the_same_receipt(scope) -> None:
    """同じ受付・tokenの資格だけが提示へ写り、受付と請求が一致する。"""
    receipt, token, device = scope
    presentation = _issue_device_presentation(
        receipt, token, reference_device=device, credential_digest=_DIGEST
    )
    state = _DEVICE_PRESENTATIONS[presentation]
    assert type(state) is _DevicePresentationState
    assert state.receipt is receipt
    assert state.reference_device == device
    assert state.credential_digest == _DIGEST
    assert _RECEIPTS[receipt].device_presentation is presentation


def test_other_request_token_cannot_issue(scope) -> None:
    """別HTTP要求のtokenでは提示を発行できない。"""
    receipt, _token, device = scope
    with pytest.raises(WriterBindingUnavailable):
        _issue_device_presentation(
            receipt, object(), reference_device=device, credential_digest=_DIGEST
        )
    assert _RECEIPTS[receipt].device_presentation is None


def test_second_issue_on_the_same_receipt_is_rejected(scope) -> None:
    """同一受付への二重発行を拒否し、最初の提示を差し替えない。"""
    receipt, token, device = scope
    first = _issue_device_presentation(
        receipt, token, reference_device=device, credential_digest=_DIGEST
    )
    with pytest.raises(WriterBindingUnavailable):
        _issue_device_presentation(
            receipt, token, reference_device=device, credential_digest=_DIGEST
        )
    assert _RECEIPTS[receipt].device_presentation is first
    assert list(_DEVICE_PRESENTATIONS) == [first]


@pytest.mark.parametrize(
    ("device", "digest"),
    [
        ("not-a-uuid", _DIGEST),
        (uuid4(), _DIGEST[:31]),
        (uuid4(), "x" * 64),
        (uuid4(), _DIGEST.hex()),
    ],
)
def test_malformed_input_is_rejected(scope, device: object, digest: object) -> None:
    """端末IDとdigestの外形不正を発行前に拒否する。"""
    receipt, token, _device = scope
    with pytest.raises(WriterBindingUnavailable):
        _issue_device_presentation(
            receipt, token, reference_device=device, credential_digest=digest
        )
    assert _RECEIPTS[receipt].device_presentation is None


def test_presentation_expires_with_the_receipt() -> None:
    """受付の寿命終了後は同じtokenでも発行できず、提示も残らない。"""
    context, request, source, token, device = _issued()
    with _e1_receipt_scope(
        context=context, request=request, source=source, entry_token=token
    ) as receipt:
        presentation = _issue_device_presentation(
            receipt, token, reference_device=device, credential_digest=_DIGEST
        )
        assert presentation in _DEVICE_PRESENTATIONS
    assert presentation not in _DEVICE_PRESENTATIONS
    with pytest.raises(WriterBindingUnavailable):
        _issue_device_presentation(
            receipt, token, reference_device=device, credential_digest=_DIGEST
        )


def test_drop_only_removes_presentations_of_the_same_receipt(scope) -> None:
    """片付けは対象受付の提示だけを破棄し、別受付の提示を残す。"""
    receipt, token, device = scope
    presentation = _issue_device_presentation(
        receipt, token, reference_device=device, credential_digest=_DIGEST
    )
    other = cast(Any, object())
    other_presentation = object.__new__(next(iter(_DEVICE_PRESENTATIONS)).__class__)
    _DEVICE_PRESENTATIONS[other_presentation] = _DevicePresentationState(
        other, None, None, device, _DIGEST
    )
    try:
        _drop_device_presentations(receipt)
        assert presentation not in _DEVICE_PRESENTATIONS
        assert other_presentation in _DEVICE_PRESENTATIONS
    finally:
        _DEVICE_PRESENTATIONS.pop(other_presentation, None)
