"""tenant-isolation のアプリケーション paths を固定する回帰テスト。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).parent.parent
CORE_AREAS_PATH = REPOSITORY_ROOT / ".claude" / "core-areas.json"
CORE_GUARD_SCRIPT = REPOSITORY_ROOT / "scripts" / "core_guard.py"
EXPECTED_APPLICATION_PATHS = frozenset(
    {
        "backend/src/pitchlog/api/**",
        "backend/src/pitchlog/services/**",
    }
)
APPLICATION_PATH_PREFIXES = (
    "backend/src/pitchlog/api/",
    "backend/src/pitchlog/services/",
)


def _load_core_guard_module() -> Any:
    """実際の core_guard.py を検出ロジックの正として読み込む。"""
    module_name = "core_guard_tenant_isolation_paths_under_test"
    spec = importlib.util.spec_from_file_location(module_name, CORE_GUARD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_configuration() -> dict[str, Any]:
    """実リポジトリのコア領域設定を読み込む。"""
    configuration = json.loads(CORE_AREAS_PATH.read_text(encoding="utf-8"))
    assert isinstance(configuration, dict)
    return configuration


def _tenant_isolation_paths(configuration: dict[str, Any]) -> list[str]:
    """tenant-isolation の paths を取得する。"""
    area = next(
        area
        for area in configuration["areas"]
        if area["id"] == "tenant-isolation"
    )
    paths = area["paths"]
    assert isinstance(paths, list)
    assert all(isinstance(path, str) for path in paths)
    return paths


def _assert_application_paths_are_exact(configuration: dict[str, Any]) -> None:
    """対象2ディレクトリの登録を exact-set で検証する。"""
    actual = frozenset(
        path
        for path in _tenant_isolation_paths(configuration)
        if path.startswith(APPLICATION_PATH_PREFIXES)
    )
    assert actual == EXPECTED_APPLICATION_PATHS, (
        "tenant-isolation のアプリケーション paths が期待集合と不一致"
    )


def test_tenant_isolation_application_paths_match_changed_files() -> None:
    """追加した2パターンが各ディレクトリの変更を検出する。"""
    core_guard = _load_core_guard_module()
    paths = _tenant_isolation_paths(_load_configuration())
    tenant_isolation = core_guard.CoreAreas(
        path_patterns=tuple(paths),
        guard_paths=frozenset(),
    )
    changed_paths = [
        "backend/src/pitchlog/api/routes.py",
        "backend/src/pitchlog/services/game_service.py",
    ]

    assert core_guard.matched_paths(changed_paths, tenant_isolation) == changed_paths


@pytest.mark.parametrize("missing_path", sorted(EXPECTED_APPLICATION_PATHS))
def test_missing_tenant_isolation_application_path_is_rejected(
    missing_path: str,
) -> None:
    """追加した2パターンのどちらを外しても exact-set 検査を red にする。"""
    configuration = _load_configuration()
    _tenant_isolation_paths(configuration).remove(missing_path)

    with pytest.raises(
        AssertionError,
        match="tenant-isolation のアプリケーション paths が期待集合と不一致",
    ):
        _assert_application_paths_are_exact(configuration)


def test_tenant_isolation_application_paths_are_exact() -> None:
    """実設定に対象2パターンが過不足なく登録されている。"""
    _assert_application_paths_are_exact(_load_configuration())
