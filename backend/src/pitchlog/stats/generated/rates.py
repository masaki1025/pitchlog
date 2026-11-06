# generated=sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d
"""自動生成されたT6表示率。T5 artifactのfacts.pyを変更しない。"""

from pitchlog.stats.generated.formatter import _rate_result


def _rate_add(*values):
    """生成された型検証・有限寄与処理。"""
    return None if any((value is None for value in values)) else sum(values)


def _ratio(numerator, denominator):
    """生成された型検証・有限寄与処理。"""
    if numerator is None or denominator is None:
        return None
    return (numerator, denominator)


def _ratio_add(*values):
    """生成された型検証・有限寄与処理。"""
    if any((value is None or value[1] == 0 for value in values)):
        return None
    numerator, denominator = (0, 1)
    for n, d in values:
        numerator, denominator = (numerator * d + n * denominator, denominator * d)
    return (numerator, denominator)


_DISPLAY_RATES = {
    "avg": {
        "scale": 3,
        "rounding": "half-up",
        "leadingZero": False,
        "zeroDivisionGlyph": "−",
        "denominators": [{"component": "avg", "prefix": "打数", "suffix": ""}],
    },
    "obp": {
        "scale": 3,
        "rounding": "half-up",
        "leadingZero": False,
        "zeroDivisionGlyph": "−",
        "denominators": [{"component": "obp", "prefix": "打席", "suffix": ""}],
    },
    "slg": {
        "scale": 3,
        "rounding": "half-up",
        "leadingZero": False,
        "zeroDivisionGlyph": "−",
        "denominators": [{"component": "slg", "prefix": "打数", "suffix": ""}],
    },
    "whip": {
        "scale": 2,
        "rounding": "half-up",
        "leadingZero": True,
        "zeroDivisionGlyph": "−",
        "denominators": [{"component": "whip", "prefix": "投球回", "suffix": ""}],
    },
}


def _display_result(value, components, display, reason):
    """表示規則の先頭0だけを最後に適用し、比の値を再計算しない。"""
    result = _rate_result(value, components, display, reason)
    if not display["leadingZero"] and result["formatted_value"] is not None:
        original = result["formatted_value"]
        formatted = original.removeprefix("0")
        result = {**result, "formatted_value": formatted}
        if result["display"] is not None:
            result = {
                **result,
                "display": formatted + result["display"][len(original) :],
            }
    return result


def _metric_value(metrics, key):
    """十分統計の状態を表示率の入力へ写す。0と未取得を混同しない。"""
    row = metrics[key]
    if type(row) is not dict or row.get("state") not in (
        "available",
        "source_unavailable",
    ):
        raise ValueError("十分統計の状態が不正です")
    if row["state"] == "source_unavailable":
        return None
    value = row.get("value")
    if type(value) is not int or value < 0:
        raise ValueError("十分統計の値が不正です")
    return value


def _reason(metrics, dependencies):
    """最初の不足理由を保持し、未取得を0へ変えない。"""
    for key in dependencies:
        row = metrics[key]
        if row["state"] == "source_unavailable":
            return row.get("reason") or "MISSING_OBSERVATION"
    return "MISSING_OBSERVATION"


def derive_display_rates(metrics):
    """宣言済みT6表示率を同じ生成済み表示規則で返す。"""
    results = {}
    values = {"h": _metric_value(metrics, "h"), "ab": _metric_value(metrics, "ab")}
    parts_0 = {"avg": _ratio(values["h"], values["ab"])}
    results["avg"] = _display_result(
        parts_0["avg"], parts_0, _DISPLAY_RATES["avg"], _reason(metrics, ("h", "ab"))
    )
    values = {
        "h": _metric_value(metrics, "h"),
        "bb": _metric_value(metrics, "bb"),
        "hbp": _metric_value(metrics, "hbp"),
        "ab": _metric_value(metrics, "ab"),
        "sf": _metric_value(metrics, "sf"),
    }
    parts_1 = {
        "obp": _ratio(
            _rate_add(values["h"], values["bb"], values["hbp"]),
            _rate_add(values["ab"], values["bb"], values["hbp"], values["sf"]),
        )
    }
    results["obp"] = _display_result(
        parts_1["obp"],
        parts_1,
        _DISPLAY_RATES["obp"],
        _reason(metrics, ("h", "bb", "hbp", "ab", "sf")),
    )
    values = {
        "total_bases": _metric_value(metrics, "total_bases"),
        "ab": _metric_value(metrics, "ab"),
    }
    parts_2 = {"slg": _ratio(values["total_bases"], values["ab"])}
    results["slg"] = _display_result(
        parts_2["slg"],
        parts_2,
        _DISPLAY_RATES["slg"],
        _reason(metrics, ("total_bases", "ab")),
    )
    values = {
        "hits_allowed": _metric_value(metrics, "hits_allowed"),
        "pitcher_bb": _metric_value(metrics, "pitcher_bb"),
        "pitching_outs": _metric_value(metrics, "pitching_outs"),
    }
    parts_3 = {
        "whip": _ratio(
            _rate_add(
                values["hits_allowed"],
                values["pitcher_bb"],
                values["hits_allowed"],
                values["pitcher_bb"],
                values["hits_allowed"],
                values["pitcher_bb"],
            ),
            values["pitching_outs"],
        )
    }
    results["whip"] = _display_result(
        parts_3["whip"],
        parts_3,
        _DISPLAY_RATES["whip"],
        _reason(metrics, ("hits_allowed", "pitcher_bb", "pitching_outs")),
    )
    return results
