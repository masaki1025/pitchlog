"""共有schemaのmeta・有限intake・公式観測を同じ明示入力で照合する。"""

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
NAMES = (
    "lineup_play_prefix_schema_v1.json",
    "lineup_play_prefix_payload_schema_v1.json",
)
CASES = json.loads(
    (ROOT / "backend/tests/fixtures/batted_operations_schema_cases_v1.json").read_text()
)


def definition(document, name):
    """外部参照を代替せず、当該閉定義の実構造だけを検査する。"""
    return Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": document["$defs"]})


@pytest.mark.parametrize("name", NAMES)
def test_meta_and_old_response_variants_remain_exact(name):
    """新応答variantを足さず、既Legacy/Runnerの排他2形を保持する。"""
    document = json.loads((ROOT / "contracts/state-transition" / name).read_text())
    Draft202012Validator.check_schema(document)
    previous = json.loads(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                "c6718e32:contracts/state-transition/" + name,
            ]
        )
    )
    for key in (
        "Value",
        "LegacyValue",
        "RunnerValue",
        "Success",
        "RunnerScoreEffect",
        "T1PerPitchPayloadV2",
    ):
        assert document["$defs"][key] == previous["$defs"][key]


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["id"])
def test_finite_input_and_official_observation_shape(case):
    """旧安打・明示同塁・犠打犠飛・DPと不正入力を両schemaで一致させる。"""
    for name in NAMES:
        document = json.loads((ROOT / "contracts/state-transition" / name).read_text())
        assert (
            definition(document, "BattedHitT1Input").is_valid(case["t1"])
            is case["t1Valid"]
        )
        if name.endswith("payload_schema_v1.json"):
            assert (
                definition(document, "BattedHitObservations").is_valid(
                    case["observations"]
                )
                is case["observationsValid"]
            )


def actual_batted_payload(row, host):
    """新実hostの真応答を封印し、schemaと既codecへ渡す。資格は作らない。"""
    from referencing import Registry, Resource
    from test_batted_hit_prefix_payload import observations

    from pitchlog.domainrt.host import NodeDomainHost
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixSuccess,
        decode_lineup_prefix_request,
        decode_lineup_prefix_response,
        lineup_wire_head,
        seal_lineup_wire,
    )
    from pitchlog.sync.terminal_pitch_payload import (
        BattedHitPlayObservations,
        LineupPitchCalculation,
        format_batted_hit_prefix_payload,
        read_lineup_pitch_payload,
    )

    samples = json.loads(
        (
            ROOT
            / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
        ).read_text()
    )
    document = json.loads((ROOT / "contracts/state-transition" / NAMES[0]).read_text())
    payload_schema = json.loads(
        (ROOT / "contracts/state-transition" / NAMES[1]).read_text()
    )
    registry = Registry().with_resource(
        document["$id"], Resource.from_contents(document)
    )
    full = Draft202012Validator(payload_schema, registry=registry)
    if type(host) is not NodeDomainHost:
        raise TypeError("実NodeDomainHostが必要")
    assert host.artifact_sha256 == samples["artifactSha256"]
    request = decode_lineup_prefix_request(json.dumps(row["request"]))
    response = decode_lineup_prefix_response(
        host.call(
            "deriveLineupPlayPrefixWithContinuation",
            request.model_dump_json(by_alias=True, exclude_unset=True),
        )
    )
    assert type(response) is LineupPrefixSuccess
    request, response = seal_lineup_wire(request, response)
    head = lineup_wire_head(request, response)
    for schema in [document, payload_schema]:
        definition(schema, "WireHead").validate(head)
        if "rbiRulingByRunner" in head:
            for key in ["rbiRulingByRunner", "runnerScoreEffects"]:
                bad = {k: v for k, v in head.items() if k != key}
                assert not definition(schema, "WireHead").is_valid(bad)
            assert not definition(schema, "WireHead").is_valid(
                {**head, "rbiRulingByRunner": {}}
            )
    q = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    observed = observations({"request": q})
    t = q["t1"]
    if t["runnerAdvanceOverrides"] != "not-applied":
        observed["runnerAdvanceOverridesByRunner"] = t["runnerAdvanceOverrides"]
    for key in ["rbiRulingByRunner", "outRunner"]:
        if key in t:
            observed[key] = t[key]
    if t["officialScoringPayload"] == "error-recorded":
        observed["officialScoringPayload"] = {
            "kind": "error-recorded",
            "errors": [
                {
                    "fielder": {
                        "kind": "official",
                        "player_id": q["source"]["participants"]["pitcherId"],
                    },
                    "count": 1,
                }
            ],
        }
    calc = LineupPitchCalculation.model_validate_json(
        json.dumps(
            {
                "formatVersion": "play-prefix-calculation-v3",
                "artifactSha256": host.artifact_sha256,
                "request": q,
                "response": response.model_dump(
                    mode="json", by_alias=True, exclude_unset=True
                ),
            }
        )
    )
    typed = BattedHitPlayObservations.model_validate_json(json.dumps(observed))
    v7, v8 = format_batted_hit_prefix_payload(typed, calc)
    decoded = read_lineup_pitch_payload(
        v7, v8, expected_calculation=calc, require_current_rbi=True
    )
    assert decoded.observations == typed
    full.validate(json.loads(v7))

    return decoded


