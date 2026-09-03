"""DB 環境期待値資産の典拠を全数検査する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from .conftest import _required_db_execution_error, _required_dsn

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ASSET_PATH = Path(__file__).with_name("environment-expectations.json")
EXPECTATION_ROOT_KEYS = (
    "oracle_policy",
    "database_environment",
    "healthcheck",
    "test_execution",
    "dsn_environment_variables",
)
EXPECTED_EXPECTATION_COUNT = 22
EXPECTED_PROVENANCE_COUNT = 25


def _load_asset() -> dict[str, Any]:
    """期待値資産を読み込む。

    Returns:
        JSON オブジェクトとして読み込んだ期待値資産。
    """
    asset = json.loads(ASSET_PATH.read_text(encoding="utf-8"))
    assert isinstance(asset, dict)
    return asset


def _normalize_whitespace(text: str) -> str:
    """空白だけを除いた比較用文字列を返す。

    Args:
        text: 比較対象の文字列。

    Returns:
        Unicode 空白を除いた文字列。
    """
    return "".join(text.split())


def _collect_expectations(
    node: object,
    location: str,
    expectations: list[tuple[str, dict[str, Any]]],
) -> None:
    """期待値ツリーから典拠を必要とする末端を採取する。

    Args:
        node: 現在走査している値。
        location: JSON 内の現在位置。
        expectations: 採取した期待値の格納先。
    """
    if not isinstance(node, dict):
        return
    if "provenance" in node:
        expectations.append((location, node))
        return
    if any(not isinstance(value, dict) for value in node.values()):
        expectations.append((location, node))
        return
    for key, value in node.items():
        _collect_expectations(value, f"{location}.{key}", expectations)


def _provenance_entries(raw: object, expectation_location: str) -> list[dict[str, Any]]:
    """単数・複数表現の典拠を共通の配列へ変換する。

    Args:
        raw: ``provenance`` の値。
        expectation_location: エラー表示用の期待値位置。

    Returns:
        1 件以上の典拠オブジェクト。
    """
    if isinstance(raw, dict):
        return [raw]
    assert isinstance(raw, list) and raw, (
        f"{expectation_location}: provenance は空でないオブジェクトまたは配列が必要"
    )
    assert all(isinstance(entry, dict) for entry in raw), (
        f"{expectation_location}: provenance 配列の全要素はオブジェクトが必要"
    )
    return raw


def _validate_provenance(asset: dict[str, Any]) -> tuple[int, int]:
    """全期待値と全典拠の実在・逐語一致を検査する。

    Args:
        asset: 検査対象の期待値資産。

    Returns:
        期待値件数と典拠件数。
    """
    expectations: list[tuple[str, dict[str, Any]]] = []
    for root_key in EXPECTATION_ROOT_KEYS:
        assert root_key in asset, f"期待値ルートがない: {root_key}"
        _collect_expectations(asset[root_key], f"$.{root_key}", expectations)
    assert expectations, "期待値が 1 件もない"

    provenance_cases: list[tuple[str, dict[str, Any]]] = []
    for location, expectation in expectations:
        assert "provenance" in expectation, f"{location}: provenance がない"
        entries = _provenance_entries(expectation["provenance"], location)
        provenance_cases.extend(
            (f"{location}.provenance[{index}]", entry)
            for index, entry in enumerate(entries)
        )
    assert provenance_cases, "provenance が 1 件もない"

    source_cache: dict[Path, str] = {}
    for location, provenance in provenance_cases:
        source_path_text = provenance.get("path")
        assert isinstance(source_path_text, str) and source_path_text, (
            f"{location}: path は空でない文字列が必要"
        )
        source_path = (REPOSITORY_ROOT / source_path_text).resolve()
        try:
            source_path.relative_to(REPOSITORY_ROOT)
        except ValueError:
            pytest.fail(
                f"{location}: path がリポジトリ外を指している: {source_path_text}"
            )
        assert source_path.is_file(), (
            f"{location}: path が実在しない: {source_path_text}"
        )

        extracted_text = provenance.get("extracted_text")
        source_summary = provenance.get("source_summary")
        assert extracted_text is not None or source_summary is not None, (
            f"{location}: extracted_text または source_summary が必要"
        )
        if extracted_text is None:
            assert isinstance(source_summary, str) and source_summary
            continue
        assert isinstance(extracted_text, str) and extracted_text, (
            f"{location}: extracted_text は空でない文字列が必要"
        )
        source_text = source_cache.setdefault(
            source_path, source_path.read_text(encoding="utf-8")
        )
        normalized_source = _normalize_whitespace(source_text)
        assert _normalize_whitespace(extracted_text) in normalized_source, (
            f"{location}: extracted_text が path の原文に逐語一致しない"
        )
    return len(expectations), len(provenance_cases)


def _remove_all_provenance(node: object) -> None:
    """負例用に全 provenance を再帰的に除く。

    Args:
        node: 破壊対象の JSON 値。
    """
    if isinstance(node, dict):
        node.pop("provenance", None)
        for value in node.values():
            _remove_all_provenance(value)
    elif isinstance(node, list):
        for value in node:
            _remove_all_provenance(value)


def test_all_expectations_have_existing_verbatim_provenance() -> None:
    """全22期待値・全24典拠を選択せず検査する。"""
    assert _validate_provenance(_load_asset()) == (
        EXPECTED_EXPECTATION_COUNT,
        EXPECTED_PROVENANCE_COUNT,
    )


def test_asset_without_any_provenance_is_red() -> None:
    """典拠を全削除した資産を拒否する。"""
    asset = copy.deepcopy(_load_asset())
    _remove_all_provenance(asset)

    with pytest.raises(AssertionError, match="provenance"):
        _validate_provenance(asset)


def test_expectation_without_provenance_is_red() -> None:
    """期待値 1 件だけの典拠欠落も拒否する。"""
    asset = copy.deepcopy(_load_asset())
    del asset["database_environment"]["image"]["provenance"]

    with pytest.raises(AssertionError, match="provenance"):
        _validate_provenance(asset)


def test_non_verbatim_extracted_text_is_red() -> None:
    """逐語でない引用への変異を拒否する。"""
    asset = copy.deepcopy(_load_asset())
    asset["healthcheck"]["transport"]["provenance"]["extracted_text"] += (
        "原文に存在しない変異"
    )

    with pytest.raises(AssertionError, match="逐語一致しない"):
        _validate_provenance(asset)


def test_nonexistent_provenance_path_is_red() -> None:
    """実在しない典拠パスへの変異を拒否する。"""
    asset = copy.deepcopy(_load_asset())
    asset["database_environment"]["encoding"]["provenance"]["path"] = (
        "missing-source.md"
    )

    with pytest.raises(AssertionError, match="path が実在しない"):
        _validate_provenance(asset)


def test_missing_dsn_is_fail_not_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """必須 DSN が未設定なら skip せず即座に失敗する。"""
    variable_name = "PITCHLOG_TEST_MISSING_DSN"
    monkeypatch.delenv(variable_name, raising=False)

    with pytest.raises(pytest.fail.Exception, match="必須 DSN"):
        _required_dsn(variable_name)


@pytest.mark.parametrize(
    ("collected", "executed", "message"),
    [
        (set(), set(), "収集"),
        ({"db-test"}, set(), "実行"),
    ],
)
def test_zero_required_db_tests_is_red(
    collected: set[str], executed: set[str], message: str
) -> None:
    """0 件収集と 0 件実行の両方を失敗と判定する。"""
    assert message in (_required_db_execution_error(collected, executed) or "")


def test_at_least_one_executed_db_test_is_green() -> None:
    """DB 必須テストが call まで到達した状態だけを受理する。"""
    assert _required_db_execution_error({"db-test"}, {"db-test"}) is None
