"""計画書の正本文書宣言と Git 差分を双方向で突合する。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

try:
    from core_guard import GuardError
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読み込む場合だけ通る。
    from scripts.core_guard import GuardError


DIFF_TIMEOUT_SECONDS = 30
INDEX_RELATIVE_PATH = "docs/README.md"
EXCLUDED_PREFIXES = (
    ("docs", "features"),
    ("docs", "worklog"),
    ("docs", "legacy"),
    ("docs", "development", "templates"),
    (".claude",),
)
EXCLUDED_ROOT_FILES = frozenset({"AGENTS.md", "CLAUDE.md", "README.md"})
BRANCH_RE = re.compile(r"^(?:feature|fix)/(?P<slug>[^/]+)$")
HEADING_RE = re.compile(r"^#{1,6}\s")
SECTION_HEADING_RE = re.compile(r"^##\s")
STATUS_PREFIX_RE = re.compile(r"^status\s*:")
STATUS_LINE_RE = re.compile(r"^status:\s*(active|in-review)(?:\s+#.*)?$")
MARKDOWN_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)"
)


@dataclass(frozen=True)
class ChangedPath:
    """Git が報告した 1 件の変更種別とパス群を表す。

    Attributes:
        status: ``A``・``M``・``D``・``R`` などの変更種別。
        paths: 変更対象パス。改名・コピーでは旧パスと新パスをこの順に持つ。
    """

    status: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Declarations:
    """計画書 3 節から抽出した文書宣言を表す。

    Attributes:
        reflected: 反映すると宣言したリポジトリ相対パス。
        no_change: ``反映なし`` と宣言したリポジトリ相対パス。
    """

    reflected: frozenset[str]
    no_change: frozenset[str]


@dataclass(frozen=True)
class CheckResult:
    """突合で得た違反と警告を表す。

    Attributes:
        violations: exit 1 にする違反メッセージ。
        warnings: exit 0 のまま表示する警告メッセージ。
    """

    violations: tuple[str, ...]
    warnings: tuple[str, ...]


def violation(path: str, reason: str) -> str:
    """所定形式の違反・警告メッセージを作る。

    Args:
        path: リポジトリ相対パス。
        reason: 表示する理由。

    Returns:
        ``パス: 理由`` 形式のメッセージ。
    """
    return f"{path}: {reason}"


def is_excluded(path: str) -> bool:
    """突合対象から除外するパスかを判定する。

    Args:
        path: リポジトリ相対の POSIX 形式パス。

    Returns:
        除外対象なら ``True``、それ以外なら ``False``。
    """
    parts = PurePosixPath(path).parts
    if len(parts) == 1 and parts[0] in EXCLUDED_ROOT_FILES:
        return True
    return any(parts[: len(prefix)] == prefix for prefix in EXCLUDED_PREFIXES)


def normalize_repository_path(path: Path, root: Path) -> str | None:
    """パスをリポジトリ配下の POSIX 形式へ正規化する。

    Args:
        path: 正規化対象の絶対または相対パス。
        root: リポジトリルート。

    Returns:
        リポジトリ配下なら相対 POSIX パス、配下でなければ ``None``。
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def normalize_git_path(path: str, root: Path) -> str:
    """Git が返したパスを安全にリポジトリ相対パスへ変換する。

    Args:
        path: Git の ``--name-status`` 出力にあるパス。
        root: リポジトリルート。

    Returns:
        正規化済みのリポジトリ相対 POSIX パス。

    Raises:
        GuardError: 空、絶対、またはリポジトリ外のパスの場合。
    """
    raw_path = Path(path)
    if not path or raw_path.is_absolute():
        raise GuardError("git diff が不正なパスを返した")
    normalized = normalize_repository_path(root / raw_path, root)
    if normalized is None:
        raise GuardError("git diff がリポジトリ外のパスを返した")
    return normalized


def parse_name_status(output: str, root: Path) -> tuple[ChangedPath, ...]:
    """``git diff --name-status`` の出力を変更種別つきで解析する。

    Args:
        output: Git の標準出力。
        root: リポジトリルート。

    Returns:
        解析済み変更レコード。

    Raises:
        GuardError: 出力の行形式や変更種別が不正な場合。
    """
    changes: list[ChangedPath] = []
    for line in output.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        status = fields[0]
        kind = status[:1]
        if kind not in {"A", "C", "D", "M", "R", "T", "U", "X", "B"}:
            raise GuardError("git diff が不正な変更種別を返した")

        expected_paths = 2 if kind in {"C", "R"} else 1
        if len(fields) != expected_paths + 1:
            raise GuardError("git diff の --name-status 出力が不正")
        paths = tuple(normalize_git_path(path, root) for path in fields[1:])
        changes.append(ChangedPath(status=kind, paths=paths))
    return tuple(changes)


