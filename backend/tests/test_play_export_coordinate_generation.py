"""付録B-7の静的値を有限宣言から生成したPython座標targetへ照合する。"""

import copy
import json
import types
from pathlib import Path

import pytest

from pitchlog.domaingen.core import _canonical_hash
from pitchlog.domaingen.export_coordinate import (
    ExportCoordinateDeclarationError,
    _generate_course_export_targets,
    generate_course_export_bundle,
)

_ROOT = Path(__file__).resolve().parents[2]


def _model():
    """T5から独立した人手表示宣言を読む。"""
    return json.loads(
        (_ROOT / "backend/domain/play-export-display.model.json").read_text()
    )


def _geometry():
    """既表示座標契約を読む。"""
    return json.loads((_ROOT / "contracts/display_geometry_263_v1.json").read_text())


def _generated_python():
    """targetを実宣言から生成し、固定期待値は生成しない。"""
    bundle, _ = generate_course_export_bundle()
    module = types.ModuleType("coordinate_export_test")
    exec(
        bundle["backend/src/pitchlog/exports/generated/coordinate_transform.py"],
        module.__dict__,
    )
    return module


@pytest.mark.parametrize(
    "saved,expected",
    [
        (("0", "0", "1/263"), ("0", "263")),
        (("132", "66", "1/263"), ("132", "197")),
        (("263", "263", "1/263"), ("263", "0")),
        ((None, None, None), (None, None)),
    ],
)
def test_b7_static_screen_values(saved, expected) -> None:
    """正準保存k/263の静的端点・本文例・両欠測を照合する。"""
    module = _generated_python()
    assert module.course_screen(*saved) == expected
    assert module.SOURCE_MODEL_HASH == _canonical_hash(_model())


@pytest.mark.parametrize(
    "saved",
    [
        ("-1", "0", "1/263"),
        ("264", "0", "1/263"),
        ("00", "0", "1/263"),
        ("1.0", "0", "1/263"),
        ("1", None, "1/263"),
        ("1", "1", "1/262"),
        (True, "1", "1/263"),
    ],
)
def test_b7_malformed_or_unknown_source_is_rejected(saved) -> None:
    """浮動小数・非正準・片軸欠測を現値へ丸めない。"""
    with pytest.raises(ValueError):
        _generated_python().course_screen(*saved)


@pytest.mark.parametrize(
    "mutation", ["kind", "unit", "size", "extra", "root", "schema", "axis"]
)
def test_export_transform_is_closed(mutation: str) -> None:
    """未知式・単位・サイズ・追加変換を生成前に拒否する。"""
    changed = copy.deepcopy(_model())
    transform = changed["exportTransforms"][0]
    if mutation == "kind":
        transform["kind"] = "free-eval"
    elif mutation == "unit":
        transform["sourceUnit"] = "1/262"
    elif mutation == "size":
        transform["size"] = 262
    elif mutation == "extra":
        changed["exportTransforms"].append(copy.deepcopy(transform))
    elif mutation == "root":
        changed["unknown"] = "new operation"
    elif mutation == "schema":
        changed["schemaVersion"] = 2
    else:
        transform["axes"]["x"] = "complement"
    with pytest.raises(ExportCoordinateDeclarationError):
        _generate_course_export_targets(changed, _canonical_hash(changed), _geometry())


def test_b7_generated_bundle_matches_checked_in_targets():
    """別D-1モデルからの二生成物とmanifestを全byte検査する。"""
    bundle, manifest = generate_course_export_bundle()
    assert len(bundle) == 2
    for path, content in bundle.items():
        assert (_ROOT / path).read_text() == content
    assert manifest == json.loads(
        (_ROOT / "backend/domain/play-export-display.manifest.json").read_text()
    )
    assert (
        "contracts/display-geometry/coordinate_transform_contract_v1.json"
        not in manifest["inputs"]
    )


def test_b7_all_sixteen_independent_canonical_vectors():
    """既規範42例のうち正準保存→画面16例を全値で照合する。"""
    cases = json.loads(
        (
            _ROOT / "contracts/display-geometry/coordinate_transform_contract_v1.json"
        ).read_text()
    )["cases"]
    canonical = [
        case
        for case in cases
        if case["input"]["coordinateSystem"] == "normalized-bottom-left-units-1-263"
    ]
    assert len(cases) == 42
    assert len(canonical) == 16
    generated = _generated_python()
    for case in canonical:
        source = case["input"]["coordinate"]
        expected = case["expected"]["coordinate"]
        assert generated.course_screen(str(source["x"]), str(source["y"]), "1/263") == (
            str(expected["x"]),
            str(expected["y"]),
        ), case["caseId"]


def test_b7_model_does_not_change_t5_model_or_profile():
    """旧v3 T5 hashとprofileをB-7表示宣言へ巻き込まない。"""
    manifest = json.loads((_ROOT / "backend/domain/stats-manifest.json").read_text())
    assert (
        _canonical_hash(
            json.loads((_ROOT / "backend/domain/play-export.model.json").read_text())
        )
        == manifest["commonModelHash"]
    )
    assert (
        manifest["nativeEvaluationProfiles"]["v3"]["model_sha256"]
        == manifest["commonModelHash"]
    )
