"""明示RBI因果をv3 wire-headへ束縛する型境界。数学期待ではない。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixProtocolError,
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
    lineup_wire_digest,
    lineup_wire_head,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads(
    (ROOT / "contracts/state-transition/batted_hit_prefix_cases_v1.json").read_text()
)["cases"][0]


def _pair(*, cause: bool, effects: bool):
    """元固定手例に新型面だけ加え、野球の正例とは主張しない。"""
    q = copy.deepcopy(BASE["request"])
    r = copy.deepcopy(BASE["expected"])
    if cause:
        q["t1"]["rbiRulingByRunner"] = {"1": "ordinary-play"}
    if effects:
        r["value"]["runnerScoreEffects"] = [
            {"base": "1", "validRun": True, "rbiCredited": True}
        ]
    return decode_lineup_prefix_request(json.dumps(q)), decode_lineup_prefix_response(
        json.dumps(r)
    )


def test_explicit_cause_and_typed_effect_are_both_in_head():
    """元観測と実効果を両方hash対象に含め、片側改変を検知する。"""
    request, response = _pair(cause=True, effects=True)
    assert response.ok
    head = lineup_wire_head(request, response)
    assert head["rbiRulingByRunner"] == {"1": "ordinary-play"}
    assert head["runnerScoreEffects"] == [
        {"base": "1", "validRun": True, "rbiCredited": True}
    ]
    old_request, old_response = _pair(cause=False, effects=False)
    assert old_response.ok
    old_head = lineup_wire_head(old_request, old_response)
    assert "rbiRulingByRunner" not in old_head
    assert "runnerScoreEffects" not in old_head
    assert lineup_wire_digest(request, response) != lineup_wire_digest(
        old_request, old_response
    )


@pytest.mark.parametrize("cause,effects", [(True, False), (False, True)])
def test_one_sided_effect_is_rejected(cause: bool, effects: bool):
    """原因のみ/結果のみを旧v3へfallbackさせない。"""
    request, response = _pair(cause=cause, effects=effects)
    assert response.ok
    with pytest.raises(LineupPrefixProtocolError):
        lineup_wire_head(request, response)
