"""ランタイム認可契約の生成モジュールを検査・描画する CLI。"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    RuntimeContractState,
    asset_digest,
    compare_staged_protected_objects,
    derive_runtime_contract_fields,
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


def switch_repository(repository_root: Path, base_revision: str) -> bool:
    """比較元の暫定契約を検証し、製品契約と生成モジュールへ切り替える。

    Args:
        repository_root: 切り替え対象のリポジトリルート。
        base_revision: 比較元となる Git revision。

    Returns:
        いずれかのファイルを変更した場合は ``True``。

    Raises:
        ValueError: 比較元、製品資産、または改訂番号が拘束を満たさない場合。
    """
    base_sha = _git(
        repository_root, "rev-parse", "--verify", f"{base_revision}^{{commit}}"
    )
    develop_sha = _git(
        repository_root, "rev-parse", "--verify", "origin/develop^{commit}"
    )
    if base_sha != develop_sha:
        raise ValueError("--base は origin/develop の先端と一致する必要があります")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, "HEAD"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        raise ValueError("--base は HEAD の祖先でなければなりません")

    base_asset = _git_json_asset(repository_root, base_sha, RUNTIME_CONTRACT_ASSET)
    base_staged = _git_json_asset(repository_root, base_sha, STAGED_PRODUCT_ASSET)
    if _git_path_exists(repository_root, base_sha, PRODUCT_ASSET):
        raise ValueError("比較元に最終パスの製品資産が存在します")
    with tempfile.TemporaryDirectory(prefix="runtime-contract-base-") as directory:
        snapshot = Path(directory)
        for path, content in (
            (
                RUNTIME_CONTRACT_ASSET,
                _git(
                    repository_root,
                    "show",
                    f"{base_sha}:{RUNTIME_CONTRACT_ASSET.as_posix()}",
                ),
            ),
            (
                STAGED_PRODUCT_ASSET,
                _git(
                    repository_root,
                    "show",
                    f"{base_sha}:{STAGED_PRODUCT_ASSET.as_posix()}",
                ),
            ),
            (GENERATED_MODULE, render_runtime_contract(base_asset)),
        ):
            destination = snapshot / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        base_state, base_violations = evaluate_repository(snapshot)
    if base_state is not RuntimeContractState.PENDING or base_violations:
        raise ValueError(
            "比較元のランタイム契約が正しい未発効状態ではありません: "
            f"{sorted(base_violations)}"
        )
    if not compare_staged_protected_objects(base_staged, base_asset).matches:
        raise ValueError("比較元で U1 の保護対象集合が一致しません")

    final_path = repository_root / PRODUCT_ASSET
    if not final_path.is_file() or (repository_root / STAGED_PRODUCT_ASSET).exists():
        raise ValueError("最終パスだけに製品資産を配置してから切り替えてください")
    final_asset = read_json_object(final_path)
    expected_product = dict(base_staged)
    expected_product.pop("pending_switch", None)
    expected_product.pop("provisional_contract_additions", None)
    if final_asset != expected_product:
        raise ValueError("最終パスの製品資産が比較元の staged 資産と一致しません")

    base_revision_value = base_asset.get("runtime_contract_revision")
    if type(base_revision_value) is not int:
        raise ValueError("比較元の runtime_contract_revision は整数が必要です")
    asset_path = repository_root / RUNTIME_CONTRACT_ASSET
    module_path = repository_root / GENERATED_MODULE
    original_asset = asset_path.read_bytes()
    original_module = module_path.read_bytes()
    current_asset = read_json_object(asset_path)
    current_revision = current_asset.get("runtime_contract_revision")
    if type(current_revision) is not int or current_revision not in (
        base_revision_value,
        base_revision_value + 1,
    ):
        raise ValueError("現在の runtime_contract_revision が比較元 + 1 を超えています")

    desired = copy.deepcopy(base_asset)
    desired["runtime_contract_revision"] = base_revision_value + 1
    desired["provisional"] = False
    desired.pop("superseded_by", None)
    desired["derived_from"] = PRODUCT_ASSET.as_posix()
    baseline = desired.get("baseline_control")
    if not isinstance(baseline, dict) or not isinstance(baseline.get("identity"), dict):
        raise ValueError("比較元の baseline_control.identity が不正です")
    baseline["identity"]["current_identifiers"] = [
        f"runtime_contract_revision:{base_revision_value + 1}"
    ]
    derived = derive_runtime_contract_fields(final_asset, desired)
    application_role = desired.get("application_role")
    if not isinstance(application_role, dict):
        raise ValueError("比較元の application_role が不正です")
    application_role["attributes"] = derived["application_role"]["attributes"]
    desired["protected_objects"] = derived["protected_objects"]
    desired["source_digest"] = asset_digest(desired)
    if current_asset != base_asset and current_asset != desired:
        raise ValueError("現在のランタイム契約資産が比較元または切り替え結果と不一致")
    desired_asset = json.dumps(desired, ensure_ascii=False, indent=2) + "\n"
    desired_module = render_runtime_contract(desired)
    changed = False
    if original_asset != desired_asset.encode("utf-8"):
        _atomic_write(asset_path, desired_asset)
        changed = True
    if original_module != desired_module.encode("utf-8"):
        _atomic_write(module_path, desired_module)
        changed = True
    if read_json_object(asset_path).get("runtime_contract_revision") != (
        base_revision_value + 1
    ):
        _atomic_write(asset_path, original_asset.decode("utf-8"))
        _atomic_write(module_path, original_module.decode("utf-8"))
        raise ValueError("書き込み後の runtime_contract_revision が比較元 + 1 と不一致")
    return changed


def _git(repository_root: Path, *arguments: str) -> str:
    """Git の標準出力を返し、失敗を切り替えエラーにする。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"git {' '.join(arguments)} に失敗: {result.stderr.strip()}")
    return result.stdout.strip() if arguments[0] == "rev-parse" else result.stdout


def _git_json_asset(
    repository_root: Path, revision: str, path: Path
) -> dict[str, object]:
    """比較元に保存された JSON object を返す。"""
    value: object = json.loads(
        _git(repository_root, "show", f"{revision}:{path.as_posix()}")
    )
    if not isinstance(value, dict):
        raise ValueError(f"比較元の資産が JSON object ではありません: {path}")
    return value


def _git_path_exists(repository_root: Path, revision: str, path: Path) -> bool:
    """比較元 tree にパスがあるか調べる。"""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}:{path.as_posix()}"],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


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
    parser.add_argument(
        "mode", nargs="?", choices=("check", "render", "switch"), default="check"
    )
    parser.add_argument("--base", help="switch の比較元 Git revision")
    args = parser.parse_args(argv)
    if args.mode == "switch" and args.base is None:
        parser.error("switch には --base が必要です")
    if args.mode != "switch" and args.base is not None:
        parser.error("--base は switch 専用です")

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
        if args.mode == "switch":
            switch_repository(root, args.base)
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
