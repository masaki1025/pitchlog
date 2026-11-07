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


NORMATIVE_EXECUTION = "9ae9d16db1f2fa48905eb0ac951c8cb3ce5704dfe308df95a7a0bba155f33d19"


def current_case(case):
    """既規範の実行pin二欄と依存自己echoだけを現物へ束縛する。"""
    result = copy.deepcopy(case)
    # 不明な入力pinを修復しない。規範row以外の入力を現行互換へ格上げしない。
    assert result["request"]["source"]["executionArtifactSha256"] == NORMATIVE_EXECUTION
    assert result["expected"]["value"]["executionArtifactSha256"] == NORMATIVE_EXECUTION
    result["request"]["source"]["executionArtifactSha256"] = ACTUAL
    result["expected"]["value"]["executionArtifactSha256"] = ACTUAL
    request = caller.decode_lineup_prefix_request(json.dumps(result["request"]))
    response = caller.decode_lineup_prefix_response(json.dumps(result["expected"]))
    assert response.ok
    digest = caller.lineup_wire_digest(request, response)
    result["request"]["nextCheckpoint"]["digest"] = digest
    result["expected"]["value"]["nextPrefixRef"]["checkpoint"]["digest"] = digest
    return result


def test_current_case_changes_only_execution_metadata_and_is_reversible():
    """旧数学/保存元pin/全fieldを保持し、自己echo以外の緩和を拒否する。"""
    for case in CASES:
        original = copy.deepcopy(case)
        bound = current_case(case)
        assert case == original
        assert bound["request"]["source"]["executionArtifactSha256"] == ACTUAL
        assert bound["expected"]["value"]["executionArtifactSha256"] == ACTUAL
        request = caller.decode_lineup_prefix_request(json.dumps(bound["request"]))
        response = caller.decode_lineup_prefix_response(json.dumps(bound["expected"]))
        assert response.ok
        caller.verify_lineup_wire_seal(request, response)
        bound["request"]["source"]["executionArtifactSha256"] = NORMATIVE_EXECUTION
        bound["expected"]["value"]["executionArtifactSha256"] = NORMATIVE_EXECUTION
        bound["request"]["nextCheckpoint"]["digest"] = original["request"][
            "nextCheckpoint"
        ]["digest"]
        bound["expected"]["value"]["nextPrefixRef"]["checkpoint"]["digest"] = original[
            "expected"
        ]["value"]["nextPrefixRef"]["checkpoint"]["digest"]
        assert bound == original


@pytest.mark.parametrize("side", ["request", "expected"])
def test_current_case_rejects_unknown_execution_pin(side):
    """未知元pinの片側差替は実host呼出前にも閉拒否する。"""
    case = copy.deepcopy(CASES[0])
    if side == "request":
        case["request"]["source"]["executionArtifactSha256"] = "0" * 64
    else:
        case["expected"]["value"]["executionArtifactSha256"] = "0" * 64
    with pytest.raises(AssertionError):
        current_case(case)


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
            ROOT / "frontend/src/api/fixtures/currentLineupPrefixPayload.v1.json"
        ).read_text()
    )["cases"]
    for original, payload in zip(CASES, vectors, strict=True):
        case = current_case(original)
        assert case["caseId"] == payload["caseId"]
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

    wire = current_case(CASES[5])["request"]
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


