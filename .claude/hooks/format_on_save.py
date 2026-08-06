"""保存時自動フォーマットフック(PostToolUse / Write|Edit)。

backend/**/*.py → ruff format + ruff check --fix、frontend/** → prettier。
ツール未導入・失敗時は静かにスキップする(fail-open。品質の最終防衛は /check と CI)。
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


def run(cmd: list[str], cwd: Path) -> None:
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=60)
    except Exception:
        pass


def main() -> int:
    try:
        # Windows のパイプ stdin は locale エンコーディングで壊れ得るため、バイト列を UTF-8 で読む(fail-open 防止)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    file_path = str(data.get("tool_input", {}).get("file_path", ""))
    if not file_path:
        return 0
    path = Path(file_path)
    if not path.exists():
        return 0

    root = None
    for parent in [path.parent, *path.parents]:
        if (parent / ".git").exists():
            root = parent
            break
    if root is None:
        return 0

    rel = path.as_posix()
    backend = root / "backend"
    frontend = root / "frontend"

    if path.suffix == ".py" and (backend / "pyproject.toml").exists() and backend.as_posix() in rel:
        run(["uv", "run", "ruff", "format", str(path)], backend)
        run(["uv", "run", "ruff", "check", "--fix", str(path)], backend)
    elif (
        path.suffix in {".ts", ".vue", ".js", ".css", ".json", ".html"}
        and (frontend / "package.json").exists()
        and frontend.as_posix() in rel
    ):
        run(["pnpm", "exec", "prettier", "--write", str(path)], frontend)
    return 0


if __name__ == "__main__":
    sys.exit(main())
