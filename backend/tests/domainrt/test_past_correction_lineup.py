"""既v3 artifactによる過去1球変更と後続再生の有限境界。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixSuccess,
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
    seal_lineup_wire,
)
from pitchlog.domainrt.past_correction_lineup import (
    LineupCorrectionUnsupported,
    SavedLineupPitch,
    _evaluate,
    _next_corrected_request,
    build_corrected_lineup_payloads,
)
from pitchlog.repositories.past_correction_source import PastCorrectionV3SourceSnapshot
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import past_correction_preparation
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.past_correction_payload import (
    PastCorrectionPayloadError,
    bind_lineup_pitch_change_payload,
    read_lineup_pitch_change_payload,
)
from pitchlog.sync.past_correction_physical import prepare_corrected_physical_pitches
from pitchlog.sync.terminal_pitch_payload import (
    LineupPitchCalculation,
    LineupPitchPlayPayload,
)

_ROOT = Path(__file__).resolve().parents[3]
_CASES = {
    row["caseId"]: row
    for row in json.loads(
        (
            _ROOT / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text(encoding="utf-8")
    )["cases"]
}
_ID1 = UUID("10000000-0000-0000-0000-000000000700")
_ID2 = UUID("10000000-0000-0000-0000-000000000703")
_NEW1 = UUID("10000000-0000-0000-0000-000000000801")
_NEW2 = UUID("10000000-0000-0000-0000-000000000802")
_CAPSULE = UUID("10000000-0000-0000-0000-000000000900")
_CHANGE = UUID("10000000-0000-0000-0000-000000000901")


def _host() -> NodeDomainHost:
    return NodeDomainHost(
        _ROOT / "frontend/public/domain/pitchlog-domain.js",
        _ROOT / "frontend/public/domain/pitchlog-domain.json",
    )


def _two_saved(host: NodeDomainHost) -> tuple[SavedLineupPitch, SavedLineupPitch]:
    first = _CASES["V3-STARTED-CHAIN-01"]
    q1 = decode_lineup_prefix_request(json.dumps(first["request"]))
    r1 = decode_lineup_prefix_response(json.dumps(first["expected"]))
    assert type(r1) is LineupPrefixSuccess
    second = _CASES["V3-STARTED-CHAIN-02"]
    old_q2 = decode_lineup_prefix_request(json.dumps(second["request"]))
    q2 = _next_corrected_request(
        old_q2,
        r1,
        None,
        UUID(second["request"]["nextCheckpoint"]["id"]),
        host.artifact_sha256,
    )
    r2 = decode_lineup_prefix_response(
        host.call(
            "deriveLineupPlayPrefixWithContinuation",
            q2.model_dump_json(by_alias=True, exclude_unset=True),
        )
    )
    assert type(r2) is LineupPrefixSuccess
    q2, r2 = seal_lineup_wire(q2, r2)

    def saved(identifier, d1, request, response):
        calculation = LineupPitchCalculation.model_validate_json(
            json.dumps(
                {
                    "formatVersion": "play-prefix-calculation-v3",
                    "artifactSha256": request.source.execution_artifact_sha256,
                    "request": request.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                    "response": response.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                }
            )
        )
        payload = LineupPitchPlayPayload.model_validate_json(
            json.dumps(
                {
                    "formatVersion": "play-prefix-play-v3",
                    "observations": {
                        "pitchTypeKey": "pitch-type.straight",
                        "course": {"unit": "1/263", "x": "131", "y": "132"},
                        "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                        "stance": None,
                        "battingSide": None,
                    },
                    "participants": response.value.before_participants.model_dump(
                        mode="json", by_alias=True
                    ),
                    "calculation": calculation.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                }
            )
        )
        return SavedLineupPitch(identifier, d1, d1, calculation, payload)

    return saved(_ID1, 1, q1, r1), saved(_ID2, 2, q2, r2)


def test_v3_two_pitch_correction_replays_real_artifact_and_preserves_source_ids() -> (
    None
):
    """旧2球の全応答を再生し、新系列の全値を同核で順次生成する。"""
    with _host() as host:
        old = _two_saved(host)
        result = _evaluate(old, "batting-result.ball", (_NEW1, _NEW2), host)
    assert [(x.source_event_id, x.d1, x.d2) for x in result] == [
        (_ID1, 1, 1),
        (_ID2, 2, 2),
    ]
    assert result[0].corrected_request.t1.result_id == "batting-result.ball"
    assert (
        result[1].corrected_request.t1.result_id
        == old[1].calculation.request.t1.result_id
    )
    assert (
        result[1].corrected_request.source.after
        == result[0].corrected_response.value.t1.after
    )
    assert (
        result[1].corrected_request.source.t2 == result[0].corrected_response.value.t2
    )
    assert (
        result[1].corrected_request.source.runners
        == result[0].corrected_response.value.runners
    )
    assert (
        result[1].corrected_request.source.responsibility
        == result[0].corrected_response.value.next_responsibility
    )
    assert (
        result[1].corrected_request.source.last_source
        == result[0].corrected_response.value.play_identity
    )
    assert (
        result[1].corrected_request.prefix_ref
        == result[0].corrected_response.value.next_prefix_ref
    )
    assert result[1].corrected_request.next_checkpoint.id == str(_NEW2)
    assert result[1].corrected_response.value.t1.after.state_fields.strikes == "1"
    assert result[1].corrected_response.value.t1.after.state_fields.balls == "1"


def test_v3_second_pitch_correction_starts_at_verified_prior_checkpoint() -> None:
    """先行原本を改変せず、２球目だけを真正１球目のCPから再評価する。"""
    with _host() as host:
        old = _two_saved(host)
        result = _evaluate(
            old,
            "batting-result.ball",
            (_NEW2,),
            host,
            target_d1=2,
        )
    assert len(result) == 1
    assert result[0].source_event_id == _ID2
    prior = old[0].calculation.response.value
    assert result[0].corrected_request.source.after == prior.t1.after
    assert result[0].corrected_request.source.t2 == prior.t2
    assert result[0].corrected_request.prefix_ref == prior.next_prefix_ref
    assert result[0].corrected_response.value.t1.after.state_fields.strikes == "1"
    assert result[0].corrected_response.value.t1.after.state_fields.balls == "1"


def test_v3_corrected_payload_keeps_downstream_observations_and_explicit_target() -> (
    None
):
    """対象の新観測だけ明示値へ変え、後続は実保存V7を維持する。"""
    with _host() as host:
        old = _two_saved(host)
        frames = _evaluate(old, "batting-result.ball", (_NEW1, _NEW2), host)
    assert old[0].payload is not None and old[1].payload is not None
    original_observation = old[0].payload.observations
    changed = original_observation.model_dump(mode="json", by_alias=True)
    changed["course"]["x"] = "130"
    replacement = FirstBallObservations.model_validate(changed)
    new = build_corrected_lineup_payloads(old, frames, replacement)
    assert new[0].observations.course.x == "130"
    assert new[1].observations == old[1].payload.observations
    assert new[0].calculation.request.t1.result_id == "batting-result.ball"
    assert new[1].calculation.request.t1.result_id == "batting-result.called-pitch"


def test_v3_corrected_payload_rejects_missing_original_v7() -> None:
    """計算だけの候補を物理投影の保存元として昇格させない。"""
    with _host() as host:
        old = _two_saved(host)
        frames = _evaluate(old, "batting-result.ball", (_NEW1, _NEW2), host)
    assert old[0].payload is not None
    missing = SavedLineupPitch(
        old[1].source_event_id,
        old[1].d1,
        old[1].d2,
        old[1].calculation,
    )
    with pytest.raises(LineupCorrectionUnsupported):
        build_corrected_lineup_payloads(
            (old[0], missing), frames, old[0].payload.observations
        )


def test_v3_physical_candidate_uses_existing_mappers_and_new_row_ids() -> None:
    """旧play identityを保ちつつ訂正行PKを分離し後続行も新計算で作る。"""
    with _host() as host:
        old = _two_saved(host)
        frames = _evaluate(old, "batting-result.ball", (_NEW1, _NEW2), host)
    assert old[0].payload is not None and old[1].payload is not None
    tenant = UUID(old[0].calculation.request.prefix_ref.tenant_id)
    game = UUID(old[0].calculation.request.prefix_ref.game_id)
    def with_row(saved: SavedLineupPitch, index: int) -> SavedLineupPitch:
        assert saved.payload is not None
        return replace(
            saved,
            play_row=pitch_physical_row(
                saved.payload.observations,
                saved.payload.participants,
                saved.calculation.request.t1.result_id,
                tenant_id=tenant,
                game_id=game,
                source_event_id=saved.source_event_id,
                row_id=UUID(saved.calculation.request.play_identity.play_id),
                play_number=index,
            ),
        )

    original = tuple(with_row(saved, index) for index, saved in enumerate(old, start=1))
    payloads = build_corrected_lineup_payloads(
        original, frames, old[0].payload.observations
    )
    result = prepare_corrected_physical_pitches(
        original,
        frames,
        payloads,
        tenant_id=tenant,
        game_id=game,
        capsule_id=_CAPSULE,
        change_event_id=_CHANGE,
    )
    assert len(result) == 2
    assert result[0].effective_event_id == _CHANGE
    assert result[1].effective_event_id == original[1].source_event_id
    assert all(item.new_play_row_id != item.original_play_row_id for item in result)
    assert [item.play_row["batting_result_key"] for item in result] == [
        "batting-result.ball",
        "batting-result.called-pitch",
    ]
    assert [item.play_row["play_number"] for item in result] == [1, 2]
    assert all(item.play_row["id"] == str(item.new_play_row_id) for item in result)
    assert original[1].play_row is not None
    forged = dict(original[1].play_row)
    forged["tenant_id"] = str(UUID(int=1))
    with pytest.raises(LineupCorrectionUnsupported):
        prepare_corrected_physical_pitches(
            (original[0], replace(original[1], play_row=forged)),
            frames,
            payloads,
            tenant_id=tenant,
            game_id=game,
            capsule_id=_CAPSULE,
            change_event_id=_CHANGE,
        )


def _change_body(rows: tuple[SavedLineupPitch, ...], target: int) -> dict:
    """実hostから得た現在headと対象identityを変更要求へ写す。"""
    saved = rows[target - 1]
    assert saved.payload is not None
    assert rows[-1].payload is not None
    return {
        "formatVersion": "p3-lineup-pitch-change-v1",
        "expectedPrefixRef": rows[-1]
        .calculation.response.value.next_prefix_ref.model_dump(
            mode="json", by_alias=True
        ),
        "targetEventId": str(saved.source_event_id),
        "targetPlayId": saved.calculation.request.play_identity.play_id,
        "originalResultId": saved.calculation.request.t1.result_id,
        "replacementResultId": "batting-result.ball",
        "replacementObservations": saved.payload.observations.model_dump(
            mode="json", by_alias=True
        ),
    }


def test_p3_preparation_binds_current_source_and_real_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同scope真正原本から現在head/明示本文/既artifact/物理行を一度に束縛する。"""
    with _host() as host:
        old = _two_saved(host)
    first = old[0]
    tenant = UUID(first.calculation.request.prefix_ref.tenant_id)
    game = UUID(first.calculation.request.prefix_ref.game_id)
    rows = tuple(
        replace(
            saved,
            play_row=pitch_physical_row(
                saved.payload.observations,
                saved.payload.participants,
                saved.calculation.request.t1.result_id,
                tenant_id=tenant,
                game_id=game,
                source_event_id=saved.source_event_id,
                row_id=UUID(saved.calculation.request.play_identity.play_id),
                play_number=index,
            ),
        )
        for index, saved in enumerate(old, start=1)
        if saved.payload is not None
    )
    assert len(rows) == 2

    class Scope:
        _bound_tenant_id = tenant

    monkeypatch.setattr(past_correction_preparation, "_TenantTransaction", Scope)
    monkeypatch.setattr(
        past_correction_preparation,
        "read_past_correction_v3_source_snapshot",
        lambda *_: PastCorrectionV3SourceSnapshot(1, rows),
    )
    body = _change_body(rows, 1)
    event = SyncEvent(
        str(_CHANGE),
        str(game),
        v5="play_change",
        v7=body,
        v10={
            "game": str(game),
            "d4": 1,
            "d1": 1,
        },
        v11=1,
    )
    prepared = past_correction_preparation.prepare_p3_lineup_correction(
        cast(_TenantTransaction, Scope()),
        event,
        capsule_id=_CAPSULE,
        change_event_id=_CHANGE,
    )
    assert prepared.target_d1 == 1
    assert len(prepared.corrected) == len(prepared.physical) == 2
    assert prepared.physical[0].effective_event_id == _CHANGE
    assert prepared.corrected[1].corrected_request.prefix_ref == (
        prepared.corrected[0].corrected_response.value.next_prefix_ref
    )
    monkeypatch.setattr(
        past_correction_preparation,
        "read_past_correction_v3_source_snapshot",
        lambda *_: PastCorrectionV3SourceSnapshot(2, rows),
    )
    with pytest.raises(
        past_correction_preparation.PastCorrectionPreparationUnavailable
    ):
        past_correction_preparation.prepare_p3_lineup_correction(
            cast(_TenantTransaction, Scope()),
            event,
            capsule_id=_CAPSULE,
            change_event_id=_CHANGE,
        )
    monkeypatch.setattr(
        past_correction_preparation,
        "read_past_correction_v3_source_snapshot",
        lambda *_: PastCorrectionV3SourceSnapshot(1, rows),
    )
    forged = SyncEvent(
        event.d5,
        event.game_id,
        v5="play_change",
        v7={**body, "targetEventId": str(_CAPSULE)},
        v10=event.v10,
        v11=1,
    )
    with pytest.raises(
        past_correction_preparation.PastCorrectionPreparationUnavailable
    ):
        past_correction_preparation.prepare_p3_lineup_correction(
            cast(_TenantTransaction, Scope()),
            forged,
            capsule_id=_CAPSULE,
            change_event_id=_CHANGE,
        )


