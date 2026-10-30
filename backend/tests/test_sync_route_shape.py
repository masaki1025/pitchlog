"""同期入口の経路選択がP2に限定され、P3を成功扱いにしないことを固定する。"""

import pytest

from pitchlog.api.routers.sync import _request_path
from pitchlog.sync.apply import _E1OutOfScope
from pitchlog.sync.model import RequestShapeError


def _event(**extra: object) -> dict[str, object]:
    request = {"d5": "x", "d1": 1, "d4": "d4.1.x", "game_id": "g"}
    request.update(extra)
    return request


def test_d1_event_with_d2_is_p2() -> None:
    """D2を持つD1列だけをP2として受ける。"""
    assert _request_path({"events": [_event(d2=1)]}) == "P2"


def test_p3_change_body_is_out_of_scope() -> None:
    """P3は本入口の対象外として閉拒否する（成功ACKを発行しない）。"""
    with pytest.raises(_E1OutOfScope):
        _request_path({"change": {}, "recovery_generation": "x"})


def test_d1_event_without_d2_is_out_of_scope() -> None:
    """初球P2以外のD1列は本入口で受けない。"""
    with pytest.raises(_E1OutOfScope):
        _request_path({"events": [_event()]})


@pytest.mark.parametrize(
    "payload",
    [{}, {"events": []}, {"events": "x"}, {"events": [1]}, "not-object", None],
)
def test_malformed_body_is_rejected(payload: object) -> None:
    """外形不正をP2として扱わない。"""
    with pytest.raises((RequestShapeError, _E1OutOfScope)):
        _request_path(payload)
