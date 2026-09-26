"""要件書・ADR-003・入力軸descriptorの3点突合を検証する。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_three_way_parity.py"
DESCRIPTOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


descriptor_checker = _load_module(
    "check_input_axes_descriptor", DESCRIPTOR_SCRIPT
)
checker = _load_module("input_axes_three_way_parity_under_test", SCRIPT)

ASSET_PATHS = (
    checker.REQUIREMENTS_PATH,
    checker.ADR_PATH,
    checker.DESCRIPTOR_PATH,
    checker.SCHEMA_PATH,
)


def _copy_fixture_root(tmp_path: Path) -> Path:
    """3点突合に必要な資産だけを一時ルートへ複製する。"""
    root = tmp_path / "repository"
    for relative_path in ASSET_PATHS:
        source = REPOSITORY_ROOT / relative_path
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return root


def _rewrite_descriptor(
    root: Path, mutate: Callable[[dict[str, Any]], None] | None = None
) -> dict[str, Any]:
    """descriptorを任意変更し、変更後の内容からdigestを再計算する。"""
    path = root / checker.DESCRIPTOR_PATH
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(descriptor, dict)
    if mutate is not None:
        mutate(descriptor)
    descriptor["digest"] = descriptor_checker.compute_descriptor_digest(descriptor)
    path.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert descriptor["digest"] == descriptor_checker.compute_descriptor_digest(
        descriptor
    )
    return descriptor


def test_repository_three_way_parity_is_green() -> None:
    """実資産の3点突合が成功する。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "input-axes-three-way-parity: OK\n"
    assert result.stderr == ""


def test_branch_ids_are_partitioned_into_covered_and_explicitly_excluded() -> None:
    """65分岐を軸の支援対象37件と理由付き対象外28件へ漏れなく分ける。"""
    report = checker.validate_three_way_parity(REPOSITORY_ROOT)
    expected_covered = {
        *(f"COLD-{number:02d}" for number in range(1, 10)),
        *(f"DRAW-{number:02d}" for number in range(1, 11) if number != 4),
        *(f"XMARK-{number:02d}" for number in range(1, 4)),
        *(f"OUT3-{number:02d}" for number in range(1, 6)),
        *(f"INT-{number:02d}" for number in range(1, 8)),
        *(f"RBI-{number:02d}" for number in range(2, 6)),
    }

    assert len(report.requirement_branch_ids) == 65
    assert report.covered_branch_ids == expected_covered
    assert len(report.covered_branch_ids) == 37
    assert len(report.excluded_branch_ids) == 28
    assert {f"req:{item}" for item in report.covered_branch_ids} <= (
        report.descriptor_supporting_clause_ids
    )
    assert (
        report.covered_branch_ids | report.excluded_branch_ids
        == report.requirement_branch_ids
    )
    assert report.covered_branch_ids.isdisjoint(report.excluded_branch_ids)
    assert all(checker.BRANCH_COVERAGE_EXCLUSIONS.values())


def test_d11_machine_readable_structure_is_exact_and_asymmetric() -> None:
    """D-11の3コレクションだけを抽出し未記載のstateTransitionAxesを捏造しない。"""
    report = checker.validate_three_way_parity(REPOSITORY_ROOT)

    assert report.d11_collection_ids == {
        "gameEndAxes[]",
        "nonCoverageFields[]",
        "projectionRules[]",
    }
    assert "stateTransitionAxes[]" not in report.d11_collection_ids


def test_d11_stage2_constraint_classes_match_descriptor_exactly() -> None:
    """D-11とdescriptorの段階2委任制約クラスが同じexact-setである。"""
    report = checker.validate_three_way_parity(REPOSITORY_ROOT)

    assert report.d11_stage2_constraint_classes == (
        descriptor_checker.EXPECTED_STAGE2_CONSTRAINT_CLASSES
    )


def test_d12_machine_readable_path_and_filename_literals_are_present() -> None:
    """D-12が領域・一般命名・descriptor固有命名をコード表記で持つ。"""
    adr_text = (REPOSITORY_ROOT / checker.ADR_PATH).read_text(encoding="utf-8")
    section = checker.extract_adr_decision_section(adr_text, "D-12")

    assert checker.D12_REQUIRED_CODE_LITERALS <= checker.extract_code_literals(section)
    assert checker.DESCRIPTOR_PATH.parts == (
        "contracts",
        "state-transition",
        "input_axes_descriptor_v1.json",
    )


