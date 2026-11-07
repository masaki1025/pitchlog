"""訂正前current原本の有限読取が未確認scopeを拒否する。"""

from __future__ import annotations

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
