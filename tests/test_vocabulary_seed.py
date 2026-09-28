"""語彙シードのschema適合・典拠一致・ID一意性を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
SCHEMA_PATH = (
    REPOSITORY_ROOT / "contracts/vocabulary/vocabulary_seed_schema_v1.json"
)
SEED_PATH = REPOSITORY_ROOT / "contracts/vocabulary/input_vocabulary_v1.json"
RESEARCH_PATH = (
    REPOSITORY_ROOT / "docs/features/appendix-e-golden-vectors/research.md"
)
REQUIREMENTS_PATH = (
    REPOSITORY_ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"
)
LEGACY_DATA_PATH = REPOSITORY_ROOT / "docs/legacy/research/data-layer.md"


class VocabularySeedError(ValueError):
    """語彙シード固有の意味制約違反を表す。"""


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
schema_checker = _load_module("vocabulary_seed_schema_checker", DESCRIPTOR_CHECKER_PATH)


def _load_object(path: Path) -> dict[str, Any]:
    """重複キーを拒否してJSON objectを読み込む。

    Args:
        path: 読み込むJSONファイル。

    Returns:
        読み込んだJSON object。
    """
    value = schema_checker.load_json(path, path.name)
    assert isinstance(value, dict)
    return value


def _schema() -> dict[str, Any]:
    """語彙シードschemaを返す。"""
    return _load_object(SCHEMA_PATH)


def _seed() -> dict[str, Any]:
    """語彙シードを返す。"""
    return _load_object(SEED_PATH)


def _validate_seed(seed: Mapping[str, Any]) -> None:
    """JSON Schemaとschema宣言の大域ID一意性でシードを検証する。

    Args:
        seed: 検証する語彙シード。

    Raises:
        VocabularySeedError: 軸IDまたは語彙IDが重複している場合。
    """
    schema = _schema()
    schema_checker._validate_instance(seed, schema, schema, "$")

    axes = seed["axes"]
    axis_ids: set[str] = set()
    entries_by_id: dict[str, str] = {}
    for axis in axes:
        axis_id = axis["axisId"]
        if axis_id in axis_ids:
            raise VocabularySeedError(f"axisIdが重複している: {axis_id}")
        axis_ids.add(axis_id)
        for entry in axis["entries"]:
            entry_id = entry["id"]
            display_name = entry["initialDisplayName"]
            if entry_id in entries_by_id:
                previous = entries_by_id[entry_id]
                raise VocabularySeedError(
                    "語彙IDが重複している: "
                    f"{entry_id}: {previous!r} / {display_name!r}"
                )
            entries_by_id[entry_id] = display_name


def _axis_entries(seed: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    """軸IDから語彙entry列への写像を返す。"""
    return {axis["axisId"]: axis["entries"] for axis in seed["axes"]}


def _axis_display_sets(seed: Mapping[str, Any]) -> dict[str, set[str]]:
    """軸ごとの初期表示名集合を返す。"""
    return {
        axis_id: {entry["initialDisplayName"] for entry in entries}
        for axis_id, entries in _axis_entries(seed).items()
    }


def _research_domain_rows() -> dict[str, str]:
    """research.md 7節の値ドメイン表を軸名で返す。"""
    text = RESEARCH_PATH.read_text(encoding="utf-8")
    section = text.split("**付録E の入力軸として使える値ドメイン**", 1)[1]
    section = section.split("**注意点 2 件**", 1)[0]
    rows: dict[str, str] = {}
    for line in section.splitlines():
        match = re.fullmatch(r"\| ([^|]+?) \| (.+) \|", line)
        if match is not None and match.group(1) not in {"軸", "---"}:
            rows[match.group(1)] = match.group(2)
    return rows


def _slash_values(text: str) -> set[str]:
    """slash区切りの表示名を集合へ変換する。"""
    return {value.strip() for value in text.split(" / ")}


def _research_expected_display_sets() -> dict[str, set[str]]:
    """research.md 7節から語彙表示名集合を決定的に導出する。"""
    rows = _research_domain_rows()
    result_values = set().union(
        *(
            _slash_values(rows[axis_label])
            for axis_label in (
                "打撃結果(継続)",
                "打撃結果(インプレー)",
                "打撃結果(三振系)",
                "打撃結果(四死球系)",
            )
        )
    )

    strategy = rows["作戦"]
    category_matches = re.findall(r"([^ /]+)\{([^}]+)\}", strategy)
    strategy_categories = {category for category, _ in category_matches}
    strategy_details = {
        value.strip()
        for _, values in category_matches
        for value in values.split(",")
    }
    result_part = strategy.split("。結果 = ", 1)[1]
    strategy_results = {
        re.sub(r"^\([^)]*\)", "", value.strip())
        for value in result_part.split(" /")
    }

    pitcher_destinations, pickoff_results = rows["投手牽制"].split(" × ", 1)
    catcher_destinations = rows["捕手牽制"].split("(", 1)[0]
    batted_ball_types = set(re.findall(r"(?:^| / )([GLF])\(", rows["打球タイプ"]))
    runner_outcomes = _slash_values(rows["一走状況"])
    runner_outcomes_only = {
        value
        for value in runner_outcomes
        if value in {"封殺", "投手牽制死", "捕手牽制死", "盗塁死", "走塁死"}
    }

    return {
        "batting-result": result_values,
        "secondary-result": _slash_values(rows["打撃結果2"]),
        "strategy-category": strategy_categories,
        "strategy-detail": strategy_details,
        "strategy-result": strategy_results,
        "error-type": _slash_values(rows["エラーの種類"]),
        "pitcher-pickoff-destination": _slash_values(pitcher_destinations),
        "catcher-pickoff-destination": _slash_values(catcher_destinations),
        "pickoff-result": _slash_values(pickoff_results),
        "batted-ball-type": batted_ball_types,
        "batter-status": _slash_values(rows["打者状況"]),
        "first-runner-status": runner_outcomes,
        "second-runner-status": {"継続", "三進", "本進"} | runner_outcomes_only,
        "third-runner-status": {"継続", "本進"} | runner_outcomes_only,
    }


def _requirements_pitch_types() -> dict[str, tuple[str, str]]:
    """付録D-4から球種コード・表示名・系統を抽出する。"""
    text = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    section = text.split("**球種の初期値（10種）", 1)[1]
    section = section.split("※括弧内は略号属性", 1)[0]
    families = {
        "直球系": "fastball-family",
        "スラ系": "slider-family",
        "落ち系": "drop-family",
        "未分類": "unclassified",
    }
    result: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        match = re.match(r"\s+- ([^:]+): (.+)", line)
        if match is None:
            continue
        family = families[match.group(1)]
        for display_name, code in re.findall(r"([^、：（]+)\(([A-Z0-9]+)\)", match.group(2)):
            result[code] = (display_name.strip("*"), family)
    return result


def _legacy_batted_ball_strengths() -> set[str]:
    """旧88列資料の打球強度行からセンチネル以外の値を抽出する。"""
    for line in LEGACY_DATA_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("| 49 | 打球強度 |"):
            return set(re.findall(r'"([ABC])"', line))
    raise AssertionError("旧88列資料から打球強度行を抽出できない")


def test_seed_conforms_to_closed_schema_and_d12_filename() -> None:
    """語彙シードが閉じたschemaとD-12の版付き命名に適合する。"""
    seed = _seed()
    _validate_seed(seed)

    assert SEED_PATH.parent.name == "vocabulary"
    assert SEED_PATH.name == f"{seed['vocabularyId']}_v1.json"
    assert seed["version"] == SEED_PATH.stem


def test_seed_matches_vocabulary_evidence_exactly() -> None:
    """収録した全軸が版固定vocab.ts由来の照合資料と完全一致する。"""
    actual = _axis_display_sets(_seed())
    expected = _research_expected_display_sets()
    expected["batted-ball-strength"] = _legacy_batted_ball_strengths()

    pitch_types = _requirements_pitch_types()
    expected["pitch-type"] = {display_name for display_name, _ in pitch_types.values()}

    assert actual == expected

    pitch_entries = _axis_entries(_seed())["pitch-type"]
    actual_pitch_types = {
        entry["shortCode"]: (entry["initialDisplayName"], entry["classification"])
        for entry in pitch_entries
    }
    assert actual_pitch_types == pitch_types


def test_seed_omits_storage_sentinel_and_preserves_pickoff_notation() -> None:
    """未選択センチネルを除外し、投捕の牽制表記差を保持する。"""
    displays = _axis_display_sets(_seed())

    assert all("0" not in values for values in displays.values())
    assert displays["pitcher-pickoff-destination"] == {
        "一塁牽制",
        "二塁牽制",
        "三塁牽制",
    }
    assert displays["catcher-pickoff-destination"] == {
        "1塁牽制",
        "2塁牽制",
        "3塁牽制",
    }


def test_entry_ids_are_global_and_axis_prefixed() -> None:
    """語彙IDが全軸で一意かつ所属軸を接頭辞として持つ。"""
    seed = _seed()
    ids: list[str] = []
    for axis_id, entries in _axis_entries(seed).items():
        for entry in entries:
            assert entry["id"].startswith(f"{axis_id}.")
            ids.append(entry["id"])

    assert len(ids) == len(set(ids))


def test_same_id_with_different_display_name_fails() -> None:
    """同一IDへ異なる初期表示名を割り当てたシードを拒否する。"""
    seed = copy.deepcopy(_seed())
    duplicate = copy.deepcopy(seed["axes"][0]["entries"][0])
    duplicate["initialDisplayName"] = "異なる表示名"
    seed["axes"][1]["entries"].append(duplicate)

    with pytest.raises(VocabularySeedError, match="語彙IDが重複"):
        _validate_seed(seed)


def test_step38_does_not_create_manifest_or_content_hash() -> None:
    """manifestと内容hashをステップ39へ残す。"""
    assert not (
        REPOSITORY_ROOT / "contracts/vocabulary/vocabulary_manifest_v1.json"
    ).exists()

    def contains_content_hash(value: object) -> bool:
        if isinstance(value, dict):
            return "contentHash" in value or any(
                contains_content_hash(child) for child in value.values()
            )
        if isinstance(value, list):
            return any(contains_content_hash(child) for child in value)
        return False

    assert not contains_content_hash(_seed())
    assert not contains_content_hash(_schema())
