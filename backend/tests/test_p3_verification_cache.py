"""P3 packet/頁のプロセス内検証cacheが全bytes一致時だけ省略することを検査する。"""

from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from pitchlog.repositories import past_correction_current as current
from pitchlog.repositories import past_correction_current_paged as paged


@pytest.fixture(autouse=True)
def _clear_caches():
    """各試験で有界cacheの内容を分離する。"""
    current._P3_PACKET_CACHE.clear()
    current._P3_PACKET_INFLIGHT.clear()
    paged._P3_PAGED_CACHE.clear()
    yield
    current._P3_PACKET_CACHE.clear()
    current._P3_PACKET_INFLIGHT.clear()
    paged._P3_PAGED_CACHE.clear()


def test_packet_verification_is_reused_only_for_identical_bytes(monkeypatch):
    """同一packet/scopeは一度だけ本体へ入り、1値変更で再検証する。"""
    tenant, game = uuid4(), uuid4()
    calls = []
    sentinel = object()

    def uncached(packet, **kwargs):
        calls.append((packet, kwargs))
        return sentinel

    monkeypatch.setattr(current, "_verify_p3_current_packet_uncached", uncached)
    packet = {"kind": "p3-current", "members": [{"d1": 1}]}
    first = current.verify_p3_current_packet(
        packet, tenant=tenant, game=game, generation=1
    )
    second = current.verify_p3_current_packet(
        packet, tenant=tenant, game=game, generation=1
    )
    assert first is sentinel and second is sentinel
    assert len(calls) == 1
    changed = {"kind": "p3-current", "members": [{"d1": 2}]}
    current.verify_p3_current_packet(
        changed, tenant=tenant, game=game, generation=1
    )
    current.verify_p3_current_packet(
        packet, tenant=tenant, game=game, generation=2
    )
    assert len(calls) == 3


def test_same_packet_is_verified_once_under_concurrency(monkeypatch):
    """同一packetの同時閲覧を単一の実検証へ集約し、CPU競合を避ける。"""
    tenant, game = uuid4(), uuid4()
    calls = []
    sentinel = object()

    def uncached(packet, **kwargs):
        calls.append(packet)
        time.sleep(0.2)
        return sentinel

    monkeypatch.setattr(current, "_verify_p3_current_packet_uncached", uncached)
    packet = {"kind": "p3-current", "members": [{"d1": 1}]}
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                current.verify_p3_current_packet(
                    packet, tenant=tenant, game=game, generation=1
                )
            )
        )
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(calls) == 1
    assert len(results) == 8 and all(result is sentinel for result in results)


def test_packet_verification_failure_is_not_cached(monkeypatch):
    """失敗したpacketを成功済みとして保持しない。"""
    tenant, game = uuid4(), uuid4()
    calls = []

    def uncached(packet, **kwargs):
        calls.append(packet)
        raise current.PastCorrectionCurrentUnavailable("P3 current packetが不正")

    monkeypatch.setattr(current, "_verify_p3_current_packet_uncached", uncached)
    packet = {"kind": "p3-current"}
    for _ in range(2):
        with pytest.raises(current.PastCorrectionCurrentUnavailable):
            current.verify_p3_current_packet(
                packet, tenant=tenant, game=game, generation=1
            )
    assert len(calls) == 2


def test_packet_cache_is_bounded(monkeypatch):
    """成功結果の保持件数は固定上限を超えない。"""
    tenant, game = uuid4(), uuid4()
    monkeypatch.setattr(
        current, "_verify_p3_current_packet_uncached", lambda packet, **kwargs: packet
    )
    for index in range(current._P3_PACKET_CACHE_LIMIT + 3):
        current.verify_p3_current_packet(
            {"packet": index}, tenant=tenant, game=game, generation=1
        )
    assert len(current._P3_PACKET_CACHE) == current._P3_PACKET_CACHE_LIMIT


def test_paged_verification_is_reused_only_for_identical_pages(monkeypatch):
    """header/全頁/要求範囲が同一のときだけ本体の再実行を省略する。"""
    tenant, game = uuid4(), uuid4()
    calls = []
    sentinel = object()

    def uncached(header, pages, **kwargs):
        calls.append((header, tuple(pages), kwargs))
        return sentinel

    monkeypatch.setattr(paged, "_verify_p3_paged_current_uncached", uncached)
    header = {"kind": "p3-paged-header"}
    pages = [{"items": [{"d1": 1}]}, {"items": [{"d1": 2}]}]
    for _ in range(2):
        assert (
            paged.verify_p3_paged_current(
                header,
                iter(pages),
                tenant=tenant,
                game=game,
                generation=1,
                selected_after_d1=0,
                selected_limit=25,
            )
            is sentinel
        )
    assert len(calls) == 1
    paged.verify_p3_paged_current(
        header,
        iter([pages[0], {"items": [{"d1": 3}]}]),
        tenant=tenant,
        game=game,
        generation=1,
        selected_after_d1=0,
        selected_limit=25,
    )
    paged.verify_p3_paged_current(
        header,
        iter(pages),
        tenant=tenant,
        game=game,
        generation=1,
        selected_after_d1=0,
        selected_limit=24,
    )
    assert len(calls) == 3


def test_paged_verification_failure_is_not_cached(monkeypatch):
    """頁検証の失敗結果を保持しない。"""
    tenant, game = uuid4(), uuid4()
    calls = []

    def uncached(header, pages, **kwargs):
        calls.append(tuple(pages))
        raise current.PastCorrectionCurrentUnavailable("P3頁境界が不一致")

    monkeypatch.setattr(paged, "_verify_p3_paged_current_uncached", uncached)
    for _ in range(2):
        with pytest.raises(current.PastCorrectionCurrentUnavailable):
            paged.verify_p3_paged_current(
                {"kind": "p3-paged-header"},
                [{"items": []}],
                tenant=tenant,
                game=game,
                generation=1,
                selected_after_d1=0,
                selected_limit=25,
            )
    assert len(calls) == 2
