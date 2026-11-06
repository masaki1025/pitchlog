"""交代の唯一artifact結果から非play CP候補を組み立てる。DB保存は行わない。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories.nonplay_prefix import _check_source
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.substitution_payload import read_substitution_event
from pitchlog.sync.undo_payload import _validate_value


class SubstitutionProjectionError(ValueError):
    """閉じた投影候補が真正前文脈と一致しない。"""


def _same(left: object, right: object) -> bool:
    """JSONの型と全値を保持して比較する。"""
    return _canonical_json(left) == _canonical_json(right)


def _transition(value: object, before: dict[str, Any]) -> dict[str, Any]:
    """artifact応答の変更可能な文脈集合だけを検査する。"""
    if type(value) is not dict:
        raise SubstitutionProjectionError("交代artifactの成功形が不一致です")
    row = cast("dict[str, Any]", value)
    if set(row) != {"ok", "state", "warnings", "afterContext"} or row["ok"] is not True:
        raise SubstitutionProjectionError("交代artifactの成功形が不一致です")
    after = row["afterContext"]
    if type(after) is not dict or not _same(
        after.get("substitutionState"), row["state"]
    ):
        raise SubstitutionProjectionError("交代状態の同値が不一致です")
    _validate_value(after, "RestoreContext")
    fixed = set(before) - {
        "lineup",
        "participants",
        "runners",
        "responsibility",
        "substitutionState",
    }
    if set(after) != set(before) | {"substitutionState"} or any(
        not _same(before[name], after[name]) for name in fixed
    ):
        raise SubstitutionProjectionError("交代以外の復元文脈が変更されました")
    if type(row["warnings"]) is not list or any(
        warning not in {"fielding-position-missing", "fielding-position-duplicate"}
        for warning in row["warnings"]
    ):
        raise SubstitutionProjectionError("交代警告が不一致です")
    return cast("dict[str, Any]", after)


def build_substitution_source(
    before: dict[str, Any],
    event: SyncEvent,
    *,
    fingerprint: str,
    artifact_sha256: str,
    transition: object,
) -> dict[str, Any]:
    """同TX保存原本との後段照合用に、交代1件分の全CP/履歴候補を作る。"""
    try:
        _check_source(before)
        payload = read_substitution_event(event).to_wire()
        cp = before["checkpoint"]
        content = cp["content"]
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
            raise SubstitutionProjectionError("交代のCP/世代/指紋が不一致です")
        event_id = str(UUID(payload["eventId"]))
        reference = {
            "eventId": event_id,
            "gameId": event.game_id,
            "generation": event.d4,
            "d1": str(event.d1),
            "d5": event.d5,
            "fingerprint": fingerprint,
            "eventKind": "substitution",
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
        frames = list(after_content.get("substitutionFrames", []))
        frames.append(frame)
        after_content.update(
            d3=str(event.d1),
            d1Head={"kind": "accepted-event", "source": reference},
            projectionHead={"kind": "d1-event", "source": reference},
            historyVersion=str(int(content["historyVersion"]) + 1),
            restored=restored,
            substitutionFrames=frames,
        )
        result["checkpoint"]["ref"]["revision"] = str(int(cp["ref"]["revision"]) + 1)
        result["checkpoint"]["ref"]["digest"] = source_fingerprint(after_content)
        _check_source(result)
        return result
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, SubstitutionProjectionError):
            raise
        raise SubstitutionProjectionError("交代CP候補が不成立です") from error
