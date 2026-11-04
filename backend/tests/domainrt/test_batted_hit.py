"""独立16手例/23,328交差と、唯一artifactへの固定一回callを検証する。"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from collections.abc import Iterator
from contextlib import nullcontext
from itertools import product
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pitchlog.domainrt.batted_hit import (
    BattedHitProtocolError,
    BattedHitRequest,
    BattedHitResponse,
    decode_batted_hit_response,
    evaluate_batted_hit,
)
from pitchlog.domainrt.host import DomainRuntimeError, NodeDomainHost, open_domain_host

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "contracts/state-transition"
_VECTORS = json.loads((_BASE / "batted_hit_cases_v1.json").read_text())
_SCHEMA = json.loads((_BASE / "batted_hit_schema_v1.json").read_text())
_RESPONSE_SCHEMA = Draft202012Validator(_SCHEMA)
_REQUEST_SCHEMA = Draft202012Validator(
    {"$ref": "#/$defs/BattedHitRequest", "$defs": _SCHEMA["$defs"]}
)
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


def _wire(response: BattedHitResponse) -> dict[str, Any]:
    """計算・補完なしに、返却された全wire値を写す。"""
    return response.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _request(value: dict[str, Any]) -> BattedHitRequest:
    """厳密JSON入力だけから型付き要求を作る。"""
    return BattedHitRequest.model_validate_json(
        json.dumps(value), by_alias=True, by_name=False
    )


@pytest.fixture(scope="module")
def actual_host() -> Iterator[NodeDomainHost]:
    """正式製品pathの実artifactだけを検証し、一つのhost寿命を所有する。"""
    with open_domain_host() as host:
        yield host


@pytest.mark.parametrize("case", _VECTORS["cases"], ids=lambda c: c["caseId"])
def test_independent_full_cases_reach_actual_fixed_host_once(case, actual_host) -> None:
    """固定前期待と全値一致し、operation/要求と実委譲一回を確認する。"""
    _REQUEST_SCHEMA.validate(case["request"])
    _RESPONSE_SCHEMA.validate(case["expected"])
    request = _request(case["request"])
    with (
        patch(
            "pitchlog.domainrt.batted_hit.open_domain_host",
            return_value=nullcontext(actual_host),
        ),
        patch.object(actual_host, "call", wraps=actual_host.call) as delegated,
    ):
        result = evaluate_batted_hit(request)
    assert _wire(result) == case["expected"]
    delegated.assert_called_once_with(
        "deriveBattedHit", request.model_dump_json(by_alias=True, exclude_unset=True)
    )
    assert (
        hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
        == actual_host.artifact_sha256
    )
    assert actual_host.artifact_sha256 == json.loads(_DECLARATION.read_text())["sha256"]


def _crossing(
    case: dict[str, Any], outs: str, strikes: str, balls: str, order: str, inactive: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """規範手例と独立NEXT表だけで展開し、製品結果を期待生成に使わない。"""
    request = copy.deepcopy(case["request"])
    expected = copy.deepcopy(case["expected"])
    fields = request["before"]["stateFields"]
    active = "away" if fields["state.half"] == "top" else "home"
    other = "home" if active == "away" else "away"
    next_order = _VECTORS["crossProduct"]["nextBattingOrder"][order]
    fields.update(
        {
            "state.outs": outs,
            "state.count.strikes": strikes,
            "state.count.balls": balls,
            "state.battingOrder": order,
        }
    )
    request["before"]["battingOrderBySide"] = {active: order, other: inactive}
    value = expected["value"]
    value["after"]["stateFields"].update(
        {"state.outs": outs, "state.battingOrder": next_order}
    )
    value["after"]["battingOrderBySide"] = {active: next_order, other: inactive}
    diff = value["historyContext"][0]["difference"]
    for key, before in (("state.count.strikes", strikes), ("state.count.balls", balls)):
        if before == "0":
            diff["stateFields"].pop(key)
        else:
            diff["stateFields"][key] = {"before": before, "after": "0"}
    diff["stateFields"]["state.battingOrder"] = {"before": order, "after": next_order}
    diff["battingOrderBySide"] = {active: {"before": order, "after": next_order}}
    return request, expected


def test_all_23328_crossings_match_full_wire_on_actual_artifact(actual_host) -> None:
    """4結果/両half/outs/count/独立両cursorの全応答を実VMで比較する。"""
    count = 0
    for case in _VECTORS["cases"]:
        if case["request"]["before"]["stateFields"]["state.battingOrder"] != "1":
            continue
        for values in product(
            ("0", "1", "2"),
            ("0", "1", "2"),
            ("0", "1", "2", "3"),
            map(str, range(1, 10)),
            map(str, range(1, 10)),
        ):
            request, expected = _crossing(case, *values)
            actual = json.loads(
                actual_host.call("deriveBattedHit", json.dumps(request))
            )
            assert actual == expected, (case["caseId"], values)
            count += 1
    assert count == 23328


@pytest.mark.parametrize("case", _VECTORS["rejectionCases"], ids=lambda c: c["caseId"])
def test_fixed_rejections_keep_expected_error_code(case, actual_host) -> None:
    """型の壊れた入力も固定artifactの公開入口で検証する。"""
    base = next(c for c in _VECTORS["cases"] if c["caseId"] == case["baseCaseId"])
    request = copy.deepcopy(base["request"])
    target = request
    keys = case["replace"]["path"].strip("/").split("/")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = case["replace"]["value"]
    if case["caseId"] == "BH-REJECT-NUMBER":
        # JS入口ではINVALID_REQUEST、固定hostは数値JSONをより前段で拒否する。
        # 既host境界を緩めず、固有の拒否codeを明示的に検証する。
        with pytest.raises(DomainRuntimeError, match="整数は十進文字列") as rejected:
            actual_host.call("deriveBattedHit", json.dumps(request))
        assert rejected.value.code == "INVALID_BOUNDARY"
        with pytest.raises(ValidationError):
            _request(request)
    else:
        assert (
            json.loads(actual_host.call("deriveBattedHit", json.dumps(request)))
            == case["expected"]
        )


def test_past_tail_and_huge_integer_are_preserved_by_typed_caller() -> None:
    """tailの順序・省略とbigintの文字列表現を変更しない。"""
    case = _VECTORS["cases"][0]
    request = copy.deepcopy(case["request"])
    expected = copy.deepcopy(case["expected"])
    tail = copy.deepcopy(case["expected"]["value"]["historyContext"])
    request["history"]["stack"] = tail
    expected["value"]["historyContext"].extend(tail)
    before = "90071992547409931234567890123456789"
    after = "90071992547409931234567890123456790"
    request["before"]["scoreboard"]["hits"] = before
    expected["value"]["after"]["scoreboard"]["hits"] = after
    expected["value"]["historyContext"][0]["difference"]["scoreboard"]["hits"] = {
        "before": before,
        "after": after,
    }
    typed = _request(request)
    assert _wire(evaluate_batted_hit(typed)) == expected
    with pytest.raises(ValidationError):
        setattr(typed.before.state_fields, "balls", "0")
    assert (
        json.loads(typed.model_dump_json(by_alias=True, exclude_unset=True)) == request
    )


@pytest.mark.parametrize("field", tuple(_VECTORS["cases"][0]["request"]))
def test_request_missing_fields_are_not_defaulted(field) -> None:
    """確定観測を含む全9必須fieldの欠落を拒否する。"""
    request = copy.deepcopy(_VECTORS["cases"][0]["request"])
    request.pop(field)
    with pytest.raises(ValidationError):
        _request(request)


@pytest.mark.parametrize("mutation", ("extra", "alias", "coercion", "forged"))
def test_request_is_closed_and_revalidated_before_opening_host(mutation) -> None:
    """未知/内部alias/型変換とmodel_copyの未検証値をhost前で拒否する。"""
    request = copy.deepcopy(_VECTORS["cases"][0]["request"])
    if mutation == "extra":
        request["extra"] = True
    elif mutation == "alias":
        request["event_kind"] = request.pop("eventKind")
    elif mutation == "coercion":
        request["before"]["stateFields"]["state.count.balls"] = 3
    with patch("pitchlog.domainrt.batted_hit.open_domain_host") as opened:
        with pytest.raises(ValidationError):
            if mutation == "forged":
                value = _request(request).model_copy(
                    update={"result_id": "batting-result.walk"}
                )
                evaluate_batted_hit(value)
            else:
                _request(request)
        opened.assert_not_called()


@pytest.mark.parametrize("case", _VECTORS["cases"][::4], ids=lambda c: c["caseId"])
@pytest.mark.parametrize(
    "mutation",
    (
        "cursor-missing",
        "cursor-empty",
        "after-runner",
        "destination",
        "head-flags",
        "unknown",
        "ok-number",
        "null-diff",
    ),
)
def test_corrupt_actual_response_is_rejected_after_real_host_delegation(
    mutation, actual_host, case
) -> None:
    """成功VMへ先に到達し、その返却だけを試験内で破壊して拒否を確認する。"""
    request = _request(case["request"])
    original_call = actual_host.call
    seen = []

    def corrupt(operation, text):
        raw = original_call(operation, text)
        seen.append((operation, json.loads(text)))
        value = json.loads(raw)
        if mutation == "cursor-missing":
            value["value"]["historyContext"][0]["difference"].pop("battingOrderBySide")
        elif mutation == "cursor-empty":
            value["value"]["historyContext"][0]["difference"]["battingOrderBySide"] = {}
        elif mutation == "after-runner":
            fields = value["value"]["after"]["stateFields"]
            fields["state.runners"] = (
                "first" if fields["state.runners"] != "first" else "second"
            )
        elif mutation == "destination":
            target = value["value"]["batterDestination"]
            target["base"] = "2" if target.get("base") == "1" else "1"
        elif mutation == "head-flags":
            value["value"]["historyContext"][0]["difference"]["statFlags"]["安打"] = (
                False
            )
        elif mutation == "unknown":
            value["value"]["unexpected"] = True
        elif mutation == "ok-number":
            value["ok"] = 1
        else:
            value["value"]["historyContext"][0]["difference"]["stateFields"][
                "state.outs"
            ] = None
        return json.dumps(value)

    with (
        patch(
            "pitchlog.domainrt.batted_hit.open_domain_host",
            return_value=nullcontext(actual_host),
        ),
        patch.object(actual_host, "call", side_effect=corrupt) as delegated,
        pytest.raises(BattedHitProtocolError, match="固定ABI"),
    ):
        evaluate_batted_hit(request)
    assert len(seen) == 1
    assert seen[0] == ("deriveBattedHit", case["request"])
    delegated.assert_called_once()


@pytest.mark.parametrize(
    "field", tuple(_VECTORS["cases"][0]["expected"]["value"]["statFlags"])
)
def test_each_stat_flag_corruption_is_rejected_by_schema_and_decoder(field) -> None:
    """23flagのどれも暗黙変換・無視せず拒否する。"""
    value = copy.deepcopy(_VECTORS["cases"][0]["expected"])
    value["value"]["statFlags"][field] = not value["value"]["statFlags"][field]
    assert not _RESPONSE_SCHEMA.is_valid(value)
    with pytest.raises(BattedHitProtocolError):
        decode_batted_hit_response(json.dumps(value))


@pytest.mark.parametrize(
    "raw",
    (
        '{"ok":false,"error":{"code":"INVALID_JSON","code":"INVALID_JSON"}}',
        '{"ok":false,"error":{"code":NaN}}',
        '{"ok":false,"error":{"code":"OTHER"}}',
    ),
)
def test_duplicate_nonfinite_and_unknown_error_are_closed(raw) -> None:
    """重複/非有限値/未知codeをdecoderで拒否する。"""
    with pytest.raises(BattedHitProtocolError):
        decode_batted_hit_response(raw)


def test_rebuild_produces_identical_single_artifact_bytes(tmp_path) -> None:
    """同sourceの独立buildも製品の唯一artifactと全byte一致する。"""
    script = (
        "import {buildDomain} from './scripts/domain-build/build.mjs';"
        " await buildDomain({outputDirectory:process.argv[1]});"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(tmp_path)],
        cwd=_ROOT / "frontend",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "pitchlog-domain.js").read_bytes() == _ARTIFACT.read_bytes()
    assert (tmp_path / "pitchlog-domain.json").read_bytes() == _DECLARATION.read_bytes()


@pytest.mark.parametrize("case", _VECTORS["cases"], ids=lambda c: c["caseId"])
def test_all_real_head_and_value_flag_replays_are_rejected(case, actual_host) -> None:
    """実hostの成功後に各23flagをhead/valueで個別破壊し型とschemaで拒否する。"""
    raw = actual_host.call("deriveBattedHit", json.dumps(case["request"]))
    actual = json.loads(raw)
    assert actual == case["expected"]
    for location in ("head", "value"):
        for key in actual["value"]["statFlags"]:
            broken = copy.deepcopy(actual)
            target = broken["value"]["statFlags"]
            if location == "head":
                target = broken["value"]["historyContext"][0]["difference"]["statFlags"]
            target[key] = not target[key]
            assert not _RESPONSE_SCHEMA.is_valid(broken), (location, key)
            with pytest.raises(BattedHitProtocolError):
                decode_batted_hit_response(json.dumps(broken))
