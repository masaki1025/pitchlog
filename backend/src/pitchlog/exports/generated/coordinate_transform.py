"""自動生成。B-7の正準座標から画面整数への一方向写像。"""

import re

SOURCE_MODEL_HASH = (
    "sha256:0054a1bc629d86a638363589d1166acdbc78d6300411a097883ed5c80e50fc8c"
)
SIZE = 263
UNIT = "1/263"
_PATTERN = re.compile("(?:0|[1-9][0-9]{0,3})\\Z")


def _number(value: str) -> int:
    """非正準・範囲外を整数化前に拒否する。"""
    if type(value) is not str or _PATTERN.fullmatch(value) is None:
        raise ValueError("正準整数座標が必要です")
    number = int(value)
    if number > SIZE:
        raise ValueError("画面座標の範囲外です")
    return number


def course_screen(
    x: str | None, y: str | None, unit: str | None
) -> tuple[str | None, str | None]:
    """保存k/263を画面整数へ写し、欠測は両軸同時だけ保持する。"""
    if x is None and y is None and (unit is None):
        return (None, None)
    if unit != UNIT or type(x) is not str or type(y) is not str:
        raise ValueError("正準座標単位が不一致です")
    x_value = _number(x)
    y_value = _number(y)
    return (str(x_value), str(SIZE - y_value))
