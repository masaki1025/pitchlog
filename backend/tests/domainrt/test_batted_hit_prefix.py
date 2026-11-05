"""採用19期待を唯一artifact/固定typed callerへ通す打球prefix比較。"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitchlog.domainrt import lineup_play_prefix_continuation as caller
from pitchlog.domainrt.host import open_domain_host

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["caseId"])
def test_all_19_actual_product_host_complete_values(case):
    """先置き規範を全field比較し、成功結果を期待として採取しない。"""
    request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
    response = caller.evaluate_lineup_prefix_continuation(request)
    assert (
        response.model_dump(mode="json", by_alias=True, exclude_unset=True)
        == case["expected"]
    )


@pytest.mark.parametrize(
    "field",
    [
        "officialScoringPayload",
        "interferenceRuling",
        "runnerAdvanceOverrides",
        "thirdOutObservation",
    ],
)
def test_missing_confirmation_is_not_completed_by_typed_input(field):
    """観測が一つ不足した新variantを旧4fieldへ落とさない。"""
    wire = copy.deepcopy(CASES[0]["request"])
    del wire["t1"][field]
    with pytest.raises(caller.LineupPrefixProtocolError):
        caller.decode_lineup_prefix_request(json.dumps(wire))


def test_all_23_flags_and_new_cursor_type_are_preserved():
    """新打球のbool/number混同と新cursor欠落を実consumerで拒否する。"""
    for name, value in CASES[0]["expected"]["value"]["t1"]["statFlags"].items():
        wire = copy.deepcopy(CASES[0]["expected"])
        wire["value"]["t1"]["statFlags"][name] = int(value)
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.decode_lineup_prefix_response(json.dumps(wire))
    wire = copy.deepcopy(CASES[0]["expected"])
    del wire["value"]["newHistoryEntry"]["difference"]["battingOrderBySide"]
    with pytest.raises(caller.LineupPrefixProtocolError):
        caller.decode_lineup_prefix_response(json.dumps(wire))


def test_batted_hit_uses_one_actual_loaded_operation_and_readonly(monkeypatch):
    """実hostへ先に委譲し一回呼出と型破損拒否を確認する。"""
    from contextlib import nullcontext

    request = caller.decode_lineup_prefix_request(json.dumps(CASES[0]["request"]))
    with pytest.raises(ValidationError):
        setattr(request.t1, "result_id", "batting-result.double")
    calls = []
    with open_domain_host() as host:
        original = host.call

        def observed(operation, raw):
            calls.append(operation)
            response = json.loads(original(operation, raw))
            response["value"]["t1"]["after"]["stateFields"]["state.outs"] = 2
            return json.dumps(response)

        monkeypatch.setattr(host, "call", observed)
        monkeypatch.setattr(caller, "open_domain_host", lambda: nullcontext(host))
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller.evaluate_lineup_prefix_continuation(request)
    assert calls == ["deriveLineupPlayPrefixWithContinuation"]
