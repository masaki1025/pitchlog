"""PR のコア領域・検査経路変更に人間確認を要求する。"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

REQUIRED_CHECK_TEXT = "コア領域/検査経路の変更: 人間による逐行確認を実施した"
NON_PR_SKIP_MESSAGE = "PR イベントではない — スキップ"
NO_CORE_PATHS_MESSAGE = (
    "コア領域の paths が未定義。設計書 6.3 の落とし込み規則に従い実装追随で登録する"
    " — コア検査対象なし"
)
DIFF_TIMEOUT_SECONDS = 30
CORE_AREAS_RELATIVE_PATH = ".claude/core-areas.json"
BASELINE_DEFINITION_PATHS = frozenset(
    {
        "scripts/core_guard.py",
        "tests/test_core_guard.py",
    }
)
# 追加層は JSON を変更するコミットより先に固定する。同一コミットでの追随を許さない。
AREA_PATH_ADDITIONS: Mapping[str, tuple[str, ...]] = {
    "game-state": (
        "backend/domain/*",
        "backend/src/pitchlog/domaincheck/*",
        "backend/src/pitchlog/domaingen/*",
        "backend/src/pitchlog/domainmut/*",
        "backend/src/pitchlog/generated/*",
        "backend/tests/domain/*",
        "frontend/src/lib/generated/*",
        "tests/domain/*",
    ),
    "data-migration": (
        "backend/domain/*",
        "backend/src/pitchlog/domaincheck/*",
        "backend/src/pitchlog/domaingen/*",
        "backend/src/pitchlog/domainmut/*",
        "backend/src/pitchlog/generated/*",
        "backend/tests/domain/*",
        "frontend/src/lib/generated/*",
        "tests/domain/*",
    ),
}
REQUIRED_CHECK_RE = re.compile(
    rf"(?m)^[ \t]*-[ \t]*\[x\][ \t]+{re.escape(REQUIRED_CHECK_TEXT)}[ \t\r]*$"
)


class GuardError(RuntimeError):
    """fail-closed で終了すべき入力・実行上のエラー。"""


@dataclass(frozen=True)
class CoreAreas:
    """core-areas.json から読み込んだ判定対象。

    Attributes:
        path_patterns: コア領域として扱う glob パターン。
        guard_paths: 検査経路として完全一致で扱うパス。
    """

    path_patterns: tuple[str, ...]
    guard_paths: frozenset[str]


@dataclass(frozen=True)
class PullRequestEvent:
    """pull_request イベントから取得した検査に必要な値。

    Attributes:
        base_sha: PR の base コミット SHA。
        head_sha: PR の head コミット SHA。
        body: PR 本文。
    """

    base_sha: str
    head_sha: str
    body: str


def load_json(path: Path, label: str) -> Any:
    """UTF-8 JSON ファイルを読み込む。

    Args:
        path: 読み込む JSON ファイルのパス。
        label: エラーメッセージに表示する対象名。

    Returns:
        JSON としてデコードした値。

    Raises:
        GuardError: ファイルを読めない、または JSON が不正な場合。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise GuardError(f"{label} を読み込めない: {error}") from error
    except UnicodeDecodeError as error:
        raise GuardError(f"{label} が UTF-8 ではない") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise GuardError(f"{label} の JSON が不正") from error


def require_string_list(value: Any, label: str) -> list[str]:
    """空文字列を含まない文字列配列であることを検証する。

    Args:
        value: 検証対象の JSON 値。
        label: エラーメッセージに表示する項目名。

    Returns:
        検証済みの文字列配列。

    Raises:
        GuardError: 値が文字列配列でない場合。
    """
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise GuardError(f"{label} が文字列配列ではない")
    return value


