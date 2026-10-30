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
    # 旧render/旧carry回帰の入力は署名済みanchorへ固定する。
    # 必須repository testはこのhelperを使わず、実checkoutの新appendを検査する。
    if path in {CONTRACT_PATH, GAME_END_CONTRACT_PATH}:
        raw = checker._carry_git_bytes(REPOSITORY_ROOT, [
            "show", f"{checker._gate6_ready_values(REPOSITORY_ROOT)[0]}:"
            f"{path.relative_to(REPOSITORY_ROOT).as_posix()}",
        ])
        value = json.loads(raw)
    else:
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


def _legacy_render_root(tmp_path: Path) -> Path:
    """旧44行の描画入力をschema/語彙も含め同じ固定anchorへ隔離する。"""
    root = tmp_path / "legacy-render-anchor"
    paths = (
        checker.STATE_TRANSITION_CONTRACT_PATH,
        checker.STATE_TRANSITION_SCHEMA_PATH,
        checker.GAME_END_CONTRACT_PATH,
        checker.GAME_END_SCHEMA_PATH,
        checker.VOCABULARY_MANIFEST_PATH,
        "contracts/vocabulary/input_vocabulary_v1.json",
        "contracts/vocabulary/vocabulary_manifest_schema_v1.json",
        "contracts/vocabulary/vocabulary_seed_schema_v1.json",
    )
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(checker._carry_git_bytes(REPOSITORY_ROOT, [
            "show", f"{checker._gate6_ready_values(REPOSITORY_ROOT)[0]}:{relative}",
        ]))
    return root


def test_matrix_rows_line_review_sheet_is_machine_generated(tmp_path: Path) -> None:
    """ステップ60の未確認表示を含むシートを契約から決定的に生成する。"""
    legacy_root = _legacy_render_root(tmp_path)
    generated = tmp_path / "matrix_rows_line_review.md"

    result = checker.main(
        [
            "--root",
            str(legacy_root),
            "--matrix-review-contract",
            str(legacy_root / CONTRACT_PATH.relative_to(REPOSITORY_ROOT)),
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


def test_stage2_line_review_sheet_detects_contract_drift(tmp_path: Path) -> None:
    """契約の期待値が変わると保存済みシートとの一致が崩れる。"""
    legacy_root = _legacy_render_root(tmp_path)
    game_end = _load_object(GAME_END_CONTRACT_PATH)
    state = _load_object(CONTRACT_PATH)
    game_end["cases"][0]["decision"]["xMark"] = "blank"
    changed = checker.render_stage2_line_review_sheet(
        legacy_root, game_end, state
    )
    assert changed != STAGE2_REVIEW_SHEET_PATH.read_text(encoding="utf-8")

def test_matrix_rows_line_review_renderer_accepts_later_rows(tmp_path: Path) -> None:
    """同じ描画器を後続ステップで行追加後も再利用できる。"""
    legacy_root = _legacy_render_root(tmp_path)
    contract = _load_object(CONTRACT_PATH)
    later_row = copy.deepcopy(contract["matrixRows"][0])
    later_row["resultId"] = "batting-result.single"
    later_row["remarks"] = "後続ステップの再利用確認用"
    contract["matrixRows"].append(later_row)

    sheet = checker.render_matrix_rows_review_sheet(legacy_root, contract)

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
    legacy_root = _legacy_render_root(tmp_path)
    vocabulary_root = tmp_path / "contracts/vocabulary"
    state_transition_root = tmp_path / "contracts/state-transition"
    shutil.copytree(legacy_root / "contracts/vocabulary", vocabulary_root)
    state_transition_root.mkdir(parents=True)
    shutil.copy2(
        legacy_root
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


def _legacy_carry_reader_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """旧carryの合成回帰だけを旧snapshotへ向け、新受理fixtureと分離する。"""
    original = checker.descriptor_checker.load_json
    subjects = {path: _load_object(path) for path in (CONTRACT_PATH, GAME_END_CONTRACT_PATH)}

    def read(path: Path, label: str) -> object:
        if path in subjects:
            return copy.deepcopy(subjects[path])
        return original(path, label)

    monkeypatch.setattr(checker.descriptor_checker, "load_json", read)
    monkeypatch.setattr(checker, "_gate6_t1_append_is_ready", lambda _: False)


def _override_carry(monkeypatch: pytest.MonkeyPatch, carry: dict[str, Any],
                    subject: dict[str, Any] | None = None) -> None:
    """保存資産を変更せず、変異した宣言/対象を読取境界へ供給する。"""
    _legacy_carry_reader_fixture(monkeypatch)
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
    _legacy_carry_reader_fixture(monkeypatch)
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
        "authority_sha256": hashlib.sha256(
            (REPOSITORY_ROOT / authority["path"]).read_bytes()
        ).hexdigest(), "pr": event.number,
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
    base_bytes = {
        path: (checker._carry_git_bytes(REPOSITORY_ROOT, [
            "show", f"{checker._gate6_ready_values(REPOSITORY_ROOT)[0]}:{path}",
        ]) if path in {str(checker.STATE_TRANSITION_CONTRACT_PATH),
                       str(checker.GAME_END_CONTRACT_PATH)}
            else (REPOSITORY_ROOT / path).read_bytes())
        for path in paths
    }
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


# PR185の試験記録はsynthetic専用。正式root受理値へ転記しない。
def _t1_append_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Any, Any, dict[str, Any]]:
    """private readerと本物core_guardの判定を残し、I/Oだけ合成fixtureへ向ける。"""
    repository = REPOSITORY_ROOT
    root = tmp_path / 'synthetic-append-not-acceptance'
    paths = {
        str(checker.GATE6_CARRY_PATH),
        str(checker.GATE6_CARRY_SCHEMA_PATH),
        str(checker.GATE6_T1_APPEND_PATH),
        str(checker.GATE6_T1_APPEND_SCHEMA_PATH),
        str(checker.STATE_TRANSITION_CONTRACT_PATH),
        str(checker.GAME_END_CONTRACT_PATH),
        str(checker.SCHEMA_PATH),
        *checker._GATE6_RETAINED_PATHS,
        'scripts/check_human_review_signature.py',
        'tests/test_human_review_signature.py',
        'scripts/core_guard.py',
        'scripts/representative_selection.py',
        'scripts/check_branch_row_mapping.py',
        'scripts/check_input_axes_descriptor.py',
        'scripts/state_transition_freeze.py',
        'contracts/state-transition/input_axes_descriptor_v1.json',
        'docs/features/appendix-e-golden-vectors/matrix_rows_line_review.md',
        'docs/features/mvp-delegated-core-review/policy.json'
    }
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / path).read_bytes())
    guard = checker._carry_core_guard(repository)
    real_git = checker._carry_git_bytes
    head = real_git(repository, ['rev-parse', 'HEAD']).decode().strip()
    base = _load_object(repository / checker.GATE6_T1_APPEND_PATH)['authority']['baseRevision']
    url = 'https://github.com/masaki1025/pitchlog/pull/185#issuecomment-185'
    event = guard.PullRequestEvent(
        base,
        head,
        f'PO-DELEGATION-EVIDENCE: {url}',
        185,
        'masaki1025/pitchlog',
        'masaki1025/pitchlog',
        'feature/mvp-t1-input-closure'
    )

    def git_read(_: Path, arguments: list[str]) -> bytes:
        if arguments[0] == 'show' and arguments[1].startswith(head + ':'):
            return (root / arguments[1].split(':', 1)[1]).read_bytes()
        return real_git(repository, arguments)
    original_delegation_git = guard._delegation_git_bytes
    original_paths = guard.changed_paths
    def delegated_read(_: Path, args: list[str], label: str) -> bytes:
        if args == ['show', head + ':docs/features/mvp-delegated-core-review/policy.json']:
            path = root / 'docs/features/mvp-delegated-core-review/policy.json'
            return path.read_bytes()
        return original_delegation_git(repository, args, label)

    monkeypatch.setattr(guard, '_delegation_git_bytes', delegated_read)
    monkeypatch.setattr(
        guard,
        'changed_paths',
        lambda _,
        before,
        after: original_paths(repository, before, after)
    )
    monkeypatch.setattr(checker, '_carry_git_bytes', git_read)
    monkeypatch.setattr(checker, '_carry_core_guard', lambda _: guard)
    anchor = checker._Gate6AcceptedAnchorReader(root)
    subject = anchor.load_json(checker.STATE_TRANSITION_CONTRACT_PATH, '試験旧subject')
    # 合成appendの現descriptor参照だけは現fixtureの実射影へ束縛する。
    # 旧anchor本体/旧prefixを変えず、実recordを合成受理に流用しない。
    descriptor = _load_object(
        root / 'contracts/state-transition/input_axes_descriptor_v1.json'
    )
    descriptor_digest = descriptor_checker.compute_descriptor_digest(descriptor)
    assert descriptor['digest'] == descriptor_digest
    subject['inputAxesDescriptor']['digest'] = descriptor_digest
    source_row = subject['matrixRows'][-2]
    source_case = subject['cases'][-2]
    rows, cases, refs = ([], [], [])
    for index, case_id in enumerate(checker._GATE6_T1_CASE_IDS):
        row = copy.deepcopy(source_row)
        held = index in {0, 2, 4}
        stopped = index >= 2
        updates = {
            'event.perPitch.rbi.cause_by_runner.third.held_too_long': held,
            'event.perPitch.rbi.cause_by_runner.third.unnecessary_throw': not held,
            'event.perPitch.rbi.runnerContinuityByRunner': (
                'single-runner-stopped-and-restarted'
                if stopped else 'single-runner-kept-running'
            )
        }
        if stopped:
            axis = 'event.perPitch.rbi.restart_by_runner.third.after_observing_misplay'
            updates[axis] = index != 4
        args = row['precondition']['args']
        args[:] = [item for item in args if item['axisId'] not in updates]
        args.extend(({'op': 'eq', 'axisId': key, 'value': value} for key, value in updates.items()))
        row['statFlags']['打点'] = index in {0, 1, 4}
        coordinate = {key: row[key] for key in ('eventKind', 'resultId', 'precondition')}
        reference = {'layer': 'matrixRows', 'coordinate': coordinate}
        case = copy.deepcopy(source_case)
        case.update(caseId=case_id, inputId=f'synthetic-gate6-{index}', rowRef=reference)
        case['inputCoordinate'].update(updates)
        case['raw'] = copy.deepcopy(case['inputCoordinate'])
        case['normalized'] = copy.deepcopy(case['inputCoordinate'])
        case['expected'] = {
            key: value for key,
            value in row.items() if key not in {'eventKind', 'resultId', 'precondition', 'remarks'}
        }
        rows.append(row)
        cases.append(case)
        refs.append(reference)
    subject['matrixRows'].extend(rows)
    subject['cases'].extend(cases)
    subject['mustOperationCoverage']['mappings'][0]['rowRefs'].extend(refs)
    _write_t1_append_json(root / checker.STATE_TRANSITION_CONTRACT_PATH, subject)
    policy = _schema()['x-pitchlog-human-review-signature-policy']
    limit = policy['subjectDigest']['safeIntegerLimit']
    record: dict[
        str,
        Any
    ] = {
        'schemaVersion': 1,
        'evidenceKind': 't1-input-append',
        'status': 'candidate-for-delegated-verification',
        'authority': {
            'repository': 'masaki1025/pitchlog',
            'pr': 185,
            'branch': 'feature/mvp-t1-input-closure',
            'path': 'docs/features/mvp-delegated-core-review/policy.json',
            'sourcePolicySha256': checker._gate6_ready_values(REPOSITORY_ROOT)[2],
            'baseRevision': base
        },
        'anchor': {
            'commit': checker._gate6_ready_values(REPOSITORY_ROOT)[0],
            'carryRawSha256': checker._gate6_ready_values(REPOSITORY_ROOT)[1]
        },
        'changedCaseIds': list(checker._GATE6_T1_CASE_IDS),
        'subjects': [],
        'scopeReceipt': {
            'kind': 'bounded-technical-candidate',
            'evidenceLabel': 'synthetic test fixture; NOT root acceptance',
            'personalReviewClaimed': False,
            'P6FullAcceptance': False,
            'P7FullAcceptance': False,
            'T1BodyStartComplete': False
        }
    }
    for path, projection in (
        (checker.STATE_TRANSITION_CONTRACT_PATH, 'operation-undo-and-cases'),
        (checker.GAME_END_CONTRACT_PATH, 'decision-cases-and-validation-errors')
    ):
        old = anchor.load_json(path, '試験固定subject')
        current = _load_object(root / path)
        changes: list[dict[
            str,
            Any
        ]] = [{
            'kind': 'replace',
            'pointer': '/inputAxesDescriptor/digest',
            'before': old['inputAxesDescriptor']['digest'],
            'after': current['inputAxesDescriptor']['digest']
        }]
        if path == checker.STATE_TRANSITION_CONTRACT_PATH:
            for pointer, count, values in (
                ('/matrixRows', 44, rows),
                ('/cases', 111, cases),
                ('/mustOperationCoverage/mappings/0/rowRefs', 44, refs)
            ):
                changes.append({
                    'kind': 'append',
                    'pointer': pointer,
                    'beforeCount': count,
                    'values': values
                })
        record['subjects'].append({
            'path': str(path),
            'anchorRawSha256': hashlib.sha256(anchor.read_bytes(path)).hexdigest(),
            'anchorDigest': checker.compute_subject_digest(old, limit),
            'currentRawSha256': hashlib.sha256((root / path).read_bytes()).hexdigest(),
            'currentDigest': checker.compute_subject_digest(current, limit),
            'projection': projection,
            'projectionDigest': checker.compute_subject_digest(
                checker._carry_projection(old, projection),
                limit
            ),
            'allowedChanges': changes
        })
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)
    evidence = {
        'authority_sha256': hashlib.sha256(
            (root / record['authority']['path']).read_bytes()
        ).hexdigest(),
        'pr': 185,
        'base': base,
        'head': head,
        'diff_sha256': guard._delegation_diff(root, event),
        'paths': guard.changed_paths(root, base, head),
        'reviewer_agent': 'synthetic-independent-reviewer',
        'candidate_agents': ['synthetic-author'],
        'independent': True,
        'verdict': 'approved',
        'findings': [],
        'report': {
            'task': 'synthetic-independent-reviewer',
            'reviewed_head': head,
            'text': 'synthetic fixture, no actual acceptance or human signature'
        }
    }
    comment = {
        'id': 185,
        'html_url': url,
        'issue_url': 'https://api.github.com/repos/masaki1025/pitchlog/issues/185',
        'author_association': 'OWNER',
        'user': {'login': 'masaki1025'},
        'body': guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    }
    monkeypatch.setattr(guard, '_fetch_delegation_comment', lambda _: comment)
    monkeypatch.setattr(guard, 'load_pull_request_event', lambda: event)
    return (root, guard, event, comment)

