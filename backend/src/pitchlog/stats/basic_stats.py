"""基本成績27項目を、単一のT5/T6十分統計から表示値へ写す。

このmoduleは集計・率の再計算を持たない。打撃16・投手11の各項目は、
保存済みの26十分統計と生成済みの表示率（OPS/打率/出塁率/長打率/WHIP）を
参照するだけであり、未供給の登板・打者数を0へ補完しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pitchlog.stats.facts import derive_rates as _derive_ops
from pitchlog.stats.generated.formatter import format_count
from pitchlog.stats.generated.rates import (
    derive_display_rates,
    format_component_rate,
)

# 生成済みT5核が返す閉26十分統計。順序はmodel宣言順。
COUNT_METRIC_IDS = (
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

# 27項目の表示順・表示名・source。countは十分統計、rateは生成formatter。
BATTING_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("pa", "打席", "count"),
    ("ab", "打数", "count"),
    ("h", "安打", "count"),
    ("doubles", "二塁打", "count"),
    ("triples", "三塁打", "count"),
    ("hr", "本塁打", "count"),
    ("runs", "得点", "count"),
    ("rbi", "打点", "count"),
    ("bb", "四球", "count"),
    ("hbp", "死球", "count"),
    ("k", "三振", "count"),
    ("stolen_bases", "盗塁", "count"),
    ("avg", "打率", "rate"),
    ("obp", "出塁率", "rate"),
    ("slg", "長打率", "rate"),
    ("ops", "OPS", "rate"),
)

PITCHING_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("appearances", "登板", "appearance"),
    ("innings_pitched", "投球回", "innings"),
    ("batters_faced", "打者数", "batters_faced"),
    ("hits_allowed", "被安打", "count"),
    ("home_runs_allowed", "被本塁打", "count"),
    ("pitcher_bb", "与四球", "count"),
    ("pitcher_hbp", "与死球", "count"),
    ("pitcher_k", "奪三振", "count"),
    ("runs_allowed", "失点", "count"),
    ("whip", "WHIP", "rate"),
    ("pitch_count", "球数", "count"),
)

_PENDING = {
    "appearances": ("D03_SOURCE_PENDING", "登板の正式出場sourceが未接続です"),
    "batters_faced": ("D04_SOURCE_PENDING", "打者数の責任帰属sourceが未接続です"),
}


@dataclass(frozen=True, slots=True)
class ItemValue:
    """1項目の表示値。stateとreasonを値から分離する。"""

    metric_id: str
    label: str
    state: str
    value: int | str | None
    display: str | None
    reason: str | None = None
    components: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSONへ写す閉じた表現を返す。"""
        return {
            "metric_id": self.metric_id,
            "label": self.label,
            "state": self.state,
            "value": self.value,
            "display": self.display,
            "reason": self.reason,
            "components": self.components,
        }


