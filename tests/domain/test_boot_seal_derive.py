"""封印集合が正本と schema から閉じて導出されることを検査する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
ASSET_PATH = ROOT / "backend/domain/boot-seal.json"
CHECK_SETS_PATH = ROOT / "backend/domain/check-sets.json"
MANIFEST_SCHEMA_PATH = ROOT / "backend/domain/manifest.schema.json"
REQUIREMENTS_PATH = ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"
DERIVER_PATH = (
    ROOT / "backend/src/pitchlog/domaincheck/boot_seal_derive.py"
)


@pytest.fixture(scope="module")
def asset() -> dict[str, Any]:
    """生成済みの封印集合資産を返す。"""
    return json.loads(ASSET_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source_inputs() -> tuple[str, dict[str, Any], dict[str, Any]]:
    """導出元の要件書、対象導出規則、schema を返す。"""
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    check_sets = json.loads(CHECK_SETS_PATH.read_text(encoding="utf-8"))
    manifest_schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    return requirements, check_sets, manifest_schema


def _elements_by_origin(asset: dict[str, Any], origin: str) -> list[dict[str, Any]]:
    """指定した由来の封印要素を返す。"""
    return [element for element in asset["elements"] if element["origin"] == origin]


def _pretty_json(value: object) -> str:
    """資産と同じ 2 空白インデントの JSON を返す。"""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _write_json(path: Path, value: object) -> None:
    """合成入力を読みやすい JSON として書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_pretty_json(value), encoding="utf-8")


def _run_deriver(root: Path) -> dict[str, Any]:
    """既存テストと同じ PYTHONPATH で導出器を別プロセス実行する。"""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pitchlog.domaincheck.boot_seal_derive",
            "--root",
            str(root),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(BACKEND_SRC)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return value


def _derive_from_inputs(
    root: Path,
    requirements: str,
    check_sets: dict[str, Any],
    manifest_schema: dict[str, Any],
) -> dict[str, Any]:
    """一時ルートへ導出元だけを置き、封印集合を実測する。"""
    requirements_path = root / REQUIREMENTS_PATH.relative_to(ROOT)
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(requirements, encoding="utf-8")
    _write_json(root / CHECK_SETS_PATH.relative_to(ROOT), check_sets)
    _write_json(root / MANIFEST_SCHEMA_PATH.relative_to(ROOT), manifest_schema)
    return _run_deriver(root)


def _constructor_values(source: str) -> list[str]:
    """構成子 enum に静的に宣言された文字列値を返す。"""
    tree = ast.parse(source)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SealConstructor"
    ]
    assert len(classes) == 1
    values: list[str] = []
    for statement in classes[0].body:
        if not isinstance(statement, ast.Assign):
            continue
        assert len(statement.targets) == 1
        assert isinstance(statement.targets[0], ast.Name)
        assert isinstance(statement.value, ast.Constant)
        assert isinstance(statement.value.value, str)
        values.append(statement.value.value)
    return values


def _assert_exact_constructor_set(source: str) -> None:
    """構成子が契約上の 2 種だけであることを要求する。"""
    values = _constructor_values(source)
    assert len(values) == 2
    assert set(values) == {
        "declaration_absence",
        "mechanism_absence",
    }


def test_asset_is_exact_output_of_independent_deriver(
    asset: dict[str, Any],
) -> None:
    """資産が手入力でなく導出器の現行出力そのものであることを検査する。"""
    assert asset == _run_deriver(ROOT)


def test_asset_is_indented_for_line_by_line_review(asset: dict[str, Any]) -> None:
    """封印集合資産が 2 空白インデントと末尾改行を持つことを検査する。"""
    assert ASSET_PATH.read_text(encoding="utf-8") == _pretty_json(asset)


def test_contract_counts_are_exact(asset: dict[str, Any]) -> None:
    """封印集合全体と 2 由来の母集合を契約値で固定する。"""
    d11_elements = _elements_by_origin(asset, "d11")
    b_elements = _elements_by_origin(asset, "nfr018-b")
    total = len(asset["elements"])
    d11 = len(d11_elements)
    b = len(b_elements)

    assert total == 136
    assert d11 == 133 and b == 3
    assert asset["counts"] == {"total": 136, "d11": 133, "b": 3}


