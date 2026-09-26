"""Codex 実行の唯一の許可経路(設計書 12.1 / 敵対レビュー P0-2 対応)。

生の `codex exec` は codex_guard フックが遮断する。本ラッパーが
計画書の plan status(implement / fast の active 必須)と承認状態・実行場所(worktree)・sandbox・
ADR-001 v1.1 のモデル対応表を検証・固定する。

使い方:
  python .claude/scripts/codex_run.py implement <plan.md> [--resume] [-]   # 実装(status: active かつ承認済み計画書必須)
  python .claude/scripts/codex_run.py fast [-]                             # 軽微 fast path(6.1。人間の事前OK前提)
  python .claude/scripts/codex_run.py research [--deep] [-]                # Web調査(read-only + live search)
  python .claude/scripts/codex_run.py review <normal|adversarial> [-]      # レビュー(read-only。差分指定はプロンプトに書く)
  python .claude/scripts/codex_run.py probe                                 # 対応表の全組を read-only で受理確認

プロンプトは末尾引数 `-` で stdin から渡す(クォート事故防止)。
ネットワーク有効化は PITCHLOG_ALLOW_NET=1 + PITCHLOG_NET_REASON="理由"(必須 — 人間へ報告済みであること)。
sandbox 安全キーは毎回 CLI で明示上書きし、config 層の値に依存しない(2周目 P0 対応)。
"""
import enum
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ADR-001 v1.1 モデル対応表(明示 ID 固定)
MODEL_MAP = {
    "軽微": ("gpt-6-sol", "medium"),
    "通常": ("gpt-6-sol", "max"),
    "コア領域": ("gpt-6-sol", "xhigh"),
    "機械的軽作業": ("gpt-6-luna", "xhigh"),
}
RESEARCH = ("gpt-6-sol", "high")
RESEARCH_DEEP = ("gpt-6-sol", "xhigh")
REVIEW_NORMAL = ("gpt-6-sol", "max")
REVIEW_ADVERSARIAL = ("gpt-6-sol", "xhigh")

WORKTREES_DIRNAME = "pitchlog-worktrees"
FRONTMATTER_LIMIT = 8 * 1024
MINIMUM_CODEX_VERSION = (0, 157, 0)
PROBE_PROMPT = "ツールを使わず OK とだけ返答してください。"