def changed_paths(root: Path, base: str, head: str) -> tuple[ChangedPath, ...]:
    """base...head の変更種別つきパスを Git から取得する。

    Args:
        root: Git リポジトリのルート。
        base: 比較元の Git revision。
        head: 比較先の Git revision。

    Returns:
        Git が報告した変更レコード。

    Raises:
        GuardError: git diff の起動、タイムアウト、実行、または出力解析に失敗した場合。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "--find-renames", f"{base}...{head}"],
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
    return parse_name_status(result.stdout, root)


def git_show(root: Path, revision: str, path: str) -> str:
    """指定 revision のファイル内容を Git から取得する。

    Args:
        root: Git リポジトリのルート。
        revision: 取得元の Git revision。
        path: リポジトリ相対ファイルパス。

    Returns:
        指定ファイルの UTF-8 テキスト。

    Raises:
        GuardError: git show の起動、タイムアウト、または実行に失敗した場合。
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError("git show がタイムアウトした") from error
    except OSError as error:
        raise GuardError(f"git show を起動できない: {error}") from error
    if result.returncode != 0:
        raise GuardError(f"git show に失敗した: {revision}:{path}")
    return result.stdout


def current_branch(root: Path) -> str:
    """現在の Git ブランチ名を取得する。

    Args:
        root: Git リポジトリのルート。

    Returns:
        detached HEAD でない現在のブランチ名。

    Raises:
        GuardError: Git の実行に失敗した、または detached HEAD の場合。
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError("git branch がタイムアウトした") from error
    except OSError as error:
        raise GuardError(f"git branch を起動できない: {error}") from error
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        raise GuardError("現在のブランチ名を取得できない")
    return branch


def derive_plan_path(root: Path) -> Path:
    """feature/fix ブランチ名から feature 計画書のパスを導出する。

    Args:
        root: Git リポジトリのルート。

    Returns:
        導出した plan.md の絶対パス。

    Raises:
        GuardError: ブランチ名が feature/fix の規約に合わない場合。
    """
    branch = current_branch(root)
    match = BRANCH_RE.fullmatch(branch)
    if match is None:
        raise GuardError("--plan を省略したがブランチ名から計画書を導出できない")
    return root / "docs" / "features" / match.group("slug") / "plan.md"


def resolve_plan_path(root: Path, plan: Path | None) -> Path:
    """明示指定またはブランチ名から計画書の絶対パスを得る。

    Args:
        root: リポジトリルート。
        plan: ``--plan`` の値。省略時は ``None``。

    Returns:
        リポジトリ配下にある plan.md の絶対パス。

    Raises:
        GuardError: 指定パスがリポジトリ外の場合。
    """
    path = derive_plan_path(root) if plan is None else plan
    if not path.is_absolute():
        path = root / path
    normalized = normalize_repository_path(path, root)
    if normalized is None:
        raise GuardError("計画書がリポジトリ外にある")
    return root / normalized


def read_plan(path: Path) -> str:
    """UTF-8 の計画書を読み込む。

    Args:
        path: 読み込む計画書のパス。

    Returns:
        計画書全文。

    Raises:
        GuardError: 読み込みまたは UTF-8 復号に失敗した場合。
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise GuardError(f"計画書を読み込めない: {error}") from error
    except UnicodeDecodeError as error:
        raise GuardError("計画書が UTF-8 ではない") from error


def parse_plan_status(plan_text: str) -> str:
    """計画書 frontmatter の status を厳密に取得する。

    Args:
        plan_text: 計画書全文。

    Returns:
        ``active`` または ``in-review`` の status。

    Raises:
        GuardError: frontmatter または status が不正な場合。
    """
    lines = plan_text.splitlines()
    if not lines or lines[0] != "---":
        raise GuardError("計画書の frontmatter がない")
    try:
        end = next(
            index for index, line in enumerate(lines[1:], start=1) if line == "---"
        )
    except StopIteration as error:
        raise GuardError("計画書の frontmatter 終端がない") from error

    status_lines = [line for line in lines[1:end] if STATUS_PREFIX_RE.match(line)]
    if len(status_lines) != 1:
        raise GuardError("計画書の status 行がちょうど 1 行ではない")
    match = STATUS_LINE_RE.fullmatch(status_lines[0])
    if match is None:
        raise GuardError("計画書の status 行が不正")
    return match.group(1)


def affected_section_lines(plan_text: str) -> list[str]:
    """計画書の「影響する正本」節に含まれる行を取得する。

    Args:
        plan_text: 計画書全文。

    Returns:
        見出し自身を除く、対象節内の行。

    Raises:
        GuardError: 対象節が存在しない場合。
    """
    lines = plan_text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if HEADING_RE.match(line) and "影響する正本" in line
        ),
        None,
    )
    if start is None:
        raise GuardError("計画書に「影響する正本」節がない")

    section: list[str] = []
    for line in lines[start + 1 :]:
        if SECTION_HEADING_RE.match(line):
            break
        section.append(line)
    return section


