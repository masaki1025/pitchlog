"""v3原本照合は実artifact再生を使い、Pythonで野球値を再計算しない。"""

import copy
import json
from pathlib import Path

import pytest

import pitchlog
from pitchlog.domainrt import lineup_play_prefix_continuation as caller
from pitchlog.domainrt import lineup_prefix_source as verifier
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection

ROOT = Path(__file__).resolve().parents[3]


def _chain():
    cases = json.loads(
        (
            ROOT / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text()
    )["cases"]
    return [c for c in cases if c["caseId"].startswith("V3-STARTED-CHAIN-")]


def _evidence(chain, count):
    """公開fixtureの実名簿ABI応答を使う。DBから取得済みとの主張はしない。"""
    first = chain[0]["request"]
    lineup = first["source"]["lineup"]
    roster_request = {"dh": True}
    for side, team in lineup.items():
        roster_request[side] = {
            "team_id": team["teamId"],
            "entries": [
                {
                    "player_id": team["pitcherId"],
                    "batting_order": None,
                    "fielding_position": {"kind": "fielding", "position": "1"},
                },
                *[
                    {
                        "player_id": player,
                        "batting_order": slot,
                        "fielding_position": {"kind": "designated-hitter"}
                        if slot == "1"
                        else {"kind": "fielding", "position": slot},
                    }
                    for slot, player in team["battingOrder"].items()
                ],
            ],
        }
    with open_domain_host() as host:
        actual = json.loads(
            host.call("validateInitialGameRoster", json.dumps(roster_request))
        )
    assert actual["ok"] is True
    roster = InitialRosterProjection.model_validate_json(json.dumps(actual["value"]))
    snapshot = copy.deepcopy(first["t1"]["before"])
    del snapshot["battingOrderBySide"]
    plays = [
        {
            "identity": c["request"]["playIdentity"],
            "position_after": {
                "d1": str(i + 1),
                "d2": str(i + 1),
                "appliedWatermark": str(i + 1),
            },
            "request": c["request"],
            "response": c["expected"],
        }
        for i, c in enumerate(chain[:count])
    ]
    return verifier.LineupSourceEvidence.model_validate_json(
        json.dumps(
            {
                "started": {
                    "tenant_id": first["prefixRef"]["tenantId"],
                    "game_id": first["prefixRef"]["gameId"],
                    "generation": first["prefixRef"]["generation"],
                    "started_event_id": first["prefixRef"]["origin"]["eventId"],
                    "prior_artifact_sha256": first["source"]["priorArtifactSha256"],
                    "roster": roster.model_dump(mode="json"),
                    "snapshot": snapshot,
                    "rules": first["rules"],
                },
                "plays": plays,
                "position": chain[count]["request"]["source"]["position"],
                "complete": True,
                "invalid_event_count": 0,
                "non_play_event_count": 0,
                "pa_change_count": 0,
            }
        )
    )


@pytest.mark.parametrize("count", [0, 2, 8, 9])
def test_actual_roster_replay_through_third_out_and_opposite_ordinary(count):
    """真正source検証機構をfixtureで実測し、DB資格とは区別する。"""
    assert str(ROOT / "backend/src") in str(pitchlog.__file__)
    assert str(ROOT / "backend/src") in str(verifier.__file__)
    chain = _chain()
    evidence = _evidence(chain, count)
    request = caller.decode_lineup_prefix_request(json.dumps(chain[count]["request"]))
    result = verifier.verify_and_evaluate_lineup_source(request, evidence)
    assert (
        result.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == chain[count]["expected"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete", False),
        ("invalid_event_count", 1),
        ("non_play_event_count", 1),
        ("pa_change_count", 1),
    ],
)
def test_incomplete_nonplay_substitution_evidence_closed(field, value):
    """不完全/非play/途中交代を資格へ昇格しない。"""
    chain = _chain()
    evidence = _evidence(chain, 2).model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    evidence[field] = value
    with pytest.raises(caller.LineupPrefixProtocolError):
        verifier.verify_and_evaluate_lineup_source(
            caller.decode_lineup_prefix_request(json.dumps(chain[2]["request"])),
            verifier.LineupSourceEvidence.model_validate_json(json.dumps(evidence)),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "tenant",
        "cursor",
        "pitcher",
        "history",
        "event",
        "order",
        "missing",
        "watermark",
        "digest",
    ],
)
def test_source_and_persisted_response_tampering_rejected(mutation):
    """actual入力/全応答/順序の改変を独立再生で拒否する。"""
    chain = _chain()
    evidence = _evidence(chain, 9).model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    request = copy.deepcopy(chain[9]["request"])
    if mutation == "tenant":
        evidence["started"]["tenant_id"] = "10000000-0000-0000-0000-000000000999"
    elif mutation == "cursor":
        evidence["plays"][0]["response"]["value"]["t1"]["after"]["battingOrderBySide"][
            "home"
        ] = "2"
    elif mutation == "pitcher":
        request["source"]["lineup"]["away"]["pitcherId"] = request["source"]["lineup"][
            "away"
        ]["catcherId"]
    elif mutation == "history":
        evidence["plays"][2]["response"]["value"]["newHistoryEntry"]["difference"][
            "statFlags"
        ]["三振"] = False
    elif mutation == "event":
        evidence["plays"][1]["identity"] = evidence["plays"][0]["identity"]
    elif mutation == "order":
        evidence["plays"][0], evidence["plays"][1] = (
            evidence["plays"][1],
            evidence["plays"][0],
        )
    elif mutation == "missing":
        evidence["plays"].pop(1)
    elif mutation == "watermark":
        evidence["plays"][0]["position_after"]["d1"] = "2"
    else:
        request["source"]["rosterDigest"] = "0" * 64
    with pytest.raises(caller.LineupPrefixProtocolError):
        verifier.verify_and_evaluate_lineup_source(
            caller.decode_lineup_prefix_request(json.dumps(request)),
            verifier.LineupSourceEvidence.model_validate_json(json.dumps(evidence)),
        )


def test_source_evidence_raw_duplicate_and_nonfinite_are_closed():
    """原本frameの重複と非有限値を辞書化で失わない。"""
    for raw in ('{"complete":true,"complete":true}', '{"complete":NaN}'):
        with pytest.raises(caller.LineupPrefixProtocolError):
            verifier.decode_lineup_source_evidence(raw)
