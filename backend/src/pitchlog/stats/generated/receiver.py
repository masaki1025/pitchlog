"""自動生成typed receiver。集計を持たない。"""

import re
from decimal import Decimal

SOURCE_MODEL_HASH = (
    "sha256:db0c52f2df92ddd76a9681a940e1bae83f29fb7ff7f9e988b23a76cd5b52b40d"
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
