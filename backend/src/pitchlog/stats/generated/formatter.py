# generated=sha256:7f0282944e6ce61d171caa428b4240a9429b0ac30d0e9f55dea828cec6a76524
"""自動生成された整数表示・型検証。"""

import re


def parse_count(value):
    """globalの整数桁上限を変えず、正準整数を有限chunkで読む。"""
    if type(value) is int and value >= 0:
        return value
    if type(value) is not str or re.fullmatch("0|[1-9][0-9]*", value) is None:
        raise ValueError("正準非負整数が必要です")
    number = 0
    for offset in range(0, len(value), 9):
        chunk = value[offset : offset + 9]
        number = number * 10 ** len(chunk) + int(chunk)
    return number


def format_count(value):
    """任意精度整数を表示し、NULLを0へ変換しない。"""
    if value is None:
        return None
    if type(value) is str and re.fullmatch("0|[1-9][0-9]*", value):
        return value
    if type(value) is not int or value < 0:
        raise ValueError("正準非負整数が必要です")
    if value == 0:
        return "0"
    groups = []
    while value:
        value, remainder = divmod(value, 1000000000)
        groups.append(str(remainder))
    return groups[-1] + "".join((group.zfill(9) for group in reversed(groups[:-1])))


def _rate_result(value, components, display, reason="MISSING_OBSERVATION"):
    """生成された型検証・有限寄与処理。"""
    if type(components) is not dict or set(components) != {
        x["component"] for x in display["denominators"]
    }:
        raise ValueError("比componentの閉集合が不正です")
    for pair in [value, *components.values()]:
        if pair is not None and (
            type(pair) is not tuple
            or len(pair) != 2
            or any((type(x) is not int or x < 0 for x in pair))
        ):
            raise ValueError("比の整数型が不正です")
    if any((pair is None for pair in components.values())):
        if value is not None:
            raise ValueError("不足観測に比を補完できません")
        return {
            "state": "source_unavailable",
            "value_state": "not_evaluated",
            "exact_ratio": None,
            "components": None,
            "formatted_value": None,
            "display": None,
            "reason": reason,
        }
    raw = {
        key: {"numerator": format_count(pair[0]), "denominator": format_count(pair[1])}
        for key, pair in components.items()
    }
    if any((pair[1] == 0 for pair in components.values())):
        exact = None
        formatted = display["zeroDivisionGlyph"]
        state = "undefined_zero_denominator"
    else:
        if value is None:
            raise ValueError("定義済み比の値が不足しています")
        n, d = value
        if d == 0:
            raise ValueError("定義済み比の分母は正です")
        a, b = (n, d)
        while b:
            a, b = (b, a % b)
        n, d = (n // a, d // a)
        exact = {"numerator": format_count(n), "denominator": format_count(d)}
        power = 10 ** display["scale"]
        quotient, remainder = divmod(n * power, d)
        rounded = quotient + (2 * remainder >= d)
        integer, fraction = divmod(rounded, power)
        formatted = (
            format_count(integer) + "." + format_count(fraction).zfill(display["scale"])
        )
        state = "defined"
    labels = [
        label["prefix"] + raw[label["component"]]["denominator"] + label["suffix"]
        for label in display["denominators"]
    ]
    return {
        "state": "available",
        "value_state": state,
        "exact_ratio": exact,
        "components": raw,
        "formatted_value": formatted,
        "display": formatted + "(" + "・".join(labels) + ")",
        "reason": None,
    }


_RATE_DISPLAYS = {
    "ops": {
        "scale": 3,
        "rounding": "half-up",
        "leadingZero": True,
        "zeroDivisionGlyph": "−",
        "denominators": [
            {"component": "obp", "prefix": "出塁率分母", "suffix": "打席"},
            {"component": "slg", "prefix": "長打率分母", "suffix": "打数"},
        ],
    }
}


def format_derived_rate(rate_id, value, components, reason="MISSING_OBSERVATION"):
    """生成された型検証・有限寄与処理。"""
    if type(rate_id) is not str or rate_id not in _RATE_DISPLAYS:
        raise ValueError("未知の派生率です")
    return _rate_result(value, components, _RATE_DISPLAYS[rate_id], reason)
