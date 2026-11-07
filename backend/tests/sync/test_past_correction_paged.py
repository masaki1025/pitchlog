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
    assert fingerprint_p3_streaming_array(
        before, "item_digests", (value for value in values), after
    ) == expected


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
