"""Codex 実行の唯一の許可経路(設計書 12.1 / 敵対レビュー P0-2 対応)。

生の `codex exec` は codex_guard フックが遮断する。本ラッパーが
計画書の承認状態・実行場所(worktree)・sandbox・モデル対応表(ADR-001)を検証・固定する。

使い方:
  python .claude/scripts/codex_run.py implement <plan.md> [--resume] [-]   # 実装(承認済み計画書必須)
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


def die(msg: str) -> None:
    print(f"codex_run: エラー: {msg}", file=sys.stderr)
    sys.exit(2)


def read_prompt(args: list[str]) -> str:
    if args and args[-1] == "-":
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む
        return sys.stdin.buffer.read().decode("utf-8", "replace")
    die("プロンプトは stdin で渡す(末尾引数に `-` を指定)")
    return ""


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        die(f"計画書 {path} に frontmatter がない")
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.split("#")[0].strip()
    return fm


def session_file(plan: Path) -> Path:
    return plan.parent / ".codex-session"


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
    return ["-c", f"sandbox_workspace_write.network_access={net}"]


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
    fm = parse_frontmatter(plan)
    approval = fm.get("承認", "未")
    if not approval.startswith("済"):
        die(f"計画書が未承認(承認: {approval})。/plan のレビューと人間承認を先に(設計書 6.1)")
    worktree = fm.get("worktree", "")
    wt = (plan.parent / worktree).resolve() if worktree and not Path(worktree).is_absolute() else Path(worktree)
    if not worktree or not wt.is_dir() or WORKTREES_DIRNAME not in wt.as_posix():
        die(f"worktree が不正({worktree})。/task-start が設定した {WORKTREES_DIRNAME} 配下のパスが必要(設計書 12.1)")
    weight = fm.get("重さ分類", "通常")
    if weight not in MODEL_MAP:
        die(f"重さ分類が不正: {weight}(軽微/通常/コア領域/機械的軽作業)")
    if "実装ステップ" not in plan.read_text(encoding="utf-8"):
        die("計画書に「実装ステップ(コミット単位)」が無い(設計書 6.1 段階実装 — plan-template 4 節の表を埋める)")
    branch = fm.get("branch", "")
    registered = worktree_branch(wt)
    if registered is None:
        die(f"worktree が git に登録されていない: {wt}(/task-start で作成する — 設計書 12.1)")
    if branch and registered != branch:
        die(f"worktree のブランチ({registered})が計画書の branch({branch})と一致しない")
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
    if worktree_branch(cwd) is None:
        die(f"cwd が git 登録済みの worktree でない: {cwd}(/task-start で作成する — 設計書 12.1)")
    model, effort = MODEL_MAP["軽微"]
    prompt = read_prompt(args)
    return run_codex(["exec", "-s", "workspace-write", "-m", model,
                      "-c", f"model_reasoning_effort={effort}",
                      "-c", 'web_search="cached"', *security_overrides(may_allow_net=True)], prompt)


def cmd_research(args: list[str]) -> int:
    # live search 併用の漏洩経路遮断(2周目 P0 対応): 秘密ファイルのある場所では実行しない
    envs = sorted(p.name for p in Path.cwd().glob(".env*") if p.name != ".env.example")
    if envs:
        die(f"cwd に {', '.join(envs)} が存在します。/research(live search 併用)は"
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