def local_markdown_path(raw_target: str, base: Path, root: Path) -> str | None:
    """ローカル Markdown のリンク先をリポジトリ相対パスへ解決する。

    Args:
        raw_target: Markdown リンクまたはコード span 内のパス。
        base: 相対パスを解決する基準ディレクトリ。
        root: リポジトリルート。

    Returns:
        リポジトリ配下の Markdown パス。対象外なら ``None``。
    """
    target = raw_target.strip().strip("<>").split("#", 1)[0]
    target_path = Path(target)
    if (
        not target
        or "://" in target
        or target_path.is_absolute()
        or target_path.suffix != ".md"
    ):
        return None
    return normalize_repository_path(base / target_path, root)


def markdown_link_paths(line: str, base: Path, root: Path) -> set[str]:
    """1 行にある Markdown リンクからローカル Markdown パスを全件抽出する。

    Args:
        line: 解析対象の 1 行。
        base: リンク先を解決する基準ディレクトリ。
        root: リポジトリルート。

    Returns:
        抽出・解決できたリポジトリ相対パスの集合。
    """
    paths: set[str] = set()
    for match in MARKDOWN_LINK_RE.finditer(line):
        path = local_markdown_path(match.group("target"), base, root)
        if path is not None:
            paths.add(path)
    return paths


def backtick_paths(line: str, root: Path) -> set[str]:
    """1 行のコード span からリポジトリ相対 Markdown パスを全件抽出する。

    Args:
        line: 解析対象の 1 行。
        root: リポジトリルート。

    Returns:
        抽出・解決できたリポジトリ相対パスの集合。
    """
    paths: set[str] = set()
    for raw_target in re.findall(r"`([^`]+)`", line):
        path = local_markdown_path(raw_target, root, root)
        if path is not None:
            paths.add(path)
    return paths


def extract_declarations(plan_text: str, plan_path: Path, root: Path) -> Declarations:
    """計画書 3 節から反映・非該当の文書宣言を抽出する。

    同一文書が両方に現れる場合は、反映宣言を優先する。

    Args:
        plan_text: 計画書全文。
        plan_path: 計画書の絶対パス。
        root: リポジトリルート。

    Returns:
        反映・非該当のパス集合。

    Raises:
        GuardError: 「影響する正本」節がない場合。
    """
    reflected: set[str] = set()
    no_change: set[str] = set()
    for line in affected_section_lines(plan_text):
        paths = markdown_link_paths(line, plan_path.parent, root)
        paths.update(backtick_paths(line, root))
        if "反映なし" in line:
            no_change.update(paths)
        else:
            reflected.update(paths)
    no_change.difference_update(reflected)
    return Declarations(frozenset(reflected), frozenset(no_change))


def parse_table_cells(line: str) -> list[str]:
    """Markdown 表の 1 行をセル配列へ分割する。

    Args:
        line: ``|`` で始まる Markdown 表の行。

    Returns:
        前後空白を除去したセル配列。
    """
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(cells: Sequence[str]) -> bool:
    """Markdown 表の区切り行かを判定する。

    Args:
        cells: 表のセル配列。

    Returns:
        区切り行なら ``True``、それ以外なら ``False``。
    """
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells
    )


def primary_table_lines(index_text: str) -> list[str]:
    """索引の「正本」見出し配下にある最初の Markdown 表を取得する。

    Args:
        index_text: docs/README.md の全文。

    Returns:
        見つけた表の行配列。

    Raises:
        GuardError: 「正本」見出しまたは表がない場合。
    """
    lines = index_text.splitlines()
    start = next(
        (index + 1 for index, line in enumerate(lines) if line == "## 正本"),
        None,
    )
    if start is None:
        raise GuardError("docs/README.md に「## 正本」見出しがない")

    table_start: int | None = None
    for index in range(start, len(lines)):
        line = lines[index]
        if SECTION_HEADING_RE.match(line):
            break
        if line.lstrip().startswith("|"):
            table_start = index
            break
    if table_start is None:
        raise GuardError("docs/README.md の「## 正本」配下に Markdown 表がない")

    table: list[str] = []
    for line in lines[table_start:]:
        if not line.lstrip().startswith("|"):
            break
        table.append(line)
    if not table:
        raise GuardError("docs/README.md の正本一覧の表が空")
    return table


