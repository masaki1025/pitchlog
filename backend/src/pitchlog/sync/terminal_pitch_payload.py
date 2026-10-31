"""v2計算の閉V7/差分V8とwire-head metadata seal。数学や資格を生成しない。"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from pitchlog.domainrt.first_ball_projection import _canonical_json, _canonical_sha256
from pitchlog.domainrt.first_pitch import _Frozen
from pitchlog.domainrt.first_pitch_continuation import _check_frozen_members
from pitchlog.domainrt.play_prefix_continuation import (
    PlayPrefixRequest,
    PlayPrefixSuccess,
)
from pitchlog.domainrt.terminal_pitch import TerminalHistoryEntry
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.ordinary_pitch_payload import (
    OrdinaryPitchParticipants,
    _raw_json,
)


class TerminalPitchPayloadError(ValueError):
    """原入力や資格を例外へ混ぜない固定の閉境界違反。"""

    def __init__(self) -> None:
        """不一致を補修しない。"""
        super().__init__("v2投球payload/metadataが実評価と一致しません")


class TerminalPitchCalculation(_Frozen):
    """実artifact一回の全request/response。保存資格とは別。"""

    format_version: Literal["play-prefix-calculation-v2"] = Field(alias="formatVersion")
    artifact_sha256: Annotated[str, AfterValidator(_canonical_sha256)] = Field(
        alias="artifactSha256"
    )
    request: PlayPrefixRequest
    response: PlayPrefixSuccess


class TerminalPitchPlayPayload(_Frozen):
    """既V7と区別した閉variant。参加者は今回before側。"""

    format_version: Literal["play-prefix-play-v2"] = Field(alias="formatVersion")
    observations: FirstBallObservations
    participants: OrdinaryPitchParticipants
    calculation: TerminalPitchCalculation


def _dump(value):
    """省略差分をnullへ補完せず全wire値を保持する。"""
    return value.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _checked(value, model):
    """強制変更/異なる実型/余剰memberをJSON再検証でも拒否する。"""
    if type(value) is not model:
        raise TerminalPitchPayloadError
    _check_frozen_members(value)
    result = model.model_validate_json(_canonical_json(_dump(value)))
    if _canonical_json(_dump(result)) != _canonical_json(_dump(value)):
        raise TerminalPitchPayloadError
    return result


def play_prefix_wire_head(
    request: PlayPrefixRequest, response: PlayPrefixSuccess
) -> dict:
    """自己echo二欄以外を落とさないexact Wを構成する。"""
    request = _checked(request, PlayPrefixRequest)
    response = _checked(response, PlayPrefixSuccess)
    q, r = _dump(request), _dump(response)["value"]
    ref, source = r["nextPrefixRef"], q["source"]
    if (
        r["previousPrefixRef"] != q["prefixRef"]
        or r["playIdentity"] != q["playIdentity"]
        or ref["checkpoint"]["id"] != q["nextCheckpoint"]["id"]
        or ref["checkpoint"]["revision"] != q["nextCheckpoint"]["revision"]
        or source["executionArtifactSha256"] != r["executionArtifactSha256"]
    ):
        raise TerminalPitchPayloadError
    return {
        "formatVersion": "play-prefix-wire-head-v2",
        "version": ref["version"],
        "scope": ref["scope"],
        "tenantId": ref["tenantId"],
        "gameId": ref["gameId"],
        "generation": ref["generation"],
        "length": ref["length"],
        "checkpointId": ref["checkpoint"]["id"],
        "checkpointRevision": ref["checkpoint"]["revision"],
        "historyVersion": ref["historyVersion"],
        "origin": ref["origin"],
        "previousPrefixRef": q["prefixRef"],
        "rules": q["rules"],
        "rulesDigest": source["rulesDigest"],
        "layoutDigest": source["layoutDigest"],
        "priorArtifactSha256": source["priorArtifactSha256"],
        "executionArtifactSha256": source["executionArtifactSha256"],
        "sourcePosition": source["position"],
        "playIdentity": q["playIdentity"],
        "responsibility": source["responsibility"],
        "before": q["t1"]["before"],
        "T1": r["t1"],
        "T2": r["t2"],
        "newHistoryEntry": r["newHistoryEntry"],
        "runners": r["runners"],
        "participants": r["participants"],
    }


def play_prefix_wire_digest(
    request: PlayPrefixRequest, response: PlayPrefixSuccess
) -> str:
    """実出力と真正sourceからwire-headだけのhashを算出する。"""
    return hashlib.sha256(
        _canonical_json(play_prefix_wire_head(request, response)).encode("utf-8")
    ).hexdigest()


def seal_play_prefix_metadata(
    request: PlayPrefixRequest, response: PlayPrefixSuccess
) -> tuple[PlayPrefixRequest, PlayPrefixSuccess]:
    """一回数学後の自己echo二箇所だけを機械追随する。"""
    digest = play_prefix_wire_digest(request, response)
    q, r = _dump(request), _dump(response)
    q["nextCheckpoint"]["digest"] = digest
    r["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
    return (
        PlayPrefixRequest.model_validate_json(_canonical_json(q)),
        PlayPrefixSuccess.model_validate_json(_canonical_json(r)),
    )


def verify_play_prefix_seal(calculation: TerminalPitchCalculation) -> None:
    """未信頼提案が実wire-head hashと一致するまで保存準備を許さない。"""
    calc = _checked(calculation, TerminalPitchCalculation)
    digest = play_prefix_wire_digest(calc.request, calc.response)
    if (
        calc.artifact_sha256 != calc.request.source.execution_artifact_sha256
        or calc.request.next_checkpoint.digest != digest
        or calc.response.value.next_prefix_ref.checkpoint.digest != digest
    ):
        raise TerminalPitchPayloadError


def format_terminal_pitch_payload(
    observations: FirstBallObservations,
    participants: OrdinaryPitchParticipants,
    calculation: TerminalPitchCalculation,
) -> tuple[str, str]:
    """V7のみ計算封筒、V8は取消用difference全値を写す。"""
    try:
        verify_play_prefix_seal(calculation)
        payload = TerminalPitchPlayPayload.model_validate_json(
            _canonical_json(
                {
                    "formatVersion": "play-prefix-play-v2",
                    "observations": _dump(
                        _checked(observations, FirstBallObservations)
                    ),
                    "participants": _dump(
                        _checked(participants, OrdinaryPitchParticipants)
                    ),
                    "calculation": _dump(
                        _checked(calculation, TerminalPitchCalculation)
                    ),
                }
            )
        )
        return _canonical_json(_dump(payload)), _canonical_json(
            _dump(calculation.response.value.new_history_entry.difference)
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise TerminalPitchPayloadError from None


def read_terminal_pitch_payload(
    v7_json: str,
    v8_json: str,
    *,
    expected_calculation: TerminalPitchCalculation,
    expected_participants: OrdinaryPitchParticipants,
) -> TerminalPitchPlayPayload:
    """独立実計算/実参加者/差分V8へ全値一致する場合だけ受け取る。"""
    try:
        calc = _checked(expected_calculation, TerminalPitchCalculation)
        people = _checked(expected_participants, OrdinaryPitchParticipants)
        verify_play_prefix_seal(calc)
        payload = TerminalPitchPlayPayload.model_validate_json(v7_json)
        if (
            _canonical_json(_raw_json(v7_json)) != _canonical_json(_dump(payload))
            or payload.calculation != calc
            or payload.participants != people
            or people.batting_order != calc.request.t1.before.state_fields.batting_order
        ):
            raise TerminalPitchPayloadError
        entry = TerminalHistoryEntry.model_validate_json(
            _canonical_json(
                {"kind": "confirmed-play", "difference": _raw_json(v8_json)}
            )
        )
        if (
            _canonical_json(_raw_json(v8_json))
            != _canonical_json(_dump(entry.difference))
            or entry.difference != calc.response.value.new_history_entry.difference
        ):
            raise TerminalPitchPayloadError
        return payload
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise TerminalPitchPayloadError from None
