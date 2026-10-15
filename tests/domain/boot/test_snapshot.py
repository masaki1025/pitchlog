"""BOOT 意味スナップショットの二時点収集とレポート接続を検証する。"""

from __future__ import annotations

import copy
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend/src"))
REPORT = importlib.import_module("pitchlog.domaincheck.boot.report")
SNAPSHOT = importlib.import_module("pitchlog.domaincheck.boot.snapshot")
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")

ASSETS = (
    "backend/domain/boot-report.schema.json",
    "backend/domain/boot-seal.json",
    "backend/domain/check-sets.json",
    "backend/domain/manifest.schema.json",
)
MANIFEST_PATH = "backend/domain/manifest.json"
SYNTHETIC_MANIFEST = ROOT / "backend/tests/domain/fixtures/synthetic_dsl/manifest.json"


@pytest.fixture(autouse=True)
def _without_ci_base_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    """合成 Git 履歴を CI の外部 base ref から独立させる。"""
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)


def _git(root: Path, *arguments: str) -> str:
    """一時リポジトリの Git コマンドを実行する。"""
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _manifest(target: str) -> dict[str, Any]:
    """既存の合成 manifest を承認済み対象 ID に結び直す。"""
    manifest = json.loads(SYNTHETIC_MANIFEST.read_text(encoding="utf-8"))
    calculation = manifest["calculations"][0]
    calculation["calculation"] = target
    calculation["vectors"][0]["calculation"] = target
    return manifest


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    """一時リポジトリにだけ manifest と参照先を置く。"""
    calculation = manifest["calculations"][0]
    paths = {
        calculation["source"]["path"],
        manifest["propertyCatalog"]["path"],
        manifest["propertyCatalog"]["schema"],
        *(item["path"] for item in calculation["generated"]),
        *(item["module"] for item in calculation["entrypoints"]),
        *(item["adapter"] for item in calculation["entrypoints"]),
        *(item["invocation"]["adapter"] for item in calculation["directTargets"]),
        *(item["path"] for item in calculation["vectors"]),
        *(item["path"] for item in calculation["properties"]),
    }
    for relative in paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic\n", encoding="utf-8")
    path = root / MANIFEST_PATH
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _repository(tmp_path: Path) -> tuple[Path, str, dict[str, Any]]:
    """manifest 不在の base と manifest ありの HEAD を作る。"""
    root = tmp_path / "repository"
    root.mkdir()
    for relative in ASSETS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, path)
    _git(root, "init", "--quiet")
    _git(root, "config", "user.name", "BOOT Snapshot Test")
    _git(root, "config", "user.email", "boot-snapshot@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "fixture base")
    base_oid = _git(root, "rev-parse", "HEAD")
    universe = PHASE2.load_target_universe(root)
    target = next(iter(sorted(universe.identifiers)))
    manifest = _manifest(target)
    _write_manifest(root, manifest)
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "fixture head")
    return root, base_oid, manifest


def test_synthetic_manifest_collects_six_observed_sets(tmp_path: Path) -> None:
    """検査成功が観測できる合成入力では六集合とも対象を持つ。"""
    root, _, manifest = _repository(tmp_path)
    target = manifest["calculations"][0]["calculation"]
    verified = {
        component: frozenset({target}) for component in SNAPSHOT.CHECK_COMPONENTS
    }

    snapshot = SNAPSHOT.collect_semantic_snapshot(
        manifest,
        allowed_target_ids={target},
        path_exists=lambda path: (root / path).exists(),
        verified_checks=verified,
    )

    assert snapshot == PHASE2.SemanticSnapshot(
        *(frozenset({target}) for _ in range(6))
    )


def test_manifest_report_emits_machine_readable_unresolved_list(
    tmp_path: Path,
) -> None:
    """manifest があっても BOOT レポートと再照合を成功させる。"""
    root, base_oid, manifest = _repository(tmp_path)
    target = manifest["calculations"][0]["calculation"]

    assert REPORT.main(["--root", str(root)]) == 0
    output = root / "backend/domain/boot-report.json"
    report = json.loads(output.read_text(encoding="utf-8"))
    assert REPORT.main(["--root", str(root), "--verify"]) == 0
    accepted = REPORT.accept_transition_green(root)
    collector = REPORT.InputAssetCollector(root)
    sealed = collector.read_json(root / "backend/domain/boot-seal.json")
    _, evidence = REPORT.measure_resolved_element_ids(
        root,
        sealed,
        _git(root, "rev-parse", "HEAD"),
        input_collector=collector,
    )

    assert accepted == report
    assert report["unresolvedCount"] == len(report["unresolvedElements"])
    assert report["unresolvedCount"] == len(sealed["elements"])
    assert all(set(item) == {"elementId", "canonicalKey"} for item in report["unresolvedElements"])
    assert evidence["baseCommitOid"] == base_oid
    assert evidence["phase2Status"] == "indeterminate-phase2"
    assert evidence["beforeSnapshot"]["declarations"] is None
    assert evidence["afterSnapshot"]["declarations"] == [target]
    assert evidence["afterSnapshot"]["vector_checks"] is None
    assert {item["path"] for item in report["provenance"]["inputFiles"]} >= {
        MANIFEST_PATH,
        "backend/domain/manifest.schema.json",
        manifest["calculations"][0]["source"]["path"],
        manifest["calculations"][0]["vectors"][0]["path"],
    }


