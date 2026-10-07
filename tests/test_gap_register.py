"""定義の穴9件を追跡するgap registerの骨格と状態述語を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_gap_register.py"
DESCRIPTOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"
PARITY_SCRIPT = (
    REPOSITORY_ROOT / "scripts" / "check_input_axes_three_way_parity.py"
)
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
_load_module("check_input_axes_descriptor", DESCRIPTOR_SCRIPT)
_load_module("check_input_axes_three_way_parity", PARITY_SCRIPT)
checker = _load_module("check_gap_register_under_test", SCRIPT)
REGISTER_PATH = REPOSITORY_ROOT / checker.REGISTER_PATH
SCHEMA_PATH = REPOSITORY_ROOT / checker.SCHEMA_PATH
CLAUSE_BRANCH_REGISTER_PATH = (
    REPOSITORY_ROOT / checker.CLAUSE_BRANCH_REGISTER_PATH
)
CLAUSE_BRANCH_SCHEMA_PATH = REPOSITORY_ROOT / checker.CLAUSE_BRANCH_SCHEMA_PATH


def _register() -> dict[str, Any]:
    """リポジトリのgap registerを読む。"""
    value = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _clause_only_register() -> dict[str, Any]:
    """段別述語の単体検査用にbranch段以降を空へ戻す。"""
    document = _register()
    for gap in document["gaps"]:
        gap["state"] = "open"
        gap["branchIds"] = []
        gap["rowIds"] = []
        gap["fixtureCaseIds"] = []
        gap["generatedCaseSelector"] = None
    return document


def _clause_branch_register() -> dict[str, Any]:
    """リポジトリの条文分岐台帳を読む。"""
    value = json.loads(CLAUSE_BRANCH_REGISTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _row_documents() -> dict[str, dict[str, Any]]:
    """凍結基準が宣言する規範行4層を実資産から読む。"""
    layers = _criteria().row_layers
    return {
        layer["sourcePath"]: json.loads(
            (REPOSITORY_ROOT / layer["sourcePath"]).read_text(encoding="utf-8")
        )
        for layer in layers
    }


def _row_rules() -> dict[str, Any]:
    """matrix行の語彙軸と典拠条文の宣言を読む。"""
    return json.loads((REPOSITORY_ROOT / checker.ROW_RULES_PATH).read_text(encoding="utf-8"))


def _fixture_documents() -> list[dict[str, Any]]:
    """凍結済みの手作業fixtureを実資産から読む。"""
    return [
        json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
        for path in checker.MANUAL_FIXTURE_PATHS
    ]


def _real_indexes(document: dict[str, Any]) -> dict[str, Any]:
    """実際の所有資産から5段すべての逆方向indexを組み立てる。"""
    rows = _row_documents()
    row_index = checker.row_reference_index(_criteria(), document["gaps"], rows)
    case_index, _ = checker.generated_case_reference_index(_criteria(), row_index, rows)
    return {
        "clauseIds": checker.clause_reference_index(_policy()),
        "branchIds": checker.clause_branch_reference_index(
            _clause_branch_register()
        ),
        "rowIds": row_index,
        "fixtureCaseIds": checker.fixture_reference_index(
            _clause_branch_register(), _fixture_documents()
        ),
        "generatedCaseSelector": case_index,
    }


def _clause_branch_policy() -> Any:
    """条文分岐台帳schemaから抽出・分類方針を読む。"""
    schema = json.loads(CLAUSE_BRANCH_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return checker.load_clause_branch_schema_policy(schema)


def _validate_clause_branches(document: dict[str, Any]) -> None:
    """要件書から抽出した条文・分岐IDで台帳を検証する。"""
    checker.validate_clause_branch_register_document(
        document,
        checker.load_requirement_clause_ids(REPOSITORY_ROOT),
        checker.load_requirement_branch_ids(REPOSITORY_ROOT),
        _clause_branch_policy(),
    )


def _criteria() -> Any:
    """資産側宣言からgap register検査基準を読む。"""
    descriptor = json.loads(
        (
            REPOSITORY_ROOT
            / checker.clause_id_source.DESCRIPTOR_PATH
        ).read_text(encoding="utf-8")
    )
    assert isinstance(descriptor, dict)
    return checker.load_gap_criteria(descriptor)


def _policy() -> Any:
    """schema資産から段ごとの参照検査方式を読む。"""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return checker.load_gap_schema_policy(schema, _criteria())


def _validate(
    document: dict[str, Any],
    reference_indexes: dict[str, Any] | None = None,
) -> None:
    """要件書から抽出した実在条文IDで文書を検証する。"""
    checker.validate_gap_register_document(
        document,
        checker.load_requirement_clause_ids(REPOSITORY_ROOT),
        _criteria(),
        _policy(),
        reference_indexes,
    )


def _reference_index(
    reference: str,
    *,
    gap_ids: frozenset[str] = frozenset({"GAP-01"}),
) -> Any:
    """1参照だけを持つ所有資産indexを作る。"""
    return checker.StageReferenceIndex(
        existing_references=frozenset({reference}),
        gap_ids_by_reference={reference: gap_ids},
    )


def _fill_all_stages(document: dict[str, Any]) -> dict[str, Any]:
    """先頭entryを5段充足したresolvedへする。"""
    gap = document["gaps"][0]
    gap["state"] = "resolved"
    gap["branchIds"] = ["BRANCH-01"]
    gap["rowIds"] = ["ROW-01"]
    gap["fixtureCaseIds"] = ["FIXTURE-01"]
    gap["generatedCaseSelector"] = {"caseIds": ["CASE-01"]}
    return document


def _all_stage_indexes(document: dict[str, Any]) -> dict[str, Any]:
    """先頭entryの5段すべてと双方向一致する参照indexを作る。"""
    gap = document["gaps"][0]
    selector = checker.canonical_reference_token(gap["generatedCaseSelector"])
    return {
        "clauseIds": _reference_index("FR-020"),
        "branchIds": _reference_index("BRANCH-01"),
        "rowIds": _reference_index("ROW-01"),
        "fixtureCaseIds": _reference_index("FIXTURE-01"),
        "generatedCaseSelector": _reference_index(selector),
    }


def test_repository_gap_register_is_green() -> None:
    """実資産が配置・命名・骨格・条文参照の検査を通る。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "gap-register: OK\n"
    assert result.stderr == ""