def _nonplay_request(index, linked=False):
    """旧構造手例へ有効名簿を明示派生し、6状態/三headは保持する。"""
    bridge = json.loads(
        (
            ROOT / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"
        ).read_text()
    )
    source = copy.deepcopy(
        bridge["crossGenerationCase"]["source"]
        if linked
        else bridge["steps"][index]["source"]
    )
    valid = CASES[0]["request"]["source"]
    contexts = [source["checkpoint"]["content"]["restored"]]
    for frame in source["activeStack"]:
        contexts.extend([frame["beforeContext"], frame["afterContext"]])
    for context in contexts:
        for key in ("rules", "lineup", "participants"):
            context[key] = copy.deepcopy(valid[key])
        context["rulesDigest"] = hashlib.sha256(
            json.dumps(
                context["rules"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        context["layoutDigest"] = hashlib.sha256(
            json.dumps(
                context["lineup"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        context["rosterDigest"] = context["layoutDigest"]
    c = source["checkpoint"]["content"]
    c["executionArtifactSha256"] = ACTUAL
    cp = source["checkpoint"]["ref"]
    cp["digest"] = hashlib.sha256(
        json.dumps(
            c,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return {
        "version": "nonplay-continuation-v1",
        "prefixRef": copy.deepcopy(cp),
        "rules": copy.deepcopy(c["restored"]["rules"]),
        "t1": {
            "eventKind": "batting-result",
            "resultId": "batting-result.ball",
            "pitchEventKind": "pitch-event",
            "before": copy.deepcopy(c["restored"]["current"]),
        },
        "source": source,
        "playIdentity": {
            "eventId": "00000000-0000-4000-8000-0000000008a1",
            "d5": "00000000-0000-4000-8000-0000000008a2",
            "playId": "00000000-0000-4000-8000-0000000008a3",
        },
        "nextCheckpoint": {
            "id": "00000000-0000-4000-8000-0000000008a4",
            "revision": str(int(cp["revision"]) + 1),
            "digest": "f" * 64,
        },
        "sourcePosition": {
            "d1": str(int(c["d3"]) + 1),
            "d2": "3072",
            "appliedWatermark": c["d3"],
        },
    }


def _nonplay_expected(r, called=False):
    """球数の手導出だけを期待へ置き、製品計算出力を採取しない。"""
    c = r["source"]["checkpoint"]["content"]["restored"]
    before = c["current"]
    field = "state.count.strikes" if called else "state.count.balls"
    old = before["stateFields"][field]
    new = {"0": "1", "1": "2", "2": "3"}[old]
    after = copy.deepcopy(before)
    after["stateFields"][field] = new
    bridge = json.loads(
        (
            ROOT / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"
        ).read_text()
    )
    flags = bridge["steps"][1]["event"]["state_diff"]["difference"]["statFlags"]
    decision = {
        "outcome": "no-end",
        "endConditionDetected": False,
        "lockFurtherPlayInput": False,
        "promptEndDeclaration": False,
        "automaticallyEndsGame": False,
        "xMark": "recorded-score",
    }
    return {
        "ok": True,
        "value": {
            "t1": {
                "countEffect": {
                    "strikes": (
                        {"kind": "delta", "value": "1"}
                        if called
                        else {"kind": "unchanged"}
                    ),
                    "balls": (
                        {"kind": "unchanged"}
                        if called
                        else {"kind": "delta", "value": "1"}
                    ),
                },
                "plateAppearanceEnded": False,
                "batterDestination": {"kind": "continue"},
                "runnerDefaultAdvance": {
                    base: {"modality": "not-applicable", "destination": None}
                    for base in ["first", "second", "third"]
                },
                "outEffect": {"count": "0", "targets": []},
                "statFlags": flags,
                "after": after,
            },
            "t2": {
                "kind": "evaluated-end-condition",
                "scope": "play-prefix-v3",
                "evaluation_point": "post-play",
                "facts": {
                    "beforeInning": "1",
                    "beforeHalf": "top",
                    "beforeOuts": "0",
                    "afterInning": "1",
                    "afterHalf": "top",
                    "afterOuts": "0",
                    "halfCompleted": False,
                    "outsUnchanged": True,
                    "scoreUnchanged": True,
                    "priorOpen": True,
                },
                "decision": decision,
                "tiebreakStartRequired": False,
            },
            "newHistoryEntry": {
                "kind": "confirmed-play",
                "difference": {
                    "stateFields": {field: {"before": old, "after": new}},
                    "scoreboard": {},
                    "statFlags": flags,
                    "battingOrderBySide": {},
                },
            },
            "previousPrefixRef": r["prefixRef"],
            "nextPrefixRef": r["nextCheckpoint"],
            "runners": c["runners"],
            "beforeParticipants": c["participants"],
            "participants": c["participants"],
            "lineup": c["lineup"],
            "rosterDigest": c["rosterDigest"],
            "responsibility": c["responsibility"],
            "nextResponsibility": c["responsibility"],
            "playIdentity": r["playIdentity"],
            "sourcePosition": r["sourcePosition"],
            "executionArtifactSha256": ACTUAL,
        },
    }


@pytest.mark.parametrize("index", range(6))
def test_nonplay_six_actual_host_responses(index):
    """実同一artifactで三head/空activeを保持した全応答を照合する。"""
    r = _nonplay_request(index)
    saved = copy.deepcopy(r)
    request = caller.decode_nonplay_lineup_prefix_request(json.dumps(r))
    response = caller.evaluate_nonplay_lineup_prefix_continuation(request)
    assert response.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    ) == _nonplay_expected(r)
    assert r == saved


def test_nonplay_host_one_call_immutable_and_failure_propagation(monkeypatch):
    """本物一回hostと不変型を確認し、host故障を内容拒否へ変換しない。"""
    from contextlib import nullcontext

    r = _nonplay_request(4)
    request = caller.decode_nonplay_lineup_prefix_request(json.dumps(r))
    with pytest.raises(ValidationError):
        setattr(request.source.checkpoint.content, "d3", "0")
    calls = []
    with open_domain_host() as host:
        original = host.call

        def counted(operation, raw):
            calls.append(operation)
            return original(operation, raw)

        monkeypatch.setattr(host, "call", counted)
        monkeypatch.setattr(caller, "open_domain_host", lambda: nullcontext(host))
        response = caller.evaluate_nonplay_lineup_prefix_continuation(request)
        assert response.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        ) == _nonplay_expected(r)
    assert calls == ["deriveLineupPlayPrefixWithContinuation"]

    def failed():
        raise RuntimeError("owned nonplay host unavailable")

    monkeypatch.setattr(caller, "open_domain_host", failed)
    with pytest.raises(RuntimeError, match="owned nonplay host unavailable"):
        caller.evaluate_nonplay_lineup_prefix_continuation(request)


def test_nonplay_closed_decoder_and_exact_flags():
    """余剰/重複/非有限/全23数値flag/旧参照混在を拒否する。"""
    r = _nonplay_request(4)
    for target in [r, r["source"], r["source"]["checkpoint"]["content"]]:
        target["unknown"] = True
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_nonplay_lineup_prefix_request(json.dumps(r))
        del target["unknown"]
    for bad in [
        '{"version":"nonplay-continuation-v1","version":"nonplay-continuation-v1"}',
        '{"x":NaN}',
    ]:
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_nonplay_lineup_prefix_request(bad)
    expected = _nonplay_expected(r)
    for key, value in expected["value"]["t1"]["statFlags"].items():
        bad = copy.deepcopy(expected)
        bad["value"]["t1"]["statFlags"][key] = int(value)
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_nonplay_lineup_prefix_response(json.dumps(bad))
    bad = copy.deepcopy(expected)
    bad["value"]["nextPrefixRef"] = CASES[0]["expected"]["value"]["nextPrefixRef"]
    with pytest.raises(caller.LineupPrefixProtocolError):
        caller.decode_nonplay_lineup_prefix_response(json.dumps(bad))


def test_nonplay_actual_execution_hash_is_checked_before_host_call(monkeypatch):
    """Source文字列の自己宣言を実loaded artifactと照合し、相違を実行しない。"""
    from contextlib import nullcontext

    wire = _nonplay_request(4)
    wire["source"]["checkpoint"]["content"]["executionArtifactSha256"] = "0" * 64
    request = caller.decode_nonplay_lineup_prefix_request(json.dumps(wire))
    calls = []
    with open_domain_host() as host:
        original = host.call

        def observed(operation, raw):
            calls.append(operation)
            return original(operation, raw)

        monkeypatch.setattr(host, "call", observed)
        monkeypatch.setattr(caller, "open_domain_host", lambda: nullcontext(host))
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.evaluate_nonplay_lineup_prefix_continuation(request)
    assert calls == []


def test_nonplay_real_host_call_failure_is_not_a_content_rejection(monkeypatch):
    """生成hostは真正のままcall障害を伝播し、False応答にしない。"""
    from contextlib import nullcontext

    request = caller.decode_nonplay_lineup_prefix_request(
        json.dumps(_nonplay_request(4))
    )
    calls = []
    with open_domain_host() as host:

        def failed(operation, raw):
            calls.append(operation)
            raise RuntimeError("owned nonplay call unavailable")

        monkeypatch.setattr(host, "call", failed)
        monkeypatch.setattr(caller, "open_domain_host", lambda: nullcontext(host))
        with pytest.raises(RuntimeError, match="owned nonplay call unavailable"):
            caller.evaluate_nonplay_lineup_prefix_continuation(request)
    assert calls == ["deriveLineupPlayPrefixWithContinuation"]


def test_nonplay_linked_prior_generation_active_is_not_initial_zero():
    """ownD3=0でも世代連結済みprior activeを消さず実hostに渡す。"""
    wire = _nonplay_request(2, linked=True)
    content = wire["source"]["checkpoint"]["content"]
    assert content["d3"] == "0" and content["activeDepth"] == "2"
    assert content["scope"]["generation"] == "2" and content["d1Head"] is None
    request = caller.decode_nonplay_lineup_prefix_request(json.dumps(wire))
    response = caller.evaluate_nonplay_lineup_prefix_continuation(request)
    assert response.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    ) == _nonplay_expected(wire)


def test_nonplay_mixed_generation_two_actual_operations_continue_from_real_output():
    """実after/履歴をそのまま次Sourceへ積み、世代2D1=1の後にも続ける。"""
    wire = _nonplay_request(2, linked=True)
    first = caller.evaluate_nonplay_lineup_prefix_continuation(
        caller.decode_nonplay_lineup_prefix_request(json.dumps(wire))
    )
    actual = first.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert actual == _nonplay_expected(wire)
    value = actual["value"]
    content = wire["source"]["checkpoint"]["content"]
    before = copy.deepcopy(content["restored"])
    after = copy.deepcopy(before)
    after.update(
        current=copy.deepcopy(value["t1"]["after"]),
        participants=copy.deepcopy(value["participants"]),
        runners=copy.deepcopy(value["runners"]),
        responsibility=copy.deepcopy(value["nextResponsibility"]),
        lastPlayEvaluation=copy.deepcopy(value["t2"]),
    )
    event = {
        "eventId": wire["playIdentity"]["eventId"],
        "gameId": content["scope"]["gameId"],
        "generation": content["scope"]["generation"],
        "d1": wire["sourcePosition"]["d1"],
        "d5": wire["playIdentity"]["d5"],
        "fingerprint": "wire-v1:" + "b" * 64,
        "eventKind": "play_input",
    }
    play = {
        "source": event,
        "playId": wire["playIdentity"]["playId"],
        "d2": wire["sourcePosition"]["d2"],
        "physicalPlayNumber": content["nextPhysicalPlayNumber"],
    }
    wire["source"]["activeStack"].insert(
        0,
        {
            "play": play,
            "historyEntry": copy.deepcopy(value["newHistoryEntry"]),
            "beforeContext": before,
            "afterContext": after,
        },
    )
    content.update(
        restored=after,
        d3=event["d1"],
        d1Head={"kind": "accepted-event", "source": copy.deepcopy(event)},
        projectionHead={"kind": "d1-event", "source": copy.deepcopy(event)},
        activeHead=copy.deepcopy(play),
        activeDepth="3",
        historyVersion=str(int(content["historyVersion"]) + 1),
        nextPhysicalPlayNumber="4",
    )
    wire["source"]["checkpoint"]["ref"] = copy.deepcopy(value["nextPrefixRef"])
    wire["source"]["checkpoint"]["ref"]["digest"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    wire["prefixRef"] = copy.deepcopy(wire["source"]["checkpoint"]["ref"])
    wire["t1"]["before"] = copy.deepcopy(value["t1"]["after"])
    wire["t1"]["resultId"] = "batting-result.called-pitch"
    wire["sourcePosition"] = {"d1": "2", "d2": "4096", "appliedWatermark": "1"}
    wire["playIdentity"] = {
        "eventId": "00000000-0000-4000-8000-0000000008b1",
        "d5": "00000000-0000-4000-8000-0000000008b2",
        "playId": "00000000-0000-4000-8000-0000000008b3",
    }
    wire["nextCheckpoint"] = {
        "id": "00000000-0000-4000-8000-0000000008b4",
        "revision": "22",
        "digest": "a" * 64,
    }
    assert [
        (x["play"]["source"]["generation"], x["play"]["source"]["d1"])
        for x in wire["source"]["activeStack"]
    ] == [("2", "1"), ("1", "2"), ("1", "1")]
    saved = copy.deepcopy(wire)
    second = caller.evaluate_nonplay_lineup_prefix_continuation(
        caller.decode_nonplay_lineup_prefix_request(json.dumps(wire))
    )
    assert second.model_dump(
        mode="json", by_alias=True, exclude_unset=True
    ) == _nonplay_expected(wire, called=True)
    assert wire == saved