# `codex_run.py` ↔ `scripts/feature_status.py:301-307` の相互参照:
# status 判定は同じ手順・正規表現リテラルを維持する。両スクリプトの独立性のため import は共有しない。
STATUS_CANDIDATE_RE = re.compile(r"^status\s*:")
STATUS_LINE_RE = re.compile(r"^status:\s*(active|in-review)(?:\s+#.*)?$")
CODEX_VERSION_LINE_RE = re.compile(
    r"^codex(?:-cli)?[ \t]+v?(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.(?P<patch>[0-9]+)(?:[ \t].*)?$"
)
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
        "反映周コミット",
    }
)
HEADING_RE = re.compile(r"^[ \t]{0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
HEADING_NUMBER_RE = re.compile(
    r"^(?:(?:\(\s*\d+(?:[-.]\d+)*\s*\)|（\s*\d+(?:[-.]\d+)*\s*）)"
    r"|(?:\d+(?:[-.]\d+)*[.)．、]))\s*"
)
TRAILING_PARENTHETICAL_RE = re.compile(r"\s*(?:\([^()]*\)|（[^（）]*）)\s*$")
STEP_ROW_RE = re.compile(r"^\s*\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|")
FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


class StepTableStatus(enum.Enum):
    """計画書の実装ステップ表の検出状態。"""

    OK = "ok"
    NO_TABLE = "no-table"
    NO_FILLED_ROW = "no-filled-row"
    TABLE_OUTSIDE_SCOPE = "table-outside-scope"
    TABLE_IN_FENCED_CODE = "table-in-fenced-code"


def die(msg: str) -> None:
    print(f"codex_run: エラー: {msg}", file=sys.stderr)
    sys.exit(2)


def read_prompt(args: list[str]) -> str:
    if args and args[-1] == "-":
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む
        return sys.stdin.buffer.read().decode("utf-8", "replace")
    die("プロンプトは stdin で渡す(末尾引数に `-` を指定)")
    return ""


def _is_step_heading(heading_text: str) -> bool:
    """正規化した見出しが実装ステップ見出しかを返す。"""
    normalized = re.sub(r"[*_]+", "", heading_text).strip()
    normalized = HEADING_NUMBER_RE.sub("", normalized, count=1)
    normalized = TRAILING_PARENTHETICAL_RE.sub("", normalized, count=1).strip()
    prefix = "実装ステップ"
    if not normalized.startswith(prefix):
        return False
    suffix = normalized[len(prefix) :].lstrip()
    return re.match(r"^(?:では(?:ない|ありません)|でない|じゃない)", suffix) is None


def _step_table_analysis(plan_text: str) -> tuple[StepTableStatus, str | None]:
    """ステップ表の状態とスコープ外の表を含む見出しを返す。

    Args:
        plan_text: 検査対象の計画書本文。

    Returns:
        ステップ表の状態と、スコープ外の記入済み行を含む見出し。該当する
        見出しがない場合、または状態がスコープ外でない場合は ``None``。
    """
    heading_stack: list[tuple[int, str, bool]] = []
    fence_character: str | None = None
    fence_length = 0
    has_table = False
    has_filled_in_scope = False
    has_filled_outside_scope = False
    has_filled_in_fence = False
    outside_heading: str | None = None

    for line in plan_text.splitlines():
        if fence_character is not None:
            stripped = line.lstrip(" \t")
            if re.fullmatch(
                rf"{re.escape(fence_character)}{{{fence_length},}}[ \t]*", stripped
            ):
                fence_character = None
                fence_length = 0
                continue
            row_match = STEP_ROW_RE.match(line)
            if row_match and row_match.group(2).strip() and row_match.group(3).strip():
                has_filled_in_fence = True
            continue

        fence_match = FENCE_OPEN_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            fence_character = fence[0]
            fence_length = len(fence)
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = re.sub(
                r"[ \t]+#+[ \t]*$", "", heading_match.group(2) or ""
            ).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text, _is_step_heading(heading_text)))
            continue

        row_match = STEP_ROW_RE.match(line)
        if row_match is None:
            continue
        has_table = True
        if not row_match.group(2).strip() or not row_match.group(3).strip():
            continue
        if any(is_step_heading for _, _, is_step_heading in heading_stack):
            has_filled_in_scope = True
        else:
            has_filled_outside_scope = True
            if outside_heading is None and heading_stack:
                outside_heading = heading_stack[-1][1]

    if has_filled_in_scope:
        return StepTableStatus.OK, None
    if has_filled_in_fence and not has_filled_outside_scope:
        return StepTableStatus.TABLE_IN_FENCED_CODE, None
    if has_filled_outside_scope:
        return StepTableStatus.TABLE_OUTSIDE_SCOPE, outside_heading
    if has_table:
        return StepTableStatus.NO_FILLED_ROW, None
    return StepTableStatus.NO_TABLE, None


def step_table_status(plan_text: str) -> StepTableStatus:
    """計画書の実装ステップ表の検出状態を返す。

    Args:
        plan_text: 検査対象の計画書本文。

    Returns:
        見出しスコープ、記入状況、fenced code を考慮した検出状態。
    """
    return _step_table_analysis(plan_text)[0]


