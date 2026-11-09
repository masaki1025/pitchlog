"""検証済みP3有効版を元D1 eventの非play frameへ束縛する。"""

from __future__ import annotations

from copy import deepcopy
from typing import cast
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.past_correction_current import (
    PastCorrectionCurrentUnavailable,
    VerifiedP3Current,
    verify_p3_current_packet,
)
from pitchlog.sync.undo_payload import _validate_value


def read_p3_nonplay_current(
    handle,
    game_id: UUID,
    generation: int,
    *,
    nonplay_checkpoint_row: dict[str, object] | None = None,
):
    """同tenant TXの現行又はLC前anchorを元source証明へ束縛する。"""
    from pitchlog.repositories.ordinary_prefix_read import _function_one
    from pitchlog.repositories.past_correction_right import _ReadP3CurrentToken
    from pitchlog.repositories.play_prefix import _verify_source_evidence
    from pitchlog.sync.terminal_pitch_tokens import PlayPrefixCheckpointReadToken

    packet = _function_one(handle, _ReadP3CurrentToken(game_id, generation))
    if type(packet) is not dict or packet.get("kind") not in {
        "none",
        "p3-current",
        "p3-anchor",
    }:
        raise PastCorrectionCurrentUnavailable("非play P3 current形が不正")
    if packet["kind"] == "none":
        return None
    if packet["kind"] == "p3-anchor":
        anchor_row = nonplay_checkpoint_row
        if anchor_row is None:
            candidate = packet.get("nonplay_checkpoint")
            if type(candidate) is not dict:
                raise PastCorrectionCurrentUnavailable("非play P3 anchor行が不正")
            anchor_row = candidate
        return verify_p3_current_packet(
            packet,
            tenant=handle._bound_tenant_id,
            game=game_id,
            generation=generation,
            nonplay_checkpoint_row=anchor_row,
        )
    if nonplay_checkpoint_row is not None:
        raise PastCorrectionCurrentUnavailable("非play P3現CP種別が不一致")
    row = packet.get("checkpoint")
    if type(row) is not dict:
        raise PastCorrectionCurrentUnavailable("非play P3 CP原本が不正")
    point = _function_one(handle, PlayPrefixCheckpointReadToken(game_id, generation))
    if (
        type(point) is not dict
        or set(point) != {"kind", "row"}
        or point["kind"] != "checkpoint"
        or type(point["row"]) is not dict
    ):
        raise PastCorrectionCurrentUnavailable("非play P3独立CP証拠が不正")
    proven = point["row"]
    # P3 next contentは原本CPのcontentだけを置換した論理版である。
    # 独立current CPとはcontent/digest/最終play列以外の同一id/rev/水位を
    # 照合し、後続playがある場合はrevision/水位の子孫だけを許可する。
    ignored = {
        "content",
        "content_digest",
        "last_history",
        "last_play_row",
        "last_play_runners",
        "source_evidence",
    }
    same = all(
        proven.get(key) == row.get(key)
        for key in set(proven) | set(row)
        if key not in ignored
    )
    try:
        descendant = (
            type(proven.get("id")) is str
            and int(proven["revision"]) > int(row["revision"])
            and int(proven["confirmed_watermark"])
            > int(row["confirmed_watermark"])
        )
    except (KeyError, TypeError, ValueError):
        descendant = False
    if not (same or descendant):
        raise PastCorrectionCurrentUnavailable("非play P3独立CPが不一致")
    _verify_source_evidence(proven, bridge=False)
    if proven["source_evidence"]["non_play_count"] != 0:
        raise PastCorrectionCurrentUnavailable("非play P3元操作が混在")
    return verify_p3_current_packet(
        packet, tenant=handle._bound_tenant_id, game=game_id, generation=generation
    )


def p3_effective_nonplay_frame(original: dict, verified: VerifiedP3Current) -> dict:
    """元frameを検証し、P3で選ばれた有効版だけを公開する。"""
    from pitchlog.repositories.nonplay_prefix import _stored_contexts

    source = original["play"]["source"]
    d1 = int(source["d1"])
    if d1 <= 0 or d1 > len(verified.items):
        if d1 <= 0:
            raise PastCorrectionCurrentUnavailable("非play P3 active位置が不一致")
        # P3 watermarkより後の実play frameはP3訂正の対象外。現在chainの
        # 前後文脈はlegacy CP再構成で別に照合する。
        _validate_value(original, "ActiveFrame")
        return original
    item = verified.items[d1 - 1]
    if d1 > int(verified.original_checkpoint.confirmed_watermark):
        play_row = cast(dict[str, object], item["play_row"])
        payload = verified.payloads[d1 - 1]
        before, after = _stored_contexts(
            payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )
        if (
            source["eventId"] != play_row["source_event_id"]
            or original["play"]["playId"] != play_row["id"]
            or original["historyEntry"] != item["history_entry"]
            or original["beforeContext"] != before
            or original["afterContext"] != after
        ):
            raise PastCorrectionCurrentUnavailable("非play P3後続frameが不一致")
        return original
    # 後続playの現chainは訂正後の実効frameを含み得る。同じ実効版なら
    # 原本へ戻さず、そのまま検証して保持する（二重適用しない）。
    effective_before, effective_after = _stored_contexts(item["payload"])
    if (
        source["eventId"] == item["effective_event_id"]
        and original["play"]["playId"] == item["effective_play_row_id"]
        and original["historyEntry"] == item["history_entry"]
        and original["beforeContext"] == effective_before
        and original["afterContext"] == effective_after
    ):
        _validate_value(original, "ActiveFrame")
        return original
    old_before, old_after = _stored_contexts(item["original_payload"])
    if (
        source["eventId"] != item["original_event_id"]
        or original["play"]["playId"] != item["original_play_row_id"]
        or original["historyEntry"] != item["original_history_entry"]
        or original["beforeContext"] != old_before
        or original["afterContext"] != old_after
    ):
        raise PastCorrectionCurrentUnavailable("非play P3元frameが不一致")
    effective = deepcopy(original)
    payload = verified.payloads[d1 - 1]
    before, after = _stored_contexts(
        payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )
    effective["play"]["playId"] = item["effective_play_row_id"]
    play_row = cast(dict[str, object], item["play_row"])
    effective["play"]["physicalPlayNumber"] = str(play_row["play_number"])
    effective["historyEntry"] = item["history_entry"]
    effective["beforeContext"] = before
    effective["afterContext"] = after
    _validate_value(effective, "ActiveFrame")
    return effective