def test_schema_declares_exact_shape_and_reference_modes() -> None:
    """schemaが7フィールドと5段の参照検査方式を閉じて宣言する。"""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    policy = checker.load_gap_schema_policy(schema, _criteria())

    assert schema["additionalProperties"] is False
    assert schema["properties"]["gaps"]["items"]["additionalProperties"] is False
    assert policy.existence_only_stages == frozenset({"clauseIds"})
    assert policy.bidirectional_stages == frozenset(
        {"branchIds", "rowIds", "fixtureCaseIds", "generatedCaseSelector"}
    )
    assert policy.resolved_additional_bidirectional_stages == frozenset(
        {"clauseIds"}
    )


def test_clause_branch_register_has_64_rows_and_four_game_end_outcomes() -> None:
    """規範表64 IDと終了判定4結果を別の分岐層として全件列挙する。"""
    document = _clause_branch_register()
    policy = _clause_branch_policy()
    requirement_ids = checker.load_requirement_branch_ids(REPOSITORY_ROOT)
    requirement_entries = {
        branch["branchId"]
        for branch in document["branches"]
        if branch["branchKind"] == policy.requirement_branch_kind
    }
    outcome_entries = {
        branch["branchId"]
        for branch in document["branches"]
        if branch["branchKind"] == policy.game_end_outcome_kind
    }

    assert len(requirement_ids) == 64
    assert requirement_entries == requirement_ids
    assert outcome_entries == set(document["gameEndOutcomeBranches"].values())
    assert set(document["gameEndOutcomeBranches"]) == {
        "normalEnd",
        "extraInningContinue",
        "limitDraw",
        "tiebreakContinue",
    }
    assert document["branchCount"] == len(document["branches"]) == 68
    assert "XC-09" not in requirement_entries
    assert not {"H", "E", "K", "B"} & requirement_entries
    entries_by_id = {
        branch["branchId"]: branch for branch in document["branches"]
    }
    assert set(
        entries_by_id[document["gameEndOutcomeBranches"]["normalEnd"]][
            "relatedClauseBranchIds"
        ]
    ) == {"COLD-08", "COLD-09", "DRAW-06", "DRAW-10"}
    assert set(
        entries_by_id[
            document["gameEndOutcomeBranches"]["extraInningContinue"]
        ]["relatedClauseBranchIds"]
    ) == {"DRAW-07", "DRAW-08"}
    assert set(
        entries_by_id[document["gameEndOutcomeBranches"]["limitDraw"]][
            "relatedClauseBranchIds"
        ]
    ) == {"DRAW-09"}
    assert set(
        entries_by_id[
            document["gameEndOutcomeBranches"]["tiebreakContinue"]
        ]["relatedClauseBranchIds"]
    ) == {"DRAW-07", "DRAW-08"}
    _validate_clause_branches(document)