def has_filled_step_row(plan_text: str) -> bool:
    """実装ステップ見出し配下に全セル記入済みの行があるかを返す。

    Args:
        plan_text: 検査対象の計画書本文。

    Returns:
        番号・ステップ内容・合格条件の3セルがすべて非空なら ``True``。
        別の見出し配下や fenced code 内の数値表では ``False``。
    """
    return step_table_status(plan_text) is StepTableStatus.OK


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """完全一致デリミタの frontmatter を辞書と本文として返す。

    Args:
        path: 解析対象の計画書。

    Returns:
        frontmatter のキー・値辞書と、開閉デリミタを除いた本文。
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        die(f"計画書 {path} に frontmatter がない")
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    except StopIteration:
        die(f"計画書 {path} に frontmatter がない")

    body = "\n".join(lines[1:end])
    fm: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.split("#")[0].strip()
    return fm, body


def require_active_plan_status(frontmatter_body: str) -> None:
    """実装前に計画書の status が active であることを確認する。"""
    status_lines = [
        line for line in frontmatter_body.splitlines() if STATUS_CANDIDATE_RE.match(line)
    ]
    if len(status_lines) != 1:
        detail = "欠落" if not status_lines else f"重複: {' / '.join(status_lines)}"
        die(
            f"計画書の status 行が不正({detail})。"
            "status: <active|in-review> をちょうど 1 行にする(設計書 7.1-5)"
        )

    status_match = STATUS_LINE_RE.fullmatch(status_lines[0])
    if status_match is None:
        die(
            f"計画書の status 行が不正({status_lines[0]})。"
            "status: <active|in-review> をちょうど 1 行にする(設計書 7.1-5)"
        )
    if status_match.group(1) != "active":
        die(
            "計画書が in-review(PR 段階)。修正の再開は先に plan frontmatter を "
            "status: active に戻す — /pr の差し戻し手順(設計書 6.1 差し戻しの往復)"
        )


def parse_fast_frontmatter_body(body: str) -> dict[str, str] | None:
    """fast 用 frontmatter 本文を feature_status.py と同じ規則で解析する。

    Args:
        body: 開閉デリミタを除いた frontmatter 本文。

    Returns:
        機構読取キーの重複がなく、厳密な status 行を持つ値の辞書。不正時は
        ``None``。
    """
    lines = body.splitlines()
    status_lines = [line for line in lines if STATUS_CANDIDATE_RE.match(line)]
    if len(status_lines) != 1 or STATUS_LINE_RE.fullmatch(status_lines[0]) is None:
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
    return values


def parse_fast_frontmatter_bytes(data: bytes) -> dict[str, str] | None:
    """8 KiB 上限内の fast 用 frontmatter を切り詰めずに解析する。

    Args:
        data: plan 先頭から読んだバイト列。

    Returns:
        有効な frontmatter の値。不正な開始・非閉止・上限超過・UTF-8 不正は
        ``None``。
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
                return parse_fast_frontmatter_body(b"".join(body).decode("utf-8"))
            except UnicodeDecodeError:
                return None
        body.append(line)
    return None


def read_fast_frontmatter(path: Path) -> dict[str, str] | None:
    """fast 用 plan の frontmatter だけを安全上限付きで読む。

    Args:
        path: 読み取る plan.md のパス。

    Returns:
        有効な frontmatter の値。読み取り失敗も ``None`` として返す。
    """
    try:
        with path.open("rb") as source:
            data = source.read(FRONTMATTER_LIMIT + 1)
    except Exception:
        return None
    return parse_fast_frontmatter_bytes(data)


def session_file(plan: Path) -> Path:
    return plan.parent / ".codex-session"


REPO_ROOT = Path(__file__).resolve().parents[2]


def git_common_dir(path: Path) -> str | None:
    """path が属するリポジトリの共有 .git ディレクトリ(絶対パス)を返す。"""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, cwd=str(path), timeout=10,
        )
        return str(Path(r.stdout.strip()).resolve()) if r.returncode == 0 else None
    except Exception:
        return None


def require_same_repo(wt: Path) -> None:
    """wt が**本リポジトリの** worktree であることを照合する(4周目 P1 — 同名別リポジトリを排除)。"""
    ours = git_common_dir(REPO_ROOT)
    theirs = git_common_dir(wt)
    if ours is None or theirs is None or ours != theirs:
        die(f"worktree が本リポジトリの worktree でない: {wt}(git-common-dir 不一致 — 設計書 12.1)")


