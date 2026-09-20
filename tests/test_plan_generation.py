"""計画書の生成結果、表構造、正例 B フラグの封印を検査する。

履歴時点の成果物実在と各 ``command`` の実行監査はステップ 52 の責務である。
本モジュールは生成元と現在の計画書の構造だけを扱い、全コマンドは実行しない。
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parents[1]
FEATURE_DIR = ROOT / "docs/features/domain-calc-dsl"
STEPS_SOURCE_PATH = FEATURE_DIR / "steps.py"
STEPS_DATA_PATH = FEATURE_DIR / "steps.json"
PLAN_PATH = FEATURE_DIR / "plan.md"
FEATURE_STATUS_PATH = ROOT / "scripts/feature_status.py"
BACKEND_SRC = ROOT / "backend/src"

# 57 ステップへ更新した PO 裁定のコミットを固定比較元とする。
# 現在のブランチ先端からは導かず、当該変更と一緒に基準が動く経路を作らない。
PB_FALSE_BASE_COMMIT = "a7849e1b705a845e02ba77a4c6ff83b76d7de407"
PB_FALSE_ASSET_PATH = "docs/features/domain-calc-dsl/steps.json#pb_false"
PB_FALSE_SEAL: dict[str, object] = {
    "schemaVersion": 1,
    "assetPath": PB_FALSE_ASSET_PATH,
    "baseCommitOid": PB_FALSE_BASE_COMMIT,
    "blobDigest": "sha256:400d36bdbd1d1113a4e7c4aa925354a4ebc7a771e803a94e8a08de55ea4879f5",
}

SECTION_5_3_CHECKS = frozenset(
    {
        "**全射**",
        "**単射**",
        "**`pb` の整合**",
        "**`artifact` の実在**",
        "**`command` の実行可能性**",
        "**トリガーの評価ステップ番号**",
        "**生成結果との一致**",
        "**`steps.py` の自己整合**",
        "**`PB_FALSE` の封印**",
        "**履歴時点の実在と `command`**",
    }
)


def _load_file_module(name: str, path: Path) -> ModuleType:
    """指定した Python ファイルを独立したモジュールとして読み込む。"""
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


STEPS_MODULE = _load_file_module("domain_calc_steps_under_test", STEPS_SOURCE_PATH)
FEATURE_STATUS_MODULE = _load_file_module(
    "domain_calc_feature_status_under_test", FEATURE_STATUS_PATH
)
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))
SEAL_MODULE = importlib.import_module("pitchlog.domaincheck.seal")


@pytest.fixture(scope="module")
def steps_data() -> dict[str, Any]:
    """ステップ単一定義を読み込む。"""
    value = json.loads(STEPS_DATA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="module")
def plan_text() -> str:
    """計画書の全文を読み込む。"""
    return PLAN_PATH.read_text(encoding="utf-8")


def _extract_generated_steps(plan: str, data: dict[str, Any]) -> str:
    """計画書 §4 から ``emit_steps`` が担う本体だけを取り出す。"""
    implementation_heading = "### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)"
    heading_at = plan.index(implementation_heading)
    first_group = f"**{data['groups'][0]['title']}**"
    start = plan.index(first_group, heading_at)
    end = plan.index("\n\n## 5.", start)
    return plan[start:end]


def _extract_generated_dod(plan: str, data: dict[str, Any]) -> str:
    """計画書 §5-1 から ``emit_dod`` が担う本体だけを取り出す。"""
    section_start = plan.index("### 5-1.")
    section_end = plan.index("\n\n### 5-2.", section_start)
    section = plan[section_start:section_end]
    first_step_id = data["steps"][0]["id"]
    start = section.index(f"| {first_step_id} |")
    return section[start:]


def _section(plan: str, heading_prefix: str, next_prefix: str) -> str:
    """2 つの見出し接頭辞で囲まれた Markdown 節を返す。"""
    start = plan.index(heading_prefix)
    end = plan.index(next_prefix, start)
    return plan[start:end]


def _table_rows(section: str) -> list[list[str]]:
    """Markdown 表から見出しと区切りを除いたセル列を返す。"""
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.removeprefix("|").removesuffix("|").split("|")]
        if cells and cells[0] != "検査":
            rows.append(cells)
    return rows


def _assert_generated_sections_match(plan: str, data: dict[str, Any]) -> None:
    """生成器の 2 出力と計画書の対応範囲が byte 相当で一致することを検査する。"""
    try:
        actual_steps = _extract_generated_steps(plan, data)
        actual_dod = _extract_generated_dod(plan, data)
    except ValueError as error:
        raise AssertionError("計画書から生成対象の範囲を一意に抽出できない") from error
    assert actual_steps == STEPS_MODULE.emit_steps(data)
    assert actual_dod == STEPS_MODULE.emit_dod(data)


def _mutate_pb_to_false(data: dict[str, Any]) -> int:
    """正例 B 必須の 1 ステップを、本文とフラグの双方で false 側へ変える。"""
    step = next(step for step in data["steps"] if step["requires_positive_b"])
    assert "正例 B" in step["criteria"]
    step["requires_positive_b"] = False
    step["criteria"] = step["criteria"].replace("正例 B", "通常動作")
    return int(step["id"])


def _pb_false_asset(data: dict[str, Any]) -> dict[str, object]:
    """封印対象を ``steps.json`` の可変な他フィールドから分離する。"""
    return {"pbFalse": data["pb_false"]}


def _fixed_pb_false_snapshot() -> dict[str, Any]:
    """固定比較元に記録されたステップ定義を Git から読む。"""
    result = subprocess.run(
        [
            "git",
            "show",
            f"{PB_FALSE_BASE_COMMIT}:docs/features/domain-calc-dsl/steps.json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return value


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """feature_status の合成履歴で Git を実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def _feature_status_repository(tmp_path: Path, plan: str, total: int) -> Path:
    """active の fixture 計画書と最小の実装履歴を持つリポジトリを作る。"""
    repository = tmp_path / "feature-status-repository"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch", "develop")
    _git(repository, "config", "user.email", "plan-test@example.invalid")
    _git(repository, "config", "user.name", "Plan Test")
    plan_path = repository / "docs/features/domain-calc-dsl/plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(plan, encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", "docs: 計画を承認する")
    _git(repository, "update-ref", "refs/remotes/origin/develop", "HEAD")
    _git(repository, "checkout", "--quiet", "-b", "feature/domain-calc-dsl")
    marker = repository / "implementation.txt"
    marker.write_text("実装\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(
        repository,
        "commit",
        "--quiet",
        "-m",
        f"test: 最初の実装 (ステップ 1/{total})",
    )
    return repository