def test_referenced_file_change_invalidates_report(tmp_path: Path) -> None:
    """Manifest が参照する資産の変更を provenance の digest で検出する。"""
    root, _, manifest = _repository(tmp_path)
    REPORT.emit_boot_report(root)
    source = root / manifest["calculations"][0]["source"]["path"]
    source.write_text("changed\n", encoding="utf-8")

    with pytest.raises(REPORT.CheckerViolation, match="一致しない"):
        REPORT.accept_transition_green(root)


def test_unobservable_layer_is_none_and_indeterminate(tmp_path: Path) -> None:
    """参照先を観測できない検査層を空集合へ倒さない。"""
    root, _, manifest = _repository(tmp_path)
    changed = copy.deepcopy(manifest)
    target = changed["calculations"][0]["calculation"]
    changed["calculations"][0]["vectors"][0]["path"] = "missing/vector.json"
    verified = {
        component: frozenset({target}) for component in SNAPSHOT.CHECK_COMPONENTS
    }

    snapshot = SNAPSHOT.collect_semantic_snapshot(
        changed,
        allowed_target_ids={target},
        path_exists=lambda path: (root / path).exists(),
        verified_checks=verified,
    )
    universe = PHASE2.load_target_universe(root)
    state = STALL.activate(
        STALL.defined_state(len(universe.identifiers)),
        "synthetic-activation",
    )
    decision = PHASE2.classify_phase2(
        state, universe, PHASE2.SemanticSnapshot.empty(), snapshot
    )

    assert snapshot.vector_checks is None
    assert snapshot.property_checks == frozenset({target})
    assert decision.status == PHASE2.Phase2Status.INDETERMINATE_PHASE2
    assert "vector_checks" in decision.indeterminate_components


def test_unknown_target_is_rejected_even_with_missing_source(tmp_path: Path) -> None:
    """参照先を欠く対象外 ID も判定不能へ埋もれさせない。"""
    root, _, manifest = _repository(tmp_path)
    original = manifest["calculations"][0]["calculation"]
    changed = copy.deepcopy(manifest)
    changed["calculations"][0]["calculation"] = "unknown-target"
    changed["calculations"][0]["source"]["path"] = "missing/source.ts"

    with pytest.raises(SNAPSHOT.CheckerViolation, match="対象欄にない宣言"):
        SNAPSHOT.collect_semantic_snapshot(
            changed,
            allowed_target_ids={original},
            path_exists=lambda path: (root / path).exists(),
        )


def test_base_and_head_snapshots_are_distinct(tmp_path: Path) -> None:
    """base に manifest がある場合は Git の旧版を別に読む。"""
    root, _, first_manifest = _repository(tmp_path)
    first = first_manifest["calculations"][0]["calculation"]
    universe = PHASE2.load_target_universe(root)
    second = next(identifier for identifier in sorted(universe.identifiers) if identifier != first)
    _write_manifest(root, _manifest(second))
    _git(root, "add", MANIFEST_PATH)
    _git(root, "commit", "--quiet", "-m", "next target")
    collector = REPORT.InputAssetCollector(root)
    sealed = collector.read_json(root / "backend/domain/boot-seal.json")

    _, evidence = REPORT.measure_resolved_element_ids(
        root, sealed, _git(root, "rev-parse", "HEAD"), input_collector=collector
    )

    assert evidence["beforeSnapshot"]["declarations"] == [first]
    assert evidence["afterSnapshot"]["declarations"] == [second]
    assert any(item["path"].startswith("git:") for item in collector.records())
    assert any(
        item["path"].endswith(first_manifest["calculations"][0]["source"]["path"])
        and item["path"].startswith("git:")
        for item in collector.records()
    )


def test_pull_request_base_uses_merge_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR 文脈では remote の比較元と HEAD の merge-base を使う。"""
    root, base_oid, _ = _repository(tmp_path)
    _git(root, "update-ref", "refs/remotes/origin/develop", base_oid)
    monkeypatch.setenv("GITHUB_BASE_REF", "develop")
    collector = REPORT.InputAssetCollector(root)
    sealed = collector.read_json(root / "backend/domain/boot-seal.json")

    _, evidence = REPORT.measure_resolved_element_ids(
        root, sealed, _git(root, "rev-parse", "HEAD"), input_collector=collector
    )

    assert evidence["baseCommitOid"] == base_oid


@pytest.mark.parametrize("mutation", ["unknown-target", "empty-calculations"])
def test_phase2_manifest_constraints_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    """13 対象外と計算 0 件は報告の成功に変えない。"""
    root, _, manifest = _repository(tmp_path)
    changed = copy.deepcopy(manifest)
    if mutation == "unknown-target":
        changed["calculations"][0]["calculation"] = "unknown-target"
        changed["calculations"][0]["vectors"][0]["calculation"] = "unknown-target"
    else:
        changed["calculations"] = []
    (root / MANIFEST_PATH).write_text(
        json.dumps(changed, ensure_ascii=False), encoding="utf-8"
    )

    assert REPORT.main(["--root", str(root)]) == 2
    assert not (root / "backend/domain/boot-report.json").exists()