def worktree_branch(wt: Path) -> str | None:
    """wt が git 登録済み worktree ならそのブランチ名を返す(未登録なら None — 2周目 P0 対応)。"""
    try:
        r = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, cwd=str(wt), timeout=10,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    cur: Path | None = None
    for line in r.stdout.splitlines():
        if line.startswith("worktree "):
            cur = Path(line[len("worktree "):])
        elif line.startswith("branch ") and cur is not None:
            try:
                if cur.resolve() == wt.resolve():
                    return line[len("branch "):].removeprefix("refs/heads/")
            except Exception:
                continue
    return None


def resolve_codex() -> list[str]:
    """codex CLI の起動コマンドを解決する。

    Windows では npm インストールの codex は `.cmd` シムであり、CreateProcess は
    シムを直接解決できない(WinError 2)。shutil.which で実体を特定し、
    バッチファイルの場合は cmd /c 経由で起動する。
    """
    exe = shutil.which("codex")
    if exe is None:
        die("codex CLI が見つからない(PATH を確認。導入は onboarding.md)")
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe]
    return [exe]


def codex_version_text() -> str:
    """解決済みの Codex CLI から ``--version`` の標準出力を取得する。

    Returns:
        正常終了した場合の標準出力。取得・実行に失敗した場合は空文字列。
    """
    try:
        completed = subprocess.run(
            [*resolve_codex(), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def parsed_codex_version(version_text: str) -> tuple[int, int, int] | None:
    """Codex CLI の版出力を比較用の 3 要素タプルへ変換する。

    Args:
        version_text: ``codex --version`` の標準出力。

    Returns:
        ``(major, minor, patch)``。想定外の出力では ``None``。
    """
    for line in version_text.splitlines():
        match = CODEX_VERSION_LINE_RE.fullmatch(line.strip())
        if match is not None:
            return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))
    return None


def require_supported_codex_version() -> None:
    """Codex CLI が ADR-001 の運用下限を満たすことを fail-closed で確認する。"""
    version = parsed_codex_version(codex_version_text())
    update_instruction = (
        "docs/development/onboarding.md の 1-6 に従い、Codex CLI のインストーラを再実行"
        "して更新してください"
    )
    if version is None:
        die(f"Codex CLI の版を解析できません。{update_instruction}")
    if version < MINIMUM_CODEX_VERSION:
        actual = ".".join(str(part) for part in version)
        required = ".".join(str(part) for part in MINIMUM_CODEX_VERSION)
        die(f"Codex CLI {actual} は下限 {required} 未満です。{update_instruction}")


def run_codex(argv: list[str], prompt: str, capture_session_to: Path | None = None) -> int:
    print(f"codex_run: 実行: codex {' '.join(argv[:8])} ...", file=sys.stderr)
    proc = subprocess.Popen(
        [*resolve_codex(), *argv, "-"],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
    )
    assert proc.stdin and proc.stderr
    proc.stdin.write(prompt)
    proc.stdin.close()
    session_id = None
    for line in proc.stderr:
        sys.stderr.write(line)
        m = re.search(r"session id:\s*([0-9a-f-]+)", line)
        if m:
            session_id = m.group(1)
    proc.wait()
    if session_id and capture_session_to:
        try:
            capture_session_to.write_text(session_id, encoding="utf-8")
        except Exception:
            pass
    return proc.returncode


