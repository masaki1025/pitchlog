"""座標計算 manifest と独立カタログの閉登録を検査する。"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from pitchlog.domaincheck.cli import CheckerViolation, validate_asset

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> dict:
    """登録ファイルの JSON を読む。"""
    return json.loads((ROOT / path).read_text())


def test_manifest_conforms_to_existing_schema_and_real_paths() -> None:
    """既schemaへ登録し、SHAと契約の計算識別を照合する。"""
    schema = _read("backend/domain/manifest.schema.json")
    manifest = _read("backend/domain/manifest.json")
    validate_asset(manifest, schema)
    catalog = manifest["propertyCatalog"]
    validate_asset(_read(catalog["path"]), _read(catalog["schema"]))
    calculation = manifest["calculations"][0]
    assert calculation["calculation"] == "course-input-quantization"
    assert len(calculation["vectors"]) == 1
    contract = _read(calculation["vectors"][0]["path"])
    assert contract["calculation"] == calculation["calculation"]
    expected_schema = {
        "$schema": schema["$schema"],
        "$ref": calculation["vectors"][0]["expectedValueSchema"],
        "$defs": schema["$defs"],
    }
    for case in contract["cases"]:
        projected = {
            "expected": case["expected"],
            "comparison": "exact",
            "provenance": "付録A-1 座標の丸め",
        }
        validate_asset(projected, expected_schema)
        assert projected["expected"] is case["expected"]
    assert calculation["comparison"] == {"mode": "lossless"}
    assert calculation["normalization"] == []
    artifact = ROOT / calculation["generated"][0]["path"]
    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert calculation["directTargets"][0]["hash"] == "sha256:" + actual
    assert _read("frontend/public/domain/pitchlog-domain.json")["sha256"] == actual
    registered = {
        (p["propertyId"], p["propertyKind"]) for p in calculation["properties"]
    }
    declared = {
        (p["propertyId"], p["propertyKind"])
        for p in _read(catalog["path"])["predicates"]
    }
    assert registered == declared
    for row in calculation["entrypoints"]:
        assert (ROOT / row["module"]).is_file()
        assert (ROOT / row["adapter"]).is_file()


@pytest.mark.parametrize(
    "missing", ["propertyCatalog", "calculations", "displayBindings"]
)
def test_manifest_missing_top_level_is_rejected(missing: str) -> None:
    """簡略化による必須宣言の欠落を拒否する。"""
    manifest = copy.deepcopy(_read("backend/domain/manifest.json"))
    del manifest[missing]
    with pytest.raises(CheckerViolation):
        validate_asset(manifest, _read("backend/domain/manifest.schema.json"))


def test_undeclared_calculation_field_is_rejected() -> None:
    """manifestに任意の抜け道を足せない。"""
    manifest = copy.deepcopy(_read("backend/domain/manifest.json"))
    manifest["calculations"][0]["skipValidation"] = True
    with pytest.raises(CheckerViolation):
        validate_asset(manifest, _read("backend/domain/manifest.schema.json"))


@pytest.mark.parametrize(
    "invalid",
    [
        {"ok": True, "value": {"unit": "1/263", "x": "0", "y": "263"}},
        {"expected": {}, "comparison": "exact"},
        {"expected": {}, "comparison": "partial", "provenance": "付録A-1 座標の丸め"},
        {
            "expected": {},
            "comparison": "exact",
            "provenance": "付録A-1 座標の丸め",
            "ignoreFields": [],
        },
    ],
)
def test_expected_value_projection_cannot_omit_metadata_or_weaken_comparison(
    invalid: dict,
) -> None:
    """生の成功封筒・不足メタデータ・部分比較・余剰指定を受け入れない。"""
    schema = _read("backend/domain/manifest.schema.json")
    with pytest.raises(CheckerViolation):
        validate_asset(
            invalid,
            {
                "$schema": schema["$schema"],
                "$ref": "#/$defs/ExpectedValue",
                "$defs": schema["$defs"],
            },
        )