def test_d11_set_is_source_cartesian_product(
    asset: dict[str, Any],
    source_inputs: tuple[str, dict[str, Any], dict[str, Any]],
) -> None:
    """D-11 集合が要件対象と schema 宣言名の直積であることを検査する。"""
    _, _, manifest_schema = source_inputs
    targets = asset["derivedInputs"]["targets"]
    fields = {
        "perCalculation": manifest_schema["$defs"]["Calculation"]["required"],
        "topLevel": manifest_schema["required"],
    }
    target_ids = {target["id"] for target in targets}
    expected_ids = {
        f"{target_id}/{field}"
        for target_id in target_ids
        for field in fields["perCalculation"]
    }
    expected_ids |= {
        f"manifest/{field}" for field in fields["topLevel"]
    }
    observed_ids = {
        element["id"] for element in _elements_by_origin(asset, "d11")
    }

    assert len(target_ids) == 13
    assert len(fields["perCalculation"]) == 10
    assert len(fields["topLevel"]) == 3
    assert expected_ids - observed_ids == set()
    assert observed_ids - expected_ids == set()


def test_schema_extension_changes_derived_d11_set(
    tmp_path: Path,
    asset: dict[str, Any],
    source_inputs: tuple[str, dict[str, Any], dict[str, Any]],
) -> None:
    """Schema に宣言名を足すと導出される直積が対象数ぶん増えることを示す。"""
    requirements, check_sets, manifest_schema = source_inputs
    changed = copy.deepcopy(manifest_schema)
    calculation = changed["$defs"]["Calculation"]
    calculation["required"].append("addedBySchema")
    calculation["properties"]["addedBySchema"] = {"type": "string"}
    after = _derive_from_inputs(tmp_path, requirements, check_sets, changed)
    before_d11 = _elements_by_origin(asset, "d11")
    after_d11 = _elements_by_origin(after, "d11")

    assert len(after_d11) - len(before_d11) == len(asset["derivedInputs"]["targets"])


def test_target_ids_are_stable_when_requirement_names_change(
    tmp_path: Path,
    asset: dict[str, Any],
    source_inputs: tuple[str, dict[str, Any], dict[str, Any]],
) -> None:
    """対象名だけの変更で位置由来の安定 ID が変わらないことを検査する。"""
    requirements, check_sets, manifest_schema = source_inputs
    changed = requirements.replace(
        ": 状況判定・**入力と表示のための座標変換**",
        ": 状況評価・**入力と表示のための座標変換**",
        1,
    )
    assert changed != requirements
    before = asset["derivedInputs"]["targets"]
    changed_asset = _derive_from_inputs(tmp_path, changed, check_sets, manifest_schema)
    after = changed_asset["derivedInputs"]["targets"]

    assert [row["id"] for row in before] == [row["id"] for row in after]
    assert [row["name"] for row in before] != [row["name"] for row in after]


def test_target_reordering_changes_asset_despite_unchanged_canonical_keys(
    tmp_path: Path,
    asset: dict[str, Any],
    source_inputs: tuple[str, dict[str, Any], dict[str, Any]],
) -> None:
    """位置 ID の再束縛が資産差分として固定 SHA の検出対象になることを示す。"""
    requirements, check_sets, manifest_schema = source_inputs
    lines = requirements.splitlines()
    index = next(
        position
        for position, line in enumerate(lines)
        if line.lstrip().startswith("- **(α)") and ":" in line
    )
    original_line = lines[index]
    swapped_line = original_line.replace("状況判定", "__SWAP_TARGET__", 1)
    swapped_line = swapped_line.replace("捕球選手推定", "状況判定", 1)
    swapped_line = swapped_line.replace("__SWAP_TARGET__", "捕球選手推定", 1)
    assert swapped_line != original_line
    lines[index] = swapped_line
    changed_requirements = "\n".join(lines)
    if requirements.endswith("\n"):
        changed_requirements += "\n"

    changed_asset = _derive_from_inputs(
        tmp_path,
        changed_requirements,
        check_sets,
        manifest_schema,
    )
    before_keys = {element["canonicalKey"] for element in asset["elements"]}
    after_keys = {
        element["canonicalKey"] for element in changed_asset["elements"]
    }
    before_bindings = {
        row["id"]: row["name"] for row in asset["derivedInputs"]["targets"]
    }
    after_bindings = {
        row["id"]: row["name"]
        for row in changed_asset["derivedInputs"]["targets"]
    }

    assert before_keys == after_keys
    assert before_bindings != after_bindings
    assert asset != changed_asset
    assert hashlib.sha256(_pretty_json(asset).encode()).digest() != hashlib.sha256(
        _pretty_json(changed_asset).encode()
    ).digest()


def test_target_derivation_applies_declared_set_union(
    tmp_path: Path,
    asset: dict[str, Any],
    source_inputs: tuple[str, dict[str, Any], dict[str, Any]],
) -> None:
    """2 群に同名対象がある写しでは set-union により一要素にする。"""
    requirements, check_sets, manifest_schema = source_inputs
    changed = requirements.replace(
        "①投手分析・打者分析・作戦分析の集計",
        "①状況判定",
        1,
    )
    assert changed != requirements
    before = asset["derivedInputs"]["targets"]
    changed_asset = _derive_from_inputs(tmp_path, changed, check_sets, manifest_schema)
    after = changed_asset["derivedInputs"]["targets"]

    assert len(after) == len(before) - 1
    assert len({row["name"] for row in after}) == len(after)


