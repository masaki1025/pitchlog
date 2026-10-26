"""PR のコア領域・検査経路変更に人間確認を要求する。"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
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
DELEGATION_POLICY_PATH = "docs/features/mvp-delegated-core-review/policy.json"
# JSON登録前・登録削除後も、この検査経路自体の変更を対象から外さない。
DELEGATION_GUARD_PATH_ADDITIONS = (DELEGATION_POLICY_PATH,)
DELEGATION_REPOSITORY = "masaki1025/pitchlog"
DELEGATION_SOURCE = "01a1686c-7000-7683-965d-0cb7d58ebb7c/user20261023"
DELEGATION_POINTER = "PO-DELEGATION-EVIDENCE:"
DELEGATION_COMMENT_MARKER = "PITCHLOG-PO-DELEGATION-V1\n"
DELEGATION_API_RESPONSE_MAX_BYTES = 1024 * 1024
DELEGATION_QUOTES = (
    "コア領域を含む最終差分の確認と是正判断",
    "条件を満たしたPRのDraft解除・通常マージ",
    "今回のMVP作業と対象PRへ限定してください",
    "委任証拠欠落・対象版不一致・重大指摘未解消を拒否する仕組みを維持してください",
)

BASELINE_DEFINITION_PATHS = frozenset(
    {
        "scripts/core_guard.py",
        "tests/test_core_guard.py",
    }
)
# 追加層は JSON を変更するコミットより先に固定する。同一コミットでの追随を許さない。
DOMAIN_RUNTIME_PATH_ADDITIONS = (
    "frontend/src/domain/*",
    "backend/src/pitchlog/domainrt/*",
    "frontend/public/domain/*",
    "frontend/scripts/domain-checks/*",
    "frontend/scripts/domain-build/*",
    "frontend/scripts/domain-sql/*",
    "frontend/index.html",
    "frontend/eslint.config.js",
    "frontend/.dependency-cruiser.cjs",
    "frontend/src/testing/vectorRunner.ts",
    "frontend/src/testing/vectorRunner.spec.ts",
    "frontend/src/testing/vectorConformance.spec.ts",
    "frontend/src/testing/handoffLoader.ts",
    "frontend/src/testing/handoffLoader.spec.ts",
    "frontend/src/testing/artifactAdapter.ts",
    "frontend/src/testing/artifactAdapter.spec.ts",
    "backend/tests/domainrt/*",
    "backend/Dockerfile",
)
INITIAL_RIGHTS_PATH_ADDITIONS = (
    "backend/src/pitchlog/recording_rights/initial_grant.py",
    "backend/tests/test_initial_recording_right_candidate.py",
)
PREPARING_READ_PATH_ADDITIONS = (
    "backend/src/pitchlog/services/game_creation.py",
    "backend/tests/test_game_preparing*.py",
)
DURABLE_LEDGER_PATH_ADDITIONS = (
    "backend/src/pitchlog/durable_rights_ledger/*",
    "backend/tests/test_durable_rights_ledger_contract.py",
)
DURABLE_LEDGER_FIXTURE_ADDITION = (
    "tests/fixtures/tenant_boundary/positive/pitchlog/durable_rights_ledger/*",
)
RG1_LIFECYCLE_PATH_ADDITIONS = (
    'backend/src/pitchlog/recording_rights/rg1_lifecycle.py',
    'backend/src/pitchlog/recording_rights/rg1_lifecycle.sql',
    'backend/src/pitchlog/recording_rights/rg1_lifecycle_manifest.json',
)
INITIAL_GRANT_DB_SCOPE_PATH_ADDITIONS = (
    "backend/src/pitchlog/repositories/initial_recording_right.py",
    "backend/src/pitchlog/repositories/function_operations.py",
    "backend/src/pitchlog/recording_rights/initial_grant_broker.py",
)
INITIAL_GAME_START_COMPONENT_PATH_ADDITIONS = (
    "backend/tests/test_initial_game_start_components.py",
)
INITIAL_GAME_START_HTTP_PATH_ADDITIONS = (
    "backend/src/pitchlog/api/routers/games.py",
    "backend/src/pitchlog/api/tenant_access.py",
    "backend/tests/test_api_app.py",
    "backend/tests/test_api_conventions.py",
    "backend/tests/test_api_tenant_match_metadata.py",
)
# 実merge-baseで未登録のinitial scope層も合成し、既追加を失わない。
AREA_PATH_ADDITIONS: Mapping[str, tuple[str, ...]] = {
    'sync-protocol': (
        *INITIAL_GRANT_DB_SCOPE_PATH_ADDITIONS,
        *INITIAL_GAME_START_COMPONENT_PATH_ADDITIONS,
    ),
    'recording-rights': (
        *INITIAL_GRANT_DB_SCOPE_PATH_ADDITIONS,
        *INITIAL_GAME_START_COMPONENT_PATH_ADDITIONS,
        *INITIAL_GAME_START_HTTP_PATH_ADDITIONS,
    ),
    'tenant-isolation': (
        *INITIAL_GRANT_DB_SCOPE_PATH_ADDITIONS,
        *INITIAL_GAME_START_COMPONENT_PATH_ADDITIONS,
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
        number: 委任確認で必須となるPR番号。
        repository: イベントの対象リポジトリ。
        head_repository: headブランチの所属リポジトリ。
        head_branch: headブランチ名。
    """

    base_sha: str
    head_sha: str
    body: str
    number: int | None = None
    repository: str | None = None
    head_repository: str | None = None
    head_branch: str | None = None


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