def test_clause_branch_register_records_creation_author_without_review_claim() -> None:
    """作成者記録を独立確認済みという署名へ読み替えず保持する。"""
    document = _clause_branch_register()
    schema = json.loads(CLAUSE_BRANCH_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert document["authorSignature"] == {
        "authorId": "codex",
        "recordedOn": "2026-09-28",
        "statement": "enumerated-directly-from-approved-requirements",
    }
    assurance = schema["x-pitchlog-clause-branch-register-policy"][
        "assuranceBoundary"
    ]
    assert "recorded-author-signature-fields-present" in assurance[
        "mechanicallyGuaranteed"
    ]
    assert "author-identity-is-truthful" in assurance["humanControls"]


def test_unknown_clause_branch_source_is_red() -> None:
    """名前空間形式が正しくても要件書に実在しない由来条文を拒否する。"""
    document = copy.deepcopy(_clause_branch_register())
    document["branches"][0]["sourceClauseIds"] = ["req:FR-999"]

    with pytest.raises(checker.GapRegisterError, match="実在しない由来条文ID"):
        _validate_clause_branches(document)


def test_missing_normative_branch_row_is_red() -> None:
    """要件書規範表の分岐を台帳から1件落としたexact-set不一致を拒否する。"""
    document = copy.deepcopy(_clause_branch_register())
    document["branches"] = [
        branch for branch in document["branches"] if branch["branchId"] != "COLD-09"
    ]
    document["branchCount"] = len(document["branches"])

    with pytest.raises(checker.GapRegisterError, match="規範表分岐と台帳"):
        _validate_clause_branches(document)


def test_missing_game_end_outcome_is_red() -> None:
    """終了判定4役割のうち1件が解決できない台帳を拒否する。"""
    document = copy.deepcopy(_clause_branch_register())
    document["branches"] = [
        branch
        for branch in document["branches"]
        if branch["branchId"] != document["gameEndOutcomeBranches"]["limitDraw"]
    ]
    document["branchCount"] = len(document["branches"])

    with pytest.raises(checker.GapRegisterError, match="game-end-outcome entry"):
        _validate_clause_branches(document)


def test_clause_branch_index_declares_every_unassigned_branch_exactly() -> None:
    """9つの穴に属さない分岐だけが資産側宣言と一致して空になる。"""
    document = _clause_branch_register()
    policy = _clause_branch_policy()
    index = checker.clause_branch_reference_index(document)
    actual_unassigned = frozenset(
        branch_id
        for branch_id, gap_ids in index.gap_ids_by_reference.items()
        if not gap_ids
    )

    assert len(index.existing_references) == 68
    assert actual_unassigned == policy.intentional_unassigned_branch_ids
    assert all(
        index.gap_ids_by_reference[branch_id]
        for branch_id in index.existing_references - actual_unassigned
    )
    _validate_clause_branches(document)


def test_five_resolved_four_open_gaps_have_real_bidirectional_references() -> None:
    """5件のresolvedと4件のopenを実資産の5段へ突合する。"""
    document = _register()
    expected_clauses = {
        "GAP-01": ["FR-020"],
        "GAP-02": ["E-1"],
        "GAP-03": ["F-1"],
        "GAP-04": ["F-1"],
        "GAP-05": ["FR-020", "FR-005"],
        "GAP-06": ["A-1", "FR-003"],
        "GAP-07": ["E-1", "FR-004"],
        "GAP-08": ["E-2", "A-2", "SO-03", "XC-13"],
        "GAP-09": ["A-3", "FR-004", "E-1", "ADV-02", "ADV-04", "RBI-01"],
    }

    assert len(document["gaps"]) == 9
    assert {gap["gapId"]: gap["clauseIds"] for gap in document["gaps"]} == (
        expected_clauses
    )
    assert {gap["gapId"] for gap in document["gaps"] if gap["state"] == "resolved"} == {
        "GAP-03", "GAP-04", "GAP-07", "GAP-08", "GAP-09"
    }
    assert {gap["gapId"] for gap in document["gaps"] if gap["state"] == "open"} == {
        "GAP-01", "GAP-02", "GAP-05", "GAP-06"
    }
    assert {gap["gapId"]: len(gap["rowIds"]) for gap in document["gaps"]} == {
        "GAP-01": 0, "GAP-02": 0, "GAP-03": 2,
        "GAP-04": 4, "GAP-05": 0, "GAP-06": 0,
        "GAP-07": 20, "GAP-08": 5, "GAP-09": 3,
    }
    assert {gap["gapId"]: len(gap["fixtureCaseIds"]) for gap in document["gaps"]} == {
        "GAP-01": 0, "GAP-02": 0, "GAP-03": 2,
        "GAP-04": 4, "GAP-05": 0, "GAP-06": 0,
        "GAP-07": 12, "GAP-08": 7, "GAP-09": 3,
    }
    assert all(
        all(checker._filled_stage_flags(gap, _criteria()))
        for gap in document["gaps"] if gap["state"] == "resolved"
    )
    assert all(
        checker._filled_stage_flags(gap, _criteria()) == (True, True, False, False, False)
        for gap in document["gaps"] if gap["state"] == "open"
    )
    _validate(document, _real_indexes(document))


def test_generated_selector_selects_cases_by_normative_row_ownership() -> None:
    """固定case IDなしでrowRefから5件のcase群を機械的に引く。"""
    document = _register()
    rows = _row_documents()
    row_index = checker.row_reference_index(_criteria(), document["gaps"], rows)
    _, selected = checker.generated_case_reference_index(_criteria(), row_index, rows)
    expected = {"GAP-03": 68, "GAP-04": 136, "GAP-07": 39,
                "GAP-08": 12, "GAP-09": 6}

    assert {
        gap["gapId"]: len(selected[checker.canonical_reference_token(
            gap["generatedCaseSelector"]
        )])
        for gap in document["gaps"] if gap["state"] == "resolved"
    } == expected
    assert all(
        gap["generatedCaseSelector"]["caseCount"] == expected[gap["gapId"]]
        for gap in document["gaps"] if gap["state"] == "resolved"
    )


def test_generated_case_added_only_to_asset_is_red() -> None:
    """生成caseだけ増やすとselectorの件数と逆方向帰属がずれる。"""
    document = _register()
    rows = _row_documents()
    source = "contracts/state-transition/game_end_contract_v1.json"
    added = copy.deepcopy(rows[source]["cases"][0])
    added["caseId"] = "GE-GAME-END-NORMAL-ADDED-ONLY-TO-ASSET"
    rows[source]["cases"].append(added)
    row_index = checker.row_reference_index(_criteria(), document["gaps"], rows)
    case_index, _ = checker.generated_case_reference_index(_criteria(), row_index, rows)
    indexes = _real_indexes(document)
    indexes["generatedCaseSelector"] = case_index

    with pytest.raises(checker.GapRegisterError, match="存在しない参照|双方向一致しない"):
        _validate(document, indexes)


@pytest.mark.parametrize(
    ("stage", "extra"),
    [
        ("clauseIds", "E-1"),
        ("branchIds", "SO-01"),
        ("rowIds", "matrixRows:batting-result:batting-result.walk"),
        ("fixtureCaseIds", "ST-SO-01"),
        ("generatedCaseSelector", None),
    ],
)
def test_resolved_gap_only_reference_is_red(stage: str, extra: str | None) -> None:
    """5段のどれもGAP側だけの参照増加を受け入れない。"""
    document = copy.deepcopy(_register())
    indexes = _real_indexes(document)
    gap = document["gaps"][2]
    if stage == "generatedCaseSelector":
        gap[stage]["caseCount"] += 1
    else:
        assert extra is not None
        gap[stage].append(extra)

    with pytest.raises(checker.GapRegisterError, match="存在しない参照|双方向一致しない"):
        _validate(document, indexes)


@pytest.mark.parametrize(
    ("stage", "extra"),
    [
        ("clauseIds", "E-1"),
        ("branchIds", "SO-01"),
        ("rowIds", "matrixRows:batting-result:batting-result.walk"),
        ("fixtureCaseIds", "ST-SO-01"),
        ("generatedCaseSelector", None),
    ],
)
def test_resolved_asset_only_reference_is_red(stage: str, extra: str | None) -> None:
    """5段のどれも所有資産側だけのGAP帰属増加を受け入れない。"""
    document = _register()
    indexes = _real_indexes(document)
    if stage == "generatedCaseSelector":
        extra = checker.canonical_reference_token(
            document["gaps"][6]["generatedCaseSelector"]
        )
    assert extra is not None
    index = indexes[stage]
    owners = dict(index.gap_ids_by_reference)
    owners[extra] = owners[extra] | frozenset({"GAP-03"})
    indexes[stage] = checker.StageReferenceIndex(index.existing_references, owners)

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, indexes)


