"""領域シードの登録境界と打球方向契約のクライアント非参照を検査する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK_SETS_PATH = Path("backend/domain/check-sets.json")
SEED_PATH = "contracts/field-regions/field_region_seed_v1.json"
DIRECTION_REFERENCE = re.compile(r"batted[-_]?ball[-_]?direction", re.IGNORECASE)
# backend/domain をディレクトリごと指す参照(エイリアス + glob)は、契約名を
# 書かずに打球方向契約へ到達できるので禁じる。一方、同じディレクトリには
# D-2 のランタイム契約(history-depth.json・check-sets.json)も置かれており、
# それを名指しする参照は正当である。したがって backend/domain の直後に
# ファイル名が続かない参照だけを違反とする。
DOMAIN_DIRECTORY_REFERENCE = re.compile(
    r"backend[/\\]domain(?![/\\][\w.-]+\.json)", re.IGNORECASE
)
BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"})
IGNORED_DIRECTORIES = frozenset({"node_modules", "dist", "coverage", ".cache", ".vite"})


def _manifest_registration_path(root: Path) -> Path:
    """登録先を check-sets の宣言から解決する。

    Args:
        root: リポジトリまたは合成ファイルのルート。

    Returns:
        3 層の登録マニフェストのパス。
    """
    check_sets = json.loads((root / CHECK_SETS_PATH).read_text(encoding="utf-8"))
    sources = [
        item["source"]
        for item in check_sets["checkSets"]
        if item["id"] == "manifest-registrations"
    ]
    assert len(sources) == 1, "3 層の登録先が一意でない"
    return root / sources[0]


def _assert_seed_not_three_layer_registered(manifest_path: Path) -> None:
    """ベクタ・性質・変異の登録欄に領域シードがないことを検査する。

    Args:
        manifest_path: 3 層の登録マニフェスト。
    """
    # 段階①では manifest.json が未生成。後から作られたときは同じ検査を適用する。
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    calculations: Any = manifest["calculations"]
    assert isinstance(calculations, list), "3 層の calculations が配列でない"
    for calculation in calculations:
        assert isinstance(calculation, dict), "3 層の calculation がオブジェクトでない"
        for layer, path_key in (
            ("vectors", "path"),
            ("properties", "path"),
            ("mutation", "target"),
        ):
            registrations = calculation[layer]
            assert isinstance(registrations, list), f"3 層の {layer} が配列でない"
            for registration in registrations:
                assert isinstance(registration, dict), f"3 層の {layer} の要素が不正"
                assert registration[path_key] != SEED_PATH, (
                    f"領域シードを 3 層の {layer} へ登録している"
                )


def _assert_frontend_has_no_direction_reference(frontend_root: Path) -> None:
    """frontend のソース・設定で打球方向契約への参照を検出する。

    Args:
        frontend_root: 走査する frontend ディレクトリ。
    """
    references: list[str] = []
    for directory, directories, files in os.walk(frontend_root):
        directories[:] = sorted(set(directories) - IGNORED_DIRECTORIES)
        for filename in sorted(files):
            path = Path(directory) / filename
            if path.suffix in BINARY_SUFFIXES:
                continue
            relative = path.relative_to(frontend_root)
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            haystacks = (relative.as_posix(), content)
            if any(
                pattern.search(haystack)
                for pattern in (DIRECTION_REFERENCE, DOMAIN_DIRECTORY_REFERENCE)
                for haystack in haystacks
            ):
                references.append(relative.as_posix())
    assert not references, f"frontend が打球方向契約を参照している: {references}"


def test_repository_seed_is_not_registered_in_three_layers() -> None:
    """領域シードを 3 層の登録対象にしない。"""
    _assert_seed_not_three_layer_registered(_manifest_registration_path(ROOT))


@pytest.mark.parametrize(
    ("layer", "path_key"),
    [("vectors", "path"), ("properties", "path"), ("mutation", "target")],
)
def test_registered_seed_is_rejected(tmp_path: Path, layer: str, path_key: str) -> None:
    """合成した 3 層への領域シード登録を拒否する。

    Args:
        tmp_path: 合成マニフェストの配置先。
        layer: 登録先の層。
        path_key: 登録欄のパスキー。
    """
    manifest_path = tmp_path / "manifest.json"
    calculation: dict[str, list[dict[str, str]]] = {
        "vectors": [], "properties": [], "mutation": []
    }
    calculation[layer].append({path_key: SEED_PATH})
    manifest_path.write_text(json.dumps({"calculations": [calculation]}), encoding="utf-8")
    with pytest.raises(AssertionError, match=f"領域シードを 3 層の {layer} へ登録"):
        _assert_seed_not_three_layer_registered(manifest_path)


def test_repository_frontend_has_no_direction_contract_reference() -> None:
    """打球方向契約を frontend のソース・設定が参照しない。"""
    _assert_frontend_has_no_direction_reference(ROOT / "frontend")


@pytest.mark.parametrize(
    ("relative_path", "contents"),
    [
        (
            "src/direction.spec.ts",
            "import '@contracts/../backend/domain/batted_ball_direction_contract_v1.json'",
        ),
        (
            "vite.config.ts",
            "alias: {'@direction': '../backend/domain/batted_ball_direction_contract_v1.json'}",
        ),
        (
            "src/direction.ts",
            "const path = '../backend/domain/batted_ball_direction_contract_v1.json'",
        ),
        (
            "vite.config.ts",
            "alias: {'@domain': '../backend/domain'}; import.meta.glob('@domain/*.json')",
        ),
    ],
)
def test_frontend_direction_reference_is_rejected(
    tmp_path: Path, relative_path: str, contents: str
) -> None:
    """合成した import・エイリアス設定・パス文字列を拒否する。

    Args:
        tmp_path: 合成 frontend の配置先。
        relative_path: 参照を記述する相対パス。
        contents: ファイルに書く参照文字列。
    """
    frontend_root = tmp_path / "frontend"
    source = frontend_root / relative_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(contents, encoding="utf-8")
    with pytest.raises(AssertionError, match="frontend が打球方向契約を参照"):
        _assert_frontend_has_no_direction_reference(frontend_root)


@pytest.mark.parametrize(
    "contents",
    [
        "const sets = await import('backend/domain/check-sets.json')",
        "'backend/domain/history-depth.json': { depth: 1 }",
        "import depth from '../../backend/domain/history-depth.json'",
    ],
)
def test_frontend_domain_runtime_reference_is_allowed(tmp_path: Path, contents: str) -> None:
    """D-2 のランタイム契約を名指しする参照は違反にしない。

    打球方向契約と同じ backend/domain に置かれているが別の資産であり、
    frontend から参照されることが正当である((β)⑦ とは無関係)。

    Args:
        tmp_path: 合成 frontend の配置先。
        contents: ファイルに書く参照文字列。
    """
    frontend_root = tmp_path / "frontend"
    source = frontend_root / "src/testing/handoffLoader.ts"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(contents, encoding="utf-8")
    _assert_frontend_has_no_direction_reference(frontend_root)
