"""v3全応答を実製品host/型境界で照合する。"""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import pitchlog
from pitchlog.domainrt import lineup_play_prefix_continuation as caller
from pitchlog.domainrt.host import open_domain_host

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads(
    (ROOT / "contracts/state-transition/lineup_play_prefix_cases_v1.json").read_text()
)["cases"]
ACTUAL = hashlib.sha256(
    (ROOT / "frontend/public/domain/pitchlog-domain.js").read_bytes()
).hexdigest()


def current_case(case):
    """正式root pinが実artifactを指すことを確認し、期待を黙って更新しない。"""
    result = copy.deepcopy(case)
    assert result["request"]["source"]["executionArtifactSha256"] == ACTUAL
    assert result["expected"]["value"]["executionArtifactSha256"] == ACTUAL
    return result


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["caseId"])
def test_all_34_actual_factory_and_typed_caller(case):
    """一回の実host評価を全値で比較し、fixture結果lookupを使わない。"""
    assert str(ROOT / "backend/src") in str(pitchlog.__file__)
    assert str(ROOT / "backend/src") in str(caller.__file__)
    case = current_case(case)
    request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
    response = caller.evaluate_lineup_prefix_continuation(request)
    assert json.dumps(
        response.model_dump(mode="json", by_alias=True, exclude_unset=True),
        sort_keys=True,
    ) == json.dumps(case["expected"], sort_keys=True)


def test_decode_rejects_all_23_numeric_flags_unknown_duplicate_nonfinite():
    """全flagのbool/number混同を実typed consumerで拒否する。"""
    expected = copy.deepcopy(CASES[0]["expected"])
    for flag, value in expected["value"]["t1"]["statFlags"].items():
        bad = copy.deepcopy(expected)
        bad["value"]["t1"]["statFlags"][flag] = int(value)
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(json.dumps(bad))
    for raw in [
        '{"ok":false,"ok":false,"error":{"code":"INVALID_REQUEST"}}',
        '{"x":NaN}',
    ]:
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(raw)
    request = copy.deepcopy(CASES[0]["request"])
    request["unknown"] = True
    with pytest.raises(caller.LineupPrefixProtocolError):
        caller.decode_lineup_prefix_request(json.dumps(request))
    for raw in ['{"version":"3","version":"3"}', '{"x":Infinity}']:
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_request(raw)


def test_actual_source_mismatch_is_rejected_before_call(monkeypatch):
    """別のartifactを成功扱いしない。factoryは実host、call到達だけ監視する。"""
    request = caller.decode_lineup_prefix_request(json.dumps(CASES[0]["request"]))
    wire = copy.deepcopy(CASES[0]["request"])
    wire["source"]["executionArtifactSha256"] = "0" * 64
    request = caller.decode_lineup_prefix_request(json.dumps(wire))
    with pytest.raises(caller.LineupPrefixProtocolError):
        caller.evaluate_lineup_prefix_continuation(request)


def test_one_real_host_call_and_readonly(monkeypatch):
    """固定応答stubなしで実一回callを数え、変更可能aliasを拒否する。"""
    case = current_case(CASES[0])
    request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
    with pytest.raises(ValidationError):
        setattr(request.source.lineup.away, "pitcher_id", "modified")
    calls = []
    with open_domain_host() as host:
        original = host.call

        def counted(operation, raw):
            calls.append(operation)
            return original(operation, raw)

        monkeypatch.setattr(host, "call", counted)
        from contextlib import nullcontext

        monkeypatch.setattr(caller, "open_domain_host", lambda: nullcontext(host))
        assert caller.evaluate_lineup_prefix_continuation(request).ok
    assert calls == ["deriveLineupPlayPrefixWithContinuation"]


