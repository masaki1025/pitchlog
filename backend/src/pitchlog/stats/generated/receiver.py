"""自動生成typed receiver。集計を持たない。"""

import re
from decimal import Decimal

SOURCE_MODEL_HASH = (
    "sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d"
)
METRIC_IDS = (
    "pitch_count",
    "pa",
    "ab",
    "h",
    "hr",
    "bb",
    "hbp",
    "k",
    "sh",
    "sf",
    "catcher_interference_reached",
    "runner_interference_reached",
    "doubles",
    "triples",
    "total_bases",
    "runs",
    "rbi",
    "stolen_bases",
    "pitching_outs",
    "pitcher_k",
    "pitcher_bb",
    "pitcher_hbp",
    "hits_allowed",
    "home_runs_allowed",
    "fielding_errors",
    "runs_allowed",
)


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


class OutputBudgetExceeded(ValueError):
    """型の値域とは別の明示的な出力資源予算超過。"""


def receive_fact_row(row, *, maximum_integer_chars):
    """閉列集合のSQL一行を検証する。"""
    if type(maximum_integer_chars) is not int or maximum_integer_chars < 1:
        raise ValueError("出力資源予算を明示してください")
    if type(row) is not dict or set(row) != {"metric_id", "state", "value"}:
        raise ValueError("SQL受け口の閉型が不正です")
    if row["metric_id"] not in METRIC_IDS:
        raise ValueError("未知のprimitiveです")
    state, value = (row["state"], row["value"])
    if state == "source_unavailable" and value is None:
        return {**row, "display": None}
    if state != "available" or value is None:
        raise ValueError("0/NULLと状態が一致しません")
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("有限SQL numericが必要です")
        if not value.is_zero() and value.adjusted() >= maximum_integer_chars:
            raise OutputBudgetExceeded("SQL numericの出力資源予算超過")
        if value != int(value):
            raise ValueError("SQL numericは有限整数が必要です")
        value = int(value)
    if type(value) is str and len(value) > maximum_integer_chars:
        raise OutputBudgetExceeded("整数文字列の出力資源予算超過")
    if type(value) is int and value.bit_length() > maximum_integer_chars * 4:
        raise OutputBudgetExceeded("整数の出力資源予算超過")
    rendered = format_count(value)
    if len(rendered) > maximum_integer_chars:
        raise OutputBudgetExceeded("整数の出力資源予算超過")
    return {**row, "value": rendered, "display": rendered}


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


_RATE_COMPONENTS = {"ops": ["obp", "slg"]}


def _receive_ratio_integer(value, budget):
    """生成された型検証・有限寄与処理。"""
    if value is None:
        return None
    if type(value) is Decimal:
        if not value.is_finite() or (
            not value.is_zero() and value.adjusted() >= budget
        ):
            raise OutputBudgetExceeded("比SQL numericの出力資源予算超過/非有限")
        if value != int(value):
            raise ValueError("比SQL numericは整数が必要です")
        value = int(value)
    if type(value) is str and len(value) > budget:
        raise OutputBudgetExceeded("比の出力資源予算超過")
    if type(value) is int and value.bit_length() > budget * 4:
        raise OutputBudgetExceeded("比の出力資源予算超過")
    rendered = format_count(value)
    if rendered is None or len(rendered) > budget:
        raise OutputBudgetExceeded("比の出力資源予算超過")
    return parse_count(rendered)


def receive_rate_row(row, *, maximum_integer_chars):
    """生成された型検証・有限寄与処理。"""
    if type(maximum_integer_chars) is not int or maximum_integer_chars < 1:
        raise ValueError("出力資源予算を明示してください")
    if (
        type(row) is not dict
        or type(row.get("rate_id")) is not str
        or row["rate_id"] not in _RATE_COMPONENTS
    ):
        raise ValueError("未知の派生率です")
    keys = _RATE_COMPONENTS[row["rate_id"]]
    expected = {"rate_id", "state", "value_state", "numerator", "denominator"} | {
        key + "_" + side for key in keys for side in ("numerator", "denominator")
    }
    if set(row) != expected:
        raise ValueError("比SQL受け口の閉型が不正です")
    value_n = _receive_ratio_integer(row["numerator"], maximum_integer_chars)
    value_d = _receive_ratio_integer(row["denominator"], maximum_integer_chars)
    components = {}
    for key in keys:
        n = _receive_ratio_integer(row[key + "_numerator"], maximum_integer_chars)
        d = _receive_ratio_integer(row[key + "_denominator"], maximum_integer_chars)
        if (n is None) != (d is None):
            raise ValueError("比componentのNULLが不整合です")
        components[key] = None if n is None else (n, d)
    if row["state"] == "source_unavailable" and row["value_state"] == "not_evaluated":
        if (
            value_n is not None
            or value_d is not None
            or any((pair is not None for pair in components.values()))
        ):
            raise ValueError("source不足を0で補完できません")
        return format_derived_rate(row["rate_id"], None, components)
    if row["state"] != "available" or any(
        (pair is None for pair in components.values())
    ):
        raise ValueError("比SQLの状態が不一致です")
    if row["value_state"] == "undefined_zero_denominator":
        if (
            value_n is not None
            or value_d is not None
            or (
                not any(
                    (pair is not None and pair[1] == 0 for pair in components.values())
                )
            )
        ):
            raise ValueError("零除算とNULLが不一致です")
        return format_derived_rate(row["rate_id"], None, components)
    if (
        row["value_state"] != "defined"
        or value_n is None
        or value_d is None
        or (value_d == 0)
        or any((pair is not None and pair[1] == 0 for pair in components.values()))
    ):
        raise ValueError("定義済み比の全値が不足しています")
    a, b = (value_n, value_d)
    while b:
        a, b = (b, a % b)
    if a != 1:
        raise ValueError("SQLの最終比は正準既約である必要があります")
    return format_derived_rate(row["rate_id"], (value_n, value_d), components)
