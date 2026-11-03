"""採用済み0036製品profileをGitの固定データから忠実に供給する。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import pytest

from pitchlog.authz import product_catalog, product_provisioning
from pitchlog.authz.asset_spec import PRODUCT_SPEC
from pitchlog.authz.ddl import generate_authz_ddl

_FIXTURE = Path(__file__).parent / "fixtures/product_authz_legacy_profile_v0036.json"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def legacy_profile_metadata() -> dict:
    """重複・型・未知fieldを閉じた固定metadataを読む。"""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("legacy metadataの重複key")
            result[key] = value
        return result

    document = json.loads(_FIXTURE.read_text(), object_pairs_hook=unique)
    if (
        type(document) is not dict
        or set(document) != {"schema_version", "revision", "files"}
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or type(document["revision"]) is not str
        or re.fullmatch(r"[0-9a-f]{40}", document["revision"]) is None
        or type(document["files"]) is not list
    ):
        raise ValueError("legacy metadataの形が不正")
    seen = set()
    for row in document["files"]:
        if type(row) is not dict or set(row) != {"path", "sha256"}:
            raise ValueError("legacy metadata行が不正")
        path, digest = row["path"], row["sha256"]
        if (
            type(path) is not str
            or not path
            or PurePosixPath(path).as_posix() != path
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or path in seen
            or type(digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("legacy metadataのpath/hashが不正")
        seen.add(path)
    return document


def legacy_file(path: str) -> bytes:
    """metadataの有限pathだけを固定Gitからhash照合して読む。"""
    metadata = legacy_profile_metadata()
    row = next((row for row in metadata["files"] if row["path"] == path), None)
    if row is None:
        raise ValueError("未登録のlegacy path")
    data = subprocess.check_output(
        ["git", "show", f"{metadata['revision']}:{path}"], cwd=_REPOSITORY_ROOT
    )
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("legacy Git blobのhashが不一致")
    return data


def materialize_legacy_profile(destination: Path) -> Path:
    """固定Git全byteを照合して隔離rootへ写し、公開DDL生成器で読む。"""
    metadata = legacy_profile_metadata()
    if destination.resolve().is_relative_to(_REPOSITORY_ROOT.resolve()):
        raise ValueError("legacy供給先は実repository外の新規rootが必要")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("legacy供給先の既存dataへfallbackしない")
    destination.mkdir(parents=True, exist_ok=True)
    for row in metadata["files"]:
        data = subprocess.check_output(
            ["git", "show", f"{metadata['revision']}:{row['path']}"],
            cwd=_REPOSITORY_ROOT,
        )
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("legacy Git blobのhashが不一致")
        target = destination / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    # 検査コードとGit履歴は現物を参照し、旧コード/固定成功を供給しない。
    for name in ("scripts", ".git"):
        link = destination / name
        if not link.exists():
            link.symlink_to(
                _REPOSITORY_ROOT / name, target_is_directory=name == "scripts"
            )
    statements = generate_authz_ddl(destination, PRODUCT_SPEC)
    if len(statements) != 380:
        raise ValueError("legacy SQLのexact380集合が不一致")
    return destination


def verify_legacy_migration_sources() -> None:
    """実行する0036までの現migrationが採用済み固定byteと同じか検査する。"""
    for row in legacy_profile_metadata()["files"]:
        if row["path"].startswith("backend/migrations/versions/"):
            if (
                hashlib.sha256(
                    (_REPOSITORY_ROOT / row["path"]).read_bytes()
                ).hexdigest()
                != row["sha256"]
            ):
                raise ValueError("旧migrationの実行sourceが固定版と不一致")


def require_bound_profile(root: Path) -> None:
    """データ読取先の混在やlegacy context寿命外の再利用を拒否する。"""
    if (
        product_provisioning._REPOSITORY_ROOT != root
        or product_catalog._REPOSITORY_ROOT != root
    ):
        raise ValueError("profileのデータcontextが不一致")


@contextmanager
def legacy_profile_context(
    monkeypatch: pytest.MonkeyPatch, destination: Path
) -> Iterator[Path]:
    """データ読取先だけを旧profileへ束縛し、公開実装/検査器を使い続ける。"""
    root = materialize_legacy_profile(destination)
    with monkeypatch.context() as context:
        context.setattr(product_provisioning, "_REPOSITORY_ROOT", root)
        context.setattr(product_catalog, "_REPOSITORY_ROOT", root)
        context.setattr(
            product_catalog,
            "_MIGRATION_BATCH_ROLE_PATH",
            root / "contracts/authz/product/migration-batch-role.json",
        )
        context.setattr(
            product_catalog,
            "_SCHEMA_MANIFEST_PATH",
            root / "contracts/db/schema-manifest.json",
        )
        yield root
