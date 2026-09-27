"""要件書・ADR-003・入力軸descriptorの3点突合を検証する。"""

from __future__ import annotations

import copy
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
FREEZE_SCRIPT = REPOSITORY_ROOT / "scripts" / "state_transition_freeze.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_SCRIPT)
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


def _descriptor() -> dict[str, Any]:
    """リポジトリのdescriptorを読む。"""
    value = json.loads(
        (REPOSITORY_ROOT / checker.DESCRIPTOR_PATH).read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def _criteria() -> Any:
    """資産側宣言から3点突合基準を読む。"""
    return checker.load_parity_criteria(_descriptor())


def _descriptor_criteria() -> Any:
    """資産側宣言からdescriptor検査基準を読む。"""
    return descriptor_checker.load_descriptor_criteria(_descriptor())


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


def _synchronize_unaccepted_freeze_record(descriptor: dict[str, Any]) -> None:
    """同一PR内の未受理基準変更を既存の単一履歴レコードへ反映する。"""
    declaration = descriptor[checker.freeze_checker.FREEZE_FIELD]
    criteria = declaration["criteria"]
    history = declaration["history"]
    assert len(history) == 1
    record = history[0]
    record["newIdentity"] = {
        "present": True,
        "values": checker.freeze_checker.current_identities(declaration),
    }
    changes = {change["criterionId"]: change for change in record["changes"]}
    definition_id = declaration["scope"]["identityCriterionId"]
    assert set(changes) == {definition_id, *criteria}
    changes[definition_id]["after"] = {
        "present": True,
        "value": copy.deepcopy(declaration["scope"]),
    }
    for criterion_id, value in criteria.items():
        changes[criterion_id]["after"] = {
            "present": True,
            "value": copy.deepcopy(value),
        }


def _remove_normative_branch_row(text: str, branch_id: str) -> str:
    """規範表の先頭セルで識別した分岐定義行を1件だけ除く。"""
    kept_lines: list[str] = []
    removed_count = 0
    for line in text.splitlines():
        match = descriptor_checker.STABLE_TABLE_CLAUSE_PATTERN.match(line)
        if match is not None and match.group("clause_id") == branch_id:
            removed_count += 1
            continue
        kept_lines.append(line)
    assert removed_count == 1
    return "\n".join(kept_lines) + "\n"


def _remove_single_line_containing(text: str, marker: str) -> str:
    """指定した機械可読markerを持つ行を1件だけ除く。"""
    kept_lines: list[str] = []
    removed_count = 0
    for line in text.splitlines():
        if marker in line:
            removed_count += 1
            continue
        kept_lines.append(line)
    assert removed_count == 1
    return "\n".join(kept_lines) + "\n"


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
    """規範表の64分岐を支援対象37件と理由付き対象外27件へ分ける。"""
    report = checker.validate_three_way_parity(REPOSITORY_ROOT)
    criteria = _criteria()
    expected_covered = criteria.requirement_branch_ids - frozenset(
        criteria.branch_coverage_exclusions
    )

    assert report.requirement_branch_ids == criteria.requirement_branch_ids
    assert report.covered_branch_ids == expected_covered
    assert {f"req:{item}" for item in report.covered_branch_ids} <= (
        report.descriptor_supporting_clause_ids
    )
    assert (
        report.covered_branch_ids | report.excluded_branch_ids
        == report.requirement_branch_ids
    )
    assert report.covered_branch_ids.isdisjoint(report.excluded_branch_ids)
    assert all(criteria.branch_coverage_exclusions.values())


def test_xc09_is_the_only_non_definition_mention_and_is_owned_by_adr_d8() -> None:
    """旧全文集合との差はXC-09だけで、D-8固有制約として帰属する。"""
    report = checker.validate_three_way_parity(REPOSITORY_ROOT)
    requirements_text = (REPOSITORY_ROOT / checker.REQUIREMENTS_PATH).read_text(
        encoding="utf-8"
    )

    assert len(checker.extract_requirement_branch_mentions(requirements_text)) == 65
    assert report.non_definition_branch_mentions == {"XC-09"}
    assert report.adr_d8_constraint_ids == {"XC-09"}
    assert report.requirement_constraint_owners == {
        "XC-09": ("D-8", "undoRows[]")
    }
    assert report.requirement_constraint_exclusions == {"XC-09": "E-1"}


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
        _descriptor_criteria().stage2_constraint_classes
    )


def test_d12_machine_readable_path_and_filename_literals_are_present() -> None:
    """D-12が領域・一般命名・descriptor固有命名をコード表記で持つ。"""
    adr_text = (REPOSITORY_ROOT / checker.ADR_PATH).read_text(encoding="utf-8")
    section = checker.extract_adr_decision_section(adr_text, "D-12")

    assert _criteria().d12_required_code_literals <= checker.extract_code_literals(
        section
    )
    assert checker.DESCRIPTOR_PATH.parts == (
        "contracts",
        "state-transition",
        "input_axes_descriptor_v1.json",
    )


def test_d12_freeze_baseline_ids_match_descriptor_exactly() -> None:
    """凍結基準の置き場・系列・保証境界IDをD-12と資産側宣言で双方向突合する。"""
    adr_text = (REPOSITORY_ROOT / checker.ADR_PATH).read_text(encoding="utf-8")
    section = checker.extract_adr_decision_section(adr_text, "D-12")
    declared = frozenset(
        literal
        for literal in _criteria().d12_required_code_literals
        if checker.D12_FREEZE_BASELINE_ID_PATTERN.fullmatch(literal) is not None
    )

    assert declared == {
        "freeze-baseline-assurance:declared-identities-only",
        "freeze-baseline-field:freezeBaseline",
        "freeze-baseline-scope:freezeBaseline.scope",
        "freeze-baseline-series:state-transition-contract-checks",
    }
    assert checker.extract_d12_freeze_baseline_ids(section) == declared