def _parent_has_area_path_additions(root: Path, revision: str) -> bool:
    """いずれかの親で領域別追加層の定義が存在したかを返す。"""
    parents = _run_git(
        root,
        ["show", "-s", "--format=%P", revision],
        f"{revision} の親コミット列挙",
    ).split()
    for parent in parents:
        paths = _run_git(
            root,
            ["ls-tree", "--name-only", parent, "--", "scripts/core_guard.py"],
            f"{parent} の core_guard.py 存在確認",
        )
        if "scripts/core_guard.py" not in paths.splitlines():
            continue
        source = _run_git(
            root,
            ["show", f"{parent}:scripts/core_guard.py"],
            f"{parent} の core_guard.py blob 読み取り",
        )
        if re.search(r"(?m)^AREA_PATH_ADDITIONS\s*(?::[^=\n]+)?=", source):
            return True
    return False


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
        if (
            CORE_AREAS_RELATIVE_PATH in changed
            and changed_definitions
            and _parent_has_area_path_additions(root, revision)
        ):
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
    repository = data.get("repository", {})
    head_repository = head.get("repo", {})
    number = pull_request.get("number")
    return PullRequestEvent(
        base["sha"], head["sha"], body,
        number if type(number) is int else None,
        repository.get("full_name") if type(repository) is dict else None,
        head_repository.get("full_name") if type(head_repository) is dict else None,
        head.get("ref"),
    )


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
        if path in DELEGATION_GUARD_PATH_ADDITIONS
        or path in core_areas.guard_paths
        or any(fnmatch.fnmatchcase(path, pattern) for pattern in core_areas.path_patterns)
    ]



def _strict_json_object(value: str, label: str) -> dict[str, Any]:
    """重複キーを許さず、委任資料をJSONオブジェクトとして読む。"""
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise GuardError(f"{label} に重複キーがある")
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=unique_pairs)
    except (ValueError, RecursionError) as error:
        raise GuardError(f"{label} のJSONが不正") from error
    if type(parsed) is not dict:
        raise GuardError(f"{label} がオブジェクトではない")
    return parsed


def _require_exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    """欠落・余分なキーを持つ委任資料を拒否する。"""
    if set(value) != keys:
        raise GuardError(f"{label} のキー集合が不一致")


def _nonempty_text(value: Any) -> bool:
    """空白だけの自己申告を証拠として扱わない。"""
    return type(value) is str and bool(value.strip())


def _load_delegation_policy(root: Path, head_sha: str) -> tuple[dict[str, Any], str]:
    """最終HEADにコミットされた今回限定policyとその識別値を読む。"""
    raw_bytes = _delegation_git_bytes(
        root, ["show", f"{head_sha}:{DELEGATION_POLICY_PATH}"], "委任policy読取",
    )
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeError as error:
        raise GuardError("委任policyがUTF-8ではない") from error
    policy = _strict_json_object(raw, "委任policy")
    _require_exact_keys(policy, {
        "schema_version", "enabled", "repository", "source", "source_kind",
        "delegated_at", "expires", "quotes", "publisher", "publisher_role", "targets",
    }, "委任policy")
    if (
        type(policy["schema_version"]) is not int or policy["schema_version"] != 1
        or policy["enabled"] is not True
        or policy["repository"] != DELEGATION_REPOSITORY
        or policy["source"] != DELEGATION_SOURCE
        or policy["source_kind"] != "local_goal_thread_not_ui_identity_proof"
        or policy["delegated_at"] != "2026-10-23"
        or policy["expires"] != "revoked_or_mvp_completed"
        or policy["quotes"] != list(DELEGATION_QUOTES)
        or policy["publisher_role"] != "github_publisher_not_po_signature"
        or policy["publisher"] != "masaki1025"
    ):
        raise GuardError("委任policyの権限根拠・有効状態が不正")
    targets = policy["targets"]
    if type(targets) is not list or not targets:
        raise GuardError("委任policyの対象表が不正")
    numbers: set[int] = set()
    for target in targets:
        if type(target) is not dict:
            raise GuardError("委任policyの対象行が不正")
        _require_exact_keys(target, {"pr", "branch"}, "委任policy対象行")
        if (
            type(target["pr"]) is not int or target["pr"] <= 0 or target["pr"] in numbers
            or not _nonempty_text(target["branch"])
            or not target["branch"].startswith(("feature/", "fix/"))
        ):
            raise GuardError("委任policyの対象識別が不正")
        numbers.add(target["pr"])
    return policy, hashlib.sha256(raw_bytes).hexdigest()



