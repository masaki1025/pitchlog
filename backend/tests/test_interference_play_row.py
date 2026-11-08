"""実859 hostの妨害原本を、同TX PlayRow全41列へ束縛する純対向。"""

import copy
import json
from functools import cache
from pathlib import Path
from uuid import UUID

import pytest
from test_runner_nonpitch_row_operations import _results, _token

from pitchlog.db.game_state.models import PlayRow
from pitchlog.domainrt.host import open_domain_host
from pitchlog.repositories.ordinary_pitch_operations import (
    PLAY_PREFIX_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
)
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = "859986408d75994d6f1530ce99c0331da1644da9d5ae6339bb479e3926ee7f2e"
PITCH = {
    "pitchTypeKey": "fixture.fastball",
    "course": {"unit": "1/263", "x": "132", "y": "131"},
    "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
    "stance": None,
    "battingSide": None,
}


@cache
def _actual(case: str):
    """旧fixtureのsource/実IDから、妨害入力だけを変更して実hostを呼ぶ。"""
    base = json.loads(
        (
            ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json"
        ).read_text()
    )["cases"][0]["request"]
    request = copy.deepcopy(base)
    request["source"]["executionArtifactSha256"] = ARTIFACT
    t1 = request["t1"]
    if case == "penalty":
        t1.update(
            eventKind="secondary-result",
            resultId="secondary-result.batting-interference",
            interferenceRuling={
                "kind": "batting-interference",
                "adopted": {"kind": "penalty-award"},
                "third_base_scoring_attempt": {"kind": "not-required"},
            },
        )
        observation = {
            **PITCH,
            "resultId": t1["resultId"],
            "interferenceRuling": t1["interferenceRuling"],
        }
    elif case == "play":
        t1["interferenceRuling"] = {
            "kind": "batting-interference",
            "adopted": {"kind": "play-result", "resultId": t1["resultId"]},
            "third_base_scoring_attempt": {"kind": "not-required"},
        }
        observation = {
            **PITCH,
            "resultId": t1["resultId"],
            "interferenceRuling": t1["interferenceRuling"],
            "battedBall": dict.fromkeys(
                (
                    "typeKey",
                    "strengthKey",
                    "hitX",
                    "hitY",
                    "rawFielderPosition",
                    "resolvedFielderId",
                )
            ),
            "officialScoringPayload": {
                "kind": "no-error",
                "errorCount": "0",
                "fielders": [],
            },
            "runnerAdvanceOverridesByRunner": {"kind": "not-applied", "overrides": []},
            "thirdOutObservation": {"kind": "none"},
            "thirdOutTimingByRunner": {},
        }
    else:
        batter = request["source"]["participants"]["batterId"]
        person = {
            "kind": "batter",
            "batter_id": {"kind": "official", "player_id": batter},
        }
        before = t1["before"]
        ruling = (
            {
                "kind": "obstruction",
                "play_kind": "play-on-obstructed-runner",
                "obstructed": person,
                "awarded_destinations": [{"person": person, "destination": "first"}],
                "out_targets": [],
                "batter_before_first": True,
            }
            if case == "obstruction"
            else {
                "kind": "offensive-interference",
                "out_targets": [person],
                "return_bases": [],
            }
        )
        t1.clear()
        t1.update(
            eventKind="secondary-result",
            resultId=(
                "secondary-result.obstruction"
                if case == "obstruction"
                else "secondary-result.offensive-interference"
            ),
            pitchEventKind="pitch-event",
            before=before,
            interferenceRuling=ruling,
        )
        observation = {
            **PITCH,
            "resultId": t1["resultId"],
            "interferenceRuling": ruling,
        }
    with open_domain_host() as host:
        assert host.artifact_sha256 == ARTIFACT
        response = json.loads(
            host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(request))
        )
    assert response["ok"] is True, case
    raw = {
        "formatVersion": "play-prefix-play-v3",
        "observations": observation,
        "participants": response["value"]["beforeParticipants"],
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "artifactSha256": ARTIFACT,
            "request": request,
            "response": response,
        },
    }
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        payload.calculation.request.t1.result_id,
        tenant_id=UUID(request["prefixRef"]["tenantId"]),
        game_id=UUID(request["prefixRef"]["gameId"]),
        source_event_id=UUID(request["playIdentity"]["eventId"]),
        row_id=UUID(request["playIdentity"]["playId"]),
        play_number=101,
    )
    return row, raw


