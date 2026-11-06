"""P3の私有E1入口が実receiptと同writerの順序を保つ対向。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import rg1
from pitchlog.sync import apply, change_path
from pitchlog.sync.control_provider import binding_control, writer_binding
from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    AuthorityBinding,
    D1lessPhaseBinding,
)
from pitchlog.sync.model import AcceptedChangeResult, SyncRequest
from pitchlog.sync.source_binding import _e1_receipt_scope
from pitchlog.sync.wire_source import freeze_wire_source


@contextmanager
def _p3_flow(monkeypatch: pytest.MonkeyPatch, *, device_active: bool = True):
    """外部資産を使わず、実receipt/phaseと同scope順序だけを観測する。"""
    game = UUID(int=2)
    device = UUID(int=5)
    d5 = UUID(int=6)
    change = {
        "d5": str(d5),
        "game_id": str(game),
        "event_kind": "play_change",
        "payload": {"formatVersion": "p3-lineup-pitch-change-v1"},
        "target_reference": {"game": str(game), "d4": 1, "d1": 1},
        "expected_version": 1,
    }
    body = {"recovery_generation": "1", "change": change}
    request = SyncRequest.from_payload("P3", str(game), body)
    source = freeze_wire_source(
        game_id=str(game), d4="1", raw_events=(change,), d1less=True
    )
    context = make_tenant_context(UUID(int=4))
    entry_token = object()
    with _e1_receipt_scope(
        context=context, request=request, source=source, entry_token=entry_token
    ) as receipt:
        phase = D1lessPhaseBinding(
            AttemptBinding(
                AuthorityBinding(UUID(int=1), UUID(int=2), UUID(int=3)),
                context.tenant_id,
                device,
                game,
                "1",
                1,
                UUID(int=7),
                1,
                source.request_fingerprint,
                1,
            ),
            UUID(int=8),
            1,
            d5,
            source.event_fingerprints[0],
        )
        snapshot = json.dumps(
            {
                "tenant_id": str(context.tenant_id),
                "phase": binding_control._phase_wire(phase, UUID(int=10), 1),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        trace: list[str] = []
        scope = SimpleNamespace(_context=context)
        bound = object.__new__(writer_binding._LiveWriterBinding)
        bound._handle = scope
        bound._owner = (object(),)
        bound._used = False
        bound._phase_snapshot = snapshot
        bound._lease = SimpleNamespace(
            _phase_snapshot=snapshot,
            device_id=device,
            game_id=game,
        )

        @contextmanager
        def transaction(_context: object) -> Iterator[object]:
            assert _context is context
            trace.append("tx")
            try:
                yield scope
            except BaseException:
                trace.append("rollback")
                raise
            else:
                trace.append("commit")

        @contextmanager
        def gate(_scope: object, _rights: object) -> Iterator[object]:
            trace.append("rg1-port")
            gated = SimpleNamespace(writer=object())
            gated.mark_written = lambda: trace.append("rg1-commit")
            yield gated

        def locked(_scope: object, _request: object, *args: object, **kwargs: object):
            trace.append("d5-and-change")
            actual_source = kwargs["bound_source"]
            actual_source.begin_write(scope, request.events[0])
            return AcceptedChangeResult(
                {"試合": str(game), "対象の D4": 1, "対象の D1": 1},
                1,
                str(d5),
                change["payload"],
                "2026-11-06T00:00:00+00:00",
            )

        monkeypatch.setattr(apply, "tenant_transaction_scope", transaction)
        monkeypatch.setattr(apply, "gated_e1_writer", gate)
        monkeypatch.setattr(
            apply,
            "_read_reference_device_state",
            lambda *_: trace.append("device") or device_active,
        )
        monkeypatch.setattr(
            apply,
            "game_accessible",
            lambda *_: trace.append("access") or True,
        )
        monkeypatch.setattr(
            rg1, "read_rg1_open", lambda *_: trace.append("rg1-core")
        )
        monkeypatch.setattr(
            binding_control.BindingControl,
            "bind_writer",
            lambda *_args, **_kwargs: trace.append("bind") or bound,
        )
        monkeypatch.setattr(
            writer_binding._LiveWriterBinding,
            "assert_event_source",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            writer_binding,
            "_verify_bound_device",
            lambda *_args, **_kwargs: trace.append("device-bound") or "match",
        )
        monkeypatch.setattr(change_path, "_apply_locked", locked)
        control = object.__new__(binding_control.BindingControl)
        yield (
            receipt,
            context,
            request,
            {
                "entry_token": entry_token,
                "phase": phase,
                "cookie": "synthetic",
                "reference_device": device,
                "control": control,
                "rights": object(),
                "projection": object(),
                "validator": object(),
            },
            trace,
        )


def test_p3_e1_source_is_live_and_commit_marked_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E1受理は資格順とsource書込開始を確認してからだけ⑧へ進む。"""
    with _p3_flow(monkeypatch) as (receipt, context, request, kwargs, trace):
        result = apply._apply_e1_p3(receipt, context, request, **kwargs)
        assert isinstance(result, AcceptedChangeResult)
        assert trace == [
            "device", "access", "tx", "rg1-core", "bind", "rg1-port",
            "device-bound", "d5-and-change", "rg1-commit", "commit",
        ]


def test_p3_e1_inactive_device_precedes_game_and_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """②で失効ならゲーム存在とE1 leaseを一切観測しない。"""
    with _p3_flow(monkeypatch, device_active=False) as (
        receipt, context, request, kwargs, trace,
    ):
        assert apply._apply_e1_p3(receipt, context, request, **kwargs) == "B11"
        assert trace == ["device"]