@pytest.mark.parametrize("stage", [
    "clauseIds", "branchIds", "rowIds", "fixtureCaseIds", "generatedCaseSelector"
])
def test_resolved_with_any_empty_stage_is_red(stage: str) -> None:
    """resolvedの5段のいずれかを空にすると実資産検査で拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][2][stage] = None if stage == "generatedCaseSelector" else []

    with pytest.raises(checker.GapRegisterError):
        _validate(document, _real_indexes(document))


@pytest.mark.parametrize("gap_id", ["GAP-01", "GAP-02", "GAP-05", "GAP-06"])
def test_open_gap_without_rows_cannot_be_resolved(gap_id: str) -> None:
    """規範行のない4件をstate変更だけでresolvedにする経路を塞ぐ。"""
    document = copy.deepcopy(_register())
    next(gap for gap in document["gaps"] if gap["gapId"] == gap_id)["state"] = "resolved"

    with pytest.raises(checker.GapRegisterError, match="resolvedは5段すべて"):
        _validate(document, _real_indexes(document))


def test_fixture_index_uses_branch_register_gap_ownership() -> None:
    """両fixtureのcaseIdを分岐台帳のgapIdsから逆引きする。"""
    index = _real_indexes(_register())["fixtureCaseIds"]

    assert len(index.existing_references) == 31
    assert index.gap_ids_by_reference["GE-GAME-END-NORMAL"] == frozenset(
        {"GAP-03", "GAP-04"}
    )
    assert index.gap_ids_by_reference["ST-XC-01"] == frozenset()


def test_fixture_reference_added_only_to_gap_is_red() -> None:
    """GAP側だけに実在する別帰属のfixtureを足しても拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][6]["fixtureCaseIds"].append("ST-XC-01")

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, _real_indexes(document))


