"""製品化の最終コミットを一時複製で構築し、その tree を検証する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pitchlog.authz.runtime_contract_generator import (
    _atomic_write,
    find_repository_root,
    switch_repository,
)
from pitchlog.authz.runtime_contract_state import (
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    read_json_object,
)

_AUTHORITY = Path("contracts/tenant_boundary/base-allowlist.json")
_SNAPSHOTS = Path("contracts/tenant_boundary/history-snapshots")
_SPEC = Path("backend/src/pitchlog/authz/asset_spec.py")
_CORPUS_MANIFEST = Path("tests/fixtures/frozen-archive-cases/manifest.json")
_CORPUS_RUNNER = Path("tests/fixtures/frozen-archive-cases/runner.py")
_ACCEPTANCE_ID = "masaki1025/pitchlog#87"


@dataclass(frozen=True, slots=True)
class DryrunResult:
    """ドライランの比較元・親・tree と一時複製を保持する。"""

    base_sha: str
    head_sha: str
    tree_sha: str
    repository: Path
    corpus_digest_updated: bool = False
    corpus_changed_paths: tuple[str, ...] = ()


def _git(root: Path, *arguments: str) -> str:
    """Git の出力を返し、失敗した操作を明示する。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"git {' '.join(arguments)} に失敗: {result.stderr.strip()}")
    return result.stdout.strip()


def _git_bytes(root: Path, revision: str, relative: str) -> bytes:
    """Git tree 内のファイルの生バイト列を返す。"""
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise ValueError(f"比較元のファイルを読めません: {relative}")
    return result.stdout


