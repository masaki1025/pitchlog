"""凍結基準の版付き履歴 parser を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "frozen_history.py"


def _load_parser() -> ModuleType:
    """parser をリポジトリの import 設定に依存せず読む。"""
    spec = importlib.util.spec_from_file_location("frozen_history_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parser = _load_parser()


def _v1_record(name: str) -> dict[str, Any]:
    """prefix の同一性検査に使う合成 v1 record を作る。"""
    return {
        "source_commit": f"commit-{name}",
        "change": {
            "subject": name,
            "before": {"state": "NO_BASELINE", "identifiers": []},
            "after": {"state": "PRESENT", "identifiers": [name]},
        },
        "reason": f"reason-{name}",
    }


def _v2_record(name: str = "third") -> dict[str, Any]:
    """版判定だけに必要な最小の合成 v2 record を作る。"""
    return {"record_schema_version": 2, "name": name}


def _base_history() -> list[dict[str, Any]]:
    """順序の異なる 2 件からなる合成 prefix を作る。"""
    return [_v1_record("first"), _v1_record("second")]


def _asset_map() -> dict[str, dict[str, dict[str, bool]]]:
    """authority 宣言を持つ 7 資産の合成マップを作る。"""
    return {
        f"asset-{index}.json": {
            "baseline_control": {"history_authority": index == 0}
        }
        for index in range(7)
    }


def test_v1_only_history_is_parsed() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    head[0] = {
        "reason": "reason-first",
        "change": {
            "after": {"identifiers": ["first"], "state": "PRESENT"},
            "before": {"identifiers": [], "state": "NO_BASELINE"},
            "subject": "first",
        },
        "source_commit": "commit-first",
    }

    records = parser.parse_history(base, head)

    assert tuple(record.schema_version for record in records) == (1, 1)
    assert records[0].value == base[0]


def test_v1_prefix_and_v2_append_are_parsed() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    head.append(_v2_record())

    records = parser.parse_history(base, head)

    assert tuple(record.schema_version for record in records) == (1, 1, 2)
    assert records[-1].value == _v2_record()


def test_changed_prefix_record_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0]["reason"] = "changed"

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_deleted_prefix_record_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head.pop()

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_reordered_prefix_records_are_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head.reverse()

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_replaced_prefix_record_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0] = _v1_record("replacement")

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_prefix_integer_replaced_with_equal_float_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    base[0]["contract_revision"] = 13
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0]["contract_revision"] = 13.0

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_prefix_float_replaced_with_equal_integer_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    base[0]["contract_revision"] = 13.0
    head = copy.deepcopy(base)
    assert parser.parse_history(base, head)
    head[0]["contract_revision"] = 13

    with pytest.raises(parser.ContractError, match="prefix"):
        parser.parse_history(base, head)


def test_versionless_append_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = [*copy.deepcopy(base), _v2_record()]
    assert parser.parse_history(base, head)
    del head[-1]["record_schema_version"]

    with pytest.raises(parser.ContractError, match="record_schema_version"):
        parser.parse_history(base, head)


def test_explicit_v1_append_is_rejected_after_valid_baseline() -> None:
    base = _base_history()
    head = [*copy.deepcopy(base), _v2_record()]
    assert parser.parse_history(base, head)
    head[-1]["record_schema_version"] = 1

    with pytest.raises(parser.ContractError, match="record_schema_version 2"):
        parser.parse_history(base, head)


@pytest.mark.parametrize("unknown_version", [3, 0, -1, 2.0, True, "2"])
def test_unknown_version_is_rejected_after_valid_baseline(unknown_version: object) -> None:
    base = _base_history()
    head = [*copy.deepcopy(base), _v2_record()]
    assert parser.parse_history(base, head)
    head[-1]["record_schema_version"] = unknown_version

    with pytest.raises(parser.ContractError, match="record_schema_version 2"):
        parser.parse_history(base, head)


def test_no_history_authority_is_rejected_after_valid_baseline() -> None:
    assets = _asset_map()
    assert parser.validate_history_authority(assets) == "asset-0.json"
    assets["asset-0.json"]["baseline_control"]["history_authority"] = False

    with pytest.raises(parser.ContractError, match="ちょうど 1 件"):
        parser.validate_history_authority(assets)


def test_multiple_history_authorities_are_rejected_after_valid_baseline() -> None:
    assets = _asset_map()
    assert parser.validate_history_authority(assets) == "asset-0.json"
    assets["asset-1.json"]["baseline_control"]["history_authority"] = True

    with pytest.raises(parser.ContractError, match="ちょうど 1 件"):
        parser.validate_history_authority(assets)
