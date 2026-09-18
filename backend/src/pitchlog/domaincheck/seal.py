"""NFR-018 (e) BOOT-SEAL の封印機構を提供する。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    EXIT_NONCONFORMING,
    CheckerExecutionError,
    CheckerViolation,
    canonical_hash,
    read_json,
    write_canonical_json,
)

_COMMIT_OID_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_SEAL_KEYS = frozenset(
    {"schemaVersion", "assetPath", "baseCommitOid", "blobDigest"}
)


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを送出する。"""
        raise CheckerExecutionError(message)


def _default_root() -> Path:
    """モジュール配置からリポジトリルートを解決する。"""
    return Path(__file__).resolve().parents[4]


def _repository_path(root: Path, raw_path: Path, label: str) -> tuple[Path, str]:
    """リポジトリ内の実パスと正規化した相対パスを返す。"""
    resolved_root = root.resolve()
    resolved = (
        raw_path.resolve()
        if raw_path.is_absolute()
        else (root / raw_path).resolve()
    )
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as error:
        raise CheckerExecutionError(f"{label}がリポジトリ外を指している") from error
    if not relative.parts:
        raise CheckerExecutionError(f"{label}がファイルを指していない")
    return resolved, relative.as_posix()


def _expect_seal(raw: object) -> dict[str, object]:
    """封印レコードの厳密な形を検査して返す。"""
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise CheckerExecutionError("封印レコードが JSON object でない")
    observed = set(raw)
    if observed != _SEAL_KEYS:
        missing = sorted(_SEAL_KEYS - observed)
        unexpected = sorted(observed - _SEAL_KEYS)
        raise CheckerExecutionError(
            f"封印レコードのキー集合が不一致: 不足={missing!r}, "
            f"未登録={unexpected!r}"
        )
    if raw["schemaVersion"] != 1 or isinstance(raw["schemaVersion"], bool):
        raise CheckerExecutionError("封印レコードの schemaVersion が 1 でない")
    asset_path = raw["assetPath"]
    base_commit = raw["baseCommitOid"]
    digest = raw["blobDigest"]
    if not isinstance(asset_path, str) or not asset_path:
        raise CheckerExecutionError("封印レコードの assetPath が空でない文字列でない")
    if (
        not isinstance(base_commit, str)
        or _COMMIT_OID_PATTERN.fullmatch(base_commit) is None
    ):
        raise CheckerExecutionError("baseCommitOid が完全な commit OID でない")
    if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
        raise CheckerExecutionError("blobDigest が canonical SHA-256 でない")
    return raw


def _assert_fixed_fields(
    seal: dict[str, object], asset_path: str, base_commit: str
) -> None:
    """対象パスと固定比較元の書き換えを拒否する。"""
    if seal["baseCommitOid"] != base_commit:
        raise CheckerViolation(
            "NFR-018 (e) BOOT-SEAL-IMMUTABLE: baseCommitOid が変更された"
        )
    if seal["assetPath"] != asset_path:
        raise CheckerViolation("封印対象の assetPath が変更された")


def _run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """版管理ツールを実行し、起動不能を判定不能へ変換する。"""
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise CheckerExecutionError(
            f"版管理ツールを実行できず履歴を判定できない: {error}"
        ) from error


def _verify_commit_oid(root: Path, commit_oid: str) -> None:
    """固定 OID が実在する commit の完全 OID であることを確認する。"""
    result = _run_git(root, "rev-parse", "--verify", f"{commit_oid}^{{commit}}")
    if result.returncode != 0:
        raise CheckerExecutionError("固定 commit OID を版管理履歴で確認できない")
    if result.stdout.strip() != commit_oid:
        raise CheckerViolation(
            "NFR-018 (e) BOOT-SEAL-BASE: 比較元が完全な commit OID でない"
        )


def _historical_base_commit(
    root: Path, seal_relative: str
) -> str | None:
    """封印レコードの Git 初出時に記録された固定 OID を返す。"""
    history = _run_git(
        root,
        "log",
        "--diff-filter=A",
        "--format=%H",
        "--",
        seal_relative,
    )
    if history.returncode != 0:
        raise CheckerExecutionError("封印レコードの追加履歴を確認できない")
    introduction_commits = [
        line for line in history.stdout.splitlines() if line
    ]
    if not introduction_commits:
        return None
    introduction = introduction_commits[-1]
    snapshot = _run_git(root, "show", f"{introduction}:{seal_relative}")
    if snapshot.returncode != 0:
        raise CheckerExecutionError("封印レコードの初出スナップショットを読めない")
    try:
        historical = json.loads(snapshot.stdout)
    except json.JSONDecodeError as error:
        raise CheckerExecutionError(
            "封印レコードの初出スナップショットが JSON でない"
        ) from error
    return str(_expect_seal(historical)["baseCommitOid"])


