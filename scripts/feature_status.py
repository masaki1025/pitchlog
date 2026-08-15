"""feature の現在地を正本から読み取り専用で導出して表示する。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence


FRONTMATTER_LIMIT = 8 * 1024
SUBPROCESS_TIMEOUT_SECONDS = 10
PROTECTED_BRANCHES = frozenset({"main", "develop"})
STATUS_CANDIDATE_RE = re.compile(r"^status\s*:")
STATUS_LINE_RE = re.compile(r"^status:\s*(active|in-review)(?:\s+#.*)?$")
HEADING_RE = re.compile(r"^#{1,6}\s")
STEP_ROW_RE = re.compile(r"\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|")
STEP_TOKEN_START_RE = re.compile(r"[（(]ステップ[ \t]+(?P<step>[0-9]+)")
PR_STATES = frozenset({"OPEN", "MERGED", "CLOSED"})
NO_STEP_TOKEN_NOTE = "ステップ記法のコミットなし(書式未一致の可能性)"
APPROVAL_HISTORY_ERROR_NOTE = "承認履歴取得失敗"
MACHINE_READ_FRONTMATTER_KEYS = frozenset(
    {
        "status",
        "承認",
        "worktree",
        "branch",
        "重さ分類",
        "計画レビュー周回",
        "確定ゲート周回",
        "実行方式",
    }
)


@dataclass(frozen=True)
class CommandResult:
    """外部コマンドの成功可否と標準出力を保持する。

    Attributes:
        succeeded: コマンドが終了コード 0 で完了したか。
        stdout: UTF-8 として復号した標準出力。
    """

    succeeded: bool
    stdout: str


@dataclass(frozen=True)
class Worktree:
    """Git が報告した worktree を表す。

    Attributes:
        path: worktree のルートパス。
        branch: 実ブランチ名。detached HEAD の場合は ``None``。
    """

    path: Path
    branch: str | None


@dataclass(frozen=True)
class Frontmatter:
    """厳密検証済みの plan frontmatter を表す。

    Attributes:
        status: ``active`` または ``in-review`` の status 値。
        branch: plan に書かれた branch 値。欠落時は ``None``。
        approval: 承認値。欠落時は空文字列。
        plan_review_round: 計画レビュー周回。非整数・負値は ``None``。
        final_gate_round: 確定ゲート周回。非整数・負値は ``None``。
        execution_mode: 正規化した実行方式値。欠落時は ``通常``。
        execution_mode_valid: 実行方式が列挙値に適合するか。
    """

    status: str
    branch: str | None
    approval: str
    plan_review_round: int | None
    final_gate_round: int | None
    execution_mode: str
    execution_mode_valid: bool


@dataclass(frozen=True)
class FeaturePlan:
    """導出対象となる plan と worktree の対応を表す。

    Attributes:
        name: feature ディレクトリ名。
        plan_path: plan.md の絶対パス。
        relative_plan_path: worktree 起点の Git パス。
        worktree: plan を含む worktree。
        frontmatter: 厳密検証済み frontmatter。
    """

    name: str
    plan_path: Path
    relative_plan_path: str
    worktree: Worktree
    frontmatter: Frontmatter


@dataclass(frozen=True)
class StepTable:
    """実装ステップ表の検証結果を表す。

    Attributes:
        valid: 番号列が ``{1..N}`` で ``N >= 1`` か。
        total: 表から得た最大番号。表が空・不正なら 0 の場合がある。
    """

    valid: bool
    total: int


@dataclass(frozen=True)
class CommitRecord:
    """進捗導出に必要なコミット情報を表す。

    Attributes:
        sha: コミット ID。
        parent_count: 親コミット数。
        subject: コミット件名。
        second_parent: 2 親マージ時の第 2 親コミット ID。その他では ``None``。
    """

    sha: str
    parent_count: int
    subject: str
    second_parent: str | None = None


@dataclass(frozen=True)
class Progress:
    """ステップ進捗の 3 値と縮退状態を表す。

    Attributes:
        kind: ``known`` / ``unknown`` / ``inconsistent`` / ``git_error`` / ``not_applicable``。
        completed: known 時の完了ステップ番号。
        total: 実装ステップ総数。
        note: 適用外時の説明。
    """

    kind: str
    completed: int | None = None
    total: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class FeatureResult:
    """1 feature 分の表示用導出結果を表す。

    Attributes:
        name: feature 名。
        branch: worktree の実ブランチ名。
        stage: 現在地表示。
        progress: ステップ進捗。
        pr_status: PR 状態。text モードの PR 段階でのみ gh から取得する。
        degradation: 縮退理由。通常時は ``None``。
        frontmatter: 表示補助に使う frontmatter。解析失敗時は ``None``。
        notion_expectation: text モードで表示する Notion の期待値。不要時は ``None``。
    """

    name: str
    branch: str | None
    stage: str
    progress: Progress
    pr_status: str
    degradation: str | None
    frontmatter: Frontmatter | None
    notion_expectation: str | None = None


@dataclass(frozen=True)
class NotionTransitions:
    """Notion map から取得した期待ステータスの語彙を表す。

    Attributes:
        task_start_status: ``transitions.task_start.status`` の値。
        pr_created_status: ``transitions.pr_created.status`` の値。
    """

    task_start_status: str
    pr_created_status: str


def run_command(
    args: Sequence[str],
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
) -> CommandResult:
    """タイムアウト付きで読み取りコマンドを実行する。

    Args:
        args: シェルを介さずに渡すコマンド引数。
        cwd: 実行ディレクトリ。``None`` なら呼び出し元のカレント。
        timeout_seconds: タイムアウト秒数。``None`` では規定の 10 秒。

    Returns:
        例外・タイムアウト・非 0 終了を失敗として表した結果。
    """
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=(
                SUBPROCESS_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
            ),
        )
    except Exception:
        return CommandResult(False, "")
    return CommandResult(completed.returncode == 0, completed.stdout)


def run_git(worktree: Worktree, args: Sequence[str]) -> CommandResult:
    """指定 worktree で Git の読み取りコマンドを実行する。

    Args:
        worktree: 実行対象の worktree。
        args: ``git`` のサブコマンド以降の引数。

    Returns:
        Git コマンドの実行結果。
    """
    return run_command(["git", "-C", str(worktree.path), *args])


def list_worktrees(cwd: Path) -> tuple[list[Worktree], bool]:
    """Git に登録された全 worktree を porcelain 形式から読み取る。

    Args:
        cwd: ``git worktree list`` を実行する基準ディレクトリ。

    Returns:
        worktree 一覧と、列挙が正常に取得できたかの組。
    """
    result = run_command(["git", "worktree", "list", "--porcelain"], cwd)
    if not result.succeeded:
        return [], False

    entries: list[Worktree] = []
    path: Path | None = None
    branch: str | None = None
    saw_worktree = False

    def append_current() -> None:
        if path is not None:
            entries.append(Worktree(path=path, branch=branch))

    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            append_current()
            raw_path = line.removeprefix("worktree ").strip()
            path = Path(raw_path) if raw_path else None
            branch = None
            saw_worktree = True
        elif line.startswith("branch ") and path is not None:
            raw_branch = line.removeprefix("branch ").strip()
            branch = raw_branch.removeprefix("refs/heads/") or None
    append_current()

    if not saw_worktree or not entries:
        return [], False
    return entries, True


def parse_nonnegative_integer(value: str | None) -> int | None:
    """半角の非負整数を解析し、不正値を ``None`` で表す。

    Args:
        value: frontmatter から取得した文字列。キー欠落時は ``None``。

    Returns:
        解析済み整数。キー欠落時は 0、不正値は ``None``。
    """
    if value is None:
        return 0
    if not re.fullmatch(r"[0-9]+", value):
        return None
    return int(value)


def parse_frontmatter_body(body: str) -> Frontmatter | None:
    """frontmatter 本文を解析し、機構読取キーと status を厳密検証する。

    Args:
        body: 開閉デリミタを除いた frontmatter 本文。

    Returns:
        有効な frontmatter。status 不適合または機構読取キーの重複時は ``None``。
    """
    lines = body.splitlines()
    status_lines = [line for line in lines if STATUS_CANDIDATE_RE.match(line)]
    if len(status_lines) != 1:
        return None
    status_match = STATUS_LINE_RE.fullmatch(status_lines[0])
    if status_match is None:
        return None

    values: dict[str, str] = {}
    seen_machine_keys: set[str] = set()
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip()
        if normalized_key in MACHINE_READ_FRONTMATTER_KEYS:
            if normalized_key in seen_machine_keys:
                return None
            seen_machine_keys.add(normalized_key)
        values[normalized_key] = value.split("#", 1)[0].strip()

    raw_mode = values.get("実行方式")
    execution_mode = "通常" if raw_mode is None else raw_mode
    return Frontmatter(
        status=status_match.group(1),
        branch=values.get("branch") or None,
        approval=values.get("承認", ""),
        plan_review_round=parse_nonnegative_integer(values.get("計画レビュー周回")),
        final_gate_round=parse_nonnegative_integer(values.get("確定ゲート周回")),
        execution_mode=execution_mode,
        execution_mode_valid=execution_mode in {"通常", "fast"},
    )


def parse_frontmatter_bytes(data: bytes) -> Frontmatter | None:
    """8KiB 上限内の frontmatter ブロックを切り詰めずに解析する。

    Args:
        data: plan 先頭から読んだバイト列。

    Returns:
        有効な frontmatter。非閉止・上限超過・UTF-8 不正時は ``None``。
    """
    lines = data.splitlines(keepends=True)
    if not lines:
        return None

    consumed = len(lines[0])
    if consumed > FRONTMATTER_LIMIT or lines[0].rstrip(b"\r\n").strip() != b"---":
        return None

    body: list[bytes] = []
    for line in lines[1:]:
        consumed += len(line)
        if consumed > FRONTMATTER_LIMIT:
            return None
        if line.rstrip(b"\r\n").strip() == b"---":
            try:
                return parse_frontmatter_body(b"".join(body).decode("utf-8"))
            except UnicodeDecodeError:
                return None
        body.append(line)
    return None


def read_frontmatter(path: Path) -> Frontmatter | None:
    """plan ファイル先頭の frontmatter だけを安全上限付きで読む。

    Args:
        path: plan.md のパス。

    Returns:
        有効な frontmatter。読み取り失敗も ``None`` として縮退する。
    """
    try:
        with path.open("rb") as source:
            data = source.read(FRONTMATTER_LIMIT + 1)
    except Exception:
        return None
    return parse_frontmatter_bytes(data)


def parse_snapshot_frontmatter(snapshot: str) -> Frontmatter | None:
    """Git スナップショットの frontmatter を同じ厳密規則で解析する。

    Args:
        snapshot: ``git show`` で取得した plan 内容。

    Returns:
        有効な frontmatter。8KiB 超過を含む解析失敗時は ``None``。
    """
    return parse_frontmatter_bytes(
        snapshot.encode("utf-8", "replace")[: FRONTMATTER_LIMIT + 1]
    )


def read_plan_text(path: Path) -> str | None:
    """実装ステップ表の検証に必要な plan 全文を読む。

    Args:
        path: plan.md のパス。

    Returns:
        UTF-8 の plan 全文。読み取り不能時は ``None``。
    """
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def parse_step_table(plan_text: str | None) -> StepTable:
    """実装ステップ見出し配下の表番号と必須セルを検証する。

    Args:
        plan_text: plan 全文。読み取り失敗時は ``None``。

    Returns:
        番号列が ``{1..N}`` で、各番号行の必須セルが埋まっているかを含む結果。
    """
    if plan_text is None:
        return StepTable(valid=False, total=0)

    numbers: list[int] = []
    has_empty_required_cell = False
    in_step_section = False
    for line in plan_text.splitlines():
        if HEADING_RE.match(line):
            in_step_section = "実装ステップ" in line
            continue
        if not in_step_section:
            continue
        match = STEP_ROW_RE.match(line)
        if match is None:
            continue
        numbers.append(int(match.group(1)))
        if not match.group(2).strip() or not match.group(3).strip():
            has_empty_required_cell = True

    total = max(numbers, default=0)
    if has_empty_required_cell or total < 1 or len(numbers) != total:
        return StepTable(valid=False, total=total)
    return StepTable(valid=set(numbers) == set(range(1, total + 1)), total=total)


def extract_step_tokens(subject: str, total: int) -> tuple[list[int], bool]:
    """コミット件名から完全トークンを抽出し、不正形を検出する。

    Args:
        subject: Git のコミット件名。
        total: 実装ステップ表の総数。

    Returns:
        有効トークンのステップ番号一覧と、不正形を見つけたかの組。
    """
    tokens: list[int] = []
    malformed = False

    for match in STEP_TOKEN_START_RE.finditer(subject):
        opener = match.group(0)[0]
        closer = ")" if opener == "(" else "）"
        other_closer = "）" if closer == ")" else ")"
        step = int(match.group("step"))
        position = match.end()

        if step <= 0:
            malformed = True
            continue

        declared_total: int | None = None
        if position < len(subject) and subject[position] == "/":
            total_match = re.match(r"/([0-9]+)", subject[position:])
            if total_match is None:
                malformed = True
                continue
            declared_total = int(total_match.group(1))
            position += len(total_match.group(0))
            if declared_total != total:
                malformed = True
                continue

        if position < len(subject) and subject[position] == closer:
            tokens.append(step)
            continue
        if position < len(subject) and subject[position] == other_closer:
            malformed = True
            continue
        if position >= len(subject) or not subject[position].isspace():
            malformed = True
            continue

        close_positions = [
            index
            for index in (subject.find(closer, position), subject.find(other_closer, position))
            if index != -1
        ]
        if not close_positions:
            malformed = True
            continue
        close_position = min(close_positions)
        suffix = subject[position:close_position]
        if subject[close_position] != closer or re.match(r"\s*/", suffix):
            malformed = True
            continue
        tokens.append(step)

    return tokens, malformed


def get_merge_base(plan: FeaturePlan) -> str | None:
    """feature ブランチと origin/develop のマージベースを取得する。

    Args:
        plan: 導出対象 feature。

    Returns:
        マージベース SHA。Git 取得失敗時は ``None``。
    """
    result = run_git(plan.worktree, ["merge-base", "origin/develop", "HEAD"])
    base = result.stdout.strip()
    return base if result.succeeded and base else None


def read_plan_history(
    plan: FeaturePlan,
    base: str,
) -> list[tuple[str, Frontmatter | None]] | None:
    """base..HEAD の plan スナップショットをコミット ID とともに読む。

    Args:
        plan: 導出対象 feature。
        base: ``origin/develop`` とのマージベース。

    Returns:
        コミット ID と frontmatter の組。Git 取得失敗時は ``None``。
        frontmatter 解析失敗は組内の ``None`` として保持する。
    """
    revisions = run_git(
        plan.worktree,
        ["log", "--format=%H", f"{base}..HEAD", "--", plan.relative_plan_path],
    )
    if not revisions.succeeded:
        return None

    history: list[tuple[str, Frontmatter | None]] = []
    for sha in (line.strip() for line in revisions.stdout.splitlines()):
        if not sha:
            continue
        snapshot = run_git(plan.worktree, ["show", f"{sha}:{plan.relative_plan_path}"])
        if not snapshot.succeeded:
            return None
        history.append((sha, parse_snapshot_frontmatter(snapshot.stdout)))
    return history


def has_unresolved_rejection(plan: FeaturePlan, base: str) -> bool | None:
    """base..HEAD に in-review の plan スナップショットがあるか調べる。

    Args:
        plan: 導出対象 feature。
        base: ``origin/develop`` とのマージベース。

    Returns:
        差し戻し修正中なら ``True``、なければ ``False``。Git による履歴取得に
        失敗した場合は ``None``。
    """
    history = read_plan_history(plan, base)
    if history is None:
        return None
    return any(
        frontmatter is not None and frontmatter.status == "in-review"
        for _, frontmatter in history
    )


def is_immediately_after_first_approval(
    plan: FeaturePlan,
    base: str,
    commits: Sequence[CommitRecord],
) -> bool | None:
    """最初の承認コミット直後かを履歴から判定する。

    Args:
        plan: 導出対象 feature。
        base: ``origin/develop`` とのマージベース。
        commits: ``base..HEAD`` のコミット一覧。先頭は HEAD である。

    Returns:
        最初に承認済みとなったコミットが HEAD なら ``True``。承認コミットが
        見つからない、または追加コミットがある場合は ``False``。履歴の取得・
        解析に失敗した場合は ``None``。
    """
    history = read_plan_history(plan, base)
    if history is None or any(frontmatter is None for _, frontmatter in history):
        return None

    first_approval_commit = next(
        (
            sha
            for sha, frontmatter in reversed(history)
            if frontmatter is not None and approved(frontmatter)
        ),
        None,
    )
    return bool(commits) and first_approval_commit == commits[0].sha


def read_commits(plan: FeaturePlan, base: str) -> list[CommitRecord] | None:
    """base..HEAD のコミット件名と親数を取得する。

    Args:
        plan: 導出対象 feature。
        base: ``origin/develop`` とのマージベース。

    Returns:
        コミット一覧。ログ取得または形式解釈に失敗した場合は ``None``。
    """
    result = run_git(
        plan.worktree,
        ["log", "--format=%H%x1f%P%x1f%s", f"{base}..HEAD"],
    )
    if not result.succeeded:
        return None

    records: list[CommitRecord] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\x1f", 2)
        if len(parts) != 3 or not parts[0]:
            return None
        parents = parts[1].split()
        records.append(
            CommitRecord(
                sha=parts[0],
                parent_count=len(parents),
                subject=parts[2],
                second_parent=parents[1] if len(parents) == 2 else None,
            )
        )
    return records


def is_planning_path(path: str, plan: FeaturePlan) -> bool:
    """変更パスが当該 feature または worklog 配下かを判定する。

    Args:
        path: Git が返した worktree 相対パス。
        plan: 導出対象 feature。

    Returns:
        計画系コミットに許可されるパスなら ``True``。
    """
    feature_prefix = str(Path(plan.relative_plan_path).parent).replace("\\", "/") + "/"
    return path.startswith(feature_prefix) or path.startswith("docs/worklog/")


def is_documentation_path(path: str) -> bool:
    """変更パスがコードに触れない文書系かを判定する。

    Args:
        path: Git が返した worktree 相対パス。

    Returns:
        docs 配下、または拡張子が ``.md`` なら ``True``。
    """
    return path.startswith("docs/") or path.endswith(".md")


def read_commit_paths(plan: FeaturePlan, commit: CommitRecord) -> list[str] | None:
    """コミットの変更パスを読み取り、取得失敗を区別して返す。

    Args:
        plan: 導出対象 feature。
        commit: 変更パスを調べるコミット。

    Returns:
        変更パス一覧。``None`` は diff-tree の取得失敗、空一覧は空 diff。
    """
    result = run_git(
        plan.worktree,
        ["diff-tree", "--no-commit-id", "--name-only", "-r", commit.sha],
    )
    if not result.succeeded:
        return None
    return [line for line in result.stdout.splitlines() if line]


def is_develop_integration_merge(plan: FeaturePlan, commit: CommitRecord) -> bool:
    """2 親マージが origin/develop の取り込みかを安全側で判定する。

    Args:
        plan: 導出対象 feature。
        commit: 判定対象のマージコミット。

    Returns:
        第 2 親が origin/develop の祖先なら ``True``。取得失敗を含む
        その他の状態は ``False``。
    """
    if commit.parent_count != 2 or commit.second_parent is None:
        return False
    result = run_git(
        plan.worktree,
        [
            "merge-base",
            "--is-ancestor",
            commit.second_parent,
            "origin/develop",
        ],
    )
    return result.succeeded


def classify_unmarked_commit(plan: FeaturePlan, commit: CommitRecord) -> str:
    """無記法コミットを進捗導出用の分類へ安全側で分ける。

    Args:
        plan: 導出対象 feature。
        commit: 判定対象コミット。

    Returns:
        planning、documentation、empty、merge_allowed、merge_unknown、
        classification_error、implementation のいずれか。
    """
    if commit.parent_count >= 2:
        if is_develop_integration_merge(plan, commit):
            return "merge_allowed"
        return "merge_unknown"
    paths = read_commit_paths(plan, commit)
    if paths is None:
        return "classification_error"
    if not paths:
        return "empty"
    if all(is_planning_path(path, plan) for path in paths):
        return "planning"
    if all(is_documentation_path(path) for path in paths):
        return "documentation"
    return "implementation"


def derive_progress(plan: FeaturePlan, base: str) -> Progress:
    """実装ステップ表と base..HEAD のコミットから進捗 3 値を導出する。

    Args:
        plan: 導出対象 feature。
        base: ``origin/develop`` とのマージベース。

    Returns:
        known / unknown / inconsistent、または Git 失敗を表す進捗。
    """
    table = parse_step_table(read_plan_text(plan.plan_path))
    if not table.valid:
        return Progress(kind="inconsistent", total=table.total)

    commits = read_commits(plan, base)
    if commits is None:
        return Progress(kind="git_error", total=table.total)

    completed: set[int] = set()
    unmarked_kinds: list[str] = []
    for commit in commits:
        tokens, malformed = extract_step_tokens(commit.subject, table.total)
        if malformed or len(tokens) > 1:
            return Progress(kind="inconsistent", total=table.total)
        merge_kind: str | None = None
        if commit.parent_count >= 2:
            merge_kind = classify_unmarked_commit(plan, commit)
        if tokens:
            step = tokens[0]
            if step > table.total:
                return Progress(kind="inconsistent", total=table.total)
            completed.add(step)
            if merge_kind == "merge_unknown":
                unmarked_kinds.append(merge_kind)
        elif merge_kind is not None:
            unmarked_kinds.append(merge_kind)
        else:
            unmarked_kinds.append(classify_unmarked_commit(plan, commit))

    if completed:
        maximum = max(completed)
        if maximum > table.total or completed != set(range(1, maximum + 1)):
            return Progress(kind="inconsistent", total=table.total)
        if "classification_error" in unmarked_kinds:
            return Progress(
                kind="unknown",
                total=table.total,
                note="コミット分類の取得失敗",
            )
        if "merge_unknown" in unmarked_kinds:
            return Progress(
                kind="unknown",
                total=table.total,
                note="許可されないマージコミット混在",
            )
        if "implementation" in unmarked_kinds:
            return Progress(
                kind="unknown",
                total=table.total,
                note="無記法の実装コミット混在",
            )
        return Progress(kind="known", completed=maximum, total=table.total)

    if "classification_error" in unmarked_kinds:
        return Progress(
            kind="unknown",
            total=table.total,
            note="コミット分類の取得失敗",
        )
    if "merge_unknown" in unmarked_kinds:
        return Progress(
            kind="unknown",
            total=table.total,
            note="許可されないマージコミット混在",
        )
    if "implementation" in unmarked_kinds:
        return Progress(
            kind="unknown",
            total=table.total,
            note="無記法の実装コミット",
        )
    if any(kind not in {"planning", "documentation"} for kind in unmarked_kinds):
        return Progress(kind="unknown", total=table.total)
    if table.total >= 1:
        immediately_after_approval = is_immediately_after_first_approval(
            plan,
            base,
            commits,
        )
        if immediately_after_approval is None:
            return Progress(
                kind="not_applicable",
                note=APPROVAL_HISTORY_ERROR_NOTE,
            )
        if not immediately_after_approval:
            return Progress(
                kind="known",
                completed=0,
                total=table.total,
                note=NO_STEP_TOKEN_NOTE,
            )
    return Progress(kind="known", completed=0, total=table.total)


def approved(frontmatter: Frontmatter) -> bool:
    """承認値が codex_run.py と同じ ``済`` 始まりか判定する。

    Args:
        frontmatter: 判定対象の frontmatter。

    Returns:
        承認済みなら ``True``。
    """
    return frontmatter.approval.startswith("済")


def number_display(value: int | None) -> str:
    """拡張キーの数値を表示用に整形する。

    Args:
        value: 検証済み数値、または不正値を示す ``None``。

    Returns:
        数値文字列または ``不正値``。
    """
    return str(value) if value is not None else "不正値"


def append_final_gate(stage: str, frontmatter: Frontmatter) -> str:
    """確定ゲート周回がある段階表示へ補助情報を加える。

    Args:
        stage: 基本の段階表示。
        frontmatter: 表示補助に使う frontmatter。

    Returns:
        確定ゲート周回を必要に応じて併記した表示。
    """
    if frontmatter.final_gate_round is not None and frontmatter.final_gate_round > 0:
        return f"{stage}（確定ゲート {frontmatter.final_gate_round} 周）"
    return stage


def pr_status_stub(_: FeaturePlan) -> str:
    """gh を呼ばない経路向けの PR 状態を返す。

    Args:
        _: 将来の表示拡張に必要となる feature 情報。

    Returns:
        hook モードなど、PR を取得しない経路の状態。
    """
    return "未取得"


def github_repository_from_origin_url(remote_url: str) -> str | None:
    """対応する GitHub origin URL から ``owner/repo`` を導出する。

    Args:
        remote_url: ``git remote get-url origin`` が返した URL。

    Returns:
        ``owner/repo``。対応しない URL や空のリポジトリ名は ``None``。
    """
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:)(?P<owner>[^/\s]+)/"
        r"(?P<repository>[^/\s]+)",
        remote_url.strip(),
    )
    if match is None:
        return None
    repository = match.group("repository")
    if repository.endswith(".git"):
        repository = repository.removesuffix(".git")
    if not repository:
        return None
    return f"{match.group('owner')}/{repository}"


def get_origin_repository(plan: FeaturePlan) -> str | None:
    """worktree の origin URL から gh 用のリポジトリ名を取得する。

    Args:
        plan: origin を調べる feature。

    Returns:
        ``owner/repo``。origin の不在・取得失敗・URL 不適合時は ``None``。
    """
    result = run_git(plan.worktree, ["remote", "get-url", "origin"])
    if not result.succeeded:
        return None
    return github_repository_from_origin_url(result.stdout)


def get_pr_status(
    plan: FeaturePlan,
    timeout_seconds: float | None = None,
) -> str:
    """gh から PR 状態を取得し、失敗時は縮退ラベルを返す。

    Args:
        plan: PR を調べる feature。
        timeout_seconds: テスト時だけ差し替えられるタイムアウト秒数。

    Returns:
        ``OPEN`` / ``MERGED`` / ``CLOSED``、または ``未取得(縮退)``。
    """
    branch = plan.worktree.branch
    if not branch:
        return "未取得(縮退)"
    repository = get_origin_repository(plan)
    if repository is None:
        return "未取得(縮退)"
    result = run_command(
        [
            "gh",
            "pr",
            "view",
            branch,
            "--repo",
            repository,
            "--json",
            "state,url",
        ],
        cwd=plan.worktree.path,
        timeout_seconds=timeout_seconds,
    )
    if not result.succeeded:
        return "未取得(縮退)"
    try:
        payload = json.loads(result.stdout)
        state = payload.get("state") if isinstance(payload, dict) else None
    except Exception:
        return "未取得(縮退)"
    if not isinstance(state, str) or state not in PR_STATES:
        return "未取得(縮退)"
    return state


def pr_stage_display(pr_status: str, frontmatter: Frontmatter) -> str:
    """PR 状態を反映した段階表示を組み立てる。

    Args:
        pr_status: gh から得た PR 状態、または縮退ラベル。
        frontmatter: 確定ゲート周回の表示に使う frontmatter。

    Returns:
        PR 状態と、必要なら /task-done 待ちを併記した段階表示。
    """
    if pr_status == "MERGED":
        stage = "PR 段階(MERGED・/task-done 待ち)"
    elif pr_status in PR_STATES:
        stage = f"PR 段階({pr_status})"
    else:
        stage = "PR 段階"
    return append_final_gate(stage, frontmatter)


def get_repository_root(plan: FeaturePlan) -> Path | None:
    """共有 Git ディレクトリからメインリポジトリのルートを取得する。

    Args:
        plan: ルートを調べる feature。

    Returns:
        共有 ``.git`` ディレクトリの親。取得失敗時は ``None``。
    """
    result = run_git(
        plan.worktree,
        ["rev-parse", "--path-format=absolute", "--git-common-dir"],
    )
    common_dir = result.stdout.strip()
    if not result.succeeded or not common_dir:
        return None
    return Path(common_dir).parent


def read_notion_transitions(repository_root: Path) -> NotionTransitions | None:
    """notion-map.json から導出に必要な状態語を読み取る。

    Args:
        repository_root: メインリポジトリのルート。

    Returns:
        task_start と pr_created の状態語。欠落・破損時は ``None``。
    """
    map_path = repository_root / ".claude" / "notion-map.json"
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        transitions = payload.get("transitions") if isinstance(payload, dict) else None
        task_start = transitions.get("task_start") if isinstance(transitions, dict) else None
        pr_created = transitions.get("pr_created") if isinstance(transitions, dict) else None
        task_start_status = task_start.get("status") if isinstance(task_start, dict) else None
        pr_created_status = pr_created.get("status") if isinstance(pr_created, dict) else None
    except Exception:
        return None
    if not isinstance(task_start_status, str) or not task_start_status:
        return None
    if not isinstance(pr_created_status, str) or not pr_created_status:
        return None
    return NotionTransitions(
        task_start_status=task_start_status,
        pr_created_status=pr_created_status,
    )


def should_display_notion_expectation(result: FeatureResult) -> bool:
    """導出済み feature に Notion 期待値を付けられるか判定する。

    Args:
        result: 判定対象の feature 結果。

    Returns:
        stage が既知で text 表示の対象なら ``True``。
    """
    return result.frontmatter is not None and not result.stage.startswith("未取得(")


def get_notion_expectation(
    result: FeatureResult,
    plan: FeaturePlan,
    cache: dict[Path, NotionTransitions | None],
) -> str | None:
    """stage と PR 状態から Notion の期待値を導出する。

    Args:
        result: stage と PR 状態を含む feature 結果。
        plan: map のリポジトリルート解決に使う feature。
        cache: リポジトリルートごとの map 読み取り結果。

    Returns:
        表示する期待値。stage が不明なら ``None``、map 取得失敗時は ``未取得``。
    """
    if not should_display_notion_expectation(result):
        return None
    repository_root = get_repository_root(plan)
    if repository_root is None:
        return "未取得"
    if repository_root not in cache:
        cache[repository_root] = read_notion_transitions(repository_root)
    transitions = cache[repository_root]
    if transitions is None:
        return "未取得"

    frontmatter = result.frontmatter
    if frontmatter is not None and frontmatter.status == "active":
        return transitions.task_start_status
    if result.pr_status == "OPEN":
        return transitions.pr_created_status
    if result.pr_status == "MERGED":
        return f"{transitions.pr_created_status}(/task-done 待ち)"
    if result.pr_status == "CLOSED":
        return "人間判断(差し戻し or 取り下げ)"
    return "未取得"


def git_failure_result(plan: FeaturePlan) -> FeatureResult:
    """feature 単位の Git 取得失敗を表示用結果へ変換する。

    Args:
        plan: 失敗した feature。

    Returns:
        Git 失敗を明示した feature 結果。
    """
    return FeatureResult(
        name=plan.name,
        branch=plan.worktree.branch,
        stage="未取得(git 失敗)",
        progress=Progress(kind="git_error"),
        pr_status=pr_status_stub(plan),
        degradation="git 失敗",
        frontmatter=plan.frontmatter,
    )


def approval_history_failure_result(
    plan: FeaturePlan,
    frontmatter: Frontmatter,
    pr_status: str,
) -> FeatureResult:
    """承認履歴の取得・解析失敗を縮退表示用結果へ変換する。

    Args:
        plan: 失敗した feature。
        frontmatter: 現在の plan frontmatter。
        pr_status: 表示用の PR 状態。

    Returns:
        承認履歴取得失敗を明示した feature 結果。
    """
    return FeatureResult(
        name=plan.name,
        branch=plan.worktree.branch,
        stage=f"未取得({APPROVAL_HISTORY_ERROR_NOTE})",
        progress=Progress(kind="not_applicable", note=APPROVAL_HISTORY_ERROR_NOTE),
        pr_status=pr_status,
        degradation=APPROVAL_HISTORY_ERROR_NOTE,
        frontmatter=frontmatter,
    )


def is_approval_history_failure(progress: Progress) -> bool:
    """進捗が承認履歴の取得・解析失敗を表すか判定する。"""
    return (
        progress.kind == "not_applicable"
        and progress.note == APPROVAL_HISTORY_ERROR_NOTE
    )


def derive_feature(
    plan: FeaturePlan,
    resolve_pr: bool = False,
    pr_timeout_seconds: float | None = None,
) -> FeatureResult:
    """stage 判定表の順序で 1 feature の現在地を導出する。

    Args:
        plan: 導出対象 feature。
        resolve_pr: text モードとして gh を呼んで PR 状態を取得するか。
        pr_timeout_seconds: テスト時だけ差し替えられる gh のタイムアウト秒数。

    Returns:
        表示に必要な stage・進捗・縮退情報。
    """
    frontmatter = plan.frontmatter
    pr_status = pr_status_stub(plan)

    if not frontmatter.execution_mode_valid:
        return FeatureResult(
            name=plan.name,
            branch=plan.worktree.branch,
            stage="未取得(実行方式不正)",
            progress=Progress(kind="not_applicable", note="実行方式不正"),
            pr_status=pr_status,
            degradation="実行方式不正",
            frontmatter=frontmatter,
        )
    if frontmatter.status == "in-review":
        if resolve_pr:
            pr_status = get_pr_status(plan, timeout_seconds=pr_timeout_seconds)
        return FeatureResult(
            name=plan.name,
            branch=plan.worktree.branch,
            stage=pr_stage_display(pr_status, frontmatter),
            progress=Progress(kind="not_applicable", note="PR 段階"),
            pr_status=pr_status,
            degradation=None,
            frontmatter=frontmatter,
        )
    if frontmatter.execution_mode == "fast":
        return FeatureResult(
            name=plan.name,
            branch=plan.worktree.branch,
            stage=append_final_gate("fast path 実装中", frontmatter),
            progress=Progress(kind="not_applicable", note="fast path"),
            pr_status=pr_status,
            degradation=None,
            frontmatter=frontmatter,
        )
    if not approved(frontmatter):
        review_round = number_display(frontmatter.plan_review_round)
        return FeatureResult(
            name=plan.name,
            branch=plan.worktree.branch,
            stage=append_final_gate(
                f"計画段階(計画レビュー周回 {review_round} 周・承認待ち)", frontmatter
            ),
            progress=Progress(kind="not_applicable", note="計画段階"),
            pr_status=pr_status,
            degradation=None,
            frontmatter=frontmatter,
        )

    base = get_merge_base(plan)
    if base is None:
        return git_failure_result(plan)
    rejection = has_unresolved_rejection(plan, base)
    if rejection is None:
        return git_failure_result(plan)
    if rejection:
        progress = derive_progress(plan, base)
        if progress.kind == "git_error":
            return git_failure_result(plan)
        if is_approval_history_failure(progress):
            return approval_history_failure_result(plan, frontmatter, pr_status)
        return FeatureResult(
            name=plan.name,
            branch=plan.worktree.branch,
            stage=append_final_gate("実装中(差し戻し修正)", frontmatter),
            progress=progress,
            pr_status=pr_status,
            degradation=None,
            frontmatter=frontmatter,
        )
    progress = derive_progress(plan, base)
    if progress.kind == "git_error":
        return git_failure_result(plan)
    if is_approval_history_failure(progress):
        return approval_history_failure_result(plan, frontmatter, pr_status)
    if progress.kind == "unknown":
        stage = "実装状況: 不明"
    elif progress.kind == "inconsistent":
        stage = "実装状況: 不整合(要確認)"
    elif progress.completed == 0:
        stage = f"実装前(全 {progress.total} ステップ)"
        if progress.note:
            stage = f"{stage}({progress.note})"
    elif progress.completed is not None and progress.total is not None and progress.completed < progress.total:
        stage = f"実装中(ステップ {progress.completed}/{progress.total} 完了)"
    else:
        stage = "実装完了・/pr 前"
    return FeatureResult(
        name=plan.name,
        branch=plan.worktree.branch,
        stage=append_final_gate(stage, frontmatter),
        progress=progress,
        pr_status=pr_status,
        degradation=None,
        frontmatter=frontmatter,
    )


def parse_failure_result(name: str, branch: str | None) -> FeatureResult:
    """frontmatter 解析失敗を表示用結果へ変換する。

    Args:
        name: feature ディレクトリ名。
        branch: worktree の実ブランチ名。

    Returns:
        解析失敗を明示した feature 結果。
    """
    return FeatureResult(
        name=name,
        branch=branch,
        stage="未取得(frontmatter 解析失敗)",
        progress=Progress(kind="not_applicable", note="frontmatter 解析失敗"),
        pr_status="未取得",
        degradation="frontmatter 解析失敗",
        frontmatter=None,
    )


def expected_feature_slug(branch: str | None) -> str | None:
    """feature/fix ブランチ名から対応 plan の期待 slug を取り出す。

    Args:
        branch: worktree の実ブランチ名。

    Returns:
        feature/<slug> または fix/<slug> の slug。対象外のブランチでは None。
    """
    if branch is None:
        return None
    prefix, separator, slug = branch.partition("/")
    if prefix not in {"feature", "fix"} or not separator or not slug or "/" in slug:
        return None
    return slug


def worktree_resolution_failure_result(
    name: str,
    branch: str,
    reason: str,
) -> FeatureResult:
    """worktree と plan の対応を解決できない結果を組み立てる。

    Args:
        name: 表示用の feature 名またはブランチ名。
        branch: worktree の実ブランチ名。
        reason: plan 不在、branch 不整合、plan 重複のいずれかの理由。

    Returns:
        対応解決失敗を明示した表示用結果。
    """
    return FeatureResult(
        name=name,
        branch=branch,
        stage=f"未取得({reason})",
        progress=Progress(kind="not_applicable", note=reason),
        pr_status="未取得",
        degradation=reason,
        frontmatter=None,
    )


def collect_features(
    cwd: Path,
    output_format: str = "text",
) -> tuple[list[FeatureResult], bool]:
    """全 worktree の対象 plan を列挙し、表示結果を導出する。

    Args:
        cwd: worktree 列挙の基準ディレクトリ。
        output_format: ``text`` のときだけ PR 状態を gh から取得する。

    Returns:
        feature 結果一覧と、worktree 列挙が成功したかの組。
    """
    worktrees, listed = list_worktrees(cwd)
    if not listed:
        return [], False

    results: list[FeatureResult] = []
    notion_cache: dict[Path, NotionTransitions | None] = {}
    for worktree in worktrees:
        if worktree.branch in PROTECTED_BRANCHES:
            continue
        feature_root = worktree.path / "docs" / "features"
        try:
            plans = sorted(feature_root.glob("*/plan.md"))
        except Exception:
            continue
        parsed_plans: dict[Path, Frontmatter] = {}
        parse_failed_paths: set[Path] = set()
        for plan_path in plans:
            frontmatter = read_frontmatter(plan_path)
            if frontmatter is None:
                results.append(parse_failure_result(plan_path.parent.name, worktree.branch))
                parse_failed_paths.add(plan_path)
                continue
            parsed_plans[plan_path] = frontmatter

        expected_slug = expected_feature_slug(worktree.branch)
        if expected_slug is None or worktree.branch is None:
            continue

        expected_plan_path = feature_root / expected_slug / "plan.md"
        misplaced_matching_plans = [
            (plan_path, frontmatter)
            for plan_path, frontmatter in parsed_plans.items()
            if plan_path != expected_plan_path and frontmatter.branch == worktree.branch
        ]
        if misplaced_matching_plans:
            results.append(
                worktree_resolution_failure_result(
                    expected_slug,
                    worktree.branch,
                    "plan 重複",
                )
            )
            continue

        frontmatter = parsed_plans.get(expected_plan_path)
        plan_path: Path | None = None

        if expected_plan_path in parse_failed_paths:
            # 期待 plan 自身の解析失敗は、走査時に既に顕在化している。
            pass
        elif frontmatter is None:
            results.append(
                worktree_resolution_failure_result(
                    worktree.branch,
                    worktree.branch,
                    "plan 不在",
                )
            )
        elif frontmatter.branch != worktree.branch:
            results.append(
                worktree_resolution_failure_result(
                    expected_slug,
                    worktree.branch,
                    "branch 不整合",
                )
            )
        else:
            plan_path = expected_plan_path

        if plan_path is None or frontmatter is None:
            continue
        try:
            relative_plan_path = plan_path.relative_to(worktree.path).as_posix()
            feature_plan = FeaturePlan(
                name=plan_path.parent.name,
                plan_path=plan_path,
                relative_plan_path=relative_plan_path,
                worktree=worktree,
                frontmatter=frontmatter,
            )
            result = derive_feature(
                feature_plan,
                resolve_pr=output_format == "text",
            )
            if output_format == "text":
                result = replace(
                    result,
                    notion_expectation=get_notion_expectation(
                        result,
                        feature_plan,
                        notion_cache,
                    ),
                )
            results.append(result)
        except Exception:
            results.append(
                FeatureResult(
                    name=plan_path.parent.name,
                    branch=worktree.branch,
                    stage="未取得(導出失敗)",
                    progress=Progress(kind="not_applicable", note="導出失敗"),
                    pr_status="未取得",
                    degradation="導出失敗",
                    frontmatter=frontmatter,
                )
            )
    return results, True


def format_progress(progress: Progress) -> str:
    """ステップ進捗を人間向けの短い表示へ変換する。

    Args:
        progress: 表示対象の進捗。

    Returns:
        text/hook で共有する進捗表示。
    """
    if progress.kind == "known":
        display = f"{progress.completed}/{progress.total}"
        return f"{display}({progress.note})" if progress.note else display
    if progress.kind == "unknown":
        return f"不明({progress.note})" if progress.note else "不明"
    if progress.kind == "inconsistent":
        return "不整合(要確認)"
    if progress.kind == "git_error":
        return "未取得(git 失敗)"
    if (
        progress.kind == "not_applicable"
        and progress.note == APPROVAL_HISTORY_ERROR_NOTE
    ):
        return f"未取得({progress.note})"
    return f"未判定({progress.note or '対象外'})"


def format_text_result(result: FeatureResult) -> str:
    """1 feature の text 形式表示を組み立てる。

    Args:
        result: 表示対象 feature の導出結果。

    Returns:
        複数行の text 形式表示。
    """
    branch = result.branch or "未取得"
    lines = [
        f"feature: {result.name} ({branch})",
        f"  段階: {result.stage}",
        f"  ステップ進捗: {format_progress(result.progress)}",
        f"  PR 状態: {result.pr_status}",
    ]
    if result.frontmatter is not None:
        lines.extend(
            [
                f"  計画レビュー周回: {number_display(result.frontmatter.plan_review_round)}",
                f"  確定ゲート周回: {number_display(result.frontmatter.final_gate_round)}",
                "  実行方式: "
                + (
                    result.frontmatter.execution_mode
                    if result.frontmatter.execution_mode_valid
                    else "不正値"
                ),
            ]
        )
    if result.notion_expectation is not None:
        lines.append(
            "  Notion 期待: "
            f"{result.notion_expectation}(実値の照合は対話セッションで)"
        )
    if result.degradation is not None:
        lines.append(f"  縮退: {result.degradation}")
    return "\n".join(lines)


def format_hook_result(result: FeatureResult) -> str:
    """1 feature の hook 形式表示を 1 行で組み立てる。

    Args:
        result: 表示対象 feature の導出結果。

    Returns:
        SessionStart 注入に使える 1 行要約。
    """
    branch = result.branch or "未取得"
    parts = [
        f"{result.name}({branch})",
        result.stage,
        f"ステップ {format_progress(result.progress)}",
        f"PR 状態: {result.pr_status}",
    ]
    if result.frontmatter is not None:
        if result.frontmatter.plan_review_round is None:
            parts.append("計画レビュー周回 不正値")
        if result.frontmatter.final_gate_round is None:
            parts.append("確定ゲート周回 不正値")
    if result.degradation is not None:
        parts.append(f"縮退: {result.degradation}")
    return " / ".join(parts)


def render(results: list[FeatureResult], listed: bool, output_format: str) -> str:
    """列挙結果全体を指定形式で表示文字列へ変換する。

    Args:
        results: feature ごとの導出結果。
        listed: worktree 列挙が成功したか。
        output_format: ``text`` または ``hook``。

    Returns:
        標準出力へ送る文字列。
    """
    if not listed:
        return "進行中 feature: 未取得(worktree 列挙失敗)"
    if output_format == "hook":
        return "\n".join(format_hook_result(result) for result in results)
    if not results:
        return "進行中 feature: なし"
    return "\n\n".join(format_text_result(result) for result in results)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace | None:
    """CLI 引数を fail-open で解析する。

    Args:
        argv: ``None`` ならプロセス引数、それ以外はテスト用引数列。

    Returns:
        解析済み引数。不正な引数形式なら ``None``。
    """
    parser = argparse.ArgumentParser(description="feature の現在地を導出して表示する")
    parser.add_argument("--format", dest="output_format", default="text")
    parser.add_argument("--cwd", default=".")
    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        return None
    if parsed.output_format not in {"text", "hook"}:
        return None
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """CLI を実行し、失敗時も常に終了コード 0 を返す。

    Args:
        argv: ``None`` ならプロセス引数、それ以外はテスト用引数列。

    Returns:
        常に 0。
    """
    try:
        parsed = parse_args(argv)
        if parsed is None:
            print("進行中 feature: 未取得(引数不正)")
            return 0
        results, listed = collect_features(Path(parsed.cwd), parsed.output_format)
        rendered = render(results, listed, parsed.output_format)
        if rendered:
            print(rendered)
    except Exception:
        print("進行中 feature: 未取得(導出失敗)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
