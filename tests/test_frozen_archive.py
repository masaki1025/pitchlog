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
CASE_RUNNER_SCRIPT = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "frozen-archive-cases"
    / "runner.py"
)


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


def _load_case_runner() -> ModuleType:
    """ステップ6の合成 PR リポジトリ runner をロードする。"""
    spec = importlib.util.spec_from_file_location(
        "frozen_archive_fail_closed_case_runner",
        CASE_RUNNER_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


case_runner = _load_case_runner()
CASE_MANIFEST = case_runner.load_manifest()


def _current_history() -> list[dict[str, Any]]:
    """現行 authority の v1・v2 混在履歴を独立コピーで返す。"""
    asset = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    history = asset["baseline_control"]["history"]
    assert isinstance(history, list)
    return copy.deepcopy(history)


def _expected_references() -> frozenset[str]:
    """生の履歴から被検査の抽出器を使わず参照集合を導出する。"""
    prefix = archive.frozen_history.SNAPSHOT_REF_PREFIX
    return frozenset(
        name
        for record in _current_history()
        if record.get("record_schema_version") == 2
        for aspect in ("external_snapshots", "asset_snapshots")
        for side in ("before", "after")
        for entry in record["change"][side][aspect]
        if (name := entry["snapshot_ref"].removeprefix(prefix))
    )


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


def test_current_mixed_history_matches_independent_snapshot_references() -> None:
    """現行の v1・v2 混在履歴の参照集合を独立算出と照合する。"""
    history = _current_history()
    versions = [record.get("record_schema_version", 1) for record in history]
    assert len(versions) >= 2  # v1 と v2 が混在しうる長さを要求する
    assert versions[0] == 1  # bootstrap は v1
    assert set(versions[1:]) == {2}  # 以降はすべて v2

    references = archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)

    expected = _expected_references()
    assert references == expected
    assert expected
    assert references <= {path.name for path in SNAPSHOT_ROOT.iterdir()}