def _assert_history_immutable(
    root: Path, seal_relative: str, current_base: object
) -> None:
    """Git 初出後の固定 OID の変更を無条件に拒否する。"""
    historical_base = _historical_base_commit(root, seal_relative)
    if historical_base is not None and current_base != historical_base:
        raise CheckerViolation(
            "NFR-018 (e) BOOT-SEAL-IMMUTABLE: "
            "Git 初出後に baseCommitOid が変更された"
        )


def _candidate(asset: object, asset_path: str, base_commit: str) -> dict[str, object]:
    """検査済み入力から新しい封印候補を構築する。"""
    return {
        "schemaVersion": 1,
        "assetPath": asset_path,
        "baseCommitOid": base_commit,
        "blobDigest": canonical_hash(asset),
    }


def _verify_record(
    seal: dict[str, object],
    asset: object,
    asset_path: str,
    base_commit: str,
) -> None:
    """封印レコードと対象資産の一致を検査する。"""
    _assert_fixed_fields(seal, asset_path, base_commit)
    if seal["blobDigest"] != canonical_hash(asset):
        raise CheckerViolation("封印対象の canonical blob digest が一致しない")


def _ci_reseal_guard() -> None:
    """CI 環境からの再封印を拒否する。"""
    try:
        os.environ["CI"]
    except KeyError:
        return
    raise CheckerViolation("CI 環境では --reseal を実行できない")


def _verify(
    root: Path,
    asset_path: Path,
    asset_relative: str,
    seal_path: Path,
    seal_relative: str,
    base_commit: str,
) -> None:
    """通常検証を読み取り専用で実行する。"""
    asset = read_json(asset_path)
    seal = _expect_seal(read_json(seal_path))
    _assert_fixed_fields(seal, asset_relative, base_commit)
    _assert_history_immutable(root, seal_relative, seal["baseCommitOid"])
    _verify_commit_oid(root, base_commit)
    _verify_record(seal, asset, asset_relative, base_commit)


def _reseal(
    root: Path,
    asset_path: Path,
    asset_relative: str,
    seal_path: Path,
    seal_relative: str,
    base_commit: str,
) -> None:
    """自己検査済みの候補だけを明示的に再封印する。"""
    _ci_reseal_guard()
    asset = read_json(asset_path)
    if seal_path.exists():
        existing = _expect_seal(read_json(seal_path))
        _assert_fixed_fields(existing, asset_relative, base_commit)
        _assert_history_immutable(
            root, seal_relative, existing["baseCommitOid"]
        )
    _verify_commit_oid(root, base_commit)
    candidate = _expect_seal(_candidate(asset, asset_relative, base_commit))
    _verify_record(candidate, asset, asset_relative, base_commit)
    write_canonical_json(seal_path, candidate)


def _build_parser() -> argparse.ArgumentParser:
    """封印 CLI の引数パーサを作る。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--reseal", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """封印を検証または明示更新し、結果を exit コードで返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        適合は 0、不適合は 1、判定不能は 2。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        if not root.is_dir():
            raise CheckerExecutionError(f"リポジトリルートを読めない: {root}")
        base_commit = arguments.base_commit
        if (
            not isinstance(base_commit, str)
            or _COMMIT_OID_PATTERN.fullmatch(base_commit) is None
        ):
            raise CheckerExecutionError("--base-commit は完全な commit OID が必要")
        asset_path, asset_relative = _repository_path(root, arguments.asset, "--asset")
        seal_path, seal_relative = _repository_path(
            root, arguments.seal, "--seal"
        )
        if asset_path == seal_path:
            message = "--asset と --seal は別ファイルでなければならない"
            raise CheckerExecutionError(message)
        if arguments.reseal:
            _reseal(
                root,
                asset_path,
                asset_relative,
                seal_path,
                seal_relative,
                base_commit,
            )
            print(f"再封印した: {arguments.seal}")
        else:
            _verify(
                root,
                asset_path,
                asset_relative,
                seal_path,
                seal_relative,
                base_commit,
            )
    except CheckerViolation as error:
        print(f"不適合: {error}", file=sys.stderr)
        return EXIT_NONCONFORMING
    except CheckerExecutionError as error:
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE
    return EXIT_CONFORMING


if __name__ == "__main__":
    raise SystemExit(main())
