"""保存済みv3通常投球の有限訂正を既唯一artifactで順次再評価する。

本関数はDB原本・P3認可・投影保存資格を発行しない。呼出側は同一取引で
対象直前の真正checkpointと全原本・末尾を確認し、未対応後続を拒否する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixRequest,
    LineupPrefixSuccess,
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
    seal_lineup_wire,
    verify_lineup_wire_seal,
)
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.terminal_pitch_payload import (
    LineupPitchCalculation,
    LineupPitchPlayPayload,
    read_lineup_pitch_payload,
)


class LineupCorrectionUnsupported(RuntimeError):
    """原本・後続・数学のいずれかを有限訂正へ結べない。"""


@dataclass(frozen=True, slots=True)
class SavedLineupPitch:
    """同一取引の実DB readerが束縛すべき原本参照と閉計算値。"""

    source_event_id: UUID
    d1: int
    d2: int
    calculation: LineupPitchCalculation
    payload: LineupPitchPlayPayload | None = None
    play_row: dict[str, object] | None = None
    play_runners: tuple[dict[str, object], ...] | None = None


@dataclass(frozen=True, slots=True)
class CorrectedLineupPitch:
    """旧原本に対応する訂正後計算候補。保存・ACKではない。"""

    source_event_id: UUID
    d1: int
    d2: int
    original: LineupPrefixSuccess
    corrected_request: LineupPrefixRequest
    corrected_response: LineupPrefixSuccess


@dataclass(frozen=True, slots=True)
class CorrectionPageState:
    """同一原本系列のページ境界で旧/新の直前応答だけを保持する。"""

    last_d1: int = 0
    last_d2: int = 0
    previous_original: LineupPrefixSuccess | None = None
    previous_corrected: LineupPrefixSuccess | None = None
    target_d1: int | None = None
    replacement_result_id: str | None = None


def _wire(value: BaseModel) -> dict:
    """閉型値を表現を落とさずJSON objectへ戻す。"""
    return value.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _same(left: object, right: object) -> bool:
    """JSONの数値型や配列順も含めて全値を比較する。"""
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False
    )


def _bound_original(
    saved: SavedLineupPitch,
    previous: LineupPrefixSuccess | None,
    host: NodeDomainHost,
) -> tuple[LineupPrefixRequest, LineupPrefixSuccess]:
    """保存済みresponseを現artifactで独立再生し、順序と参照を照合する。"""
    if (
        type(saved) is not SavedLineupPitch
        or type(saved.source_event_id) is not UUID
        or type(saved.d1) is not int
        or type(saved.d2) is not int
        or type(saved.calculation) is not LineupPitchCalculation
        or not 0 < saved.d1 < 2**63
        or not 0 < saved.d2 < 2**63
    ):
        raise LineupCorrectionUnsupported("保存済みv3原本参照が不正")
    request = saved.calculation.request
    original = saved.calculation.response
    if saved.payload is not None and (
        type(saved.payload) is not LineupPitchPlayPayload
        or saved.payload.calculation != saved.calculation
        or type(saved.payload.observations) is not FirstBallObservations
    ):
        raise LineupCorrectionUnsupported("保存済みv3 V7と計算原本が不一致")
    if (
        request.play_identity.event_id != str(saved.source_event_id)
        or request.source.position.d1 != str(saved.d1)
        or request.source.position.d2 != str(saved.d2)
        or original.value.play_identity != request.play_identity
        or original.value.source_position != request.source.position
        or request.t1.result_id
        not in {
            "batting-result.ball",
            "batting-result.called-pitch",
            "batting-result.called-strikeout",
        }
    ):
        raise LineupCorrectionUnsupported("保存済みv3原本と位置が不一致")
    verify_lineup_wire_seal(request, original)
    if previous is not None:
        prior = previous.value
        source = request.source
        if (
            request.prefix_ref != prior.next_prefix_ref
            or source.prefix_ref != prior.next_prefix_ref
            or source.after != prior.t1.after
            or source.t2 != prior.t2
            or source.runners != prior.runners
            or source.participants != prior.participants
            or source.responsibility != prior.next_responsibility
            or source.lineup != prior.lineup
            or source.last_source != prior.play_identity
            or source.prior_artifact_sha256 != prior.execution_artifact_sha256
        ):
            raise LineupCorrectionUnsupported("旧v3原本の前後連鎖が不一致")
    actual = decode_lineup_prefix_response(
        host.call(
            "deriveLineupPlayPrefixWithContinuation",
            request.model_dump_json(by_alias=True, exclude_unset=True),
        )
    )
    if type(actual) is not LineupPrefixSuccess or not _same(
        _wire(actual), _wire(original)
    ):
        raise LineupCorrectionUnsupported("旧v3原本が現artifactの再生値と不一致")
    return request, original


def _next_corrected_request(
    original: LineupPrefixRequest,
    previous: LineupPrefixSuccess | None,
    replacement_result_id: str | None,
    next_checkpoint_id: UUID,
    artifact_sha256: str,
) -> LineupPrefixRequest:
    """元D1/D2/IDを保持し、前回の実応答だけを次sourceへ写す。"""
    request = _wire(original)
    source = request["source"]
    if previous is not None:
        prior = _wire(previous)["value"]
        ref = prior["nextPrefixRef"]
        request["prefixRef"] = ref
        request["t1"]["before"] = prior["t1"]["after"]
        source.update(
            {
                "kind": "evaluated-prefix-v3",
                "prefixRef": ref,
                "after": prior["t1"]["after"],
                "t2": prior["t2"],
                "historyDepth": ref["length"],
                "playCount": ref["length"],
                "lastSource": prior["playIdentity"],
                "priorArtifactSha256": prior["executionArtifactSha256"],
                "lineup": prior["lineup"],
                "runners": prior["runners"],
                "participants": prior["participants"],
                "responsibility": prior["nextResponsibility"],
                "provenance": {
                    "kind": "confirmed-prefix",
                    "checkpoint": ref["checkpoint"],
                    "sourceIdentity": prior["playIdentity"],
                    "historyDepth": ref["length"],
                },
            }
        )
    if replacement_result_id is not None:
        request["t1"]["resultId"] = replacement_result_id
    source["executionArtifactSha256"] = artifact_sha256
    request["nextCheckpoint"]["id"] = str(next_checkpoint_id)
    request["nextCheckpoint"]["digest"] = "0" * 64
    return decode_lineup_prefix_request(json.dumps(request, ensure_ascii=False))


def _evaluate_page(
    rows: tuple[SavedLineupPitch, ...],
    replacement_result_id: Literal[
        "batting-result.ball", "batting-result.called-pitch"
    ],
    checkpoint_ids: tuple[UUID, ...],
    host: NodeDomainHost,
    state: CorrectionPageState,
    *,
    target_d1: int,
) -> tuple[CorrectionPageState, tuple[CorrectedLineupPitch, ...]]:
    """元/新直前値を持ち越し、25件以下を唯一hostで順に検証する。"""
    if (
        type(rows) is not tuple
        or not 1 <= len(rows) <= 25
        or type(state) is not CorrectionPageState
        or type(state.last_d1) is not int
        or type(state.last_d2) is not int
        or state.last_d1 < 0
        or state.last_d2 < 0
        or (state.last_d1 == 0) != (state.previous_original is None)
        or (state.last_d1 == 0) != (state.previous_corrected is None)
        or (
            state.previous_original is not None
            and type(state.previous_original) is not LineupPrefixSuccess
        )
        or (
            state.previous_corrected is not None
            and type(state.previous_corrected) is not LineupPrefixSuccess
        )
        or (
            state.last_d1 > 0
            and (
                type(state.target_d1) is not int
                or type(state.replacement_result_id) is not str
            )
        )
        or type(target_d1) is not int
        or target_d1 < 1
        or type(host) is not NodeDomainHost
        or replacement_result_id
        not in {"batting-result.ball", "batting-result.called-pitch"}
        or (state.target_d1 is not None and state.target_d1 != target_d1)
        or (
            state.replacement_result_id is not None
            and state.replacement_result_id != replacement_result_id
        )
        or type(checkpoint_ids) is not tuple
        or any(type(identifier) is not UUID for identifier in checkpoint_ids)
        or len(set(checkpoint_ids)) != len(checkpoint_ids)
        or len(checkpoint_ids)
        != sum(state.last_d1 + index >= target_d1 for index in range(1, len(rows) + 1))
    ):
        raise LineupCorrectionUnsupported("訂正v3ページ境界が不正")
    previous_original = state.previous_original
    previous_corrected = state.previous_corrected
    prior_d2 = state.last_d2
    corrected: list[CorrectedLineupPitch] = []
    checkpoint_index = 0
    for offset, saved in enumerate(rows, start=1):
        if saved.d1 != state.last_d1 + offset or saved.d2 <= prior_d2:
            raise LineupCorrectionUnsupported("訂正v3原本のページ順序が不正")
        original_request, original_response = _bound_original(
            saved, previous_original, host
        )
        previous_original = original_response
        prior_d2 = saved.d2
        if saved.d1 < target_d1:
            previous_corrected = original_response
            continue
        request = _next_corrected_request(
            original_request,
            previous_corrected,
            replacement_result_id if saved.d1 == target_d1 else None,
            checkpoint_ids[checkpoint_index],
            host.artifact_sha256,
        )
        checkpoint_index += 1
        response = decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                request.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
        if type(response) is not LineupPrefixSuccess:
            raise LineupCorrectionUnsupported("訂正後v3結果が未対応")
        request, response = seal_lineup_wire(request, response)
        corrected.append(
            CorrectedLineupPitch(
                saved.source_event_id,
                saved.d1,
                saved.d2,
                original_response,
                request,
                response,
            )
        )
        previous_corrected = response
    return (
        CorrectionPageState(
            state.last_d1 + len(rows),
            prior_d2,
            previous_original,
            previous_corrected,
            target_d1,
            replacement_result_id,
        ),
        tuple(corrected),
    )


def _evaluate(
    rows: tuple[SavedLineupPitch, ...],
    replacement_result_id: Literal[
        "batting-result.ball", "batting-result.called-pitch"
    ],
    checkpoint_ids: tuple[UUID, ...],
    host: NodeDomainHost,
    *,
    target_d1: int = 1,
) -> tuple[CorrectedLineupPitch, ...]:
    """旧正史の各球を照合し、訂正系列だけを同核で再導出する。"""
    if (
        type(rows) is not tuple
        or not 1 <= len(rows) <= 25
        or type(target_d1) is not int
        or not 1 <= target_d1 <= len(rows)
        or type(checkpoint_ids) is not tuple
        or len(checkpoint_ids) != len(rows) - target_d1 + 1
        or any(type(identifier) is not UUID for identifier in checkpoint_ids)
        or len(set(checkpoint_ids)) != len(checkpoint_ids)
        or replacement_result_id
        not in {"batting-result.ball", "batting-result.called-pitch"}
        or type(host) is not NodeDomainHost
    ):
        raise LineupCorrectionUnsupported("訂正v3有限pageの入力が不正")
    _, corrected = _evaluate_page(
        rows,
        replacement_result_id,
        checkpoint_ids,
        host,
        CorrectionPageState(),
        target_d1=target_d1,
    )
    return corrected


def evaluate_lineup_pitch_result_correction(
    rows: tuple[SavedLineupPitch, ...],
    replacement_result_id: Literal[
        "batting-result.ball", "batting-result.called-pitch"
    ],
    checkpoint_ids: tuple[UUID, ...],
    *,
    target_d1: int = 1,
) -> tuple[CorrectedLineupPitch, ...]:
    """製品固定artifactだけで有限v3結果候補を返す。"""
    with open_domain_host() as host:
        return _evaluate(
            rows,
            replacement_result_id,
            checkpoint_ids,
            host,
            target_d1=target_d1,
        )


def build_corrected_lineup_payloads(
    rows: tuple[SavedLineupPitch, ...],
    corrected: tuple[CorrectedLineupPitch, ...],
    replacement_observations: FirstBallObservations,
) -> tuple[LineupPitchPlayPayload, ...]:
    """訂正観測と後続の保存観測を実再評価値へ厳密に束縛する。"""
    if (
        type(rows) is not tuple
        or type(corrected) is not tuple
        or not corrected
        or type(replacement_observations) is not FirstBallObservations
    ):
        raise LineupCorrectionUnsupported("訂正v3観測原本が不正")
    by_d1 = {row.d1: row for row in rows}
    if len(by_d1) != len(rows):
        raise LineupCorrectionUnsupported("訂正v3観測原本の位置が重複")
    result: list[LineupPitchPlayPayload] = []
    for index, frame in enumerate(corrected):
        saved = by_d1.get(frame.d1)
        if (
            type(frame) is not CorrectedLineupPitch
            or type(saved) is not SavedLineupPitch
            or type(saved.payload) is not LineupPitchPlayPayload
            or saved.source_event_id != frame.source_event_id
            or saved.d2 != frame.d2
            or saved.payload.calculation != saved.calculation
            or frame.corrected_request.source.participants
            != saved.calculation.request.source.participants
            or frame.corrected_request.source.lineup
            != saved.calculation.request.source.lineup
        ):
            raise LineupCorrectionUnsupported("訂正v3保存観測の参照が不一致")
        observations = (
            replacement_observations if index == 0 else saved.payload.observations
        )
        if type(observations) is not FirstBallObservations:
            raise LineupCorrectionUnsupported("訂正v3後続観測が未対応")
        calculation = LineupPitchCalculation.model_validate_json(
            _canonical_json(
                {
                    "formatVersion": "play-prefix-calculation-v3",
                    "artifactSha256": (
                        frame.corrected_request.source.execution_artifact_sha256
                    ),
                    "request": _wire(frame.corrected_request),
                    "response": _wire(frame.corrected_response),
                }
            )
        )
        payload = {
            "formatVersion": "play-prefix-play-v3",
            "observations": _wire(observations),
            "participants": _wire(saved.payload.participants),
            "calculation": _wire(calculation),
        }
        result.append(
            read_lineup_pitch_payload(
                _canonical_json(payload),
                _canonical_json(
                    _wire(frame.corrected_response.value.new_history_entry.difference)
                ),
                expected_calculation=calculation,
            )
        )
    return tuple(result)
