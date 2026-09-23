"""ドメイン計算検査器の共通 CLI 契約をプロセス境界で検査する。"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
SCHEMA_PATH = ROOT / "backend/domain/manifest.schema.json"
HASH = f"sha256:{'0' * 64}"
EXPECTED_LEAF_COUNT = 120
EXPECTED_MUTATION_ATTEMPTS = 240

JsonPath = tuple[str | int, ...]


def _generated(generated_id: str, artifact_kind: str) -> dict[str, str]:
    """合成生成物の宣言を返す。"""
    return {
        "generatedId": generated_id,
        "path": f"synthetic/generated/{generated_id}.txt",
        "artifactKind": artifact_kind,
    }


def _calculation(target_class: str) -> dict[str, Any]:
    """対象区分に対応する合成対象計算を返す。"""
    calculation_id = f"synthetic-{target_class}"
    stages_by_class = {
        "alpha": ["python"],
        "beta-1-5": ["sql", "typed-receiver", "formatter"],
        "beta-7": ["sql", "typed-receiver"],
    }
    stages = stages_by_class[target_class]
    generated = [
        _generated(f"{calculation_id}-{stage}", stage) for stage in stages
    ]
    invocation = {
        "adapter": f"synthetic/adapters/{calculation_id}.py",
        "operation": "run",
    }
    if len(stages) == 1:
        direct_target: dict[str, Any] = {
            "directTargetId": f"{calculation_id}-direct",
            "targetClass": target_class,
            "kind": "single",
            "generated": generated[0]["generatedId"],
            "hash": HASH,
            "invocation": invocation,
        }
    else:
        direct_target = {
            "directTargetId": f"{calculation_id}-direct",
            "targetClass": target_class,
            "kind": "composite",
            "components": [
                {
                    "stage": stage,
                    "generated": artifact["generatedId"],
                    "hash": HASH,
                }
                for stage, artifact in zip(stages, generated, strict=True)
            ],
            "invocation": invocation,
        }

    return {
        "calculation": calculation_id,
        "source": {
            "path": f"synthetic/source/{calculation_id}.json",
            "provenance": "ADR-003 D-11 構成の完全性",
        },
        "generated": generated,
        "entrypoints": [
            {
                "entrypointId": f"{calculation_id}-entrypoint",
                "module": f"synthetic/product/{calculation_id}.py",
                "symbol": "execute",
                "adapter": f"synthetic/adapters/{calculation_id}.py",
            }
        ],
        "directTargets": [direct_target],
        "comparison": {"mode": "lossless"},
        "normalization": [],
        "vectors": [
            {
                "vectorId": f"{calculation_id}-vector",
                "calculation": calculation_id,
                "path": f"synthetic/vectors/{calculation_id}.json",
                "runner": "pytest",
                "expectedValueSchema": "#/$defs/ExpectedValue",
                "provenance": "ADR-003 D-6 契約分類",
            }
        ],
        "properties": [
            {
                "propertyId": f"{calculation_id}-invariant",
                "propertyKind": "invariant",
                "path": f"synthetic/properties/{calculation_id}.py",
                "provenance": "NFR-018 (b)② 差分の検出可能性",
            }
        ],
        "mutation": [
            {
                "mutationId": f"{calculation_id}-mutation",
                "target": generated[0]["path"],
                "operators": ["replace-constant"],
            }
        ],
    }


def _valid_asset() -> dict[str, Any]:
    """全 target 分岐を通る製品非依存の合成資産を返す。"""
    return {
        "propertyCatalog": {
            "path": "synthetic/properties/catalog.json",
            "schema": "synthetic/properties/catalog.schema.json",
            "provenance": "ADR-003 D-11 3 層表 プロパティ層",
        },
        "calculations": [
            _calculation("alpha"),
            _calculation("beta-1-5"),
            _calculation("beta-7"),
        ],
        "displayBindings": [
            {
                "displayItem": "synthetic-score",
                "callsite": "synthetic/product/score.py",
                "formatter": "format-score",
                "provenance": "ADR-003 D-11 構成の完全性",
            }
        ],
    }


@pytest.fixture
def checker_root(tmp_path: Path) -> Path:
    """実資産を変更しない一時検査ルートを作る。"""
    root = tmp_path / "repository"
    root.mkdir()
    shutil.copyfile(SCHEMA_PATH, root / "schema.json")
    return root


def _write_json(path: Path, value: object) -> None:
    """一時 fixture を UTF-8 JSON として書く。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_checker(
    root: Path,
    asset: Path | None,
    *,
    schema: Path | None = None,
    print_hash: bool = False,
    include_root: bool = True,
) -> subprocess.CompletedProcess[str]:
    """検査器を独立プロセスで実行する。"""
    command = [sys.executable, "-m", "pitchlog.domaincheck.cli"]
    if include_root:
        command.extend(["--root", str(root)])
    if schema is not None:
        command.extend(["--schema", str(schema)])
    if asset is not None:
        command.extend(["--asset", str(asset)])
    if print_hash:
        command.append("--print-hash")
    return subprocess.run(
        command,
        cwd=ROOT,
        env={"PYTHONPATH": str(BACKEND_SRC)},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_fixture(
    root: Path,
    asset: object,
    *,
    name: str = "asset.json",
    print_hash: bool = False,
) -> subprocess.CompletedProcess[str]:
    """一時資産を書き、同じ一時ルートの schema で検査する。"""
    asset_path = root / name
    _write_json(asset_path, asset)
    return _run_checker(
        root,
        Path(name),
        schema=Path("schema.json"),
        print_hash=print_hash,
    )


def _leaf_paths(value: object, prefix: JsonPath = ()) -> Iterator[JsonPath]:
    """JSON 契約木の全 scalar 葉を深さ優先で列挙する。"""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaf_paths(child, (*prefix, key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaf_paths(child, (*prefix, index))
        return
    yield prefix


def _parent_at(value: object, path: JsonPath) -> tuple[dict[str, Any] | list[Any], str | int]:
    """指定葉の親コンテナと最終キーを返す。"""
    if not path:
        raise AssertionError("root 自体は葉として変異できません")
    node = value
    for segment in path[:-1]:
        if isinstance(segment, str) and isinstance(node, dict):
            node = node[segment]
        elif isinstance(segment, int) and isinstance(node, list):
            node = node[segment]
        else:
            raise AssertionError(f"葉パスを解決できません: {path!r}")
    if not isinstance(node, (dict, list)):
        raise AssertionError(f"葉の親がコンテナではありません: {path!r}")
    return node, path[-1]


def _replace_leaf(value: object, path: JsonPath) -> None:
    """指定葉を元の型と異なる値へ置換する。"""
    parent, key = _parent_at(value, path)
    if isinstance(parent, dict) and isinstance(key, str):
        original = parent[key]
        parent[key] = 0 if isinstance(original, str) else "invalid"
        return
    if isinstance(parent, list) and isinstance(key, int):
        original = parent[key]
        parent[key] = 0 if isinstance(original, str) else "invalid"
        return
    raise AssertionError(f"葉を置換できません: {path!r}")


def _delete_leaf(value: object, path: JsonPath) -> None:
    """指定葉を親コンテナから削除する。"""
    parent, key = _parent_at(value, path)
    if isinstance(parent, dict) and isinstance(key, str):
        del parent[key]
        return
    if isinstance(parent, list) and isinstance(key, int):
        del parent[key]
        return
    raise AssertionError(f"葉を削除できません: {path!r}")


def _reverse_object_keys(value: object) -> object:
    """array 順序を保ち、全 object のキー挿入順だけを反転する。"""
    if isinstance(value, dict):
        return {
            key: _reverse_object_keys(value[key])
            for key in reversed(tuple(value))
        }
    if isinstance(value, list):
        return [_reverse_object_keys(child) for child in value]
    return value


def test_conforming_asset_exits_zero(checker_root: Path) -> None:
    result = _run_fixture(checker_root, _valid_asset())

    assert result.returncode == 0, result.stderr


def test_nonconforming_asset_exits_one(checker_root: Path) -> None:
    asset = _valid_asset()
    asset["unknown"] = True
    result = _run_fixture(checker_root, asset)

    assert result.returncode == 1
    assert "不適合" in result.stderr


def test_invalid_schema_exits_two(checker_root: Path) -> None:
    invalid_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "unsupported",
    }
    _write_json(checker_root / "invalid-schema.json", invalid_schema)
    _write_json(checker_root / "asset.json", _valid_asset())
    result = _run_checker(
        checker_root,
        Path("asset.json"),
        schema=Path("invalid-schema.json"),
    )

    assert result.returncode == 2
    assert "判定不能" in result.stderr


def test_missing_required_argument_exits_two(checker_root: Path) -> None:
    result = _run_checker(
        checker_root,
        asset=None,
        schema=Path("schema.json"),
    )

    assert result.returncode == 2
    assert "判定不能" in result.stderr


def test_default_root_is_resolved_from_module_position(tmp_path: Path) -> None:
    asset_path = tmp_path / "asset.json"
    _write_json(asset_path, _valid_asset())
    result = _run_checker(
        ROOT,
        asset_path,
        include_root=False,
    )

    assert result.returncode == 0, result.stderr


def test_exact_set_reports_expected_but_unobserved(checker_root: Path) -> None:
    asset = _valid_asset()
    del asset["displayBindings"]
    result = _run_fixture(checker_root, asset)

    assert result.returncode == 1
    assert "不足=['displayBindings']" in result.stderr
    assert "未登録=[]" in result.stderr


def test_exact_set_reports_observed_but_unexpected(checker_root: Path) -> None:
    asset = _valid_asset()
    asset["undeclared"] = []
    result = _run_fixture(checker_root, asset)

    assert result.returncode == 1
    assert "不足=[]" in result.stderr
    assert "未登録=['undeclared']" in result.stderr


def test_canonical_hash_ignores_object_key_order(checker_root: Path) -> None:
    original = _valid_asset()
    reordered = _reverse_object_keys(original)
    original_result = _run_fixture(
        checker_root,
        original,
        name="original.json",
        print_hash=True,
    )
    reordered_result = _run_fixture(
        checker_root,
        reordered,
        name="reordered.json",
        print_hash=True,
    )

    assert original_result.returncode == 0, original_result.stderr
    assert reordered_result.returncode == 0, reordered_result.stderr
    assert original_result.stdout == reordered_result.stdout
    assert original_result.stdout.startswith("sha256:")


def test_all_contract_leaves_reject_value_and_deletion_mutations(
    checker_root: Path,
) -> None:
    asset = _valid_asset()
    leaf_paths = list(_leaf_paths(asset))
    escaped: list[str] = []
    attempts = 0

    assert len(leaf_paths) == EXPECTED_LEAF_COUNT

    for index, path in enumerate(leaf_paths):
        replaced = copy.deepcopy(asset)
        _replace_leaf(replaced, path)
        result = _run_fixture(checker_root, replaced, name=f"replace-{index}.json")
        attempts += 1
        if result.returncode != 1:
            escaped.append(f"値変異: {path!r}: exit {result.returncode}")

        deleted = copy.deepcopy(asset)
        _delete_leaf(deleted, path)
        result = _run_fixture(checker_root, deleted, name=f"delete-{index}.json")
        attempts += 1
        if result.returncode != 1:
            escaped.append(f"削除変異: {path!r}: exit {result.returncode}")

    assert attempts == EXPECTED_MUTATION_ATTEMPTS
    assert escaped == []
