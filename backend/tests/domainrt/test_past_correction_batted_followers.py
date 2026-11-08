"""真正の保存打球を唯一artifactで訂正系列へ再評価する有限対向。"""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from domainrt.test_past_correction_lineup import _host, _two_saved
from test_batted_hit_prefix_payload import observations

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
    _bound_original,
    _corrected_payload,
    _evaluate,
    _evaluate_page,
    _next_corrected_request,
    build_corrected_lineup_payloads,
)
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.terminal_pitch_payload import (
    BattedHitPlayObservations,
    LineupPitchCalculation,
    format_batted_hit_prefix_payload,
    read_lineup_pitch_payload,
)

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = json.loads(
    (_ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]
_HITS = ("single", "double", "triple", "home-run")


def _hit(host, previous, result="single", destination=None):
    """原観測だけを提出し、after/走者/差分は実hostの応答から得る。"""
    d1 = previous.d1 + 1
    raw = deepcopy(_TEMPLATE["request"])
    raw["t1"]["resultId"] = "batting-result." + result
    if destination is not None:
        raw["t1"]["runnerAdvanceOverrides"] = {
            "kind": "applied",
            "overrides": [{"runnerBase": "1", "destination": destination}],
        }
    raw["playIdentity"] = {
        "eventId": str(UUID(int=3000 + d1 * 3)),
        "d5": str(UUID(int=3001 + d1 * 3)),
        "playId": str(UUID(int=3002 + d1 * 3)),
    }
    raw["source"]["position"] = {
        "d1": str(d1),
        "d2": str(d1),
        "appliedWatermark": str(d1 - 1),
    }
    raw["nextCheckpoint"]["revision"] = str(d1 + 1)
    q = _next_corrected_request(
        decode_lineup_prefix_request(json.dumps(raw)),
        previous.calculation.response,
        None,
        UUID(int=4000 + d1),
        host.artifact_sha256,
    )
    r = decode_lineup_prefix_response(
        host.call(
            "deriveLineupPlayPrefixWithContinuation",
            q.model_dump_json(by_alias=True, exclude_unset=True),
        )
    )
    assert type(r) is LineupPrefixSuccess, r
    q, r = seal_lineup_wire(q, r)
    calc = LineupPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": host.artifact_sha256,
                "request": q.model_dump(mode="json", by_alias=True, exclude_unset=True),
                "response": r.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
        )
    )
    observed = observations({"request": raw})
    if destination is not None:
        observed["runnerAdvanceOverridesByRunner"] = raw["t1"]["runnerAdvanceOverrides"]
    obs = BattedHitPlayObservations.model_validate_json(json.dumps(observed))
    v7, v8 = format_batted_hit_prefix_payload(obs, calc)
    payload = read_lineup_pitch_payload(v7, v8, expected_calculation=calc)
    return SavedLineupPitch(UUID(q.play_identity.event_id), d1, d1, calc, payload)


def _correct(host, rows):
    return _evaluate(
        rows,
        "batting-result.ball",
        tuple(UUID(int=5000 + i) for i in range(len(rows))),
        host,
    )


@pytest.mark.parametrize("hit", _HITS)
def test_four_saved_hits_are_followers_not_correction_targets(hit):
    """4安打を実再生し、同じ原観測と元IDの新系列へ束縛する。"""
    with _host() as host:
        first = _two_saved(host)[0]
        second = _hit(host, first, hit)
        rows = (first, second)
        corrected = _correct(host, rows)
        assert corrected[0].corrected_response.value.t1.after.state_fields.balls == "1"
        assert (
            corrected[0].corrected_response.value.t1.after.state_fields.strikes == "0"
        )
        assert first.calculation.response.value.t1.after.state_fields.strikes == "1"
        assert first.payload is not None and second.payload is not None
        assert type(first.payload.observations) is FirstBallObservations
        payloads = build_corrected_lineup_payloads(
            rows, corrected, first.payload.observations
        )
        assert payloads[1].observations == second.payload.observations
        assert payloads[1].participants == second.payload.participants
        assert corrected[1].source_event_id == second.source_event_id
        assert corrected[1].corrected_request.t1.result_id == "batting-result." + hit
        assert (
            corrected[1].corrected_response.value.t1.after
            == second.calculation.response.value.t1.after
        )
        # 対象を安打へ拡張しない。
        with pytest.raises(LineupCorrectionUnsupported):
            _evaluate(rows, "batting-result.ball", (UUID(int=6001),), host, target_d1=2)


def test_explicit_non_scoring_runner_observation_is_preserved():
    """一塁走者の三塁到達を推測せず元の明示観測で再評価する。"""
    with _host() as host:
        first = _two_saved(host)[0]
        single = _hit(host, first)
        next_hit = _hit(host, single, destination="3")
        rows = (first, single, next_hit)
        corrected = _correct(host, rows)
        assert first.payload is not None and next_hit.payload is not None
        assert type(first.payload.observations) is FirstBallObservations
        payloads = build_corrected_lineup_payloads(
            rows, corrected, first.payload.observations
        )
        assert payloads[-1].observations == next_hit.payload.observations
        assert (
            corrected[-1].corrected_response.value.t1.after.state_fields.runners
            == "first-third"
        )


