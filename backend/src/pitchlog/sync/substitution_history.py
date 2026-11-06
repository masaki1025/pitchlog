"""交代frameをplay原本の間に置き、文脈の隙間を全値で照合する。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pitchlog.domainrt.first_ball_projection import _canonical_json


class SubstitutionHistoryError(ValueError):
    """交代/プレイ文脈の接続が不成立。"""


def _same(left: object, right: object) -> bool:
    """欠落・型・全memberを保持する比較。"""
    return _canonical_json(left) == _canonical_json(right)


def verify_substitution_gaps(
    source: Mapping[str, Any], control_bridges: list[dict] | None = None
) -> None:
    """Play frameを改変せず、交代frameによる全区間の接続を検査する。

    DB原本/世代連鎖/イベント指紋は呼出側が別途照合する。ここでの成功は
    保存資格ではない。
    """
    try:
        content = source["checkpoint"]["content"]
        stack = source["activeStack"]
        substitutions = content.get("substitutionFrames", [])
        if type(stack) is not list or type(substitutions) is not list:
            raise SubstitutionHistoryError("交代履歴の配列が不一致")
        by_anchor: dict[str | None, list] = {}
        controls: dict[str, list] = {}
        seen_events: set[tuple[str, str]] = set()
        seen_ids: set[str] = set()
        seen_d5: set[str] = set()
        play_ids = {frame["play"]["playId"] for frame in stack}
        for frame in substitutions:
            source_ref = frame["source"]
            anchor = frame["afterPlayId"]
            identity = (source_ref["generation"], source_ref["d1"])
            if (
                source_ref["eventKind"] != "substitution"
                or source_ref["gameId"] != content["scope"]["gameId"]
                or (anchor is not None and anchor not in play_ids)
                or identity in seen_events
                or source_ref["eventId"] in seen_ids
                or source_ref["d5"] in seen_d5
                or "substitutionState" not in frame["afterContext"]
            ):
                raise SubstitutionHistoryError("交代frameの参照が不一致")
            seen_events.add(identity)
            seen_ids.add(source_ref["eventId"])
            seen_d5.add(source_ref["d5"])
            by_anchor.setdefault(anchor, []).append(frame)

        for bridge in control_bridges or []:
            ref = bridge["source"]
            if (
                ref["eventId"] in seen_ids
                or (ref["generation"], ref["d1"]) in seen_events
                or ref["d5"] in seen_d5
            ):
                raise SubstitutionHistoryError("制御/交代のeventが重複")
            seen_ids.add(ref["eventId"])
            seen_events.add((ref["generation"], ref["d1"]))
            seen_d5.add(ref["d5"])
            controls.setdefault(bridge["anchorEventId"], []).append(bridge)

        def gap(
            play_anchor: str | None,
            event_anchor: str,
            before: object | None,
            after: object,
        ) -> None:
            frames = by_anchor.pop(play_anchor, []) + controls.pop(event_anchor, [])
            frames.sort(key=lambda frame: int(frame["source"]["d1"]))
            current = before
            for frame in frames:
                if current is not None and not _same(current, frame["beforeContext"]):
                    raise SubstitutionHistoryError("交代/制御frameの前文脈が不一致")
                current = frame["afterContext"]
            if current is not None and not _same(current, after):
                raise SubstitutionHistoryError("交代/制御frameの後文脈が不一致")

        # 最古playより前の交代。初期文脈はDB開始原本から別途照合する。
        if stack:
            gap(
                None,
                content["origin"]["eventId"],
                None,
                stack[-1]["beforeContext"],
            )
        else:
            gap(None, content["origin"]["eventId"], None, content["restored"])
        for index in range(len(stack) - 1, -1, -1):
            older = stack[index]
            newer = stack[index - 1] if index else None
            target = (
                newer["beforeContext"] if newer is not None else content["restored"]
            )
            gap(
                older["play"]["playId"],
                older["play"]["source"]["eventId"],
                older["afterContext"],
                target,
            )
        if by_anchor or controls:
            raise SubstitutionHistoryError("未接続の交代/制御frameが残りました")
    except (KeyError, TypeError, AttributeError) as error:
        raise SubstitutionHistoryError("交代履歴の閉形が不一致") from error
