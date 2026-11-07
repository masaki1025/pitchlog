"""E1受付参照の同一HTTP要求束縛と寿命失効を固定する。"""

from typing import Any, cast
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
    events = payload["events"]
    assert isinstance(events, list)
    event = events[0]
    assert isinstance(event, dict)
    raw = dict(event)
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


@pytest.mark.parametrize("changed", ["d4.2.changed", None, {"key": "different"}])
def test_recovery_body_covers_v12_without_changing_event_identity(changed):
    """V12変更を独立束縛し、業務D5/既要求指紋の算式は維持する。"""
    from pitchlog.sync.source_binding import receipt_body_fingerprint

    game, d5 = str(uuid4()), str(uuid4())
    payload = _payload(game, d5)
    source = _source(payload, game)
    token = object()
    request = SyncRequest.from_payload("P2", game, payload)
    with _scope(request=request, source=source, entry_token=token) as receipt:
        original = receipt_body_fingerprint(receipt, token)
        assert original == receipt_body_fingerprint(receipt, token)
    with pytest.raises(ValueError):
        receipt_body_fingerprint(receipt, token)
    payload["recording_right_proof"] = changed
    changed_request = SyncRequest.from_payload("P2", game, payload)
    changed_source = _source(payload, game)
    assert source.request_fingerprint == changed_source.request_fingerprint
    assert source.event_fingerprints == changed_source.event_fingerprints
    with _scope(
        request=changed_request, source=changed_source, entry_token=token
    ) as changed_receipt:
        assert receipt_body_fingerprint(changed_receipt, token) != original


def test_recovery_body_cannot_be_read_with_another_entry_token(issued):
    """自由なdigest発行口へせず、真正受付と同HTTP tokenを必須にする。"""
    from pitchlog.sync.source_binding import receipt_body_fingerprint

    receipt, _token = issued
    with pytest.raises(ValueError):
        receipt_body_fingerprint(receipt, object())


@pytest.mark.parametrize(
    "result", ["matching", "absent", "unresolved", "unknown", None]
)
def test_control_body_state_is_closed_and_keeps_all_identity(result, monkeypatch):
    """専用固定関数への全識別供給と閉じた結果だけを検査する。"""
    from pitchlog.sync.control_provider.binding_control import (
        WriterBindingUnavailable,
        _BindingAuthority,
    )
    from pitchlog.sync.stop_contract import AttemptIdentity

    issuer, tenant, device, game, attempt, d5 = (uuid4() for _ in range(6))
    authority = object.__new__(_BindingAuthority)
    authority._issuer = issuer
    identity = AttemptIdentity(str(attempt), str(game), "D4", 1, "request-original")
    calls = []

    def call(*args):
        calls.append(args)
        return () if result is None else (result,)

    monkeypatch.setattr(authority, "_call", call)
    if result in ("matching", "absent", "unresolved"):
        assert (
            authority.read_attempt_body_state(
                tenant, device, identity, d5, "event-original", "a" * 64
            )
            == result
        )
    else:
        with pytest.raises(WriterBindingUnavailable):
            authority.read_attempt_body_state(
                tenant, device, identity, d5, "event-original", "a" * 64
            )
    assert calls == [
        (
            "control",
            "SELECT sync_control.read_attempt_recovery_state("
            "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                tenant,
                attempt,
                device,
                game,
                "D4",
                1,
                "request-original",
                issuer,
                d5,
                "event-original",
                "a" * 64,
            ),
        )
    ]


@pytest.mark.parametrize("field", ["proof", "recovery", "target", "version", "payload"])
def test_p3_recovery_digest_covers_original_change_without_d1(field):
    """P3元change/対象/復旧世代/V12を真正受付から一体で束縛する。"""
    import copy

    from pitchlog.sync.source_binding import receipt_body_fingerprint

    game, d5 = str(uuid4()), str(uuid4())
    payload: dict[str, Any] = {
        "recording_right_proof": "original-proof",
        "recovery_generation": "1",
        "change": {
            "d5": d5,
            "game_id": game,
            "event_kind": "play_change",
            "target_reference": {"game": game, "d4": "original-D4", "d1": 1},
            "expected_version": 1,
            "payload": {},
        },
    }

    def digest(body):
        request = SyncRequest.from_payload("P3", game, body)
        source = freeze_wire_source(
            game_id=game, d4="original-D4", raw_events=(body["change"],), d1less=True
        )
        token = object()
        with _scope(request=request, source=source, entry_token=token) as receipt:
            return receipt_body_fingerprint(receipt, token), source

    original, source = digest(payload)
    changed = copy.deepcopy(payload)
    if field == "proof":
        changed["recording_right_proof"] = "different-proof"
    elif field == "recovery":
        changed["recovery_generation"] = "2"
    elif field == "target":
        changed["change"]["target_reference"]["d1"] = 2
    elif field == "version":
        changed["change"]["expected_version"] = 2
    else:
        changed["change"]["payload"] = {"replacement": "different"}
    actual, changed_source = digest(changed)
    assert actual != original
    if field in ("proof", "recovery"):
        assert changed_source.request_fingerprint == source.request_fingerprint
        assert changed_source.event_fingerprints == source.event_fingerprints


def test_p3_body_state_uses_only_dedicated_closed_reader(monkeypatch):
    """P3専用readを使い、旧D1付きreaderをnullable条件へ広げない。"""
    from pitchlog.sync.control_provider.binding_control import (
        WriterBindingUnavailable,
        _BindingAuthority,
    )
    from pitchlog.sync.stop_contract import AttemptIdentity

    issuer, tenant, device, game, attempt, d5 = (uuid4() for _ in range(6))
    authority = object.__new__(_BindingAuthority)
    authority._issuer = issuer
    identity = AttemptIdentity(str(attempt), str(game), "D4", 1, "request-original")
    calls = []

    def call(*args):
        calls.append(args)
        return ("matching",)

    monkeypatch.setattr(authority, "_call", call)
    assert (
        authority.read_attempt_body_state(
            tenant,
            device,
            identity,
            d5,
            "event-original",
            "a" * 64,
            phase_kind="d1less",
        )
        == "matching"
    )
    assert calls[0][1] == (
        "SELECT sync_control.read_p3_attempt_recovery_state("
        "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    assert calls[0][2][-1] == "a" * 64
    with pytest.raises(WriterBindingUnavailable):
        authority.read_attempt_body_state(
            tenant,
            device,
            identity,
            d5,
            "event-original",
            "a" * 64,
            phase_kind=cast(Any, "unknown"),
        )
    assert len(calls) == 1