def test_requirements_only_drift_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """要件書へ未被覆の分岐IDを1件足すとdescriptorのdigestが正しくても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.REQUIREMENTS_PATH
    text = path.read_text(encoding="utf-8")
    source_row = next(line for line in text.splitlines() if "| `COLD-09` |" in line)
    extra_row = source_row.replace("COLD-09", "COLD-10")
    path.write_text(text.replace(source_row, f"{source_row}\n{extra_row}", 1), encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"descriptorの軸から参照されない必須分岐ID.*COLD-10",
    ):
        checker.validate_three_way_parity(root)

def test_adr_only_drift_is_red_after_digest_recalculation(tmp_path: Path) -> None:
    """D-11から名指しコレクションを1件落とすとdigestが正しくても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.ADR_PATH
    text = path.read_text(encoding="utf-8")
    d11_start = text.index("### D-11:")
    token_index = text.index("`projectionRules[]`", d11_start)
    drifted = (
        text[:token_index]
        + "`projectionRules`"
        + text[token_index + len("`projectionRules[]`") :]
    )
    path.write_text(drifted, encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"D-11のdescriptorコレクションIDがexact-set不一致",
    ):
        checker.validate_three_way_parity(root)


@pytest.mark.parametrize(
    "constraint_class",
    [
        "payload-string-policy-reconciliation",
        "stat-flag-derivation-rules",
        "third-out-type-observation-input",
        "official-scorer-judgment-inputs",
    ],
)
def test_adr_stage2_constraint_omission_is_red_after_digest_recalculation(
    tmp_path: Path,
    constraint_class: str,
) -> None:
    """D-11だけから延期制約を1件落とすとdigestを合わせても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.ADR_PATH
    text = path.read_text(encoding="utf-8")
    marker = f"`stage2-constraint:{constraint_class}`"
    assert text.count(marker) == 1
    path.write_text(
        text.replace(marker, f"`{constraint_class}`", 1),
        encoding="utf-8",
    )
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=rf"段階2委任制約クラスがexact-set不一致.*{constraint_class}",
    ):
        checker.validate_three_way_parity(root)


def test_descriptor_only_drift_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """descriptorだけが未知の条文IDを参照するとdigestを合わせても拒否する。"""
    root = _copy_fixture_root(tmp_path)

    def mutate(descriptor: dict[str, Any]) -> None:
        axis = next(
            item
            for item in descriptor["stateTransitionAxes"]
            if item["axisId"] == "state.half"
        )
        axis["sourceClauseId"] = "req:FR-999"

    _rewrite_descriptor(root, mutate)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"由来条文IDが正本に実在しない.*FR-999",
    ):
        checker.validate_three_way_parity(root)


def test_same_named_clause_in_wrong_namespace_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """要件書D-4をADR側の同名IDへ誤接続しても実在扱いで通さない。"""
    root = _copy_fixture_root(tmp_path)

    def mutate(descriptor: dict[str, Any]) -> None:
        axis = next(
            item
            for item in descriptor["stateTransitionAxes"]
            if item["axisId"] == "event.perPitch.resultId"
        )
        axis["sourceClauseId"] = "adr:D-4"

    _rewrite_descriptor(root, mutate)

    with pytest.raises(
        checker.ThreeWayParityError,
        match="同名条文IDの名前空間が誤っている",
    ):
        checker.validate_three_way_parity(root)


@pytest.mark.parametrize(
    ("axis_id", "branch_id"),
    [
        ("event.perPitch.thirdOutTimingByRunner", "OUT3-04"),
        ("event.perPitch.interferenceRuling", "INT-02"),
    ],
)
def test_observation_branch_reference_removal_is_red_after_digest_recalculation(
    tmp_path: Path,
    axis_id: str,
    branch_id: str,
) -> None:
    """観測入力軸から分岐参照を1件落とすとdigestを合わせても拒否する。"""
    root = _copy_fixture_root(tmp_path)

    def mutate(descriptor: dict[str, Any]) -> None:
        axis = next(
            item
            for item in descriptor["stateTransitionAxes"]
            if item["axisId"] == axis_id
        )
        axis["supportingClauseIds"].remove(f"req:{branch_id}")

    _rewrite_descriptor(root, mutate)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=rf"descriptorの軸から参照されない必須分岐ID.*{branch_id}",
    ):
        checker.validate_three_way_parity(root)