def _active_plan_fixture(plan: str) -> str:
    """実計画書の可変な現在状態に依存しない active の写しを作る。"""
    active, replacements = re.subn(
        r"(?m)^status:\s*(?:active|in-review)(\s*(?:#.*)?)$",
        r"status: active\1",
        plan,
        count=1,
    )
    assert replacements == 1, "fixture の status を active に固定できない"
    return active


def _assert_pb_false_sealed(data: dict[str, Any]) -> None:
    """既存の BOOT-SEAL 機構で ``pb_false`` を固定基準へ照合する。"""
    SEAL_MODULE._verify_commit_oid(ROOT, PB_FALSE_BASE_COMMIT)
    seal = SEAL_MODULE._expect_seal(copy.deepcopy(PB_FALSE_SEAL))
    SEAL_MODULE._verify_record(
        seal,
        _pb_false_asset(data),
        PB_FALSE_ASSET_PATH,
        PB_FALSE_BASE_COMMIT,
    )


def _assert_check_rejects(
    original: dict[str, Any], mutate: Callable[[dict[str, Any]], None]
) -> None:
    """単一定義の写しへ変異を加え、自己整合検査が拒否することを確かめる。"""
    changed = copy.deepcopy(original)
    mutate(changed)
    assert STEPS_MODULE.check(changed), "不正なステップ定義が自己整合検査を通過した"