def _preflight(row, raw):
    """既INSERTの同TX読取と全列判定を純呼出する。"""
    token = _token(row)
    operation = PLAY_PREFIX_PLAY_OPERATIONS[0]
    _, params = operation.prepare(token)
    assert operation.preflight is not None
    gate = operation.preflight(token, {**params, "tenant_id": UUID(row["tenant_id"])})
    gate.validate(_results(row, raw))


@pytest.mark.parametrize("case", ("penalty", "play", "obstruction", "offensive"))
def test_actual_host_interference_is_bound_to_accepted_row(case):
    """実host結果と原V7から唯一mapperが作る41列だけを受理する。"""
    row, raw = copy.deepcopy(_actual(case))
    assert set(row) == set(PlayRow.__table__.c.keys()) and len(row) == 41
    assert row["event_kind"] == "pitch"
    if case == "play":
        assert row["batting_result_key"] == raw["observations"]["resultId"]
    else:
        assert row["batting_result_key"] is None
    assert row["secondary_batting_result_key"] == (
        "secondary-result.batting-interference"
        if case == "play"
        else raw["observations"]["resultId"]
    )
    _preflight(row, raw)


@pytest.mark.parametrize(
    "mutation",
    (
        "secondary",
        "primary",
        "fielder",
        "participant",
        "source-event",
        "play-id",
        "d5",
        "tenant",
        "observed-ruling",
        "request-ruling",
        "missing-effects",
        "extra-observation",
        "ordinary-token",
    ),
)
def test_changed_row_or_original_does_not_reach_insert(mutation):
    """同TX原本・ID・裁定・typed効果・全物理列の差替えを拒否する。"""
    row, raw = copy.deepcopy(_actual("penalty"))
    if mutation == "secondary":
        row["secondary_batting_result_key"] = None
    elif mutation == "primary":
        row["batting_result_key"] = "batting-result.ball"
    elif mutation == "fielder":
        row["resolved_fielder_id"] = str(UUID(int=77))
    elif mutation == "participant":
        row["batter_id"] = str(UUID(int=77))
    elif mutation == "source-event":
        raw["calculation"]["request"]["playIdentity"]["eventId"] = str(UUID(int=77))
    elif mutation == "play-id":
        raw["calculation"]["request"]["playIdentity"]["playId"] = str(UUID(int=77))
    elif mutation == "d5":
        raw["calculation"]["request"]["playIdentity"]["d5"] = str(UUID(int=77))
    elif mutation == "tenant":
        raw["calculation"]["request"]["prefixRef"]["tenantId"] = str(UUID(int=77))
    elif mutation == "observed-ruling":
        raw["observations"]["interferenceRuling"]["adopted"]["kind"] = "play-result"
    elif mutation == "request-ruling":
        raw["calculation"]["request"]["t1"]["interferenceRuling"]["adopted"]["kind"] = (
            "play-result"
        )
    elif mutation == "missing-effects":
        del raw["calculation"]["response"]["value"]["runnerScoreEffects"]
    elif mutation == "extra-observation":
        raw["observations"]["unknown"] = True
    else:
        with pytest.raises(OrdinaryPlayRowError):
            PLAY_PREFIX_PLAY_OPERATIONS[0].prepare(
                _token(row, OrdinaryPlayRowInsertToken)
            )
        return
    with pytest.raises(OrdinaryPlayRowError):
        _preflight(row, raw)
