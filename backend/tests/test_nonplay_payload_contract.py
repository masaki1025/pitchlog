"""新inner closedprofileのcanonical JSONSchema/Pydantic同原wire対向。"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from test_nonplay_normal_payload import fixture_values

from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload

ROOT = Path(__file__).resolve().parents[2]


def validator():
    """ローカル正式schemaだけを登録しnetwork fallbackを使わない。"""
    registry = Registry()
    for p in (ROOT / "contracts/state-transition").glob("*schema*.json"):
        value = json.loads(p.read_text())
        resource = Resource.from_contents(value, default_specification=DRAFT202012)
        registry = registry.with_resource(
            "https://pitchlog.local/contracts/" + p.name, resource
        )
        if "$id" in value:
            registry = registry.with_resource(value["$id"], resource)
    schema = json.loads(
        (
            ROOT
            / "contracts/state-transition/lineup_play_prefix_payload_schema_v1.json"
        ).read_text()
    )
    return Draft202012Validator(schema, registry=registry)


def test_same_native_wire_is_valid_in_both_closed_consumers():
    """JSONを旧形式へ書換えず二consumerが同値を受理する。"""
    v7, _ = fixture_values()
    validator().validate(v7)
    assert (
        LineupPitchPlayPayload.model_validate_json(json.dumps(v7)).model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        == v7
    )


@pytest.mark.parametrize(
    "kind",
    [
        "profile",
        "extra",
        "source-kind",
        "d3-number",
        "flag-number",
        "result",
        "tag",
        "eos",
    ],
)
def test_closed_schema_and_model_reject_same_mutants(kind):
    """未知枝/型/指紋EOSを同じ原JSONのまま拒否する。"""
    v7, _ = fixture_values()
    q = v7["calculation"]["request"]
    if kind == "profile":
        v7["calculation"]["formatVersion"] = "unknown"
    elif kind == "extra":
        v7["calculation"]["secret"] = False
    elif kind == "source-kind":
        q["source"]["formatVersion"] = "play-prefix-source-v3"
    elif kind == "d3-number":
        q["source"]["checkpoint"]["content"]["d3"] = 4
    elif kind == "flag-number":
        flags = v7["calculation"]["response"]["value"]["t1"]["statFlags"]
        key = next(iter(flags))
        flags[key] = int(flags[key])
    elif kind == "result":
        q["t1"]["resultId"] = "batting-result.single"
    else:
        src = q["source"]["checkpoint"]["content"]["d1Head"]["source"]
        src["fingerprint"] = ("other:" + "a" * 64) if kind == "tag" else "a" * 64 + "\n"
    assert not validator().is_valid(v7)
    with pytest.raises(ValueError):
        LineupPitchPlayPayload.model_validate_json(json.dumps(v7))
