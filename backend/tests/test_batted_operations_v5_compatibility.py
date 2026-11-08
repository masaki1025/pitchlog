"""打球群追加後の有限v3互換を数学全値と改変対向で検査する。"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.host import open_domain_host
from pitchlog.repositories import play_prefix as reader
from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "contracts/state-transition"
CURRENT = "71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff"


def _raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _inputs():
    return (
        json.loads((BASE / "nonplay_v3_compatibility_witness_v5.json").read_bytes()),
        json.loads((BASE / "play_prefix_v3_source_compatibility_v5.json").read_bytes()),
        (BASE / "nonplay_v3_compatibility_witness_v4.json").read_bytes(),
    )


def _reseal(data, registry):
    data["samplesSha256"] = hashlib.sha256(
        json.dumps(
            data["samples"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    digest = hashlib.sha256(_raw(data)).hexdigest()
    registry["currentWitnessSha256"] = digest
    for row in registry["cases"]:
        row["witnessSha256"] = digest


def test_actual_53_full_responses_match_inherited_expected_values():
    """新hostの実全応答を旧期待由来の全型値へ照合し、期待を生成しない。"""
    data, registry, previous = _inputs()
    reader._validated_v3_witness_v5(_raw(data), _raw(registry), previous, CURRENT)
    with open_domain_host() as host:
        assert host.artifact_sha256 == CURRENT
        for sample in data["samples"]:
            actual = json.loads(
                host.call(
                    "deriveLineupPlayPrefixWithContinuation",
                    json.dumps(sample["currentRequest"]),
                )
            )
            assert reader._canonical_json(actual) == reader._canonical_json(
                sample["currentExpected"]
            ), sample["caseId"]
            assert reader._canonical_json(actual) == reader._canonical_json(
                sample["currentActual"]
            ), sample["caseId"]


@pytest.mark.parametrize(
    "fault",
    [
        "prior-math",
        "current-math",
        "bool-int",
        "actual",
        "extra-sample",
        "pair",
        "operation",
        "order",
        "scope",
    ],
)
def test_followed_hashes_do_not_qualify_changed_math_or_scope(fault):
    """witnessとregistryのhashを追随しても旧数学/型/範囲の変更を拒否する。"""
    data, registry, previous = _inputs()
    sample = data["samples"][0]
    if fault == "prior-math":
        sample["priorExpected"]["value"]["t1"]["after"]["stateFields"]["state.outs"] = (
            "99"
        )
    elif fault == "current-math":
        sample["currentExpected"]["value"]["t1"]["after"]["stateFields"][
            "state.outs"
        ] = "99"
        sample["currentActual"] = copy.deepcopy(sample["currentExpected"])
    elif fault == "bool-int":
        sample["currentExpected"]["ok"] = 1
        sample["currentActual"] = copy.deepcopy(sample["currentExpected"])
    elif fault == "actual":
        sample["currentActual"]["ok"] = False
    elif fault == "extra-sample":
        data["samples"].append(copy.deepcopy(sample))
    elif fault == "pair":
        registry["cases"][0]["priorArtifactSha256"] = "0" * 64
    elif fault == "operation":
        registry["cases"][0]["compatibleOperations"].append("applyUndo")
    elif fault == "order":
        data["samples"][0], data["samples"][1] = data["samples"][1], data["samples"][0]
    else:
        data["scope"]["HTTPorDB"] = True
    _reseal(data, registry)
    with pytest.raises(ValueError):
        reader._validated_v3_witness_v5(_raw(data), _raw(registry), previous, CURRENT)


def test_real_gate_accepts_only_five_fixed_pairs():
    """正規登録を含む実入口で有限5組以外を補修しない。"""
    _, registry, _ = _inputs()
    assert len(registry["cases"]) == 5
    for row in registry["cases"]:
        reader._require_legacy_compatibility(
            row["priorArtifactSha256"], CURRENT, source_format="play-prefix-play-v3"
        )
    for prior, execution in [
        ("0" * 64, CURRENT),
        (CURRENT, "0" * 64),
        (
            registry["cases"][1]["priorArtifactSha256"],
            registry["cases"][1]["priorArtifactSha256"],
        ),
    ]:
        with pytest.raises(OrdinaryPrefixError):
            reader._require_legacy_compatibility(
                prior, execution, source_format="play-prefix-play-v3"
            )


def test_legacy_registry_raw_change_is_rejected_before_qualification(tmp_path):
    """旧registryがJSONとして読めても原本byteの変更を資格化しない。"""
    import shutil

    for name in (
        "play_prefix_v2_source_compatibility_v1.json",
        "nonplay_v3_compatibility_witness_v1.json",
        "nonplay_v3_compatibility_witness_v2.json",
        "play_prefix_v3_source_compatibility_v2.json",
        "batted_current_identity_witness_v1.json",
        "nonplay_v3_compatibility_witness_v3.json",
        "play_prefix_v3_source_compatibility_v3.json",
        "nonplay_v3_compatibility_witness_v4.json",
        "play_prefix_v3_source_compatibility_v4.json",
        "nonplay_v3_compatibility_witness_v5.json",
        "play_prefix_v3_source_compatibility_v5.json",
    ):
        destination = tmp_path / "contracts/state-transition" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / name, destination)
    for name in ("pitchlog-domain.js", "pitchlog-domain.json"):
        destination = tmp_path / "frontend/public/domain" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "frontend/public/domain" / name, destination)
    reader._require_v3_compatibility(tmp_path, CURRENT, CURRENT)
    registry = (
        tmp_path
        / "contracts/state-transition/play_prefix_v2_source_compatibility_v1.json"
    )
    registry.write_bytes(registry.read_bytes() + b" ")
    with pytest.raises(ValueError):
        reader._require_v3_compatibility(tmp_path, CURRENT, CURRENT)


@pytest.mark.parametrize(
    "name",
    [
        "nonplay_v3_compatibility_witness_v1.json",
        "nonplay_v3_compatibility_witness_v2.json",
        "nonplay_v3_compatibility_witness_v3.json",
        "nonplay_v3_compatibility_witness_v4.json",
        "play_prefix_v3_source_compatibility_v2.json",
        "play_prefix_v3_source_compatibility_v3.json",
        "play_prefix_v3_source_compatibility_v4.json",
    ],
)
def test_all_historical_chain_bytes_remain_mandatory(tmp_path, name):
    """過去どの段の原本byteを変えても新現行互換へ進めない。"""
    import shutil

    source = tmp_path / "contracts/state-transition"
    source.mkdir(parents=True)
    for original in BASE.glob("*compatibility*.json"):
        shutil.copyfile(original, source / original.name)
    shutil.copyfile(
        BASE / "batted_current_identity_witness_v1.json",
        source / "batted_current_identity_witness_v1.json",
    )
    target = tmp_path / "frontend/public/domain"
    target.mkdir(parents=True)
    for artifact in ("pitchlog-domain.js", "pitchlog-domain.json"):
        shutil.copyfile(ROOT / "frontend/public/domain" / artifact, target / artifact)
    reader._require_v3_compatibility(tmp_path, CURRENT, CURRENT)
    bad = source / name
    bad.write_bytes(bad.read_bytes() + b" ")
    with pytest.raises(ValueError):
        reader._require_v3_compatibility(tmp_path, CURRENT, CURRENT)


@pytest.mark.parametrize(
    "fault",
    [
        "registry-order",
        "duplicate-pair",
        "missing-pair",
        "rbi",
        "out3",
        "responsibility",
        "normalization",
    ],
)
def test_resealed_v5_still_rejects_mathematical_and_registry_changes(fault):
    """hashを追随してもRBI/OUT3/責任/許可pair集合を緩めない。"""
    data, registry, previous = _inputs()
    if fault == "registry-order":
        registry["cases"][0], registry["cases"][1] = (
            registry["cases"][1],
            registry["cases"][0],
        )
    elif fault == "duplicate-pair":
        registry["cases"][-1] = copy.deepcopy(registry["cases"][0])
    elif fault == "missing-pair":
        registry["cases"].pop()
    elif fault == "normalization":
        data["normalization"]["responsePointers"].append("/value/t1/statFlags")
    else:
        sample = data["samples"][0]
        value = sample["currentExpected"]["value"]
        if fault == "rbi":
            value["t1"]["statFlags"]["打点"] = not value["t1"]["statFlags"]["打点"]
        elif fault == "out3":
            value["t1"]["outEffect"]["count"] = "3"
        else:
            value["nextResponsibility"]["paStartSource"]["id"] = (
                "00000000-0000-0000-0000-000000009999"
            )
        sample["currentActual"] = copy.deepcopy(sample["currentExpected"])
    _reseal(data, registry)
    with pytest.raises(ValueError):
        reader._validated_v3_witness_v5(_raw(data), _raw(registry), previous, CURRENT)