def security_overrides(*, may_allow_net: bool) -> list[str]:
    """安全キーを CLI で毎回明示上書きする(2周目 P0 対応)。

    ユーザー/プロジェクト config 層の値に依存しない(config で network_access=true が
    仕込まれていても CLI 指定が優先される)。ネットワーク例外は PITCHLOG_ALLOW_NET=1 に
    加えて PITCHLOG_NET_REASON(理由の記録 — 12.1 の例外運用)を必須とする。
    """
    net = "false"
    if may_allow_net and os.environ.get("PITCHLOG_ALLOW_NET") == "1":
        reason = os.environ.get("PITCHLOG_NET_REASON", "").strip()
        if not reason:
            die('PITCHLOG_ALLOW_NET=1 には PITCHLOG_NET_REASON="理由" が必須(12.1 の例外運用の記録)')
        print(f"codex_run: 警告: ネットワーク有効(理由: {reason})", file=sys.stderr)
        net = "true"
    return [
        "-c", f"sandbox_workspace_write.network_access={net}",
        # 書込境界も config 層に依存させない(3周目 P0): 追加 writable root を無効化し、
        # /tmp・$TMPDIR は許容する(ビルドツール前提)ことを明示固定する
        "-c", "sandbox_workspace_write.writable_roots=[]",
        "-c", "sandbox_workspace_write.exclude_slash_tmp=false",
        "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=false",
    ]


def implement_argv(base: list[str], resume_sid: str | None) -> list[str]:
    """exec の引数列を構築する。

    resume はサブコマンドのため、exec レベルのオプション(-C/-s/-m/-c)は
    `resume` より前に置く(後置は 0.146.1 で unexpected argument — 敵対レビュー2周目 P1)。
    """
    if resume_sid:
        return ["exec", *base, "resume", resume_sid]
    return ["exec", *base]


def cmd_implement(args: list[str]) -> int:
    resume = "--resume" in args
    args = [a for a in args if a != "--resume"]
    if not args:
        die("implement <plan.md> が必要")
    plan = Path(args[0]).resolve()
    if not plan.is_file():
        die(f"計画書が見つからない: {plan}")
    fm, frontmatter_body = parse_frontmatter(plan)
    require_active_plan_status(frontmatter_body)
    approval = fm.get("承認", "未")
    if not approval.startswith("済"):
        die(f"計画書が未承認(承認: {approval})。/plan のレビューと人間承認を先に(設計書 6.1)")
    worktree = fm.get("worktree", "")
    wt = (plan.parent / worktree).resolve() if worktree and not Path(worktree).is_absolute() else Path(worktree)
    if not worktree or not wt.is_dir() or wt.parent.name != WORKTREES_DIRNAME:
        die(f"worktree が不正({worktree})。/task-start が設定した {WORKTREES_DIRNAME} **直下**のパスが必要(設計書 12.1 — 部分文字列でなく親ディレクトリ名で判定)")
    weight = fm.get("重さ分類")
    if weight not in MODEL_MAP:
        display_weight = weight if weight else "未設定"
        die(
            "重さ分類が不正または未設定: "
            f"{display_weight}(軽微/通常/コア領域/機械的軽作業 のいずれかが必須)"
        )
    plan_text = plan.read_text(encoding="utf-8")
    table_status = step_table_status(plan_text)
    if table_status in {StepTableStatus.NO_TABLE, StepTableStatus.NO_FILLED_ROW}:
        die("計画書の「実装ステップ(コミット単位)」見出し配下に、番号・ステップ・合格条件が"
            "すべて埋まった行が無い(設計書 6.1 段階実装 — 空のテンプレ表・無関係な表は不可)")
    if table_status is StepTableStatus.TABLE_OUTSIDE_SCOPE:
        _, outside_heading = _step_table_analysis(plan_text)
        heading = outside_heading or "文書先頭"
        die(
            f"ステップ表は見出し『{heading}』の配下にあります。"
            "『実装ステップ』見出しの配下へ移すか、その見出し名に"
            "『実装ステップ』を含めてください(設計書 6.1)"
        )
    if table_status is StepTableStatus.TABLE_IN_FENCED_CODE:
        die(
            "実装ステップ表がコードブロック内にあります。"
            "コードブロックの外に置いてください(設計書 6.1)"
        )
    branch = fm.get("branch", "")
    if not re.fullmatch(r"(?:feature|fix)/\S+", branch):
        die(f"計画書の branch が不正({branch or '未設定'})。feature/* または fix/* が必要(設計書 6.2)")
    registered = worktree_branch(wt)
    if registered is None:
        die(f"worktree が git に登録されていない: {wt}(/task-start で作成する — 設計書 12.1)")
    if registered != branch:
        die(f"worktree のブランチ({registered})が計画書の branch({branch})と一致しない")
    require_same_repo(wt)
    model, effort = MODEL_MAP[weight]
    prompt = read_prompt(args)
    base = ["-C", str(wt), "-s", "workspace-write", "-m", model,
            "-c", f"model_reasoning_effort={effort}",
            "-c", 'web_search="cached"', *security_overrides(may_allow_net=True)]
    if resume:
        sid_file = session_file(plan)
        if not sid_file.is_file():
            die("保存されたセッション ID がない(--resume 不可。新規実行する)")
        sid = sid_file.read_text(encoding="utf-8").strip()
        return run_codex(implement_argv(base, sid), prompt)
    return run_codex(implement_argv(base, None), prompt, capture_session_to=session_file(plan))


