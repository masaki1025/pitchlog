"""人間確認の署名記録について機械検査する範囲だけを検証する。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
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
STAGE2_REVIEW_SHEET_PATH = (
    REPOSITORY_ROOT / "docs/features/adr003-stage2-runtime/step33_line_review.md"
)
GAME_END_CONTRACT_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/game_end_contract_v1.json"
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


GATE6_SIGNATURE_DIRECTORY = (
    REPOSITORY_ROOT / "docs/features/adr003-stage2-runtime/signatures"
)
GATE6_REVIEW_SHEET = (
    REPOSITORY_ROOT / "docs/features/adr003-stage2-runtime/step33_line_review.md"
)


def test_repository_gate6_signature_records_match_current_contracts() -> None:
    """TSK-538ゲート⑥の署名記録が現行の両契約と宣言どおりに一致する。"""
    records = {
        path.name: _load_object(path)
        for path in sorted(GATE6_SIGNATURE_DIRECTORY.glob("*.json"))
    }

    assert set(records) == {"gate6-game-end.json", "gate6-state-transition.json"}
    checker.validate_gate6_subject_carry(REPOSITORY_ROOT)
    subjects = set()
    for record in records.values():
        subjects.add(record["subject"]["path"])
        assert record["artifactAuthorId"] == "codex"
        assert record["recordedReviewerId"] == "山田正輝"
        assert "step33_line_review.md" in record["reviewScope"]
        sheet_digest = hashlib.sha256(GATE6_REVIEW_SHEET.read_bytes()).hexdigest()
        assert sheet_digest in record["reviewScope"], "署名後に逐行確認シートが変わった"
    assert subjects == {
        "contracts/state-transition/game_end_contract_v1.json",
        "contracts/state-transition/state_transition_contract_v1.json",
    }

    # 既必須harnessが今回PRの最終証拠検査を実際に実行する。
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            assert checker.main([
                "--root", str(REPOSITORY_ROOT), "--gate6-carry", "--ci",
            ]) == 0
            return
        elif os.environ.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}:
            pytest.fail("Actionsのeventが不明で最終委任を検査できない")
    print("gate6 subject carry: TECHNICAL ONLY; final delegation NOT CHECKED")


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
    """ステップ60の未確認表示を含むシートを契約から決定的に生成する。"""
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
    assert "確認済み" not in sheet
    assert "本表の全行に共通する前提:** なし" in sheet
    assert "state_transition_contract_v1.json` の `matrixRows[]`" in sheet

    assert "{\"" not in sheet
    assert '"投球数": false' not in sheet
    table_rows = [
        line
        for line in sheet.splitlines()
        if line.startswith("| ")
        and line.removeprefix("| ").split(" | ", maxsplit=1)[0].isdigit()
    ]
    assert len(table_rows) == 44
    assert (
        "| 1 | 打撃結果 | 見逃し | 無死 / 走者なし / カウント 0-0 / "
        "投球イベント | S+1 |"
    ) in sheet
    assert (
        "| 4 | 打撃結果 | ボール | 無死 / 走者なし / カウント 0-0 / "
        "投球イベント | B+1 |"
    ) in sheet
    assert "| 7 | 打撃結果 | 振り逃げ | 2死 / 走者なし / カウント 0-2 / 投球イベント |" in sheet
    assert "| 9 | 打撃結果 | 三振ゲッツー | 1死 / 走者 1塁 / カウント 0-2 / 投球イベント |" in sheet
    assert "| 終了 | アウト | 1塁停止 | 2（打者・1塁走者） |" in sheet
    assert "| 10 | 打撃結果 | 四球 | 無死 / 走者 1塁・3塁 / カウント 3-0 / 投球イベント |" in sheet
    assert "| 11 | 打撃結果 | 死球 | 無死 / 走者 1塁・3塁 / カウント 0-0 / 投球イベント |" in sheet
    assert (
        "| 12 | 打撃結果 | 申告敬遠 | 無死 / 走者 1塁・3塁 / カウント 0-0 / "
        "非投球イベント |"
    ) in sheet
    assert "1塁→2塁（強制） / 3塁停止" in sheet
    assert "| 与四球・打席・四球 |" in sheet
    assert "| 13 | 打撃結果 | 単打 | 無死 / 走者なし / カウント 0-0 / 投球イベント |" in sheet
    assert "| 14 | 打撃結果 | 二塁打 | 無死 / 走者なし / カウント 0-0 / 投球イベント |" in sheet
    assert "| 15 | 打撃結果 | 三塁打 | 無死 / 走者なし / カウント 0-0 / 投球イベント |" in sheet
    assert (
        "| 16 | 打撃結果 | 本塁打 | 無死 / 走者 1塁・2塁・3塁 / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert (
        "1塁→本塁（非フォース） / 2塁→本塁（非フォース） / "
        "3塁→本塁（非フォース）"
    ) in sheet
    assert "投球数・被安打・被本塁打・失点・打席・打数・安打・本塁打・塁打・得点・打点" in sheet
    assert "RBI-06により4得点・4打点" in sheet
    assert "| 17 | 打撃結果 | 凡打死 | 無死 / 走者なし / カウント 0-0 / 投球イベント |" in sheet
    assert (
        "| 18 | 打撃結果 | 凡打出塁 | 無死 / 走者 1塁・2塁 / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert "1塁→2塁（強制） / 2塁→3塁（強制）" in sheet
    assert (
        "| 19 | 打撃結果 | ファールフライ | 無死 / 走者なし / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert "| 20 | 打撃結果 | 併殺打 | 無死 / 走者 1塁 / カウント 0-0 / 投球イベント |" in sheet
    assert (
        "| 21 | 打撃結果 | ライナー併殺 | 無死 / 走者 1塁 / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert "2（打者・1塁走者）" in sheet
    assert (
        "| 22 | 打撃結果 | エラー | 無死 / 走者 1塁・2塁 / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert (
        "| 23 | 打撃結果 | 野手選択 | 無死 / 走者 1塁・2塁 / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert "投球数・失策・打席・打数" in sheet
    assert "対象野手・失策種別の公式記録判断は段階2待ち" in sheet
    assert "野手選択とする公式記録判断は段階2待ち" in sheet
    assert "| 24 | 打撃結果 | 犠打 | 無死 / 走者 1塁・2塁 / カウント 0-0 / 投球イベント |" in sheet
    assert "1塁→2塁（非フォース） / 2塁→3塁（非フォース）" in sheet
    assert "| 投球回算入アウト・投球数・打席・犠打 |" in sheet
    assert "| 25 | 打撃結果 | 犠飛 | 無死 / 走者 3塁 / カウント 0-0 / 投球イベント |" in sheet
    assert "3塁→本塁（非フォース）" in sheet
    assert "RBI-08・旧sacrifice" in sheet
    assert (
        "| 26 | 打撃結果 | 犠打失策 | 無死 / 走者 1塁・2塁 / "
        "カウント 0-0 / 投球イベント |"
    ) in sheet
    assert "投球数・失策・打席・犠打" in sheet
    assert "公認野球規則9.08の既定側" in sheet
    assert "安打狙いと判断して犠打を記録せず打数を記録する分岐" in sheet
    assert "GAP-09・段階2待ち" in sheet
    assert "公式記録上の分類・失策導出は段階2待ち" in sheet
    assert "requiredSet①はsafe/outの2行を要求" in sheet
    assert "| 27 | 打撃結果2 | PB |" in sheet
    assert "| 28 | 打撃結果2 | WP |" in sheet
    assert "| 29 | 打撃結果2 | 守備妨害 |" in sheet
    assert "| 30 | 打撃結果2 | 打撃妨害 |" in sheet
    assert "| 31 | 打撃結果2 | 走塁妨害 |" in sheet
    assert "| 32 | 打撃結果2 | ボーク |" in sheet
    assert "| 33 | 打撃結果2 | ピッチクロック違反 |" in sheet
    assert "規則上の既定ではない" in sheet
    assert "GAP-07の未解決差" in sheet
    assert (
        "| 34 | 走者イベント | 盗塁 | 無死 / 走者 1塁 / カウント 0-0 / "
        "投球イベント | — | — | — | 1塁→2塁（非フォース） | 0 | 投球数 |"
    ) in sheet
    assert (
        "| 35 | 走者イベント | バント | 無死 / 走者 1塁 / カウント 0-0 / "
        "投球イベント | — | — | — | 1塁停止 | 0 | 投球数 |"
    ) in sheet
    assert (
        "| 36 | 走者イベント | エンドラン | 無死 / 走者 1塁 / カウント 0-0 / "
        "投球イベント | — | — | — | 1塁→2塁（非フォース） | 0 | 投球数 |"
    ) in sheet
    assert (
        "| 37 | 走者イベント | 一塁牽制 | 無死 / 走者 1塁 / カウント 0-0 / "
        "非投球イベント | — | — | — | 1塁停止 | 0 | なし |"
    ) in sheet
    assert (
        "| 38 | 走者イベント | 二塁牽制 | 無死 / 走者 2塁 / カウント 0-0 / "
        "非投球イベント | — | — | — | 2塁停止 | 0 | なし |"
    ) in sheet
    assert (
        "| 39 | 走者イベント | 三塁牽制 | 無死 / 走者 3塁 / カウント 0-0 / "
        "非投球イベント | — | — | — | 3塁停止 | 0 | なし |"
    ) in sheet
    assert (
        "| 40 | 走者イベント | 1塁牽制 | 無死 / 走者 1塁 / カウント 0-0 / "
        "非投球イベント | — | — | — | 1塁停止 | 0 | なし |"
    ) in sheet
    assert (
        "| 41 | 走者イベント | 2塁牽制 | 無死 / 走者 2塁 / カウント 0-0 / "
        "非投球イベント | — | — | — | 2塁停止 | 0 | なし |"
    ) in sheet
    assert (
        "| 42 | 走者イベント | 3塁牽制 | 無死 / 走者 3塁 / カウント 0-0 / "
        "非投球イベント | — | — | — | 3塁停止 | 0 | なし |"
    ) in sheet
    assert "牽制死・牽制エラーはrunnerEventPayloadで上書きする実結果" in sheet
    assert "A-4の成否はFR-027の分析・集計" in sheet
    assert "本行単独からは導出しない" in sheet
    assert "## 短縮表示できなかった値" in sheet
    assert "## 人間が判断すること" in sheet
    assert "段階2" in sheet


def test_stage2_line_review_sheet_is_complete_and_reproducible(tmp_path: Path) -> None:
    """規範行と派生caseを全件載せ、2回の生成をバイト一致させる。"""
    generated_paths = [tmp_path / "first.md", tmp_path / "second.md"]
    for path in generated_paths:
        assert (
            checker.main(
                [
                    "--root",
                    str(REPOSITORY_ROOT),
                    "--stage2-review",
                    "--output",
                    str(path),
                ]
            )
            == 0
        )
    sheet = STAGE2_REVIEW_SHEET_PATH.read_bytes()
    assert generated_paths[0].read_bytes() == generated_paths[1].read_bytes() == sheet
    assert hashlib.sha256(generated_paths[0].read_bytes()).digest() == hashlib.sha256(
        generated_paths[1].read_bytes()
    ).digest()

    game_end = _load_object(GAME_END_CONTRACT_PATH)
    state = _load_object(CONTRACT_PATH)
    text = sheet.decode("utf-8")
    assert text.count("#### `decisionRows[") == len(game_end["decisionRows"])
    assert text.count("#### `operationRows[") == len(state["operationRows"])
    assert text.count("#### `undoRows[") == len(state["undoRows"])
    selected_cases = game_end["cases"] + [
        case
        for case in state["cases"]
        if case["rowRef"]["layer"] in {"operationRows", "undoRows"}
    ]
    assert text.count("##### case `") == len(selected_cases)
    for case in selected_cases:
        assert text.count(f"##### case `{case['caseId']}`") == 1
    assert "独立確認: **未実施**" in text
    assert "作成者: codex" in text
    assert "[x]" not in text


def test_stage2_line_review_sheet_detects_contract_drift() -> None:
    """契約の期待値が変わると保存済みシートとの一致が崩れる。"""
    game_end = _load_object(GAME_END_CONTRACT_PATH)
    state = _load_object(CONTRACT_PATH)
    game_end["cases"][0]["decision"]["xMark"] = "blank"
    changed = checker.render_stage2_line_review_sheet(
        REPOSITORY_ROOT, game_end, state
    )
    assert changed != STAGE2_REVIEW_SHEET_PATH.read_text(encoding="utf-8")

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
    assert len(table_rows) == len(contract["matrixRows"])
    assert f"| {len(contract['matrixRows'])} | 打撃結果 | 単打 |" in sheet


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

    assert "| 1 | 打撃結果 | 見逃し（テスト） |" in sheet


def _carry() -> dict[str, Any]:
    """今回限定のcarry候補を読む。本人署名recordとしては扱わない。"""
    return _load_object(REPOSITORY_ROOT / checker.GATE6_CARRY_PATH)


def _override_carry(monkeypatch: pytest.MonkeyPatch, carry: dict[str, Any],
                    subject: dict[str, Any] | None = None) -> None:
    """保存資産を変更せず、変異した宣言/対象を読取境界へ供給する。"""
    original = checker.descriptor_checker.load_json

    def read(path: Path, label: str) -> object:
        if path == REPOSITORY_ROOT / checker.GATE6_CARRY_PATH:
            return copy.deepcopy(carry)
        if subject is not None and path == CONTRACT_PATH:
            return copy.deepcopy(subject)
        return original(path, label)

    monkeypatch.setattr(checker.descriptor_checker, "load_json", read)


def test_subject_carry_is_technical_only_without_final_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """local成功は最終委任・本人確認・署名成功を表明しない。"""
    assert checker.main(["--root", str(REPOSITORY_ROOT), "--gate6-carry"]) == 0
    assert "TECHNICAL ONLY; final delegation NOT CHECKED" in capsys.readouterr().out
    with pytest.raises(checker.HumanReviewSignatureRecordError, match="eventが未提供"):
        checker.validate_delegated_gate6_subject_carry(REPOSITORY_ROOT, None)


def test_subject_carry_ci_requires_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """--ciはevent不在をlocal成功へfallbackしない。"""
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert checker.main(["--root", str(REPOSITORY_ROOT), "--gate6-carry", "--ci"]) == 1


@pytest.mark.parametrize(
    "target", ["authority", "retained", "anchor", "current", "receipt", "scope"],
)
def test_subject_carry_rejects_invalid_binding(
    monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    """根拠/保存byte/旧対象/現対象/受理記録/本人scopeの変異を拒否する。"""
    carry = _carry()
    if target == "authority":
        carry["authority"]["sha256"] = "0" * 64
    elif target == "retained":
        carry["retainedDocuments"][0]["sha256"] = "0" * 64
    elif target == "anchor":
        carry["subjects"][0]["oldSubjectCommit"] = "0" * 40
    elif target == "current":
        carry["subjects"][0]["currentSubjectDigest"] = "sha256:" + "0" * 64
    elif target == "receipt":
        carry["adoptionReceiptDigest"] = "sha256:" + "0" * 64
    else:
        carry["boundary"]["personalReviewClaimed"] = True
    _override_carry(monkeypatch, carry)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_subject_carry(REPOSITORY_ROOT)


@pytest.mark.parametrize("target", ["old-projection", "undeclared-field", "new-case"])
def test_subject_carry_rejects_change_even_when_current_digest_follows(
    monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    """新digestだけ追随しても旧範囲変更・許可外差分・新case改変は通らない。"""
    carry = _carry()
    subject = _load_object(CONTRACT_PATH)
    if target == "old-projection":
        subject["operationRows"][0]["operationResult"] = "rejected-precondition"
    elif target == "undeclared-field":
        subject["unauthorized"] = True
    else:
        subject["cases"][-1]["expected"]["statFlags"]["安打"] = False
    entry = next(
        x for x in carry["subjects"]
        if x["path"] == str(CONTRACT_PATH.relative_to(REPOSITORY_ROOT))
    )
    policy = _schema()["x-pitchlog-human-review-signature-policy"]
    limit = policy["subjectDigest"]["safeIntegerLimit"]
    entry["currentSubjectDigest"] = checker.compute_subject_digest(subject, limit)
    _override_carry(monkeypatch, carry, subject)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_subject_carry(REPOSITORY_ROOT)


def _final_carry_fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, dict[str, Any]]:
    """実承認と混同しない合成commentで、既core_guardをそのまま実行する。"""
    guard = checker._carry_core_guard(REPOSITORY_ROOT)
    authority = _carry()["authority"]
    head = checker._carry_git_bytes(REPOSITORY_ROOT, ["rev-parse", "HEAD"]).decode().strip()
    url = f"https://github.com/{authority['repository']}/pull/{authority['pr']}#issuecomment-123"
    event = guard.PullRequestEvent(
        base_sha=authority["baseRevision"], head_sha=head,
        body=f"PO-DELEGATION-EVIDENCE: {url}", number=authority["pr"],
        repository=authority["repository"], head_repository=authority["repository"],
        head_branch=authority["branch"],
    )
    evidence = {
        "authority_sha256": authority["sha256"], "pr": event.number,
        "base": event.base_sha, "head": event.head_sha,
        "diff_sha256": guard._delegation_diff(REPOSITORY_ROOT, event),
        "paths": guard.changed_paths(REPOSITORY_ROOT, event.base_sha, event.head_sha),
        "reviewer_agent": "fixture-reviewer", "candidate_agents": ["fixture-author"],
        "independent": True, "verdict": "approved", "findings": [],
        "report": {"task": "fixture-reviewer", "reviewed_head": head,
                   "text": "synthetic unit fixture; not an actual independent review"},
    }
    policy = _load_object(REPOSITORY_ROOT / authority["path"])
    comment = {
        "id": 123, "html_url": url,
        "issue_url": f"https://api.github.com/repos/{authority['repository']}/issues/{event.number}",
        "author_association": "OWNER", "user": {"login": policy["publisher"]},
        "body": guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence),
    }
    monkeypatch.setattr(guard, "_fetch_delegation_comment", lambda _: comment)
    monkeypatch.setattr(guard, "load_pull_request_event", lambda: event)
    monkeypatch.setattr(checker, "_carry_core_guard", lambda _: guard)
    # 未commitの候補にも使える、最終checkoutのGit blobを表す合成境界。
    # 実CI経路ではこの差替えを使わず、必ず本物のevent.head blobを読む。
    original = checker._carry_git_bytes

    def read_git(root: Path, arguments: list[str]) -> bytes:
        if arguments[0] == "show" and arguments[1].startswith(head + ":"):
            return (root / arguments[1].split(":", 1)[1]).read_bytes()
        return original(root, arguments)

    monkeypatch.setattr(checker, "_carry_git_bytes", read_git)
    return guard, event, comment


def test_final_carry_uses_existing_core_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一event/現byte/全差分の合成正常証拠だけを既判定器で受理する。"""
    _, event, _ = _final_carry_fixture(monkeypatch)
    checker.validate_delegated_gate6_subject_carry(REPOSITORY_ROOT, event)