@pytest.mark.parametrize(
    "row",
    json.loads(
        (
            ROOT
            / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
        ).read_text()
    )["samples"],
    ids=lambda row: row["operation"],
)
def test_actual_host_seal_v7_v8_and_paired_wire_head(row):
    """再利用helperでも全schema/head/公式codec照合を省かない。"""
    from pitchlog.domainrt.host import open_domain_host

    with open_domain_host() as host:
        actual_batted_payload(row, host)


@pytest.mark.parametrize(
    "fault",
    [
        "run",
        "rbi",
        "allowed",
        "numeric-false",
        "score",
        "family",
        "overrides",
        "extra-effect",
        "forged-rbi",
    ],
)
def test_no_run_head_never_promotes_unknown_or_scoring_context(fault):
    """空effectだけで成功せず、元の有限入力/実flags/scoreも照合する。"""
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import (
        LineupPrefixProtocolError,
        LineupPrefixSuccess,
        decode_lineup_prefix_request,
        decode_lineup_prefix_response,
        lineup_wire_head,
    )

    source = json.loads(
        (
            ROOT
            / "backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json"
        ).read_text()
    )["samples"]
    row = next(r for r in source if r["operation"] == "batted-out")
    with open_domain_host() as host:
        q = decode_lineup_prefix_request(json.dumps(row["request"]))
        r = decode_lineup_prefix_response(
            host.call(
                "deriveLineupPlayPrefixWithContinuation",
                q.model_dump_json(by_alias=True, exclude_unset=True),
            )
        )
        assert type(r) is LineupPrefixSuccess
        assert lineup_wire_head(q, r)["runnerScoreEffects"] == []
        value = r.value
        if fault in ["run", "rbi", "allowed", "numeric-false"]:
            field = {
                "run": "run",
                "rbi": "rbi",
                "allowed": "run_allowed",
                "numeric-false": "run",
            }[fault]
            flags = value.t1.stat_flags.model_copy(
                update={field: 0 if fault == "numeric-false" else True}
            )
            r = r.model_copy(
                update={
                    "value": value.model_copy(
                        update={"t1": value.t1.model_copy(update={"stat_flags": flags})}
                    )
                }
            )
        elif fault == "score":
            state = value.t1.after.state_fields
            after = value.t1.after.model_copy(
                update={
                    "state_fields": state.model_copy(
                        update={"score": state.score.model_copy(update={"away": "999"})}
                    )
                }
            )
            r = r.model_copy(
                update={
                    "value": value.model_copy(
                        update={"t1": value.t1.model_copy(update={"after": after})}
                    )
                }
            )
        elif fault in ["family", "overrides", "forged-rbi"]:
            update = (
                {"result_id": "batting-result.single"}
                if fault == "family"
                else {"runner_advance_overrides": "not-applied"}
                if fault == "overrides"
                else {"rbi_ruling_by_runner": {"1": "ordinary-play"}}
            )
            q = q.model_copy(update={"t1": q.t1.model_copy(update=update)})
        else:
            scoring = next(r for r in source if r["operation"] == "sacrifice-fly")
            actual = decode_lineup_prefix_response(
                host.call(
                    "deriveLineupPlayPrefixWithContinuation",
                    json.dumps(scoring["request"]),
                )
            )
            assert type(actual) is LineupPrefixSuccess
            from pitchlog.domainrt.lineup_play_prefix_continuation import RunnerValue

            assert type(actual.value) is RunnerValue
            r = r.model_copy(
                update={
                    "value": value.model_copy(
                        update={
                            "runner_score_effects": actual.value.runner_score_effects
                        }
                    )
                }
            )
        with pytest.raises(LineupPrefixProtocolError):
            lineup_wire_head(q, r)