def cmd_fast(args: list[str]) -> int:
    cwd = Path.cwd().resolve()
    if WORKTREES_DIRNAME not in cwd.as_posix():
        die(f"fast path も worktree 内でのみ実行可({WORKTREES_DIRNAME} 配下で実行する — 設計書 6.1)")
    wb = worktree_branch(cwd)
    if wb is None:
        die(f"cwd が git 登録済みの worktree でない: {cwd}(/task-start で作成する — 設計書 12.1)")
    if not re.fullmatch(r"(?:feature|fix)/\S+", wb):
        die(f"fast は feature/*・fix/* の worktree でのみ実行可(現在: {wb} — 設計書 6.1/6.2)")
    require_same_repo(cwd)

    prefix, separator, slug = wb.partition("/")
    if prefix not in {"feature", "fix"} or not separator or not slug or "/" in slug:
        die(
            "fast は feature/<slug>・fix/<slug> の worktree でのみ実行可"
            f"(現在: {wb} — 設計書 6.1/6.2)"
        )

    plan = cwd / "docs" / "features" / slug / "plan.md"
    if not plan.is_file():
        die(f"fast 用の正規位置の計画書が見つからない: {plan}")
    frontmatter = read_fast_frontmatter(plan)
    if frontmatter is None:
        die(
            "fast 用の正規位置の計画書 frontmatter が不正または読めない"
            "(開始/閉止区切り、8 KiB、UTF-8、status、機構読取キー重複を確認)"
        )

    plans_root = cwd / "docs" / "features"
    for candidate in plans_root.glob("*/plan.md"):
        if candidate == plan:
            continue
        candidate_frontmatter = read_fast_frontmatter(candidate)
        if candidate_frontmatter is None:
            die(
                "fast 用計画書の一意性を確認できない: "
                f"別位置の計画書を読めないか frontmatter が不正: {candidate}"
            )
        if candidate_frontmatter.get("branch") == wb:
            die(
                "fast 用計画書が一意でない: "
                f"同じ branch {wb} を持つ別位置の計画書がある: {candidate}"
            )

    if frontmatter.get("branch") != wb:
        die(
            "fast 用計画書の branch が現在のブランチと一致しない: "
            f"{frontmatter.get('branch') or '未設定'} != {wb}"
        )
    if frontmatter.get("status") != "active":
        die("fast は計画書の status: active が必須(in-review を含む不一致は不可)")
    if frontmatter.get("重さ分類") != "軽微":
        die("fast は計画書の重さ分類: 軽微 が必須")
    if frontmatter.get("実行方式") != "fast":
        die("fast は計画書の実行方式: fast が必須")

    model, effort = MODEL_MAP["軽微"]
    prompt = read_prompt(args)
    return run_codex(["exec", "-s", "workspace-write", "-m", model,
                      "-c", f"model_reasoning_effort={effort}",
                      "-c", 'web_search="cached"', *security_overrides(may_allow_net=True)], prompt)


