"""実859 hostの妨害原本を、同TX PlayRow全41列へ束縛する純対向。"""

import copy
import json
from functools import cache
from pathlib import Path
from uuid import UUID

import pytest
from test_runner_nonpitch_row_operations import _results, _token

from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import IdempotencyLedger, OperationEvent
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.lineup_play_prefix_continuation import PrefixRef
from pitchlog.repositories.ordinary_pitch_operations import (
    PLAY_PREFIX_PLAY_OPERATIONS,
    OrdinaryPlayRowError,
)
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.ordinary_pitch_physical import pitch_physical_row
from pitchlog.sync.ordinary_pitch_tokens import OrdinaryPlayRowInsertToken
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixPlayRowInsertToken

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = "bb6768eae395bda43e13a1b97e8b6da0f2ab2b66a78a460590c0a8fd1151daa1"
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


def _preflight_original_d5(row, raw):
    """原V7のD5と同じ受理event/ledgerを同TX結果として照合する。"""
    d5 = UUID(raw["calculation"]["request"]["playIdentity"]["d5"])
    token = PlayPrefixPlayRowInsertToken(
        UUID(row["game_id"]),
        1,
        101,
        101,
        d5,
        "wire-v1:" + "a" * 64,
        json.dumps(row),
    )
    operation = PLAY_PREFIX_PLAY_OPERATIONS[0]
    _, params = operation.prepare(token)
    assert operation.preflight is not None
    gate = operation.preflight(token, {**params, "tenant_id": UUID(row["tenant_id"])})
    results = _results(row, raw)
    event = list(results[0].rows[0])
    ledger = list(results[1].rows[0])
    event[list(OperationEvent.__table__.c.keys()).index("d5")] = d5
    ledger[list(IdempotencyLedger.__table__.c.keys()).index("d5")] = d5
    gate.validate(
        (
            TenantOperationResult((tuple(event),)),
            TenantOperationResult((tuple(ledger),)),
            results[2],
        )
    )


@cache
def _actual_adopted_error(operation="error"):
    """旧error原本の元走者・失策野手を保持して実859採用プレイを得る。"""
    from test_batted_operations_schema import actual_batted_payload

    samples = json.loads(
        (
            ROOT
            / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
        ).read_text()
    )["samples"]
    sample = copy.deepcopy(
        next(row for row in samples if row["operation"] == operation)
    )
    sample["request"]["source"]["executionArtifactSha256"] = ARTIFACT
    with open_domain_host() as host:
        previous = actual_batted_payload(sample, host, expected_artifact=ARTIFACT)
    raw = previous.model_dump(mode="json", by_alias=True, exclude_unset=True)
    ruling = {
        "kind": "batting-interference",
        "adopted": {
            "kind": "play-result",
            "resultId": sample["request"]["t1"]["resultId"],
        },
        "third_base_scoring_attempt": {"kind": "not-required"},
    }
    raw["calculation"]["request"]["t1"]["interferenceRuling"] = ruling
    raw["observations"]["interferenceRuling"] = ruling
    with open_domain_host() as host:
        response = json.loads(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                json.dumps(raw["calculation"]["request"]),
            )
        )
    assert response["ok"] is True
    raw["calculation"]["response"] = response
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    q = payload.calculation.request
    assert isinstance(q.prefix_ref, PrefixRef)
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=101,
    )
    return row, raw


@pytest.mark.parametrize("operation", ("error", "sacrifice-bunt-error"))
def test_adopted_error_keeps_real_fielder_and_accepted_primary_secondary(operation):
    """実失策採用を主error/副妨害として原41列のまま保存する。"""
    row, raw = copy.deepcopy(_actual_adopted_error(operation))
    assert row["batting_result_key"] == raw["observations"]["resultId"]
    assert (
        row["secondary_batting_result_key"] == "secondary-result.batting-interference"
    )
    assert (
        raw["observations"]["officialScoringPayload"]["errors"][0]["fielder"][
            "player_id"
        ]
        is not None
    )
    assert row["resolved_fielder_id"] is None
    _preflight_original_d5(row, raw)
    row["resolved_fielder_id"] = str(UUID(int=88))
    with pytest.raises(OrdinaryPlayRowError):
        _preflight_original_d5(row, raw)


