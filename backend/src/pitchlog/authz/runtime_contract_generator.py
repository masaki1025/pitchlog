"""ランタイム認可契約の生成モジュールを検査・描画する CLI。"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    RUNTIME_CONTRACT_ASSET,
    evaluate_repository,
    read_json_object,
    render_runtime_contract,
)


def find_repository_root(start: Path | None = None) -> Path | None:
    """``contracts`` と ``.git`` を持つリポジトリルートを探す。

    Args:
        start: 探索を始めるファイルまたはディレクトリ。省略時は本ファイル。

    Returns:
        見つかったリポジトリルート。見つからなければ ``None``。
    """
    current = (start or Path(__file__)).resolve()
    if not current.is_dir():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "contracts").is_dir() and (candidate / ".git").exists():
            return candidate
    return None


def check_repository(repository_root: Path) -> set[str]:
    """リポジトリのランタイム契約を検査する。

    Args:
        repository_root: 検査するリポジトリのルート。

    Returns:
        違反 ID の集合。
    """
    _, violations = evaluate_repository(repository_root)
    return violations


def render_repository(repository_root: Path) -> bool:
    """生成モジュールを原子的に置き換える。

    Args:
        repository_root: 描画するリポジトリのルート。

    Returns:
        ファイルの内容を変更した場合は ``True``。
    """
    asset = read_json_object(repository_root / RUNTIME_CONTRACT_ASSET)
    rendered = render_runtime_contract(asset)
    target = repository_root / GENERATED_MODULE
    if target.is_file() and target.read_text(encoding="utf-8") == rendered:
        return False
    _atomic_write(target, rendered)
    return True


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    """CLI を実行する。

    Args:
        argv: 公開 CLI の引数。省略時はプロセスの引数を使う。
        repository_root: 試験用のリポジトリルート差し替え。

    Returns:
        終了コード。契約違反は 1、ルート未検出は 2。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("check", "render"), default="check")
    args = parser.parse_args(argv)

    root = (
        find_repository_root(repository_root)
        if repository_root is not None
        else find_repository_root()
    )
    if root is None:
        print(
            "エラー: contracts/ と .git を持つリポジトリルートが見つかりません。",
            file=sys.stderr,
        )
        return 2

    try:
        if args.mode == "render":
            render_repository(root)
            return 0

        violations = check_repository(root)
        if not violations:
            return 0
        for violation in sorted(violations):
            print(violation, file=sys.stderr)
        _print_generated_diff(root)
        return 1
    except (OSError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


def _print_generated_diff(repository_root: Path) -> None:
    """現在と期待する生成モジュールの unified diff を表示する。"""
    asset_path = repository_root / RUNTIME_CONTRACT_ASSET
    if not asset_path.is_file():
        return
    asset = read_json_object(asset_path)
    expected = render_runtime_contract(asset)
    module_path = repository_root / GENERATED_MODULE
    actual = module_path.read_text(encoding="utf-8") if module_path.is_file() else ""
    diff = difflib.unified_diff(
        actual.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile=GENERATED_MODULE.as_posix(),
        tofile=f"{GENERATED_MODULE.as_posix()} (expected)",
    )
    sys.stderr.writelines(diff)


def _atomic_write(target: Path, content: str) -> None:
    """同じディレクトリの一時ファイルを使って原子的に書き込む。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            dir=target.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            payload = content.encode("utf-8")
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("一時ファイルへの書き込みが進みません")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        temporary_path.chmod(mode)
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