def _write_t1_append_json(path: Path, value: object) -> None:
    """合成fixtureだけを書き、正式値へ反映しない。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def test_t1_append_pending_record_is_not_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """root未確定の合成recordは拒否する。実recordの永久pendingは要求しない。"""
    root, _, _, _ = _t1_append_fixture(tmp_path, monkeypatch)
    schema = _load_object(root / checker.GATE6_T1_APPEND_SCHEMA_PATH)
    pending = schema["oneOf"][0]["const"]
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, pending)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match="未確定"):
        checker._validate_gate6_t1_input_append(root)


def test_t1_append_synthetic_positive_uses_real_core_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧anchor/旧validator/全差分/非作者判定を通すが実受理とは呼ばない。"""
    root, _, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    assert 'DELEGATED VERIFIED' in checker.validate_gate6_ci_event(root, event)
    assert checker.main(['--root', str(root), '--gate6-carry', '--ci']) == 0

@pytest.mark.parametrize(
    'mutation',
    [
        'old-row',
        'operation',
        'unauthorized',
        'missing-case',
        'duplicate-case',
        'extra-case',
        'row-ref',
        'coverage-ref',
        'output',
        'unknown-pointer',
        'duplicate-pointer',
        'anchor',
        'anchor-hash',
        'raw-hash',
        'projection',
        'descriptor-after',
        'extra-field',
        'authority-hash',
        'old-carry',
        'old-record',
        'unknown-case-id'
    ]
)
def test_t1_append_rejects_bounded_delta_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str
) -> None:
    """現digestが追随しても許可外・固定集合・旧記録の改変を閉じる。"""
    root, _, _, _ = _t1_append_fixture(tmp_path, monkeypatch)
    record = _load_object(root / checker.GATE6_T1_APPEND_PATH)
    entry = next(
        x for x in record['subjects']
        if x['path'] == str(checker.STATE_TRANSITION_CONTRACT_PATH)
    )
    changes = {x['pointer']: x for x in entry['allowedChanges']}
    subject = _load_object(root / checker.STATE_TRANSITION_CONTRACT_PATH)
    if mutation == 'old-row':
        subject['matrixRows'][0]['statFlags']['打点'] = True
    elif mutation == 'operation':
        subject['operationRows'][0]['operationResult'] = 'unauthorized'
    elif mutation == 'unauthorized':
        subject['unauthorized'] = True
    elif mutation in {'missing-case', 'duplicate-case', 'extra-case'}:
        values = changes['/cases']['values']
        if mutation == 'missing-case':
            values.pop()
        elif mutation == 'duplicate-case':
            values[-1] = copy.deepcopy(values[0])
        else:
            values.append(copy.deepcopy(values[0]))
    elif mutation == 'row-ref':
        changes['/cases']['values'][0]['rowRef'] = copy.deepcopy(subject['cases'][0]['rowRef'])
    elif mutation == 'coverage-ref':
        values = changes['/mustOperationCoverage/mappings/0/rowRefs']['values']
        values[0] = copy.deepcopy(subject['cases'][0]['rowRef'])
    elif mutation == 'output':
        changes['/cases']['values'][0]['expected']['statFlags']['打点'] = False
    elif mutation == 'unknown-pointer':
        entry['allowedChanges'][0]['pointer'] = '/not-allowed'
    elif mutation == 'duplicate-pointer':
        entry['allowedChanges'][0] = copy.deepcopy(entry['allowedChanges'][1])
    elif mutation == 'anchor':
        record['anchor']['commit'] = '0' * 40
    elif mutation == 'anchor-hash':
        record['anchor']['carryRawSha256'] = '0' * 64
    elif mutation == 'raw-hash':
        entry['anchorRawSha256'] = '0' * 64
    elif mutation == 'projection':
        entry['projectionDigest'] = 'sha256:' + '0' * 64
    elif mutation == 'descriptor-after':
        entry['allowedChanges'][0]['after'] = 'sha256:' + '0' * 64
    elif mutation == 'extra-field':
        record['approved'] = True
    elif mutation == 'authority-hash':
        record['authority']['sourcePolicySha256'] = '0' * 64
    elif mutation == 'unknown-case-id':
        record['changedCaseIds'][-1] = 'ST-UNKNOWN'
    elif mutation == 'old-carry':
        (root / checker.GATE6_CARRY_PATH).write_text('{}', encoding='utf-8')
    else:
        (root / next(iter(checker._GATE6_RETAINED_PATHS))).write_text('{}', encoding='utf-8')
    _write_t1_append_json(root / checker.STATE_TRANSITION_CONTRACT_PATH, subject)
    raw = (root / checker.STATE_TRANSITION_CONTRACT_PATH).read_bytes()
    entry['currentRawSha256'] = hashlib.sha256(raw).hexdigest()
    policy = _schema()['x-pitchlog-human-review-signature-policy']
    limit = policy['subjectDigest']['safeIntegerLimit']
    entry['currentDigest'] = checker.compute_subject_digest(subject, limit)
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)
    with pytest.raises((
        checker.HumanReviewSignatureRecordError,
        descriptor_checker.DescriptorCheckError
    )):
        checker._validate_gate6_t1_input_append(root)