def p3_effective_nonplay_stack(
    stack: list[dict],
    verified: VerifiedP3Current,
    *,
    first_control_before: dict[str, object] | None = None,
    first_control_d1: int | None = None,
) -> list[dict]:
    """元frame証明を残し、対象slotの有効文脈だけを共通射影で選ぶ。"""
    if (
        len(stack) < len(verified.items)
        or int(verified.original_checkpoint.confirmed_watermark) > len(verified.items)
        or verified.historical_anchor
        != (first_control_before is not None and first_control_d1 is not None)
    ):
        raise PastCorrectionCurrentUnavailable("非play P3 stack件数が不一致")
    result = []
    seen = set()
    for original in stack:
        d1 = int(original["play"]["source"]["d1"])
        if d1 in seen:
            raise PastCorrectionCurrentUnavailable("非play P3 active位置が不一致")
        seen.add(d1)
        result.append(p3_effective_nonplay_frame(original, verified))
    if not set(range(1, len(verified.items) + 1)).issubset(seen):
        raise PastCorrectionCurrentUnavailable("非play P3 active集合が不一致")
    if verified.historical_anchor:
        if type(first_control_d1) is not int or first_control_d1 <= len(verified.items):
            raise PastCorrectionCurrentUnavailable("非play P3制御位置が不一致")
        before_control = next(
            (
                frame
                for frame in result
                if int(frame["play"]["source"]["d1"]) == first_control_d1 - 1
            ),
            None,
        )
        if (
            before_control is None
            or before_control["afterContext"] != first_control_before
        ):
            raise PastCorrectionCurrentUnavailable("非play P3制御前文脈が不一致")
        ordered = sorted(
            (
                frame
                for frame in result
                if int(frame["play"]["source"]["d1"]) < first_control_d1
            ),
            key=lambda frame: int(frame["play"]["source"]["d1"]),
        )
        for previous, following in zip(ordered, ordered[1:]):
            if (
                int(following["play"]["source"]["d1"])
                == int(previous["play"]["source"]["d1"]) + 1
                and previous["afterContext"] != following["beforeContext"]
            ):
                raise PastCorrectionCurrentUnavailable("非play P3訂正後連鎖が不一致")
        first_prep = verified.first_control_preparation
        if type(first_prep) is not dict:
            raise PastCorrectionCurrentUnavailable("非play P3初回制御印が欠落")
        before_source = first_prep.get("before_source")
        storage = first_prep.get("storage")
        if type(before_source) is not dict or type(storage) is not dict:
            raise PastCorrectionCurrentUnavailable("非play P3初回制御原本が不正")
        before_checkpoint = before_source.get("checkpoint")
        before_content = (
            before_checkpoint.get("content")
            if type(before_checkpoint) is dict
            else None
        )
        if type(before_content) is not dict:
            raise PastCorrectionCurrentUnavailable("非play P3初回CP内容が不正")
        artifact = before_content.get("executionArtifactSha256")
        if type(artifact) is not str:
            raise PastCorrectionCurrentUnavailable("非play P3初回artifactが不正")
        precontrol = [
            frame
            for frame in result
            if int(frame["play"]["source"]["d1"]) < first_control_d1
        ]
        if type(before_checkpoint) is not dict or precontrol != before_source.get(
            "activeStack"
        ):
            raise PastCorrectionCurrentUnavailable("非play P3初回制御stackが不一致")
        from pitchlog.repositories.nonplay_prefix import _checkpoint_from_legacy

        logical = _checkpoint_from_legacy(
            verified.checkpoint,
            precontrol,
            storage,
            artifact,
        )
        if logical != before_checkpoint:
            raise PastCorrectionCurrentUnavailable("非play P3旧CP論理版が不一致")
    else:
        marker = next(
            (
                frame
                for frame in result
                if int(frame["play"]["source"]["d1"]) == len(verified.items)
            ),
            None,
        )
        if marker is None or _canonical_json(
            marker["afterContext"]["current"]
        ) != _canonical_json(
            verified.checkpoint.after.model_dump(mode="json", by_alias=True)
        ):
            raise PastCorrectionCurrentUnavailable("非play P3現状態が不一致")
    return result
