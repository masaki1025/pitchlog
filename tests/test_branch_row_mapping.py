"""分岐と規範行の別資産対応表を実資産へ突合する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = next(ROOT.rglob("branch_row_mapping_v1.json"))
MAPPING_RELATIVE = MAPPING_PATH.relative_to(ROOT)


def _load_module(name: str, path: Path) -> Any:
    """検査器をテスト用に読み込む。

    Args:
        name: モジュール名。
        path: ソースファイル。

    Returns:
        読み込んだモジュール。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_module("check_branch_row_mapping", ROOT / "scripts/check_branch_row_mapping.py")


def _mapping() -> dict[str, Any]:
    """実資産の対応表を変更可能な形で読む。"""
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _entry(mapping: dict[str, Any], branch_id: str) -> dict[str, Any]:
    """分岐IDで対応項目を取得する。

    Args:
        mapping: 対応表。
        branch_id: 分岐ID。

    Returns:
        対応項目。
    """
    return next(item for item in mapping["mappings"] if item["branchId"] == branch_id)


def test_repository_branch_row_mapping_is_consistent() -> None:
    """31件のfixture分岐を台帳と実在規範行へ突合する。"""
    checker.check_repository(ROOT, MAPPING_RELATIVE)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("unknown-branch", "台帳にない対応表の分岐ID"),
        ("unknown-coordinate", "規範行の座標が一意に実在しない"),
        ("missing-mapping", "対応表とfixtureを持つ分岐のexact-setが不一致"),
        ("wrong-row", "fixtureと規範行の入力種別が異なる"),
        ("decision-identity", "終了判定行自身の分岐IDが不一致"),
        ("unknown-field", "未知キー"),
        ("invalid-asset-path", "const不一致"),
    ],
)
def test_branch_row_mapping_rejects_mutated_assets(change: str, message: str) -> None:
    """架空分岐・架空座標・被覆欠落・誤帰属・schema違反を拒否する。"""
    mapping = _mapping()
    if change == "unknown-branch":
        _entry(mapping, "SO-01")["branchId"] = "NOT-IN-REGISTER"
    elif change == "unknown-coordinate":
        _entry(mapping, "SO-01")["rowRef"]["coordinate"]["resultId"] = "not-a-result"
    elif change == "missing-mapping":
        mapping["mappings"] = [
            item for item in mapping["mappings"] if item["branchId"] != "SO-01"
        ]
    elif change == "wrong-row":
        _entry(mapping, "SO-01")["rowRef"] = copy.deepcopy(
            _entry(mapping, "SO-02")["rowRef"]
        )
    elif change == "decision-identity":
        _entry(mapping, "COLD-08")["rowRef"]["coordinate"]["branchId"] = (
            "GAME-END-NORMAL"
        )
    elif change == "invalid-asset-path":
        mapping["fixtureCoveragePath"] = "not-the-declared-coverage.json"
    else:
        _entry(mapping, "SO-01")["unapprovedField"] = True
    with pytest.raises(checker.BranchRowMappingError, match=message):
        checker.check_repository(ROOT, MAPPING_RELATIVE, mapping)


def test_decision_row_branch_id_is_authoritative() -> None:
    """終了判定行の分岐IDを変えると二重保持の不一致を拒否する。"""
    mapping = _mapping()
    schema = checker._read_object(ROOT, MAPPING_RELATIVE.parent / checker.SCHEMA_NAME)
    coverage = checker._read_object(ROOT, mapping["fixtureCoveragePath"])
    register = checker._read_object(ROOT, coverage["branchRegisterPath"])
    state = checker._read_object(ROOT, mapping["stateContractPath"])
    game_end = checker._read_object(ROOT, mapping["gameEndContractPath"])
    fixtures = {
        source["fixturePath"]: checker._read_object(ROOT, source["fixturePath"])
        for source in coverage["fixtureSources"]
    }
    game_end["decisionRows"][0]["branchId"] = "NOT-IN-REGISTER"
    with pytest.raises(checker.BranchRowMappingError, match="規範行の座標が一意に実在しない"):
        checker.check_documents(mapping, schema, coverage, register, state, game_end, fixtures)