def test_scoring_legacy_observation_is_replayable_but_not_new_correction():
    """旧保存を再生できても欠測RBIを新訂正へ暗黙補完しない。"""
    with _host() as host:
        first = _two_saved(host)[0]
        single = _hit(host, first)
        double = _hit(host, single, "double", "4")
        _bound_original(double, single.calculation.response, host, allow_batted=True)
        with pytest.raises(LineupCorrectionUnsupported, match="観測と計算"):
            _correct(host, (first, single, double))


@pytest.mark.parametrize(
    "mutation", ("missing", "observations", "identity", "response")
)
def test_saved_batted_damage_is_closed(mutation):
    """元V7/応答/イベント参照を外した打球を成功へ流さない。"""
    with _host() as host:
        first = _two_saved(host)[0]
        hit = _hit(host, first)
        assert first.payload is not None and hit.payload is not None
        if mutation == "missing":
            hit = replace(hit, payload=None)
        elif mutation == "observations":
            hit = replace(
                hit,
                payload=hit.payload.model_copy(
                    update={"observations": first.payload.observations}
                ),
            )
        elif mutation == "identity":
            hit = replace(hit, source_event_id=UUID(int=8000))
        else:
            bad = hit.calculation.response.model_copy(
                update={"value": first.calculation.response.value}
            )
            hit = replace(
                hit, calculation=hit.calculation.model_copy(update={"response": bad})
            )
        with pytest.raises((LineupCorrectionUnsupported, ValueError)):
            _correct(host, (first, hit))


def test_runner_identity_must_survive_correction_and_page_boundary():
    """ページ持越しも実応答だけを使い、同じ塁の別走者へ観測を転用しない。"""
    with _host() as host:
        first = _two_saved(host)[0]
        single = _hit(host, first)
        next_hit = _hit(host, single, destination="3")
        state, prefix = _evaluate_page(
            (first, single),
            "batting-result.ball",
            (UUID(int=9000), UUID(int=9001)),
            host,
            CorrectionPageState(),
            target_d1=1,
        )
        _, tail = _evaluate_page(
            (next_hit,),
            "batting-result.ball",
            (UUID(int=9002),),
            host,
            state,
            target_d1=1,
        )
        assert len(prefix) == 2 and len(tail) == 1
        frame = tail[0]
        assert next_hit.payload is not None
        # Frozen sourceの改変コピーを資格に採らない。runner全値不一致を直接対向。
        altered_source = frame.corrected_request.source.model_copy(
            update={"runners": single.calculation.request.source.runners}
        )
        altered = replace(
            frame,
            corrected_request=frame.corrected_request.model_copy(
                update={"source": altered_source}
            ),
        )
        with pytest.raises(LineupCorrectionUnsupported, match="走者"):
            _corrected_payload(next_hit, altered, next_hit.payload.observations)


@pytest.mark.parametrize("mutation", ("participant", "lineup", "unknown-hit", "rbi"))
def test_corrected_observations_cannot_be_rebound_to_other_context(mutation):
    """別参加者/名簿/未知打球/原観測にないRBIを新資格へ持ち込めない。"""
    with _host() as host:
        first = _two_saved(host)[0]
        hit = _hit(host, first)
        frames = _correct(host, (first, hit))
        frame = frames[-1]
        assert hit.payload is not None
        if mutation in {"participant", "lineup"}:
            field = "participants" if mutation == "participant" else "lineup"
            old_value = getattr(frame.corrected_request.source, field)
            # 期待する実型そのものを保持し、値が異なる原本を生成する。
            wire = old_value.model_dump(mode="json", by_alias=True, exclude_unset=True)

            def change_identifier(value):
                if type(value) is dict:
                    for key, member in value.items():
                        if type(member) is str and len(member) == 36:
                            value[key] = str(UUID(int=8888))
                            return True
                        if change_identifier(member):
                            return True
                elif type(value) is list:
                    for member in value:
                        if change_identifier(member):
                            return True
                return False

            assert change_identifier(wire)
            changed = type(old_value).model_validate_json(json.dumps(wire))
            source = frame.corrected_request.source.model_copy(update={field: changed})
            frame = replace(
                frame,
                corrected_request=frame.corrected_request.model_copy(
                    update={"source": source}
                ),
            )
        elif mutation == "unknown-hit":
            t1 = frame.corrected_request.t1.model_copy(
                update={"result_id": "batting-result.batted-out"}
            )
            frame = replace(
                frame,
                corrected_request=frame.corrected_request.model_copy(update={"t1": t1}),
            )
        else:
            observed = hit.payload.observations.model_copy(
                update={"rbi_ruling_by_runner": {"1": "ordinary-play"}}
            )
            with pytest.raises(LineupCorrectionUnsupported):
                _corrected_payload(hit, frame, observed)
            return
        with pytest.raises(LineupCorrectionUnsupported):
            _corrected_payload(hit, frame, hit.payload.observations)


