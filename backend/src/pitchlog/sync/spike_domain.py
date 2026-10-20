"""spike 用のドメイン計算（T1 状態遷移・T2 試合終了）。

製品の単一成果物（`frontend/public/domain/pitchlog-domain.js`）は、変換可能な
構文を `frontend/scripts/domain-checks/policy.ts` で限定している。T1/T2 の
計算はその限定集合（要素アクセス・Set・分割代入・複合代入を含まない）では
まだ表現できないため、この spike では同じ規則を Python 側の 1 実装として
置き、1 球保存の経路へ接続する。規則の正本は要件書 付録E/E-1・E-2・
付録A・付録F-1・FR-014・DRAW-01〜03 で、P-6 の独立導出
（`.devsetup/p6/derive.py`・`t2_validate.py`）と同じ意味を持つ。

数値は Python の int で扱う。成果物の境界（十進文字列・bigint）へ移すのは
成果物側の課題で、この spike の対象外（README に申し送り）。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# 結果IDごとの遷移。pa = plateAppearanceEnded、batter = (kind, base)、
# outs = outEffect.count と targets（起点塁 or "batter"）、
# adv = 進塁の型（force/plus1_all/explicit/hold_all）、count = カウントの増減。
RULES: dict[str, dict[str, Any]] = {
    "batting-result.called-pitch": {
        "pa": False, "batter": ("continue", None), "outs": 0, "targets": [],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("delta", 1), "balls": ("unchanged", None)},
    },
    "batting-result.swinging-strike": {
        "pa": False, "batter": ("continue", None), "outs": 0, "targets": [],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("delta", 1), "balls": ("unchanged", None)},
    },
    "batting-result.foul": {
        "pa": False, "batter": ("continue", None), "outs": 0, "targets": [],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("delta", 1), "balls": ("unchanged", None)},
    },
    "batting-result.ball": {
        "pa": False, "batter": ("continue", None), "outs": 0, "targets": [],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("delta", 1)},
    },
    "batting-result.called-strikeout": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.swinging-strikeout": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.dropped-third-strike": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.k3": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.strikeout-double-play": {
        "pa": True, "batter": ("out", None), "outs": 2, "targets": ["batter", 1],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.walk": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.hit-by-pitch": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.intentional-walk": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.single": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 1, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.double": {
        "pa": True, "batter": ("reach", 2), "outs": 0, "targets": [],
        "adv": "force", "step": 2, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.triple": {
        "pa": True, "batter": ("reach", 3), "outs": 0, "targets": [],
        "adv": "force", "step": 3, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.home-run": {
        "pa": True, "batter": ("score", None), "outs": 0, "targets": [],
        "adv": "explicit", "step": 0, "explicit": {1: 4, 2: 4, 3: 4},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.batted-out": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.foul-fly": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.double-play": {
        "pa": True, "batter": ("out", None), "outs": 2, "targets": ["batter", 1],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.line-double-play": {
        "pa": True, "batter": ("out", None), "outs": 2, "targets": ["batter", 1],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.batted-reach": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.error": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.fielders-choice": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.sacrifice-bunt": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "plus1_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.sacrifice-fly": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "explicit", "step": 0, "explicit": {1: None, 2: None, 3: 4},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "batting-result.sacrifice-bunt-error": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "secondary-result.passed-ball": {
        "pa": False, "batter": ("not-applicable", None), "outs": 0, "targets": [],
        "adv": "plus1_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "secondary-result.wild-pitch": {
        "pa": False, "batter": ("not-applicable", None), "outs": 0, "targets": [],
        "adv": "plus1_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "secondary-result.balk": {
        "pa": False, "batter": ("not-applicable", None), "outs": 0, "targets": [],
        "adv": "plus1_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "secondary-result.offensive-interference": {
        "pa": True, "batter": ("out", None), "outs": 1, "targets": ["batter"],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "secondary-result.batting-interference": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "secondary-result.obstruction": {
        "pa": True, "batter": ("reach", 1), "outs": 0, "targets": [],
        "adv": "force", "step": 0, "explicit": {},
        "count": {"strikes": ("reset", None), "balls": ("reset", None)},
    },
    "secondary-result.pitch-clock-violation": {
        "pa": False, "batter": ("continue", None), "outs": 0, "targets": [],
        "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("delta", 1)},
    },
    "strategy-category.steal": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "explicit", "step": 0,
        "explicit": {1: 2, 2: None, 3: None},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "strategy-category.bunt": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "strategy-category.hit-and-run": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "explicit", "step": 0,
        "explicit": {1: 2, 2: None, 3: None},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "pitcher-pickoff-destination.first": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "pitcher-pickoff-destination.second": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "pitcher-pickoff-destination.third": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "catcher-pickoff-destination.first": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "catcher-pickoff-destination.second": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
    "catcher-pickoff-destination.third": {
        "pa": "not-applicable", "batter": ("not-applicable", None), "outs": 0,
        "targets": [], "adv": "hold_all", "step": 0, "explicit": {},
        "count": {"strikes": ("unchanged", None), "balls": ("unchanged", None)},
    },
}

RUNNERS_TO_SET: dict[str, set[int]] = {
    "empty": set(),
    "first": {1},
    "second": {2},
    "third": {3},
    "first-second": {1, 2},
    "first-third": {1, 3},
    "second-third": {2, 3},
    "loaded": {1, 2, 3},
    "first-second-third": {1, 2, 3},
}

HITS = {
    "batting-result.single",
    "batting-result.double",
    "batting-result.triple",
    "batting-result.home-run",
}
STRIKEOUTS = {
    "batting-result.called-strikeout",
    "batting-result.swinging-strikeout",
    "batting-result.dropped-third-strike",
    "batting-result.k3",
    "batting-result.strikeout-double-play",
}
WALKS = {"batting-result.walk", "batting-result.intentional-walk"}

STAT_FLAGS = (
    "投球回算入アウト", "投球数", "奪三振", "与四球", "与死球", "被安打",
    "被本塁打", "失点", "失策", "打席", "打数", "安打", "本塁打", "塁打",
    "犠打", "犠飛", "四球", "死球", "三振", "打撃妨害出塁", "走塁妨害出塁",
    "得点", "打点",
)

STARTING_STATE_FIELDS: dict[str, Any] = {
    "state.half": "top",
    "state.count.strikes": 0,
    "state.count.balls": 0,
    "state.outs": 0,
    "state.runners": "empty",
    "state.battingOrder": 1,
    "state.tiebreakActive": False,
    "state.gameEnded": False,
    "state.inning": 1,
    "state.score": {"home": 0, "away": 0},
}

STARTING_SCOREBOARD: dict[str, Any] = {
    "inningScores": {"home": 0, "away": 0},
    "hits": 0,
    "errors": 0,
    "strikeouts": 0,
    "walks": 0,
}


def set_to_runners(bases: set[int]) -> str:
    """在塁の集合を `state.runners` の値域へ写す。"""
    key = "".join(str(base) for base in (1, 2, 3) if base in bases)
    return {
        "": "empty", "1": "first", "2": "second", "3": "third",
        "12": "first-second", "13": "first-third", "23": "second-third",
        "123": "loaded",
    }[key]


def advance_plan(
    rule: dict[str, Any], before: set[int], batter_kind: str
) -> dict[int, tuple[str, int | None]]:
    """ADV-01..04: 各起点塁の (modality, destination) を返す。"""
    plan: dict[int, tuple[str, int | None]] = {}
    for base in (1, 2, 3):
        if base not in before:
            plan[base] = ("not-applicable", None)
            continue
        if rule["adv"] == "hold_all":
            plan[base] = ("hold", None)
            continue
        if rule["adv"] == "plus1_all":
            plan[base] = ("optional", min(base + 1, 4))
            continue
        if rule["adv"] == "explicit":
            destination = rule["explicit"].get(base)
            plan[base] = (
                ("hold", None) if destination is None else ("optional", destination)
            )
            continue
        chained = batter_kind == "reach" and all(
            item in before for item in range(1, base + 1)
        )
        if chained:
            plan[base] = ("forced", min(base + max(rule["step"], 1), 4))
        elif rule["step"] > 0:
            plan[base] = ("optional", min(base + rule["step"], 4))
        else:
            plan[base] = ("hold", None)
    return plan


def derive(
    before_fields: dict[str, Any],
    before_scoreboard: dict[str, Any],
    result_id: str,
    pitch_event_kind: str | None = None,
) -> dict[str, Any]:
    """1 球の遷移（5 面・23 フラグ・遷移後の状態）を導出する。

    Args:
        before_fields: 遷移前の `state.*`。
        before_scoreboard: 遷移前のスコアボード。
        result_id: 結果ID（`batting-result.single` など）。
        pitch_event_kind: 毎球入力の種別（投球数フラグの根拠）。

    Returns:
        契約の `expected` と同じ 5 面＋`statFlags` と、`after` を持つ辞書。

    Raises:
        KeyError: 未知の結果ID。
    """
    rule = RULES[result_id]
    before_runners = set(RUNNERS_TO_SET[before_fields["state.runners"]])
    batter_kind, batter_base = rule["batter"]
    plan = advance_plan(rule, before_runners, batter_kind)

    after_runners: set[int] = set()
    scored: list[tuple[str, int | None]] = []
    for base, (_modality, destination) in plan.items():
        if base not in before_runners:
            continue
        if base in rule["targets"]:
            continue
        if destination == 4:
            scored.append(("runner", base))
        elif destination is None:
            after_runners.add(base)
        else:
            after_runners.add(destination)
    if batter_kind == "reach":
        after_runners.add(batter_base)
    if batter_kind == "score":
        scored.append(("batter", None))

    runs = len(scored)
    rbi = 0
    if result_id == "batting-result.home-run":
        rbi = runs
    else:
        for kind, base in scored:
            if result_id in WALKS or result_id == "batting-result.hit-by-pitch":
                forced = (
                    kind == "runner"
                    and base is not None
                    and plan[base][0] == "forced"
                )
                rbi += 1 if forced else 0
            elif result_id in {
                "batting-result.single", "batting-result.double",
                "batting-result.triple", "batting-result.sacrifice-bunt",
                "batting-result.sacrifice-fly", "batting-result.batted-out",
                "batting-result.fielders-choice", "batting-result.batted-reach",
            }:
                rbi += 1
            elif result_id in {
                "batting-result.double-play", "batting-result.line-double-play",
            }:
                rbi += 0
            elif result_id == "batting-result.error":
                rbi += -1

    count = dict(before_fields)
    for side in ("strikes", "balls"):
        kind, value = rule["count"][side]
        key = f"state.count.{side}"
        if kind == "delta":
            count[key] = count[key] + value
        elif kind == "reset":
            count[key] = 0

    outs = before_fields["state.outs"] + rule["outs"]
    half = before_fields["state.half"]
    inning = before_fields["state.inning"]
    if outs >= 3:
        outs = 0
        after_runners = set()
        count["state.count.strikes"] = 0
        count["state.count.balls"] = 0
        if half == "top":
            half = "bottom"
        else:
            half = "top"
            inning = inning + 1

    side = "away" if before_fields["state.half"] == "top" else "home"
    score = dict(before_fields["state.score"])
    score[side] = score[side] + max(runs, 0)
    scoreboard = deepcopy(before_scoreboard)
    scoreboard["inningScores"][side] = scoreboard["inningScores"][side] + max(runs, 0)

    after_fields = {
        "state.half": half,
        "state.count.strikes": count["state.count.strikes"],
        "state.count.balls": count["state.count.balls"],
        "state.outs": outs,
        "state.runners": set_to_runners(after_runners),
        "state.battingOrder": (
            (before_fields["state.battingOrder"] % 9) + 1
            if rule["pa"] is True
            else before_fields["state.battingOrder"]
        ),
        "state.tiebreakActive": before_fields["state.tiebreakActive"],
        "state.gameEnded": before_fields["state.gameEnded"],
        "state.inning": inning,
        "state.score": score,
    }

    flags = {name: False for name in STAT_FLAGS}
    flags["投球数"] = pitch_event_kind == "pitch-event"
    flags["投球回算入アウト"] = rule["outs"] > 0
    flags["打席"] = rule["pa"] is True
    flags["四球"] = result_id in WALKS
    flags["与四球"] = result_id in WALKS
    flags["死球"] = result_id == "batting-result.hit-by-pitch"
    flags["与死球"] = result_id == "batting-result.hit-by-pitch"
    flags["三振"] = result_id in STRIKEOUTS
    flags["奪三振"] = result_id in STRIKEOUTS
    flags["安打"] = result_id in HITS
    flags["被安打"] = result_id in HITS
    flags["本塁打"] = result_id == "batting-result.home-run"
    flags["被本塁打"] = result_id == "batting-result.home-run"
    flags["塁打"] = result_id in HITS
    flags["犠打"] = result_id in {
        "batting-result.sacrifice-bunt", "batting-result.sacrifice-bunt-error",
    }
    flags["犠飛"] = result_id == "batting-result.sacrifice-fly"
    flags["失策"] = result_id in {
        "batting-result.error", "batting-result.sacrifice-bunt-error",
    }
    flags["打撃妨害出塁"] = result_id == "secondary-result.batting-interference"
    flags["走塁妨害出塁"] = result_id == "secondary-result.obstruction"
    flags["得点"] = runs > 0
    flags["失点"] = runs > 0
    flags["打点"] = rbi > 0
    flags["打数"] = flags["打席"] and not (
        flags["四球"] or flags["死球"] or flags["犠打"] or flags["犠飛"]
        or flags["打撃妨害出塁"] or flags["走塁妨害出塁"]
    )

    scoreboard["hits"] = scoreboard["hits"] + (1 if flags["安打"] else 0)
    scoreboard["errors"] = scoreboard["errors"] + (1 if flags["失策"] else 0)
    scoreboard["strikeouts"] = scoreboard["strikeouts"] + (1 if flags["三振"] else 0)
    scoreboard["walks"] = scoreboard["walks"] + (1 if flags["四球"] else 0)

    count_effect: dict[str, dict[str, Any]] = {}
    for side_name in ("strikes", "balls"):
        kind, value = rule["count"][side_name]
        count_effect[side_name] = (
            {"kind": "delta", "value": value} if kind == "delta" else {"kind": kind}
        )

    return {
        "countEffect": count_effect,
        "plateAppearanceEnded": rule["pa"],
        "batterDestination": (
            {"kind": batter_kind, "base": batter_base}
            if batter_kind == "reach"
            else {"kind": batter_kind}
        ),
        "runnerDefaultAdvance": {
            "first": _advance(plan[1]),
            "second": _advance(plan[2]),
            "third": _advance(plan[3]),
        },
        "outEffect": {
            "count": rule["outs"],
            "targets": [
                "batter" if target == "batter" else {"runner": target}
                for target in rule["targets"]
            ],
        },
        "statFlags": flags,
        "after": {"stateFields": after_fields, "scoreboard": scoreboard},
    }


def _advance(item: tuple[str, int | None]) -> dict[str, Any]:
    """進塁計画の 1 塁分を JSON 形へ写す。"""
    modality, destination = item
    return {"modality": modality, "destination": destination}


def fold(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """イベント列（各 payload の resultId）を先頭から畳み込む。

    Args:
        payloads: 受理順のイベント payload。

    Returns:
        現在の state とスコアボード、適用できたイベント数。
    """
    fields = deepcopy(STARTING_STATE_FIELDS)
    scoreboard = deepcopy(STARTING_SCOREBOARD)
    applied = 0
    for payload in payloads:
        result_id = payload.get("resultId")
        if not isinstance(result_id, str) or result_id not in RULES:
            continue
        value = derive(fields, scoreboard, result_id, payload.get("pitchEventKind"))
        fields = value["after"]["stateFields"]
        scoreboard = value["after"]["scoreboard"]
        applied += 1
    return {
        "stateFields": fields,
        "scoreboard": scoreboard,
        "appliedEvents": applied,
    }


def validate_rule(rule: dict[str, Any]) -> list[str]:
    """規則設定の拒否理由を返す（空なら保存可）。

    Args:
        rule: regulationInnings・coldConditions・extensionLimit・tiebreak。

    Returns:
        条文・descriptor の ID 付きの拒否理由。
    """
    reasons: list[str] = []
    regulation = rule["regulationInnings"]
    tiers = rule["coldConditions"]
    limit = rule["extensionLimit"]
    tiebreak = rule["tiebreak"]
    if not (1 <= regulation <= 99):
        reasons.append("adr:D-11(regulationInnings 1..99)")
    if len(tiers) > 16:
        reasons.append("adr:D-11(coldConditions tierCount 0..16)")
    for tier in tiers:
        if not (1 <= tier["pointDifference"] <= 99):
            reasons.append("adr:D-11(coldConditions pointDifference 1..99)")
        if not (1 <= tier["startInning"] <= 99):
            reasons.append("adr:D-11(coldConditions startInning 1..99)")
    if limit is not None and not (1 <= limit <= 99):
        reasons.append("adr:D-11(extensionLimit 1..99)")
    if tiebreak is not None and not (1 <= tiebreak <= 99):
        reasons.append("adr:D-11(tiebreak startInning 1..99)")
    if limit is not None and limit < regulation:
        reasons.append("req:DRAW-01(L<R)")
    if any(tier["pointDifference"] <= 0 for tier in tiers):
        reasons.append("req:DRAW-02(M<=0)")
    if tiebreak is not None:
        if tiebreak <= regulation:
            reasons.append("req:DRAW-03(発動回<=R)")
        if limit is not None and tiebreak > limit:
            reasons.append("req:DRAW-03(発動回>L)")
    return list(dict.fromkeys(reasons))


SCORING_RESULTS = {
    "batting-result.home-run",
    "batting-result.single",
    "batting-result.double",
    "batting-result.triple",
    "batting-result.sacrifice-fly",
}


def decide(inputs: dict[str, Any]) -> dict[str, Any]:
    """確定プレイ後の状態から試合終了の判定を導出する。

    Args:
        inputs: 規則設定・イニング・攻守・点差・イベント（任意）。

    Returns:
        判定（outcome・終了の各フラグ・xMark）。
    """
    regulation = inputs["regulationInnings"]
    limit = inputs["extensionLimit"]
    ended = {
        "endConditionDetected": True,
        "lockFurtherPlayInput": True,
        "promptEndDeclaration": True,
        "automaticallyEndsGame": False,
    }
    proceeding = {
        "endConditionDetected": False,
        "lockFurtherPlayInput": False,
        "promptEndDeclaration": False,
        "automaticallyEndsGame": False,
    }

    if inputs["gameEnded"]:
        return {"outcome": "already-ended", **proceeding, "xMark": "recorded-score"}

    if (
        inputs["satisfiedColdTierCount"] > 0
        and inputs["half"] == "bottom"
        and inputs["scoreDiff"] > 0
    ):
        return {"outcome": "cold-end", **ended, "xMark": "x-mark"}

    if inputs["half"] == "bottom":
        event = inputs.get("event") or {}
        if (
            inputs["inning"] >= regulation
            and inputs["scoreDiff"] > 0
            and event.get("operationKind") == "per-pitch"
            and event.get("kind") == "batting-result"
            and event.get("resultId") in SCORING_RESULTS
        ):
            return {"outcome": "walk-off", **ended, "xMark": "recorded-score"}
        if (
            inputs["inning"] == regulation
            and inputs["scoreDiff"] > 0
            and (limit is None or limit <= regulation)
        ):
            return {"outcome": "normal-end", **ended, "xMark": "x-mark"}

    if inputs["half"] == "top":
        effective = limit if limit is not None else regulation
        if inputs["inning"] == effective + 1:
            if inputs["scoreDiff"] < 0:
                return {"outcome": "normal-end", **ended, "xMark": "recorded-score"}
            if inputs["scoreDiff"] == 0:
                return {"outcome": "limit-draw", **ended, "xMark": "recorded-score"}
        if inputs["inning"] == regulation + 1 and inputs["scoreDiff"] == 0:
            outcome = (
                "tiebreak-continue" if inputs["tiebreakActive"] else "extra-continue"
            )
            return {"outcome": outcome, **proceeding, "xMark": "recorded-score"}

    return {"outcome": "no-decision", **proceeding, "xMark": "recorded-score"}