def _json_bytes(content: bytes, label: str) -> dict[str, Any]:
    """Git の JSON object を検証して返す。"""
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object ではありません: {label}")
    return cast(dict[str, Any], value)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    """複製内の JSON を一貫した体裁で保存する。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _tenant_assets(root: Path, revision: str | None) -> dict[str, dict[str, Any]]:
    """比較元または複製の凍結資産を全件読む。"""
    if revision is None:
        paths = sorted((root / "contracts/tenant_boundary").glob("*.json"))
        return {
            path.relative_to(root).as_posix(): cast(
                dict[str, Any], read_json_object(path)
            )
            for path in paths
        }
    names = _git(
        root,
        "ls-tree",
        "-r",
        "--name-only",
        revision,
        "contracts/tenant_boundary",
    ).splitlines()
    return {
        name: _json_bytes(_git_bytes(root, revision, name), name)
        for name in names
        if Path(name).parent == Path("contracts/tenant_boundary")
        and name.endswith(".json")
    }


def _history_module(root: Path) -> Any:
    """複製に保存された既存の凍結履歴実装を読み込む。"""
    path = root / "scripts/frozen_history.py"
    spec = importlib.util.spec_from_file_location(
        "pitchlog_dryrun_frozen_history", path
    )
    if spec is None or spec.loader is None:
        raise ValueError("複製の frozen_history.py を読み込めません")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _corpus_runner(root: Path) -> Any:
    """複製に保存された corpus digest の正本実装を読み込む。"""
    path = root / _CORPUS_RUNNER
    spec = importlib.util.spec_from_file_location(
        "pitchlog_dryrun_frozen_archive_runner", path
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"比較 corpus の runner を読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _snapshot(path: Path, content: bytes) -> None:
    """内容アドレス付き snapshot を複製に追加する。"""
    target = path / hashlib.sha256(content).hexdigest()
    if target.exists():
        if target.read_bytes() != content:
            raise ValueError(f"既存 snapshot の内容が不正です: {target.name}")
    else:
        target.write_bytes(content)


def _append_history(root: Path, base_sha: str) -> None:
    """既存の凍結履歴 API で実遷移を導出して v2 記録を追記する。"""
    history = _history_module(root)
    base_assets = _tenant_assets(root, base_sha)
    head_assets = _tenant_assets(root, None)
    if set(base_assets) != set(head_assets):
        raise ValueError("比較元と複製の凍結資産集合が異なります")
    base_components = history._repository_components(
        base_assets, "比較元", allow_undeclared_authority=True
    )
    head_components = history._repository_components(head_assets, "HEAD")
    base_targets = tuple(
        sorted(
            {
                path
                for component in base_components.values()
                for path in component.external_files
            }
        )
    )
    head_targets = tuple(
        sorted(
            {
                path
                for component in head_components.values()
                for path in component.external_files
            }
        )
    )
    base_files = {path: _git_bytes(root, base_sha, path) for path in base_targets}
    head_files = {path: (root / path).read_bytes() for path in head_targets}
    base_asset_refs, base_projections = history._asset_projection_snapshots(
        base_assets, base_files, "比較元"
    )
    head_asset_refs, head_projections = history._asset_projection_snapshots(
        head_assets, head_files, "HEAD"
    )
    before = {
        "declaration": {
            name: base_components[name].declaration for name in sorted(base_components)
        },
        "movement_policy": {
            name: base_components[name].movement_policy
            for name in sorted(base_components)
        },
        "external_snapshots": history._implementation_snapshots(
            base_targets, base_files, "比較元.implementations"
        ),
        "asset_snapshots": base_asset_refs,
    }
    after = {
        "declaration": {
            name: head_components[name].declaration for name in sorted(head_components)
        },
        "movement_policy": {
            name: head_components[name].movement_policy
            for name in sorted(head_components)
        },
        "external_snapshots": history._implementation_snapshots(
            head_targets, head_files, "HEAD.implementations"
        ),
        "asset_snapshots": head_asset_refs,
    }
    aspects = history.derive_aspects(before, after)
    if aspects != {"asset_snapshots", "declaration"}:
        raise ValueError(f"凍結履歴の aspect が設計値と不一致: {sorted(aspects)}")
    snapshot_root = root / _SNAPSHOTS
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for content in (
        *base_files.values(),
        *head_files.values(),
        *base_projections.values(),
        *head_projections.values(),
    ):
        _snapshot(snapshot_root, content)
    authority_name = history.validate_history_authority(head_assets)
    if authority_name != _AUTHORITY.as_posix():
        raise ValueError("想定外の凍結履歴 authority です")
    authority = head_assets[authority_name]
    control = authority["baseline_control"]
    base_runtime = base_components[
        RUNTIME_CONTRACT_ASSET.as_posix()
    ].current_identifiers
    head_runtime = head_components[
        RUNTIME_CONTRACT_ASSET.as_posix()
    ].current_identifiers
    if len(base_runtime) != 1 or len(head_runtime) != 1:
        raise ValueError("ランタイム契約の識別値が単一ではありません")
    for name in sorted(base_components):
        if name != RUNTIME_CONTRACT_ASSET.as_posix() and (
            base_components[name].current_identifiers
            != head_components[name].current_identifiers
        ):
            raise ValueError(f"ランタイム契約以外の識別値が動きました: {name}")
    record = {
        "record_schema_version": 2,
        "acceptance_id": _ACCEPTANCE_ID,
        "new_baseline_identifiers": {
            name: list(head_components[name].current_identifiers)
            for name in sorted(head_components)
        },
        "previous_baseline_identifiers": {
            name: list(base_components[name].current_identifiers)
            for name in sorted(base_components)
        },
        "change": {
            "subject": "TSK-443: ランタイム認可契約を同じパスで製品化する",
            "aspect": ["asset_snapshots", "declaration"],
            "before": before,
            "after": after,
        },
        "movement_fact": (
            "ランタイム契約を provisional から製品へ切り替え、superseded_by を除去し "
            "derived_from を最終製品資産へ向けた。保護関数は 33 件から 38 件、"
            "保護スキーマは 1 件から 2 件となった。関数の差分は migration "
            "0015・0016・0017・0024 で暫定資産が追随しなかった 4 件と "
            "authz_private の補助関数 1 件、スキーマの差分は authz_private である。"
            "保護対象の並びを辞書順へ変更した。この資産の "
            "v1 記録にある source_commit と承認の 2 欄は PR #72 のマージ後も"
            "受理値へ更新されておらず、追記のみの規律によって書き換えずに残した。"
            "比較元コミットは "
            f"{base_sha}。"
        ),
        "reason": (
            "TSK-424 PR B として U-T1 の暫定ランタイム契約を製品 DDL 資産から導いた"
            "値へ切り替える。暫定資産を削除せず同じパスで製品化するのは、"
            "2026-09-26 の人間の判断による。削除は現行検査器で必ず不合格となり、"
            "退去の機構は TSK-461 の射程である。凍結対象を製品資産へ向け直すと"
            "ファイル全体が凍結され、後続の RLS ポリシー変更も凍結基準の移動と"
            "なるため。"
        ),
        "approved_by": "DRYRUN",
        "approved_on": "1970-01-01",
    }
    control["history"].append(record)
    _write_json(root / _AUTHORITY, authority)
    history.validate_repository_histories(
        base_assets,
        _tenant_assets(root, None),
        base_implementations=base_files,
        head_implementations=head_files,
        base_snapshot_root=root / _SNAPSHOTS,
        head_snapshot_root=snapshot_root,
        evaluation_context=history.EvaluationContext(
            history.EvaluationMode.INVARIANT, None
        ),
    )


def _changed_corpus_paths(
    root: Path,
    base_sha: str,
    files: Sequence[Path],
    trees: Sequence[Path],
) -> tuple[str, ...]:
    """比較元と複製の corpus 入力をバイト単位で比べ、許可外の移動を拒否する。

    Args:
        root: 製品化途中の複製。
        base_sha: 比較元 S のコミット SHA。
        files: manifest が指定する単独ファイル。
        trees: manifest が指定するディレクトリ。

    Returns:
        動いた入力のリポジトリ相対パス。

    Raises:
        ValueError: 許可外の入力変更や既存 snapshot の変更がある場合。
    """
    paths = (*files, *trees, _CORPUS_MANIFEST)
    base_paths = {
        Path(name)
        for name in _git(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            base_sha,
            "--",
            *(path.as_posix() for path in paths),
        ).splitlines()
    }
    for relative_tree in trees:
        tree = root / relative_tree
        if tree.is_symlink() or not tree.is_dir():
            raise ValueError(
                f"corpus 入力の tree がディレクトリでない: {relative_tree}"
            )
    work_paths = {
        path
        for path in (*files, _CORPUS_MANIFEST)
        if (root / path).exists() or (root / path).is_symlink()
    } | {
        candidate.relative_to(root)
        for relative_tree in trees
        for candidate in (root / relative_tree).rglob("*")
        if not candidate.is_dir() or candidate.is_symlink()
    }
    changed = tuple(
        path
        for path in sorted(base_paths | work_paths)
        if path not in base_paths
        or path not in work_paths
        or (root / path).is_symlink()
        or not (root / path).is_file()
        or _git_bytes(root, base_sha, path.as_posix()) != (root / path).read_bytes()
    )
    fixed_assets = {_AUTHORITY, RUNTIME_CONTRACT_ASSET}
    unexpected = tuple(
        path
        for path in changed
        if not (
            path in fixed_assets
            and path in base_paths
            and path in work_paths
            and (root / path).is_file()
            and not (root / path).is_symlink()
        )
        and not (
            path.parent == _SNAPSHOTS
            and path not in base_paths
            and path in work_paths
            and (root / path).is_file()
            and not (root / path).is_symlink()
        )
    )
    if unexpected:
        raise ValueError(
            "許可外の corpus 入力変更: "
            + ", ".join(path.as_posix() for path in unexpected)
        )
    return tuple(path.as_posix() for path in changed)


def _refresh_corpus_digest(root: Path, base_sha: str) -> tuple[bool, tuple[str, ...]]:
    """許可した入力移動だけなら正本の関数で digest を取り直す。

    Args:
        root: 製品化途中の複製。
        base_sha: 比較元 S のコミット SHA。

    Returns:
        digest を取り直したかと、動いた入力パス。

    Raises:
        ValueError: 許可外の入力変更や manifest の想定外の差がある場合。
    """
    runner = _corpus_runner(root)
    manifest_path = root / _CORPUS_MANIFEST
    manifest = runner.load_manifest(manifest_path)
    inputs = manifest.corpus_inputs
    changed_paths = _changed_corpus_paths(root, base_sha, inputs.files, inputs.trees)
    actual = runner.corpus_input_digest(root, manifest)
    previous = inputs.digest
    if actual == previous:
        return False, changed_paths

    original = manifest_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    expected_line = f'"digest": "{previous}",'
    matching = [
        index for index, line in enumerate(lines) if line.strip() == expected_line
    ]
    if len(matching) != 1:
        raise ValueError("manifest.corpus_inputs.digest の行を一意に特定できません")
    updated_lines = list(lines)
    updated_lines[matching[0]] = lines[matching[0]].replace(previous, actual)
    if (
        sum(before != after for before, after in zip(lines, updated_lines, strict=True))
        != 1
    ):
        raise ValueError("manifest の digest 以外にも差分が生じました")
    _atomic_write(manifest_path, "".join(updated_lines))
    try:
        runner.validate_corpus_inputs(root, runner.load_manifest(manifest_path))
    except Exception:
        _atomic_write(manifest_path, original)
        raise
    return True, changed_paths


def _activate_product_spec(root: Path) -> None:
    """複製内の製品 DDL 資産の参照を最終パスへ切り替える。"""
    path = root / _SPEC
    source = path.read_text(encoding="utf-8")
    old = f'ddl_elements_path=PurePosixPath("{STAGED_PRODUCT_ASSET.as_posix()}")'
    new = f'ddl_elements_path=PurePosixPath("{PRODUCT_ASSET.as_posix()}")'
    if source.count(old) != 1:
        raise ValueError("PRODUCT_SPEC の staged パスを一意に置換できません")
    path.write_text(source.replace(old, new), encoding="utf-8")


def build_dryrun(source_root: Path, destination: Path) -> DryrunResult:
    """現在の HEAD の複製で最終コミットを作り、その tree SHA を返す。

    Args:
        source_root: 実作業ツリーのルート。
        destination: 存在しない一時複製のパス。

    Returns:
        比較元 S、親 H、tree D と複製先。
    """
    if find_repository_root(source_root) != source_root.resolve():
        raise ValueError("contracts/ と .git を持つ作業ツリーだけで実行できます")
    base_sha = _git(source_root, "rev-parse", "origin/develop^{commit}")
    head_sha = _git(source_root, "rev-parse", "HEAD^{commit}")
    subprocess.run(
        [
            "git",
            "clone",
            "--local",
            "--no-hardlinks",
            str(source_root),
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if _git(destination, "rev-parse", "HEAD") != head_sha:
        raise ValueError("複製の HEAD が実作業ツリーと一致しません")
    runner = _corpus_runner(destination)
    manifest = runner.load_manifest(destination / _CORPUS_MANIFEST)
    _changed_corpus_paths(
        destination,
        base_sha,
        manifest.corpus_inputs.files,
        manifest.corpus_inputs.trees,
    )
    _git(destination, "update-ref", "refs/remotes/origin/develop", base_sha)
    _git(destination, "mv", STAGED_PRODUCT_ASSET.as_posix(), PRODUCT_ASSET.as_posix())
    product = read_json_object(destination / PRODUCT_ASSET)
    product.pop("pending_switch")
    product.pop("provisional_contract_additions")
    _write_json(destination / PRODUCT_ASSET, product)
    _activate_product_spec(destination)
    switch_repository(destination, base_sha)
    _append_history(destination, base_sha)
    corpus_digest_updated, corpus_changed_paths = _refresh_corpus_digest(
        destination, base_sha
    )
    _git(
        destination,
        "add",
        "-A",
        "contracts",
        _SPEC.as_posix(),
        RUNTIME_CONTRACT_ASSET.as_posix(),
        "backend/src/pitchlog/authz/runtime_contract.py",
        _CORPUS_MANIFEST.as_posix(),
    )
    _git(
        destination,
        "-c",
        "user.name=Runtime Contract Dryrun",
        "-c",
        "user.email=runtime-contract@example.invalid",
        "commit",
        "-m",
        "feat: ランタイム認可契約の製品化ドライラン",
    )
    if _git(destination, "rev-parse", "HEAD^1") != head_sha:
        raise ValueError("ドライランコミットの親が H と不一致です")
    return DryrunResult(
        base_sha,
        head_sha,
        _git(destination, "rev-parse", "HEAD^{tree}"),
        destination,
        corpus_digest_updated,
        corpus_changed_paths,
    )


def _verify_pr_acceptance(result: DryrunResult) -> None:
    """同じ tree の二親 merge を作り、凍結検査の PR 受理経路を実行する。"""
    root = result.repository
    final_sha = _git(root, "rev-parse", "HEAD")
    merge_sha = _git(
        root,
        "-c",
        "user.name=Runtime Contract Dryrun",
        "-c",
        "user.email=runtime-contract@example.invalid",
        "commit-tree",
        result.tree_sha,
        "-p",
        result.base_sha,
        "-p",
        final_sha,
        "-m",
        "dryrun pull request merge",
    )
    event = {
        "repository": {"full_name": "masaki1025/pitchlog"},
        "pull_request": {
            "number": 87,
            "base": {"ref": "develop", "sha": result.base_sha},
            "head": {"sha": final_sha},
        },
    }
    with tempfile.TemporaryDirectory(prefix="runtime-contract-event-") as directory:
        event_path = Path(directory) / "event.json"
        _write_json(event_path, event)
        _git(root, "checkout", "--detach", merge_sha)
        env = {
            **os.environ,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_WORKSPACE": str(root),
        }
        try:
            result_process = subprocess.run(
                [sys.executable, str(root / "scripts/check_tenant_boundary_bypass.py")],
                cwd=root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if result_process.returncode:
                raise ValueError(
                    "PR 受理モードの迂回検査に失敗: "
                    f"{result_process.stdout}\n{result_process.stderr}"
                )
        finally:
            _git(root, "checkout", "--detach", final_sha)


def main(argv: Sequence[str] | None = None) -> int:
    """複製内の製品化と受理検査を実行し、S・H・D を表示する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="作成する複製のパス")
    args = parser.parse_args(argv)
    root = find_repository_root(Path.cwd())
    if root is None:
        print("エラー: リポジトリの作業ツリーが見つかりません", file=sys.stderr)
        return 2
    destination = (
        args.output
        or Path(tempfile.mkdtemp(prefix="runtime-contract-dryrun-")) / "repository"
    )
    try:
        result = build_dryrun(root, destination)
        _verify_pr_acceptance(result)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print(f"S={result.base_sha}\nH={result.head_sha}\nD={result.tree_sha}")
    print(f"corpus digest: {'取り直した' if result.corpus_digest_updated else '不要'}")
    print("corpus inputs changed:")
    for path in result.corpus_changed_paths:
        print(f"  {path}")
    if not result.corpus_changed_paths:
        print("  (なし)")
    print(f"COPY={result.repository}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