def test_fixture_reference_added_only_to_asset_is_red() -> None:
    """fixture側のbranchIdだけを変更した逆方向帰属の追加を拒否する。"""
    document = _register()
    fixture_documents = _fixture_documents()
    fixture = next(
        fixture for fixture in fixture_documents[0]["fixtures"]
        if fixture["case"]["caseId"] == "ST-XC-01"
    )
    fixture["case"]["branchId"] = "XC-02"
    indexes = _real_indexes(document)
    indexes["fixtureCaseIds"] = checker.fixture_reference_index(
        _clause_branch_register(), fixture_documents
    )

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, indexes)


def test_unknown_fixture_reference_is_red() -> None:
    """存在しないfixtureのcaseIdを指すと拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][6]["fixtureCaseIds"].append("ST-NOT-A-FIXTURE")

    with pytest.raises(checker.GapRegisterError, match="存在しない参照"):
        _validate(document, _real_indexes(document))


def test_open_skipping_fixture_stage_for_generated_selector_is_red() -> None:
    """fixtureCaseIdsが空のまま生成case段を埋めるprefix違反を拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][0]["generatedCaseSelector"] = {"caseIds": ["CASE-01"]}

    with pytest.raises(checker.GapRegisterError, match="連続したprefix"):
        _validate(document, _real_indexes(document))


def test_normative_row_natural_keys_are_unique_in_all_four_layers() -> None:
    """操作種別の重複も前提軸と値で分離し全54行を識別する。"""
    document = _register()
    index = _real_indexes(document)["rowIds"]

    assert len(index.existing_references) == 54
    assert len([row for row in index.existing_references if row.startswith("operationRows:")]) == 6
    assert "operationRows:substitution:state.gameEnded:false" in index.existing_references
    assert "operationRows:substitution:state.gameEnded:true" in index.existing_references


def test_step99_no_orphan_normative_rows() -> None:
    """4層54行すべてが分岐または要件条文に辿れることを確認する。"""
    orphans = checker.orphan_normative_row_ids(
        _criteria(), _row_documents(), _clause_branch_register(),
        checker.load_requirement_clause_ids(REPOSITORY_ROOT), _row_rules(),
    )
    assert orphans == []