@pytest.mark.parametrize(
    "literal",
    [
        "freeze-baseline-assurance:declared-identities-only",
        "freeze-baseline-field:freezeBaseline",
        "freeze-baseline-scope:freezeBaseline.scope",
    ],
)
def test_d12_freeze_baseline_id_removal_from_adr_is_red_after_digest_recalculation(
    tmp_path: Path, literal: str
) -> None:
    """D-12だけから凍結基準IDを消すとdescriptorのdigestを合わせても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.ADR_PATH
    text = path.read_text(encoding="utf-8")
    marker = f"`{literal}`"
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, "凍結基準フィールドID", 1), encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"freezeBaseline宣言IDがexact-set不一致",
    ):
        checker.validate_three_way_parity(root)


@pytest.mark.parametrize(
    "literal",
    [
        "freeze-baseline-assurance:declared-identities-only",
        "freeze-baseline-field:freezeBaseline",
        "freeze-baseline-scope:freezeBaseline.scope",
    ],
)
def test_d12_freeze_baseline_id_removal_from_descriptor_is_red_after_reseal(
    tmp_path: Path, literal: str
) -> None:
    """資産側だけからIDを消し単一履歴とdigestを追随させても拒否する。"""
    root = _copy_fixture_root(tmp_path)

    def mutate(descriptor: dict[str, Any]) -> None:
        literals = descriptor["freezeBaseline"]["criteria"]["threeWayParity"][
            "d12RequiredCodeLiterals"
        ]
        literals.remove(literal)
        _synchronize_unaccepted_freeze_record(descriptor)

    _rewrite_descriptor(root, mutate)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"freezeBaseline宣言IDがexact-set不一致",
    ):
        checker.validate_three_way_parity(root)


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
        match=r"要件書の規範表にある分岐IDがexact-set不一致.*COLD-10",
    ):
        checker.validate_three_way_parity(root)


def test_cold09_normative_row_removal_is_red_even_if_other_mentions_remain(
    tmp_path: Path,
) -> None:
    """COLD-09規範行だけを消し履歴等に言及が残っても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.REQUIREMENTS_PATH
    text = path.read_text(encoding="utf-8")
    drifted = _remove_normative_branch_row(text, "COLD-09")
    assert "`COLD-09`" in drifted
    path.write_text(drifted, encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"規範表にある分岐IDがexact-set不一致.*COLD-09",
    ):
        checker.validate_three_way_parity(root)


def test_xc13_normative_row_removal_is_red_even_if_other_mentions_remain(
    tmp_path: Path,
) -> None:
    """XC-13原則行だけを消し履歴等に言及が残っても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.REQUIREMENTS_PATH
    text = path.read_text(encoding="utf-8")
    drifted = _remove_normative_branch_row(text, "XC-13")
    assert "`XC-13`" in drifted
    path.write_text(drifted, encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"規範表にある分岐IDがexact-set不一致.*XC-13",
    ):
        checker.validate_three_way_parity(root)


def test_xc13_principle_marker_removal_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """XC-13行を残して導出原則IDだけを消しても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.REQUIREMENTS_PATH
    text = path.read_text(encoding="utf-8")
    marker = f"`{_criteria().principle_markers['XC-13']}`"
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, "導出原則", 1), encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"XC-13規範行に凍結した原則IDが無い",
    ):
        checker.validate_three_way_parity(root)


def test_adr_d8_xc09_definition_removal_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """D-8のXC-09定義を消し他の言及が残っても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.ADR_PATH
    text = path.read_text(encoding="utf-8")
    drifted = _remove_single_line_containing(text, "`constraint:XC-09`")
    assert "`XC-09`" in drifted
    path.write_text(drifted, encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"D-8固有の制約定義IDがexact-set不一致.*XC-09",
    ):
        checker.validate_three_way_parity(root)


def test_requirement_xc09_ownership_removal_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """E-1のXC-09帰属を消し他の言及が残っても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.REQUIREMENTS_PATH
    text = path.read_text(encoding="utf-8")
    marker = "`constraint-owner:XC-09:adr:D-8:undoRows[]`"
    drifted = _remove_single_line_containing(text, marker)
    assert "`XC-09`" in drifted
    path.write_text(drifted, encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"E-1の外部制約帰属がexact-set不一致.*XC-09",
    ):
        checker.validate_three_way_parity(root)


def test_requirement_xc09_exclusion_removal_is_red_after_digest_recalculation(
    tmp_path: Path,
) -> None:
    """E-1表からXC-09を除外する宣言を消しても拒否する。"""
    root = _copy_fixture_root(tmp_path)
    path = root / checker.REQUIREMENTS_PATH
    text = path.read_text(encoding="utf-8")
    marker = "`constraint-exclusion:XC-09:req:E-1`"
    drifted = text.replace(marker, "外部制約除外", 1)
    assert drifted != text
    path.write_text(drifted, encoding="utf-8")
    _rewrite_descriptor(root)

    with pytest.raises(
        checker.ThreeWayParityError,
        match=r"E-1の外部制約除外がexact-set不一致.*XC-09",
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
