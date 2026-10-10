"""backend 実行イメージの版固定と秘密情報の除外を検査する。"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "backend/Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def _from_images() -> list[tuple[str, str | None]]:
    """Dockerfile の基底イメージとステージ名を返す。"""
    return re.findall(
        r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$",
        DOCKERFILE.read_text(encoding="utf-8"),
        flags=re.IGNORECASE | re.MULTILINE,
    )


def test_node_version_matches_mise_and_is_copied() -> None:
    """Node の版と同梱元ステージを確認する。"""
    mise = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    node_version = mise["tools"]["node"]
    node_images = [(image, stage) for image, stage in _from_images() if image.startswith("node:")]
    assert len(node_images) == 1
    image, stage = node_images[0]
    assert image.startswith(f"node:{node_version}-")
    assert stage is not None
    assert re.search(
        rf"^COPY\s+--from={re.escape(stage)}\s+/usr/local/bin/node\s+/usr/local/bin/node\s*$",
        DOCKERFILE.read_text(encoding="utf-8"),
        flags=re.IGNORECASE | re.MULTILINE,
    )


def test_every_from_uses_sha256_digest() -> None:
    """すべての基底イメージが完全な digest で固定されていることを確認する。"""
    images = _from_images()
    assert len(images) >= 2
    for image, _ in images:
        assert re.fullmatch(r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}", image)


def test_environment_files_are_ignored_and_not_copied() -> None:
    """環境変数ファイルがコンテキストと COPY・ADD から除外されることを確認する。"""
    patterns = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert {".env", ".env.*", "**/.env", "**/.env.*"} <= patterns
    assert {".git", "**/.git", "node_modules", "**/node_modules", ".venv", "**/.venv"} <= patterns
    instructions = re.findall(
        r"^(?:COPY|ADD)\s+.*$",
        DOCKERFILE.read_text(encoding="utf-8"),
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert instructions
    assert all(".env" not in instruction for instruction in instructions)


def test_runtime_uses_non_root_user() -> None:
    """最後のステージで root 以外へ切り替えることを確認する。"""
    runtime = DOCKERFILE.read_text(encoding="utf-8").split(" AS runtime\n", 1)
    assert len(runtime) == 2
    users = re.findall(r"^USER\s+(\S+)\s*$", runtime[1], flags=re.IGNORECASE | re.MULTILINE)
    assert users
    assert users[-1] not in {"root", "0", "0:0"}


def test_runtime_assets_are_copied_without_chown() -> None:
    """artifact・宣言・仮想環境を実行ユーザーの所有物にしない。"""
    copy_lines = [
        line.strip()
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.lstrip().upper().startswith("COPY ")
    ]
    expected_copies = {
        "/app/backend/.venv": "COPY --from=build /app/backend/.venv ./.venv",
        "frontend/public/domain/pitchlog-domain.js": (
            "COPY frontend/public/domain/pitchlog-domain.js "
            "/app/frontend/public/domain/pitchlog-domain.js"
        ),
        "frontend/public/domain/pitchlog-domain.json": (
            "COPY frontend/public/domain/pitchlog-domain.json "
            "/app/frontend/public/domain/pitchlog-domain.json"
        ),
    }
    for source, expected in expected_copies.items():
        matching = [line for line in copy_lines if source in line.split()]
        assert matching == [expected]
        assert all("--chown" not in line.lower() for line in matching)