def test_generated_steps_and_dod_match_plan_exactly(
    plan_text: str, steps_data: dict[str, Any]
) -> None:
    _assert_generated_sections_match(plan_text, steps_data)


def test_one_character_difference_from_generated_body_is_rejected(
    plan_text: str, steps_data: dict[str, Any]
) -> None:
    generated = STEPS_MODULE.emit_steps(steps_data)
    changed_body = generated.replace("ステップ", "ステツプ", 1)
    changed_plan = plan_text.replace(generated, changed_body, 1)

    with pytest.raises(AssertionError):
        _assert_generated_sections_match(changed_plan, steps_data)


def test_dod_step_ids_are_surjective(
    plan_text: str, steps_data: dict[str, Any]
) -> None:
    body = _extract_generated_dod(plan_text, steps_data)
    observed = {
        int(matched.group(1))
        for line in body.splitlines()
        if (matched := re.match(r"^\| (\d+) \|", line)) is not None
    }
    total = int(steps_data["expected_total"])
    expected = set(range(1, total + 1))

    assert observed - expected == set()
    assert expected - observed == set()


def test_dod_step_ids_are_injective_and_mother_set_is_measured(
    plan_text: str, steps_data: dict[str, Any]
) -> None:
    body = _extract_generated_dod(plan_text, steps_data)
    ids = [
        int(matched.group(1))
        for line in body.splitlines()
        if (matched := re.match(r"^\| (\d+) \|", line)) is not None
    ]
    counts = Counter(ids)

    assert len(ids) == steps_data["expected_total"]
    assert set(counts.values()) == {1}


def test_section_five_three_has_every_nonempty_implementation_cell(
    plan_text: str,
) -> None:
    section = _section(plan_text, "### 5-3.", "\n\n## 6.")
    rows = _table_rows(section)
    observed_checks = {row[0] for row in rows}

    assert len(rows) == len(SECTION_5_3_CHECKS)
    assert observed_checks == SECTION_5_3_CHECKS
    assert all(len(row) == 4 for row in rows)
    assert all(row[3] for row in rows)


def test_steps_check_accepts_the_valid_single_source(steps_data: dict[str, Any]) -> None:
    assert STEPS_MODULE.check(copy.deepcopy(steps_data)) == []


def test_steps_check_rejects_a_dropped_last_step(steps_data: dict[str, Any]) -> None:
    def drop_last(data: dict[str, Any]) -> None:
        data["steps"].pop()

    _assert_check_rejects(steps_data, drop_last)


def test_steps_check_rejects_a_step_in_the_wrong_group(steps_data: dict[str, Any]) -> None:
    def move_step(data: dict[str, Any]) -> None:
        current = data["steps"][0]["group"]
        data["steps"][0]["group"] = current + 1

    _assert_check_rejects(steps_data, move_step)


@pytest.mark.parametrize("mode", ["duplicate", "reverse"])
def test_steps_check_rejects_duplicate_or_reversed_group_ids(
    steps_data: dict[str, Any], mode: str
) -> None:
    def break_group_ids(data: dict[str, Any]) -> None:
        if mode == "duplicate":
            data["groups"][1]["id"] = data["groups"][0]["id"]
        else:
            data["groups"][0], data["groups"][1] = data["groups"][1], data["groups"][0]

    _assert_check_rejects(steps_data, break_group_ids)


def test_steps_check_rejects_an_unparseable_group_heading(
    steps_data: dict[str, Any],
) -> None:
    def remove_range_syntax(data: dict[str, Any]) -> None:
        group = data["groups"][0]
        group["title"] = re.sub(r"\(\d+〜\d+\)", "範囲不明", group["title"])

    _assert_check_rejects(steps_data, remove_range_syntax)


