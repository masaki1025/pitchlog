"""セッション開始時の文脈注入フック(SessionStart)。

現在ブランチ・未コミット差分・feature_status.py が導出した進行中 feature・
最新 worklog の要点を additionalContext として注入する(設計書 8.3)。
"""
import json
import subprocess
import sys
from pathlib import Path


FEATURE_STATUS_PYTHON = "/usr/bin/python3"
FEATURE_STATUS_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "feature_status.py"
FEATURE_STATUS_TIMEOUT_SECONDS = 10

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def git(args: list[str], cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=cwd or None, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def feature_status_summary(cwd: str) -> str | None:
    """feature_status.py の hook 形式出力を取得する。

    Args:
        cwd: SessionStart 入力で指定された基準ディレクトリ。

    Returns:
        正常終了時は末尾改行を除いた hook 出力。子プロセスの失敗時は ``None``。
    """
    try:
        result = subprocess.run(
            [
                FEATURE_STATUS_PYTHON,
                str(FEATURE_STATUS_SCRIPT),
                "--format",
                "hook",
                "--cwd",
                cwd,
            ],
            capture_output=True,
            cwd=cwd or None,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=FEATURE_STATUS_TIMEOUT_SECONDS,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\r\n")


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
    summary = feature_status_summary(cwd)
    if summary is None:
        lines.append("進行中 feature: 未取得(導出失敗)")
    elif summary:
        lines.append(summary)

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