def test_all_34_wire_heads_and_only_self_echo_sealing():
    """正式head32fieldを実consumerで照合し自己echo以外を変更しない。"""
    vectors = json.loads(
        (
            ROOT
            / "contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json"
        ).read_text()
    )["cases"]
    for case, payload in zip(CASES, vectors, strict=True):
        request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
        response = caller.decode_lineup_prefix_response(json.dumps(case["expected"]))
        assert response.ok
        assert caller.lineup_wire_head(request, response) == payload["wireHead"]
        assert caller.lineup_wire_digest(request, response) == payload["wireDigest"]
        caller.verify_lineup_wire_seal(request, response)
        changed_request = copy.deepcopy(case["request"])
        changed_response = copy.deepcopy(case["expected"])
        changed_request["nextCheckpoint"]["digest"] = "0" * 64
        changed_response["value"]["nextPrefixRef"]["checkpoint"]["digest"] = "0" * 64
        changed_typed_response = caller.decode_lineup_prefix_response(
            json.dumps(changed_response)
        )
        assert changed_typed_response.ok
        sealed_request, sealed_response = caller.seal_lineup_wire(
            caller.decode_lineup_prefix_request(json.dumps(changed_request)),
            changed_typed_response,
        )
        assert sealed_request == request
        assert sealed_response == response