def test_steps_check_rejects_a_group_heading_range_mismatch(
    steps_data: dict[str, Any],
) -> None:
    def change_heading_range(data: dict[str, Any]) -> None:
        group = data["groups"][0]
        replacement_last = int(group["last"]) - 1
        group["title"] = re.sub(
            r"\(\d+〜\d+\)",
            f"({group['first']}〜{replacement_last})",
            group["title"],
        )

    _assert_check_rejects(steps_data, change_heading_range)


def test_steps_check_rejects_pb_flag_and_text_both_set_false(
    steps_data: dict[str, Any],
) -> None:
    def set_both_false(data: dict[str, Any]) -> None:
        _mutate_pb_to_false(data)

    _assert_check_rejects(steps_data, set_both_false)


def test_pb_false_seal_matches_fixed_commit_and_current_source(
    steps_data: dict[str, Any],
) -> None:
    fixed = _fixed_pb_false_snapshot()
    candidate = SEAL_MODULE._candidate(
        _pb_false_asset(fixed), PB_FALSE_ASSET_PATH, PB_FALSE_BASE_COMMIT
    )

    assert candidate == PB_FALSE_SEAL
    _assert_pb_false_sealed(steps_data)


def test_pb_false_fixed_sha_cannot_be_changed_with_the_record(
    steps_data: dict[str, Any],
) -> None:
    seal = SEAL_MODULE._expect_seal(copy.deepcopy(PB_FALSE_SEAL))
    different_base = "0" * len(PB_FALSE_BASE_COMMIT)

    with pytest.raises(SEAL_MODULE.CheckerViolation, match="BOOT-SEAL-IMMUTABLE"):
        SEAL_MODULE._verify_record(
            seal,
            _pb_false_asset(steps_data),
            PB_FALSE_ASSET_PATH,
            different_base,
        )


def test_simultaneous_pb_flag_and_pb_false_change_is_rejected_by_seal(
    steps_data: dict[str, Any],
) -> None:
    changed = copy.deepcopy(steps_data)
    changed_id = _mutate_pb_to_false(changed)
    changed["pb_false"] = sorted([*changed["pb_false"], changed_id])

    assert STEPS_MODULE.check(changed) == [], "自己申告どうしの整合だけでは検出できない変異である"
    with pytest.raises(SEAL_MODULE.CheckerViolation, match="blob digest"):
        _assert_pb_false_sealed(changed)


def test_feature_status_reads_every_step_from_active_plan_fixture(
    tmp_path: Path, plan_text: str, steps_data: dict[str, Any]
) -> None:
    active_plan = _active_plan_fixture(plan_text)
    parsed = FEATURE_STATUS_MODULE.parse_step_table(active_plan)
    total = int(steps_data["expected_total"])
    repository = _feature_status_repository(tmp_path, active_plan, total)
    result = subprocess.run(
        [
            sys.executable,
            str(FEATURE_STATUS_PATH),
            "--format",
            "hook",
            "--cwd",
            str(repository),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert parsed.valid is True
    assert parsed.total == total
    assert result.returncode == 0
    feature_line = next(
        line for line in result.stdout.splitlines() if line.startswith("domain-calc-dsl(")
    )
    assert f"/{total}" in feature_line, "比較したステップ総数が CLI 出力に現れなければならない"


def test_markdown_group_heading_splits_feature_status_table_and_fails(
    plan_text: str, steps_data: dict[str, Any]
) -> None:
    active_plan = _active_plan_fixture(plan_text)
    first_group = f"**{steps_data['groups'][0]['title']}**"
    changed = active_plan.replace(
        first_group, f"#### {steps_data['groups'][0]['title']}", 1
    )
    parsed = FEATURE_STATUS_MODULE.parse_step_table(changed)

    assert parsed.valid is False
    assert parsed.total != steps_data["expected_total"]
    with pytest.raises(AssertionError):
        _assert_generated_sections_match(changed, steps_data)
