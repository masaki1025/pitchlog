"""訂正前current原本の有限読取が未確認scopeを拒否する。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from pitchlog.repositories import past_correction_source as source
from pitchlog.repositories.ordinary_prefix_read import OrdinaryPrefixView
from pitchlog.repositories.started_read import StartedGameView
from pitchlog.repositories.transaction import _TenantTransaction

_GAME = UUID("10000000-0000-0000-0000-000000000002")


def test_untrusted_scope_or_out_of_range_target_cannot_read_as_current_source(
    monkeypatch,
) -> None:
    """未認可scope・範囲外対象を既定値で先頭扱いにしない。"""

    class _Scope:
        pass

    monkeypatch.setattr(source, "_TenantTransaction", _Scope)
    with pytest.raises(source.PastCorrectionSourceUnavailable):
        source.read_past_correction_v3_source(
            cast(_TenantTransaction, object()), _GAME, 1
        )
    with pytest.raises(source.PastCorrectionSourceUnavailable):
        source.read_past_correction_v3_source(
            cast(_TenantTransaction, _Scope()), _GAME, 26
        )


@pytest.mark.parametrize(
    "page",
    [
        None,
        {"items": [], "next_cursor": None},
        {"items": [None], "next_cursor": "older"},
    ],
)
def test_incomplete_or_unbounded_page_is_rejected_before_raw_read(
    monkeypatch,
    page,
) -> None:
    """現在readが全suffixを供給しなければ原packetを資格にしない。"""

    class _Scope:
        pass

    monkeypatch.setattr(source, "_TenantTransaction", _Scope)
    monkeypatch.setattr(
        source,
        "read_lineup_prefix",
        lambda *_args, **_kwargs: OrdinaryPrefixView(
            cast(StartedGameView, None), {"page": page}
        ),
    )
    with pytest.raises(source.PastCorrectionSourceUnavailable):
        source.read_past_correction_v3_source(
            cast(_TenantTransaction, _Scope()), _GAME, 1
        )


@pytest.mark.parametrize("tamper", [None, "terminal-cursor", "changed-head"])
def test_paged_source_visits_26_in_two_bounded_pages_or_rejects_tamper(
    monkeypatch, tamper: str | None
) -> None:
    """26件を25+1で消費し、最終cursorとページ間head変化を閉じる。"""
    tenant = UUID("10000000-0000-0000-0000-000000000001")
    checkpoint_id = UUID("10000000-0000-0000-0000-000000000700")
    head = SimpleNamespace(
        length="26", tenant_id=str(tenant), game_id=str(_GAME),
        checkpoint=SimpleNamespace(id=str(checkpoint_id)), history_version="1",
    )
    changed = SimpleNamespace(
        length="26", tenant_id=str(tenant), game_id=str(_GAME),
        checkpoint=SimpleNamespace(id=str(checkpoint_id)), history_version="2",
    )
    storage = SimpleNamespace(id=str(checkpoint_id), history_epoch="1")
    checkpoint = SimpleNamespace(
        id=str(checkpoint_id), revision="1", prefix_ref=head,
        internal_generation="1", confirmed_watermark="26",
        content_digest="a" * 64,
    )
    current = {"generation": 1, "confirmed_watermark": 26}
    saved = {}
    for d1 in range(1, 27):
        event_id = UUID(int=1000 + d1)
        row_id = UUID(int=2000 + d1)
        entry = {"source": d1}
        saved[d1] = SimpleNamespace(
            d1=d1, d2=d1, source_event_id=event_id,
            play_row={"id": str(row_id), "source_event_id": str(event_id)},
            calculation=SimpleNamespace(response=SimpleNamespace(value=SimpleNamespace(
                new_history_entry=SimpleNamespace(
                    model_dump=lambda *, mode, by_alias, exclude_unset, entry=entry: (
                        entry
                    )
                ),
                next_prefix_ref=head,
            ))),
        )

    class _Scope:
        _bound_tenant_id = tenant

        def run(self, _token):
            return current

        def run_function(self, token):
            assert token.page_size == 25
            return SimpleNamespace(
                rows=tuple(
                    (d1,)
                    for d1 in range(token.after_d1 + 1, min(token.after_d1 + 27, 27))
                )
            )

    def read(_scope, _game, *, limit, cursor):
        assert limit == 25
        start = 1 if cursor is None else 26
        assert cursor == (None if start == 1 else "next")
        stop = 26 if start == 1 else 27
        items = [
            {"play_row": saved[d1].play_row, "history_entry": {"source": d1}}
            for d1 in range(start, stop)
        ]
        return OrdinaryPrefixView(
            cast(StartedGameView, None),
            {
                "page": {
                    "items": items,
                    "next_cursor": (
                        "next" if start == 1 else
                        "stale" if tamper == "terminal-cursor" else None
                    ),
                },
                "prefix_ref": (
                    changed if tamper == "changed-head" and start == 26 else head
                ),
                "checkpoint_anchor": {"id": str(checkpoint_id), "revision": "1"},
                "storage_anchor": storage,
            },
        )

    monkeypatch.setattr(source, "_TenantTransaction", _Scope)
    monkeypatch.setattr(source, "_one", lambda value, _columns: value)
    monkeypatch.setattr(source, "read_lineup_prefix", read)
    monkeypatch.setattr(source, "_function_one", lambda *_args: {
        "kind": "checkpoint",
        "row": {
            "id": str(checkpoint_id), "state": "current", "content": {},
            "content_digest": "a" * 64,
        },
    })
    monkeypatch.setattr(source, "read_lineup_prefix_document", lambda _raw: checkpoint)
    monkeypatch.setattr(
        source, "_saved_from_packet", lambda packet, *_args: saved[packet[0]]
    )
    sizes: list[int] = []

    def run():
        return source.visit_past_correction_v3_source_pages(
            cast(_TenantTransaction, _Scope()),
            _GAME,
            26,
            lambda page, _checkpoint: sizes.append(len(page)),
        )
    if tamper is not None:
        with pytest.raises(source.PastCorrectionSourceUnavailable):
            run()
    else:
        result = run()
        assert result.watermark == 26
        assert result.internal_generation == 1
        assert result.checkpoint is checkpoint
        assert sizes == [25, 1]
