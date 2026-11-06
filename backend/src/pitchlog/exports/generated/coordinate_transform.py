"""自動生成。B-7の正準座標から画面整数への一方向写像。"""

import re
from datetime import datetime, timezone

SOURCE_MODEL_HASH = (
    "sha256:6be2f315e519fa8054ae6980ce8b5e161dbf197793d1400bbbe1e56ac15d7e14"
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


def server_accepted_elapsed(start: datetime, accepted: datetime) -> str:
    """試合開始からサーバー受理までの完了分をh:mmで返す。"""
    if (
        type(start) is not datetime
        or type(accepted) is not datetime
        or start.utcoffset() is None
        or (accepted.utcoffset() is None)
    ):
        raise ValueError("開始/受理時刻が不正です")
    try:
        first = start.astimezone(timezone.utc)
        last = accepted.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ValueError("開始/受理時刻が不正です") from None
    if last < first:
        raise ValueError("開始/受理時刻が不正です")
    elapsed = last - first
    minutes = elapsed.days * 1440 + elapsed.seconds // 60
    hours, minute = divmod(minutes, 60)
    return f"{hours}:{minute:02d}"


FIELDING_POSITION_LABELS = {
    "1": "P",
    "2": "C",
    "3": "1B",
    "4": "2B",
    "5": "3B",
    "6": "SS",
    "7": "LF",
    "8": "CF",
    "9": "RF",
}
DH_LABEL = "DH"


def fielding_position_label(role: dict[str, str]) -> str:
    """保存された有限守備roleを旧表示欄へ写す。"""
    if type(role) is not dict:
        raise ValueError("守備位置roleが不正です")
    if role == {"kind": "designated-hitter"}:
        return DH_LABEL
    if set(role) != {"kind", "position"} or role.get("kind") != "fielding":
        raise ValueError("守備位置roleが不正です")
    position = role["position"]
    if type(position) is not str or position not in FIELDING_POSITION_LABELS:
        raise ValueError("守備位置roleが不正です")
    return FIELDING_POSITION_LABELS[position]


PLATE_RESULT_ALIASES = {
    "見逃し三振": "見三振",
    "空振り三振": "空三振",
    "三振ゲッツー": "三振併",
    "振り逃げ": "振逃",
    "ファールフライ": "邪飛",
}


def plate_result_display(
    label: str | None, pa_ended: bool, fielder: str | None, ball_type: str | None
) -> str | None:
    """確定打席結果だけを旧有限表示へ写す。"""
    if type(pa_ended) is not bool or (label is not None and type(label) is not str):
        raise ValueError("打席結果原本が不正です")
    if not pa_ended:
        return None
    if not label:
        raise ValueError("完了打席の結果が欠測です")
    if label in PLATE_RESULT_ALIASES:
        return PLATE_RESULT_ALIASES[label]
    if label in ("併殺打", "ライナー併殺", "凡打死", "凡打出塁"):
        if type(fielder) is not str or fielder not in tuple(
            (str(n) for n in range(1, 10))
        ):
            raise ValueError("捕球選手が欠測です")
        if label == "ライナー併殺":
            return f"{fielder}ライナー併"
        if type(ball_type) is not str or not ball_type:
            raise ValueError("打球種類が欠測です")
        return f"{fielder}{ball_type}" + ("併" if label == "併殺打" else "")
    return label
