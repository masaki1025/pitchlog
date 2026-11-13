"""妨害後継artifactからv8へ連なる有限53応答と8組だけのv3互換を確認する。"""

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
OLD = "bb6768eae395bda43e13a1b97e8b6da0f2ab2b66a78a460590c0a8fd1151daa1"
CURRENT = "961844ed9d013afc4d72945e73d07bc7e1b3fb7680edad20a5a8568c599dad70"


def _raw(value):
    """固定の整形JSON byteを作る。"""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _inputs():
    """新2原本と変更しない直前v6原本を読む。"""
    return (
        json.loads((BASE / "nonplay_v3_compatibility_witness_v8.json").read_bytes()),
        json.loads((BASE / "play_prefix_v3_source_compatibility_v8.json").read_bytes()),
        (BASE / "nonplay_v3_compatibility_witness_v7.json").read_bytes(),
    )


def _reseal(data, registry):
    """改竄後も表面的hashを追随させて実検査を試す。"""
    data["samplesSha256"] = hashlib.sha256(
        json.dumps(
            data["samples"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    witness_sha = hashlib.sha256(_raw(data)).hexdigest()
    registry["currentWitnessSha256"] = witness_sha
    for row in registry["cases"]:
        row["witnessSha256"] = witness_sha


def test_actual_53_full_responses_match_inherited_expected_values():
    """新hostの実全応答と旧期待由来の値を比較し、数学期待を採取しない。"""
    data, registry, previous = _inputs()
    reader._validated_v3_witness_v8(_raw(data), _raw(registry), previous, CURRENT)
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
        "actual",
        "bool-int",
        "extra-sample",
        "pair",
        "operation",
        "order",
        "scope",
        "normalization",
    ],
)
def test_resealed_v8_rejects_math_and_scope_changes(fault):
    """hash再封印だけで旧/新数学、型、許可範囲の変更を資格化しない。"""
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
    elif fault == "actual":
        sample["currentActual"]["ok"] = False
    elif fault == "bool-int":
        sample["currentExpected"]["ok"] = 1
        sample["currentActual"] = copy.deepcopy(sample["currentExpected"])
    elif fault == "extra-sample":
        data["samples"].append(copy.deepcopy(sample))
    elif fault == "pair":
        registry["cases"][0]["priorArtifactSha256"] = "0" * 64
    elif fault == "operation":
        registry["cases"][0]["compatibleOperations"].append("applyUndo")
    elif fault == "order":
        data["samples"][0], data["samples"][1] = data["samples"][1], data["samples"][0]
    elif fault == "scope":
        data["scope"]["HTTPorDB"] = True
    else:
        data["normalization"]["responsePointers"].append("/value/t1/statFlags")
    _reseal(data, registry)
    with pytest.raises(ValueError):
        reader._validated_v3_witness_v8(_raw(data), _raw(registry), previous, CURRENT)


def test_real_gate_accepts_only_eight_fixed_pairs():
    """新実入口は旧6 priorと新自己だけを認め、未知/旧executionを閉じる。"""
    _, registry, _ = _inputs()
    assert len(registry["cases"]) == 8
    assert registry["cases"][-2]["priorArtifactSha256"] == OLD
    assert registry["cases"][-1]["priorArtifactSha256"] == CURRENT
    for row in registry["cases"]:
        reader._require_legacy_compatibility(
            row["priorArtifactSha256"], CURRENT, source_format="play-prefix-play-v3"
        )
    for prior, execution in (
        ("0" * 64, CURRENT),
        (CURRENT, "0" * 64),
        (registry["cases"][1]["priorArtifactSha256"], OLD),
    ):
        with pytest.raises(OrdinaryPrefixError):
            reader._require_legacy_compatibility(
                prior, execution, source_format="play-prefix-play-v3"
            )


@pytest.mark.parametrize(
    "name",
    [
        "nonplay_v3_compatibility_witness_v1.json",
        "nonplay_v3_compatibility_witness_v2.json",
        "nonplay_v3_compatibility_witness_v3.json",
        "nonplay_v3_compatibility_witness_v4.json",
        "nonplay_v3_compatibility_witness_v5.json",
        "nonplay_v3_compatibility_witness_v6.json",
        "nonplay_v3_compatibility_witness_v7.json",
        "play_prefix_v3_source_compatibility_v2.json",
        "play_prefix_v3_source_compatibility_v3.json",
        "play_prefix_v3_source_compatibility_v4.json",
        "play_prefix_v3_source_compatibility_v5.json",
        "play_prefix_v3_source_compatibility_v6.json",
        "play_prefix_v3_source_compatibility_v7.json",
    ],
)
def test_historical_chain_byte_change_rejected(tmp_path, name):
    """過去どの世代の原本変更も現在の資格を失わせる。"""
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