def test_wire_commits_prior_digest_before_runners_history_and_all_selected_fields():
    """digestという名前を再帰除外せず、前source/全履歴を拘束する。"""
    case = copy.deepcopy(CASES[2])
    request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
    response = caller.decode_lineup_prefix_response(json.dumps(case["expected"]))
    assert response.ok
    head = caller.lineup_wire_head(request, response)
    digest = caller.lineup_wire_digest(request, response)
    assert len(head) == 32
    for field in head:
        changed = copy.deepcopy(head)
        changed[field] = None
        encoded = json.dumps(
            changed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        assert hashlib.sha256(encoded.encode()).hexdigest() != digest
    for path in [
        ("source", "prefixRef", "checkpoint", "digest"),
        ("source", "runners", 0, "responsiblePitcherId"),
        ("source", "t2", "facts", "beforeInning"),
    ]:
        changed = copy.deepcopy(case["request"])
        cursor = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = (
            "1"
            if path[-1] == "beforeInning"
            else "10000000-0000-0000-0000-000000000999"
            if path[-1] == "responsiblePitcherId"
            else "f" * 64
        )
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.verify_lineup_wire_seal(
                caller.decode_lineup_prefix_request(json.dumps(changed)), response
            )


def test_new_head_cursor_is_required_and_never_synthesized():
    """SO新headのcursor差分を欠落/空にして成功へ補完しない。"""
    for replacement in (None, {}):
        bad = copy.deepcopy(CASES[0]["expected"])
        difference = bad["value"]["newHistoryEntry"]["difference"]
        if replacement is None:
            del difference["battingOrderBySide"]
        else:
            difference["battingOrderBySide"] = replacement
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(json.dumps(bad))


def test_decision_literal_union_matches_real_schema_for_all_flags_and_enums():
    """P1対向: 7 outcome全bool/表示組を実schemaと実decoderで同じ閉集合にする。"""
    from itertools import product

    from jsonschema import Draft202012Validator

    schema = json.loads(
        (
            ROOT / "contracts/state-transition/lineup_play_prefix_schema_v1.json"
        ).read_text()
    )
    validator = Draft202012Validator(schema["$defs"]["Decision"])
    outcomes = [
        "no-end",
        "normal-end",
        "extra-continue",
        "limit-draw",
        "tiebreak-continue",
        "cold-end",
        "walk-off",
        "unknown",
    ]
    fields = [
        "endConditionDetected",
        "lockFurtherPlayInput",
        "promptEndDeclaration",
        "automaticallyEndsGame",
    ]
    accepted = 0
    rejected = 0
    for outcome, flags, mark in product(
        outcomes,
        product([False, True], repeat=4),
        ["recorded-score", "x-mark", "unknown"],
    ):
        decision = {
            "outcome": outcome,
            "xMark": mark,
            **dict(zip(fields, flags, strict=True)),
        }
        raw = copy.deepcopy(CASES[0]["expected"])
        raw["value"]["t2"]["decision"] = decision
        if validator.is_valid(decision):
            assert caller.decode_lineup_prefix_response(json.dumps(raw)).ok
            accepted += 1
        else:
            with pytest.raises(caller.LineupPrefixProtocolError):
                caller.decode_lineup_prefix_response(json.dumps(raw))
            rejected += 1
    assert accepted == 9
    assert rejected == 375
    valid = copy.deepcopy(CASES[0]["expected"])
    for field in fields:
        bad = copy.deepcopy(valid)
        bad["value"]["t2"]["decision"][field] = int(
            bad["value"]["t2"]["decision"][field]
        )
        assert not validator.is_valid(bad["value"]["t2"]["decision"])
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(json.dumps(bad))
    for change in ("extra", "missing"):
        bad = copy.deepcopy(valid)
        if change == "extra":
            bad["value"]["t2"]["decision"]["unknown"] = True
        else:
            del bad["value"]["t2"]["decision"]["lockFurtherPlayInput"]
        assert not validator.is_valid(bad["value"]["t2"]["decision"])
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(json.dumps(bad))


def test_actual_cold05_strikeout_completed_bottom_retains_recorded_score():
    """P1対向: 既COLD05の有効SOをschema/typed callerの両方が受理する。"""
    from jsonschema import Draft202012Validator

    wire = copy.deepcopy(CASES[5]["request"])
    wire["rules"]["coldConditions"] = [{"pointDifference": "7", "startInning": "7"}]
    wire["source"]["rules"] = copy.deepcopy(wire["rules"])
    before = wire["t1"]["before"]
    before["stateFields"]["state.inning"] = "7"
    before["stateFields"]["state.score"] = {"home": "0", "away": "7"}
    before["scoreboard"]["inningScores"] = {"home": "0", "away": "7"}
    wire["source"]["after"] = copy.deepcopy(before)
    wire["source"]["t2"]["facts"]["beforeInning"] = "7"
    wire["source"]["t2"]["facts"]["afterInning"] = "7"
    response = caller.evaluate_lineup_prefix_continuation(
        caller.decode_lineup_prefix_request(json.dumps(wire))
    )
    assert response.ok
    assert response.value.t2.decision.outcome == "cold-end"
    assert response.value.t2.decision.x_mark == "recorded-score"
    assert response.value.t1.after.state_fields.half == "top"
    assert response.value.t2.facts.half_completed is True
    schema = json.loads(
        (
            ROOT / "contracts/state-transition/lineup_play_prefix_schema_v1.json"
        ).read_text()
    )
    Draft202012Validator(schema["$defs"]["Decision"]).validate(
        response.value.t2.decision.model_dump(mode="json", by_alias=True)
    )


def test_request_source_decision_uses_same_closed_literal_variants():
    """source側も応答と同じ型であり、flag偽装/数値coercionを拒否する。"""
    for value in (True, 0):
        wire = copy.deepcopy(CASES[0]["request"])
        wire["source"]["t2"]["decision"]["endConditionDetected"] = value
        with pytest.raises((ValueError, caller.LineupPrefixProtocolError)):
            caller.decode_lineup_prefix_request(json.dumps(wire))
        with pytest.raises(ValueError):
            caller.LineupPrefixRequest.model_validate_json(
                json.dumps(wire), by_alias=True, by_name=False
            )


def test_prior_boundary_innings_are_positive_in_request_and_response():
    """P1対向: 前/後の回0を既Positive型で拒否し、算式は追加しない。"""
    for field in ("beforeInning", "afterInning"):
        request = copy.deepcopy(CASES[0]["request"])
        request["source"]["t2"]["facts"][field] = "0"
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_request(json.dumps(request))
        response = copy.deepcopy(CASES[0]["expected"])
        response["value"]["t2"]["facts"][field] = "0"
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(json.dumps(response))
