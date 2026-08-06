"""Codex 実行の唯一の許可経路(設計書 12.1 / 敵対レビュー P0-2 対応)。

生の `codex exec` は codex_guard フックが遮断する。本ラッパーが
計画書の承認状態・実行場所(worktree)・sandbox・モデル対応表(ADR-001)を検証・固定する。

使い方:
  python .claude/scripts/codex_run.py implement <plan.md> [--resume] [-]   # 実装(承認済み計画書必須)
  python .claude/scripts/codex_run.py fast [-]                             # 軽微 fast path(6.1。人間の事前OK前提)
  python .claude/scripts/codex_run.py research [--deep] [-]                # Web調査(read-only + live search)
  python .claude/scripts/codex_run.py review <normal|adversarial> [--base <ref>] [-]  # レビュー(read-only)

プロンプトは末尾引数 `-` で stdin から渡す(クォート事故防止)。
ネットワーク有効化は環境変数 PITCHLOG_ALLOW_NET=1 のみ(理由を人間へ報告済みであること)。
"""
import os
import re
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
        return sys.stdin.read()
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


def run_codex(argv: list[str], prompt: str, capture_session_to: Path | None = None) -> int:
    print(f"codex_run: 実行: codex {' '.join(argv[:8])} ...", file=sys.stderr)
    proc = subprocess.Popen(
        ["codex", *argv, "-"],
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


def network_flags() -> list[str]:
    if os.environ.get("PITCHLOG_ALLOW_NET") == "1":
        print("codex_run: 警告: ネットワーク有効(12.1 の例外運用 — 理由の報告が必要)", file=sys.stderr)
        return ["-c", "sandbox_workspace_write.network_access=true"]
    return []


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
    model, effort = MODEL_MAP[weight]
    prompt = read_prompt(args)
    base = ["-C", str(wt), "-s", "workspace-write", "-m", model,
            "-c", f"model_reasoning_effort={effort}", *network_flags()]
    if resume:
        sid_file = session_file(plan)
        if not sid_file.is_file():
            die("保存されたセッション ID がない(--resume 不可。新規実行する)")
        sid = sid_file.read_text(encoding="utf-8").strip()
        return run_codex(["exec", "resume", sid, *base], prompt)
    return run_codex(["exec", *base], prompt, capture_session_to=session_file(plan))


def cmd_fast(args: list[str]) -> int:
    cwd = Path.cwd().resolve()
    if WORKTREES_DIRNAME not in cwd.as_posix():
        die(f"fast path も worktree 内でのみ実行可({WORKTREES_DIRNAME} 配下で実行する — 設計書 6.1)")
    model, effort = MODEL_MAP["軽微"]
    prompt = read_prompt(args)
    return run_codex(["exec", "-s", "workspace-write", "-m", model,
                      "-c", f"model_reasoning_effort={effort}"], prompt)


def cmd_research(args: list[str]) -> int:
    model, effort = RESEARCH_DEEP if "--deep" in args else RESEARCH
    prompt = read_prompt([a for a in args if a != "--deep"] or ["-"])
    return run_codex(["exec", "--skip-git-repo-check", "-s", "read-only", "-m", model,
                      "-c", f"model_reasoning_effort={effort}", "-c", 'web_search="live"'], prompt)


def cmd_review(args: list[str]) -> int:
    if not args or args[0] not in ("normal", "adversarial"):
        die("review <normal|adversarial> が必要")
    model, effort = REVIEW_NORMAL if args[0] == "normal" else REVIEW_ADVERSARIAL
    prompt = read_prompt(args)
    return run_codex(["exec", "-s", "read-only", "-m", model,
                      "-c", f"model_reasoning_effort={effort}"], prompt)


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