def test_v3_change_payload_binds_real_target_and_current_head() -> None:
    """対象2球目の明示変更が旧原本と現在headに一致した時だけ通す。"""
    with _host() as host:
        rows = _two_saved(host)
    body = _change_body(rows, 2)
    payload = read_lineup_pitch_change_payload(json.dumps(body))
    bind_lineup_pitch_change_payload(
        payload, rows, 2, rows[-1].calculation.response.value.next_prefix_ref
    )
    for field, changed in (
        ("targetEventId", str(_CHANGE)),
        ("originalResultId", "batting-result.ball"),
    ):
        forged = {**body, field: changed}
        parsed = read_lineup_pitch_change_payload(json.dumps(forged))
        with pytest.raises(PastCorrectionPayloadError):
            bind_lineup_pitch_change_payload(
                parsed, rows, 2, rows[-1].calculation.response.value.next_prefix_ref
            )
    stale_head = rows[0].calculation.response.value.next_prefix_ref
    with pytest.raises(PastCorrectionPayloadError):
        bind_lineup_pitch_change_payload(payload, rows, 2, stale_head)


@pytest.mark.parametrize("malformed", ["duplicate", "unknown", "wrong-type"])
def test_v3_change_payload_rejects_ambiguous_wire(malformed: str) -> None:
    """重複key・未知member・数値化を本文で補修しない。"""
    with _host() as host:
        rows = _two_saved(host)
    body = _change_body(rows, 1)
    if malformed == "duplicate":
        raw = json.dumps(body)[:-1] + ',"targetEventId":"' + str(_CHANGE) + '"}'
    elif malformed == "unknown":
        raw = json.dumps({**body, "future": True})
    else:
        body["expectedPrefixRef"]["length"] = 2
        raw = json.dumps(body)
    with pytest.raises(PastCorrectionPayloadError):
        read_lineup_pitch_change_payload(raw)