@cache
def _actual_old_batted_runtime(index):
    """旧9結果の真正host出力を新実行SHAへ再計算し原本化する。"""
    from test_batted_operations_schema import actual_batted_payload

    samples = json.loads(
        (
            ROOT
            / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
        ).read_text()
    )["samples"]
    sample = copy.deepcopy(samples[index])
    sample["request"]["source"]["executionArtifactSha256"] = ARTIFACT
    with open_domain_host() as host:
        payload = actual_batted_payload(sample, host, expected_artifact=ARTIFACT)
    q = payload.calculation.request
    assert isinstance(q.prefix_ref, PrefixRef)
    raw = payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert q.t1.interference_ruling == "not-required"
    assert raw["observations"]["interferenceRuling"] == {"kind": "not-required"}
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=101,
    )
    return row, raw


@pytest.mark.parametrize("index", range(10))
def test_previous_batted_runtime_source_still_reaches_same_tx_preflight(index):
    """旧打球9結果10原本のnot-required裁定を妨害へ誤分類しない。"""
    row, raw = _actual_old_batted_runtime(index)
    _preflight_original_d5(row, raw)


@pytest.mark.parametrize(
    "mutation", ("unknown-observed", "request-only-int", "observation-only-int")
)
def test_previous_batted_source_does_not_mask_unknown_or_one_sided_ruling(mutation):
    """旧正常枝へ未知dictやINT裁定の片側差替えを逃がさない。"""
    row, raw = copy.deepcopy(_actual_old_batted_runtime(0))
    ruling = {
        "kind": "batting-interference",
        "adopted": {"kind": "play-result", "resultId": "batting-result.single"},
        "third_base_scoring_attempt": {"kind": "not-required"},
    }
    if mutation == "unknown-observed":
        raw["observations"]["interferenceRuling"] = {"kind": "unknown"}
    elif mutation == "request-only-int":
        raw["calculation"]["request"]["t1"]["interferenceRuling"] = ruling
    else:
        raw["observations"]["interferenceRuling"] = ruling
    with pytest.raises(OrdinaryPlayRowError):
        _preflight_original_d5(row, raw)


@pytest.mark.parametrize(
    "result",
    ("batting-result.double", "batting-result.triple", "batting-result.home-run"),
)
def test_previous_hit_results_complete_all_twelve_batted_kinds(result):
    """旧10原本に無かった3安打も実859 hostから同TX挿入へ進む。"""
    from test_batted_hit_prefix_payload import observations

    cases = json.loads(
        (
            ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json"
        ).read_text()
    )["cases"]
    request = copy.deepcopy(
        next(c["request"] for c in cases if c["request"]["t1"]["resultId"] == result)
    )
    request["source"]["executionArtifactSha256"] = ARTIFACT
    with open_domain_host() as host:
        response = json.loads(
            host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(request))
        )
    assert response["ok"] is True
    raw = {
        "formatVersion": "play-prefix-play-v3",
        "participants": response["value"]["beforeParticipants"],
        "observations": observations({"request": request}),
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "artifactSha256": ARTIFACT,
            "request": request,
            "response": response,
        },
    }
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    q = payload.calculation.request
    assert isinstance(q.prefix_ref, PrefixRef)
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=101,
    )
    _preflight_original_d5(row, raw)


def test_previous_ordinary_v3_source_still_reaches_same_tx_preflight():
    """旧通常の実保存V7も妨害型を要求せず同TX照合へ進む。"""
    raw = json.loads(
        (
            ROOT
            / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
        ).read_text()
    )["cases"][0]["V7"]
    payload = LineupPitchPlayPayload.model_validate_json(json.dumps(raw))
    q = payload.calculation.request
    assert isinstance(q.prefix_ref, PrefixRef)
    row = pitch_physical_row(
        payload.observations,
        payload.participants,
        q.t1.result_id,
        tenant_id=UUID(q.prefix_ref.tenant_id),
        game_id=UUID(q.prefix_ref.game_id),
        source_event_id=UUID(q.play_identity.event_id),
        row_id=UUID(q.play_identity.play_id),
        play_number=101,
    )
    _preflight_original_d5(row, raw)


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
