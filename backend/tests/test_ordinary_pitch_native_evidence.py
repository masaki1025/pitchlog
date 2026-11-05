"""native headの再構成を閉じたwire JSONへ固定し、python直接構成の欠陥を再発させない。"""

import json
import subprocess
from pathlib import Path

import pydantic
import pytest

from pitchlog.domainrt import lineup_prefix_source as verifier
from pitchlog.domainrt.host import NodeDomainHost, open_domain_host
from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixProtocolError,
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
    verify_lineup_wire_seal,
)
from pitchlog.sync import ordinary_pitch_execution as execution
from pitchlog.sync.terminal_pitch_payload import LineupPitchCalculation

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = "frontend/public/domain/pitchlog-domain.js"
DECLARATION = "frontend/public/domain/pitchlog-domain.json"


def _chain():
    """公開fixtureの実名簿chainを返す。DBから取得済みとは主張しない。"""
    cases = json.loads(
        (
            ROOT / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text()
    )["cases"]
    return [c for c in cases if c["caseId"].startswith("V3-STARTED-CHAIN-")]


def _accepted_host(tmp_path):
    """fixtureがpinする受理済みartifactでhostを作る。作業木の未受理差分は使わない。"""
    for relative in (ARTIFACT, DECLARATION):
        content = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        (tmp_path / Path(relative).name).write_bytes(content)
    return NodeDomainHost(
        tmp_path / "pitchlog-domain.js", tmp_path / "pitchlog-domain.json"
    )


def _roster(chain):
    """公開fixtureのlineupから実名簿投影を再構成する。"""
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
    return InitialRosterProjection.model_validate_json(json.dumps(actual["value"]))


def _previous(case):
    """保存済み1投球分のcalculationを実型で組み立てる。"""
    return LineupPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": case["request"]["source"]["executionArtifactSha256"],
                "request": case["request"],
                "response": case["expected"],
            }
        )
    )


@pytest.mark.parametrize("index", [1, 2, 8])
def test_native_evidence_rebuilt_from_wire_json_replays(index, tmp_path):
    """省略fieldをwire表現のまま保ち、native2投球目の独立再生を通す。"""
    chain = _chain()
    request = decode_lineup_prefix_request(json.dumps(chain[index]["request"]))
    roster = _roster(chain)
    previous = _previous(chain[index - 1])
    evidence = execution._native_lineup_evidence(request.source, roster, previous)
    assert type(evidence) is verifier.NativeLineupEvidence
    with _accepted_host(tmp_path) as host:
        verifier.verify_native_lineup_source(request, evidence, host)


def test_python_instance_construction_still_rejected():
    """差分欄の省略が明示nullへ戻るため、python直接構成は受理されない。"""
    chain = _chain()
    request = decode_lineup_prefix_request(json.dumps(chain[2]["request"]))
    roster = _roster(chain)
    previous = _previous(chain[1])
    with pytest.raises(pydantic.ValidationError):
        verifier.NativeLineupEvidence(
            expected_source=request.source,
            roster=roster,
            previous_request=previous.request,
            previous_response=previous.response,
        )


def test_substituted_previous_response_rejected(tmp_path):
    """直前応答の差替えを、wire sealで拒否する。"""
    chain = _chain()
    request = decode_lineup_prefix_request(json.dumps(chain[2]["request"]))
    roster = _roster(chain)
    previous = _previous(chain[1])
    tampered = previous.model_dump(mode="json", by_alias=True, exclude_unset=True)
    strikes = tampered["response"]["value"]["newHistoryEntry"]["difference"][
        "stateFields"
    ]["state.count.strikes"]
    strikes["after"] = "0" if strikes["after"] != "0" else "1"
    substituted = LineupPitchCalculation.model_validate_json(json.dumps(tampered))
    evidence = execution._native_lineup_evidence(request.source, roster, substituted)
    with _accepted_host(tmp_path) as host:
        with pytest.raises(LineupPrefixProtocolError):
            verifier.verify_native_lineup_source(request, evidence, host)


def test_host_replay_mismatch_rejected(tmp_path):
    """別時点の応答を差し込むと、前段のwire sealで拒否する。"""
    chain = _chain()
    request = decode_lineup_prefix_request(json.dumps(chain[2]["request"]))
    roster = _roster(chain)
    previous = _previous(chain[1])
    other = _previous(chain[0])
    plain = previous.model_dump(mode="json", by_alias=True, exclude_unset=True)
    plain["response"] = other.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )["response"]
    mismatched = LineupPitchCalculation.model_validate_json(json.dumps(plain))
    evidence = execution._native_lineup_evidence(request.source, roster, mismatched)
    with _accepted_host(tmp_path) as host:
        with pytest.raises(LineupPrefixProtocolError):
            verifier.verify_native_lineup_source(request, evidence, host)


@pytest.mark.parametrize("index", [1, 2, 9])
def test_actual_host_replay_response_mismatch_rejected(index, tmp_path, monkeypatch):
    """正常原本の実再生後だけ応答を改変し、全応答比較の拒否を確認する。"""
    chain = _chain()
    request = decode_lineup_prefix_request(json.dumps(chain[index]["request"]))
    roster = _roster(chain)
    previous = _previous(chain[index - 1])
    evidence = execution._native_lineup_evidence(request.source, roster, previous)
    verify_lineup_wire_seal(evidence.previous_request, evidence.previous_response)
    operation = "deriveLineupPlayPrefixWithContinuation"
    prior_json = evidence.previous_request.model_dump_json(
        by_alias=True, exclude_unset=True
    )
    expected = evidence.previous_response.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    )
    calls = []
    decoded_faults = []
    with _accepted_host(tmp_path) as host:
        assert host.artifact_sha256 == previous.artifact_sha256
        # 同じ正常Evidenceが実artifactで受理されることを先に確認する。
        verifier.verify_native_lineup_source(request, evidence, host)
        actual_call = host.call

        def replay_then_corrupt(actual_operation, actual_request):
            # 実呼出の結果を得る前に成功応答や拒否を合成しない。
            raw = actual_call(actual_operation, actual_request)
            calls.append((actual_operation, actual_request))
            assert calls == [(operation, prior_json)]
            replayed = decode_lineup_prefix_response(raw)
            assert replayed.ok is True
            assert (
                replayed.model_dump(mode="json", by_alias=True, exclude_unset=True)
                == expected
            )
            altered = json.loads(raw)
            flags = altered["value"]["t1"]["statFlags"]
            flags["投球数"] = not flags["投球数"]
            changed_raw = json.dumps(altered, ensure_ascii=False, allow_nan=False)
            changed = decode_lineup_prefix_response(changed_raw)
            assert changed.ok is True
            assert (
                changed.model_dump(mode="json", by_alias=True, exclude_unset=True)
                == altered
            )
            assert altered != expected
            decoded_faults.append(changed)
            return changed_raw

        monkeypatch.setattr(host, "call", replay_then_corrupt)
        with pytest.raises(
            LineupPrefixProtocolError,
            match="^native headの独立全応答が一致しません$",
        ):
            verifier.verify_native_lineup_source(request, evidence, host)
        assert calls == [(operation, prior_json)]
        assert len(decoded_faults) == 1
