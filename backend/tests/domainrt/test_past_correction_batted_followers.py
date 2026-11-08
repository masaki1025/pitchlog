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
        "batting-result.called-pitch",
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
            "batting-result.called-pitch",
            (UUID(int=9000), UUID(int=9001)),
            host,
            CorrectionPageState(),
            target_d1=1,
        )
        _, tail = _evaluate_page(
            (next_hit,),
            "batting-result.called-pitch",
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
