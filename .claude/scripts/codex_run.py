"""Codex 実行の唯一の許可経路(設計書 12.1 / 敵対レビュー P0-2 対応)。

生の `codex exec` は codex_guard フックが遮断する。本ラッパーが
計画書の plan status(implement のみ・active 必須)と承認状態・実行場所(worktree)・sandbox・モデル対応表(ADR-001)を検証・固定する。

使い方:
  python .claude/scripts/codex_run.py implement <plan.md> [--resume] [-]   # 実装(status: active かつ承認済み計画書必須)
  python .claude/scripts/codex_run.py fast [-]                             # 軽微 fast path(6.1。人間の事前OK前提)
  python .claude/scripts/codex_run.py research [--deep] [-]                # Web調査(read-only + live search)
  python .claude/scripts/codex_run.py review <normal|adversarial> [-]      # レビュー(read-only。差分指定はプロンプトに書く)

プロンプトは末尾引数 `-` で stdin から渡す(クォート事故防止)。
ネットワーク有効化は PITCHLOG_ALLOW_NET=1 + PITCHLOG_NET_REASON="理由"(必須 — 人間へ報告済みであること)。
sandbox 安全キーは毎回 CLI で明示上書きし、config 層の値に依存しない(2周目 P0 対応)。
"""
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

# ADR-001 モデル対応表(明示 ID 固定)
MODEL_MAP = {
    "軽微": ("gpt-5.6-terra", "medium"),
    "通常": ("gpt-5.6-terra", "max"),
    "コア領域": ("gpt-5.6-sol", "xhigh"),
    "機械的軽作業": ("gpt-5.6-luna", "xhigh"),
}
RESEARCH = ("gpt-5.6-terra", "high")
RESEARCH_DEEP = ("gpt-5.6-sol", "xhigh")
REVIEW_NORMAL = ("gpt-5.6-terra", "max")
REVIEW_ADVERSARIAL = ("gpt-5.6-sol", "xhigh")

WORKTREES_DIRNAME = "pitchlog-worktrees"

# `codex_run.py` ↔ `scripts/feature_status.py:301-307` の相互参照:
# status 判定は同じ手順・正規表現リテラルを維持する。両スクリプトの独立性のため import は共有しない。
STATUS_CANDIDATE_RE = re.compile(r"^status\s*:")
STATUS_LINE_RE = re.compile(r"^status:\s*(active|in-review)(?:\s+#.*)?$")


def die(msg: str) -> None:
    print(f"codex_run: エラー: {msg}", file=sys.stderr)
    sys.exit(2)


def read_prompt(args: list[str]) -> str:
    if args and args[-1] == "-":
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む
        return sys.stdin.buffer.read().decode("utf-8", "replace")
    die("プロンプトは stdin で渡す(末尾引数に `-` を指定)")
    return ""


def has_filled_step_row(plan_text: str) -> bool:
    """「実装ステップ」見出し**配下の表**に、全セル記入済みの行があるか(4周目 P1)。

    番号・ステップ内容・合格条件の3セルすべて非空を要求する。別の見出し配下の
    数値表では条件を満たさない(見出し単位で判定範囲を区切る)。
    """
    in_section = False
    for line in plan_text.splitlines():
        if re.match(r"#{1,6}\s", line):
            in_section = "実装ステップ" in line
            continue
        if not in_section:
            continue
        m = re.match(r"\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|", line)
        if m and m.group(2).strip() and m.group(3).strip():
            return True
    return False


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
    weight = fm.get("重さ分類", "通常")
    if weight not in MODEL_MAP:
        die(f"重さ分類が不正: {weight}(軽微/通常/コア領域/機械的軽作業)")
    plan_text = plan.read_text(encoding="utf-8")
    if not has_filled_step_row(plan_text):
        die("計画書の「実装ステップ(コミット単位)」見出し配下に、番号・ステップ・合格条件が"
            "すべて埋まった行が無い(設計書 6.1 段階実装 — 空のテンプレ表・無関係な表は不可)")
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


def main() -> int:
    if len(sys.argv) < 2:
        die("モード(implement/fast/research/review)が必要")
    mode, rest = sys.argv[1], sys.argv[2:]
    if mode == "implement":
        return cmd_implement(rest)
    if mode == "fast":
        return cmd_fast(rest)
    if mode == "research":
        return cmd_research(rest)
    if mode == "review":
        return cmd_review(rest)
    die(f"不明なモード: {mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
