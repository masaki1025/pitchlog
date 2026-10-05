"""凍結基準の受理記録と snapshot の雛形を組み立てる CLI。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_SOURCE_ROOT = Path(__file__).resolve().parents[4]
_SNAPSHOT_DIRECTORY = Path("contracts/tenant_boundary/history-snapshots")


def _history_module() -> Any:
    """同じリポジトリの凍結履歴検査器を再利用する。"""
    scripts = str(_SOURCE_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("frozen_history")


def _git(repository_root: Path, *arguments: str) -> bytes:
    """Git の出力を bytes で取得する。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"git {' '.join(arguments)} に失敗しました")
    return result.stdout


def build_acceptance_template(
    base_assets: Mapping[str, object],
    head_assets: Mapping[str, object],
    *,
    base_implementations: Mapping[str, bytes],
    head_implementations: Mapping[str, bytes],
    head_snapshot_root: Path,
    acceptance_id: str,
    approved_by: str,
    approved_on: str,
    reason: str,
    movement_fact: str,
) -> dict[str, object]:
    """実差分から v2 記録と不足する snapshot の出力束を作る。

    Args:
        base_assets: 比較元の tenant_boundary JSON 資産集合。
        head_assets: 受理後の tenant_boundary JSON 資産集合。
        base_implementations: 比較元の外部凍結対象の内容。
        head_implementations: 受理後の外部凍結対象の内容。
        head_snapshot_root: 受理後の既存 snapshot ディレクトリ。
        acceptance_id: PR の owner/repository#number。
        approved_by: 受理者名。
        approved_on: 受理日。
        reason: 受理の理由。
        movement_fact: 観測した移動の事実。

    Returns:
        authority、v2 記録、追記に必要な snapshot の base64 表現。
    """
    history = _history_module()
    authority = history.validate_history_authority(head_assets)
    history._validate_base_authority_migration(base_assets, authority)
    base_components = history._repository_components(base_assets, "比較元")
    head_components = history._repository_components(head_assets, "HEAD")
    if base_components[authority].history != head_components[authority].history:
        raise ValueError("authority の history は雛形を作る前に追記できません")
    base_names = sorted(base_components)
    head_names = sorted(head_components)
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
    before_assets, base_projection_bytes = history._asset_projection_snapshots(
        base_assets, base_implementations, "比較元"
    )
    after_assets, head_projection_bytes = history._asset_projection_snapshots(
        head_assets, head_implementations, "HEAD"
    )
    before = {
        "declaration": {name: base_components[name].declaration for name in base_names},
        "movement_policy": {
            name: base_components[name].movement_policy for name in base_names
        },
        "external_snapshots": history._implementation_snapshots(
            base_targets, base_implementations, "比較元.implementations"
        ),
        "asset_snapshots": before_assets,
    }
    after = {
        "declaration": {name: head_components[name].declaration for name in head_names},
        "movement_policy": {
            name: head_components[name].movement_policy for name in head_names
        },
        "external_snapshots": history._implementation_snapshots(
            head_targets, head_implementations, "HEAD.implementations"
        ),
        "asset_snapshots": after_assets,
    }
    aspects = history.derive_aspects(before, after)
    if not aspects:
        raise ValueError("受理記録に対応する実差分がありません")
    previous = {
        name: list(base_components[name].current_identifiers)
        if name in base_components
        else ["NO_BASELINE"]
        for name in head_names
    }
    current = {
        name: list(head_components[name].current_identifiers) for name in head_names
    }
    record: dict[str, object] = {
        "record_schema_version": 2,
        "acceptance_id": acceptance_id,
        "previous_baseline_identifiers": previous,
        "new_baseline_identifiers": current,
        "change": {
            "subject": f"{acceptance_id} の製品認可契約の受理",
            "aspect": sorted(aspects),
            "before": before,
            "after": after,
        },
        "movement_fact": movement_fact,
        "reason": reason,
        "approved_by": approved_by,
        "approved_on": approved_on,
    }
    history._validate_acceptance_id(acceptance_id, "acceptance_id")
    history._validate_iso_date(
        history._nonempty_string(approved_on, "approved_on"), "approved_on"
    )
    for field in ("approved_by", "reason", "movement_fact"):
        history._nonempty_string(record[field], field)
    history._reject_v2_reserved_markers(record, "acceptance_template")

    contents = (
        *[base_implementations[path] for path in base_targets],
        *[head_implementations[path] for path in head_targets],
        *base_projection_bytes.values(),
        *head_projection_bytes.values(),
    )
    existing = history._read_snapshot_directory(head_snapshot_root, "HEAD.snapshots")
    missing: dict[str, bytes] = {}
    for content in contents:
        digest = hashlib.sha256(content).hexdigest()
        if digest not in existing:
            missing[digest] = content
    return {
        "authority_asset": authority,
        "record": record,
        "snapshots_base64": {
            digest: base64.b64encode(content).decode("ascii")
            for digest, content in sorted(missing.items())
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """指定した比較元と作業木から雛形をリポジトリ外へ出力する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=_SOURCE_ROOT)
    parser.add_argument("--base", required=True)
    parser.add_argument("--acceptance-id", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-on", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--movement-fact", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.repository.resolve()
    try:
        if args.output is not None and args.output.resolve().is_relative_to(root):
            raise ValueError("出力先はリポジトリ外を指定してください")
        base_sha = (
            _git(root, "rev-parse", "--verify", f"{args.base}^{{commit}}")
            .decode()
            .strip()
        )
        _git(root, "merge-base", "--is-ancestor", base_sha, "HEAD")
        paths = (
            _git(
                root,
                "ls-tree",
                "-r",
                "--name-only",
                base_sha,
                "contracts/tenant_boundary",
            )
            .decode()
            .splitlines()
        )
        base_paths = sorted(
            path
            for path in paths
            if path.startswith("contracts/tenant_boundary/") and path.endswith(".json")
        )
        head_paths = sorted(
            path.relative_to(root).as_posix()
            for path in (root / "contracts/tenant_boundary").glob("*.json")
        )
        base_assets = {
            path: json.loads(_git(root, "show", f"{base_sha}:{path}"))
            for path in base_paths
        }
        head_assets = {
            path: json.loads((root / path).read_bytes()) for path in head_paths
        }
        history = _history_module()
        base_components = history._repository_components(base_assets, "比較元")
        head_components = history._repository_components(head_assets, "HEAD")
        base_targets = sorted(
            {
                path
                for component in base_components.values()
                for path in component.external_files
            }
        )
        head_targets = sorted(
            {
                path
                for component in head_components.values()
                for path in component.external_files
            }
        )
        bundle = build_acceptance_template(
            base_assets,
            head_assets,
            base_implementations={
                path: _git(root, "show", f"{base_sha}:{path}") for path in base_targets
            },
            head_implementations=history._read_external_implementations(
                root, head_targets, "HEAD.external_files"
            ),
            head_snapshot_root=root / _SNAPSHOT_DIRECTORY,
            acceptance_id=args.acceptance_id,
            approved_by=args.approved_by,
            approved_on=args.approved_on,
            reason=args.reason,
            movement_fact=args.movement_fact,
        )
        output = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            print(output, end="")
        else:
            args.output.write_text(output, encoding="utf-8")
        return 0
    except (OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