@pytest.mark.parametrize(
    'mutation',
    [
        'missing-event',
        'other-pr',
        'branch',
        'repository',
        'head',
        'base',
        'diff',
        'open-p1',
        'same-author',
        'missing-evidence',
        'approved-text',
        'head-blob',
        'executed-validator',
        'disabled-policy',
        'nonancestor',
        'old-policy-target',
        'missing-pr-target',
        'old-evidence-policy'
    ]
)
def test_t1_append_final_event_and_evidence_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str
) -> None:
    """少なくとも16種の最終event/委任/旧根拠の拒否を既判定へ通す。"""
    root, guard, event, comment = _t1_append_fixture(tmp_path, monkeypatch)
    evidence = json.loads(comment['body'].split('\n', 1)[1])
    if mutation == 'missing-event':
        event = None
    elif mutation == 'other-pr':
        event = guard.PullRequestEvent(**{**vars(event), 'number': 186})
    elif mutation == 'branch':
        event = guard.PullRequestEvent(**{**vars(event), 'head_branch': 'fix/other'})
    elif mutation == 'repository':
        event = guard.PullRequestEvent(**{**vars(event), 'head_repository': 'other/repo'})
    elif mutation == 'head':
        event = guard.PullRequestEvent(**{**vars(event), 'head_sha': '0' * 40})
    elif mutation == 'base':
        event = guard.PullRequestEvent(**{
            **vars(event),
            'base_sha': checker._gate6_ready_values(REPOSITORY_ROOT)[0]
        })
    elif mutation == 'diff':
        evidence['diff_sha256'] = '0' * 64
    elif mutation == 'open-p1':
        evidence['findings'] = [{'severity': 'P1', 'resolved': False, 'detail': 'synthetic open'}]
    elif mutation == 'same-author':
        evidence['candidate_agents'] = [evidence['reviewer_agent']]
    elif mutation == 'old-evidence-policy':
        evidence['authority_sha256'] = checker._gate6_ready_values(REPOSITORY_ROOT)[2]
    elif mutation == 'missing-evidence':

        def missing(_: str) -> Any:
            raise guard.GuardError('synthetic missing evidence')
        monkeypatch.setattr(guard, '_fetch_delegation_comment', missing)
    elif mutation == 'approved-text':
        event = guard.PullRequestEvent(**{**vars(event), 'body': 'approved'})
    elif mutation == 'head-blob':
        old = checker._carry_git_bytes

        def different(r: Path, args: list[str]) -> bytes:
            if args == ['show', f'{event.head_sha}:{checker.GATE6_T1_APPEND_PATH}']:
                return b'{}'
            return old(r, args)
        monkeypatch.setattr(checker, '_carry_git_bytes', different)
    elif mutation == 'executed-validator':
        (root / 'scripts/check_human_review_signature.py').write_text(
            '# different',
            encoding='utf-8'
        )
    elif mutation == 'nonancestor':
        old = checker._carry_git_bytes

        def no_ancestor(r: Path, args: list[str]) -> bytes:
            if args[0] == 'merge-base':
                raise checker.HumanReviewSignatureRecordError('synthetic nonancestor')
            return old(r, args)
        monkeypatch.setattr(checker, '_carry_git_bytes', no_ancestor)
    else:
        policy_path = root / 'docs/features/mvp-delegated-core-review/policy.json'
        policy = _load_object(policy_path)
        if mutation == 'disabled-policy':
            policy['enabled'] = False
        elif mutation == 'missing-pr-target':
            policy['targets'] = [item for item in policy['targets'] if item['pr'] != 185]
        else:
            policy['targets'][0]['branch'] = 'fix/changed-old-target'
        _write_t1_append_json(policy_path, policy)
    comment['body'] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_delegated_gate6_t1_input_append(root, event)

def _t1_append_later_event(
    root: Path,
    guard: Any,
    event: Any,
    monkeypatch: pytest.MonkeyPatch
) -> Any:
    """後続PRのbaseに今回記録が既存という合成Git境界を作る。"""
    # 導入前baseの同じcommitへ導入後blobを上書きする合成衝突を避ける。
    # 後続baseは新recordが存在する元headのsnapshotとして扱う。
    policy = _load_object(root / guard.DELEGATION_POLICY_PATH)
    later_number = _synthetic_later_number(policy)
    later = guard.PullRequestEvent(**{**vars(event), 'base_sha': event.head_sha,
                                    'number': later_number, 'head_branch': 'fix/later'})
    paths = [
        str(checker.GATE6_T1_APPEND_PATH),
        str(checker.GATE6_T1_APPEND_SCHEMA_PATH),
        str(checker.STATE_TRANSITION_CONTRACT_PATH),
        str(checker.GAME_END_CONTRACT_PATH)
    ]
    before = {p: (root / p).read_bytes() for p in paths}
    old = checker._carry_git_bytes

    def read(r: Path, args: list[str]) -> bytes:
        if args[0] == 'show' and args[1].startswith(later.base_sha + ':'):
            path = args[1].split(':', 1)[1]
            if path == 'contracts/state-transition':
                return ('\n'.join(Path(key).name for key in before) + '\n').encode()
            if path in before:
                return before[path]
        return old(r, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    return later

def test_t1_append_later_pr_is_unchanged_not_new_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """不変後続PRは新しいPR185受理や本人署名を表明しない。"""
    root, guard, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    later = _t1_append_later_event(root, guard, event, monkeypatch)

    def no_fetch(_: str) -> Any:
        raise AssertionError('後続継承で新受理証拠を取得しない')
    monkeypatch.setattr(guard, '_fetch_delegation_comment', no_fetch)
    assert 'no new PR185 acceptance' in checker.validate_gate6_ci_event(root, later)

@pytest.mark.parametrize('target', ['record', 'schema', 'subject'])
def test_t1_append_later_pr_rejects_coordinated_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str
) -> None:
    """後続PRはrecord/schema/subjectのbaseとの差を黙って採用しない。"""
    root, guard, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    later = _t1_append_later_event(root, guard, event, monkeypatch)
    path = {
        'record': checker.GATE6_T1_APPEND_PATH,
        'schema': checker.GATE6_T1_APPEND_SCHEMA_PATH,
        'subject': checker.GAME_END_CONTRACT_PATH
    }[target]
    if target == 'subject':
        (root / path).write_bytes((root / path).read_bytes() + b'\n')
        record = _load_object(root / checker.GATE6_T1_APPEND_PATH)
        entry = next((x for x in record['subjects'] if x['path'] == str(path)))
        entry['currentRawSha256'] = hashlib.sha256((root / path).read_bytes()).hexdigest()
        _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)
    else:
        value = _load_object(root / path)
        if target == 'record':
            value['scopeReceipt']['evidenceLabel'] += ' changed'
        else:
            value['title'] += ' changed'
        _write_t1_append_json(root / path, value)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='後続PR'):
        checker.validate_gate6_ci_event(root, later)

def test_t1_append_no_public_revision_switch() -> None:
    """固定private readerに任意commitを与える公開入口はない。"""
    with pytest.raises(TypeError):
        checker._Gate6AcceptedAnchorReader(REPOSITORY_ROOT, '0' * 40)
    with pytest.raises(SystemExit):
        checker.main(['--root', str(REPOSITORY_ROOT), '--revision', '0' * 40])


