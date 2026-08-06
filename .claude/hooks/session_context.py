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

    root = Path(cwd)
    features = root / "docs" / "features"
    if features.is_dir():
        active = []
        for plan in features.glob("*/plan.md"):
            try:
                head = plan.read_text(encoding="utf-8")[:800]
                if "status: active" not in head and "status: in-review" not in head:
                    continue
                # worktree が現存するものだけを「進行中」とする(完了の正は PR/Notion/worktree — 設計書 6.1)
                m = None
                for ln in head.splitlines():
                    if ln.startswith("worktree:"):
                        m = ln.split(":", 1)[1].split("#")[0].strip()
                        break
                wt = (plan.parent / m).resolve() if m and not Path(m).is_absolute() else (Path(m) if m else None)
                if wt is None or wt.is_dir():
                    active.append(plan.parent.name)
            except Exception:
                pass
        if active:
            lines.append("進行中の feature(worktree 現存): " + ", ".join(sorted(active)))

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
