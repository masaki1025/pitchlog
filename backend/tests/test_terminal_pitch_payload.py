"""v2閉payload、実応答由来のwire seal、取消用差分を検査する。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.play_prefix_continuation import (
    PlayPrefixRequest,
    PlayPrefixSuccess,
)
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.ordinary_pitch_payload import OrdinaryPitchParticipants
from pitchlog.sync.terminal_pitch_payload import (
    TerminalPitchCalculation,
    TerminalPitchPayloadError,
    format_terminal_pitch_payload,
    play_prefix_wire_head,
    read_terminal_pitch_payload,
    seal_play_prefix_metadata,
    verify_play_prefix_seal,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (ROOT / "contracts/state-transition/play_prefix_v2_cases.json").read_text()
)["cases"]
SUCCESS = [c for c in CASES if c["expected"]["ok"]]


def values(case=None):
    """受理済み静的期待を使い、製品出力から期待を生成しない。"""
    case = case or SUCCESS[0]
    q = PlayPrefixRequest.model_validate_json(json.dumps(case["request"]))
    r = PlayPrefixSuccess.model_validate_json(json.dumps(case["expected"]))
    q, r = seal_play_prefix_metadata(q, r)
    calc = TerminalPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v2",
                "artifactSha256": q.source.execution_artifact_sha256,
                "request": q.model_dump(mode="json", by_alias=True, exclude_unset=True),
                "response": r.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
        )
    )
    people = OrdinaryPitchParticipants.model_validate_json(
        json.dumps(
            {
                **q.source.participants.model_dump(mode="json", by_alias=True),
                "catcherId": "10000000-0000-0000-0000-000000000099",
            }
        )
    )
    obs = FirstBallObservations.model_validate_json(
        json.dumps(
            {
                "pitchTypeKey": "pitch-type.straight",
                "course": {"unit": "1/263", "x": "131", "y": "132"},
                "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                "stance": None,
                "battingSide": None,
            }
        )
    )
    return obs, people, calc


@pytest.mark.parametrize("case", SUCCESS, ids=lambda c: c["caseId"])
def test_all_static_responses_and_v8_difference(case):
    """全比較面を保持しV8へcalculationを混ぜない。"""
    obs, people, calc = values(case)
    v7, v8 = format_terminal_pitch_payload(obs, people, calc)
    actual = read_terminal_pitch_payload(
        v7, v8, expected_calculation=calc, expected_participants=people
    )
    assert actual.calculation == calc
    assert json.loads(v8) == case["expected"]["value"]["newHistoryEntry"]["difference"]
    assert (v7, v8) == format_terminal_pitch_payload(obs, people, calc)


def test_seal_changes_only_two_echoes_and_retains_prior_digest():
    """選択fieldのhashから自己echoだけを外し真正prior digestを残す。"""
    case = SUCCESS[0]
    _, _, calc = values(case)
    q = calc.request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    r = calc.response.model_dump(mode="json", by_alias=True, exclude_unset=True)
    q["nextCheckpoint"]["digest"] = case["request"]["nextCheckpoint"]["digest"]
    r["value"]["nextPrefixRef"]["checkpoint"]["digest"] = case["expected"]["value"][
        "nextPrefixRef"
    ]["checkpoint"]["digest"]
    assert q == case["request"]
    assert r == case["expected"]
    head = play_prefix_wire_head(calc.request, calc.response)
    assert (
        head["previousPrefixRef"]["checkpoint"]["digest"]
        == case["request"]["prefixRef"]["checkpoint"]["digest"]
    )
    for field in head:
        changed = copy.deepcopy(head)
        changed[field] = None
        import hashlib

        from pitchlog.domainrt.first_ball_projection import _canonical_json

        assert (
            hashlib.sha256(_canonical_json(changed).encode()).hexdigest()
            != calc.request.next_checkpoint.digest
        )


def test_unsealed_fullresponse_or_extra_or_wrong_v8_rejected():
    """未信頼digest/余剰/取消差分の改変を補修しない。"""
    obs, people, calc = values()
    v7, v8 = format_terminal_pitch_payload(obs, people, calc)
    for changed in [
        json.dumps({**json.loads(v7), "extra": True}),
        v7.replace(calc.request.next_checkpoint.digest, "0" * 64),
    ]:
        with pytest.raises(TerminalPitchPayloadError):
            read_terminal_pitch_payload(
                changed, v8, expected_calculation=calc, expected_participants=people
            )
    with pytest.raises(TerminalPitchPayloadError):
        read_terminal_pitch_payload(
            v7, "{}", expected_calculation=calc, expected_participants=people
        )
    verify_play_prefix_seal(calc)


def test_candidate_schema_vectors_and_all_selected_field_mutations():
    """新契約56件を照合し、Wの各fieldに対応する変更を全て拒否する。"""
    from jsonschema import Draft202012Validator
    from pydantic import ValidationError

    base = ROOT / "contracts/state-transition"
    schema = json.loads((base / "play_prefix_v2_payload_schema.json").read_text())
    vectors = json.loads((base / "play_prefix_v2_payload_vectors.json").read_text())
    assert [case["caseId"] for case in vectors["cases"]] == [
        case["caseId"] for case in SUCCESS
    ]
    validator = Draft202012Validator(schema)
    for case in vectors["cases"]:
        validator.validate(case["V7"])
        expected = next(c for c in SUCCESS if c["caseId"] == case["caseId"])
        assert (
            case["V8"] == expected["expected"]["value"]["newHistoryEntry"]["difference"]
        )
    _, _, calc = values()
    paths: list[tuple[str, ...]] = (
        [
            ("response", "value", "nextPrefixRef", key)
            for key in (
                "version",
                "scope",
                "tenantId",
                "gameId",
                "generation",
                "length",
                "historyVersion",
                "origin",
            )
        ]
        + [
            ("response", "value", "nextPrefixRef", "checkpoint", key)
            for key in ("id", "revision")
        ]
        + [("request", key) for key in ("prefixRef", "rules", "playIdentity")]
    )
    paths += [
        ("request", "source", key)
        for key in (
            "rulesDigest",
            "layoutDigest",
            "priorArtifactSha256",
            "executionArtifactSha256",
            "position",
            "responsibility",
        )
    ]
    paths += [("request", "t1", "before")]
    paths += [
        ("response", "value", key)
        for key in ("t1", "t2", "newHistoryEntry", "runners", "participants")
    ]
    for path in paths:
        raw = calc.model_dump(mode="json", by_alias=True, exclude_unset=True)
        target = raw
        for field in path[:-1]:
            target = target[field]
        target[path[-1]] = None
        with pytest.raises((ValidationError, TerminalPitchPayloadError)):
            changed = TerminalPitchCalculation.model_validate_json(json.dumps(raw))
            verify_play_prefix_seal(changed)
