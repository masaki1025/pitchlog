"""人間確認の署名記録について機械検査する範囲だけを検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
SIGNATURE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_human_review_signature.py"
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/human_review_signature_schema_v1.json"
)
SUBJECT_RELATIVE_PATH = Path(
    "contracts/state-transition/input_axes_descriptor_v1.json"
)
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_contract_v1.json"
)
REVIEW_SHEET_PATH = (
    REPOSITORY_ROOT
    / "docs/features/appendix-e-golden-vectors/matrix_rows_line_review.md"
)
DESIGN_PATH = REPOSITORY_ROOT / "docs/features/appendix-e-golden-vectors/design.md"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
descriptor_checker = _load_module(
    "check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH
)
checker = _load_module("check_human_review_signature", SIGNATURE_CHECKER_PATH)


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _schema() -> dict[str, Any]:
    """署名記録schemaを返す。"""
    return _load_object(SCHEMA_PATH)


def _signature_record() -> dict[str, Any]:
    """宣言済みの機械検査範囲を充足する署名記録を返す。"""
    schema = _schema()
    digest_rule = schema["x-pitchlog-human-review-signature-policy"][
        "subjectDigest"
    ]
    subject = descriptor_checker.load_json(
        REPOSITORY_ROOT / SUBJECT_RELATIVE_PATH, "署名対象"
    )
    return {
        "schemaVersion": 1,
        "signatureId": "input-axes-review",
        "subject": {
            "path": SUBJECT_RELATIVE_PATH.as_posix(),
            "digest": checker.compute_subject_digest(
                subject, digest_rule["safeIntegerLimit"]
            ),
        },
        "artifactAuthorId": "artifact-author",
        "recordedReviewerId": "recorded-reviewer",
        "recordedOn": "2026-09-28",
        "reviewScope": "対象JSON文書全体",
        "recordedMethod": "direct-clause-comparison",
        "attestations": [
            {
                "attestationId": "direct-clause-review-declared",
                "recordedResponse": True,
            }
        ],
    }


def _validate(record: dict[str, Any]) -> None:
    """署名記録をリポジトリの宣言で検証する。"""
    checker.validate_signature_record(
        REPOSITORY_ROOT,
        record,
        schema_value=_schema(),
    )


def test_repository_signature_schema_declares_record_only_assurance_boundary() -> None:
    """人間行為でなく記録だけを機械検査する境界を確認する。"""
    policy = _schema()["x-pitchlog-human-review-signature-policy"]
    assurance = policy["assuranceBoundary"]

    assert assurance["wordingRule"] == (
        "record-presence-and-value-checks-not-human-action-proof"
    )
    assert "review-actually-performed" in assurance["humanControls"]
    assert "reviewer-is-actually-a-different-person" in assurance["humanControls"]
    assert "review-was-actually-direct-from-authoritative-clauses" in assurance[
        "humanControls"
    ]
    assert "record-was-actually-authored-by-recorded-reviewer" in assurance[
        "humanControls"
    ]
    assert all("actually" not in claim for claim in assurance["mechanicallyGuaranteed"])
    assert policy["provenanceRelation"].startswith("step40-provenance")
    assert policy["devHarness63Relation"].startswith("separate-from-pr-line-review")
    design = DESIGN_PATH.read_text(encoding="utf-8")
    assert "署名の記載と対象 digest の一致だけ" in design
    assert "6.3 の PR 側の逐行確認実施記録とは別" in design


def test_matching_subject_digest_and_recorded_attestation_are_accepted() -> None:
    """対象digestと宣誓記載が揃った記録を受理する。"""
    _validate(_signature_record())


def test_subject_digest_mismatch_is_red() -> None:
    """署名対象の現物と一致しない記録digestを拒否する。"""
    record = _signature_record()
    record["subject"]["digest"] = "sha256:" + "0" * 64

    with pytest.raises(
        checker.HumanReviewSignatureRecordError,
        match="署名対象digestが現物と不一致",
    ):
        _validate(record)


def test_missing_recorded_attestation_is_red() -> None:
    """人間行為でなく必須の宣誓記載が欠けた記録を拒否する。"""
    record = _signature_record()
    del record["attestations"]

    with pytest.raises(
        checker.HumanReviewSignatureRecordError,
        match="必須キー不足: .*attestations",
    ):
        _validate(record)


def test_equal_recorded_author_and_reviewer_identifiers_are_red() -> None:
    """実人物でなく記録上の作成者・確認者識別子の同一を拒否する。"""
    record = _signature_record()
    record["recordedReviewerId"] = record["artifactAuthorId"]

    with pytest.raises(
        checker.HumanReviewSignatureRecordError,
        match="記録上の識別子が同一",
    ):
        _validate(record)


def test_unaccepted_recorded_attestation_response_is_red() -> None:
    """宣誓の真実性でなく、記録済み応答が充足値でない場合を拒否する。"""
    record = copy.deepcopy(_signature_record())
    record["attestations"][0]["recordedResponse"] = False

    with pytest.raises(
        checker.HumanReviewSignatureRecordError,
        match="宣誓の記録済み応答が充足値でない",
    ):
        _validate(record)


def test_unsupported_declared_digest_method_is_red() -> None:
    """実装していないdigest方式を検査済みとして扱わない。"""
    schema = copy.deepcopy(_schema())
    schema["x-pitchlog-human-review-signature-policy"]["subjectDigest"][
        "algorithm"
    ] = "unsupported"

    with pytest.raises(
        checker.HumanReviewSignatureRecordError,
        match="未対応のsubjectDigest.algorithm",
    ):
        checker.validate_signature_record(
            REPOSITORY_ROOT,
            _signature_record(),
            schema_value=schema,
        )


def test_matrix_rows_line_review_sheet_is_machine_generated(tmp_path: Path) -> None:
    """ステップ52の未確認シートを契約から決定的に生成する。"""
    generated = tmp_path / "matrix_rows_line_review.md"

    result = checker.main(
        [
            "--root",
            str(REPOSITORY_ROOT),
            "--matrix-review-contract",
            str(CONTRACT_PATH),
            "--output",
            str(generated),
        ]
    )

    assert result == 0
    assert generated.read_text(encoding="utf-8") == REVIEW_SHEET_PATH.read_text(
        encoding="utf-8"
    )
    sheet = generated.read_text(encoding="utf-8")
    assert "独立確認: **未実施**" in sheet
    assert "確認者:" not in sheet
    assert "確認済み" not in sheet
    assert "本表の全行に共通する前提:** 打撃結果" in sheet
    assert "state_transition_contract_v1.json` の `matrixRows[]`" in sheet
    assert "{\"" not in sheet
    assert "false" not in sheet
    table_rows = [
        line
        for line in sheet.splitlines()
        if line.startswith("| ")
        and line.removeprefix("| ").split(" | ", maxsplit=1)[0].isdigit()
    ]
    assert len(table_rows) == 12
    assert "| 1 | 見逃し | 無死 / 走者なし / カウント 0-0 / 投球イベント | S+1 |" in sheet
    assert "| 4 | ボール | 無死 / 走者なし / カウント 0-0 / 投球イベント | B+1 |" in sheet
    assert "| 7 | 振り逃げ | 2死 / 走者なし / カウント 0-2 / 投球イベント |" in sheet
    assert "| 9 | 三振ゲッツー | 1死 / 走者 1塁 / カウント 0-2 / 投球イベント |" in sheet
    assert "| 終了 | アウト | 1塁停止 | 2（打者・1塁走者） |" in sheet
    assert "| 10 | 四球 | 無死 / 走者 1塁・3塁 / カウント 3-0 / 投球イベント |" in sheet
    assert "| 11 | 死球 | 無死 / 走者 1塁・3塁 / カウント 0-0 / 投球イベント |" in sheet
    assert "| 12 | 申告敬遠 | 無死 / 走者 1塁・3塁 / カウント 0-0 / 非投球イベント |" in sheet
    assert "1塁→2塁（強制） / 3塁停止" in sheet
    assert "| 与四球・打席・四球 |" in sheet
    assert "requiredSet①はsafe/outの2行を要求" in sheet
    assert "## 短縮表示できなかった値" not in sheet
    assert "## 人間が判断すること" in sheet
    assert "段階2" in sheet


def test_matrix_rows_line_review_renderer_accepts_later_rows() -> None:
    """同じ描画器を後続ステップで行追加後も再利用できる。"""
    contract = _load_object(CONTRACT_PATH)
    later_row = copy.deepcopy(contract["matrixRows"][0])
    later_row["resultId"] = "batting-result.single"
    later_row["remarks"] = "後続ステップの再利用確認用"
    contract["matrixRows"].append(later_row)

    sheet = checker.render_matrix_rows_review_sheet(REPOSITORY_ROOT, contract)

    table_rows = [
        line
        for line in sheet.splitlines()
        if line.startswith("| ")
        and line.removeprefix("| ").split(" | ", maxsplit=1)[0].isdigit()
    ]
    assert len(table_rows) == 13
    assert "| 13 | 単打 |" in sheet


def test_matrix_rows_result_names_follow_vocabulary_seed(tmp_path: Path) -> None:
    """結果名を固定対応表でなくmanifest参照先の語彙シードから取得する。"""
    vocabulary_root = tmp_path / "contracts/vocabulary"
    state_transition_root = tmp_path / "contracts/state-transition"
    shutil.copytree(REPOSITORY_ROOT / "contracts/vocabulary", vocabulary_root)
    state_transition_root.mkdir(parents=True)
    shutil.copy2(
        REPOSITORY_ROOT
        / "contracts/state-transition/state_transition_contract_schema_v1.json",
        state_transition_root / "state_transition_contract_schema_v1.json",
    )
    seed_path = vocabulary_root / "input_vocabulary_v1.json"
    manifest_path = vocabulary_root / "vocabulary_manifest_v1.json"
    seed = _load_object(seed_path)
    seed["axes"][0]["entries"][0]["initialDisplayName"] = "見逃し（テスト）"
    seed_path.write_text(
        json.dumps(seed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = _load_object(manifest_path)
    manifest["seeds"][0]["contentHash"] = (
        checker.vocabulary_checker.compute_content_hash(seed)
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    sheet = checker.render_matrix_rows_review_sheet(
        tmp_path,
        _load_object(CONTRACT_PATH),
    )

    assert "| 1 | 見逃し（テスト） |" in sheet
