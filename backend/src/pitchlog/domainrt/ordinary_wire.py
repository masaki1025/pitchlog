"""通常投球の凍結wire名。API層は語彙を再宣言せずこの定数を参照する。"""

from __future__ import annotations

from typing import Any

# 初期応答と同じ凍結wire名。
RECOVERY_WIRE_FIELD = "recovery_generation"


def assert_prefix_matches(
    prefix_ref: Any, game_id: str, current_d4: str | None
) -> None:
    """prefixの試合とD4が現在値へ一致することを検査する。

    Args:
        prefix_ref: 検証対象のprefix参照。
        game_id: 応答が表す試合ID。
        current_d4: 応答が表す現在D4。

    Raises:
        ValueError: prefixと試合またはD4が不一致。
    """
    values = prefix_ref.model_dump()
    if prefix_ref.game_id != game_id or values["generation"] != current_d4:
        raise ValueError("prefixと試合/現在D4が不一致")
