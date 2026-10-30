"""部分座標operationがBOOT全対象成立へ昇格しない対向検査。"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend/src"))
BIND = importlib.import_module("pitchlog.domaincheck.boot.operation_bindings")
SNAP = importlib.import_module("pitchlog.domaincheck.boot.snapshot")
PHASE = importlib.import_module("pitchlog.domaincheck.boot.phase2")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")
REPORT = importlib.import_module("pitchlog.domaincheck.boot.report")
TARGET = "nfr018-alpha-02"
OP = "course-input-quantization"


def _json(path: str) -> dict:
    """実資産を読む。"""
    return json.loads((ROOT / path).read_text())


CASES = _json("backend/tests/domain/fixtures/boot_coordinate_binding_cases_v1.json")["cases"]


def _binding():
    """実資産の閉対応を解決する。"""
    return BIND.load_bindings(ROOT, PHASE.load_target_universe(ROOT).identifiers)


def _snapshot(manifest=None, *, verified=True, missing=None, bindings=None):
    """部分operationの実manifestを製品収集器へ渡す。"""
    return SNAP.collect_semantic_snapshot(
        manifest or _json("backend/domain/manifest.json"),
        allowed_target_ids=PHASE.load_target_universe(ROOT).identifiers,
        path_exists=lambda path: path != missing and (ROOT / path).exists(),
        verified_checks=(
            {key: frozenset({OP, TARGET, "nfr018-alpha-01"}) for key in SNAP.CHECK_COMPONENTS}
            if verified else None
        ),
        operation_bindings=_binding() if bindings is None else bindings,
    )


def _decision(snapshot):
    """既phase2判定の全体解消集合を計算する。"""
    universe = PHASE.load_target_universe(ROOT)
    state = STALL.activate(STALL.defined_state(len(universe.identifiers)), "candidate")
    return PHASE.classify_phase2(state, universe, PHASE.SemanticSnapshot.empty(), snapshot)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_all_binding_candidate_cases(case, tmp_path):
    """候補15対向を省略せず実製品関数で消費する。"""
    identifier = case["id"]
    assert len(CASES) == 15
    if identifier in {"BIND-03", "BIND-04", "BIND-05", "BIND-06", "BIND-07", "BIND-09"}:
        value = _json("backend/domain/boot-operation-bindings.json")
        mutations = {
            "BIND-03": ("operation", "unknown-operation"),
            "BIND-04": ("targetId", "nfr018-alpha-01"),
            "BIND-05": ("targetId", "unknown-target"),
            "BIND-06": ("coverage", "complete"),
            "BIND-09": ("skipValidation", True),
        }
        if identifier == "BIND-07":
            value["bindings"] *= 2
        else:
            key, item = mutations[identifier]
            value["bindings"][0][key] = item
        with pytest.raises(BIND.CheckerViolation):
            BIND.parse_bindings(
                value, _json("backend/domain/boot-operation-bindings.schema.json"), {TARGET}
            )
    elif identifier == "BIND-08":
        assert BIND.load_bindings(tmp_path, {TARGET}) == ()
        with pytest.raises(SNAP.CheckerViolation):
            _snapshot(bindings=())
    elif identifier in {"BIND-01", "BIND-02"}:
        snapshot = _snapshot(verified=identifier == "BIND-02")
        decision = _decision(snapshot)
        assert decision.resolution_target_ids == frozenset()
        resolved = REPORT.resolved_element_ids_from_phase2(
            _json("backend/domain/boot-seal.json"), decision
        )
        assert resolved == frozenset()
        for component in SNAP.CHECK_COMPONENTS:
            expected = frozenset() if identifier == "BIND-02" else None
            assert getattr(snapshot, component) == expected
    elif identifier == "BIND-10":
        spec = importlib.util.spec_from_file_location(
            "boot_binding_snapshot_helpers", ROOT / "tests/domain/boot/test_snapshot.py"
        )
        assert spec is not None and spec.loader is not None
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        root, _, _ = helper._repository(tmp_path)
        helper._write_manifest(root, _json("backend/domain/manifest.json"))
        helper._git(root, "add", ".")
        helper._git(root, "commit", "--quiet", "-m", "legacy operation manifest")
        before = helper._git(root, "show", "HEAD:backend/domain/manifest.json")
        for path in (BIND.BINDINGS_PATH, BIND.BINDINGS_SCHEMA_PATH):
            shutil.copy2(ROOT / path, root / path)
        helper._git(root, "add", ".")
        helper._git(root, "commit", "--quiet", "-m", "finite binding assets")
        collector = REPORT.InputAssetCollector(root)
        resolved, evidence = REPORT.measure_resolved_element_ids(
            root, _json("backend/domain/boot-seal.json"),
            helper._git(root, "rev-parse", "HEAD"), input_collector=collector,
        )
        assert resolved == frozenset()
        assert evidence["beforeSnapshot"]["declarations"] == [TARGET]
        assert evidence["afterSnapshot"]["declarations"] == [TARGET]
        assert helper._git(root, "show", "HEAD^:backend/domain/manifest.json") == before
    elif identifier in {"BIND-11", "BIND-12", "BIND-14"}:
        manifest = _json("backend/domain/manifest.json")
        stable = copy.deepcopy(manifest["calculations"][0])
        stable["calculation"] = TARGET if identifier == "BIND-12" else "nfr018-alpha-01"
        if identifier == "BIND-11":
            manifest["calculations"] = [stable]
        else:
            manifest["calculations"].append(stable)
        if identifier == "BIND-12":
            with pytest.raises(SNAP.CheckerViolation):
                _snapshot(manifest)
        else:
            decision = _decision(_snapshot(manifest))
            assert decision.resolution_target_ids == frozenset({"nfr018-alpha-01"})
    elif identifier == "BIND-13":
        calculation = _json("backend/domain/manifest.json")["calculations"][0]
        paths = [
            calculation["source"]["path"],
            calculation["generated"][0]["path"],
            calculation["entrypoints"][0]["module"],
            calculation["directTargets"][0]["invocation"]["adapter"],
            calculation["vectors"][0]["path"],
            calculation["properties"][0]["path"],
            calculation["mutation"][0]["target"],
        ]
        for path in paths:
            snapshot = _snapshot(missing=path)
            assert _decision(snapshot).resolution_target_ids == frozenset()
            components = ("declarations", "generated", "product_calls", *SNAP.CHECK_COMPONENTS)
            assert any(getattr(snapshot, component) is None for component in components)
    elif identifier == "BIND-15":
        manifest = _json("backend/domain/manifest.json")
        manifest["calculations"][0]["source"]["path"] = "another/source.ts"
        with pytest.raises(SNAP.CheckerViolation):
            _snapshot(manifest)
    else:
        pytest.fail(f"未実行case: {identifier}")


def test_forged_binding_cannot_bypass_unknown_operation():
    """公開引数へ任意の対応を渡しても対象外拒否を維持する。"""
    with pytest.raises(SNAP.CheckerViolation):
        _snapshot(bindings=(BIND.PartialOperationBinding("unknown", TARGET, "arbitrary.ts"),))


def test_missing_manifest_remains_missing():
    """bindingの有無でmanifest不在の既挙動を変更しない。"""
    snapshot = SNAP.collect_semantic_snapshot(
        None, allowed_target_ids={TARGET}, path_exists=lambda _: True,
        operation_bindings=_binding(),
    )
    assert snapshot == PHASE.SemanticSnapshot.missing()


def test_binding_assets_are_recorded_in_input_evidence():
    """正式readerへ実bindingとschemaのhashを残す。"""
    collector = REPORT.InputAssetCollector(ROOT)
    assert BIND.load_bindings(ROOT, {TARGET}, read_asset=collector.read_json) == _binding()
    assert {row["path"] for row in collector.records()} == {
        BIND.BINDINGS_PATH.as_posix(), BIND.BINDINGS_SCHEMA_PATH.as_posix()
    }


@pytest.mark.parametrize(
    "target", sorted(PHASE.load_target_universe(ROOT).identifiers)
)
def test_all_stable_targets_preserve_existing_completion(target):
    """既13対象は有限bindingの追加で完了判定を変えない。"""
    manifest = _json("backend/domain/manifest.json")
    manifest["calculations"][0]["calculation"] = target
    verified = {key: frozenset({target}) for key in SNAP.CHECK_COMPONENTS}
    snapshot = SNAP.collect_semantic_snapshot(
        manifest,
        allowed_target_ids=PHASE.load_target_universe(ROOT).identifiers,
        path_exists=lambda path: (ROOT / path).exists(),
        verified_checks=verified,
        operation_bindings=_binding(),
    )
    assert _decision(snapshot).resolution_target_ids == frozenset({target})