@pytest.mark.parametrize("mutation", ["extra-record", "personal-claim", "unknown-change"])
def test_t1_append_relaxed_candidate_schema_cannot_expand_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """新schemaも同時に緩めた場合でも閉じた記録/本人確認境界を保つ。"""
    root, _, _, _ = _t1_append_fixture(tmp_path, monkeypatch)
    record = _load_object(root / checker.GATE6_T1_APPEND_PATH)
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_SCHEMA_PATH, {})
    if mutation == "extra-record":
        record["approved"] = True
    elif mutation == "personal-claim":
        record["scopeReceipt"]["personalReviewClaimed"] = True
    else:
        record["subjects"][0]["allowedChanges"][0]["approved"] = True
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._validate_gate6_t1_input_append(root)


@pytest.mark.parametrize("mutation", ["missing-base", "schema-missing", "subject-missing"])
def test_t1_append_later_pr_never_invents_missing_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """後続PRで基準blobが欠けても現値へ代用しない。"""
    root, guard, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    later = _t1_append_later_event(root, guard, event, monkeypatch)
    path = {"missing-base": checker.GATE6_T1_APPEND_PATH,
            "schema-missing": checker.GATE6_T1_APPEND_SCHEMA_PATH,
            "subject-missing": checker.STATE_TRANSITION_CONTRACT_PATH}[mutation]
    old = checker._carry_git_bytes

    def missing(r: Path, args: list[str]) -> bytes:
        if args == ["show", f"{later.base_sha}:{path}"]:
            raise checker.HumanReviewSignatureRecordError("synthetic missing base")
        return old(r, args)

    monkeypatch.setattr(checker, "_carry_git_bytes", missing)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match="missing base"):
        checker.validate_gate6_ci_event(root, later)


def test_t1_append_anchor_reader_uses_snapshot_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現schemaの緩和をanchor内の旧record再検査へ混ぜない。"""
    root, _, _, _ = _t1_append_fixture(tmp_path, monkeypatch)
    expected = checker._Gate6AcceptedAnchorReader(root).load_json(
        checker.SCHEMA_PATH, "固定schema"
    )
    _write_t1_append_json(root / checker.SCHEMA_PATH, {})
    assert checker._Gate6AcceptedAnchorReader(root).load_json(
        checker.SCHEMA_PATH, "固定schema"
    ) == expected
    with pytest.raises(checker.HumanReviewSignatureRecordError, match="旧本人記録"):
        checker._validate_gate6_t1_input_append(root)


@pytest.mark.parametrize("stale", [False, True])
def test_t1_append_required_repository_test_reaches_final_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stale: bool,
) -> None:
    """必須repository testが新appendの実委任判定まで到達し、旧HEAD証拠で赤になる。"""
    root, guard, _, comment = _t1_append_fixture(tmp_path, monkeypatch)
    if stale:
        evidence = json.loads(comment["body"].split("\n", 1)[1])
        evidence["head"] = "0" * 40
        comment["body"] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    monkeypatch.setattr(sys.modules[__name__], "REPOSITORY_ROOT", root)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    if stale:
        with pytest.raises(AssertionError):
            test_repository_gate6_signature_records_match_current_contracts()
    else:
        test_repository_gate6_signature_records_match_current_contracts()


def test_t1_append_later_policy_target_append_keeps_record_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正当なpolicy対象追記だけならrecord根拠は固定して後続不変継承できる。"""
    root, guard, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    later = _t1_append_later_event(root, guard, event, monkeypatch)
    record_before = (root / checker.GATE6_T1_APPEND_PATH).read_bytes()
    policy_path = root / 'docs/features/mvp-delegated-core-review/policy.json'
    policy = _load_object(policy_path)
    policy['targets'].append({'pr': later.number, 'branch': later.head_branch})
    _write_t1_append_json(policy_path, policy)
    assert 'no new PR185 acceptance' in checker.validate_gate6_ci_event(root, later)
    assert (root / checker.GATE6_T1_APPEND_PATH).read_bytes() == record_before


@pytest.mark.parametrize("mutation", [
    "anchor-is-base", "joint-base", "duplicate-ready", "reverse-parents",
    "third-parent", "missing-parent", "carry", "carry-schema", "signature",
    "policy", "old-subject", "unknown-git",
])
def test_event_baseline_rejects_joint_changes_and_old_material_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """実baseの親/旧原本を根にし、自己整合した申告だけでは旧基線を選ばせない。"""
    root, _, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    record_path = root / checker.GATE6_T1_APPEND_PATH
    record = _load_object(record_path)
    schema_path = root / checker.GATE6_T1_APPEND_SCHEMA_PATH
    schema = _load_object(schema_path)
    ready = next(x for x in schema['oneOf'] if 'properties' in x)
    if mutation == 'anchor-is-base':
        record['anchor']['commit'] = event.base_sha
        ready['properties']['anchor']['properties']['commit']['const'] = event.base_sha
    elif mutation == 'joint-base':
        record['authority']['baseRevision'] = event.head_sha
        ready['properties']['authority']['properties']['baseRevision'] = {'const': event.head_sha}
    elif mutation == 'duplicate-ready':
        schema['oneOf'].append(copy.deepcopy(ready))
    _write_t1_append_json(record_path, record)
    _write_t1_append_json(schema_path, schema)
    old = checker._carry_git_bytes
    anchor = checker._gate6_ready_values(REPOSITORY_ROOT)[0]
    paths = {
        'carry': str(checker.GATE6_CARRY_PATH),
        'carry-schema': str(checker.GATE6_CARRY_SCHEMA_PATH),
        'signature': 'docs/features/adr003-stage2-runtime/signatures/gate6-game-end.json',
        'policy': 'docs/features/mvp-delegated-core-review/policy.json',
        'old-subject': str(checker.STATE_TRANSITION_CONTRACT_PATH),
    }

    def changed(r: Path, arguments: list[str]) -> bytes:
        if arguments == ['rev-parse', event.base_sha + '^@']:
            parents = old(r, arguments).decode().split()
            if mutation == 'reverse-parents':
                return ('\n'.join(reversed(parents)) + '\n').encode()
            if mutation == 'third-parent':
                return ('\n'.join(parents + [event.head_sha]) + '\n').encode()
            if mutation == 'missing-parent':
                return (parents[0] + '\n').encode()
        if mutation in paths and arguments == ['show', anchor + ':' + paths[mutation]]:
            return old(r, arguments) + b'\n'
        if mutation == 'unknown-git' and arguments[0] == 'show':
            raise checker.HumanReviewSignatureRecordError('Git原本を読めない')
        return old(r, arguments)

    monkeypatch.setattr(checker, '_carry_git_bytes', changed)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_delegated_gate6_t1_input_append(root, event)


def test_final_base_mismatch_is_rejected_before_old_git_material_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """record/schemaでbaseを同時変更しても、actualevent照合より先に読まない。"""
    root, _, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    record = _load_object(root / checker.GATE6_T1_APPEND_PATH)
    record['authority']['baseRevision'] = event.head_sha
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)

    def unexpected(*_: object) -> Any:
        raise AssertionError('不一致recordから旧原本を選択しない')
    monkeypatch.setattr(checker, '_gate6_git_object', unexpected)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='最終PR base'):
        checker.validate_delegated_gate6_t1_input_append(root, event)


def test_later_joint_record_schema_change_is_rejected_before_baseline_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """後続は実baseの新4assetを先に固定し、headの自己申告を使わない。"""
    root, guard, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    later = _t1_append_later_event(root, guard, event, monkeypatch)
    record = _load_object(root / checker.GATE6_T1_APPEND_PATH)
    record['authority']['baseRevision'] = later.head_sha
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)
    schema = _load_object(root / checker.GATE6_T1_APPEND_SCHEMA_PATH)
    schema['title'] += ' coordinated modification'
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_SCHEMA_PATH, schema)

    def unexpected(*_: object, **__: object) -> Any:
        raise AssertionError('後続の改変recordを基準にしない')
    monkeypatch.setattr(checker, '_gate6_baseline', unexpected)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='後続PR'):
        checker.validate_other_pr_gate6_t1_append_unchanged(root, later)


@pytest.mark.parametrize("layout", [
    "head", "merge", "reverse", "third-parent", "missing-parent", "other-base",
    "different-tree", "not-ancestor", "invalid-checkout", "unknown-git",
])
def test_checkout_accepts_only_exact_head_or_identical_tree_two_parent_merge(
    monkeypatch: pytest.MonkeyPatch, layout: str,
) -> None:
    """環境の信用宣言を使わず、親順/祖先/treeの全条件を閉じる。"""
    from types import SimpleNamespace

    base, head, merge, tree = ('a' * 40, 'b' * 40, 'c' * 40, 'd' * 40)
    event = SimpleNamespace(base_sha=base, head_sha=head)

    def git(_: Path, args: list[str]) -> bytes:
        if layout == 'unknown-git':
            raise checker.HumanReviewSignatureRecordError('Git故障')
        if args == ['rev-parse', 'HEAD']:
            return ((head if layout == 'head' else 'unknown' if layout == 'invalid-checkout'
                     else merge) + '\n').encode()
        if args == ['rev-parse', merge + '^@']:
            parents = [base, head]
            if layout == 'reverse':
                parents.reverse()
            elif layout == 'third-parent':
                parents.append(tree)
            elif layout == 'missing-parent':
                parents.pop()
            elif layout == 'other-base':
                parents[0] = tree
            return ('\n'.join(parents) + '\n').encode()
        if args == ['merge-base', '--is-ancestor', base, head]:
            if layout == 'not-ancestor':
                raise checker.HumanReviewSignatureRecordError('祖先でない')
            return b''
        if args == ['rev-parse', merge + '^{tree}']:
            return ((base if layout == 'different-tree' else tree) + '\n').encode()
        if args == ['rev-parse', head + '^{tree}']:
            return (tree + '\n').encode()
        raise AssertionError(args)

    monkeypatch.setattr(checker, '_carry_git_bytes', git)
    if layout in {'head', 'merge'}:
        checker._validate_gate6_checkout(REPOSITORY_ROOT, event)
    else:
        with pytest.raises(checker.HumanReviewSignatureRecordError):
            checker._validate_gate6_checkout(REPOSITORY_ROOT, event)