def _normalized_metrics(metrics: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """閉26十分統計だけを受け取り、余剰・欠落・型混同を拒否する。"""
    if type(metrics) is not dict:
        raise ValueError("十分統計はdictが必要です")
    required = set(COUNT_METRIC_IDS)
    # 27番目以降の追加metric（BF等）は任意で受け取る。ただし未知IDは拒否。
    optional = {"appearances", "batters_faced"}
    if not required <= set(metrics) or not set(metrics) <= required | optional:
        raise ValueError("十分統計の閉集合が不一致です")
    result: dict[str, dict[str, Any]] = {}
    for key, row in metrics.items():
        if type(key) is not str or type(row) is not dict:
            raise ValueError("十分統計の型が不正です")
        if row.get("state") not in ("available", "source_unavailable"):
            raise ValueError("十分統計の状態が不正です")
        if row["state"] == "available":
            value = row.get("value")
            if type(value) is not int or value < 0:
                raise ValueError("十分統計の値が不正です")
            result[key] = {"state": "available", "value": value}
        else:
            reason = row.get("reason")
            if reason is not None and type(reason) is not str:
                raise ValueError("不足理由の型が不正です")
            result[key] = {"state": "source_unavailable", "reason": reason}
    return result


def _count_item(
    metric_id: str, label: str, metrics: Mapping[str, Mapping[str, Any]]
) -> ItemValue:
    """保存済み整数をそのまま表示し、未取得を0へ変えない。"""
    row = metrics[metric_id]
    if row["state"] == "source_unavailable":
        return ItemValue(
            metric_id,
            label,
            "source_unavailable",
            None,
            None,
            row.get("reason") or "MISSING_OBSERVATION",
        )
    value = row["value"]
    return ItemValue(metric_id, label, "available", value, format_count(value))


def _rate_item(
    metric_id: str,
    label: str,
    rates: Mapping[str, Mapping[str, Any]],
) -> ItemValue:
    """生成済み表示率だけを写し、丸めや分母を再計算しない。"""
    row = rates[metric_id]
    if row["state"] == "source_unavailable":
        return ItemValue(
            metric_id,
            label,
            "source_unavailable",
            None,
            None,
            row.get("reason") or "MISSING_OBSERVATION",
        )
    value_state = row["value_state"]
    display = row["display"]
    return ItemValue(
        metric_id,
        label,
        "available",
        display,
        display,
        None,
        {
            "value_state": value_state,
            "exact_ratio": row["exact_ratio"],
            "components": row["components"],
        },
    )


def _innings_item(metrics: Mapping[str, Mapping[str, Any]]) -> ItemValue:
    """投球回はアウト数の表示変換だけを行い、率を再計算しない。"""
    row = metrics["pitching_outs"]
    if row["state"] == "source_unavailable":
        return ItemValue(
            "innings_pitched",
            "投球回",
            "source_unavailable",
            None,
            None,
            row.get("reason") or "MISSING_OBSERVATION",
        )
    outs = row["value"]
    whole, remainder = divmod(outs, 3)
    return ItemValue(
        "innings_pitched",
        "投球回",
        "available",
        f"{whole}.{remainder}",
        f"{whole}.{remainder}",
        None,
        {"outs": outs},
    )


def _pending_item(metric_id: str) -> ItemValue:
    """正式sourceが未接続の項目を、0ではなく未取得として返す。"""
    reason, message = _PENDING[metric_id]
    label = next(label for key, label, _ in PITCHING_ITEMS if key == metric_id)
    return ItemValue(
        metric_id, label, "source_unavailable", None, None, reason, {"message": message}
    )


def build_basic_stats(
    metrics: Mapping[str, Any], *, appearances: int | None = None
) -> dict[str, Any]:
    """26十分統計から打撃16・投手11の表示値を組み立てる。

    Args:
        metrics: metric_idごとの ``{"state", "value"}``。閉26を必須とする。
        appearances: 正式な投手出場数が供給された場合だけ渡す。未供給はNone。

    Returns:
        ``batting``/``pitching``/``is_pitcher``/``pending`` を持つ辞書。

    Raises:
        ValueError: 十分統計の閉集合・型・状態が不正な場合。
    """
    normalized = _normalized_metrics(metrics)
    if appearances is not None and (type(appearances) is not int or appearances < 0):
        raise ValueError("登板数は非負整数が必要です")
    if appearances is not None:
        normalized["appearances"] = {"state": "available", "value": appearances}

    # 生成率は閉26を要求する。追加metricを混ぜず、元の26だけを渡す。
    count_metrics = {key: normalized[key] for key in COUNT_METRIC_IDS}
    rates = derive_display_rates(count_metrics)
    # 生成済みT5核のOPS入力はvalue/display/reasonの閉型を要求する。
    ops_metrics = {}
    for key, row in count_metrics.items():
        if row["state"] == "available":
            rendered = format_count(row["value"])
            ops_metrics[key] = {
                "state": "available",
                "value": rendered,
                "display": rendered,
                "reason": None,
            }
        else:
            reason = row.get("reason")
            if reason not in (
                "MISSING_OBSERVATION",
                "MISSING_ATTRIBUTION",
                "UNSUPPORTED_SOURCE_VARIANT",
            ):
                reason = "MISSING_OBSERVATION"
            ops_metrics[key] = {
                "state": "source_unavailable",
                "value": None,
                "display": None,
                "reason": reason,
            }
    ops = _derive_ops(ops_metrics)["ops"]
    rates["ops"] = ops
    # OBP/SLGはT5 OPSの同じcomponent pairを使い、式を二重実装しない。
    for component in ("obp", "slg"):
        if ops["state"] == "source_unavailable":
            rates[component] = ops
            continue
        raw = ops["components"][component]
        rates[component] = format_component_rate(
            component,
            (int(raw["numerator"]), int(raw["denominator"])),
        )

    batting = []
    for metric_id, label, kind in BATTING_ITEMS:
        if kind == "count":
            batting.append(_count_item(metric_id, label, normalized).as_dict())
        else:
            batting.append(_rate_item(metric_id, label, rates).as_dict())

    pitching = []
    for metric_id, label, kind in PITCHING_ITEMS:
        if kind == "count":
            pitching.append(_count_item(metric_id, label, normalized).as_dict())
        elif kind == "innings":
            pitching.append(_innings_item(normalized).as_dict())
        elif kind == "rate":
            pitching.append(_rate_item(metric_id, label, rates).as_dict())
        elif kind == "appearance":
            if "appearances" in normalized:
                pitching.append(_count_item(metric_id, label, normalized).as_dict())
            else:
                pitching.append(_pending_item(metric_id).as_dict())
        else:
            if "batters_faced" in normalized:
                pitching.append(_count_item(metric_id, label, normalized).as_dict())
            else:
                pitching.append(_pending_item(metric_id).as_dict())

    pitch_count = normalized["pitch_count"]
    is_pitcher = (
        (pitch_count["state"] == "available" and pitch_count["value"] > 0)
        or (
            normalized["pitching_outs"]["state"] == "available"
            and normalized["pitching_outs"]["value"] > 0
        )
        or "appearances" in normalized
        or "batters_faced" in normalized
    )

    return {
        "batting": batting,
        "pitching": pitching,
        "is_pitcher": is_pitcher,
        "pending": [
            "D03_SOURCE_PENDING" if "appearances" not in normalized else None,
            "D04_SOURCE_PENDING" if "batters_faced" not in normalized else None,
        ],
    }
