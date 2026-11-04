"""自動生成。単一遷移の寄与のみ。真正sourceの検証は呼出側。"""

import re

SOURCE_MODEL_HASH = (
    "sha256:db0c52f2df92ddd76a9681a940e1bae83f29fb7ff7f9e988b23a76cd5b52b40d"
)
if __name__ != "__pitchlog_generated_wrapper__":
    raise ImportError("生成targetは登録wrapper経由だけです")


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


def _p(owner, path):
    """生成された型検証・有限寄与処理。"""
    for part in path.split("."):
        if owner is None:
            return None
        if type(owner) is not dict or part not in owner:
            raise ValueError("閉入力のfieldが不足しています")
        owner = owner[part]
    return owner


def _n(value):
    """生成された型検証・有限寄与処理。"""
    return parse_count(value)


def _check(value, kind, nullable, minimum=None, maximum=None, allowed=None):
    """生成された型検証・有限寄与処理。"""
    if value is None and nullable:
        return
    if allowed is not None and value not in allowed:
        raise ValueError("未知のenum値です")
    if kind == "integer":
        if type(value) is str and maximum is not None and (len(value) > len(maximum)):
            raise ValueError("既有限整数fieldの変換前上限違反")
        number = _n(value)
        if minimum is not None and number < _n(minimum):
            raise ValueError("整数範囲の下限違反")
        if maximum is not None and number > _n(maximum):
            raise ValueError("整数範囲の上限違反")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError("booleanが必要です")
    elif kind == "string":
        if type(value) is not str:
            raise ValueError("文字列が必要です")
    else:
        raise ValueError("未知の入力型です")


def _append_credit(credits, player, amount):
    """生成された型検証・有限寄与処理。"""
    for credit in credits:
        if credit["player_id"] == player:
            credit["quantity"] = add_counts(credit["quantity"], amount)
            return
    credits.append({"player_id": player, "quantity": format_count(amount)})


def _zero():
    """生成された型検証・有限寄与処理。"""
    return {
        "state": "available",
        "value": "0",
        "display": "0",
        "reason": None,
        "credits": [],
    }


def _missing(reason="MISSING_OBSERVATION"):
    """生成された型検証・有限寄与処理。"""
    return {
        "state": "source_unavailable",
        "value": None,
        "display": None,
        "reason": reason,
        "credits": [],
    }


def add_counts(left, right):
    """生成された整数add primitive（全イベント畳込み入口ではない）。"""
    return format_count(_n(left) + _n(right))


