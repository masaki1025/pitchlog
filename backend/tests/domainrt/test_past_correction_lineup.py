"""既v3 artifactによる過去1球変更と後続再生の有限境界。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
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
    CorrectionPageState,
    LineupCorrectionUnsupported,
    SavedLineupPitch,
    _evaluate,
    _evaluate_page,
    _next_corrected_request,
    build_corrected_lineup_payloads,
)
from pitchlog.repositories.past_correction_source import PastCorrectionV3SourceSnapshot
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync import past_correction_paged, past_correction_preparation
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.past_correction_capsule import (
    build_p3_current_capsule,
    build_p3_current_item,
)
from pitchlog.sync.past_correction_checkpoint import (
    build_corrected_lineup_checkpoint,
    build_corrected_lineup_checkpoint_from_head,
)
from pitchlog.sync.past_correction_paged import (
    PreparedP3Page,
    _page_seal,
    fingerprint_p3_streaming_array,
)
from pitchlog.sync.past_correction_payload import (
    PastCorrectionPayloadError,
    bind_lineup_pitch_change_payload,
    bind_lineup_pitch_change_target,
    read_lineup_pitch_change_payload,
)
from pitchlog.sync.past_correction_physical import prepare_corrected_physical_pitches
from pitchlog.sync.past_correction_stats import (
    P3StatsSourceCandidate,
    evaluate_p3_capsule_stats,
    evaluate_p3_current_item_stats,
)
from pitchlog.sync.terminal_pitch_payload import (
    LineupPitchCalculation,
    LineupPitchPlayPayload,
)
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

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


def _twenty_six_saved(host: NodeDomainHost) -> tuple[SavedLineupPitch, ...]:
    """既唯一hostの連続成功値だけから26球の旧原本を構成する。"""
    saved = list(_two_saved(host))
    previous = saved[-1].calculation.response
    second = _CASES["V3-STARTED-CHAIN-02"]["request"]
    for d1 in range(3, 27):
        request_value = deepcopy(second)
        request_value["source"]["position"] = {
            "d1": str(d1),
            "d2": str(d1),
            "appliedWatermark": str(d1 - 1),
        }
        event_id = UUID(int=7000 + d1 * 3)
        request_value["playIdentity"] = {
            "eventId": str(event_id),
            "d5": str(UUID(int=7001 + d1 * 3)),
            "playId": str(UUID(int=7002 + d1 * 3)),
        }
        request_value["nextCheckpoint"]["revision"] = str(d1 + 1)
        template = decode_lineup_prefix_request(json.dumps(request_value))
        result = (
            "batting-result.called-strikeout"
            if previous.value.t1.after.state_fields.strikes == "2"
            else "batting-result.called-pitch"
        )
        request = _next_corrected_request(
            template, previous, result, UUID(int=600 + d1), host.artifact_sha256
        )
        response = decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                request.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
        assert type(response) is LineupPrefixSuccess
        request, response = seal_lineup_wire(request, response)
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
        saved.append(SavedLineupPitch(event_id, d1, d1, calculation))
        previous = response
    return tuple(saved)


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


@pytest.mark.parametrize("target", [1, 2])
def test_v3_page_boundary_preserves_the_same_old_and_corrected_chain(
    target: int,
) -> None:
    """対象が頁の前後どちらでも同じ唯一hostの旧/新連鎖を維持する。"""
    with _host() as host:
        old = _two_saved(host)
        ids = (_NEW1, _NEW2) if target == 1 else (_NEW2,)
        expected = _evaluate(old, "batting-result.ball", ids, host, target_d1=target)
        state, first = _evaluate_page(
            old[:1],
            "batting-result.ball",
            (_NEW1,) if target == 1 else (),
            host,
            CorrectionPageState(),
            target_d1=target,
        )
        state, second = _evaluate_page(
            old[1:],
            "batting-result.ball",
            (_NEW2,),
            host,
            state,
            target_d1=target,
        )
    assert first + second == expected
    assert state.last_d1 == 2
    assert state.last_d2 == old[-1].d2
    assert state.previous_original == old[-1].calculation.response
    assert state.previous_corrected == expected[-1].corrected_response


def test_v3_page_boundary_rejects_a_changed_target_and_missing_d1() -> None:
    """頁間の対象差替えと位置欠落を次の成功へ読み替えない。"""
    with _host() as host:
        old = _two_saved(host)
        state, _ = _evaluate_page(
            old[:1], "batting-result.ball", (), host, CorrectionPageState(),
            target_d1=2,
        )
        with pytest.raises(LineupCorrectionUnsupported):
            _evaluate_page(
                old[1:], "batting-result.ball", (), host, state, target_d1=3,
            )
        with pytest.raises(LineupCorrectionUnsupported):
            _evaluate_page(
                (replace(old[1], d1=3),), "batting-result.ball", (), host,
                state, target_d1=2,
            )
        with pytest.raises(LineupCorrectionUnsupported):
            _evaluate_page(
                old[1:], "batting-result.ball", (_NEW2,), host,
                replace(state, previous_original=None), target_d1=2,
            )


def test_v3_target_26_uses_two_bounded_pages_and_the_same_real_host() -> None:
    """26球目を旧25件目の実応答から評価し、25件上限を試合上限にしない。"""
    with _host() as host:
        old = _twenty_six_saved(host)
        state, first = _evaluate_page(
            old[:25], "batting-result.ball", (), host, CorrectionPageState(),
            target_d1=26,
        )
        state, second = _evaluate_page(
            old[25:], "batting-result.ball", (UUID(int=9900),), host,
            state, target_d1=26,
        )
    assert first == ()
    assert len(second) == 1
    assert second[0].source_event_id == old[25].source_event_id
    assert second[0].corrected_request.prefix_ref == (
        old[24].calculation.response.value.next_prefix_ref
    )
    assert second[0].corrected_request.t1.result_id == "batting-result.ball"
    assert state.last_d1 == 26
    assert state.previous_original == old[25].calculation.response
    assert state.previous_corrected == second[0].corrected_response


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
    assert isinstance(new[0].observations, FirstBallObservations)
    assert new[0].observations.course.x == "130"
    assert new[1].observations == old[1].payload.observations
    assert new[0].calculation.request.t1.result_id == "batting-result.ball"
    assert new[1].calculation.request.t1.result_id == "batting-result.called-pitch"
    suffix = build_corrected_lineup_payloads(
        old[1:], frames[1:], replacement, target_d1=1
    )
    assert suffix == new[1:]


def test_v3_corrected_payload_rejects_missing_original_v7() -> None:
    """計算だけの候補を物理投影の保存元として昇格させない。"""
    with _host() as host:
        old = _two_saved(host)
        frames = _evaluate(old, "batting-result.ball", (_NEW1, _NEW2), host)
    assert old[0].payload is not None
    assert isinstance(old[0].payload.observations, FirstBallObservations)
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


def test_v3_physical_candidate_uses_existing_mappers_and_new_row_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """訂正対象を別PKで作り、後続の物理全値同一なら元行を再利用する。"""
    with _host() as host:
        old = _two_saved(host)
        frames = _evaluate(old, "batting-result.ball", (_NEW1, _NEW2), host)
    assert old[0].payload is not None and old[1].payload is not None
    tenant = UUID(old[0].calculation.request.prefix_ref.tenant_id)
    game = UUID(old[0].calculation.request.prefix_ref.game_id)

    def with_row(saved: SavedLineupPitch, index: int) -> SavedLineupPitch:
        assert saved.payload is not None
        request = saved.calculation.request
        row_id = UUID(request.play_identity.play_id)
        return replace(
            saved,
            play_row=pitch_physical_row(
                saved.payload.observations,
                saved.payload.participants,
                saved.calculation.request.t1.result_id,
                tenant_id=tenant,
                game_id=game,
                source_event_id=saved.source_event_id,
                row_id=row_id,
                play_number=index,
            ),
            play_runners=tuple(
                runner_physical_rows(
                    request.source.runners,
                    t1=saved.calculation.response.value.t1,
                    t1_input=request.t1,
                    tenant_id=tenant,
                    play_id=row_id,
                )
            ),
        )

    original = tuple(with_row(saved, index) for index, saved in enumerate(old, start=1))
    assert isinstance(old[0].payload.observations, FirstBallObservations)
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
    assert result[0].new_play_row_id != result[0].original_play_row_id
    assert result[1].new_play_row_id == result[1].original_play_row_id
    assert [item.play_row["batting_result_key"] for item in result] == [
        "batting-result.ball",
        "batting-result.called-pitch",
    ]
    assert [item.play_row["play_number"] for item in result] == [1, 2]
    assert all(item.play_row["id"] == str(item.new_play_row_id) for item in result)
    suffix = prepare_corrected_physical_pitches(
        original[1:],
        frames[1:],
        payloads[1:],
        tenant_id=tenant,
        game_id=game,
        capsule_id=_CAPSULE,
        change_event_id=_CHANGE,
        target_d1=1,
    )
    assert suffix == result[1:]
    first_seal = _page_seal(
        "0" * 64, PreparedP3Page(original[:1], frames[:1], payloads[:1], result[:1])
    )
    second_seal = _page_seal(
        first_seal, PreparedP3Page(original[1:], frames[1:], payloads[1:], suffix)
    )
    assert second_seal == _page_seal(
        first_seal, PreparedP3Page(original[1:], frames[1:], payloads[1:], suffix)
    )
    assert second_seal != _page_seal(
        first_seal,
        PreparedP3Page(
            original[1:],
            frames[1:],
            payloads[1:],
            (replace(suffix[0], effective_event_id=_CHANGE),),
        ),
    )
    class Scope:
        _bound_tenant_id = tenant

    def read_pages(_scope, _game, _target, consume):
        checkpoint = SimpleNamespace(
            prefix_ref=original[-1].calculation.response.value.next_prefix_ref,
            content_digest="d" * 64,
        )
        consume(original[:1], checkpoint)
        consume(original[1:], checkpoint)
        return SimpleNamespace(
            internal_generation=1,
            watermark=2,
            checkpoint=checkpoint,
        )

    monkeypatch.setattr(past_correction_paged, "_TenantTransaction", Scope)
    monkeypatch.setattr(
        past_correction_paged, "_bound_target", lambda *_: (game, 1, 1)
    )
    monkeypatch.setattr(
        past_correction_paged, "visit_past_correction_v3_source_pages", read_pages
    )
    monkeypatch.setattr(
        past_correction_paged,
        "build_corrected_lineup_checkpoint_from_head",
        lambda *_: SimpleNamespace(id="next", content_digest="e" * 64),
    )
    monkeypatch.setattr(
        past_correction_paged,
        "build_p3_current_item",
        lambda saved, **_kwargs: {
            "d1": saved.d1,
            "digest": source_fingerprint({"d1": saved.d1}),
        },
    )
    monkeypatch.setattr(
        past_correction_paged,
        "evaluate_p3_current_item_stats",
        lambda item, d1: P3StatsSourceCandidate(
            d1,
            original[d1 - 1].source_event_id,
            original[d1 - 1].source_event_id,
            UUID(int=d1),
            {},
            "b" * 64,
            {},
            "c" * 64,
        ),
    )
    event = SyncEvent(
        str(_CHANGE), str(game), v5="play_change", v7=_change_body(original, 1)
    )
    pages: list[PreparedP3Page] = []
    proof = past_correction_paged.visit_p3_lineup_correction_pages(
        cast(_TenantTransaction, Scope()),
        event,
        capsule_id=_CAPSULE,
        change_event_id=_CHANGE,
        bound_source=object(),
        consume=pages.append,
    )
    assert proof.page_count == 2
    assert proof.watermark == 2
    assert [len(page.originals) for page in pages] == [1, 1]
    assert original[1].payload is not None
    assert pages[1].payloads[0].observations == original[1].payload.observations
    assert pages[1].physical[0].effective_event_id == original[1].source_event_id
    assert pages[1].physical[0].play_row == original[1].play_row
    replay = past_correction_paged.visit_p3_lineup_correction_pages(
        cast(_TenantTransaction, Scope()),
        event,
        capsule_id=_CAPSULE,
        change_event_id=_CHANGE,
        bound_source=object(),
        consume=lambda _page: None,
    )
    assert replay == proof
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
        "expectedPrefixRef": rows[
            -1
        ].calculation.response.value.next_prefix_ref.model_dump(
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
            play_runners=tuple(
                runner_physical_rows(
                    saved.calculation.request.source.runners,
                    t1=saved.calculation.response.value.t1,
                    t1_input=saved.calculation.request.t1,
                    tenant_id=tenant,
                    play_id=UUID(saved.calculation.request.play_identity.play_id),
                )
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
    assert deepcopy(prepared) == prepared
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
    with pytest.raises(past_correction_preparation.PastCorrectionContentRejected):
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
    bind_lineup_pitch_change_target(
        payload, rows[1], 2, 2, rows[-1].calculation.response.value.next_prefix_ref
    )
    with pytest.raises(PastCorrectionPayloadError):
        bind_lineup_pitch_change_target(
            payload, rows[1], 2, 3, rows[-1].calculation.response.value.next_prefix_ref
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


def test_v3_change_payload_accepts_saved_called_strikeout_only_as_original() -> None:
    """既保存三振は元結果として読めるが、未知値と未接続の置換値は閉じる。"""
    with _host() as host:
        rows = _two_saved(host)
    body = _change_body(rows, 1)
    body["originalResultId"] = "batting-result.called-strikeout"
    parsed = read_lineup_pitch_change_payload(json.dumps(body))
    assert parsed.original_result_id == "batting-result.called-strikeout"
    with pytest.raises(PastCorrectionPayloadError):
        bind_lineup_pitch_change_payload(
            parsed, rows, 1, rows[-1].calculation.response.value.next_prefix_ref
        )
    for field in ("originalResultId", "replacementResultId"):
        forged = {**body, field: "batting-result.unknown"}
        with pytest.raises(PastCorrectionPayloadError):
            read_lineup_pitch_change_payload(json.dumps(forged))
    forged = {**body, "replacementResultId": "batting-result.called-strikeout"}
    with pytest.raises(PastCorrectionPayloadError):
        read_lineup_pitch_change_payload(json.dumps(forged))


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


def test_v3_corrected_checkpoint_uses_native_chain_and_new_physical_head() -> None:
    """実二球再評価の末尾だけを新CPへ写し、元IDと物理PKを区別する。"""
    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.repositories.play_prefix import read_lineup_prefix_document
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.past_correction_preparation import PreparedP3LineupCorrection
    from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

    with _host() as host:
        original = _two_saved(host)
        rows = []
        for saved in original:
            payload = saved.payload
            assert payload is not None
            request = saved.calculation.request
            physical = pitch_physical_row(
                payload.observations,
                payload.participants,
                request.t1.result_id,
                tenant_id=UUID(request.prefix_ref.tenant_id),
                game_id=UUID(request.prefix_ref.game_id),
                source_event_id=saved.source_event_id,
                row_id=UUID(request.play_identity.play_id),
                play_number=saved.d1,
            )
            runners = runner_physical_rows(
                request.source.runners,
                t1=saved.calculation.response.value.t1,
                t1_input=request.t1,
                tenant_id=UUID(request.prefix_ref.tenant_id),
                play_id=UUID(request.play_identity.play_id),
            )
            rows.append(replace(saved, play_row=physical, play_runners=tuple(runners)))
        saved_rows = tuple(rows)
        last = saved_rows[-1]
        old_value = last.calculation.response.value
        old_ref = old_value.next_prefix_ref
        old_request = last.calculation.request
        raw = {
            "version": "3",
            "id": old_ref.checkpoint.id,
            "revision": old_ref.checkpoint.revision,
            "history_version": "1",
            "storage_anchor": {"id": old_ref.checkpoint.id, "history_epoch": "1"},
            "prefix_ref": old_ref.model_dump(mode="json", by_alias=True),
            "wire_d4": old_ref.generation,
            "internal_generation": "1",
            "recovery_generation": "1",
            "confirmed_watermark": "2",
            "applied_watermark": "2",
            "last_source": {
                "id": str(last.source_event_id),
                "tenant_id": old_ref.tenant_id,
                "game_id": old_ref.game_id,
                "generation": "1",
                "d1": "2",
                "d2": "2",
                "d5": old_request.play_identity.d5,
                "source_fingerprint": "f" * 64,
                "event_fingerprint": "f" * 64,
            },
            "history_depth": old_ref.length,
            "after": old_value.t1.after.model_dump(mode="json", by_alias=True),
            "rules": old_request.rules.model_dump(mode="json", by_alias=True),
            "t2": old_value.t2.model_dump(mode="json", by_alias=True),
            "runners": [
                r.model_dump(mode="json", by_alias=True) for r in old_value.runners
            ],
            "participants": old_value.participants.model_dump(
                mode="json", by_alias=True
            ),
            "pa_start_source": old_value.next_responsibility.pa_start_source.model_dump(
                mode="json", by_alias=True
            ),
            "lineup": old_value.lineup.model_dump(mode="json", by_alias=True),
            "roster_digest": old_value.roster_digest,
            "roster_source_digest": "e" * 64,
            "source_origin": old_ref.origin.model_dump(mode="json", by_alias=True),
            "previous_prefix_ref": old_value.previous_prefix_ref.model_dump(
                mode="json", by_alias=True
            ),
            "artifact_sha256": old_value.execution_artifact_sha256,
            "state": "current",
            "projection_snapshot": {
                "play_row": last.play_row,
                "play_runners": [],
            },
        }
        raw["content_digest"] = source_fingerprint(raw)
        old_checkpoint = read_lineup_prefix_document(_canonical_json(raw))
        corrected = _evaluate(saved_rows, "batting-result.ball", (_NEW1, _NEW2), host)
        assert saved_rows[0].payload is not None
        observations = saved_rows[0].payload.observations
        assert isinstance(observations, FirstBallObservations)
        payloads = build_corrected_lineup_payloads(saved_rows, corrected, observations)
        physical = prepare_corrected_physical_pitches(
            saved_rows,
            corrected,
            payloads,
            tenant_id=UUID(old_ref.tenant_id),
            game_id=UUID(old_ref.game_id),
            capsule_id=_CAPSULE,
            change_event_id=_CHANGE,
        )
        with pytest.raises(LineupCorrectionUnsupported):
            prepare_corrected_physical_pitches(
                (saved_rows[0], replace(saved_rows[1], play_runners=None)),
                corrected,
                payloads,
                tenant_id=UUID(old_ref.tenant_id),
                game_id=UUID(old_ref.game_id),
                capsule_id=_CAPSULE,
                change_event_id=_CHANGE,
            )
    prepared = PreparedP3LineupCorrection(
        _CAPSULE,
        _CHANGE,
        1,
        1,
        saved_rows,
        corrected,
        payloads,
        physical,
        old_checkpoint,
    )
    fresh = build_corrected_lineup_checkpoint(prepared)
    assert fresh == build_corrected_lineup_checkpoint_from_head(
        old_checkpoint, saved_rows[-1], corrected[-1], physical[-1], 2
    )
    assert fresh.id == old_checkpoint.id
    assert fresh.prefix_ref.checkpoint.id == (
        corrected[-1].corrected_response.value.next_prefix_ref.checkpoint.id
    )
    assert fresh.after == corrected[-1].corrected_response.value.t1.after
    assert fresh.projection_snapshot is not None
    assert fresh.projection_snapshot.play_row == physical[-1].play_row
    assert fresh.last_source == old_checkpoint.last_source
    capsule = build_p3_current_capsule(prepared)
    assert capsule.next_checkpoint == fresh
    assert len(capsule.items) == 2
    assert capsule.items[0]["original_event_id"] == str(_ID1)
    assert capsule.items[0]["effective_event_id"] == str(_CHANGE)
    assert capsule.items[1]["original_event_id"] == str(_ID2)
    assert capsule.items[1]["effective_event_id"] == str(_ID2)
    assert capsule.items[1]["play_row"] == physical[-1].play_row
    assert capsule.items[1] == build_p3_current_item(
        saved_rows[1],
        target_d1=1,
        change_event_id=_CHANGE,
        checkpoint=old_checkpoint,
        frame=corrected[1],
        payload=payloads[1],
        projected=physical[1],
    )
    assert capsule.source_set_digest == fingerprint_p3_streaming_array(
        {"capsule_id": str(_CAPSULE), "change_event_id": str(_CHANGE)},
        "item_digests",
        (item["digest"] for item in capsule.items),
        {
            "new_checkpoint_digest": fresh.content_digest,
            "old_checkpoint_digest": old_checkpoint.content_digest,
        },
    )
    assert saved_rows[-1].play_row is not None
    assert capsule.items[1]["effective_play_row_id"] == saved_rows[-1].play_row["id"]
    assert capsule.items[0]["original_play_row"] == saved_rows[0].play_row
    assert saved_rows[0].play_runners is not None
    assert capsule.items[0]["original_play_runners"] == list(saved_rows[0].play_runners)
    assert saved_rows[0].payload is not None
    assert capsule.items[0]["original_payload"] == saved_rows[0].payload.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    stats = evaluate_p3_capsule_stats(capsule)
    assert stats.sources[0] == evaluate_p3_current_item_stats(capsule.items[0], 1)
    assert stats.evaluation_set_digest != capsule.source_set_digest
    assert [source.effective_event_id for source in stats.sources] == [_CHANGE, _ID2]
    assert all(source.evaluation for source in stats.sources)
    from pitchlog.stats.facts import evaluate_native_projection

    assert saved_rows[0].payload is not None
    old_stats = evaluate_native_projection(
        saved_rows[0].payload.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ),
        source_event_id=_CHANGE,
    )
    old_stats["native_rule_sha256"] = source_fingerprint(
        saved_rows[0].payload.calculation.request.rules.model_dump(
            mode="json", by_alias=True
        )
    )
    # この2値は現T5の27群では同じ寄与。版/有効source IDは別に更新が必要。
    assert stats.sources[0].evaluation == old_stats
