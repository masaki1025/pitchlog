"""到達ID/責任/打点の写像を検査する。野球計算の別oracleは作らない。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.stats.facts import evaluate_native_projection, native_projection

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"]
EVENT = UUID("00000000-0000-0000-0000-000000000701")


def _payload(case):
    """正準契約のrequest/expectedを無変更で包み、明示no-error観測を添える。"""
    return {
        "formatVersion": "play-prefix-play-v3",
        "participants": copy.deepcopy(case["expected"]["value"]["beforeParticipants"]),
        "observations": {
            "pitchTypeKey": "fixture.fastball",
            "course": {"unit": "1/263", "x": "132", "y": "131"},
            "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
            "stance": None,
            "battingSide": None,
            "battedBall": {
                "typeKey": None,
                "strengthKey": None,
                "hitX": None,
                "hitY": None,
                "rawFielderPosition": None,
                "resolvedFielderId": None,
            },
            "resultId": case["request"]["t1"]["resultId"],
            "officialScoringPayload": {
                "kind": "no-error",
                "errorCount": "0",
                "fielders": [],
            },
            "interferenceRuling": {"kind": "not-required"},
            "thirdOutObservation": {"kind": "none"},
            "thirdOutTimingByRunner": {},
            "runnerAdvanceOverridesByRunner": {"kind": "not-applied", "overrides": []},
        },
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "artifactSha256": case["request"]["source"]["executionArtifactSha256"],
            "request": copy.deepcopy(case["request"]),
            "response": copy.deepcopy(case["expected"]),
        },
    }


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["caseId"])
def test_canonical_hits_copy_exact_batter_credit_or_proven_empty(case):
    """正準19行の打者生還または非生還を写し、原値は変更しない。"""
    raw = _payload(case)
    before = copy.deepcopy(raw)
    result = evaluate_native_projection(raw, source_event_id=EVENT)
    scored = case["request"]["t1"]["resultId"] == "batting-result.home-run"
    people = raw["participants"]
    for metric, player in (
        ("runs", people["batterId"]),
        ("rbi", people["batterId"]),
        ("runs_allowed", people["pitcherId"]),
    ):
        assert result["metrics"][metric] == {
            "state": "available",
            "value": "1" if scored else "0",
            "display": "1" if scored else "0",
            "reason": None,
            "credits": [{"player_id": player, "quantity": "1"}] if scored else [],
        }
    assert raw == before


def _runner_payload(result, destinations, count):
    """adapterだけの手定入力。真正frame/実artifact成功との主張はしない。"""
    case = next(c for c in CASES if c["caseId"] == "BHP-BH-HomeRun-top-O1")
    raw = _payload(case)
    q = raw["calculation"]["request"]
    t1 = raw["calculation"]["response"]["value"]["t1"]
    q["t1"]["resultId"] = raw["observations"]["resultId"] = result
    q["t1"]["before"]["stateFields"]["state.score"] = {"home": "0", "away": "0"}
    t1["after"]["stateFields"]["state.score"] = {"home": "0", "away": count}
    lineup = q["source"]["lineup"]
    runners = [
        {
            "base": str(base),
            "runnerId": lineup["away"]["battingOrder"][str(base + 1)],
            "responsiblePitcherId": lineup["home"]["battingOrder"][str(base + 1)],
        }
        for base in destinations
    ]
    q["source"]["runners"] = runners
    overrides = {
        "kind": "applied",
        "overrides": [
            {"runnerBase": str(base), "destination": destination}
            for base, destination in destinations.items()
        ],
    }
    q["t1"]["runnerAdvanceOverrides"] = copy.deepcopy(overrides)
    raw["observations"]["runnerAdvanceOverridesByRunner"] = overrides
    for base, name in ((1, "first"), (2, "second"), (3, "third")):
        t1["runnerDefaultAdvance"][name] = {
            "modality": "forced" if base in destinations else "not-applicable",
            "destination": destinations.get(base),
        }
    t1["batterDestination"] = (
        {"kind": "score"}
        if result == "batting-result.home-run"
        else {"kind": "reach", "base": "2"}
    )
    return raw, runners


@pytest.mark.parametrize(
    "result,destinations,count,scoring_bases",
    [
        ("batting-result.single", {1: "3", 2: "4"}, "1", [2]),
        ("batting-result.double", {1: "3", 2: "4"}, "1", [2]),
        ("batting-result.triple", {1: "4", 2: "4"}, "2", [1, 2]),
        ("batting-result.home-run", {1: "4", 2: "4", 3: "4"}, "4", [1, 2, 3]),
    ],
)
def test_all_scoring_runner_ids_and_previous_responsible_pitchers_are_preserved(
    result, destinations, count, scoring_bases
):
    """非生還走者を加算せず、前任投手の責任を現在投手で補完しない。"""
    raw, runners = _runner_payload(result, destinations, count)
    projected = native_projection(raw, source_event_id=EVENT)
    chosen = [r for r in runners if int(r["base"]) in scoring_bases]
    expected = [
        {
            "runner_id": r["runnerId"],
            "responsible_pitcher_id": r["responsiblePitcherId"],
            "valid_run": True,
            "rbi_credited": True,
            "rbi_batter_id": raw["participants"]["batterId"],
        }
        for r in chosen
    ]
    if result == "batting-result.home-run":
        expected.append(
            {
                "runner_id": raw["participants"]["batterId"],
                "responsible_pitcher_id": raw["participants"]["pitcherId"],
                "valid_run": True,
                "rbi_credited": True,
                "rbi_batter_id": raw["participants"]["batterId"],
            }
        )
    assert projected["runner_scores"] == expected
    actual = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    for metric in ("runs", "rbi", "runs_allowed"):
        assert actual[metric]["state"] == "available"
        assert actual[metric]["value"] == count


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-scores",
        "missing-plan",
        "missing-pitcher",
        "third-out",
        "third-timing",
        "error",
        "interference",
        "score-mismatch",
        "rbi-false",
        "missing-observation",
        "unknown-result",
        "missing-overrides",
        "unconfirmed-overrides",
        "duplicate-runner",
    ],
)
def test_incomplete_or_unsupported_causality_stays_unavailable(mutation):
    """得点差や結果名で欠測の選手/打点を推測しない。"""
    raw, _ = _runner_payload("batting-result.triple", {1: "4", 2: "4"}, "2")
    q = raw["calculation"]["request"]
    t1 = raw["calculation"]["response"]["value"]["t1"]
    if mutation == "missing-scores":
        del t1["after"]["stateFields"]["state.score"]
    elif mutation == "missing-plan":
        del t1["runnerDefaultAdvance"]
    elif mutation == "missing-pitcher":
        del q["source"]["runners"][0]["responsiblePitcherId"]
    elif mutation == "third-out":
        t1["outEffect"]["count"] = "3"
    elif mutation == "third-timing":
        raw["observations"]["thirdOutTimingByRunner"] = {"1": "home-before-third-out"}
    elif mutation == "error":
        raw["observations"]["officialScoringPayload"]["kind"] = "error"
    elif mutation == "interference":
        q["t1"]["interferenceRuling"] = "required"
    elif mutation == "score-mismatch":
        t1["after"]["stateFields"]["state.score"]["away"] = "4"
    elif mutation == "rbi-false":
        t1["statFlags"]["打点"] = False
    elif mutation == "missing-observation":
        del raw["observations"]["thirdOutObservation"]
    elif mutation == "unknown-result":
        q["t1"]["resultId"] = "unknown"
    elif mutation == "missing-overrides":
        del raw["observations"]["runnerAdvanceOverridesByRunner"]
    elif mutation == "unconfirmed-overrides":
        raw["observations"]["runnerAdvanceOverridesByRunner"]["overrides"].pop()
    elif mutation == "duplicate-runner":
        q["source"]["runners"][1]["runnerId"] = q["source"]["runners"][0]["runnerId"]
    result = evaluate_native_projection(raw, source_event_id=EVENT)
    for key in ("runs", "rbi", "runs_allowed"):
        assert result["metrics"][key]["state"] == "source_unavailable"
        assert result["metrics"][key]["value"] is None
        assert result["metrics"][key]["credits"] == []


@pytest.mark.parametrize(
    "result_id", ["batting-result.ball", "batting-result.called-pitch"]
)
def test_canonical_ordinary_zero_is_complete_but_missing_destination_is_not(result_id):
    """正式初球原本の非生還・不変scoreを確認し、欠けた結果は0にしない。"""
    cases = json.loads(
        (ROOT / "backend/tests/fixtures/first_ball_payload_vectors_v1.json").read_text()
    )["cases"]
    raw = next(
        json.loads(c["v7Json"])
        for c in cases
        if json.loads(c["v7Json"])["calculation"]["request"]["t1"]["resultId"]
        == result_id
    )
    for metric in ("runs", "rbi", "runs_allowed"):
        assert evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][
            metric
        ] == {
            "state": "available",
            "value": "0",
            "display": "0",
            "reason": None,
            "credits": [],
        }
    del raw["calculation"]["response"]["value"]["t1"]["batterDestination"]
    for metric in ("runs", "rbi", "runs_allowed"):
        assert (
            evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][metric][
                "state"
            ]
            == "source_unavailable"
        )


_K_CASES = [
    c
    for c in json.loads(
        (
            ROOT
            / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
        ).read_text()
    )["cases"]
    if "strikeout" in c["V7"]["calculation"]["request"]["t1"]["resultId"]
]


@pytest.mark.parametrize("case", _K_CASES, ids=lambda c: c["caseId"])
def test_canonical_strikeout_third_out_and_side_change_are_proven_zero(case):
    """第3outを含む正準Kの不変score/非生還は欠測ではない。"""
    raw = copy.deepcopy(case["V7"])
    original = copy.deepcopy(raw)
    result = evaluate_native_projection(raw, source_event_id=EVENT)
    for metric in ("runs", "rbi", "runs_allowed"):
        assert result["metrics"][metric] == {
            "state": "available",
            "value": "0",
            "display": "0",
            "reason": None,
            "credits": [],
        }
    assert raw == original
    # 正準0出力のscoreだけを改変した正得点を推測成立させない。
    score = raw["calculation"]["response"]["value"]["t1"]["after"]["stateFields"][
        "state.score"
    ]
    score["away"] = str(int(score["away"]) + 1)
    for metric in ("runs", "rbi", "runs_allowed"):
        assert (
            evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][metric][
                "state"
            ]
            == "source_unavailable"
        )


def test_strikeout_goldens_include_third_out_and_inning_transition():
    """3out/攻守交代/延長へのカバレッジをfixture名だけで推定しない。"""
    pairs = [
        (
            c["V7"]["calculation"]["request"]["t1"]["before"]["stateFields"],
            c["V7"]["calculation"]["response"]["value"]["t1"]["after"]["stateFields"],
        )
        for c in _K_CASES
    ]
    assert any(b["state.outs"] == "2" and a["state.outs"] == "0" for b, a in pairs)
    assert any(b["state.half"] != a["state.half"] for b, a in pairs)
    assert any(b["state.inning"] != a["state.inning"] for b, a in pairs)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["caseId"])
def test_all_27_primitives_have_complete_inputs_for_canonical_closed_hits(case):
    """MVP表示27とは別のT5原始27。既全入力が揃う安打を一括照合する。"""
    raw = _payload(case)
    actual = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    assert len(actual) == 27
    assert {
        key: m["reason"] for key, m in actual.items() if m["state"] != "available"
    } == {}
    name = case["request"]["t1"]["resultId"]
    bases = {
        "batting-result.single": "1",
        "batting-result.double": "2",
        "batting-result.triple": "3",
        "batting-result.home-run": "4",
    }
    assert actual["doubles"]["value"] == (
        "1" if name == "batting-result.double" else "0"
    )
    assert actual["triples"]["value"] == (
        "1" if name == "batting-result.triple" else "0"
    )
    assert actual["total_bases"]["value"] == bases[name]
    assert actual["stolen_bases"] == {
        "state": "available",
        "value": "0",
        "display": "0",
        "reason": None,
        "credits": [],
    }


@pytest.mark.parametrize("case", _K_CASES, ids=lambda c: c["caseId"])
def test_runner_hold_and_third_out_in_closed_normal_k_do_not_invent_steal(case):
    """無走者限定ではなく、走者保持/第三outの既非複合操作を閉確認する。"""
    raw = copy.deepcopy(case["V7"])
    actual = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    assert actual["stolen_bases"] == {
        "state": "available",
        "value": "0",
        "display": "0",
        "reason": None,
        "credits": [],
    }
    assert {
        k: v["reason"] for k, v in actual.items() if v["state"] != "available"
    } == {}


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-runner-operation",
        "unknown-result",
        "runner-event",
        "compound-k",
        "fake-false-flag",
    ],
)
def test_no_steal_requires_closed_original_codec_and_noncompound_operation(mutation):
    """余剰/未知/複合を落として空集合にせず、元辞書も変えない。"""
    raw = copy.deepcopy(_K_CASES[0]["V7"])
    q = raw["calculation"]["request"]["t1"]
    t1 = raw["calculation"]["response"]["value"]["t1"]
    if mutation == "extra-runner-operation":
        raw["observations"]["runnerEvent"] = {"kind": "steal"}
    elif mutation == "unknown-result":
        q["resultId"] = "batting-result.unknown"
    elif mutation == "runner-event":
        q["eventKind"] = "runner-event"
    elif mutation == "compound-k":
        t1["outEffect"] = {"count": "2", "targets": ["batter", {"runner": "1"}]}
    elif mutation == "fake-false-flag":
        t1["statFlags"]["盗塁"] = False
    before = copy.deepcopy(raw)
    if mutation == "fake-false-flag":
        assert (
            native_projection(raw, source_event_id=EVENT)["completeness"]["steals"]
            == "unavailable"
        )
        with pytest.raises(ValueError, match="閉record"):
            evaluate_native_projection(raw, source_event_id=EVENT)
        assert raw == before
        return
    metric = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][
        "stolen_bases"
    ]
    assert metric["state"] == "source_unavailable" and metric["value"] is None
    assert raw == before


def test_unknown_hit_kind_never_defaults_to_single_or_none():
    """安打trueの未知語彙から塁打を推測しない。"""
    raw = _payload(CASES[0])
    raw["calculation"]["request"]["t1"]["resultId"] = "batting-result.unknown-hit"
    metrics = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    for key in ("doubles", "triples", "total_bases"):
        assert metrics[key]["state"] == "source_unavailable"


def _award_payload(result_id):
    """既製品artifactに明示満塁sourceを渡す作者pure fixture。DB真正性は主張しない。"""
    from pitchlog.domainrt.host import open_domain_host

    case = next(c for c in CASES if c["caseId"] == "BHP-BH-Single-top-O1")
    q = copy.deepcopy(case["request"])
    q["t1"] = {
        k: v
        for k, v in q["t1"].items()
        if k in ("eventKind", "resultId", "pitchEventKind", "before")
    }
    q["t1"]["resultId"] = result_id
    if result_id == "batting-result.intentional-walk":
        q["t1"]["pitchEventKind"] = "non-pitch-event"
    q["t1"]["before"]["stateFields"]["state.runners"] = "first-second-third"
    q["source"]["after"] = copy.deepcopy(q["t1"]["before"])
    q["source"]["runners"] = [
        {
            "runnerId": q["source"]["lineup"]["away"]["battingOrder"][str(base + 1)],
            "responsiblePitcherId": q["source"]["lineup"]["home"]["battingOrder"][
                str(base + 1)
            ],
            "base": str(base),
            "status": "継続",
            "statusSource": "auto",
        }
        for base in (1, 2, 3)
    ]
    with open_domain_host() as host:
        response = json.loads(
            host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(q))
        )
    assert response["ok"] is True
    observed = {
        key: val
        for key, val in _payload(case)["observations"].items()
        if key in ("pitchTypeKey", "course", "pitchSpeed", "stance", "battingSide")
    }
    if result_id == "batting-result.intentional-walk":
        observed = {"kind": "intentional-walk"}
    return {
        "formatVersion": "play-prefix-play-v3",
        "observations": observed,
        "participants": response["value"]["beforeParticipants"],
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "artifactSha256": q["source"]["executionArtifactSha256"],
            "request": q,
            "response": response,
        },
    }


@pytest.mark.parametrize(
    "result_id",
    ["batting-result.walk", "batting-result.hit-by-pitch"],
)
def test_rbi07_uses_only_artifact_forced_arrival_and_saved_runner_responsibility(
    result_id,
):
    """RBI-07の1点を唯一artifactで確定し、前任責任と打点を写す。"""
    raw = _award_payload(result_id)
    scorer = raw["calculation"]["request"]["source"]["runners"][2]
    actual = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    for metric, player in (
        ("runs", scorer["runnerId"]),
        ("rbi", raw["participants"]["batterId"]),
        ("runs_allowed", scorer["responsiblePitcherId"]),
    ):
        assert actual[metric]["state"] == "available"
        assert actual[metric]["value"] == "1"
        assert actual[metric]["credits"] == [{"player_id": player, "quantity": "1"}]
    assert actual["stolen_bases"]["state"] == "available"
    assert actual["stolen_bases"]["value"] == "0"
    # forcedをoptionalへ改変してもRBI07と推測しない。
    raw["calculation"]["response"]["value"]["t1"]["runnerDefaultAdvance"]["third"][
        "modality"
    ] = "optional"
    for metric in ("runs", "rbi", "runs_allowed"):
        assert (
            evaluate_native_projection(raw, source_event_id=EVENT)["metrics"][metric][
                "state"
            ]
            == "source_unavailable"
        )


def test_existing_intentional_walk_scope_uses_real_codec_without_phantom_steal():
    """既一三塁0-0の申告敬遠を再利用し、未実装満塁へ広げない。"""
    import importlib.util

    from pitchlog.sync.nonpitch_payload import format_intentional_walk_prefix_payload

    path = ROOT / "backend/tests/test_nonpitch_payload.py"
    spec = importlib.util.spec_from_file_location("native_intentional_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calculation = module._calculation()
    raw, _ = format_intentional_walk_prefix_payload(calculation)
    raw = json.loads(raw)
    original = copy.deepcopy(raw)
    metrics = evaluate_native_projection(raw, source_event_id=EVENT)["metrics"]
    assert metrics["pitch_count"]["value"] == "0"
    for key in ("runs", "rbi", "runs_allowed", "stolen_bases"):
        assert metrics[key] == {
            "state": "available",
            "value": "0",
            "display": "0",
            "reason": None,
            "credits": [],
        }
    assert raw == original