def test_step99_orphan_row_is_red_without_case_coverage_check() -> None:
    """case参照を維持し、1行だけ条文への帰属を失わせて拒否する。"""
    rules = _row_rules()
    target = "batting-result.called-pitch"
    partition = next(
        rule for rule in rules["partitionRules"] if target in rule["vocabularyIds"]
    )
    partition["vocabularyIds"].remove(target)

    orphans = checker.orphan_normative_row_ids(
        _criteria(), _row_documents(), _clause_branch_register(),
        checker.load_requirement_clause_ids(REPOSITORY_ROOT), rules,
    )
    assert orphans == [f"matrixRows:batting-result:{target}"]
    with pytest.raises(checker.GapRegisterError, match="孤立した規範行"):
        checker.assert_no_orphan_normative_rows(orphans)


def test_step99_all_row_ids_resolve() -> None:
    """gapのrowIdsと266件のcase参照が一意な規範行へ解決する。"""
    rows = _row_documents()
    index = checker.row_reference_index(_criteria(), _register()["gaps"], rows)
    assert len(index.existing_references) == 54
    assert checker.unresolved_row_references(
        _criteria(), _register()["gaps"], rows, index
    ) == []


def test_step99_unknown_case_row_id_is_red_without_other_checks() -> None:
    """caseの行ID解決だけを検査し、未知の自然キーを拒否する。"""
    rows = _row_documents()
    source = "contracts/state-transition/state_transition_contract_v1.json"
    rows[source]["cases"][0]["rowRef"]["coordinate"]["resultId"] = "missing-result"
    index = checker.row_reference_index(_criteria(), _register()["gaps"], rows)

    unresolved = checker.unresolved_row_references(
        _criteria(), _register()["gaps"], rows, index
    )
    assert len(unresolved) == 1
    assert "matrixRows:batting-result:missing-result" in unresolved[0]
    with pytest.raises(checker.GapRegisterError, match="行IDを一意に解決できない"):
        checker.assert_row_ids_resolve(unresolved)


def test_row_reference_added_only_to_gap_is_red() -> None:
    """実在しても行側が帰属させない参照を拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][0]["rowIds"].append(
        "matrixRows:batting-result:batting-result.called-pitch"
    )

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, _real_indexes(document))


def test_row_reference_added_only_to_asset_is_red() -> None:
    """規範行の備考にだけGAP帰属を足しても拒否する。"""
    document = _register()
    row_documents = _row_documents()
    source = "contracts/state-transition/state_transition_contract_v1.json"
    row_documents[source]["matrixRows"][0]["remarks"] += " GAP-01"
    indexes = _real_indexes(document)
    indexes["rowIds"] = checker.row_reference_index(
        _criteria(), document["gaps"], row_documents
    )

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, indexes)


def test_unknown_row_reference_is_red() -> None:
    """存在しない行IDを指すと拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][2]["rowIds"].append("decisionRows:NOT-A-ROW")

    with pytest.raises(checker.GapRegisterError, match="存在しない参照"):
        _validate(document, _real_indexes(document))