def test_pr183_acceptance_does_not_read_later_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新appendのない旧受理は旧carry/policy/最終証拠だけで検査できる。"""
    _, event, _ = _final_carry_fixture(monkeypatch)
    original = checker.descriptor_checker.load_json

    def read(path: Path, label: str) -> object:
        if path in {REPOSITORY_ROOT / checker.GATE6_T1_APPEND_PATH,
                    REPOSITORY_ROOT / checker.GATE6_T1_APPEND_SCHEMA_PATH}:
            raise AssertionError('旧PR183は新appendへ依存しない')
        return original(path, label)
    monkeypatch.setattr(checker.descriptor_checker, 'load_json', read)
    assert 'VERIFIED' in checker.validate_gate6_ci_event(REPOSITORY_ROOT, event)


def test_legacy_prefix_accepts_minified_current_semantics_without_new_hash(
) -> None:
    """現raw書式を制約せず旧原文の唯一SHA一致prefixだけを復元する。"""
    carry = _carry()
    policy = _load_object(REPOSITORY_ROOT / carry['authority']['path'])
    current = json.loads(json.dumps(policy, separators=(',', ':')))
    accepted = checker._gate6_legacy_policy_prefix(carry['authority'], current)
    raw = (json.dumps(accepted, ensure_ascii=False, indent=2) + '\n').encode()
    assert hashlib.sha256(raw).hexdigest() == carry['authority']['sha256']
    assert policy['targets'][:len(accepted['targets'])] == accepted['targets']


@pytest.mark.parametrize('change', ['no-match', 'non-target', 'old-target'])
def test_legacy_prefix_rejects_changed_old_materials(change: str) -> None:
    """旧hashを復元できない改変や任意hashを新受理しない。"""
    carry = _carry()
    policy = _load_object(REPOSITORY_ROOT / carry['authority']['path'])
    authority = copy.deepcopy(carry['authority'])
    if change == 'no-match':
        authority['sha256'] = '0' * 64
    elif change == 'non-target':
        policy['publisher'] += '-changed'
    else:
        policy['targets'][0]['branch'] += '-changed'
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._gate6_legacy_policy_prefix(authority, policy)


def test_local_technical_context_cannot_replace_final_actual_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """local成功後も最終はactualeventから基準を作り直す。"""
    root, _, event, _ = _t1_append_fixture(tmp_path, monkeypatch)
    checker.validate_gate6_subject_carry(root)
    record = _load_object(root / checker.GATE6_T1_APPEND_PATH)
    record['authority']['baseRevision'] = event.head_sha
    _write_t1_append_json(root / checker.GATE6_T1_APPEND_PATH, record)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='最終PR base'):
        checker.validate_delegated_gate6_t1_input_append(root, event)


def test_legacy_prefix_requires_a_unique_matching_raw_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じhashを返す故障観測も一意でなければ拒否する。"""
    from types import SimpleNamespace

    carry = _carry()
    policy = _load_object(REPOSITORY_ROOT / carry['authority']['path'])
    assert len(policy['targets']) > 1
    fake_hash = SimpleNamespace(hexdigest=lambda: carry['authority']['sha256'])
    monkeypatch.setattr(checker, 'hashlib', SimpleNamespace(sha256=lambda _: fake_hash))
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._gate6_legacy_policy_prefix(carry['authority'], policy)


def _ordinary_test_materials(repository: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """正式9資産からPR187限定record/schemaの試験入力を構成する。"""
    names = (
        'state_transition_contract_v1.json', 'required_set_input_coverage_v1.json',
        'branch_row_mapping_v1.json', 'game_end_coverage_declaration_v1.json',
        'appendix_e_consumer_handoff_v1.json', 'ordinary_pitch_request_schema_v1.json',
        'ordinary_pitch_response_schema_v1.json', 'ordinary_pitch_vectors_v1.json',
        'ordinary_pitch_v1.d.ts',
    )
    record = {
        'schemaVersion': 1, 'evidenceKind': 't1-ordinary-pitch-33',
        'status': 'candidate-for-delegated-verification',
        'authority': {'repository': 'masaki1025/pitchlog', 'pr': 187,
                      'branch': 'feature/mvp-t1-ordinary-pitches',
                      'baseRevision': checker._ORDINARY_PUBLIC_BASE},
        'anchor': checker._ORDINARY_ANCHOR,
        'assets': {f'contracts/state-transition/{name}': hashlib.sha256(
            (repository / 'contracts/state-transition' / name).read_bytes(),
        ).hexdigest() for name in names},
        'scopeReceipt': {'personalReviewClaimed': False, 'P6FullAcceptance': False,
                         'P7FullAcceptance': False, 'T1BodyStartComplete': False},
    }

    def closed(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {'type': 'object', 'additionalProperties': False,
                    'required': list(value),
                    'properties': {key: closed(item) for key, item in value.items()}}
        return {'type': 'boolean' if type(value) is bool else 'integer'
                if type(value) is int else 'string', 'const': value}

    return record, {'$schema': 'https://json-schema.org/draft/2020-12/schema', **closed(record)}


@pytest.fixture
def ordinary_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """実原本＋合成最終blob/公開コメントを使う。実公開受理とは区別する。"""
    repository = Path(__file__).resolve().parents[1]
    root = tmp_path / 'ordinary'
    root.mkdir()
    record, schema = _ordinary_test_materials(repository)
    paths = {
        *record['assets'], *checker._ORDINARY_FIXED_INPUTS,
        *checker._ORDINARY_EXECUTION_INPUTS,
        'scripts/check_human_review_signature.py', 'tests/test_human_review_signature.py',
        'docs/features/mvp-delegated-core-review/policy.json',
    }
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / path).read_bytes())
    # coverage consumerの固定Git読取だけを既objectsへ向ける。index/refは変更しない。
    gitdir = checker._carry_git_bytes(
        repository, ['rev-parse', '--absolute-git-dir'],
    ).decode().strip()
    (root / '.git').write_text('gitdir: ' + gitdir + '\n')
    _write_t1_append_json(root / checker.GATE6_ORDINARY_PATH, record)
    _write_t1_append_json(root / checker.GATE6_ORDINARY_SCHEMA_PATH, schema)
    policy_path = root / 'docs/features/mvp-delegated-core-review/policy.json'
    policy = json.loads(policy_path.read_bytes())
    if {'pr': 187, 'branch': checker._ORDINARY_BRANCH} not in policy['targets']:
        policy['targets'].append({'pr': 187, 'branch': checker._ORDINARY_BRANCH})
    _write_t1_append_json(policy_path, policy)
    real_git = checker._carry_git_bytes
    head = real_git(repository, ['rev-parse', 'HEAD']).decode().strip()
    guard = checker._carry_core_guard(repository)
    old_delegation_git = guard._delegation_git_bytes
    base = 'b' * 40
    baseline = {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob('*') if path.is_file() and path.name != '.git'}
    calls = []

    def read(_: Path, args: list[str]) -> bytes:
        calls.append(args)
        if args[0] == 'show' and args[1].startswith(head + ':'):
            return (root / args[1].split(':', 1)[1]).read_bytes()
        if args[0] == 'show' and args[1].startswith(base + ':'):
            path = args[1].split(':', 1)[1]
            if path == 'contracts/state-transition':
                return ('\n'.join(Path(key).name for key in baseline
                                  if key.startswith(path + '/')) + '\n').encode()
            if path not in baseline:
                raise checker.HumanReviewSignatureRecordError('試験base blob欠損')
            return baseline[path]
        return real_git(repository, args)

    def delegation_read(_: Path, args: list[str], label: str) -> bytes:
        if args == ['show', head + ':docs/features/mvp-delegated-core-review/policy.json']:
            return policy_path.read_bytes()
        return old_delegation_git(repository, args, label)

    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    monkeypatch.setattr(guard, '_delegation_git_bytes', delegation_read)
    monkeypatch.setattr(checker, '_carry_core_guard', lambda _: guard)
    url = 'https://github.com/masaki1025/pitchlog/pull/187#issuecomment-187'
    event = guard.PullRequestEvent(checker._ORDINARY_PUBLIC_BASE, head,
        'PO-DELEGATION-EVIDENCE: ' + url, 187, 'masaki1025/pitchlog',
        'masaki1025/pitchlog', checker._ORDINARY_BRANCH)
    evidence = {
        'authority_sha256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'pr': 187, 'base': event.base_sha, 'head': head,
        'diff_sha256': guard._delegation_diff(repository, event),
        'paths': guard.changed_paths(repository, event.base_sha, head),
        'reviewer_agent': 'ordinary-nonauthor',
        'candidate_agents': ['t2_first_pitch_plan_review', 'root'],
        'independent': True, 'verdict': 'approved', 'findings': [],
        'report': {'task': 'ordinary-nonauthor', 'reviewed_head': head,
                   'text': '合成試験資料。実PRの公開受理ではない。'},
    }
    comment = {'id': 187, 'html_url': url,
               'issue_url': 'https://api.github.com/repos/masaki1025/pitchlog/issues/187',
               'author_association': 'OWNER', 'user': {'login': 'masaki1025'},
               'body': guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)}
    fetches = []

    def fetch(comment_id: str) -> dict[str, Any]:
        fetches.append(comment_id)
        return comment

    monkeypatch.setattr(guard, '_fetch_delegation_comment', fetch)
    return root, guard, event, base, baseline, calls, comment, fetches