def _pitchlog_generated(event):
    """正規providerが検証した単一遷移を受ける。認可を代行しない。"""
    record = _p(event, "stat_flags")
    if (
        type(record) is not dict
        or len(record) != 23
        or any(
            (
                key not in record
                for key in (
                    "投球回算入アウト",
                    "投球数",
                    "奪三振",
                    "与四球",
                    "与死球",
                    "被安打",
                    "被本塁打",
                    "失点",
                    "失策",
                    "打席",
                    "打数",
                    "安打",
                    "本塁打",
                    "塁打",
                    "犠打",
                    "犠飛",
                    "四球",
                    "死球",
                    "三振",
                    "打撃妨害出塁",
                    "走塁妨害出塁",
                    "得点",
                    "打点",
                )
            )
        )
    ):
        raise ValueError("閉recordの未知/不足fieldです")
    _check(
        _p(event, "event_kind"),
        "string",
        False,
        None,
        None,
        ["pitch", "non_pitch", "control"],
    )
    _check(
        _p(event, "source.lifecycle"),
        "string",
        False,
        None,
        None,
        ["effective", "replaced", "retired", "tombstone", "audit_control"],
    )
    _check(_p(event, "source.source_event_id"), "string", False, None, None, None)
    _check(_p(event, "pa.ended_here"), "boolean", False, None, None, None)
    _check(_p(event, "pa.pa_id"), "string", True, None, None, None)
    _check(_p(event, "pa.ordinal_for_batter"), "string", True, None, None, None)
    _check(
        _p(event, "pa.hit_kind"),
        "string",
        False,
        None,
        None,
        ["none", "single", "double", "triple", "home_run"],
    )
    _check(_p(event, "pa.result_display"), "string", True, None, None, None)
    _check(_p(event, "pa.reached_by"), "string", False, None, None, None)
    _check(_p(event, "before.inning"), "string", False, None, None, None)
    _check(_p(event, "before.half"), "string", False, None, None, None)
    _check(_p(event, "out_effect.effective_count"), "integer", True, "0", "3", None)
    _check(_p(event, "stat_flags.投球回算入アウト"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.投球数"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.奪三振"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.与四球"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.与死球"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.被安打"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.被本塁打"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.失点"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.失策"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.打席"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.打数"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.安打"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.本塁打"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.塁打"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.犠打"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.犠飛"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.四球"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.死球"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.三振"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.打撃妨害出塁"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.走塁妨害出塁"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.得点"), "boolean", False, None, None, None)
    _check(_p(event, "stat_flags.打点"), "boolean", False, None, None, None)
    _check(
        _p(event, "completeness.pa"),
        "string",
        False,
        None,
        None,
        ["complete", "unavailable"],
    )
    _check(
        _p(event, "completeness.participants"),
        "string",
        False,
        None,
        None,
        ["complete", "unavailable"],
    )
    _check(
        _p(event, "completeness.outs"),
        "string",
        False,
        None,
        None,
        ["complete", "unavailable"],
    )
    _check(
        _p(event, "completeness.runs_rbi"),
        "string",
        False,
        None,
        None,
        ["complete", "unavailable"],
    )
    _check(
        _p(event, "completeness.steals"),
        "string",
        False,
        None,
        None,
        ["complete", "unavailable"],
    )
    _check(
        _p(event, "participants.actual_pitcher_id"), "string", False, None, None, None
    )
    _check(
        _p(event, "participants.actual_batter_id"), "string", False, None, None, None
    )
    _check(
        _p(event, "participants.credited_batter_id"), "string", True, None, None, None
    )
    _check(
        _p(event, "participants.strikeout_pitcher_id"), "string", True, None, None, None
    )
    _check(_p(event, "participants.walk_pitcher_id"), "string", True, None, None, None)
    _check(_p(event, "participants.hbp_pitcher_id"), "string", True, None, None, None)
    _check(_p(event, "participants.hit_pitcher_id"), "string", True, None, None, None)
    _check(
        _p(event, "participants.home_run_pitcher_id"), "string", True, None, None, None
    )
    _check(_p(event, "participants.outs_pitcher_id"), "string", True, None, None, None)
    _check(_p(event, "participants.error_fielder_id"), "string", True, None, None, None)
    collection = _p(event, "runner_scores")
    if collection is not None:
        if type(collection) is not list or len(collection) > 4:
            raise ValueError("遷移内collectionの有限上限が不正です")
        for item in collection:
            _check(_p(item, "runner_id"), "string", False)
            _check(_p(item, "responsible_pitcher_id"), "string", False)
            _check(_p(item, "valid_run"), "boolean", False)
            _check(_p(item, "rbi_credited"), "boolean", False)
            _check(_p(item, "rbi_batter_id"), "string", True)
            _check(_p(item, "rbi_branch"), "string", True)
    collection = _p(event, "steal_attempts")
    if collection is not None:
        if type(collection) is not list or len(collection) > 3:
            raise ValueError("遷移内collectionの有限上限が不正です")
        for item in collection:
            _check(_p(item, "runner_id"), "string", False)
            _check(_p(item, "attempted"), "boolean", False)
            _check(_p(item, "successful"), "boolean", False)
    metrics = {
        name: _zero()
        for name in [
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
        ]
    }
    selected = _p(event, "source.lifecycle") == "effective"
    if selected:
        if not _p(event, "completeness.participants") == "complete":
            metrics["pitch_count"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "event_kind") == "pitch" and _p(event, "stat_flags.投球数"):
                amount = _n(1)
                player = _p(event, "participants.actual_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["pitch_count"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["pa"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.打席"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["pa"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["ab"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.打数"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["ab"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["h"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.安打"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["h"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["hr"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.本塁打"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["hr"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["bb"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.四球"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["bb"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["hbp"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.死球"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["hbp"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["k"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.三振"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["k"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["sh"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.犠打"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["sh"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["sf"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.犠飛"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["sf"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["catcher_interference_reached"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.打撃妨害出塁"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["catcher_interference_reached"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["runner_interference_reached"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.走塁妨害出塁"):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["runner_interference_reached"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["doubles"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if (
                _p(event, "pa.ended_here")
                and _p(event, "stat_flags.安打")
                and (_p(event, "pa.hit_kind") == "double")
            ):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["doubles"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["triples"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if (
                _p(event, "pa.ended_here")
                and _p(event, "stat_flags.安打")
                and (_p(event, "pa.hit_kind") == "triple")
            ):
                amount = _n(1)
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["triples"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.pa") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["total_bases"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "pa.ended_here") and _p(event, "stat_flags.塁打"):
                amount = _n(
                    {"none": 0, "single": 1, "double": 2, "triple": 3, "home_run": 4}[
                        _p(event, "pa.hit_kind")
                    ]
                )
                player = _p(event, "participants.credited_batter_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["total_bases"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.runs_rbi") == "complete":
            metrics["runs"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            collection = _p(event, "runner_scores")
            if collection is None:
                missing = True
            else:
                for item in collection:
                    if _p(event, "stat_flags.得点") and _p(item, "valid_run"):
                        amount = _n(1)
                        player = _p(item, "runner_id")
                        if amount and player is None:
                            missing = True
                        elif amount:
                            quantity += amount
                            _append_credit(credits, player, amount)
            metrics["runs"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.runs_rbi") == "complete":
            metrics["rbi"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            collection = _p(event, "runner_scores")
            if collection is None:
                missing = True
            else:
                for item in collection:
                    if (
                        _p(event, "stat_flags.打点")
                        and _p(item, "valid_run")
                        and _p(item, "rbi_credited")
                    ):
                        amount = _n(1)
                        player = _p(item, "rbi_batter_id")
                        if amount and player is None:
                            missing = True
                        elif amount:
                            quantity += amount
                            _append_credit(credits, player, amount)
            metrics["rbi"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.steals") == "complete":
            metrics["stolen_bases"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            collection = _p(event, "steal_attempts")
            if collection is None:
                missing = True
            else:
                for item in collection:
                    if _p(item, "attempted") and _p(item, "successful"):
                        amount = _n(1)
                        player = _p(item, "runner_id")
                        if amount and player is None:
                            missing = True
                        elif amount:
                            quantity += amount
                            _append_credit(credits, player, amount)
            metrics["stolen_bases"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not (
            _p(event, "completeness.outs") == "complete"
            and _p(event, "completeness.participants") == "complete"
        ):
            metrics["pitching_outs"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.投球回算入アウト"):
                amount = _n(_n(_p(event, "out_effect.effective_count")))
                player = _p(event, "participants.outs_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["pitching_outs"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.participants") == "complete":
            metrics["pitcher_k"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.奪三振"):
                amount = _n(1)
                player = _p(event, "participants.strikeout_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["pitcher_k"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.participants") == "complete":
            metrics["pitcher_bb"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.与四球"):
                amount = _n(1)
                player = _p(event, "participants.walk_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["pitcher_bb"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.participants") == "complete":
            metrics["pitcher_hbp"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.与死球"):
                amount = _n(1)
                player = _p(event, "participants.hbp_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["pitcher_hbp"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.participants") == "complete":
            metrics["hits_allowed"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.被安打"):
                amount = _n(1)
                player = _p(event, "participants.hit_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["hits_allowed"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.participants") == "complete":
            metrics["home_runs_allowed"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.被本塁打"):
                amount = _n(1)
                player = _p(event, "participants.home_run_pitcher_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["home_runs_allowed"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.participants") == "complete":
            metrics["fielding_errors"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            if _p(event, "stat_flags.失策"):
                amount = _n(1)
                player = _p(event, "participants.error_fielder_id")
                if amount and player is None:
                    missing = True
                elif amount:
                    quantity += amount
                    _append_credit(credits, player, amount)
            metrics["fielding_errors"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
        if not _p(event, "completeness.runs_rbi") == "complete":
            metrics["runs_allowed"] = _missing()
        else:
            quantity = 0
            credits = []
            missing = False
            collection = _p(event, "runner_scores")
            if collection is None:
                missing = True
            else:
                for item in collection:
                    if _p(event, "stat_flags.失点") and _p(item, "valid_run"):
                        amount = _n(1)
                        player = _p(item, "responsible_pitcher_id")
                        if amount and player is None:
                            missing = True
                        elif amount:
                            quantity += amount
                            _append_credit(credits, player, amount)
            metrics["runs_allowed"] = (
                _missing("MISSING_ATTRIBUTION")
                if missing
                else {
                    "state": "available",
                    "value": format_count(quantity),
                    "display": format_count(quantity),
                    "reason": None,
                    "credits": credits,
                }
            )
    pa_row = None
    if selected and (
        _p(event, "pa.ended_here") and _p(event, "completeness.pa") == "complete"
    ):
        pa_row = {
            "pa_id": _p(event, "pa.pa_id"),
            "batter_id": _p(event, "participants.credited_batter_id"),
            "ordinal_for_batter": _p(event, "pa.ordinal_for_batter"),
            "inning": _p(event, "before.inning"),
            "half": _p(event, "before.half"),
            "result_display": _p(event, "pa.result_display"),
            "counts_as_ab": _p(event, "stat_flags.打数"),
            "hit_kind": _p(event, "pa.hit_kind"),
            "reached_by": _p(event, "pa.reached_by"),
        }
        pa_row["rbi"] = metrics["rbi"]["value"]
        pa_row["rbi_state"] = metrics["rbi"]["state"]
    return {
        "metrics": metrics,
        "pa_row": pa_row,
        "source_event_id": _p(event, "source.source_event_id"),
        "selected": selected,
        "pending": {
            "named_category": {
                "state": "decision_pending",
                "decision_id": "D02",
                "value": None,
            },
            "appearances": {
                "state": "decision_pending",
                "decision_id": "D03",
                "value": None,
            },
            "batters_faced": {
                "state": "decision_pending",
                "decision_id": "D04",
                "value": None,
            },
            "ops": {"state": "decision_pending", "decision_id": "D05", "value": None},
        },
    }
