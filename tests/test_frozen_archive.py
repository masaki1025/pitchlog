"""凍結 archive の構造的 snapshot 参照抽出を検証する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts/frozen_archive.py"
FROZEN_HISTORY_SCRIPT = REPOSITORY_ROOT / "scripts/frozen_history.py"
AUTHORITY = REPOSITORY_ROOT / "contracts/tenant_boundary/base-allowlist.json"
SNAPSHOT_ROOT = REPOSITORY_ROOT / "contracts/tenant_boundary/history-snapshots"


def _load_archive() -> ModuleType:
    """参照抽出器をリポジトリの import 設定に依存せず読む。"""
    spec = importlib.util.spec_from_file_location(
        "frozen_archive_under_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


archive = _load_archive()


def _current_history() -> list[dict[str, Any]]:
    """現行 authority の v1・v2 混在履歴を独立コピーで返す。"""
    asset = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    history = asset["baseline_control"]["history"]
    assert isinstance(history, list)
    return copy.deepcopy(history)


def _write_snapshot(snapshot_root: Path, content: bytes) -> str:
    """テスト用 content-addressed snapshot を書き、ファイル名を返す。"""
    digest = hashlib.sha256(content).hexdigest()
    snapshot_root.mkdir(parents=True, exist_ok=True)
    (snapshot_root / digest).write_bytes(content)
    return digest


def _snapshot_item(digest: str) -> dict[str, str]:
    """有効な v2 snapshot 行を作る。"""
    return {
        "path": "scripts/example.py",
        "sha256": digest,
        "snapshot_ref": f"{archive.frozen_history.SNAPSHOT_REF_PREFIX}{digest}",
    }


def _v2_history(item: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """参照抽出に必要な最小 v2 履歴を作る。"""
    snapshots = [] if item is None else [item]
    state = {
        "declaration": {},
        "movement_policy": {},
        "external_snapshots": snapshots,
        "asset_snapshots": [],
    }
    return [
        {
            "record_schema_version": 2,
            "change": {
                "before": copy.deepcopy(state),
                "after": copy.deepcopy(state),
            },
        }
    ]


def _current_references() -> frozenset[str]:
    """現行履歴が正常であることを確認して参照集合を返す。"""
    return archive.extract_referenced_snapshot_names(
        _current_history(),
        SNAPSHOT_ROOT,
    )


def test_current_mixed_history_has_18_unique_snapshot_references() -> None:
    """現行の v1・v2 混在履歴から一意参照18件を再現する。"""
    history = _current_history()
    assert [record.get("record_schema_version", 1) for record in history] == [1, 2]

    references = archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)

    assert len(references) == 18
    assert references <= {path.name for path in SNAPSHOT_ROOT.iterdir()}


def test_added_aspect_is_red_after_current_table_is_green(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ASPECT_NAMES の第5キー追加を抽出表の未更新として拒否する。"""
    assert len(_current_references()) == 18
    monkeypatch.setattr(
        archive.frozen_history,
        "ASPECT_NAMES",
        archive.frozen_history.ASPECT_NAMES | {"retired_history"},
    )

    with pytest.raises(archive.ContractError, match="キー集合が不一致"):
        _current_references()


@pytest.mark.parametrize(
    "aspect",
    [
        "declaration",
        "movement_policy",
        "external_snapshots",
        "asset_snapshots",
    ],
)
def test_reversed_aspect_classification_is_red_after_current_table_is_green(
    monkeypatch: pytest.MonkeyPatch,
    aspect: str,
) -> None:
    """4キーそれぞれの参照分類反転を exact-map 不一致として拒否する。"""
    assert len(_current_references()) == 18
    mutated = dict(archive.ASPECT_REFERENCE_KINDS)
    current = mutated[aspect]
    mutated[aspect] = (
        archive.AspectReferenceKind.SNAPSHOT_ARRAY
        if current is archive.AspectReferenceKind.NONE
        else archive.AspectReferenceKind.NONE
    )
    monkeypatch.setattr(archive, "ASPECT_REFERENCE_KINDS", mutated)

    with pytest.raises(archive.ContractError, match="分類値が期待表と不一致"):
        _current_references()


