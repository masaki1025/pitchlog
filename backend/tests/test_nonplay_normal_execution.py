"""NP通常球の実host一回と実参照issuerの型/寿命対向。E1/PG試験ではない。"""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_nonplay_normal_payload import fixture_values

from pitchlog.domainrt.host import open_domain_host
from pitchlog.repositories import nonplay_prefix_read as reader
from pitchlog.sync import ordinary_pitch_execution as api
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload


def test_existing_host_once_and_payload_fullcomparison(monkeypatch):
    """資格readだけを明示doubleにし、数学応答成功stubを置かない。"""
    v7, v8 = fixture_values()
    supplied = LineupPitchPlayPayload.model_validate_json(json.dumps(v7))
    sentinel = object()
    calls = []
    monkeypatch.setattr(
        reader, "read_confirmed_nonplay_normal", lambda *a, **k: sentinel
    )
    monkeypatch.setattr(api, "_live", lambda state: None)
    source = SimpleNamespace(
        bound=SimpleNamespace(
            _lease=SimpleNamespace(nonce=b"x" * 32), _phase_snapshot="pure"
        ),
        phase=object(),
    )
    state = SimpleNamespace(handle=object(), event=object(), source=source)
    with open_domain_host() as host:
        original = host.call

        def call(operation, raw):
            calls.append(operation)
            return original(operation, raw)

        monkeypatch.setattr(host, "call", call)

        @contextmanager
        def factory():
            yield host

        monkeypatch.setattr(api, "open_domain_host", factory)
        api._evaluate_nonplay_normal_bound(
            state, supplied, json.dumps(v7), json.dumps(v8)
        )
    assert calls == ["deriveLineupPlayPrefixWithContinuation"]
    assert state.phase == "ready" and state.prefix is sentinel
    assert (
        state.payload.model_dump(mode="json", by_alias=True, exclude_unset=True) == v7
    )
    assert type(state.frame) is api.OrdinaryPitchFrame
    assert type(state.frame_id) is UUID
    assert state.stats_source_reference[0] is state.frame


def test_free_constructor_and_unregistered_prefix_refused():
    """自由dataclass/cloneをframe用の実原本資格へ変えない。"""
    with pytest.raises(reader.NonplaySourceUnavailable):
        reader.ConfirmedNonplayNormalPrefix()
    handle = SimpleNamespace(_state_key=object())
    with pytest.raises(reader.NonplaySourceUnavailable):
        reader._assert_nonplay_normal_prefix(
            SimpleNamespace(handle=handle, prefix=object())
        )


@pytest.mark.parametrize("kind", ["old", "nonplay"])
def test_position_selector_uses_true_profile(kind):
    """NPのtop-level実位置を旧Source.positionへ偽装しない。"""
    v7, _ = fixture_values()
    request = LineupPitchPlayPayload.model_validate_json(
        json.dumps(v7)
    ).calculation.request
    if kind == "nonplay":
        from pitchlog.domainrt.lineup_play_prefix_continuation import (
            NonplayLineupPrefixRequest,
        )

        assert type(request) is NonplayLineupPrefixRequest
        assert api._lineup_position(request) is request.source_position
    else:
        position = object()
        old = SimpleNamespace(source=SimpleNamespace(position=position))
        assert api._lineup_position(old) is position