@pytest.mark.parametrize("target", [0, 3, True])
def test_v3_correction_rejects_unknown_target(target: int) -> None:
    """対象位置の曖昧な補完やboolの整数化を認めない。"""
    with _host() as host, pytest.raises(LineupCorrectionUnsupported):
        _evaluate(
            _two_saved(host),
            "batting-result.ball",
            (_NEW2,),
            host,
            target_d1=target,
        )


@pytest.mark.parametrize("mutation", ["id", "d2", "old-after", "old-response"])
def test_v3_replay_rejects_forged_old_source(mutation: str) -> None:
    """旧原本参照・応答・前後連鎖を補修せず閉じる。"""
    with _host() as host:
        first, second = _two_saved(host)
        if mutation == "id":
            second = SavedLineupPitch(_NEW1, 2, 2, second.calculation)
        elif mutation == "d2":
            second = SavedLineupPitch(_ID2, 2, 1, second.calculation)
        else:
            raw = second.calculation.model_dump(mode="json", by_alias=True)
            if mutation == "old-after":
                raw["request"]["source"]["after"] = (
                    first.calculation.request.source.after.model_dump(
                        mode="json", by_alias=True
                    )
                )
                raw["request"]["t1"]["before"] = raw["request"]["source"]["after"]
            else:
                raw["response"]["value"]["t1"]["after"]["stateFields"][
                    "state.count.strikes"
                ] = "2"
            try:
                second = SavedLineupPitch(
                    _ID2, 2, 2, LineupPitchCalculation.model_validate(raw)
                )
            except ValueError:
                return
        with pytest.raises(LineupCorrectionUnsupported):
            _evaluate((first, second), "batting-result.ball", (_NEW1, _NEW2), host)
