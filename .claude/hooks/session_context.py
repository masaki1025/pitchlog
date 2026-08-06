"""セッション開始時の文脈注入フック(SessionStart)。

現在ブランチ・未コミット差分・進行中 feature(plan.md の status: active)・
最新 worklog の要点を additionalContext として注入する(設計書 8.3)。失敗時は沈黙。
"""
import json
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import Path


def git(args: list[str], cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=cwd or None, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def list_worktrees(cwd: str) -> list[dict]:
    """全 worktree(メインツリー含む)を path・branch で列挙する(2周目 P1 対応)。"""
    out = git(["worktree", "list", "--porcelain"], cwd)
    wts: list[dict] = []
    cur: dict = {}
    for ln in out.splitlines():
        if ln.startswith("worktree "):
            if cur:
                wts.append(cur)
            cur = {"path": ln[len("worktree "):]}
        elif ln.startswith("branch "):
            cur["branch"] = ln[len("branch "):].removeprefix("refs/heads/")
    if cur:
        wts.append(cur)
    return wts


def main() -> int:
    try:
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    cwd = data.get("cwd", "") or "."
    lines: list[str] = []

    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch:
        dirty = git(["status", "--porcelain"], cwd)
        n = len([ln for ln in dirty.splitlines() if ln.strip()])
        lines.append(f"現在ブランチ: {branch}(未コミット変更 {n} 件)")
        if branch in ("main", "develop"):
            lines.append("注意: 保護ブランチ上にいます。作業は /task-start で feature/* を切ってから。")

    # 進行中 feature の正は「worktree の現存」(設計書 6.1/7.6)。cwd 配下だけでなく
    # 全 worktree(メインツリー・兄弟 worktree)の plan.md を列挙する(2周目 P1 対応)
    root = Path(cwd)
    active = []
    worktree_entries = list_worktrees(cwd) or [{"path": str(root)}]
    for wt in worktree_entries:
        fdir = Path(wt.get("path", "")) / "docs" / "features"
        if not fdir.is_dir():
            continue
        for plan in fdir.glob("*/plan.md"):
            try:
                head = plan.read_text(encoding="utf-8")[:800]
            except Exception:
                continue
            if "status: active" in head or "status: in-review" in head:
                b = wt.get("branch", "")
                active.append(f"{plan.parent.name}({b})" if b else plan.parent.name)
    if active:
        lines.append("進行中の feature(worktree 現存): " + ", ".join(sorted(set(active))))

    worklog = root / "docs" / "worklog"
    if worklog.is_dir():
        logs = sorted(worklog.glob("*.md"))
        if logs:
            latest = logs[-1]
            try:
                excerpt = "\n".join(latest.read_text(encoding="utf-8").splitlines()[:15])
                lines.append(f"最新 worklog({latest.name} 冒頭):\n{excerpt}")
            except Exception:
                pass

    if lines:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "【pitchlog ハーネス】\n" + "\n".join(lines),
            }
        }
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