def _verify_delegation_base_policy(root: Path, event: PullRequestEvent) -> None:
    """baseの失効済みpolicyを古いheadの有効policyで復活させない。"""
    present = _delegation_git_bytes(
        root, ["ls-tree", "--format=%(objecttype)", event.base_sha,
               "--", DELEGATION_POLICY_PATH], "base委任policy存在確認",
    )
    if present == b"":
        if event.number != 177 or event.head_branch != "feature/mvp-delegated-core-review":
            raise GuardError("baseに委任policyがない。導入PR以外は委任を使用できない")
        return
    if present != b"blob\n":
        raise GuardError("base委任policyの種別が不正")
    _load_delegation_policy(root, event.base_sha)


def _delegation_git_bytes(root: Path, arguments: list[str], label: str) -> bytes:
    """委任資料のGit識別値を、文字コード置換せず固定バイト列から得る。"""
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=root, capture_output=True,
            timeout=DIFF_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GuardError(f"{label}を取得できない") from error
    if result.returncode != 0:
        raise GuardError(f"{label}の取得に失敗")
    return result.stdout


def _delegation_diff(root: Path, event: PullRequestEvent) -> str:
    """実Git差分のバイト列を、外部diffを無効にして識別する。"""
    raw = _delegation_git_bytes(
        root, ["diff", "--no-ext-diff", "--binary", "--no-renames",
               f"{event.base_sha}...{event.head_sha}"], "委任対象差分",
    )
    return hashlib.sha256(raw).hexdigest()


class _RejectDelegationRedirects(urllib.request.HTTPRedirectHandler):
    """固定GitHub API以外へ証拠取得を転送しない。"""

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        """HTTPリダイレクトは追従せず、urllibのHTTPErrorへ委ねる。"""
        return None