@pytest.mark.parametrize("aspect", ["declaration", "movement_policy"])
def test_reference_shaped_value_in_non_reference_aspect_is_not_extracted(
    tmp_path: Path,
    aspect: str,
) -> None:
    """参照なしの2分類に有効な参照形があっても抽出対象にしない。"""
    digest = _write_snapshot(tmp_path, b"unrelated structured value\n")
    history = _v2_history()
    reference = f"{archive.frozen_history.SNAPSHOT_REF_PREFIX}{digest}"
    for side in ("before", "after"):
        history[0]["change"][side][aspect]["decoy"] = {
            "snapshot_ref": reference
        }

    assert archive.extract_referenced_snapshot_names(history, tmp_path) == frozenset()


def test_v1_record_forced_through_v2_shape_is_red_after_mixed_history_is_green() -> None:
    """2キーだけの v1 state を v2 として走査すると拒否する。"""
    history = _current_history()
    assert len(
        archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)
    ) == 18
    history[0]["record_schema_version"] = 2

    with pytest.raises(archive.ContractError, match="キー集合が不一致"):
        archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)


def test_missing_v2_snapshot_ref_is_red_after_current_history_is_green() -> None:
    """v2 の参照フィールド欠落を拒否する。"""
    history = _current_history()
    assert len(
        archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)
    ) == 18
    del history[1]["change"]["before"]["external_snapshots"][0][
        "snapshot_ref"
    ]

    with pytest.raises(archive.ContractError, match="キー集合が不一致"):
        archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)


def test_unrelated_hex_values_are_not_snapshot_references(tmp_path: Path) -> None:
    """射影digest・source_digest・識別値のhexを参照へ混入させない。"""
    digest = hashlib.sha256(b"not a snapshot reference").hexdigest()
    clean_history = _v2_history()
    assert (
        archive.extract_referenced_snapshot_names(clean_history, tmp_path)
        == frozenset()
    )
    history: list[dict[str, Any]] = [
        {
            "change": {
                "before": {
                    "state": "PRESENT",
                    "frozen_projection_sha256": digest,
                },
                "after": {
                    "state": "PRESENT",
                    "frozen_projection_sha256": digest,
                },
            }
        },
        copy.deepcopy(clean_history[0]),
    ]
    history[1]["source_digest"] = digest
    history[1]["new_baseline_identifiers"] = {
        "asset.json": [f"contract_revision:{digest}"]
    }
    history[1]["previous_baseline_identifiers"] = {
        "asset.json": [f"contract_revision:{digest}"]
    }
    for side in ("before", "after"):
        history[1]["change"][side]["declaration"]["source_digest"] = digest

    assert archive.extract_referenced_snapshot_names(history, tmp_path) == frozenset()


@pytest.mark.parametrize("mutation", ["prefix", "length", "missing-file"])
def test_invalid_reference_is_red_after_valid_reference_is_green(
    tmp_path: Path,
    mutation: str,
) -> None:
    """prefix・桁数・実ファイル不在の各参照を拒否する。"""
    digest = _write_snapshot(tmp_path, b"referenced snapshot\n")
    history = _v2_history(_snapshot_item(digest))
    assert archive.extract_referenced_snapshot_names(history, tmp_path) == {
        digest
    }

    item = history[0]["change"]["before"]["external_snapshots"][0]
    if mutation == "prefix":
        item["snapshot_ref"] = f"invalid-history-snapshots/{digest}"
    elif mutation == "length":
        short_digest = digest[:-1]
        item["sha256"] = short_digest
        item["snapshot_ref"] = (
            f"{archive.frozen_history.SNAPSHOT_REF_PREFIX}{short_digest}"
        )
    else:
        (tmp_path / digest).unlink()

    with pytest.raises(archive.ContractError):
        archive.extract_referenced_snapshot_names(history, tmp_path)


def test_import_direction_is_only_frozen_archive_to_frozen_history() -> None:
    """依存方向が frozen_archive から frozen_history への一方向だと示す。"""
    archive_tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    history_tree = ast.parse(FROZEN_HISTORY_SCRIPT.read_text(encoding="utf-8"))

    def imported_modules(tree: ast.AST) -> set[str]:
        """AST に現れる静的 import のモジュール名を返す。"""
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules.add(node.module)
        return modules

    assert "frozen_history" in imported_modules(archive_tree)
    assert "frozen_archive" not in imported_modules(history_tree)
    assert dict(archive.RECORD_REFERENCE_EXTRACTORS) == {}
