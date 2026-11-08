"""P3の有界ページ指紋と旧一括正規JSONの全値一致。"""

from __future__ import annotations

import pytest

from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.past_correction_paged import (
    PastCorrectionPageUnavailable,
    fingerprint_p3_streaming_array,
)


@pytest.mark.parametrize("size", [0, 1, 25, 26, 51])
def test_streaming_array_digest_equals_existing_canonical_source_fingerprint(
    size: int,
) -> None:
    """25件境界とUnicode/入れ子を旧完全JSONのSHAへ一致させる。"""
    before = {"capsule_id": "壱", "change_event_id": "2"}
    values = [
        {"d1": index, "entry": {"b": [None, True, "球"], "a": index}}
        for index in range(size)
    ]
    after = {"new_checkpoint_digest": "a" * 64, "old_checkpoint_digest": "b" * 64}
    expected = source_fingerprint({**before, "item_digests": values, **after})
    assert (
        fingerprint_p3_streaming_array(
            before, "item_digests", (value for value in values), after
        )
        == expected
    )


@pytest.mark.parametrize(
    ("before", "key", "values", "after"),
    [
        ({"z": 1}, "items", (), {}),
        ({}, "items", (), {"a": 1}),
        ({}, "items", "text", {}),
        ({}, "items", (float("nan"),), {}),
    ],
)
def test_streaming_array_digest_rejects_invalid_order_or_value(
    before, key, values, after
) -> None:
    """key順序逆転・文字列反復・非JSON数値を閉じる。"""
    with pytest.raises(PastCorrectionPageUnavailable):
        fingerprint_p3_streaming_array(before, key, values, after)


def test_page_binding_checks_same_opaque_source_and_keeps_expiry_failure(monkeypatch):
    """同scope/event/sourceを変えず呼び、対象差替えと失効を成功化しない。"""
    from uuid import UUID

    from pitchlog.sync import past_correction_paged as paged

    scope = object.__new__(paged._TenantTransaction)
    event = object.__new__(paged.SyncEvent)
    source = object()
    expected = (UUID(int=1), 1, 26, "opaque-original-d4")
    calls = []

    def target(actual_scope, actual_event, actual_source):
        calls.append((actual_scope, actual_event, actual_source))
        return expected

    monkeypatch.setattr(paged, "_bound_target", target)
    paged._assert_page_binding(scope, event, source, expected)
    assert calls == [(scope, event, source)]
    changed = (UUID(int=1), 1, 25, "opaque-original-d4")
    with pytest.raises(PastCorrectionPageUnavailable):
        paged._assert_page_binding(scope, event, source, changed)
    failure = RuntimeError("失効した真正資格")

    def expired(*_args):
        raise failure

    monkeypatch.setattr(paged, "_bound_target", expired)
    with pytest.raises(RuntimeError) as caught:
        paged._assert_page_binding(scope, event, source, expected)
    assert caught.value is failure
