# generated=sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6
"""自動生成されたT6表示率。T5 artifactのfacts.pyを変更しない。"""

from pitchlog.stats.generated.formatter import _rate_result, format_count


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
    "whip": {
        "scale": 2,
        "rounding": "half-up",
        "leadingZero": True,
        "zeroDivisionGlyph": "−",
        "denominators": [
            {"component": "whip", "prefix": "", "suffix": "", "format": "innings"}
        ],
    },
}
_COMPONENT_DISPLAYS = {
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
}


def format_innings(outs):
    """アウト数をA-2の混合分数へ表示する。"""
    if type(outs) is not int or outs < 0:
        raise ValueError("投球回のアウト数は非負整数です")
    whole, remainder = divmod(outs, 3)
    return (
        format_count(whole)
        + "回"
        + (format_count(remainder) + "/3" if remainder else "")
    )


def _display_result(value, components, display, reason):
    """表示規則の先頭0だけを最後に適用し、比の値を再計算しない。"""
    result = _rate_result(value, components, display, reason)
    if result["state"] == "available" and any(
        ("format" in label for label in display["denominators"])
    ):
        labels = []
        for label in display["denominators"]:
            denominator = int(result["components"][label["component"]]["denominator"])
            rendered = (
                format_innings(denominator)
                if label.get("format") == "innings"
                else format_count(denominator)
            )
            labels.append(label["prefix"] + rendered + label["suffix"])
        result = {
            **result,
            "display": result["formatted_value"] + "(" + "・".join(labels) + ")",
        }
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


def format_component_rate(component_id, pair, reason="MISSING_OBSERVATION"):
    """T5が計算した比componentを、T6の表示規則だけで表示する。"""
    if type(component_id) is not str or component_id not in _COMPONENT_DISPLAYS:
        raise ValueError("未知の表示componentです")
    display = _COMPONENT_DISPLAYS[component_id]
    result = _display_result(pair, {component_id: pair}, display, reason)
    return result


def derive_display_rates(metrics):
    """宣言済みT6表示率を同じ生成済み表示規則で返す。"""
    results = {}
    values = {"h": _metric_value(metrics, "h"), "ab": _metric_value(metrics, "ab")}
    parts_0 = {"avg": _ratio(values["h"], values["ab"])}
    results["avg"] = _display_result(
        parts_0["avg"], parts_0, _DISPLAY_RATES["avg"], _reason(metrics, ("h", "ab"))
    )
    values = {
        "hits_allowed": _metric_value(metrics, "hits_allowed"),
        "pitcher_bb": _metric_value(metrics, "pitcher_bb"),
        "pitching_outs": _metric_value(metrics, "pitching_outs"),
    }
    parts_1 = {
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
        parts_1["whip"],
        parts_1,
        _DISPLAY_RATES["whip"],
        _reason(metrics, ("hits_allowed", "pitcher_bb", "pitching_outs")),
    )
    return results
