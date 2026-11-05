"""自動生成。単一遷移の寄与のみ。真正sourceの検証は呼出側。"""

import re

SOURCE_MODEL_HASH = (
    "sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d"
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


class MissingProjectionField(ValueError):
    """有限射影で真正観測がまだ供給されないfield。"""


def _p(owner, path):
    """生成された型検証・有限寄与処理。"""
    for part in path.split("."):
        if owner is None:
            return None
        if type(owner) is not dict:
            raise ValueError("閉入力の親型が不正です")
        if part not in owner:
            raise MissingProjectionField("閉入力のfieldが不足しています")
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


def _checked_ref(owner, path, kind, nullable, minimum, maximum, allowed):
    """生成された型検証・有限寄与処理。"""
    value = _p(owner, path)
    _check(value, kind, nullable, minimum, maximum, allowed)
    return value


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


def _pitchlog_generated(event, requested_metrics=None):
    """正規providerが検証した単一遷移を受ける。認可を代行しない。"""
    known_metrics = [
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
    if requested_metrics is not None:
        if type(requested_metrics) not in (list, tuple) or len(requested_metrics) > 26:
            raise ValueError("primitive射影の有限型違い")
        if any(
            (type(x) is not str or x not in known_metrics for x in requested_metrics)
        ):
            raise ValueError("未知primitive射影")
        if len(set(requested_metrics)) != len(requested_metrics):
            raise ValueError("primitive射影の重複")
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
    if requested_metrics is None:
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
        _check(
            _p(event, "stat_flags.投球回算入アウト"), "boolean", False, None, None, None
        )
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
            _p(event, "participants.actual_pitcher_id"),
            "string",
            False,
            None,
            None,
            None,
        )
        _check(
            _p(event, "participants.actual_batter_id"),
            "string",
            False,
            None,
            None,
            None,
        )
        _check(
            _p(event, "participants.credited_batter_id"),
            "string",
            True,
            None,
            None,
            None,
        )
        _check(
            _p(event, "participants.strikeout_pitcher_id"),
            "string",
            True,
            None,
            None,
            None,
        )
        _check(
            _p(event, "participants.walk_pitcher_id"), "string", True, None, None, None
        )
        _check(
            _p(event, "participants.hbp_pitcher_id"), "string", True, None, None, None
        )
        _check(
            _p(event, "participants.hit_pitcher_id"), "string", True, None, None, None
        )
        _check(
            _p(event, "participants.home_run_pitcher_id"),
            "string",
            True,
            None,
            None,
            None,
        )
        _check(
            _p(event, "participants.outs_pitcher_id"), "string", True, None, None, None
        )
        _check(
            _p(event, "participants.error_fielder_id"), "string", True, None, None, None
        )
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
        if requested_metrics is None or name in requested_metrics
    }
    selected = (
        _checked_ref(
            event,
            "source.lifecycle",
            "string",
            False,
            None,
            None,
            ["effective", "replaced", "retired", "tombstone", "audit_control"],
        )
        == "effective"
    )
    if selected:
        if requested_metrics is None or "pitch_count" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["pitch_count"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event,
                        "event_kind",
                        "string",
                        False,
                        None,
                        None,
                        ["pitch", "non_pitch", "control"],
                    ) == "pitch" and _checked_ref(
                        event, "stat_flags.投球数", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.actual_pitcher_id",
                            "string",
                            False,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["pitch_count"] = _missing()
        if requested_metrics is None or "pa" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["pa"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.打席", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["pa"] = _missing()
        if requested_metrics is None or "ab" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["ab"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.打数", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["ab"] = _missing()
        if requested_metrics is None or "h" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["h"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.安打", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["h"] = _missing()
        if requested_metrics is None or "hr" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["hr"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.本塁打", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["hr"] = _missing()
        if requested_metrics is None or "bb" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["bb"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.四球", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["bb"] = _missing()
        if requested_metrics is None or "hbp" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["hbp"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.死球", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["hbp"] = _missing()
        if requested_metrics is None or "k" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["k"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.三振", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["k"] = _missing()
        if requested_metrics is None or "sh" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["sh"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.犠打", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["sh"] = _missing()
        if requested_metrics is None or "sf" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["sf"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.犠飛", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["sf"] = _missing()
        if (
            requested_metrics is None
            or "catcher_interference_reached" in requested_metrics
        ):
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["catcher_interference_reached"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event,
                        "stat_flags.打撃妨害出塁",
                        "boolean",
                        False,
                        None,
                        None,
                        None,
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["catcher_interference_reached"] = _missing()
        if (
            requested_metrics is None
            or "runner_interference_reached" in requested_metrics
        ):
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["runner_interference_reached"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event,
                        "stat_flags.走塁妨害出塁",
                        "boolean",
                        False,
                        None,
                        None,
                        None,
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["runner_interference_reached"] = _missing()
        if requested_metrics is None or "doubles" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["doubles"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if (
                        _checked_ref(
                            event, "pa.ended_here", "boolean", False, None, None, None
                        )
                        and _checked_ref(
                            event, "stat_flags.安打", "boolean", False, None, None, None
                        )
                        and (
                            _checked_ref(
                                event,
                                "pa.hit_kind",
                                "string",
                                False,
                                None,
                                None,
                                ["none", "single", "double", "triple", "home_run"],
                            )
                            == "double"
                        )
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["doubles"] = _missing()
        if requested_metrics is None or "triples" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["triples"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if (
                        _checked_ref(
                            event, "pa.ended_here", "boolean", False, None, None, None
                        )
                        and _checked_ref(
                            event, "stat_flags.安打", "boolean", False, None, None, None
                        )
                        and (
                            _checked_ref(
                                event,
                                "pa.hit_kind",
                                "string",
                                False,
                                None,
                                None,
                                ["none", "single", "double", "triple", "home_run"],
                            )
                            == "triple"
                        )
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["triples"] = _missing()
        if requested_metrics is None or "total_bases" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.pa",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["total_bases"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "pa.ended_here", "boolean", False, None, None, None
                    ) and _checked_ref(
                        event, "stat_flags.塁打", "boolean", False, None, None, None
                    ):
                        amount = _n(
                            {
                                "none": 0,
                                "single": 1,
                                "double": 2,
                                "triple": 3,
                                "home_run": 4,
                            }[
                                _checked_ref(
                                    event,
                                    "pa.hit_kind",
                                    "string",
                                    False,
                                    None,
                                    None,
                                    ["none", "single", "double", "triple", "home_run"],
                                )
                            ]
                        )
                        player = _checked_ref(
                            event,
                            "participants.credited_batter_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["total_bases"] = _missing()
        if requested_metrics is None or "runs" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.runs_rbi",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["runs"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    collection = _p(event, "runner_scores")
                    if collection is None:
                        missing = True
                    else:
                        if type(collection) is not list or len(collection) > 4:
                            raise ValueError("遷移内collectionの有限上限違反")
                        for item in collection:
                            if _checked_ref(
                                event,
                                "stat_flags.得点",
                                "boolean",
                                False,
                                None,
                                None,
                                None,
                            ) and _checked_ref(
                                item, "valid_run", "boolean", False, None, None, None
                            ):
                                amount = _n(1)
                                player = _checked_ref(
                                    item, "runner_id", "string", False, None, None, None
                                )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["runs"] = _missing()
        if requested_metrics is None or "rbi" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.runs_rbi",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["rbi"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    collection = _p(event, "runner_scores")
                    if collection is None:
                        missing = True
                    else:
                        if type(collection) is not list or len(collection) > 4:
                            raise ValueError("遷移内collectionの有限上限違反")
                        for item in collection:
                            if (
                                _checked_ref(
                                    event,
                                    "stat_flags.打点",
                                    "boolean",
                                    False,
                                    None,
                                    None,
                                    None,
                                )
                                and _checked_ref(
                                    item,
                                    "valid_run",
                                    "boolean",
                                    False,
                                    None,
                                    None,
                                    None,
                                )
                                and _checked_ref(
                                    item,
                                    "rbi_credited",
                                    "boolean",
                                    False,
                                    None,
                                    None,
                                    None,
                                )
                            ):
                                amount = _n(1)
                                player = _checked_ref(
                                    item,
                                    "rbi_batter_id",
                                    "string",
                                    True,
                                    None,
                                    None,
                                    None,
                                )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["rbi"] = _missing()
        if requested_metrics is None or "stolen_bases" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.steals",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["stolen_bases"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    collection = _p(event, "steal_attempts")
                    if collection is None:
                        missing = True
                    else:
                        if type(collection) is not list or len(collection) > 3:
                            raise ValueError("遷移内collectionの有限上限違反")
                        for item in collection:
                            if _checked_ref(
                                item, "attempted", "boolean", False, None, None, None
                            ) and _checked_ref(
                                item, "successful", "boolean", False, None, None, None
                            ):
                                amount = _n(1)
                                player = _checked_ref(
                                    item, "runner_id", "string", False, None, None, None
                                )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["stolen_bases"] = _missing()
        if requested_metrics is None or "pitching_outs" in requested_metrics:
            try:
                if not (
                    _checked_ref(
                        event,
                        "completeness.outs",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                    and _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["pitching_outs"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event,
                        "stat_flags.投球回算入アウト",
                        "boolean",
                        False,
                        None,
                        None,
                        None,
                    ):
                        amount = _n(
                            _n(
                                _checked_ref(
                                    event,
                                    "out_effect.effective_count",
                                    "integer",
                                    True,
                                    "0",
                                    "3",
                                    None,
                                )
                            )
                        )
                        player = _checked_ref(
                            event,
                            "participants.outs_pitcher_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["pitching_outs"] = _missing()
        if requested_metrics is None or "pitcher_k" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["pitcher_k"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "stat_flags.奪三振", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.strikeout_pitcher_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["pitcher_k"] = _missing()
        if requested_metrics is None or "pitcher_bb" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["pitcher_bb"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "stat_flags.与四球", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.walk_pitcher_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["pitcher_bb"] = _missing()
        if requested_metrics is None or "pitcher_hbp" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["pitcher_hbp"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "stat_flags.与死球", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.hbp_pitcher_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["pitcher_hbp"] = _missing()
        if requested_metrics is None or "hits_allowed" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["hits_allowed"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "stat_flags.被安打", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.hit_pitcher_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["hits_allowed"] = _missing()
        if requested_metrics is None or "home_runs_allowed" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["home_runs_allowed"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "stat_flags.被本塁打", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.home_run_pitcher_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["home_runs_allowed"] = _missing()
        if requested_metrics is None or "fielding_errors" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.participants",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["fielding_errors"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    if _checked_ref(
                        event, "stat_flags.失策", "boolean", False, None, None, None
                    ):
                        amount = _n(1)
                        player = _checked_ref(
                            event,
                            "participants.error_fielder_id",
                            "string",
                            True,
                            None,
                            None,
                            None,
                        )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["fielding_errors"] = _missing()
        if requested_metrics is None or "runs_allowed" in requested_metrics:
            try:
                if (
                    not _checked_ref(
                        event,
                        "completeness.runs_rbi",
                        "string",
                        False,
                        None,
                        None,
                        ["complete", "unavailable"],
                    )
                    == "complete"
                ):
                    metrics["runs_allowed"] = _missing()
                else:
                    quantity = 0
                    credits = []
                    missing = False
                    collection = _p(event, "runner_scores")
                    if collection is None:
                        missing = True
                    else:
                        if type(collection) is not list or len(collection) > 4:
                            raise ValueError("遷移内collectionの有限上限違反")
                        for item in collection:
                            if _checked_ref(
                                event,
                                "stat_flags.失点",
                                "boolean",
                                False,
                                None,
                                None,
                                None,
                            ) and _checked_ref(
                                item, "valid_run", "boolean", False, None, None, None
                            ):
                                amount = _n(1)
                                player = _checked_ref(
                                    item,
                                    "responsible_pitcher_id",
                                    "string",
                                    False,
                                    None,
                                    None,
                                    None,
                                )
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
            except MissingProjectionField:
                if requested_metrics is None:
                    raise
                metrics["runs_allowed"] = _missing()
    pa_row = None
    if (
        requested_metrics is None
        and selected
        and (
            _checked_ref(event, "pa.ended_here", "boolean", False, None, None, None)
            and _checked_ref(
                event,
                "completeness.pa",
                "string",
                False,
                None,
                None,
                ["complete", "unavailable"],
            )
            == "complete"
        )
    ):
        pa_row = {
            "pa_id": _checked_ref(event, "pa.pa_id", "string", True, None, None, None),
            "batter_id": _checked_ref(
                event,
                "participants.credited_batter_id",
                "string",
                True,
                None,
                None,
                None,
            ),
            "ordinal_for_batter": _checked_ref(
                event, "pa.ordinal_for_batter", "string", True, None, None, None
            ),
            "inning": _checked_ref(
                event, "before.inning", "string", False, None, None, None
            ),
            "half": _checked_ref(
                event, "before.half", "string", False, None, None, None
            ),
            "result_display": _checked_ref(
                event, "pa.result_display", "string", True, None, None, None
            ),
            "counts_as_ab": _checked_ref(
                event, "stat_flags.打数", "boolean", False, None, None, None
            ),
            "hit_kind": _checked_ref(
                event,
                "pa.hit_kind",
                "string",
                False,
                None,
                None,
                ["none", "single", "double", "triple", "home_run"],
            ),
            "reached_by": _checked_ref(
                event, "pa.reached_by", "string", False, None, None, None
            ),
        }
        pa_row["rbi"] = metrics["rbi"]["value"]
        pa_row["rbi_state"] = metrics["rbi"]["state"]
    return {
        "metrics": metrics,
        "pa_row": pa_row,
        "source_event_id": _p(event, "source.source_event_id"),
        "selected": selected,
        "decisions": {
            "D02": {
                "decision_id": "D02",
                "decision_state": "adopted",
                "choice": "A",
                "implementation_state": "available",
            },
            "D03": {
                "decision_id": "D03",
                "decision_state": "adopted",
                "choice": "A",
                "implementation_state": "pending",
                "source_state": "not_evaluated",
                "value": None,
            },
            "D04": {
                "decision_id": "D04",
                "decision_state": "adopted",
                "choice": "A",
                "implementation_state": "pending",
                "source_state": "not_evaluated",
                "value": None,
            },
            "D05": {
                "decision_id": "D05",
                "decision_state": "adopted",
                "choice": "A",
                "implementation_state": "available",
            },
        },
    }


def _rate_inputs(metrics, names):
    """生成された型検証・有限寄与処理。"""
    if type(metrics) is not dict or set(metrics) != set(names):
        raise ValueError("派生率の十分統計は閉26項目が必要です")
    values = {}
    for key in names:
        row = metrics[key]
        if type(row) is dict:
            if set(row) != {"state", "value", "display", "reason"}:
                raise ValueError("十分統計の閉型が不正です")
            if row["state"] == "source_unavailable":
                if (
                    row["value"] is not None
                    or row["display"] is not None
                    or row["reason"]
                    not in (
                        "MISSING_OBSERVATION",
                        "MISSING_ATTRIBUTION",
                        "UNSUPPORTED_SOURCE_VARIANT",
                    )
                ):
                    raise ValueError("不足観測の型が不正です")
                values[key] = None
                continue
            if (
                row["state"] != "available"
                or row["value"] is None
                or row["reason"] is not None
                or (row["display"] != row["value"])
            ):
                raise ValueError("十分統計の状態が不正です")
            row = row["value"]
        if row is None:
            values[key] = None
        elif type(row) is str:
            values[key] = parse_count(row)
        else:
            raise ValueError("十分統計は正準整数文字列です")
    return values


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


def _rate_reason(metrics, dependencies):
    """生成された型検証・有限寄与処理。"""
    for key in dependencies:
        value = metrics[key]
        if type(value) is dict and value["state"] == "source_unavailable":
            return value["reason"]
    return "MISSING_OBSERVATION"


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


GAME_TYPE_SCOPES = {
    "official": ["game_official", "game_semi_official"],
    "practice": ["game_open", "game_intrasquad", "game_other"],
    "all": [
        "game_official",
        "game_semi_official",
        "game_open",
        "game_intrasquad",
        "game_other",
    ],
}


def select_game_type_keys(named_category="all", raw_game_type_keys=None):
    """生成された型検証・有限寄与処理。"""
    if type(named_category) is not str or named_category not in GAME_TYPE_SCOPES:
        raise ValueError("未知のnamed categoryです")
    keys = list(GAME_TYPE_SCOPES[named_category])
    if raw_game_type_keys is not None and (
        type(raw_game_type_keys) is not list
        or any((type(x) is not str for x in raw_game_type_keys))
        or raw_game_type_keys != keys
    ):
        raise ValueError("named/raw集合が不一致です")
    return keys


def decision_metadata():
    """生成された型検証・有限寄与処理。"""
    return {
        "D02": {
            "decision_id": "D02",
            "decision_state": "adopted",
            "choice": "A",
            "implementation_state": "available",
        },
        "D03": {
            "decision_id": "D03",
            "decision_state": "adopted",
            "choice": "A",
            "implementation_state": "pending",
            "source_state": "not_evaluated",
            "value": None,
        },
        "D04": {
            "decision_id": "D04",
            "decision_state": "adopted",
            "choice": "A",
            "implementation_state": "pending",
            "source_state": "not_evaluated",
            "value": None,
        },
        "D05": {
            "decision_id": "D05",
            "decision_state": "adopted",
            "choice": "A",
            "implementation_state": "available",
        },
    }


def derive_rates(metrics):
    """生成された型検証・有限寄与処理。"""
    values = _rate_inputs(
        metrics,
        (
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
        ),
    )
    results = {}
    parts_0 = {
        "obp": _ratio(
            _rate_add(values["h"], values["bb"], values["hbp"]),
            _rate_add(values["ab"], values["bb"], values["hbp"], values["sf"]),
        ),
        "slg": _ratio(values["total_bases"], values["ab"]),
    }
    results["ops"] = _rate_result(
        _ratio_add(parts_0["obp"], parts_0["slg"]),
        parts_0,
        {
            "scale": 3,
            "rounding": "half-up",
            "leadingZero": True,
            "zeroDivisionGlyph": "−",
            "denominators": [
                {"component": "obp", "prefix": "出塁率分母", "suffix": "打席"},
                {"component": "slg", "prefix": "長打率分母", "suffix": "打数"},
            ],
        },
        _rate_reason(metrics, ("h", "bb", "hbp", "ab", "sf", "total_bases")),
    )
    return results