@pytest.mark.parametrize("hit", _HITS + ("runner-third",))
def test_corrected_hits_use_unchanged_single_physical_and_t5_pipeline(hit):
    """後続41列/runnerを既mapperで全比較し、既T5だけへ候補を渡す。"""
    from pitchlog.stats.facts import evaluate_native_projection
    from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
    from pitchlog.sync.past_correction_physical import (
        prepare_corrected_physical_pitches,
    )
    from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

    with _host() as host:
        first = _two_saved(host)[0]
        if hit == "runner-third":
            single = _hit(host, first)
            original = (first, single, _hit(host, single, destination="3"))
        else:
            original = (first, _hit(host, first, hit))
        tenant = UUID(first.calculation.request.prefix_ref.tenant_id)
        game = UUID(first.calculation.request.prefix_ref.game_id)
        rows = []
        for row in original:
            assert row.payload is not None
            q, r = row.calculation.request, row.calculation.response
            row_id = UUID(q.play_identity.play_id)
            rows.append(
                replace(
                    row,
                    play_row=pitch_physical_row(
                        row.payload.observations,
                        row.payload.participants,
                        q.t1.result_id,
                        tenant_id=tenant,
                        game_id=game,
                        source_event_id=row.source_event_id,
                        row_id=row_id,
                        play_number=row.d1,
                    ),
                    play_runners=tuple(
                        runner_physical_rows(
                            q.source.runners,
                            t1=r.value.t1,
                            t1_input=q.t1,
                            tenant_id=tenant,
                            play_id=row_id,
                        )
                    ),
                )
            )
        originals = tuple(rows)
        corrected = _correct(host, originals)
        assert (
            first.payload is not None
            and type(first.payload.observations) is FirstBallObservations
        )
        payloads = build_corrected_lineup_payloads(
            originals, corrected, first.payload.observations
        )
        physical = prepare_corrected_physical_pitches(
            originals,
            corrected,
            payloads,
            tenant_id=tenant,
            game_id=game,
            capsule_id=UUID(int=10000),
            change_event_id=UUID(int=10001),
        )
        assert len(physical) == len(originals)
        for saved, projected, payload in zip(
            originals[1:], physical[1:], payloads[1:], strict=True
        ):
            assert projected.play_row == saved.play_row
            assert projected.play_runners == saved.play_runners
            assert projected.effective_event_id == saved.source_event_id
            native = evaluate_native_projection(
                payload.model_dump(mode="json", by_alias=True, exclude_unset=True),
                source_event_id=projected.effective_event_id,
            )
            assert native["selected"] is True
            assert native["source_event_id"] == str(saved.source_event_id)
            assert saved.payload is not None
            assert native == evaluate_native_projection(
                saved.payload.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
                source_event_id=saved.source_event_id,
            )
            assert native["metrics"]["h"]["state"] == "available"
            assert native["metrics"]["h"]["value"] == "1"


def test_saved_hit_before_target_is_carried_without_reclassifying_target():
    """対象前の既安打も旧原本再生で持ち越し、対象は通常球に限る。"""
    with _host() as host:
        first, ordinary = _two_saved(host)
        hit = _hit(host, first)
        wire = ordinary.calculation.request.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        wire["source"]["position"] = {"d1": "3", "d2": "3", "appliedWatermark": "2"}
        wire["playIdentity"] = {
            "eventId": str(UUID(int=11000)),
            "d5": str(UUID(int=11001)),
            "playId": str(UUID(int=11002)),
        }
        wire["nextCheckpoint"]["revision"] = "4"
        q = _next_corrected_request(
            decode_lineup_prefix_request(json.dumps(wire)),
            hit.calculation.response,
            None,
            UUID(int=11003),
            host.artifact_sha256,
        )
        r = decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                q.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
        assert type(r) is LineupPrefixSuccess
        q, r = seal_lineup_wire(q, r)
        calc = LineupPitchCalculation.model_validate_json(
            json.dumps(
                {
                    "formatVersion": "play-prefix-calculation-v3",
                    "artifactSha256": host.artifact_sha256,
                    "request": q.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                    "response": r.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    ),
                }
            )
        )
        assert ordinary.payload is not None
        payload = ordinary.payload.model_copy(
            update={"calculation": calc, "participants": r.value.before_participants}
        )
        third = SavedLineupPitch(UUID(int=11000), 3, 3, calc, payload)
        corrected = _evaluate(
            (first, hit, third),
            "batting-result.ball",
            (UUID(int=11004),),
            host,
            target_d1=3,
        )
        assert (
            len(corrected) == 1
            and corrected[0].source_event_id == third.source_event_id
        )
        assert corrected[0].corrected_request.source.runners == q.source.runners
        assert corrected[0].corrected_response.value.t1.after.state_fields.balls == "1"