def test_ordinary_local_technical_and_actual_pr_modes(ordinary_fixture: Any,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    """localはfetch0、新受理だけが既実証拠validatorを呼ぶ。"""
    root, _, event, _, _, _, _, fetches = ordinary_fixture
    assert checker.main(['--root', str(root), '--gate6-carry']) == 0
    output = capsys.readouterr().out
    assert 'TECHNICAL ONLY; final delegation NOT CHECKED; no new ordinary acceptance' in output
    assert fetches == []
    assert 'DELEGATED VERIFIED' in checker.validate_gate6_ci_event(root, event)
    assert fetches == ['187']


def test_ordinary_inherits_base_first_without_fetch(ordinary_fixture: Any) -> None:
    """正常統合後の全byte不変継承はbase先読・新受理なし・fetch0。"""
    root, guard, event, base, _, calls, _, fetches = ordinary_fixture
    later = _ordinary_later_event(root, guard, event, base)
    result = checker.validate_gate6_ci_event(root, later)
    assert 'UNCHANGED FROM PR BASE; no new ordinary acceptance' in result
    record_read = ['show', f'{base}:{checker.GATE6_ORDINARY_PATH}']
    assert record_read in calls
    assert fetches == []


@pytest.mark.parametrize('target', [
    'record', 'schema', 'subject', 'request', 'response', 'vectors', 'typescript',
    'coverage', 'mapping', 'game-coverage', 'handoff', 'old-record', 'descriptor',
    'old-signature', 'old-policy', 'placeholder', 'linked', 'delete-record', 'delete-schema',
])
def test_ordinary_rejects_mutated_or_missing_fixed_values(ordinary_fixture: Any,
                                                        target: str) -> None:
    """全固定資産・旧原本・連動改変/欠損はlocalも継承も拒否する。"""
    root, guard, event, base, _, _, _, fetches = ordinary_fixture
    path = {
        'record': checker.GATE6_ORDINARY_PATH,
        'schema': checker.GATE6_ORDINARY_SCHEMA_PATH,
        'subject': checker.STATE_TRANSITION_CONTRACT_PATH,
        'request': 'contracts/state-transition/ordinary_pitch_request_schema_v1.json',
        'response': 'contracts/state-transition/ordinary_pitch_response_schema_v1.json',
        'vectors': 'contracts/state-transition/ordinary_pitch_vectors_v1.json',
        'typescript': 'contracts/state-transition/ordinary_pitch_v1.d.ts',
        'coverage': 'contracts/state-transition/required_set_input_coverage_v1.json',
        'mapping': 'contracts/state-transition/branch_row_mapping_v1.json',
        'game-coverage': 'contracts/state-transition/game_end_coverage_declaration_v1.json',
        'handoff': 'contracts/state-transition/appendix_e_consumer_handoff_v1.json',
        'old-record': checker.GATE6_T1_APPEND_PATH,
        'descriptor': 'contracts/state-transition/input_axes_descriptor_v1.json',
        'old-signature': ('docs/features/adr003-stage2-runtime/signatures/'
                          'gate6-state-transition.json'),
        'old-policy': 'docs/features/mvp-delegated-core-review/policy.json',
    }.get(target, checker.GATE6_ORDINARY_PATH)
    file = root / path
    if target.startswith('delete-'):
        (root / (checker.GATE6_ORDINARY_PATH if target == 'delete-record'
                 else checker.GATE6_ORDINARY_SCHEMA_PATH)).unlink()
    elif target == 'linked':
        subject = root / checker.STATE_TRANSITION_CONTRACT_PATH
        subject.write_bytes(subject.read_bytes() + b' ')
        record = json.loads(file.read_bytes())
        record['assets'][str(checker.STATE_TRANSITION_CONTRACT_PATH)] = hashlib.sha256(
            subject.read_bytes(),
        ).hexdigest()
        _write_t1_append_json(file, record)
    elif target == 'old-policy':
        value = json.loads(file.read_bytes())
        value['quotes'][0] += '改変'
        _write_t1_append_json(file, value)
    elif target == 'placeholder':
        record = json.loads(file.read_bytes())
        record['authority']['pr'] = None
        _write_t1_append_json(file, record)
    else:
        file.write_bytes(file.read_bytes() + b' ')
    assert checker.main(['--root', str(root), '--gate6-carry']) == 1
    later = _ordinary_later_event(root, guard, event, base)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, later)
    assert fetches == []


@pytest.mark.parametrize('mutation', ['head', 'self-review', 'major', 'url', 'publisher', 'api'])
def test_ordinary_public_invalid_evidence_never_falls_back(ordinary_fixture: Any,
                                                          monkeypatch: pytest.MonkeyPatch,
                                                          mutation: str) -> None:
    """無効な公開証拠/取得故障はC/local成功へfallbackしない。"""
    root, guard, event, _, _, _, comment, _ = ordinary_fixture
    evidence = json.loads(comment['body'][len(guard.DELEGATION_COMMENT_MARKER):])
    if mutation == 'head':
        evidence['head'] = '0' * 40
    elif mutation == 'self-review':
        evidence['candidate_agents'].append(evidence['reviewer_agent'])
    elif mutation == 'major':
        evidence['findings'] = [{'severity': 'P1', 'resolved': False, 'detail': '未解消'}]
    elif mutation == 'url':
        comment['html_url'] = comment['html_url'].replace('/187#', '/186#')
    elif mutation == 'publisher':
        comment['user']['login'] = 'other'
    else:
        def failed(_: str) -> Any:
            raise guard.GuardError('試験API取得失敗')
        monkeypatch.setattr(guard, '_fetch_delegation_comment', failed)
    comment['body'] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)


@pytest.mark.parametrize('mutation', ['record', 'schema', 'missing', 'false-head'])
def test_ordinary_rejects_corrupt_base_before_current(ordinary_fixture: Any,
                                                    mutation: str) -> None:
    """base記録/schema不正・欠損・自己申告ではcurrentへ比較元を移さない。"""
    root, guard, event, base, baseline, _, _, fetches = ordinary_fixture
    path = str(checker.GATE6_ORDINARY_SCHEMA_PATH if mutation == 'schema'
               else checker.GATE6_ORDINARY_PATH)
    if mutation == 'missing':
        del baseline[path]
    elif mutation == 'false-head':
        value = json.loads(baseline[path])
        value['authority']['baseRevision'] = event.head_sha
        baseline[path] = json.dumps(value).encode()
    else:
        baseline[path] += b' '
    later = _ordinary_later_event(root, guard, event, base)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, later)
    assert fetches == []


