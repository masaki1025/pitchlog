"""定義の穴9件を追跡するgap registerの骨格と状態述語を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
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
        gap["branchIds"] = []
    return document


def _clause_branch_register() -> dict[str, Any]:
    """リポジトリの条文分岐台帳を読む。"""
    value = json.loads(CLAUSE_BRANCH_REGISTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


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


def test_nine_open_gaps_have_clause_and_branch_prefix_filled() -> None:
    """全9件がclauseIdsとbranchIdsまでを持つopenの連続prefixである。"""
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
        "GAP-09": ["A-3", "E-1", "ADV-02", "ADV-04", "RBI-01"],
    }

    assert len(document["gaps"]) == 9
    assert {gap["gapId"]: gap["clauseIds"] for gap in document["gaps"]} == (
        expected_clauses
    )
    assert all(gap["state"] == "open" for gap in document["gaps"])
    assert all(
        gap["branchIds"]
        and gap["rowIds"] == []
        and gap["fixtureCaseIds"] == []
        and gap["generatedCaseSelector"] is None
        for gap in document["gaps"]
    )
    _validate(
        document,
        {
            "branchIds": checker.clause_branch_reference_index(
                _clause_branch_register()
            )
        },
    )


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
    """openからresolvedだけを許しresolvedからopenへの逆遷移を拒否する。"""
    open_document = _register()
    resolved_document = copy.deepcopy(open_document)
    resolved_document["gaps"][0]["state"] = "resolved"

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
