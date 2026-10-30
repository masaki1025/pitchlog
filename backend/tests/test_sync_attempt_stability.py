"""再送時に同じ attempt と同じ phase を使い、新 ID へ置換しないことを固定する。"""

from uuid import uuid4

from pitchlog.api.routers.sync import _phase_id


def test_same_attempt_and_request_reuse_the_same_phase() -> None:
    """同一要求の再送で phase が変わらない（二重処理の温床を作らない）。"""
    attempt, fingerprint = uuid4(), "a" * 64
    assert _phase_id(attempt, fingerprint) == _phase_id(attempt, fingerprint)


def test_different_attempt_gets_a_different_phase() -> None:
    """別 attempt は別 phase になり、同じ要求を取り違えない。"""
    fingerprint = "b" * 64
    assert _phase_id(uuid4(), fingerprint) != _phase_id(uuid4(), fingerprint)


def test_same_attempt_with_different_content_is_a_different_phase() -> None:
    """同じ attempt でも内容が変われば同一要求として扱わない。"""
    attempt = uuid4()
    assert _phase_id(attempt, "c" * 64) != _phase_id(attempt, "d" * 64)