@pytest.fixture(autouse=True)
def historical_gate6_technical_inputs(request: pytest.FixtureRequest,
                                     tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """旧local/CI欠落対向だけは受理済み185の全値を固定し、現33と分ける。"""
    if request.node.originalname not in {
        'test_required_repository_test_calls_ci_validation',
        'test_other_pr_cannot_follow_changed_case_with_changed_carry',
        'test_other_pr_inherits_only_unchanged_base_without_new_acceptance',
        'test_other_pr_requires_base_carry_schema_and_subject',
        'test_other_pr_rejects_changed_schema',
        'test_other_pr_rejects_foreign_head_repository',
        'test_other_pr_dispatch_cannot_be_retargeted_by_carry',
        'test_subject_carry_is_technical_only_without_final_event',
        'test_required_ci_route_rejects_missing_event',
    }:
        return
    repository = Path(__file__).resolve().parents[1]
    root = tmp_path / 'accepted-185'
    paths = {*checker._ORDINARY_FIXED_INPUTS, str(checker.STATE_TRANSITION_CONTRACT_PATH),
             'scripts/core_guard.py', 'scripts/check_human_review_signature.py',
             'tests/test_human_review_signature.py',
             'docs/features/mvp-delegated-core-review/policy.json'}
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if (path.endswith('policy.json') or path.startswith('scripts/')
                or path == 'tests/test_human_review_signature.py'):
            target.write_bytes((repository / path).read_bytes())
        else:
            target.write_bytes(checker._carry_git_bytes(repository, [
                'show', f'{checker._ORDINARY_ANCHOR}:{path}',
            ]))
    gitdir = checker._carry_git_bytes(
        repository, ['rev-parse', '--absolute-git-dir'],
    ).decode().strip()
    (root / '.git').write_text('gitdir: ' + gitdir + '\n')
    monkeypatch.setattr(sys.modules[__name__], 'REPOSITORY_ROOT', root)
    # 旧testのpath比較/relative_toも同じ歴史rootへ束縛する。実現行資産は変更しない。
    monkeypatch.setattr(sys.modules[__name__], 'CONTRACT_PATH',
        root / checker.STATE_TRANSITION_CONTRACT_PATH)
    monkeypatch.setattr(sys.modules[__name__], 'GAME_END_CONTRACT_PATH',
        root / checker.GAME_END_CONTRACT_PATH)


def _synthetic_later_number(policy: dict[str, Any]) -> int:
    """正式targetと既導入const全体から未使用の合成番号を選ぶ。"""
    reserved = {checker._GATE6_INTRODUCTION_PR, checker._GATE6_T1_APPEND_PR,
                checker._ORDINARY_PR}
    return max(reserved | {target['pr'] for target in policy['targets']}) + 1


def _ordinary_later_event(root: Path, guard: Any, event: Any, base: str) -> Any:
    """同じ合成eventへ後続番号とbranchを束縛する。"""
    policy = json.loads((root / guard.DELEGATION_POLICY_PATH).read_bytes())
    return guard.PullRequestEvent(base, event.head_sha, '', _synthetic_later_number(policy),
        event.repository, event.head_repository, 'feature/later-unrelated')


def test_ordinary_inheritance_allows_only_policy_target_suffix(ordinary_fixture: Any) -> None:
    """Cは合法target末尾追記を許すが、今回A/Bの新受理へ流さない。"""
    root, guard, event, base, _, _, _, fetches = ordinary_fixture
    later = _ordinary_later_event(root, guard, event, base)
    path = root / guard.DELEGATION_POLICY_PATH
    policy = json.loads(path.read_bytes())
    policy['targets'].append({'pr': later.number, 'branch': later.head_branch})
    _write_t1_append_json(path, policy)
    assert 'no new ordinary acceptance' in checker.validate_gate6_ci_event(root, later)
    assert fetches == []
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)


@pytest.mark.parametrize('mutation', [
    'guard-third-strike', 'guard-fourth-ball', 'guard-bool', 'guard-order',
    'fifth-row', 'flag', 'expected', 'history', 'duplicate-case', 'extra-case',
    'tail', 'missing-history', 'extra-abi-field',
])
def test_ordinary_rejects_semantic_delta_expansion(ordinary_fixture: Any,
                                                mutation: str) -> None:
    """4guard/12移行/1case/必須stack/全tailの採用全値から逸脱させない。"""
    root, _, _, _, _, _, _, fetches = ordinary_fixture
    path = root / checker.STATE_TRANSITION_CONTRACT_PATH
    value = json.loads(path.read_bytes())
    result_id = ('batting-result.ball' if mutation == 'guard-fourth-ball'
                 else 'batting-result.called-pitch')
    row = next(row for row in value['matrixRows'] if row['resultId'] == result_id)
    if mutation.startswith('guard-'):
        axis = 'state.count.balls' if mutation == 'guard-fourth-ball' else 'state.count.strikes'
        leaf = next(leaf for leaf in row['precondition']['args'] if leaf['axisId'] == axis)
        if mutation == 'guard-order':
            leaf['values'].reverse()
        else:
            leaf['values'].append(True if mutation == 'guard-bool' else
                                  2 if mutation == 'guard-third-strike' else 3)
    elif mutation == 'fifth-row':
        value['matrixRows'][10]['remarks'] = '未採用変更'
    elif mutation == 'flag':
        flag = next(iter(row['statFlags']))
        row['statFlags'][flag] = not row['statFlags'][flag]
    elif mutation == 'expected':
        value['cases'][0]['expected'] = {}
    elif mutation == 'history':
        value['cases'][0]['historyInput'] = []
    elif mutation in {'duplicate-case', 'extra-case'}:
        value['cases'].append(copy.deepcopy(value['cases'][-1]))
        if mutation == 'extra-case':
            value['cases'][-1]['caseId'] = 'UNACCEPTED'
    elif mutation == 'tail':
        path = root / 'contracts/state-transition/ordinary_pitch_vectors_v1.json'
        value = json.loads(path.read_bytes())
        value['historyTailCases'] = []
    else:
        path = root / 'contracts/state-transition/ordinary_pitch_request_schema_v1.json'
        value = json.loads(path.read_bytes())
        if mutation == 'missing-history':
            for branch in value['oneOf']:
                branch['required'].remove('history')
                del branch['properties']['history']
        else:
            value['oneOf'][0]['properties']['unaccepted-field'] = {'type': 'string'}
    _write_t1_append_json(path, value)
    assert checker.main(['--root', str(root), '--gate6-carry']) == 1
    assert fetches == []


@pytest.mark.parametrize('mutation', ['branch', 'fork', 'base', 'head', 'other-pr', 'dirty'])
def test_ordinary_event_and_executed_blob_mismatch(ordinary_fixture: Any,
                                                 mutation: str) -> None:
    """番号/branch/repo/版/実行blobが違う対象を今回新受理へ流さない。"""
    root, guard, event, _, _, _, _, fetches = ordinary_fixture
    fields = vars(event).copy()
    if mutation == 'branch':
        fields['head_branch'] = 'feature/unaccepted'
    elif mutation == 'fork':
        fields['head_repository'] = 'other/pitchlog'
    elif mutation == 'base':
        fields['base_sha'] = '0' * 40
    elif mutation == 'head':
        fields['head_sha'] = '0' * 40
    elif mutation == 'other-pr':
        fields['number'] = _synthetic_later_number(
            json.loads((root / guard.DELEGATION_POLICY_PATH).read_bytes()))
    else:
        (root / 'scripts/check_human_review_signature.py').write_text('# dirty\n')
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, guard.PullRequestEvent(**fields))
    assert fetches == []


@pytest.mark.parametrize('different_tree', [False, True])
def test_ordinary_exact_ci_merge_tree_binding(ordinary_fixture: Any,
                                             monkeypatch: pytest.MonkeyPatch,
                                             different_tree: bool) -> None:
    """最終headと同tree/正確2親のCI mergeだけを検査入力として許す。"""
    root, _, event, _, _, _, _, fetches = ordinary_fixture
    record = checker._ordinary_record(root)
    merge = 'c' * 40
    old = checker._carry_git_bytes

    def read(r: Path, args: list[str]) -> bytes:
        if args == ['rev-parse', 'HEAD']:
            return (merge + '\n').encode()
        if args == ['rev-parse', merge + '^@']:
            return (event.base_sha + '\n' + event.head_sha + '\n').encode()
        if args == ['rev-parse', merge + '^{tree}']:
            if different_tree:
                return ('0' * 40 + '\n').encode()
            return old(r, ['rev-parse', event.head_sha + '^{tree}'])
        return old(r, args)

    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    if different_tree:
        with pytest.raises(checker.HumanReviewSignatureRecordError):
            checker._ordinary_head(root, event, record)
    else:
        checker._ordinary_head(root, event, record)
    assert fetches == []