def _fetch_delegation_comment(comment_id: str) -> dict[str, Any]:
    """公開GitHub APIを無認証・既定TLSで読み、失敗や本文をログへ漏らさない。"""
    if type(comment_id) is not str or re.fullmatch(r"[1-9][0-9]*", comment_id) is None:
        raise GuardError("委任証拠APIのcomment IDが不正")
    url = (
        f"https://api.github.com/repos/{DELEGATION_REPOSITORY}"
        f"/issues/comments/{comment_id}"
    )
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PitchLog-Core-Guard",
    }, method="GET")
    # HTTPSHandlerは標準の証明書/hostname検証を使う。認証headerは付けない。
    opener = urllib.request.build_opener(_RejectDelegationRedirects())
    try:
        with opener.open(request, timeout=DIFF_TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.geturl() != url:
                raise GuardError("委任証拠APIの応答状態・所在が不正")
            raw = response.read(DELEGATION_API_RESPONSE_MAX_BYTES + 1)
        if len(raw) > DELEGATION_API_RESPONSE_MAX_BYTES:
            raise GuardError("委任証拠APIの応答が上限を超えた")
        content = raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        raise GuardError("委任証拠APIを取得できない") from error
    return _strict_json_object(content, "委任証拠API")


def verify_delegated_confirmation(root: Path, event: PullRequestEvent) -> None:
    """今回MVPの対象版・独立レビュー資料を照合する。意味的正しさは認証しない。

    Args:
        root: Gitリポジトリのルート。
        event: 検査対象のPRイベント。

    Raises:
        GuardError: 委任資料の欠落・対象不一致・重大指摘未解消・取得不能。
    """
    if (
        type(event.number) is not int or event.number <= 0
        or event.repository != DELEGATION_REPOSITORY
        or event.head_repository != DELEGATION_REPOSITORY
        or not _nonempty_text(event.head_branch)
        or re.fullmatch(r"[0-9a-f]{40}", event.base_sha) is None
        or re.fullmatch(r"[0-9a-f]{40}", event.head_sha) is None
    ):
        raise GuardError("委任対象のPRイベント識別が不正")
    if event.body.count(DELEGATION_POINTER) != 1:
        raise GuardError("委任証拠markerは正確に1件が必要")
    match = re.search(
        rf"(?m)^{re.escape(DELEGATION_POINTER)} "
        rf"(https://github\.com/{re.escape(DELEGATION_REPOSITORY)}/pull/"
        rf"{event.number}#issuecomment-([1-9][0-9]*))[ \t\r]*$", event.body,
    )
    if match is None:
        raise GuardError("委任証拠URLが対象PRと不一致")
    policy, policy_digest = _load_delegation_policy(root, event.head_sha)
    _verify_delegation_base_policy(root, event)
    if {"pr": event.number, "branch": event.head_branch} not in policy["targets"]:
        raise GuardError("委任policyの対象PR・branchと不一致")
    comment = _fetch_delegation_comment(match[2])
    user = comment.get("user")
    comment_body = comment.get("body")
    if (
        comment.get("id") != int(match[2]) or type(comment.get("id")) is not int
        or comment.get("html_url") != match[1]
        or comment.get("issue_url") != (
            f"https://api.github.com/repos/{DELEGATION_REPOSITORY}/issues/{event.number}"
        )
        or comment.get("author_association") not in ("OWNER", "MEMBER", "COLLABORATOR")
        or type(user) is not dict or user.get("login") != policy["publisher"]
        or type(comment_body) is not str
        or not comment_body.startswith(DELEGATION_COMMENT_MARKER)
    ):
        raise GuardError("委任証拠の所在・掲載主体・markerが不正")
    evidence = _strict_json_object(
        comment_body[len(DELEGATION_COMMENT_MARKER):], "委任証拠本文",
    )
    _require_exact_keys(evidence, {
        "authority_sha256", "pr", "base", "head", "diff_sha256", "paths",
        "reviewer_agent", "candidate_agents", "independent", "verdict", "findings", "report",
    }, "委任証拠本文")
    if (
        evidence["authority_sha256"] != policy_digest
        or type(evidence["pr"]) is not int or evidence["pr"] != event.number
        or evidence["base"] != event.base_sha or evidence["head"] != event.head_sha
        or evidence["diff_sha256"] != _delegation_diff(root, event)
        or evidence["paths"] != changed_paths(root, event.base_sha, event.head_sha)
    ):
        raise GuardError("委任証拠の根拠・対象版・実差分が不一致")
    candidates = evidence["candidate_agents"]
    reviewer = evidence["reviewer_agent"]
    report = evidence["report"]
    if (
        not _nonempty_text(reviewer)
        or type(candidates) is not list or not candidates
        or any(not _nonempty_text(candidate) for candidate in candidates)
        or len(candidates) != len(set(candidates)) or reviewer in candidates
        or evidence["independent"] is not True or evidence["verdict"] != "approved"
        or type(report) is not dict
    ):
        raise GuardError("独立レビューの識別・判定・報告が不正")
    _require_exact_keys(report, {"task", "reviewed_head", "text"}, "独立レビュー報告")
    if (
        report["task"] != reviewer or report["reviewed_head"] != event.head_sha
        or not _nonempty_text(report["text"])
    ):
        raise GuardError("独立レビュー報告の出典・対象版が不正")
    findings = evidence["findings"]
    if type(findings) is not list:
        raise GuardError("独立レビュー指摘一覧が不正")
    for finding in findings:
        if type(finding) is not dict:
            raise GuardError("独立レビュー指摘が不正")
        _require_exact_keys(finding, {"severity", "resolved", "detail"}, "独立レビュー指摘")
        if (
            finding["severity"] not in ("P0", "P1", "P2")
            or type(finding["resolved"]) is not bool or not _nonempty_text(finding["detail"])
            or (finding["severity"] in ("P0", "P1") and not finding["resolved"])
        ):
            raise GuardError("独立レビューの重大未解消または指摘形式不正")


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
    if DELEGATION_POINTER in event.body:
        try:
            verify_delegated_confirmation(root, event)
        except GuardError as error:
            print(f"core_guard: {error}", file=sys.stderr)
            return 1
        return 0
    if detected and not is_required_check_completed(event.body):
        required_line = f"- [x] {REQUIRED_CHECK_TEXT}"
        for path in detected:
            print(f"{path}: PR 本文に必須チェックがない: {required_line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
