"""frame参照の偽造と、値型を資格へ昇格しない境界。"""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from pitchlog.sync.first_ball_frame import (
    FirstBallBridge,
    FirstBallFrame,
    FirstBallFrameError,
    FirstBallFrameValue,
    FirstBallIntent,
)
from pitchlog.sync.port_guard import validate_port_source


@pytest.mark.parametrize("token", [FirstBallBridge, FirstBallFrame])
def test_public_construction_never_issues_a_private_reference(token: type) -> None:
    """通常構築は拒否し、object経由の偽物は値を持たない。"""
    with pytest.raises(FirstBallFrameError):
        token()
    forged = object.__new__(token)
    assert not hasattr(forged, "__dict__")


@pytest.mark.parametrize("value", [None, 1, True, b"ball", [], {}])
def test_intent_never_coerces_non_string_input(value: object) -> None:
    """wire未確定の入力をここで変換・補完しない。"""
    with pytest.raises(FirstBallFrameError):
        FirstBallIntent(cast(str, value), "batting-result.ball", "pitch-event")


def test_intent_is_frozen_and_the_value_is_not_a_certificate() -> None:
    """値型を構築してもbridgeやReadyを取得できない。"""
    intent = FirstBallIntent("batting-result", "batting-result.ball", "pitch-event")
    with pytest.raises(FrozenInstanceError):
        setattr(intent, "result_id", "other")
    value = FirstBallFrameValue(
        uuid4(),
        uuid4(),
        1,
        1,
        uuid4(),
        "f" * 64,
        "a" * 64,
        "PRIVATE_CANARY",
        "PRIVATE_CANARY",
        "PRIVATE_CANARY",
    )
    assert "PRIVATE_CANARY" not in repr(value)
    assert not hasattr(value, "ready")
    with pytest.raises(FrozenInstanceError):
        setattr(value, "response_json", "other")


def test_value_module_remains_legal_for_registered_port_imports() -> None:
    """frame値のimport閉包へhost/DB/transactionを入れない。"""
    path = Path(__file__).parents[1] / "src/pitchlog/sync/first_ball_frame.py"
    validate_port_source(path.read_text(), "pitchlog.sync.first_ball_frame")