def test_origins_are_disjoint_and_canonical_keys_are_unique(
    asset: dict[str, Any],
) -> None:
    """2 由来の ID が互いに素で、全正規キーが一意であることを検査する。"""
    d11_elements = _elements_by_origin(asset, "d11")
    b_elements = _elements_by_origin(asset, "nfr018-b")
    d11_ids = {element["id"] for element in d11_elements}
    b_ids = {element["id"] for element in b_elements}
    keys = [element["canonicalKey"] for element in asset["elements"]]

    assert d11_ids & b_ids == set()
    assert len(keys) == len(set(keys))


def test_canonical_keys_depend_only_on_constructor_arguments(
    asset: dict[str, Any],
) -> None:
    """自然文の解消述語でなく代数的な引数が同一性を決めることを検査する。"""
    for element in asset["elements"]:
        arguments = element["arguments"]
        if element["constructor"] == "declaration_absence":
            expected = (
                f"declaration_absence({arguments['target']},{arguments['field']})"
            )
        else:
            assert element["constructor"] == "mechanism_absence"
            expected = f"mechanism_absence({arguments['bClause']})"
        assert element["canonicalKey"] == expected

    changed = copy.deepcopy(asset)
    for element in changed["elements"]:
        element["resolutionPredicate"] = {"operator": "changed-for-test"}
    assert {
        element["canonicalKey"] for element in changed["elements"]
    } == {element["canonicalKey"] for element in asset["elements"]}


def test_b_elements_map_one_to_one_to_nfr018_subclauses(
    asset: dict[str, Any],
) -> None:
    """機構不在要素が NFR-018 (b) ①②③ と一対一であることを検査する。"""
    clauses = asset["derivedInputs"]["bClauses"]
    expected = {clause["id"] for clause in clauses}
    elements = _elements_by_origin(asset, "nfr018-b")
    observed = {element["arguments"]["bClause"] for element in elements}

    assert {clause["ordinal"] for clause in clauses} == {1, 2, 3}
    assert expected - observed == set()
    assert observed - expected == set()
    for element in elements:
        clause_id = element["arguments"]["bClause"]
        assert element["id"] == f"{clause_id}/mechanism"
        assert element["resolutionPredicate"] == {
            "operator": "raw-check-conforms",
            "check": "nfr018-b-mechanism",
            "bClause": clause_id,
        }


def test_b_clause_ids_are_stable_when_headings_change(
    tmp_path: Path,
    asset: dict[str, Any],
    source_inputs: tuple[str, dict[str, Any], dict[str, Any]],
) -> None:
    """NFR-018 (b) の見出し改名で丸数字由来の ID が変わらないことを示す。"""
    requirements, check_sets, manifest_schema = source_inputs
    changed = requirements.replace(
        "① 出所と派生物の乖離の検出",
        "① 派生物乖離の検査",
        1,
    )
    assert changed != requirements
    before = asset["derivedInputs"]["bClauses"]
    changed_asset = _derive_from_inputs(tmp_path, changed, check_sets, manifest_schema)
    after = changed_asset["derivedInputs"]["bClauses"]

    assert [row["id"] for row in before] == [row["id"] for row in after]
    assert [row["name"] for row in before] != [row["name"] for row in after]


def test_algebraic_type_has_exactly_two_constructors_statically(
    asset: dict[str, Any],
) -> None:
    """実装と資産の構成子が宣言不在と機構不在の 2 種だけか検査する。"""
    source = DERIVER_PATH.read_text(encoding="utf-8")
    _assert_exact_constructor_set(source)
    assert asset["algebraicType"]["constructors"] == [
        {"name": "declaration_absence", "arguments": ["target", "field"]},
        {"name": "mechanism_absence", "arguments": ["bClause"]},
    ]


def test_third_constructor_is_rejected_by_static_check() -> None:
    """3 つ目の構成子を加えた実装の写しが静的検査で落ちることを示す。"""
    source = DERIVER_PATH.read_text(encoding="utf-8")
    changed = source.replace(
        '    MECHANISM_ABSENCE = "mechanism_absence"',
        '    MECHANISM_ABSENCE = "mechanism_absence"\n'
        '    THIRD_FOR_TEST = "third_for_test"',
        1,
    )
    assert changed != source
    with pytest.raises(AssertionError):
        _assert_exact_constructor_set(changed)
