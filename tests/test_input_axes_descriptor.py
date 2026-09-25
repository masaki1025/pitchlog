"""入力軸descriptorの構造とdigest規則を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_module("check_input_axes_descriptor_under_test", SCRIPT)
DESCRIPTOR_PATH = REPOSITORY_ROOT / checker.DESCRIPTOR_PATH
SCHEMA_PATH = REPOSITORY_ROOT / checker.SCHEMA_PATH


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _descriptor() -> dict[str, Any]:
    """リポジトリのdescriptorを読む。"""
    return _load_object(DESCRIPTOR_PATH)


def _schema() -> dict[str, Any]:
    """リポジトリのdescriptor schemaを読む。"""
    return _load_object(SCHEMA_PATH)


def _with_digest(descriptor: dict[str, Any]) -> dict[str, Any]:
    """descriptorへ現在内容のdigestを設定して返す。"""
    descriptor["digest"] = checker.compute_descriptor_digest(descriptor)
    return descriptor


def test_repository_descriptor_passes_schema_and_digest_validation() -> None:
    """リポジトリ実物が閉じたschemaとdigest検査を通る。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "input-axes-descriptor: OK\n"
    assert result.stderr == ""


def test_schema_defines_the_complete_top_level_and_closed_axis_enum() -> None:
    """schemaが全トップレベル列と3分類の閉じた集合を定める。"""
    schema = _schema()
    descriptor = _descriptor()

    assert schema["version"] == checker.SCHEMA_PATH.stem
    assert descriptor["version"] == checker.DESCRIPTOR_PATH.stem
    assert set(schema["required"]) == checker.EXPECTED_TOP_LEVEL_FIELDS
    assert set(schema["properties"]) == checker.EXPECTED_TOP_LEVEL_FIELDS
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["axisClassification"]["enum"] == [
        "finite-enumerable",
        "boundary-partition",
        "non-finite",
    ]


def test_digest_is_reproducible_and_independent_of_object_key_order() -> None:
    """同じJSON値はobjectの記述順に依存せず同じdigestになる。"""
    descriptor = _descriptor()
    reordered = dict(reversed(tuple(descriptor.items())))

    first = checker.compute_descriptor_digest(descriptor)
    second = checker.compute_descriptor_digest(descriptor)
    reordered_digest = checker.compute_descriptor_digest(reordered)

    assert first == descriptor["digest"]
    assert second == first
    assert reordered_digest == first


@pytest.mark.parametrize(
    ("axis", "classification"),
    [
        (
            {
                "axisId": "schema.finiteProbe",
                "sourceClauseId": "D-11",
                "classification": "finite-enumerable",
                "values": [False, True],
            },
            "finite-enumerable",
        ),
        (
            {
                "axisId": "schema.boundaryProbe",
                "sourceClauseId": "D-11",
                "classification": "boundary-partition",
                "boundaryValues": [0, 1, "D"],
            },
            "boundary-partition",
        ),
        (
            {
                "axisId": "schema.nonFiniteProbe",
                "sourceClauseId": "FR-006",
                "classification": "non-finite",
                "nonFiniteReason": "実行時の履歴深さに上限を置かないため",
            },
            "non-finite",
        ),
    ],
)
def test_each_closed_axis_shape_is_accepted(
    axis: dict[str, Any], classification: str
) -> None:
    """3分類の各軸が対応する値域表現だけを持てる。"""
    descriptor = _descriptor()
    descriptor["stateTransitionAxes"] = [axis]
    _with_digest(descriptor)

    checker.validate_descriptor_document(descriptor, _schema())

    assert descriptor["stateTransitionAxes"][0]["classification"] == classification


def test_changing_only_source_clause_id_changes_digest_and_is_red() -> None:
    """由来条文IDだけの差し替えを保存済みdigestとの不一致で拒否する。"""
    descriptor = _descriptor()
    descriptor["stateTransitionAxes"] = [
        {
            "axisId": "digest.sourceClauseProbe",
            "sourceClauseId": "FR-009",
            "classification": "finite-enumerable",
            "values": ["D"],
        }
    ]
    _with_digest(descriptor)
    baseline_digest = descriptor["digest"]
    checker.validate_descriptor_document(descriptor, _schema())

    changed = copy.deepcopy(descriptor)
    changed["stateTransitionAxes"][0]["sourceClauseId"] = "FR-010"
    changed_digest = checker.compute_descriptor_digest(changed)

    assert changed_digest != baseline_digest
    with pytest.raises(checker.DescriptorCheckError, match="digest不一致"):
        checker.validate_descriptor_document(changed, _schema())


def test_stage1_descriptor_has_empty_future_sections_and_no_external_reference() -> None:
    """後続ステップの配列を先取りせず外部ファイルも参照しない。"""
    descriptor = _descriptor()
    raw_text = DESCRIPTOR_PATH.read_text(encoding="utf-8")

    assert descriptor["stateTransitionAxes"] == []
    assert descriptor["gameEndAxes"] == []
    assert descriptor["nonCoverageFields"] == []
    assert descriptor["projectionRules"] == []
    assert descriptor["digestSpec"]["stage1ExternalReferences"] == "forbidden"
    assert "history-depth.json" not in raw_text