def test_added_aspect_is_red_after_current_table_is_green(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ASPECT_NAMES の第5キー追加を抽出表の未更新として拒否する。"""
    expected = _expected_references()
    assert _current_references() == expected
    assert expected
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
    expected = _expected_references()
    assert _current_references() == expected
    assert expected
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
    expected = _expected_references()
    assert archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT) == expected
    assert expected
    history[0]["record_schema_version"] = 2

    with pytest.raises(archive.ContractError, match="キー集合が不一致"):
        archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)


def test_missing_v2_snapshot_ref_is_red_after_current_history_is_green() -> None:
    """v2 の参照フィールド欠落を拒否する。"""
    history = _current_history()
    expected = _expected_references()
    assert archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT) == expected
    assert expected
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


def _snapshot_item_at_path(digest: str, path: str) -> dict[str, str]:
    """任意 path を持つ有効な v2 snapshot 行を作る。"""
    item = _snapshot_item(digest)
    item["path"] = path
    return item


def _v2_history_with_items(
    items: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """複数の snapshot 行を持つ最小 v2 履歴を作る。"""
    history = _v2_history()
    for side in ("before", "after"):
        history[0]["change"][side]["external_snapshots"] = copy.deepcopy(items)
    return history


def _expected_current_archive_totals() -> tuple[int, int, int, int]:
    """snapshot ファイルと独立参照集合から現況の集計値を導出する。"""
    files = sorted(path for path in SNAPSHOT_ROOT.iterdir() if path.is_file())
    expected_count = len(files)
    expected_bytes = sum(path.stat().st_size for path in files)
    expected_orphans = {path.name for path in files} - _expected_references()
    expected_orphan_bytes = sum(
        (SNAPSHOT_ROOT / name).stat().st_size for name in expected_orphans
    )
    return (
        expected_count,
        expected_bytes,
        len(expected_orphans),
        expected_orphan_bytes,
    )


def test_current_archive_metrics_are_within_limits() -> None:
    """現況の snapshot と既存孤児を比較元相対の予算内として受理する。"""
    comparison = archive.validate_snapshot_archive_limits(
        _current_history(),
        _current_history(),
        base_snapshot_root=SNAPSHOT_ROOT,
        head_snapshot_root=SNAPSHOT_ROOT,
    )

    count, total_bytes, orphan_count, orphan_bytes = (
        _expected_current_archive_totals()
    )
    expected = archive.SnapshotArchiveMetrics(
        snapshot_count=count,
        snapshot_bytes=total_bytes,
        orphan_count=orphan_count,
        orphan_bytes=orphan_bytes,
    )
    assert archive.SNAPSHOT_COUNT_LIMIT == 500
    assert archive.SNAPSHOT_BYTES_LIMIT == 33_554_432
    assert comparison.base == expected
    assert comparison.head == expected
    metrics = comparison.head
    assert metrics.snapshot_count <= archive.SNAPSHOT_COUNT_LIMIT
    assert metrics.snapshot_bytes <= archive.SNAPSHOT_BYTES_LIMIT
    assert comparison.head.orphan_count <= comparison.base.orphan_count


def test_snapshot_count_over_limit_is_red_after_exact_limit_is_green(
    tmp_path: Path,
) -> None:
    """snapshot 総件数は500件を受理し、501件を拒否する。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    base_root.mkdir()
    items: list[dict[str, str]] = []
    for index in range(archive.SNAPSHOT_COUNT_LIMIT):
        digest = _write_snapshot(head_root, f"snapshot {index}\n".encode())
        items.append(
            _snapshot_item_at_path(digest, f"scripts/snapshot-{index}.py")
        )

    comparison = archive.validate_snapshot_archive_limits(
        _v2_history(),
        _v2_history_with_items(items),
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    assert comparison.head.snapshot_count == archive.SNAPSHOT_COUNT_LIMIT
    assert comparison.head.orphan_count == 0

    digest = _write_snapshot(head_root, b"snapshot over count limit\n")
    items.append(_snapshot_item_at_path(digest, "scripts/over-count-limit.py"))
    with pytest.raises(archive.ContractError, match="件数が予算を超過"):
        archive.validate_snapshot_archive_limits(
            _v2_history(),
            _v2_history_with_items(items),
            base_snapshot_root=base_root,
            head_snapshot_root=head_root,
        )


def test_snapshot_bytes_over_limit_is_red_after_exact_limit_is_green(
    tmp_path: Path,
) -> None:
    """snapshot 総バイト数は32 MiBを受理し、1バイト超過を拒否する。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    base_root.mkdir()
    exact_digest = _write_snapshot(
        head_root,
        b"x" * archive.SNAPSHOT_BYTES_LIMIT,
    )
    exact_history = _v2_history(_snapshot_item(exact_digest))

    comparison = archive.validate_snapshot_archive_limits(
        _v2_history(),
        exact_history,
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    assert comparison.head.snapshot_bytes == archive.SNAPSHOT_BYTES_LIMIT
    assert comparison.head.orphan_bytes == 0

    (head_root / exact_digest).unlink()
    over_digest = _write_snapshot(
        head_root,
        b"y" * (archive.SNAPSHOT_BYTES_LIMIT + 1),
    )
    with pytest.raises(archive.ContractError, match="総バイト数が予算を超過"):
        archive.validate_snapshot_archive_limits(
            _v2_history(),
            _v2_history(_snapshot_item(over_digest)),
            base_snapshot_root=base_root,
            head_snapshot_root=head_root,
        )


def test_orphan_count_increase_is_red_after_29_orphans_are_green(
    tmp_path: Path,
) -> None:
    """比較元と同じ孤児29件を受理し、1件の増加を拒否する。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    for index in range(29):
        content = f"grandfathered orphan {index}\n".encode()
        _write_snapshot(base_root, content)
        _write_snapshot(head_root, content)

    comparison = archive.validate_snapshot_archive_limits(
        _v2_history(),
        _v2_history(),
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    assert comparison.base.orphan_count == 29
    assert comparison.head.orphan_count == 29

    _write_snapshot(head_root, b"new orphan\n")
    with pytest.raises(archive.ContractError, match="孤児 snapshot 件数"):
        archive.validate_snapshot_archive_limits(
            _v2_history(),
            _v2_history(),
            base_snapshot_root=base_root,
            head_snapshot_root=head_root,
        )


def test_orphan_bytes_increase_is_red_after_equal_bytes_are_green(
    tmp_path: Path,
) -> None:
    """孤児件数が同じでも比較元より総バイト数が増えれば拒否する。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    base_digest = _write_snapshot(base_root, b"0123456789")
    head_digest = _write_snapshot(head_root, b"0123456789")

    comparison = archive.validate_snapshot_archive_limits(
        _v2_history(),
        _v2_history(),
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    assert comparison.base.orphan_bytes == 10
    assert comparison.head.orphan_bytes == 10

    (head_root / head_digest).unlink()
    _write_snapshot(head_root, b"01234567890")
    with pytest.raises(archive.ContractError, match="孤児 snapshot 総バイト数"):
        archive.validate_snapshot_archive_limits(
            _v2_history(),
            _v2_history(),
            base_snapshot_root=base_root,
            head_snapshot_root=head_root,
        )
    assert (base_root / base_digest).is_file()


def test_base_and_head_use_different_histories_and_snapshot_sets(
    tmp_path: Path,
) -> None:
    """比較元とHEADをそれぞれの履歴・snapshot集合で独立に測定する。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    base_reference = _write_snapshot(base_root, b"base referenced\n")
    _write_snapshot(base_root, b"base orphan is larger\n")
    head_reference = _write_snapshot(head_root, b"head referenced differs\n")
    _write_snapshot(head_root, b"head orphan\n")

    comparison = archive.validate_snapshot_archive_limits(
        _v2_history(_snapshot_item(base_reference)),
        _v2_history(_snapshot_item(head_reference)),
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )

    assert comparison.base == archive.SnapshotArchiveMetrics(
        snapshot_count=2,
        snapshot_bytes=38,
        orphan_count=1,
        orphan_bytes=22,
    )
    assert comparison.head == archive.SnapshotArchiveMetrics(
        snapshot_count=2,
        snapshot_bytes=36,
        orphan_count=1,
        orphan_bytes=12,
    )


def test_current_archive_has_no_unreferenced_new_snapshot() -> None:
    """現況を同じ比較元とHEADへ渡すと新規参照不変量を満たす。"""
    comparison = archive.validate_snapshot_archive(
        _current_history(),
        _current_history(),
        base_snapshot_root=SNAPSHOT_ROOT,
        head_snapshot_root=SNAPSHOT_ROOT,
    )

    count, total_bytes, orphan_count, orphan_bytes = (
        _expected_current_archive_totals()
    )
    assert comparison.head.snapshot_count == count
    assert comparison.head.snapshot_bytes == total_bytes
    assert comparison.head.orphan_count == orphan_count
    assert comparison.head.orphan_bytes == orphan_bytes


def test_recreated_record_rejects_previous_attempt_until_snapshot_is_removed(
    tmp_path: Path,
) -> None:
    """同一受理の作り直しで残った前試行snapshotを拒否し、除去後は受理する。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    base_root.mkdir()
    first_attempt = _write_snapshot(head_root, b"first acceptance attempt\n")
    first_history = _v2_history(_snapshot_item(first_attempt))

    initial = archive.validate_snapshot_archive(
        _v2_history(),
        first_history,
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    assert initial.head.orphan_count == 0

    second_attempt = _write_snapshot(head_root, b"second acceptance attempt\n")
    recreated_history = _v2_history(_snapshot_item(second_attempt))
    with pytest.raises(
        archive.ContractError,
        match="新規 snapshot が履歴から参照されていない",
    ):
        archive.validate_snapshot_archive(
            _v2_history(),
            recreated_history,
            base_snapshot_root=base_root,
            head_snapshot_root=head_root,
        )

    (head_root / first_attempt).unlink()
    cleaned = archive.validate_snapshot_archive(
        _v2_history(),
        recreated_history,
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )
    assert cleaned.head.snapshot_count == 1
    assert cleaned.head.orphan_count == 0


def test_orphan_already_in_base_is_grandfathered_by_new_snapshot_invariant(
    tmp_path: Path,
) -> None:
    """比較元にすでに存在する孤児を新規snapshotとして拒否しない。"""
    base_root = tmp_path / "base"
    head_root = tmp_path / "head"
    grandfathered = b"grandfathered orphan\n"
    assert _write_snapshot(base_root, grandfathered) == _write_snapshot(
        head_root,
        grandfathered,
    )
    current = _write_snapshot(head_root, b"current referenced snapshot\n")

    comparison = archive.validate_snapshot_archive(
        _v2_history(),
        _v2_history(_snapshot_item(current)),
        base_snapshot_root=base_root,
        head_snapshot_root=head_root,
    )

    assert comparison.base.orphan_count == 1
    assert comparison.head.orphan_count == 1


PRODUCTION_FAIL_CLOSED_CASES = (
    ("F1", "HEAD history-snapshots の件数が予算を超過"),
    ("F2", "HEAD history-snapshots の総バイト数が予算を超過"),
    ("F3", "HEAD の孤児 snapshot 件数が比較元から増加"),
    ("F4", "HEAD の孤児 snapshot 総バイト数が比較元から増加"),
    ("F5", "HEAD の新規 snapshot が履歴から参照されていない"),
    ("F6", "snapshot_ref: sha256 と末尾セグメントが不一致"),
    ("F7", ".sha256: SHA-256 が不正"),
    ("F8", "snapshot_ref: snapshot を解決できない"),
    ("F9", "missing=['snapshot_ref']"),
    ("F10", "snapshot 参照抽出表と ASPECT_NAMES のキー集合が不一致"),
    ("F11", "history-snapshots: 既存 snapshot を削除できない"),
)


def _prepare_green_production_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, ModuleType]:
    """runner を流用して変更なしの二親 merge と PR event を作る。"""
    prepared = case_runner.prepare_case(
        CASE_MANIFEST.cases[0],
        tmp_path,
        REPOSITORY_ROOT,
        CASE_MANIFEST,
        monkeypatch,
    )
    helpers = case_runner._load_repository_helpers(REPOSITORY_ROOT)
    return prepared, helpers


def _run_production_checker(
    checker: ModuleType,
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    """本番 CLI から check_repository を実行して終了コードと出力を返す。"""
    exit_code = checker.main(["--root", str(repository)])
    captured = capsys.readouterr()
    return exit_code, captured.out.strip(), captured.err.strip()


def _promote_worktree_to_comparison_base(
    prepared: Any,
    helpers: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failure_id: str,
) -> None:
    """現在の変異を比較元にも含め、同じ内容の二親 merge を作り直す。"""
    base_sha = helpers._commit_test_repository(
        prepared.repository,
        f"{failure_id} comparison base",
    )
    helpers._seal_pull_request_worktree(
        prepared.repository,
        base_sha,
        monkeypatch,
        prepared.event_path,
        number=CASE_MANIFEST.pull_request_number,
    )


def _reseal_head_mutation(
    prepared: Any,
    helpers: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """比較元を保ったまま現在の変異を PR head と二親 merge に封入する。"""
    helpers._seal_pull_request_worktree(
        prepared.repository,
        prepared.base_sha,
        monkeypatch,
        prepared.event_path,
        number=CASE_MANIFEST.pull_request_number,
    )


def _mutate_existing_v2_reference(
    prepared: Any,
    helpers: ModuleType,
    failure_id: str,
) -> None:
    """既存 v2 記録の参照を F6〜F9 の指定形へ変異させる。"""
    authority_path = prepared.repository / helpers.checker.DEFAULT_ALLOWLIST
    authority = case_runner._read_json_object(authority_path)
    record = case_runner._first_v2_record(authority)
    snapshot = case_runner._external_snapshot_entry(record)
    digest = case_runner._string(snapshot["sha256"], "snapshot.sha256")
    prefix = helpers.checker.frozen_history.SNAPSHOT_REF_PREFIX
    if failure_id == "F6":
        snapshot["snapshot_ref"] = f"invalid-history-snapshots/{digest}"
    elif failure_id == "F7":
        invalid_digest = digest[:-1]
        snapshot["sha256"] = invalid_digest
        snapshot["snapshot_ref"] = f"{prefix}{invalid_digest}"
    elif failure_id == "F8":
        missing_digest = "0" * 64
        assert not (
            prepared.repository
            / case_runner.HISTORY_SNAPSHOT_DIRECTORY
            / missing_digest
        ).exists()
        snapshot["sha256"] = missing_digest
        snapshot["snapshot_ref"] = f"{prefix}{missing_digest}"
    else:
        assert failure_id == "F9"
        snapshot.pop("snapshot_ref")
    helpers._write_contract_asset(authority_path, authority)


def _install_metric_mutation(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failure_id: str,
) -> None:
    """F5 より後段の孤児量分岐へ比較元・HEAD の異なる測定値を渡す。"""
    metrics_type = checker.frozen_archive.SnapshotArchiveMetrics
    base = metrics_type(
        snapshot_count=64,
        snapshot_bytes=2_181_430,
        orphan_count=29,
        orphan_bytes=1_021_201,
    )
    head = metrics_type(
        snapshot_count=64,
        snapshot_bytes=2_181_430,
        orphan_count=30 if failure_id == "F3" else 29,
        orphan_bytes=1_021_201 if failure_id == "F3" else 1_021_202,
    )
    measured = iter((base, head))

    def mutated_measure(
        history: object,
        snapshot_root: Path,
        *,
        location: str,
    ) -> object:
        """比較元と HEAD に独立した変異測定値を順番に返す。"""
        del history, snapshot_root, location
        return next(measured)

    monkeypatch.setattr(
        checker.frozen_archive,
        "_measure_snapshot_archive",
        mutated_measure,
    )


def _apply_production_failure_mutation(
    failure_id: str,
    prepared: Any,
    helpers: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1〜F11 の変異を合成リポジトリまたは本番検査部品へ適用する。"""
    checker = helpers.checker
    repository = prepared.repository
    if failure_id == "F1":
        case_runner._add_snapshot_count_case(
            repository,
            helpers,
            checker.frozen_archive.SNAPSHOT_COUNT_LIMIT + 1,
        )
        _promote_worktree_to_comparison_base(
            prepared,
            helpers,
            monkeypatch,
            failure_id,
        )
    elif failure_id == "F2":
        case_runner._add_snapshot_bytes_case(
            repository,
            helpers,
            checker.frozen_archive.SNAPSHOT_BYTES_LIMIT + 1,
        )
        _promote_worktree_to_comparison_base(
            prepared,
            helpers,
            monkeypatch,
            failure_id,
        )
    elif failure_id in {"F3", "F4"}:
        _install_metric_mutation(checker, monkeypatch, failure_id)
    elif failure_id == "F5":
        helpers._write_content_snapshot(repository, b"step 7 new orphan snapshot\n")
        _reseal_head_mutation(prepared, helpers, monkeypatch)
    elif failure_id in {"F6", "F7", "F8", "F9"}:
        _mutate_existing_v2_reference(prepared, helpers, failure_id)
        _promote_worktree_to_comparison_base(
            prepared,
            helpers,
            monkeypatch,
            failure_id,
        )
    elif failure_id == "F10":
        mutated = dict(checker.frozen_archive.ASPECT_REFERENCE_KINDS)
        mutated.pop("declaration")
        monkeypatch.setattr(
            checker.frozen_archive,
            "ASPECT_REFERENCE_KINDS",
            mutated,
        )
    else:
        assert failure_id == "F11"
        authority = case_runner._read_json_object(
            repository / checker.DEFAULT_ALLOWLIST
        )
        history = authority["baseline_control"]["history"]
        references = checker.frozen_archive.extract_referenced_snapshot_names(
            history,
            repository / case_runner.HISTORY_SNAPSHOT_DIRECTORY,
        )
        orphan = next(
            path
            for path in sorted(
                (repository / case_runner.HISTORY_SNAPSHOT_DIRECTORY).iterdir()
            )
            if path.name not in references
        )
        orphan.unlink()
        _reseal_head_mutation(prepared, helpers, monkeypatch)


@pytest.mark.parametrize(
    ("failure_id", "expected_error"),
    PRODUCTION_FAIL_CLOSED_CASES,
    ids=[failure_id.lower() for failure_id, _ in PRODUCTION_FAIL_CLOSED_CASES],
)
def test_production_check_repository_fails_closed_for_each_design_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_id: str,
    expected_error: str,
) -> None:
    """F1〜F11 を改変前 green から本番 PR 受理 CLI の識別可能な red にする。"""
    assert {case_id for case_id, _ in PRODUCTION_FAIL_CLOSED_CASES} == {
        f"F{index}" for index in range(1, 12)
    }
    prepared, helpers = _prepare_green_production_case(tmp_path, monkeypatch)

    green_exit, green_stdout, green_stderr = _run_production_checker(
        helpers.checker,
        prepared.repository,
        capsys,
    )
    assert green_exit == 0
    assert green_stdout == "tenant-boundary bypass check: ok"
    assert green_stderr == ""

    _apply_production_failure_mutation(
        failure_id,
        prepared,
        helpers,
        monkeypatch,
    )
    red_exit, red_stdout, red_stderr = _run_production_checker(
        helpers.checker,
        prepared.repository,
        capsys,
    )

    assert red_exit == 2
    assert red_stdout == ""
    assert expected_error in red_stderr

    if failure_id == "F10":
        classification_mutation = dict(
            helpers.checker.frozen_archive.EXPECTED_ASPECT_REFERENCE_KINDS
        )
        classification_mutation["declaration"] = (
            helpers.checker.frozen_archive.AspectReferenceKind.SNAPSHOT_ARRAY
        )
        monkeypatch.setattr(
            helpers.checker.frozen_archive,
            "ASPECT_REFERENCE_KINDS",
            classification_mutation,
        )
        classification_exit, classification_stdout, classification_stderr = (
            _run_production_checker(
                helpers.checker,
                prepared.repository,
                capsys,
            )
        )
        assert classification_exit == 2
        assert classification_stdout == ""
        assert "snapshot 参照抽出表の分類値が期待表と不一致" in (
            classification_stderr
        )