def load_core_areas(root: Path) -> CoreAreas:
    """core-areas.json を読み込み、判定用の設定へ変換する。

    Args:
        root: リポジトリルート。

    Returns:
        検証済みのコア領域設定。

    Raises:
        GuardError: 設定ファイルまたはその構造が不正な場合。
    """
    data = load_json(root / CORE_AREAS_RELATIVE_PATH, "core-areas.json")
    if not isinstance(data, dict):
        raise GuardError("core-areas.json のルートがオブジェクトではない")

    areas = data.get("areas")
    if not isinstance(areas, list):
        raise GuardError("core-areas.json の areas が配列ではない")
    guard_paths = require_string_list(data.get("guard_paths"), "core-areas.json の guard_paths")

    path_patterns: list[str] = []
    for index, area in enumerate(areas):
        if not isinstance(area, dict):
            raise GuardError(f"core-areas.json の areas[{index}] がオブジェクトではない")
        paths = require_string_list(area.get("paths"), f"core-areas.json の areas[{index}].paths")
        path_patterns.extend(paths)

    return CoreAreas(tuple(path_patterns), frozenset(guard_paths))


def _run_git(root: Path, arguments: Sequence[str], label: str) -> str:
    """Git を実行して標準出力を返す。

    Args:
        root: Git リポジトリのルート。
        arguments: `git` へ渡す引数。
        label: エラー時に表示する処理名。

    Returns:
        Git の標準出力。

    Raises:
        GuardError: 起動、タイムアウト、または Git の処理に失敗した場合。
    """
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError(f"{label} がタイムアウトした") from error
    except OSError as error:
        raise GuardError(f"{label} を起動できない: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "標準エラー出力なし"
        raise GuardError(f"{label} に失敗した: {detail}")
    return result.stdout


def merge_base_revision(root: Path, base_sha: str, head_sha: str) -> str:
    """PR の比較元と head の変更不能な共通祖先を返す。

    `base_sha` 自体の blob ではなく Git が確定した merge-base を使う。これにより、
    PR head 内で基線を指すリテラルを書き換えても比較元は移動しない。

    Args:
        root: Git リポジトリのルート。
        base_sha: PR イベントの base SHA。
        head_sha: PR イベントの head SHA。

    Returns:
        merge-base の完全 commit OID。

    Raises:
        GuardError: merge-base が一意に得られない場合。
    """
    output = _run_git(
        root,
        ["merge-base", "--", base_sha, head_sha],
        "git merge-base",
    )
    revisions = output.splitlines()
    if len(revisions) != 1 or not revisions[0]:
        raise GuardError("git merge-base が一意な commit OID を返さない")
    return revisions[0]


def load_core_areas_at_revision(root: Path, revision: str) -> dict[str, Any]:
    """指定 revision の core-areas.json blob を読み込む。

    Args:
        root: Git リポジトリのルート。
        revision: 読み取る commit OID。

    Returns:
        JSON オブジェクト。

    Raises:
        GuardError: blob が読めない、または JSON オブジェクトでない場合。
    """
    text = _run_git(
        root,
        ["show", f"{revision}:{CORE_AREAS_RELATIVE_PATH}"],
        f"{revision} の core-areas.json blob 読み取り",
    )
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise GuardError(f"{revision} の core-areas.json が不正") from error
    if not isinstance(value, dict):
        raise GuardError(f"{revision} の core-areas.json がオブジェクトではない")
    return value


def _area_paths_by_id(document: Mapping[str, Any], label: str) -> dict[str, tuple[str, ...]]:
    """core-areas 文書から領域別 paths を厳密に取り出す。"""
    areas = document.get("areas")
    if not isinstance(areas, list):
        raise GuardError(f"{label} の areas が配列ではない")
    paths_by_id: dict[str, tuple[str, ...]] = {}
    for index, area in enumerate(areas):
        if not isinstance(area, dict):
            raise GuardError(f"{label} の areas[{index}] がオブジェクトではない")
        area_id = area.get("id")
        if not isinstance(area_id, str) or not area_id:
            raise GuardError(f"{label} の areas[{index}].id が文字列ではない")
        paths = require_string_list(area.get("paths"), f"{label} の {area_id}.paths")
        if len(paths) != len(set(paths)):
            raise GuardError(f"{label} の {area_id}.paths に重複がある")
        if area_id in paths_by_id:
            raise GuardError(f"{label} の領域 ID {area_id} が重複している")
        paths_by_id[area_id] = tuple(paths)
    return paths_by_id


def validate_area_path_layers(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    additions: Mapping[str, tuple[str, ...]] = AREA_PATH_ADDITIONS,
) -> None:
    """据え置き層と領域別追加層に candidate が一致することを検査する。

    追加対象領域は基線そのもの、または基線へ宣言済み追加層を全件加えた形だけを
    受理する。部分追加、削除、置換、並べ替え、未宣言追加はいずれも拒否する。

    Args:
        baseline: merge-base blob から読んだ変更不能な文書。
        candidate: PR head blob から読んだ検査対象文書。
        additions: JSON より前のコミットで固定する領域別追加層。

    Raises:
        GuardError: 領域集合または paths が二層の契約と一致しない場合。
    """
    baseline_paths = _area_paths_by_id(baseline, "merge-base")
    candidate_paths = _area_paths_by_id(candidate, "PR head")
    baseline_ids = set(baseline_paths)
    candidate_ids = set(candidate_paths)
    if candidate_ids != baseline_ids:
        raise GuardError(
            "領域 ID 集合が merge-base と不一致: "
            f"不足={sorted(baseline_ids - candidate_ids)}, "
            f"追加={sorted(candidate_ids - baseline_ids)}"
        )

    for area_id, base_paths in baseline_paths.items():
        declared = additions.get(area_id, ())
        if len(declared) != len(set(declared)):
            raise GuardError(f"{area_id} の追加層に重複がある")
        overlap = set(base_paths) & set(declared)
        if overlap and overlap != set(declared):
            raise GuardError(f"{area_id} の追加層が一部だけ基線へ取り込まれている")
        pending_additions = () if overlap else declared
        allowed_states = {base_paths, (*base_paths, *pending_additions)}
        if candidate_paths[area_id] not in allowed_states:
            raise GuardError(
                f"{area_id}.paths が merge-base の据え置き層と宣言済み追加層に不一致"
            )


def _commits_between(root: Path, base_revision: str, head_sha: str) -> tuple[str, ...]:
    """基線より後から head までのコミットを古い順で返す。"""
    output = _run_git(
        root,
        ["rev-list", "--reverse", f"{base_revision}..{head_sha}"],
        "基線以後のコミット列挙",
    )
    return tuple(output.splitlines())


def _changed_paths_in_commit(root: Path, revision: str) -> frozenset[str]:
    """指定コミットだけが変更したパス集合を返す。"""
    output = _run_git(
        root,
        [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            revision,
        ],
        f"{revision} の変更パス列挙",
    )
    return frozenset(output.splitlines())


def verify_area_path_baseline(root: Path, base_sha: str, head_sha: str) -> str:
    """merge-base blob と PR head の領域別二層契約を検査する。

    Args:
        root: Git リポジトリのルート。
        base_sha: PR イベントの base SHA。
        head_sha: PR イベントの head SHA。

    Returns:
        実際に比較へ使った merge-base の commit OID。

    Raises:
        GuardError: 二層契約違反、または JSON と基線定義の共変更がある場合。
    """
    baseline_revision = merge_base_revision(root, base_sha, head_sha)
    baseline = load_core_areas_at_revision(root, baseline_revision)
    candidate = load_core_areas_at_revision(root, head_sha)
    validate_area_path_layers(baseline, candidate)

    for revision in _commits_between(root, baseline_revision, head_sha):
        changed = _changed_paths_in_commit(root, revision)
        changed_definitions = sorted(changed & BASELINE_DEFINITION_PATHS)
        if CORE_AREAS_RELATIVE_PATH in changed and changed_definitions:
            raise GuardError(
                "core-areas.json と基線定義を同一コミットで変更している: "
                f"{revision}: {changed_definitions}"
            )
    return baseline_revision


def load_pull_request_event() -> PullRequestEvent:
    """環境変数が指す pull_request イベントを検証して読み込む。

    Returns:
        base/head SHA と本文を含む PR イベント。

    Raises:
        GuardError: イベントパス、JSON、または必須項目が不正な場合。
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise GuardError("GITHUB_EVENT_PATH が未設定")
    data = load_json(Path(event_path), "GITHUB_EVENT_PATH")
    if not isinstance(data, dict):
        raise GuardError("PR イベント JSON のルートがオブジェクトではない")

    pull_request = data.get("pull_request")
    if not isinstance(pull_request, dict):
        raise GuardError("PR イベントに pull_request がない")
    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, dict) or not isinstance(base.get("sha"), str) or not base["sha"]:
        raise GuardError("PR イベントに base SHA がない")
    if not isinstance(head, dict) or not isinstance(head.get("sha"), str) or not head["sha"]:
        raise GuardError("PR イベントに head SHA がない")
    body = pull_request.get("body")
    if body is None:
        raise GuardError("PR 本文(body)が null")
    if not isinstance(body, str):
        raise GuardError("PR 本文(body)が文字列ではない")
    return PullRequestEvent(base["sha"], head["sha"], body)


def changed_paths(root: Path, base_sha: str, head_sha: str) -> list[str]:
    """base...head の差分ファイルパスを git から取得する。

    Args:
        root: git リポジトリのルート。
        base_sha: 比較元コミット SHA。
        head_sha: 比較先コミット SHA。

    Returns:
        git diff が出力したファイルパスの配列。

    Raises:
        GuardError: git diff の起動、タイムアウト、または実行に失敗した場合。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--no-renames", "--name-only", f"{base_sha}...{head_sha}"],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError("git diff がタイムアウトした") from error
    except OSError as error:
        raise GuardError(f"git diff を起動できない: {error}") from error
    if result.returncode != 0:
        raise GuardError("git diff に失敗した")
    return [path for path in result.stdout.splitlines() if path]


def is_required_check_completed(body: str) -> bool:
    """PR 本文に必須の完了済みチェック行があるかを判定する。

    Args:
        body: PR 本文。

    Returns:
        必須チェックが ``- [x]`` で完了していれば ``True``。
    """
    return REQUIRED_CHECK_RE.search(body) is not None


def matched_paths(paths: Sequence[str], core_areas: CoreAreas) -> list[str]:
    """コア領域または検査経路に該当する差分パスを抽出する。

    Args:
        paths: git diff が出力した差分パス。
        core_areas: コア領域と検査経路の設定。

    Returns:
        コア glob または guard_paths 完全一致に該当したパスの配列。
    """
    return [
        path
        for path in paths
        if path in core_areas.guard_paths
        or any(fnmatch.fnmatchcase(path, pattern) for pattern in core_areas.path_patterns)
    ]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        解釈済みのコマンドライン引数。
    """
    parser = argparse.ArgumentParser(description="コア領域・検査経路の PR 変更を検査する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """環境変数に対応するイベントのコア領域変更を検査する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        非 PR イベントまたは違反なしなら 0、違反・検査不能なら 1。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        print(NON_PR_SKIP_MESSAGE)
        return 0

    root = parse_args(argv).root.resolve()
    try:
        event = load_pull_request_event()
        core_areas = load_core_areas(root)
        paths = changed_paths(root, event.base_sha, event.head_sha)
        verify_area_path_baseline(root, event.base_sha, event.head_sha)
    except GuardError as error:
        print(f"core_guard: {error}", file=sys.stderr)
        return 1

    if not core_areas.path_patterns:
        print(NO_CORE_PATHS_MESSAGE)

    detected = matched_paths(paths, core_areas)
    if detected and not is_required_check_completed(event.body):
        required_line = f"- [x] {REQUIRED_CHECK_TEXT}"
        for path in detected:
            print(f"{path}: PR 本文に必須チェックがない: {required_line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