def test_open_skipping_row_stage_for_fixture_is_red() -> None:
    """rowIdsが空のままfixtureを先行させるprefix違反を拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][0]["fixtureCaseIds"] = ["FIXTURE-01"]

    with pytest.raises(checker.GapRegisterError, match="連続したprefix"):
        _validate(document, _real_indexes(document))


def test_gap_side_branch_membership_mismatch_is_red() -> None:
    """gap側だけから既存分岐の帰属を落とした片方向変更を拒否する。"""
    document = copy.deepcopy(_register())
    document["gaps"][2]["branchIds"].remove("COLD-01")

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(
            document,
            {
                "branchIds": checker.clause_branch_reference_index(
                    _clause_branch_register()
                )
            },
        )


def test_branch_side_gap_membership_mismatch_is_red() -> None:
    """分岐側だけからgap帰属を落とした片方向変更を拒否する。"""
    branch_document = copy.deepcopy(_clause_branch_register())
    branch_document["branches"][0]["gapIds"] = []

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(
            _register(),
            {
                "branchIds": checker.clause_branch_reference_index(
                    branch_document
                )
            },
        )


def test_undeclared_unassigned_branch_is_red() -> None:
    """資産側宣言にない分岐を空のgap帰属へ戻す変更を拒否する。"""
    document = copy.deepcopy(_clause_branch_register())
    document["branches"][0]["gapIds"] = []

    with pytest.raises(checker.GapRegisterError, match="exact-set宣言"):
        _validate_clause_branches(document)


def test_declared_unassigned_branch_cannot_gain_silent_ownership() -> None:
    """非帰属宣言した分岐へgapを足すなら宣言の更新も要求する。"""
    document = copy.deepcopy(_clause_branch_register())
    branch = next(
        item for item in document["branches"] if item["branchId"] == "XC-01"
    )
    branch["gapIds"] = ["GAP-07"]

    with pytest.raises(checker.GapRegisterError, match="exact-set宣言"):
        _validate_clause_branches(document)


def test_requirement_clause_extractor_is_reused_and_requirement_scoped() -> None:
    """既存抽出器を要件書だけへ適用しADRだけの決定IDを混入させない。"""
    clause_ids = checker.load_requirement_clause_ids(REPOSITORY_ROOT)

    assert {"FR-020", "A-1", "A-2", "A-3", "E-1", "E-2", "F-1"} <= (
        clause_ids
    )
    assert "D-11" not in clause_ids


def test_skipping_clause_stage_before_branch_stage_is_red() -> None:
    """clauseIdsを空にしてbranchIdsだけ埋めた途中段の飛ばしを拒否する。"""
    document = copy.deepcopy(_clause_only_register())
    gap = document["gaps"][0]
    gap["clauseIds"] = []
    gap["branchIds"] = ["XMARK-01"]

    with pytest.raises(checker.GapRegisterError, match="連続したprefix"):
        _validate(document)


def test_unknown_requirement_clause_id_is_red() -> None:
    """文字列形式が妥当でも要件書に実在しないclauseIdを拒否する。"""
    document = copy.deepcopy(_clause_only_register())
    document["gaps"][0]["clauseIds"] = ["FR-999"]

    with pytest.raises(checker.GapRegisterError, match="要件書に実在しない"):
        _validate(document)


def test_open_unknown_branch_reference_is_red() -> None:
    """openの連続prefixでも所有資産に存在しないbranch参照を拒否する。"""
    document = copy.deepcopy(_clause_only_register())
    document["gaps"][0]["branchIds"] = ["BRANCH-MISSING"]
    indexes = {"branchIds": _reference_index("BRANCH-OTHER")}

    with pytest.raises(checker.GapRegisterError, match="存在しない参照"):
        _validate(document, indexes)


def test_open_filled_stage_without_reference_source_is_red() -> None:
    """参照元がまだ無い段を先に埋めても未確認を正常扱いしない。"""
    document = copy.deepcopy(_clause_only_register())
    document["gaps"][0]["branchIds"] = ["BRANCH-01"]

    with pytest.raises(checker.GapRegisterError, match="参照元が未整備"):
        _validate(document)


def test_open_reverse_branch_membership_mismatch_is_red() -> None:
    """gapからの参照だけがあり所有資産からの帰属が無いopenを拒否する。"""
    document = copy.deepcopy(_clause_only_register())
    document["gaps"][0]["branchIds"] = ["BRANCH-01"]
    indexes = {
        "branchIds": _reference_index("BRANCH-01", gap_ids=frozenset())
    }

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, indexes)


def test_open_contiguous_intermediate_prefix_is_green() -> None:
    """clauseとbranchまでを正しく埋めたopenの途中状態を受理する。"""
    document = copy.deepcopy(_clause_only_register())
    document["gaps"][0]["branchIds"] = ["BRANCH-01"]

    _validate(document, {"branchIds": _reference_index("BRANCH-01")})


def test_resolved_without_all_five_stages_is_red() -> None:
    """clauseIdsしか持たないentryをresolvedへ変えても受理しない。"""
    document = copy.deepcopy(_clause_only_register())
    document["gaps"][0]["state"] = "resolved"

    with pytest.raises(checker.GapRegisterError, match="resolvedは5段すべて"):
        _validate(document)


def test_resolved_with_reverse_mismatch_is_red() -> None:
    """5段が埋まっていても所有資産だけにある逆方向帰属を拒否する。"""
    document = _fill_all_stages(copy.deepcopy(_clause_only_register()))
    indexes = _all_stage_indexes(document)
    indexes["rowIds"] = checker.StageReferenceIndex(
        existing_references=frozenset({"ROW-01", "ROW-EXTRA"}),
        gap_ids_by_reference={
            "ROW-01": frozenset({"GAP-01"}),
            "ROW-EXTRA": frozenset({"GAP-01"}),
        },
    )

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, indexes)


def test_resolved_without_clause_reverse_membership_is_red() -> None:
    """resolvedではclause段も独立資産からの逆方向帰属を必要とする。"""
    document = _fill_all_stages(copy.deepcopy(_clause_only_register()))
    indexes = _all_stage_indexes(document)
    indexes.pop("clauseIds")

    with pytest.raises(checker.GapRegisterError, match="双方向一致しない"):
        _validate(document, indexes)


def test_resolved_with_all_bidirectional_stages_is_green() -> None:
    """5段すべてが実在し所有資産と双方向一致するresolvedを受理する。"""
    document = _fill_all_stages(copy.deepcopy(_clause_only_register()))

    _validate(document, _all_stage_indexes(document))


def test_state_progression_is_one_way() -> None:
    """実資産のresolvedをopenへ戻す逆遷移を拒否する。"""
    resolved_document = _register()
    open_document = copy.deepcopy(resolved_document)
    open_document["gaps"][2]["state"] = "open"

    checker.validate_state_progression(
        open_document, resolved_document, _criteria()
    )
    with pytest.raises(checker.GapRegisterError, match="resolvedからopenへの逆遷移"):
        checker.validate_state_progression(
            resolved_document, open_document, _criteria()
        )


def test_register_path_and_version_follow_d12_naming() -> None:
    """1階層のstate-transition領域と<対象>_v<N>.json命名を固定する。"""
    document = _register()

    assert checker.REGISTER_PATH.parts == (
        "contracts",
        "state-transition",
        "gap_register_v1.json",
    )
    assert checker.parity_checker.CONTRACT_FILENAME_PATTERN.fullmatch(
        checker.REGISTER_PATH.name
    )
    assert document["version"] == checker.REGISTER_PATH.stem
    assert document["schemaVersion"] == 1


REPORT_PATH = (
    REPOSITORY_ROOT
    / "docs/features/appendix-e-golden-vectors/unresolved-report.md"
)
DESIGN_PATH = REPOSITORY_ROOT / "docs/features/appendix-e-golden-vectors/design.md"


def _report_rows(section: str, column_count: int) -> list[list[str]]:
    """未解消レポートの指定区分を表の行として読む。"""
    report = REPORT_PATH.read_text(encoding="utf-8")
    start = f"<!-- report:{section}:start -->"
    end = f"<!-- report:{section}:end -->"
    assert report.count(start) == report.count(end) == 1
    table = report.split(start, 1)[1].split(end, 1)[0]
    lines = [line for line in table.splitlines() if line.startswith("|")]
    assert lines[1].startswith("| ---")
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    assert all(len(row) == column_count for row in rows)
    return rows[2:]


def test_unresolved_report_gap_states_match_register() -> None:
    """レポートの全GAP状態と送り先を実台帳に突き合わせる。"""
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "## 1. `gapRegister` の状態（9件）" in report
    assert "追跡状態" in report
    assert "解決したことを意味しない" in report
    rows = _report_rows("gap", 4)
    actual = {row[0]: row[1] for row in rows}
    expected = {gap["gapId"]: gap["state"] for gap in _register()["gaps"]}
    assert len(rows) == len(actual) == 9
    assert actual == expected
    assert {state: list(actual.values()).count(state) for state in set(actual.values())} == {
        "resolved": 5,
        "open": 4,
    }
    assert all(row[2] and row[3] for row in rows)
    stage2_ids = {row[0] for row in _report_rows("stage2", 4)}
    assert all(
        set(re.findall(r"\bS\d{2}\b", row[3])) <= stage2_ids for row in rows
    )


def test_unresolved_report_human_and_stage2_sources_resolve() -> None:
    """人間統制と段階2送りの全行に担当と設計書の実在断片を要求する。"""
    design = DESIGN_PATH.read_text(encoding="utf-8")
    report = REPORT_PATH.read_text(encoding="utf-8")
    sections = {"human": 9, "stage2": 34}
    assert "## 2. 人間統制に委ねた項目（9件）" in report
    assert "## 3. 段階2へ送った項目（34件）" in report
    for section, count in sections.items():
        rows = _report_rows(section, 4)
        ids = [row[0] for row in rows]
        prefix = "H" if section == "human" else "S"
        assert ids == [f"{prefix}{number:02}" for number in range(1, count + 1)]
        assert all(row[1] and row[2] and row[3] in design for row in rows)

    stage2 = {row[0]: row for row in _report_rows("stage2", 4)}
    assert "39件" in stage2["S25"][1]
    assert "2817件" in stage2["S28"][1]
    assert "12件" in stage2["S29"][1]