def indexed_paths(index_text: str, root: Path) -> frozenset[str]:
    """索引スナップショットの掲載正本を抽出する。

    Args:
        index_text: docs/README.md の全文。
        root: リポジトリルート。

    Returns:
        除外済みの掲載正本パス集合。

    Raises:
        GuardError: 索引表の構造または文書リンクが不正な場合。
    """
    table = primary_table_lines(index_text)
    header = parse_table_cells(table[0])
    try:
        document_column = header.index("文書")
    except ValueError as error:
        raise GuardError("docs/README.md の正本一覧に「文書」列がない") from error

    paths: set[str] = set()
    for line in table[1:]:
        cells = parse_table_cells(line)
        if is_table_separator(cells):
            continue
        if len(cells) <= document_column:
            raise GuardError("docs/README.md の正本一覧の行に文書列がない")
        row_paths = markdown_link_paths(cells[document_column], root / "docs", root)
        if not row_paths:
            raise GuardError(
                "docs/README.md の正本一覧の文書列にローカル .md リンクがない"
            )
        paths.update(path for path in row_paths if not is_excluded(path))
    return frozenset(paths)


def filesystem_paths(root: Path) -> frozenset[str]:
    """HEAD のファイルシステムにある非除外 Markdown パスを取得する。

    Args:
        root: リポジトリルート。

    Returns:
        ``docs/**/*.md`` にある非除外のリポジトリ相対パス集合。
    """
    paths: set[str] = set()
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        return frozenset()
    for path in docs_dir.glob("**/*.md"):
        if not path.is_file():
            continue
        normalized = normalize_repository_path(path, root)
        if normalized is not None and not is_excluded(normalized):
            paths.add(normalized)
    return frozenset(paths)


def target_paths(root: Path, base: str, head: str) -> frozenset[str]:
    """宣言突合の対象となる文書集合を構築する。

    Args:
        root: リポジトリルート。
        base: 比較元の Git revision。
        head: 比較先の Git revision。

    Returns:
        索引自身、base/HEAD 索引、HEAD FS の和集合。

    Raises:
        GuardError: base/HEAD 側索引を Git から取得または解析できない場合。
    """
    paths = {INDEX_RELATIVE_PATH}
    paths.update(indexed_paths(git_show(root, base, INDEX_RELATIVE_PATH), root))
    paths.update(indexed_paths(git_show(root, head, INDEX_RELATIVE_PATH), root))
    paths.update(filesystem_paths(root))
    return frozenset(path for path in paths if not is_excluded(path))


def check_sync(
    changes: Sequence[ChangedPath],
    targets: frozenset[str],
    declarations: Declarations,
    plan_status: str,
) -> CheckResult:
    """対象差分と計画書宣言を双方向で突合する。

    Args:
        changes: Git が報告した変更種別つきパス。
        targets: 突合対象の文書集合。
        declarations: 計画書 3 節の宣言。
        plan_status: 計画書 frontmatter の status。

    Returns:
        exit 判定に使う違反・警告。
    """
    changed = frozenset(
        path for change in changes for path in change.paths if path in targets
    )
    reflected = declarations.reflected & targets
    no_change = declarations.no_change & targets

    violations: list[str] = []
    for path in sorted(changed):
        if path in reflected:
            continue
        if path in no_change:
            violations.append(violation(path, "計画書 3 節で「反映なし」と宣言されている"))
        else:
            violations.append(violation(path, "計画書 3 節に宣言がない"))

    declared_without_change = reflected - changed
    if plan_status == "in-review":
        violations.extend(
            violation(path, "計画書 3 節で反映すると宣言したが差分にない")
            for path in sorted(declared_without_change)
        )
        return CheckResult(tuple(violations), ())

    warnings = tuple(
        violation(
            path,
            "計画書 3 節で反映すると宣言したが差分にない(作業中のため警告)",
        )
        for path in sorted(declared_without_change)
    )
    return CheckResult(tuple(violations), warnings)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        解釈済みのコマンドライン引数。
    """
    parser = argparse.ArgumentParser(description="計画書の正本文書宣言と Git 差分を突合する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help="計画書パス(省略時は feature/fix ブランチ名から導出)",
    )
    parser.add_argument(
        "--base",
        default="origin/develop",
        help="比較元(既定: origin/develop)",
    )
    parser.add_argument("--head", default="HEAD", help="比較先(既定: HEAD)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """計画書の正本文書宣言と差分の双方向突合を実行する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        違反なしなら 0、違反または検査不能なら 1。
    """
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        plan_path = resolve_plan_path(root, args.plan)
        plan_text = read_plan(plan_path)
        plan_status = parse_plan_status(plan_text)
        declarations = extract_declarations(plan_text, plan_path, root)
        changes = changed_paths(root, args.base, args.head)
        targets = target_paths(root, args.base, args.head)
    except GuardError as error:
        print(f"check_plan_docs_sync: {error}", file=sys.stderr)
        return 1

    result = check_sync(changes, targets, declarations, plan_status)
    for message in result.warnings:
        print(message, file=sys.stderr)
    for message in result.violations:
        print(message, file=sys.stderr)
    return 1 if result.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
