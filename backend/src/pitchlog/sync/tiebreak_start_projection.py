"""タイブレーク開始のartifact結果から非play CP候補を組み立てる。DB保存は行わない。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.nonplay_prefix import _check_source
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tiebreak_start_payload import read_tiebreak_start_event
from pitchlog.sync.undo_payload import _validate_value


class TiebreakStartProjectionError(ValueError):
    """閉じた投影候補が真正前文脈と一致しない。"""


def _same(left: object, right: object) -> bool:
    """JSONの型と全値を保持して比較する。"""
    return _canonical_json(left) == _canonical_json(right)


def _transition(value: object, before: dict[str, Any]) -> dict[str, Any]:
    """artifact応答の変更可能な文脈集合だけを検査する。"""
    if type(value) is not dict:
        raise TiebreakStartProjectionError(
            "タイブレーク開始artifactの成功形が不一致です"
        )
    after = cast("dict[str, Any]", value)
    _validate_value(after, "RestoreContext")
    fixed = set(before) - {
        "current",
        "participants",
        "runners",
        "lineup",
        "responsibility",
        "substitutionState",
    }
    if set(after) != set(before) or any(
        not _same(before[name], after[name]) for name in fixed
    ):
        raise TiebreakStartProjectionError(
            "タイブレーク開始以外の復元文脈が変更されました"
        )
    if not _same(after.get("lineup"), before.get("lineup")) or not _same(
        after.get("responsibility"), before.get("responsibility")
    ):
        raise TiebreakStartProjectionError(
            "タイブレーク開始で名簿・責任が変更されました"
        )
    return cast("dict[str, Any]", after)


def build_tiebreak_start_source(
    before: dict[str, Any],
    event: SyncEvent,
    *,
    fingerprint: str,
    artifact_sha256: str,
    transition: object,
) -> dict[str, Any]:
    """同TX保存原本との後段照合用に、タイブレーク開始1件分の全CP候補を作る。"""
    try:
        _check_source(before)
        payload = read_tiebreak_start_event(event).to_wire()
        cp = before["checkpoint"]
        content = cp["content"]
        restored = content["restored"]
        fields = restored["current"]["stateFields"]
        rules = restored["rules"]["tiebreak"]
        if (
            payload["leadoffBatter"] != fields["state.battingOrder"]
            or payload["inning"] != fields["state.inning"]
            or payload["runnerPlacement"] != "first-second"
            or rules.get("runnerPlacement")
            not in ("first-second", "no_out_first_second")
            or rules.get("leadoffRule") != "continue_lineup"
        ):
            raise TiebreakStartProjectionError(
                "タイブレーク開始の先頭打者・回・配置が保存状態と不一致です"
            )
        if (
            not _same(payload["expectedCheckpoint"], cp["ref"])
            or event.game_id != content["scope"]["gameId"]
            or event.d4 != content["scope"]["generation"]
            or event.d1 != int(content["d3"]) + 1
            or content["executionArtifactSha256"] != artifact_sha256
            or type(fingerprint) is not str
            or not fingerprint.startswith("wire-v1:")
            or len(fingerprint) != 72
        ):
            raise TiebreakStartProjectionError(
                "タイブレーク開始のCP/世代/指紋が不一致です"
            )
        event_id = str(UUID(cast(str, payload["eventId"])))
        reference = {
            "eventId": event_id,
            "gameId": event.game_id,
            "generation": event.d4,
            "d1": str(event.d1),
            "d5": event.d5,
            "fingerprint": fingerprint,
            "eventKind": "tiebreak_start",
        }
        restored = _transition(transition, content["restored"])
        result = deepcopy(before)
        after_content = result["checkpoint"]["content"]
        prior_stack = result["activeStack"]
        after_play_id = prior_stack[0]["play"]["playId"] if prior_stack else None
        frame = {
            "source": reference,
            "afterPlayId": after_play_id,
            "beforeContext": content["restored"],
            "afterContext": restored,
        }
        frames = list(after_content.get("tiebreakFrames", []))
        frames.append(frame)
        after_content.update(
            d3=str(event.d1),
            d1Head={"kind": "accepted-event", "source": reference},
            projectionHead={"kind": "d1-event", "source": reference},
            historyVersion=str(int(content["historyVersion"]) + 1),
            restored=restored,
            tiebreakFrames=frames,
        )
        result["checkpoint"]["ref"]["revision"] = str(int(cp["ref"]["revision"]) + 1)
        result["checkpoint"]["ref"]["digest"] = source_fingerprint(after_content)
        _check_source(result)
        return result
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, TiebreakStartProjectionError):
            raise
        raise TiebreakStartProjectionError(
            "タイブレーク開始CP候補が不成立です"
        ) from error