def find_env_files(root: Path) -> list[str]:
    """root 配下の秘密ファイル(.env*)を**除外なしで**再帰検出する(4/5周目 P0)。

    exact `.env.example` のみ許可。除外ディレクトリを設けない(「cwd 配下に存在すれば
    拒否」が仕様)。`os.walk(onerror=...)` で走査エラーを**明示伝播**し fail-closed に倒す
    (rglob は OSError を握り潰すため使わない — 5周目 P0)。ディレクトリ symlink は追跡しない。
    """
    found: list[str] = []

    def on_error(err: OSError) -> None:
        die(f"秘密ファイルの走査に失敗(fail-closed — 12.1): {err}")

    for dirpath, _dirs, files in os.walk(root, onerror=on_error, followlinks=False):
        for name in files:
            if name.startswith(".env") and name != ".env.example":
                found.append(str(Path(dirpath, name).relative_to(root)))
    return sorted(found)


def cmd_research(args: list[str]) -> int:
    # live search 併用の漏洩経路遮断(2周目/3周目 P0 対応): 秘密ファイルのある場所では実行しない
    envs = find_env_files(Path.cwd())
    if envs:
        die(f"配下に {', '.join(envs)} が存在します。/research(live search 併用)は"
            "秘密レスの作業コピーで実行してください(設計書 12.1)")
    model, effort = RESEARCH_DEEP if "--deep" in args else RESEARCH
    prompt = read_prompt([a for a in args if a != "--deep"] or ["-"])
    return run_codex(["exec", "--skip-git-repo-check", "-s", "read-only", "-m", model,
                      "-c", f"model_reasoning_effort={effort}", "-c", 'web_search="live"',
                      *security_overrides(may_allow_net=False)], prompt)


def cmd_review(args: list[str]) -> int:
    if "--base" in args:
        die("--base は未対応(差分の指定はプロンプト本文に含める — 受理したふりをしない)")
    if not args or args[0] not in ("normal", "adversarial"):
        die("review <normal|adversarial> が必要")
    model, effort = REVIEW_NORMAL if args[0] == "normal" else REVIEW_ADVERSARIAL
    prompt = read_prompt(args)
    return run_codex(["exec", "-s", "read-only", "-m", model,
                      "-c", f"model_reasoning_effort={effort}",
                      "-c", 'web_search="cached"', *security_overrides(may_allow_net=False)], prompt)


def configured_model_pairs() -> tuple[tuple[str, str], ...]:
    """ADR-001 のラッパー定数に現れる一意なモデル・effort 組を返す。

    Returns:
        定数の定義順を保った重複なしの ``(model, effort)`` 組。
    """
    pairs = [*MODEL_MAP.values(), RESEARCH, RESEARCH_DEEP, REVIEW_NORMAL, REVIEW_ADVERSARIAL]
    unique_pairs: list[tuple[str, str]] = []
    for pair in pairs:
        if pair not in unique_pairs:
            unique_pairs.append(pair)
    return tuple(unique_pairs)


def cmd_probe(args: list[str]) -> int:
    """対応表の全一意なモデル・effort 組を read-only で受理確認する。"""
    if args:
        die("probe は引数を受け取らない(stdin も読まない)")

    failed = False
    for model, effort in configured_model_pairs():
        exit_code = run_codex(
            [
                "exec",
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-m",
                model,
                "-c",
                f"model_reasoning_effort={effort}",
                "-c",
                'web_search="cached"',
                *security_overrides(may_allow_net=False),
            ],
            PROBE_PROMPT,
        )
        print(
            f"codex_run: probe {model} / {effort} の終了コード: {exit_code}",
            file=sys.stderr,
        )
        if exit_code != 0:
            failed = True
    return 1 if failed else 0


def main() -> int:
    if len(sys.argv) < 2:
        die("モード(implement/fast/research/review/probe)が必要")
    mode, rest = sys.argv[1], sys.argv[2:]
    require_supported_codex_version()
    if mode == "implement":
        return cmd_implement(rest)
    if mode == "fast":
        return cmd_fast(rest)
    if mode == "research":
        return cmd_research(rest)
    if mode == "review":
        return cmd_review(rest)
    if mode == "probe":
        return cmd_probe(rest)
    die(f"不明なモード: {mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