@pytest.mark.parametrize(
    "target", ["stale-head", "diff", "open-p1", "same-author", "api-missing", "bytes"],
)
def test_final_carry_rejects_missing_stale_or_unresolved_evidence(
    monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    """最終対象/全差分/非作者/重大指摘/API/現byteの拒否を実判定へ通す。"""
    guard, event, comment = _final_carry_fixture(monkeypatch)
    evidence = json.loads(comment["body"].split("\n", 1)[1])
    if target == "stale-head":
        evidence["head"] = "0" * 40
    elif target == "diff":
        evidence["diff_sha256"] = "0" * 64
    elif target == "open-p1":
        evidence["findings"] = [{"severity": "P1", "resolved": False, "detail": "open"}]
    elif target == "same-author":
        evidence["candidate_agents"] = [evidence["reviewer_agent"]]
    elif target == "api-missing":
        def fail(_: str) -> Any:
            raise guard.GuardError("委任証拠APIを取得できない")
        monkeypatch.setattr(guard, "_fetch_delegation_comment", fail)
    else:
        original = checker._carry_git_bytes
        def different(root: Path, arguments: list[str]) -> bytes:
            if arguments == ["show", f"{event.head_sha}:{checker.GATE6_CARRY_PATH}"]:
                return b"{}"
            return original(root, arguments)
        monkeypatch.setattr(checker, "_carry_git_bytes", different)
    comment["body"] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_delegated_gate6_subject_carry(REPOSITORY_ROOT, event)


@pytest.mark.parametrize("stale", [False, True])
def test_required_repository_test_calls_ci_validation(
    monkeypatch: pytest.MonkeyPatch, stale: bool,
) -> None:
    """既必須harness testが--ciを実行し、旧HEAD証拠では実際に失敗する。"""
    guard, _, comment = _final_carry_fixture(monkeypatch)
    if stale:
        evidence = json.loads(comment["body"].split("\n", 1)[1])
        evidence["head"] = "0" * 40
        comment["body"] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    if stale:
        with pytest.raises(AssertionError):
            test_repository_gate6_signature_records_match_current_contracts()
    else:
        test_repository_gate6_signature_records_match_current_contracts()


def _other_pr_fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    """PR baseに既受理carryがある別PRの合成入力を作る。実受理ではない。"""
    guard, previous, _ = _final_carry_fixture(monkeypatch)
    event = guard.PullRequestEvent(
        base_sha=previous.base_sha, head_sha=previous.head_sha, body=previous.body,
        number=previous.number + 1, repository=previous.repository,
        head_repository=previous.head_repository, head_branch="fix/other-pr-fixture",
    )
    monkeypatch.setattr(guard, "load_pull_request_event", lambda: event)
    before = _carry()
    paths = [str(checker.GATE6_CARRY_PATH), str(checker.GATE6_CARRY_SCHEMA_PATH)]
    paths.extend(subject["path"] for subject in before["subjects"])
    base_bytes = {path: (REPOSITORY_ROOT / path).read_bytes() for path in paths}
    original = checker._carry_git_bytes

    def read(root: Path, arguments: list[str]) -> bytes:
        if arguments[0] == "show" and arguments[1].startswith(event.base_sha + ":"):
            path = arguments[1].split(":", 1)[1]
            if path in base_bytes:
                return base_bytes[path]
        return original(root, arguments)

    monkeypatch.setattr(checker, "_carry_git_bytes", read)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    return guard, event


def test_other_pr_cannot_follow_changed_case_with_changed_carry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1反例: 別PRで安打flagと許可差分/digestを共変更しても必須testが拒否する。"""
    _other_pr_fixture(monkeypatch)
    carry = _carry()
    subject = _load_object(CONTRACT_PATH)
    subject["cases"][-1]["expected"]["statFlags"]["安打"] = False
    entry = next(x for x in carry["subjects"] if x["path"] == str(
        CONTRACT_PATH.relative_to(REPOSITORY_ROOT)
    ))
    change = next(x for x in entry["allowedChanges"] if x["pointer"] == "/cases")
    change["values"][-1] = copy.deepcopy(subject["cases"][-1])
    limit = _schema()["x-pitchlog-human-review-signature-policy"]["subjectDigest"][
        "safeIntegerLimit"
    ]
    entry["currentSubjectDigest"] = checker.compute_subject_digest(subject, limit)
    _override_carry(monkeypatch, carry, subject)
    with pytest.raises(AssertionError):
        test_repository_gate6_signature_records_match_current_contracts()


def test_other_pr_inherits_only_unchanged_base_without_new_acceptance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """別PRの不変継承は通り、今回PRの新受理や新署名とは表示しない。"""
    guard, _ = _other_pr_fixture(monkeypatch)

    def unexpected(_: str) -> Any:
        raise AssertionError("別PRの不変継承で新PR183の証拠を取りに行かない")

    monkeypatch.setattr(guard, "_fetch_delegation_comment", unexpected)
    test_repository_gate6_signature_records_match_current_contracts()
    assert "UNCHANGED FROM PR BASE; no new PR183 acceptance" in capsys.readouterr().out


@pytest.mark.parametrize("target", ["carry", "schema", "subject"])
def test_other_pr_requires_base_carry_schema_and_subject(
    monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    """既受理のPR base入力が欠けた時は現在値を基準へすり替えない。"""
    _, event = _other_pr_fixture(monkeypatch)
    paths = {
        "carry": str(checker.GATE6_CARRY_PATH),
        "schema": str(checker.GATE6_CARRY_SCHEMA_PATH),
        "subject": str(CONTRACT_PATH.relative_to(REPOSITORY_ROOT)),
    }
    original = checker._carry_git_bytes

    def missing(root: Path, arguments: list[str]) -> bytes:
        if arguments == ["show", f"{event.base_sha}:{paths[target]}"]:
            raise checker.HumanReviewSignatureRecordError("PR base入力が欠落")
        return original(root, arguments)

    monkeypatch.setattr(checker, "_carry_git_bytes", missing)
    with pytest.raises(AssertionError):
        test_repository_gate6_signature_records_match_current_contracts()


def test_other_pr_rejects_changed_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """schemaだけの変更も既受理の継承へ黙って取り込まない。"""
    _other_pr_fixture(monkeypatch)
    original = checker.descriptor_checker.load_json

    def changed(path: Path, label: str) -> object:
        value = original(path, label)
        if path == REPOSITORY_ROOT / checker.GATE6_CARRY_SCHEMA_PATH:
            value = copy.deepcopy(value)
            value["title"] += " changed by another PR"
        return value

    monkeypatch.setattr(checker.descriptor_checker, "load_json", changed)
    with pytest.raises(AssertionError):
        test_repository_gate6_signature_records_match_current_contracts()


def test_other_pr_rejects_foreign_head_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """別PRでもeventのrepo境界と現Git byteの検査を省略しない。"""
    guard, event = _other_pr_fixture(monkeypatch)
    event = guard.PullRequestEvent(**{**vars(event), "head_repository": "foreign/repository"})
    monkeypatch.setattr(guard, "load_pull_request_event", lambda: event)
    with pytest.raises(AssertionError):
        test_repository_gate6_signature_records_match_current_contracts()


@pytest.mark.parametrize("field", ["head_repository", "head_branch"])
def test_pr183_retains_exact_repository_and_branch_gate(
    monkeypatch: pytest.MonkeyPatch, field: str,
) -> None:
    """反映1でもPR183の同repo/対象branchの境界を維持する。"""
    guard, event, _ = _final_carry_fixture(monkeypatch)
    value = "foreign/repository" if field == "head_repository" else "fix/another-branch"
    event = guard.PullRequestEvent(**{**vars(event), field: value})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(REPOSITORY_ROOT, event)


def test_required_ci_route_rejects_missing_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """必須testでもCI event欠落をtechnical成功へ戻さない。"""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    with pytest.raises(AssertionError):
        test_repository_gate6_signature_records_match_current_contracts()


def test_other_pr_dispatch_cannot_be_retargeted_by_carry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可変宣言を同時に変えても別PRを今回の新受理経路へ移さない。"""
    _, event = _other_pr_fixture(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(checker, "validate_delegated_gate6_subject_carry",
                        lambda *_: calls.append("new-acceptance"))
    monkeypatch.setattr(checker, "validate_other_pr_gate6_carry_unchanged",
                        lambda *_: calls.append("unchanged-base"))
    carry = _carry()
    carry["authority"]["pr"] = event.number
    _override_carry(monkeypatch, carry)
    result = checker.validate_gate6_ci_event(REPOSITORY_ROOT, event)
    assert calls == ["unchanged-base"]
    assert "no new PR183 acceptance" in result