def test_ordinary_public_cli_reaches_existing_delegation(ordinary_fixture: Any,
                                                        monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    """公開CLIの--ciがlocalで済まさず、既非作者証拠検査まで実行する。"""
    root, guard, event, _, _, _, _, fetches = ordinary_fixture
    monkeypatch.setattr(guard, 'load_pull_request_event', lambda: event)
    assert checker.main(['--root', str(root), '--gate6-carry', '--ci']) == 0
    assert 'DELEGATED VERIFIED' in capsys.readouterr().out
    assert fetches == ['187']
def _policy_extension_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """実factoryの固定基線と現reader/HEAD照合を合成入力へ接ぐ。"""
    from types import SimpleNamespace

    guard = checker._carry_core_guard(REPOSITORY_ROOT)
    authority = copy.deepcopy(_carry()["authority"])
    baseline = checker._gate6_baseline(REPOSITORY_ROOT)
    anchor = baseline.anchor
    head = checker._carry_git_bytes(REPOSITORY_ROOT, ["rev-parse", "HEAD"]).decode().strip()
    accepted_bytes = baseline.materials[authority["path"]]
    accepted = json.loads(accepted_bytes)
    current = copy.deepcopy(accepted)
    current["targets"].append({"pr": 184, "branch": "feature/fixture-policy-extension"})
    policy_path = tmp_path / authority["path"]
    policy_path.parent.mkdir(parents=True)
    paths = {
        str(checker.GATE6_CARRY_PATH), str(checker.GATE6_CARRY_SCHEMA_PATH),
        str(checker.STATE_TRANSITION_CONTRACT_PATH), str(checker.GAME_END_CONTRACT_PATH),
        "scripts/check_human_review_signature.py", "tests/test_human_review_signature.py",
        "docs/features/appendix-e-golden-vectors/matrix_rows_line_review.md",
        *checker._GATE6_RETAINED_PATHS,
    }
    current_materials = {path: (REPOSITORY_ROOT / path).read_bytes() for path in paths}
    for path, raw in current_materials.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    blobs = {anchor: accepted_bytes}
    original_git = checker._carry_git_bytes

    def read_git(_: Path, arguments: list[str]) -> bytes:
        if arguments == ["show", f"{anchor}:{authority['path']}"]:
            if anchor not in blobs:
                raise checker.HumanReviewSignatureRecordError("固定anchorのpolicyがない")
            return blobs[anchor]
        if arguments[0] == "show" and arguments[1].startswith(head + ":"):
            path = arguments[1].split(":", 1)[1]
            if path == authority["path"]:
                return blobs[head]
            return current_materials[path]
        return original_git(REPOSITORY_ROOT, arguments)

    def read_policy(_: Path, arguments: list[str], label: str) -> bytes:
        try:
            return read_git(tmp_path, arguments)
        except checker.HumanReviewSignatureRecordError as error:
            raise guard.GuardError(label) from error

    monkeypatch.setattr(guard, "_delegation_git_bytes", read_policy)
    monkeypatch.setattr(checker, "_carry_git_bytes", read_git)
    event = SimpleNamespace(base_sha=baseline.base, head_sha=head)

    def validate(*, sync_worktree: bool = True) -> None:
        raw = json.dumps(current, ensure_ascii=False).encode()
        blobs[head] = raw
        if sync_worktree:
            policy_path.write_bytes(raw)
        # 基線は合成値を直接授権せず、実factoryの原本/anchor照合を毎回通す。
        fixed = checker._gate6_baseline(REPOSITORY_ROOT)
        reader = checker._Gate6CurrentReader(tmp_path)
        try:
            policy, digest = guard._load_delegation_policy(tmp_path, reader.head)
        except guard.GuardError as error:
            raise checker.HumanReviewSignatureRecordError(str(error)) from error
        checker._validate_gate6_head_bytes(tmp_path, event, authority)
        checker._validate_gate6_carry_policy(
            tmp_path, reader.head, guard, authority, policy, digest,
            reader.read_bytes(authority["path"]), fixed,
        )

    return validate, authority, current, blobs


def test_carry_policy_accepts_only_old_policy_or_target_append(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """固定旧hashの経路と、同一非targets/旧全prefixの追記だけを通す。"""
    validate, authority, current, blobs = _policy_extension_fixture(monkeypatch, tmp_path)
    validate()
    current["targets"].append({"pr": 185, "branch": "fix/second-fixture-extension"})
    validate()
    accepted = json.loads(blobs[checker._gate6_ready_values(REPOSITORY_ROOT)[0]])
    current.clear()
    current.update(accepted)
    # 元のraw byteと異なる整形でも、旧対象だけの意味同値は追記0件として扱う。
    validate()
    guard = checker._carry_core_guard(REPOSITORY_ROOT)
    raw = blobs[checker._gate6_ready_values(REPOSITORY_ROOT)[0]]
    path = tmp_path / authority["path"]
    path.write_bytes(raw)
    checker._validate_gate6_carry_policy(
        tmp_path, checker._carry_git_bytes(REPOSITORY_ROOT, ["rev-parse", "HEAD"]).decode().strip(),
        guard, authority, accepted, hashlib.sha256(raw).hexdigest(), raw,
        checker._gate6_baseline(REPOSITORY_ROOT),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "schema-version", "disabled", "repository", "source", "source-kind",
        "delegated-at", "expiry",
        "quotes", "publisher", "publisher-role", "unknown-field", "target-unknown-field",
        "duplicate-target", "bool-pr", "remove-old", "reorder-old", "replace-old",
    ],
)
def test_carry_policy_extension_rejects_invalid_or_nonappend_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str,
) -> None:
    """既loaderの有効性検査と全旧targetsのprefix検査を両方維持する。"""
    validate, _, current, _ = _policy_extension_fixture(monkeypatch, tmp_path)
    fields = {
        "schema-version": ("schema_version", 2),
        "disabled": ("enabled", False), "repository": ("repository", "foreign/repo"),
        "source": ("source", "unknown-source"), "source-kind": ("source_kind", "unknown"),
        "delegated-at": ("delegated_at", "2026-10-24"),
        "expiry": ("expires", "never"), "quotes": ("quotes", ["other"]),
        "publisher": ("publisher", "other"), "publisher-role": ("publisher_role", "other"),
        "unknown-field": ("unknown", True),
    }
    if mutation in fields:
        key, value = fields[mutation]
        current[key] = value
    elif mutation == "target-unknown-field":
        current["targets"][-1]["unknown"] = True
    elif mutation == "duplicate-target":
        current["targets"].append(copy.deepcopy(current["targets"][0]))
    elif mutation == "bool-pr":
        current["targets"][-1]["pr"] = True
    elif mutation == "remove-old":
        current["targets"].pop(0)
    elif mutation == "reorder-old":
        current["targets"][0], current["targets"][1] = (
            current["targets"][1], current["targets"][0],
        )
    else:
        current["targets"][0]["branch"] = "fix/replaced-old-target"
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        validate()


@pytest.mark.parametrize(
    "mutation",
    ["authority-hash", "authority-pr", "authority-branch", "anchor-hash", "missing-anchor",
     "unknown-anchor", "nonancestor", "worktree-head-mismatch", "validator-head-mismatch"],
)
def test_carry_policy_extension_rejects_unbound_anchor_or_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str,
) -> None:
    """既受理c6da/固定ancestorと現worktree→HEAD byteの束縛を省略しない。"""
    validate, authority, _, blobs = _policy_extension_fixture(monkeypatch, tmp_path)
    if mutation == "authority-hash":
        authority["sha256"] = "0" * 64
    elif mutation == "authority-pr":
        authority["pr"] = 184
        authority["branch"] = "feature/fixture-policy-extension"
    elif mutation == "authority-branch":
        authority["branch"] = "fix/other-pr183-branch"
    elif mutation == "anchor-hash":
        accepted = json.loads(blobs[checker._gate6_ready_values(REPOSITORY_ROOT)[0]])
        accepted["targets"].append({"pr": 186, "branch": "fix/changed-anchor"})
        blobs[checker._gate6_ready_values(REPOSITORY_ROOT)[0]] = json.dumps(accepted).encode()
    elif mutation == "missing-anchor":
        blobs.pop(checker._gate6_ready_values(REPOSITORY_ROOT)[0])
    elif mutation == "unknown-anchor":
        _, carry_hash, policy_hash = checker._gate6_ready_values(REPOSITORY_ROOT)
        monkeypatch.setattr(checker, "_gate6_ready_values", lambda _: (
            "0" * 40, carry_hash, policy_hash,
        ))
    elif mutation == "nonancestor":
        original = checker._carry_git_bytes
        def reject(root: Path, arguments: list[str]) -> bytes:
            if arguments[:2] == ["merge-base", "--is-ancestor"]:
                raise checker.HumanReviewSignatureRecordError("固定anchorは祖先でない")
            return original(root, arguments)
        monkeypatch.setattr(checker, "_carry_git_bytes", reject)
    elif mutation == "validator-head-mismatch":
        source = tmp_path / "scripts/check_human_review_signature.py"
        source.write_bytes(source.read_bytes() + b"\n")
    else:
        (tmp_path / authority["path"]).write_text("{}")
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        validate(sync_worktree=mutation != "worktree-head-mismatch")


def test_carry_policy_extension_rejects_missing_worktree_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """HEADのpolicyが有効でもcheckoutから消えた入力を継承しない。"""
    validate, _, _, _ = _policy_extension_fixture(monkeypatch, tmp_path)
    with pytest.raises(FileNotFoundError):
        validate(sync_worktree=False)


def test_carry_policy_extension_requires_non_targets_exact_even_after_valid_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """loader通過後も旧policyと全非targetsを独立に比較する。"""
    guard = checker._carry_core_guard(REPOSITORY_ROOT)
    validate, authority, current, _ = _policy_extension_fixture(monkeypatch, tmp_path)
    current["quotes"].append("synthetic extra quote")
    raw = json.dumps(current, ensure_ascii=False).encode()
    (tmp_path / authority["path"]).write_bytes(raw)
    baseline = checker._gate6_baseline(REPOSITORY_ROOT)
    accepted, _ = guard._load_delegation_policy(REPOSITORY_ROOT, baseline.anchor)
    head = checker._carry_git_bytes(REPOSITORY_ROOT, ["rev-parse", "HEAD"]).decode().strip()
    with pytest.raises(checker.HumanReviewSignatureRecordError, match="追記以外"):
        checker._validate_gate6_carry_policy(
            tmp_path, head, guard, authority, current, hashlib.sha256(raw).hexdigest(),
            raw, baseline,
        )
    # 同じ改変は、独立の既loaderでも拒否される。
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        validate()


@pytest.mark.parametrize('base', [checker._ORDINARY_ANCHOR, '0' * 40])
def test_ordinary_rejects_legacy_or_foreign_public_base(ordinary_fixture: Any, base: str) -> None:
    """規範原本のanchorを実PR baseの代用にせず、未知baseも拒否する。"""
    root, guard, event, _, _, _, _, _ = ordinary_fixture
    changed = guard.PullRequestEvent(**{**vars(event), 'base_sha': base})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, changed)
