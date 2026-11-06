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
    """旧33受理済みrecord/schemaを同じ固定原典から復元する。"""
    anchor = _formal_190_revision()
    return tuple(json.loads(checker._carry_git_bytes(repository, [
        'show', f'{anchor}:{path}',
    ])) for path in (checker.GATE6_ORDINARY_PATH, checker.GATE6_ORDINARY_SCHEMA_PATH))


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
        if path in {*record['assets'], *checker._ORDINARY_FIXED_INPUTS}:
            target.write_bytes(checker._carry_git_bytes(repository, [
                'show', f'{_formal_190_revision()}:{path}',
            ]))
        else:
            target.write_bytes((repository / path).read_bytes())
    # coverage consumerの固定Git読取だけを既objectsへ向ける。index/refは変更しない。
    gitdir = checker._carry_git_bytes(
        repository, ['rev-parse', '--absolute-git-dir'],
    ).decode().strip()
    (root / '.git').write_text('gitdir: ' + gitdir + '\n')
    _write_t1_append_json(root / checker.GATE6_ORDINARY_PATH, record)
    _write_t1_append_json(root / checker.GATE6_ORDINARY_SCHEMA_PATH, schema)
    policy_path = root / 'docs/features/mvp-delegated-core-review/policy.json'
    # 合成PR187のpolicyは実公開base＋既PR186依存suffixへ固定する。
    # 最新policyの後続targetsを今回新受理のfixtureへ混入しない。
    pins = checker._ordinary_pins(repository)
    policy = json.loads(checker._carry_git_bytes(repository, [
        'show', f'{pins["public_base"]}:docs/features/mvp-delegated-core-review/policy.json',
    ]))
    policy['targets'].extend([
        {'pr': 186, 'branch': 'feature/mvp-t1-first-pitch'},
        {'pr': 187, 'branch': checker._ORDINARY_BRANCH},
    ])
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
        if args == ['merge-base', '--is-ancestor', base, head]:
            return b''  # 合成の後続baseを同headの祖先として供給する。
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
        if args == ['show', base + ':docs/features/mvp-delegated-core-review/policy.json']:
            return baseline['docs/features/mvp-delegated-core-review/policy.json']
        return old_delegation_git(repository, args, label)

    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    monkeypatch.setattr(guard, '_delegation_git_bytes', delegation_read)
    monkeypatch.setattr(checker, '_carry_core_guard', lambda _: guard)
    url = 'https://github.com/masaki1025/pitchlog/pull/187#issuecomment-187'
    event = guard.PullRequestEvent(checker._ordinary_pins(repository)["public_base"], head,
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


def test_ordinary_rejects_pr197_code_binding_history_cochange(
    ordinary_fixture: Any,
) -> None:
    """PR197の検査器束縛と履歴を一緒に偽装しても旧33へ流用しない。"""
    root, _, _, _, _, _, _, _ = ordinary_fixture
    path = root / checker._ORDINARY_BASELINE_LEDGER_PATH
    ledger = _load_object(path)
    changed = ledger["history"][-1]["changes"]
    assert len(changed) == 1
    fake_sha = "0" * 64
    changed[0]["after"]["code_assets"][0]["sha256"] = fake_sha
    ledger["implementation_bindings"]["code_assets"][0]["sha256"] = fake_sha
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    with pytest.raises(
        checker.HumanReviewSignatureRecordError,
        match="通常33 oracle実装束縛の閉履歴が不一致",
    ):
        checker.validate_gate6_subject_carry(root)


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
             str(checker.ORDINARY_PINS_PATH), str(checker._ORDINARY_BASELINE_LEDGER_PATH),
             'scripts/frozen_baselines.py',
             'docs/features/mvp-delegated-core-review/policy.json'}
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if (path.endswith('policy.json') or path.startswith('scripts/')
                or path == 'tests/test_human_review_signature.py'
                or path in {str(checker.ORDINARY_PINS_PATH),
                            str(checker._ORDINARY_BASELINE_LEDGER_PATH)}):
            target.write_bytes((repository / path).read_bytes())
        else:
            target.write_bytes(checker._carry_git_bytes(repository, [
                'show', f'{checker._ordinary_pins(repository)["anchor"]}:{path}',
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


@pytest.mark.parametrize('base', [checker._ordinary_pins(REPOSITORY_ROOT)["anchor"], '0' * 40])
def test_ordinary_rejects_legacy_or_foreign_public_base(ordinary_fixture: Any, base: str) -> None:
    """規範原本のanchorを実PR baseの代用にせず、未知baseも拒否する。"""
    root, guard, event, _, _, _, _, _ = ordinary_fixture
    changed = guard.PullRequestEvent(**{**vars(event), 'base_sha': base})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, changed)


@pytest.fixture
def ordinary_pin_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """固定Git blobと現JSONを別々に供給し、承認台帳reader自体は実物を使う。"""
    repository = Path(__file__).resolve().parents[1]
    root = tmp_path / 'ordinary-pins'
    pin_path = root / checker.ORDINARY_PINS_PATH
    ledger_path = root / checker._ORDINARY_BASELINE_LEDGER_PATH
    pin_path.parent.mkdir(parents=True)
    ledger_path.parent.mkdir(parents=True)
    pin_path.write_bytes((repository / checker.ORDINARY_PINS_PATH).read_bytes())
    ledger_path.write_bytes((repository / checker._ORDINARY_BASELINE_LEDGER_PATH).read_bytes())
    from scripts.frozen_baselines import load_latest_series_identity

    revision = load_latest_series_identity(ledger_path, 'oracle_input')[0].value
    blob = [pin_path.read_bytes()]
    calls: list[list[str]] = []
    head = '1' * 40

    def read(_: Path, arguments: list[str]) -> bytes:
        calls.append(arguments)
        if arguments == ['show', f'{revision}:{checker.ORDINARY_PINS_PATH}']:
            return blob[0]
        if arguments == ['rev-parse', 'HEAD']:
            return head.encode()
        if arguments == ['merge-base', '--is-ancestor', revision, head]:
            return b''
        pytest.fail(f'authority以外へのGit fallback: {arguments!r}')

    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    return root, revision, blob, calls, read


def test_ordinary_pins_use_only_approved_fixed_commit(ordinary_pin_fixture: Any) -> None:
    """値は台帳単一commitのblobだけから取り、record/schemaを読まない。"""
    root, revision, blob, calls, _ = ordinary_pin_fixture
    value = checker._ordinary_pins(root)
    assert value == json.loads(blob[0])
    assert calls == [
        ['show', f'{revision}:{checker.ORDINARY_PINS_PATH}'],
        ['rev-parse', 'HEAD'],
        ['merge-base', '--is-ancestor', revision, '1' * 40],
    ]
    assert not (root / checker.GATE6_ORDINARY_PATH).exists()
    assert not (root / checker.GATE6_ORDINARY_SCHEMA_PATH).exists()


@pytest.mark.parametrize('mutation', [
    'unknown', 'missing', 'duplicate', 'scalar', 'list', 'invalid-json',
    'anchor-type', 'base-type', 'record-type', 'schema-type',
    'anchor-width', 'base-width', 'record-width', 'schema-width',
    'uppercase-commit', 'uppercase-digest',
])
def test_ordinary_pins_reject_invalid_fixed_json(ordinary_pin_fixture: Any,
                                                mutation: str) -> None:
    """Git原本と現JSONの両方が同じ不正値でもclosed4key/型/桁を拒否する。"""
    root, _, blob, _, _ = ordinary_pin_fixture
    value = json.loads(blob[0])
    original_anchor = value['anchor']
    if mutation == 'unknown':
        value['unknown'] = 'extra'
    elif mutation == 'missing':
        del value['anchor']
    elif mutation == 'scalar':
        value = None
    elif mutation == 'list':
        value = [value]
    elif mutation.endswith('-type'):
        key = {'anchor-type': 'anchor', 'base-type': 'public_base',
               'record-type': 'record_sha256', 'schema-type': 'schema_sha256'}[mutation]
        value[key] = True
    elif mutation.endswith('-width'):
        key = {'anchor-width': 'anchor', 'base-width': 'public_base',
               'record-width': 'record_sha256', 'schema-width': 'schema_sha256'}[mutation]
        value[key] = value[key][:-1]
    elif mutation == 'uppercase-commit':
        value['anchor'] = value['anchor'].upper()
    elif mutation == 'uppercase-digest':
        value['record_sha256'] = value['record_sha256'].upper()
    raw = json.dumps(value).encode()
    if mutation == 'duplicate':
        raw = b'{"anchor":"' + original_anchor.encode() + b'",' + raw[1:]
    elif mutation == 'invalid-json':
        raw = b'{invalid'
    blob[0] = raw
    (root / checker.ORDINARY_PINS_PATH).write_bytes(raw)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_pins(root)


@pytest.mark.parametrize('mutation', [
    'missing', 'invalid-json', 'duplicate', 'no-series', 'missing-history',
    'not-present', 'empty', 'two-values', 'duplicate-values', 'wrong-kind',
    'wrong-type', 'wrong-width',
    'uppercase', 'extra-value-field',
])
def test_ordinary_pins_reject_invalid_ledger_without_git_fallback(
    ordinary_pin_fixture: Any, mutation: str,
) -> None:
    """不正台帳から現JSON/HEAD/recordの自己申告へ切替えない。"""
    root, _, _, calls, _ = ordinary_pin_fixture
    path = root / checker._ORDINARY_BASELINE_LEDGER_PATH
    ledger = json.loads(path.read_bytes())
    latest = [r for r in ledger['history'] if r['series'] == 'oracle_input'][-1]
    identity = latest['new_identity']
    if mutation == 'missing':
        path.unlink()
    elif mutation == 'invalid-json':
        path.write_bytes(b'{invalid')
    elif mutation == 'duplicate':
        path.write_bytes(b'{"history": [],' + path.read_bytes()[1:])
    else:
        if mutation == 'no-series':
            ledger['history'] = [r for r in ledger['history'] if r['series'] != 'oracle_input']
        elif mutation == 'missing-history':
            del ledger['history']
        elif mutation == 'not-present':
            identity['present'] = False
        elif mutation == 'empty':
            identity['values'] = []
        elif mutation == 'two-values':
            identity['values'].append({'kind': 'literal_commit_string', 'value': '2' * 40})
        elif mutation == 'duplicate-values':
            identity['values'].append(copy.deepcopy(identity['values'][0]))
        elif mutation == 'wrong-kind':
            identity['values'][0]['kind'] = 'head'
        elif mutation == 'wrong-type':
            identity['values'][0]['value'] = 123
        elif mutation == 'wrong-width':
            identity['values'][0]['value'] = '2' * 39
        elif mutation == 'uppercase':
            identity['values'][0]['value'] = 'A' * 40
        else:
            identity['values'][0]['unknown'] = True
        path.write_text(json.dumps(ledger))
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_pins(root)
    assert calls == []


@pytest.mark.parametrize('failure', ['git-missing', 'not-ancestor', 'missing-current',
                                    'changed-current', 'linked-current-record'])
def test_ordinary_pins_fail_closed_without_current_or_head_fallback(
    ordinary_pin_fixture: Any, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    """固定Git欠落/到達不能/現JSON改変で自己生成へfallbackしない。"""
    root, revision, _, calls, read = ordinary_pin_fixture
    path = root / checker.ORDINARY_PINS_PATH
    if failure == 'missing-current':
        path.unlink()
    elif failure == 'changed-current':
        path.write_bytes(path.read_bytes() + b' ')
    elif failure == 'linked-current-record':
        record = b'{"attacker":"record"}'
        schema = b'{"attacker":"schema"}'
        (root / checker.GATE6_ORDINARY_PATH).write_bytes(record)
        (root / checker.GATE6_ORDINARY_SCHEMA_PATH).write_bytes(schema)
        value = json.loads(path.read_bytes())
        value['record_sha256'] = hashlib.sha256(record).hexdigest()
        value['schema_sha256'] = hashlib.sha256(schema).hexdigest()
        path.write_text(json.dumps(value))
    else:
        def unavailable(repository: Path, arguments: list[str]) -> bytes:
            if ((failure == 'git-missing' and arguments[0] == 'show')
                    or (failure == 'not-ancestor' and arguments[0] == 'merge-base')):
                calls.append(arguments)
                raise checker.HumanReviewSignatureRecordError('固定authority取得失敗')
            return read(repository, arguments)
        monkeypatch.setattr(checker, '_carry_git_bytes', unavailable)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_pins(root)
    assert ['show', f'{revision}:{checker.ORDINARY_PINS_PATH}'] in calls
    assert all(not (a[0] == 'show' and a[1].startswith('HEAD:')) for a in calls)


def test_ordinary_corrupt_base_rejects_before_current_record_and_fetch(
    ordinary_fixture: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """独立authority読取追加後もevent.baseを現recordより先に検査する。"""
    root, guard, event, base, baseline, _, _, fetches = ordinary_fixture
    baseline[str(checker.GATE6_ORDINARY_PATH)] += b' '
    def forbidden(_: Path) -> Any:
        pytest.fail('不正baseより先に現recordへ到達')
    monkeypatch.setattr(checker, '_ordinary_record', forbidden)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='base記録'):
        checker.validate_gate6_ci_event(root, _ordinary_later_event(root, guard, event, base))
    assert fetches == []


@pytest.mark.parametrize('path', [str(checker.ORDINARY_PINS_PATH),
                                str(checker._ORDINARY_BASELINE_LEDGER_PATH),
                                'scripts/frozen_baselines.py'])
def test_ordinary_authority_and_reader_are_bound_to_final_head(
    ordinary_fixture: Any, monkeypatch: pytest.MonkeyPatch, path: str,
) -> None:
    """新authority/台帳/readerも最終headの全byte束縛から除外しない。"""
    root, _, event, _, baseline, _, _, _ = ordinary_fixture
    assert path in checker._ORDINARY_EXECUTION_INPUTS
    record = checker._ordinary_record(root)
    original = checker._carry_git_bytes
    committed = baseline[path]
    def read(repository: Path, arguments: list[str]) -> bytes:
        if arguments == ['show', f'{event.head_sha}:{path}']:
            return committed
        return original(repository, arguments)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    (root / path).write_bytes(committed + b' ')
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_head(root, event, record)



def test_ordinary_authority_failure_never_falls_back_to_legacy_validation(
    ordinary_fixture: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ordinary原本がある場合、authority欠損を旧carry/append成功へ切替えない。"""
    root, _, event, _, _, _, _, fetches = ordinary_fixture
    (root / checker.ORDINARY_PINS_PATH).unlink()
    def forbidden(*_: Any, **__: Any) -> Any:
        pytest.fail('ordinary authority欠損から旧検査へfallback')
    monkeypatch.setattr(checker, '_validate_gate6_subject_carry', forbidden)
    monkeypatch.setattr(checker, '_validate_gate6_t1_input_append', forbidden)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_subject_carry(root)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.fixture(scope='module')
def integration_origin() -> tuple[str, dict[str, Any]]:
    """承認Git原典の祖先から正式18かつordinary未導入の実baseを選ぶ。"""
    repository = Path(__file__).resolve().parents[1]
    revision = checker._ordinary_authority_revision(repository)
    guard = checker._carry_core_guard(repository)
    expected, _ = guard._load_delegation_policy(repository, revision)
    if len(expected['targets']) == 19:
        # 後発197台帳の現行19ではなく、直前の実承認policy18から旧189を作る。
        ledger = json.loads((repository / checker._ORDINARY_BASELINE_LEDGER_PATH).read_bytes())
        tail = ledger['history'][-1]
        assert tail['acceptance_id'] == 'masaki1025/pitchlog#197'
        assert tail['new_identity']['values'] == [
            {'kind': 'literal_commit_string', 'value': revision}]
        revision = tail['prior_identity']['values'][0]['value']
        expected, _ = guard._load_delegation_policy(repository, revision)
        assert len(expected['targets']) == 18
    queue = [revision]
    seen: set[str] = set()
    while queue and len(seen) < 256:
        candidate = queue.pop(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        if checker._ordinary_base_presence(repository, candidate) == (False, False):
            policy, _ = guard._load_delegation_policy(repository, candidate)
            if policy == expected:
                return candidate, expected
        queue.extend(checker._carry_git_bytes(repository, [
            'rev-parse', f'{candidate}^@',
        ]).decode().split())
    pytest.fail('正式policy18と両ordinary不存在の承認済み祖先baseがない')


@pytest.fixture
def integration_fixture(ordinary_fixture: Any,
                        integration_origin: tuple[str, dict[str, Any]]) -> Any:
    """実base/head/diffと本物委任validatorを使うPR189合成証拠を作る。"""
    root, guard, old_event, later_base, baseline, calls, comment, fetches = ordinary_fixture
    base, policy = integration_origin
    policy_path = root / guard.DELEGATION_POLICY_PATH
    _write_t1_append_json(policy_path, policy)
    baseline[str(guard.DELEGATION_POLICY_PATH)] = policy_path.read_bytes()
    url = 'https://github.com/masaki1025/pitchlog/pull/189#issuecomment-189'
    event = guard.PullRequestEvent(base, old_event.head_sha,
        'PO-DELEGATION-EVIDENCE: ' + url, 189, old_event.repository,
        old_event.head_repository, 'feature/mvp-first-ball-vertical')
    evidence = {
        'authority_sha256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'pr': 189, 'base': base, 'head': event.head_sha,
        'diff_sha256': guard._delegation_diff(root, event),
        'paths': guard.changed_paths(root, base, event.head_sha),
        'reviewer_agent': 'integration-nonauthor',
        'candidate_agents': ['integration-author', 'root'],
        'independent': True, 'verdict': 'approved', 'findings': [],
        'report': {'task': 'integration-nonauthor', 'reviewed_head': event.head_sha,
                   'text': '合成189単位試験。実公開受理の資料ではない。'},
    }
    comment.clear()
    comment.update({'id': 189, 'html_url': url,
        'issue_url': 'https://api.github.com/repos/masaki1025/pitchlog/issues/189',
        'author_association': 'OWNER', 'user': {'login': 'masaki1025'},
        'body': guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)})
    return root, guard, event, later_base, baseline, calls, comment, fetches


def test_integration_189_local_technical_and_actual_delegation_are_distinct(
    integration_fixture: Any, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """localはfetch0、189だけは実委任照合を呼び旧187受理とは別表示する。"""
    root, guard, event, _, _, _, _, fetches = integration_fixture
    assert checker.main(['--root', str(root), '--gate6-carry']) == 0
    local = capsys.readouterr().out
    assert 'TECHNICAL ONLY; final delegation NOT CHECKED' in local
    assert 'DELEGATED VERIFIED' not in local
    assert fetches == []
    observed = []
    original = guard.verify_delegated_confirmation
    def verified(actual_root: Path, actual_event: Any) -> None:
        observed.append((actual_root, actual_event))
        original(actual_root, actual_event)
    monkeypatch.setattr(guard, 'verify_delegated_confirmation', verified)
    monkeypatch.setattr(guard, 'load_pull_request_event', lambda: event)
    assert checker.main(['--root', str(root), '--gate6-carry', '--ci']) == 0
    public = capsys.readouterr().out
    assert 'PR189 integration carry: DELEGATED VERIFIED' in public
    assert 'not PR187 acceptance; not a personal signature' in public
    assert observed == [(root, event)]
    assert fetches == ['189']


@pytest.mark.parametrize('mutation', ['number', 'branch', 'repository', 'fork',
                                    'base', 'head', 'bool-number'])
def test_integration_189_event_is_exact(integration_fixture: Any, mutation: str) -> None:
    """番号/branch/両repo/版を189限定手続きの外へ広げない。"""
    root, guard, event, _, _, _, _, fetches = integration_fixture
    fields = vars(event).copy()
    key, value = {
        'number': ('number', 190), 'branch': ('head_branch', 'feature/other'),
        'repository': ('repository', 'other/pitchlog'),
        'fork': ('head_repository', 'other/pitchlog'),
        'base': ('base_sha', '0' * 40), 'head': ('head_sha', '0' * 40),
        'bool-number': ('number', True),
    }[mutation]
    fields[key] = value
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_integration_ci(root, guard.PullRequestEvent(**fields))
    assert fetches == []


@pytest.mark.parametrize('present', ['record', 'schema', 'both'])
def test_integration_189_rejects_any_base_ordinary_presence(
    integration_fixture: Any, monkeypatch: pytest.MonkeyPatch, present: str,
) -> None:
    """189はbase両不存在だけを許し、片側/両方の存在を継承へfallbackしない。"""
    root, _, event, _, _, _, _, fetches = integration_fixture
    original = checker._carry_git_bytes
    def read(repository: Path, args: list[str]) -> bytes:
        if args == ['show', f'{event.base_sha}:contracts/state-transition']:
            names = []
            if present in {'record', 'both'}:
                names.append(checker.GATE6_ORDINARY_PATH.name)
            if present in {'schema', 'both'}:
                names.append(checker.GATE6_ORDINARY_SCHEMA_PATH.name)
            return '\n'.join(names).encode()
        return original(repository, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='両資産不存在'):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('path', [str(checker.GATE6_ORDINARY_PATH),
                                str(checker.GATE6_ORDINARY_SCHEMA_PATH)])
def test_integration_189_requires_both_head_records(integration_fixture: Any,
                                                  path: str) -> None:
    """head片側欠損を189統合の成立にしない。"""
    root, _, event, _, _, _, _, fetches = integration_fixture
    (root / path).unlink()
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('side', ['base', 'head'])
@pytest.mark.parametrize('mutation', ['missing', 'extra', 'order', 'field', 'prefix'])
def test_integration_189_requires_fixed_policy18_all_fields(
    integration_fixture: Any, monkeypatch: pytest.MonkeyPatch, side: str, mutation: str,
) -> None:
    """実base/head双方の18全field/順序を固定Git原典へ一致させる。"""
    root, guard, event, _, _, _, _, fetches = integration_fixture
    path = root / guard.DELEGATION_POLICY_PATH
    policy = json.loads(path.read_bytes())
    if mutation == 'missing':
        policy['targets'].pop()
    elif mutation == 'extra':
        policy['targets'].append({'pr': 194, 'branch': 'feature/extra'})
    elif mutation == 'order':
        policy['targets'].reverse()
    elif mutation == 'field':
        policy['quotes'][0] += 'changed'
    else:
        policy['targets'][12] = {'pr': 186, 'branch': 'feature/mvp-t1-first-pitch'}
    raw = json.dumps(policy).encode()
    if side == 'head':
        path.write_bytes(raw)
    else:
        original = guard._delegation_git_bytes
        def read(repository: Path, args: list[str], label: str) -> bytes:
            if args == ['show', f'{event.base_sha}:{guard.DELEGATION_POLICY_PATH}']:
                return raw
            return original(repository, args, label)
        monkeypatch.setattr(guard, '_delegation_git_bytes', read)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('target', ['record', 'schema', 'subject', 'request', 'response',
                                   'vectors', 'typescript', 'coverage', 'mapping',
                                   'game-coverage', 'handoff'])
def test_integration_189_retains_all_record_schema_and_math_hashes(
    integration_fixture: Any, target: str,
) -> None:
    """189手続きも旧4pinと数学9資産の全byte照合を通る。"""
    root, _, event, _, _, _, _, fetches = integration_fixture
    record = json.loads((root / checker.GATE6_ORDINARY_PATH).read_bytes())
    paths = {'record': checker.GATE6_ORDINARY_PATH,
             'schema': checker.GATE6_ORDINARY_SCHEMA_PATH}
    labels = ['subject', 'coverage', 'mapping', 'game-coverage', 'handoff',
              'request', 'response', 'vectors', 'typescript']
    for label, path in zip(labels, record['assets'], strict=True):
        paths[label] = path
    path = root / paths[target]
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mutation', ['marker-missing', 'marker-duplicate', 'url',
    'publisher', 'head', 'base', 'diff', 'paths', 'authority', 'same-author',
    'not-independent', 'p0', 'p1', 'report-head', 'api'])
def test_integration_189_invalid_delegation_never_falls_back(
    integration_fixture: Any, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """189の今回版/差分/全path/掲載主体/独立性/重大指摘を既validatorで拒否する。"""
    root, guard, event, _, _, _, comment, _ = integration_fixture
    evidence = json.loads(comment['body'][len(guard.DELEGATION_COMMENT_MARKER):])
    body = event.body
    if mutation == 'marker-missing':
        body = ''
    elif mutation == 'marker-duplicate':
        body += '\n' + body
    elif mutation == 'url':
        comment['html_url'] = comment['html_url'].replace('/189#', '/187#')
    elif mutation == 'publisher':
        comment['user']['login'] = 'other'
    elif mutation in {'head', 'base'}:
        evidence[mutation] = '0' * 40
    elif mutation == 'diff':
        evidence['diff_sha256'] = '0' * 64
    elif mutation == 'paths':
        evidence['paths'] = []
    elif mutation == 'authority':
        evidence['authority_sha256'] = '0' * 64
    elif mutation == 'same-author':
        evidence['candidate_agents'].append(evidence['reviewer_agent'])
    elif mutation == 'not-independent':
        evidence['independent'] = False
    elif mutation in {'p0', 'p1'}:
        evidence['findings'] = [{'severity': mutation.upper(), 'resolved': False,
                                 'detail': '合成未解消'}]
    elif mutation == 'report-head':
        evidence['report']['reviewed_head'] = '0' * 40
    else:
        def failed(_: str) -> Any:
            raise guard.GuardError('合成API故障')
        monkeypatch.setattr(guard, '_fetch_delegation_comment', failed)
    comment['body'] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    changed = guard.PullRequestEvent(**{**vars(event), 'body': body})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, changed)


def test_integration_189_does_not_accept_unknown_first_introduction_or_187_reuse(
    integration_fixture: Any,
) -> None:
    """未知PR初導入と189証拠の旧187新受理への流用を拒否する。"""
    root, guard, event, _, _, _, _, fetches = integration_fixture
    unknown = guard.PullRequestEvent(**{**vars(event), 'number': 194,
                                       'head_branch': 'feature/unknown'})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, unknown)
    old = guard.PullRequestEvent(**{**vars(event), 'number': 187,
        'base_sha': checker._ordinary_pins(root)['public_base'],
        'head_branch': checker._ORDINARY_BRANCH})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, old)
    assert fetches == []


def test_integration_190_base_first_inheritance_has_no_new_acceptance(
    integration_fixture: Any,
) -> None:
    """正式189後18系の不変継承は公開fetch/新187受理をしない。"""
    root, guard, event, base, _, _, _, fetches = integration_fixture
    later = guard.PullRequestEvent(base, event.head_sha, '', 190, event.repository,
        event.head_repository, 'feature/mvp-recording-continuation')
    assert 'UNCHANGED FROM PR BASE; no new ordinary acceptance' in (
        checker.validate_gate6_ci_event(root, later))
    assert fetches == []


@pytest.mark.parametrize('mutation', ['record', 'schema', 'missing-record', 'missing-schema',
                                    'both-missing', 'asset', 'old-input', 'policy'])
def test_integration_190_corrupt_base_rejects_before_current_math(
    integration_fixture: Any, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """baseの両record/数学/旧入力/policy腐敗を現recordの読取前に拒否する。"""
    root, guard, event, base, baseline, _, _, fetches = integration_fixture
    record = json.loads(baseline[str(checker.GATE6_ORDINARY_PATH)])
    if mutation in {'record', 'schema'}:
        path = (checker.GATE6_ORDINARY_PATH if mutation == 'record'
                else checker.GATE6_ORDINARY_SCHEMA_PATH)
        baseline[str(path)] += b' '
    elif mutation in {'missing-record', 'missing-schema', 'both-missing'}:
        if mutation in {'missing-record', 'both-missing'}:
            del baseline[str(checker.GATE6_ORDINARY_PATH)]
        if mutation in {'missing-schema', 'both-missing'}:
            del baseline[str(checker.GATE6_ORDINARY_SCHEMA_PATH)]
    elif mutation == 'asset':
        baseline[next(iter(record['assets']))] += b' '
    elif mutation == 'old-input':
        baseline[next(iter(checker._ORDINARY_FIXED_INPUTS))] += b' '
    else:
        policy = json.loads(baseline[str(guard.DELEGATION_POLICY_PATH)])
        policy['targets'].pop()
        baseline[str(guard.DELEGATION_POLICY_PATH)] = json.dumps(policy).encode()
    original = Path.read_bytes
    prohibited = {root / checker.GATE6_ORDINARY_PATH,
                  root / checker.GATE6_ORDINARY_SCHEMA_PATH,
                  *(root / path for path in record['assets'])}
    def read(path: Path) -> bytes:
        if path in prohibited:
            pytest.fail('不正baseより先にcurrent数学を読取')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    later = guard.PullRequestEvent(base, event.head_sha, '', 190, event.repository,
        event.head_repository, 'feature/mvp-recording-continuation')
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, later)
    assert fetches == []


def test_integration_local_is_closed_but_later_policy_suffix_is_explicit(
    integration_fixture: Any,
) -> None:
    """local exact18と後続の末尾追記を区別し、18系を旧PRへ継承させない。"""
    root, guard, event, base, _, _, _, fetches = integration_fixture
    path = root / guard.DELEGATION_POLICY_PATH
    policy = json.loads(path.read_bytes())
    policy['targets'].append({'pr': 194, 'branch': 'feature/later'})
    _write_t1_append_json(path, policy)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_subject_carry(root)
    later = guard.PullRequestEvent(base, event.head_sha, '', 194, event.repository,
        event.head_repository, 'feature/later')
    assert 'no new ordinary acceptance' in checker.validate_gate6_ci_event(root, later)
    old = guard.PullRequestEvent(**{**vars(later), 'number': 188})
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, old)
    assert fetches == []



@pytest.mark.parametrize('mode', ['integration189', 'inheritance190'])
def test_integration_base_must_be_actual_head_ancestor(
    integration_fixture: Any, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    """同一policyを持つ別履歴baseを189/正式18継承の比較元にしない。"""
    root, guard, event, base, _, _, _, fetches = integration_fixture
    if mode == 'inheritance190':
        event = guard.PullRequestEvent(base, event.head_sha, '', 190, event.repository,
            event.head_repository, 'feature/mvp-recording-continuation')
    original = checker._carry_git_bytes
    def read(repository: Path, args: list[str]) -> bytes:
        if args == ['merge-base', '--is-ancestor', event.base_sha, event.head_sha]:
            raise checker.HumanReviewSignatureRecordError('合成baseはheadの祖先でない')
        return original(repository, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='祖先'):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


def _formal_190_revision() -> str:
    """旧119受理recordと全数学資産を同じ独立JSON原典へ束縛する。"""
    path = (Path(__file__).resolve().parents[1]
            / "tests/fixtures/pr191_formal_ordinary_baseline_v1.json")
    pin = json.loads(path.read_text(encoding="utf-8"),
                     object_pairs_hook=descriptor_checker._reject_duplicate_keys)
    assert type(pin) is dict and set(pin) == {"schema_version", "baseline_commit"}
    assert type(pin["schema_version"]) is int and pin["schema_version"] == 1
    revision = pin["baseline_commit"]
    assert type(revision) is str and len(revision) == 40
    assert all(char in "0123456789abcdef" for char in revision)
    return revision


@pytest.fixture
def terminal_extension_fixture(ordinary_fixture: Any,
                               monkeypatch: pytest.MonkeyPatch) -> Any:
    """固定224/40ceと合成公開proofを使い、実受理と区別する。"""
    root, guard, prior_event, _, _, calls, comment, fetches = ordinary_fixture
    repository = Path(__file__).resolve().parents[1]
    reference_path = repository / checker._TERMINAL_REFERENCE_PATH
    reference = json.loads(reference_path.read_bytes())
    for path in checker._TERMINAL_EXTENSION_FILES:
        (root / path).write_bytes(checker._carry_git_bytes(repository, [
            'show', reference['candidate_revision'] + ':' + path,
        ]))
    for path in checker._TERMINAL_EXTENSION_INPUTS:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository / path).read_bytes())
    frozen_path = root / 'contracts/tenant_boundary/frozen-inputs.json'
    frozen = json.loads(frozen_path.read_bytes())
    # 合成境界の登録であり、正式frozen台帳の受理を代行しない。
    frozen['frozen_inputs']['terminal_ordinary_extension_revision'] = {
        'value': reference['candidate_revision'],
        'purpose': ('PR191 ordinary33の歴史scopeとterminal有限extensionの全前後を'
                    '審査済み固定Gitへ束縛する。旧署名subject・現木自己期待・'
                    '任意PRの受理に流用しない。'),
        'sources': ['scripts/check_human_review_signature.py:_terminal_extension_reference',
                    'tests/test_human_review_signature.py:terminal_extension_fixture'],
    }
    _write_t1_append_json(frozen_path, frozen)
    policy_path = root / guard.DELEGATION_POLICY_PATH
    policy_path.write_bytes(checker._carry_git_bytes(repository, [
        'show', reference['base_revision'] + ':' + str(guard.DELEGATION_POLICY_PATH),
    ]))
    url = 'https://github.com/masaki1025/pitchlog/pull/191#issuecomment-191'
    event = guard.PullRequestEvent(reference['base_revision'], prior_event.head_sha,
        'PO-DELEGATION-EVIDENCE: ' + url, 191, prior_event.repository,
        prior_event.head_repository, 'feature/mvp-terminal-pitches')
    evidence = {
        'authority_sha256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'pr': 191, 'base': event.base_sha, 'head': event.head_sha,
        'diff_sha256': guard._delegation_diff(root, event),
        'paths': guard.changed_paths(root, event.base_sha, event.head_sha),
        'reviewer_agent': 'terminal-nonauthor', 'candidate_agents': ['terminal-author', 'root'],
        'independent': True, 'verdict': 'approved', 'findings': [],
        'report': {'task': 'terminal-nonauthor', 'reviewed_head': event.head_sha,
                   'text': '独立単体試験の合成公開proof。実PR191受理・本人署名ではない。'},
    }
    comment.clear()
    comment.update({'id': 191, 'html_url': url,
        'issue_url': 'https://api.github.com/repos/masaki1025/pitchlog/issues/191',
        'author_association': 'OWNER', 'user': {'login': 'masaki1025'},
        'body': guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)})
    committed = {path.relative_to(root).as_posix(): path.read_bytes()
                 for path in root.rglob('*') if path.is_file() and path.name != '.git'}
    original = checker._carry_git_bytes
    def read(repository: Path, args: list[str]) -> bytes:
        if args[0] == 'show' and args[1].startswith(event.head_sha + ':'):
            path = args[1].split(':', 1)[1]
            if path not in committed:
                raise checker.HumanReviewSignatureRecordError('合成head欠落')
            return committed[path]
        return original(repository, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    return root, guard, event, comment, fetches, committed, calls


def test_terminal_extension_local_and_public_proof_remain_distinct(
    terminal_extension_fixture: Any, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧scope保持は技術確認、現追加だけは実validatorの公開証拠を要求する。"""
    root, guard, event, _, fetches, _, _ = terminal_extension_fixture
    assert checker.main(['--root', str(root), '--gate6-carry']) == 0
    assert 'TECHNICAL ONLY; final delegation NOT CHECKED' in capsys.readouterr().out
    assert fetches == []
    observed = []
    original = guard.verify_delegated_confirmation
    def verify(actual_root: Path, actual_event: Any) -> None:
        observed.append((actual_root, actual_event))
        original(actual_root, actual_event)
    monkeypatch.setattr(guard, 'verify_delegated_confirmation', verify)
    monkeypatch.setattr(guard, 'load_pull_request_event', lambda: event)
    assert checker.main(['--root', str(root), '--gate6-carry', '--ci']) == 0
    output = capsys.readouterr().out
    assert 'HISTORICAL PRESERVED; PR191 terminal extension: DELEGATED VERIFIED' in output
    assert 'not new PR187 acceptance; not a personal signature' in output
    assert observed == [(root, event)]
    assert fetches == ['191']


@pytest.mark.parametrize('mutation', [
    'old-case', 'old-row', 'missing', 'duplicate', 'extra', 'result', 'runner', 'ended',
    'expectation', 'history', 'descriptor-history', 'descriptor-axis', 't2-rule',
    'mapping', 'count', 'handoff', 'joint-source-pin', 'pin', 'pin-extra', 'pin-missing',
    'purpose', 'consumer', 'revision', 'record', 'schema', 'dirty-checker',
])
def test_terminal_extension_rejects_scope_or_joint_source_pin_changes(
    terminal_extension_fixture: Any, mutation: str,
) -> None:
    """固定Git全前後と旧scopeのいずれを変えても追加受理を拒否する。"""
    root, _, event, _, fetches, _, _ = terminal_extension_fixture
    contract_path = root / checker.STATE_TRANSITION_CONTRACT_PATH
    contract = json.loads(contract_path.read_bytes())
    if mutation in {'old-case', 'old-row', 'missing', 'duplicate', 'extra', 'result',
                    'runner', 'ended', 'expectation', 'history', 'joint-source-pin'}:
        case = contract['cases'][119]
        if mutation == 'old-case':
            contract['cases'][0]['expected']['plateAppearanceEnded'] = True
        elif mutation == 'old-row':
            contract['matrixRows'][0]['remarks'] += 'changed'
        elif mutation == 'missing':
            contract['cases'].pop()
        elif mutation == 'duplicate':
            contract['cases'].append(copy.deepcopy(case))
        elif mutation == 'extra':
            extra = copy.deepcopy(case)
            extra['caseId'] += '-unknown'
            contract['cases'].append(extra)
        elif mutation in {'result', 'runner', 'ended'}:
            key, value = {'result': ('resultId', 'batting-result.single'),
                          'runner': ('state.runners', 'first'),
                          'ended': ('state.gameEnded', True)}[mutation]
            case['inputCoordinate'][key] = value
        elif mutation in {'expectation', 'joint-source-pin'}:
            case['expected']['plateAppearanceEnded'] = False
        else:
            case['historyInput']['before']['stateFields']['state.outs'] = 1
        _write_t1_append_json(contract_path, contract)
        if mutation == 'joint-source-pin':
            path = root / checker._TERMINAL_REFERENCE_PATH
            pin = json.loads(path.read_bytes())
            pin['files'][str(checker.STATE_TRANSITION_CONTRACT_PATH)]['after_sha256'] = (
                hashlib.sha256(contract_path.read_bytes()).hexdigest())
            _write_t1_append_json(path, pin)
    elif mutation in {'descriptor-history', 'descriptor-axis', 't2-rule', 'mapping',
                      'count', 'handoff'}:
        paths = {'descriptor-history': 'input_axes_descriptor_v1.json',
                 'descriptor-axis': 'input_axes_descriptor_v1.json',
                 't2-rule': 'game_end_contract_v1.json', 'mapping': 'branch_row_mapping_v1.json',
                 'count': 'game_end_coverage_declaration_v1.json',
                 'handoff': 'appendix_e_consumer_handoff_v1.json'}
        path = root / 'contracts/state-transition' / paths[mutation]
        data = json.loads(path.read_bytes())
        if mutation == 'descriptor-history':
            data['freezeBaseline']['history'][0]['fact'] += 'changed'
        elif mutation == 'descriptor-axis':
            data['freezeBaseline']['criteria']['gapRegister']['rowLayers'][0][
                'qualifyWhenPredicateAxes'].append('state.count.balls')
        elif mutation == 't2-rule':
            data['decisionRows'][0]['decision']['endConditionDetected'] = False
        elif mutation == 'mapping':
            data['mappings'][11]['additionalCaseMappings'].pop()
        elif mutation == 'count':
            data['normalCaseCounts']['stateTransition'] = 135
        else:
            data['artifacts'][0]['digest'] = 'sha256:' + '0' * 64
        _write_t1_append_json(path, data)
    elif mutation in {'pin', 'pin-extra', 'pin-missing'}:
        path = root / checker._TERMINAL_REFERENCE_PATH
        pin = json.loads(path.read_bytes())
        if mutation == 'pin':
            pin['candidate_revision'] = event.head_sha
        elif mutation == 'pin-extra':
            pin['unknown'] = True
        else:
            path.unlink()
        if mutation != 'pin-missing':
            _write_t1_append_json(path, pin)
    elif mutation in {'purpose', 'consumer', 'revision'}:
        path = root / 'contracts/tenant_boundary/frozen-inputs.json'
        data = json.loads(path.read_bytes())
        entry = data['frozen_inputs']['terminal_ordinary_extension_revision']
        if mutation == 'purpose':
            entry['purpose'] += 'changed'
        elif mutation == 'consumer':
            entry['sources'].append('unknown:consumer')
        else:
            entry['value'] = event.head_sha
        _write_t1_append_json(path, data)
    else:
        path = root / {'record': checker.GATE6_ORDINARY_PATH,
                       'schema': checker.GATE6_ORDINARY_SCHEMA_PATH,
                       'dirty-checker': Path('scripts/check_human_review_signature.py')}[mutation]
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mutation', ['pr', 'branch', 'fork', 'base', 'head', 'bool-pr'])
def test_terminal_extension_rejects_other_actual_events(
    terminal_extension_fixture: Any, mutation: str,
) -> None:
    """未知targetや別base/headをPR191の受理へ流用しない。"""
    root, guard, event, _, fetches, _, _ = terminal_extension_fixture
    fields = vars(event).copy()
    key, value = {'pr': ('number', 192), 'branch': ('head_branch', 'feature/unknown'),
                  'fork': ('head_repository', 'other/pitchlog'),
                  'base': ('base_sha', '0' * 40), 'head': ('head_sha', '0' * 40),
                  'bool-pr': ('number', True)}[mutation]
    fields[key] = value
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_terminal_ci(root, guard.PullRequestEvent(**fields))
    assert fetches == []


@pytest.mark.parametrize('mutation', [
    'author-approved', 'same-author', 'non-independent', 'p0', 'p1', 'report-head',
    'head', 'base', 'diff', 'paths', 'authority', 'api',
])
def test_terminal_extension_requires_actual_independent_public_proof(
    terminal_extension_fixture: Any, mutation: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自己申告approvedや別commitの証拠を公開PO検証の代わりにしない。"""
    root, guard, event, comment, _, _, _ = terminal_extension_fixture
    evidence = json.loads(comment['body'][len(guard.DELEGATION_COMMENT_MARKER):])
    if mutation == 'author-approved':
        comment['body'] = 'author approved'
    elif mutation == 'same-author':
        evidence['candidate_agents'].append(evidence['reviewer_agent'])
    elif mutation == 'non-independent':
        evidence['independent'] = False
    elif mutation in {'p0', 'p1'}:
        evidence['findings'] = [{'severity': mutation.upper(), 'resolved': False,
                                 'detail': '合成未解消'}]
    elif mutation == 'report-head':
        evidence['report']['reviewed_head'] = '0' * 40
    elif mutation in {'head', 'base'}:
        evidence[mutation] = '0' * 40
    elif mutation in {'diff', 'authority'}:
        evidence[{'diff': 'diff_sha256', 'authority': 'authority_sha256'}[mutation]] = '0' * 64
    elif mutation == 'paths':
        evidence['paths'] = []
    else:
        def fail(_: str) -> Any:
            raise guard.GuardError('合成API故障')
        monkeypatch.setattr(guard, '_fetch_delegation_comment', fail)
    if mutation != 'author-approved':
        comment['body'] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)


@pytest.mark.parametrize('relation', ['base-head', 'candidate-head'])
def test_terminal_extension_rejects_nonancestor_inputs(
    terminal_extension_fixture: Any, monkeypatch: pytest.MonkeyPatch, relation: str,
) -> None:
    """基線または固定Cが実HEAD祖先でなければ公開証拠を読まない。"""
    root, _, event, _, fetches, _, _ = terminal_extension_fixture
    original = checker._carry_git_bytes
    pin = json.loads((root / checker._TERMINAL_REFERENCE_PATH).read_bytes())
    prior = event.base_sha if relation == 'base-head' else pin['candidate_revision']
    def read(repository: Path, args: list[str]) -> bytes:
        if args == ['merge-base', '--is-ancestor', prior, event.head_sha]:
            raise checker.HumanReviewSignatureRecordError('合成非祖先')
        return original(repository, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.fixture
def strikeout_extension_fixture(ordinary_fixture: Any,
                                 monkeypatch: pytest.MonkeyPatch) -> Any:
    """root前置Gitと合成公開proofで192を検査し、実公開受理と分離する。"""
    root, guard, prior_event, _, _, calls, comment, fetches = ordinary_fixture
    repository = Path(__file__).resolve().parents[1]
    reference = json.loads((repository / checker._STRIKEOUT_REFERENCE_PATH).read_bytes())
    for path in reference['files']:
        (root / path).write_bytes(checker._carry_git_bytes(repository, [
            'show', reference['candidate_revision'] + ':' + path,
        ]))
    for path in checker._STRIKEOUT_EXTENSION_INPUTS:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(checker._carry_git_bytes(repository, [
            'show', reference['candidate_revision'] + ':' + path,
        ]) if path in checker._STRIKEOUT_AUXILIARY_INPUTS
            else (repository / path).read_bytes())
    policy_path = root / guard.DELEGATION_POLICY_PATH
    policy_path.write_bytes(checker._carry_git_bytes(repository, [
        'show', reference['formal_base_revision'] + ':' + str(guard.DELEGATION_POLICY_PATH),
    ]))
    url = 'https://github.com/masaki1025/pitchlog/pull/192#issuecomment-192'
    event = guard.PullRequestEvent(reference['formal_base_revision'], prior_event.head_sha,
        'PO-DELEGATION-EVIDENCE: ' + url, 192, prior_event.repository,
        prior_event.head_repository, 'feature/mvp-strikeout-pitches')
    evidence = {
        'authority_sha256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'pr': 192, 'base': event.base_sha, 'head': event.head_sha,
        'diff_sha256': guard._delegation_diff(root, event),
        'paths': guard.changed_paths(root, event.base_sha, event.head_sha),
        'reviewer_agent': 'strikeout-nonauthor',
        'candidate_agents': ['strikeout-author', 'root'],
        'independent': True, 'verdict': 'approved', 'findings': [],
        'report': {'task': 'strikeout-nonauthor', 'reviewed_head': event.head_sha,
                   'text': '独立純試験の合成公開proof。実PR192受理・本人署名ではない。'},
    }
    comment.clear()
    comment.update({'id': 192, 'html_url': url,
        'issue_url': 'https://api.github.com/repos/masaki1025/pitchlog/issues/192',
        'author_association': 'OWNER', 'user': {'login': 'masaki1025'},
        'body': guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)})
    committed = {path.relative_to(root).as_posix(): path.read_bytes()
                 for path in root.rglob('*') if path.is_file() and path.name != '.git'}
    original = checker._carry_git_bytes
    def read(repository: Path, args: list[str]) -> bytes:
        if args[0] == 'show' and args[1].startswith(event.head_sha + ':'):
            path = args[1].split(':', 1)[1]
            if path not in committed:
                raise checker.HumanReviewSignatureRecordError('合成192head欠落')
            return committed[path]
        return original(repository, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    return root, guard, event, comment, fetches, committed, calls


def test_strikeout_extension_closes_real_base_failure_without_new_signature(
    strikeout_extension_fixture: Any, capsys: pytest.CaptureFixture[str],
) -> None:
    """旧失敗を残し、旧署名を更新せず技術確認と最終公開proofを分ける。"""
    root, _, event, _, fetches, _, calls = strikeout_extension_fixture
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='base数学9資産'):
        checker._ordinary_ci(root, event, new_acceptance=False)
    assert fetches == []
    assert checker.main(['--root', str(root), '--gate6-carry']) == 0
    assert 'TECHNICAL ONLY; final delegation NOT CHECKED' in capsys.readouterr().out
    assert fetches == []
    assert ('PR192 strikeout extension: DELEGATED VERIFIED; not new PR187/191 acceptance; '
            'not a personal signature') in checker.validate_gate6_ci_event(root, event)
    assert fetches == ['192']
    reference = json.loads((root / checker._STRIKEOUT_REFERENCE_PATH).read_bytes())
    # 正式mergeと候補の二系統を独立に合流検査し、偽のbase→候補祖先を要求しない。
    assert ['merge-base', '--is-ancestor', event.base_sha,
            reference['candidate_revision']] not in calls
    for prior in (event.base_sha, reference['candidate_revision']):
        assert ['merge-base', '--is-ancestor', prior, event.head_sha] in calls


@pytest.mark.parametrize('mutation', [
    'old-case', 'old-row', 'missing-case', 'duplicate-case', 'unknown-case', 'old-rowref',
    'new-case', 'new-history', 'new-flag', 'new-row', 'new-rowref', 'mapping', 'count',
    'handoff', 'descriptor', 'game-end', 'record', 'schema', 'ordinary-vectors',
    'case-source', 'case-schema', 'reference', 'joint-source-reference', 'projection',
    'pin', 'purpose', 'consumer', 'pin-extra', 'delete-reference', 'dirty-checker',
    'dirty-tests', 'joint-source-declaration', 'joint-expectation-declaration',
])
def test_strikeout_extension_rejects_every_scope_and_joint_reference_change(
    strikeout_extension_fixture: Any, mutation: str,
) -> None:
    """旧値/新有限値/原典/用途の改竄は自己一致や合成公開proofで救済しない。"""
    root, _, event, _, fetches, _, _ = strikeout_extension_fixture
    path = root / checker.STATE_TRANSITION_CONTRACT_PATH
    contract = json.loads(path.read_bytes())
    if mutation in {'old-case', 'old-row', 'missing-case', 'duplicate-case', 'unknown-case',
                    'old-rowref', 'new-case', 'new-history', 'new-flag', 'new-row',
                    'new-rowref', 'joint-source-reference', 'joint-source-declaration'}:
        if mutation == 'old-case':
            contract['cases'][0]['expected']['plateAppearanceEnded'] = True
        elif mutation == 'old-row':
            contract['matrixRows'][0]['remarks'] += 'tampered'
        elif mutation == 'missing-case':
            contract['cases'].pop()
        elif mutation == 'duplicate-case':
            contract['cases'].append(copy.deepcopy(contract['cases'][134]))
        elif mutation == 'unknown-case':
            contract['cases'][-1]['caseId'] += '-unknown'
        elif mutation in {'old-rowref', 'new-rowref'}:
            index = 0 if mutation == 'old-rowref' else 51
            contract['mustOperationCoverage']['mappings'][0]['rowRefs'].pop(index)
        elif mutation == 'new-row':
            contract['matrixRows'][51]['remarks'] += 'tampered'
        elif mutation == 'new-history':
            contract['cases'][134]['historyInput']['before']['stateFields']['state.outs'] = 1
        elif mutation == 'new-flag':
            flags = contract['cases'][134]['expected']['statFlags']
            key = next(iter(flags))
            flags[key] = not flags[key]
        else:
            contract['cases'][134]['expected']['plateAppearanceEnded'] = False
        _write_t1_append_json(path, contract)
        if mutation in {'joint-source-reference', 'joint-source-declaration'}:
            reference_path = root / checker._STRIKEOUT_REFERENCE_PATH
            reference = json.loads(reference_path.read_bytes())
            reference['files'][str(checker.STATE_TRANSITION_CONTRACT_PATH)]['after_sha256'] = (
                hashlib.sha256(path.read_bytes()).hexdigest())
            _write_t1_append_json(reference_path, reference)
            if mutation == 'joint-source-declaration':
                frozen_path = root / 'contracts/tenant_boundary/frozen-inputs.json'
                frozen = json.loads(frozen_path.read_bytes())
                frozen['frozen_inputs']['pr192_ordinary_extension_reference_revision']['value'] = (
                    reference['candidate_revision'])
                _write_t1_append_json(frozen_path, frozen)
    elif mutation in {'mapping', 'count', 'handoff', 'descriptor', 'game-end', 'case-source',
                      'case-schema', 'record', 'schema', 'ordinary-vectors'}:
        paths = {
            'mapping': checker._STRIKEOUT_CHANGED_PATHS[1],
            'count': checker._STRIKEOUT_CHANGED_PATHS[2],
            'handoff': checker._STRIKEOUT_CHANGED_PATHS[3],
            'descriptor': 'contracts/state-transition/input_axes_descriptor_v1.json',
            'game-end': str(checker.GAME_END_CONTRACT_PATH),
            'case-source': 'contracts/state-transition/strikeout_pitch_cases_v1.json',
            'case-schema': 'contracts/state-transition/strikeout_pitch_schema_v1.json',
            'record': str(checker.GATE6_ORDINARY_PATH),
            'schema': str(checker.GATE6_ORDINARY_SCHEMA_PATH),
            'ordinary-vectors': 'contracts/state-transition/ordinary_pitch_vectors_v1.json',
        }
        target = root / paths[mutation]
        value = json.loads(target.read_bytes())
        value['unknown-extension'] = True
        _write_t1_append_json(target, value)
    elif mutation in {'reference', 'projection', 'delete-reference'}:
        target = root / checker._STRIKEOUT_REFERENCE_PATH
        if mutation == 'delete-reference':
            target.unlink()
        else:
            value = json.loads(target.read_bytes())
            if mutation == 'projection':
                value['finite_extension']['projection_operations'][0]['before_length'] = 0
            else:
                value['formal_base_revision'] = value['terminal_accepted_revision']
            _write_t1_append_json(target, value)
    elif mutation in {'dirty-checker', 'dirty-tests'}:
        target = root / ('scripts/check_human_review_signature.py' if mutation == 'dirty-checker'
                         else 'tests/test_human_review_signature.py')
        target.write_text(target.read_text() + '\n# 合成未保存差分\n')
    elif mutation == 'joint-expectation-declaration':
        target = root / 'tests/fixtures/pr192_tenant_source_expected_v1.json'
        value = json.loads(target.read_bytes())
        value['formal_base_revision'] = '0' * 40
        _write_t1_append_json(target, value)
        target = root / 'contracts/tenant_boundary/frozen-inputs.json'
        value = json.loads(target.read_bytes())
        value['frozen_inputs']['pr192_source_expectation_revision']['value'] = (
            value['frozen_inputs']['pr192_source_registration_revision']['value'])
        _write_t1_append_json(target, value)
    else:
        target = root / 'contracts/tenant_boundary/frozen-inputs.json'
        value = json.loads(target.read_bytes())
        entry = value['frozen_inputs']['pr192_ordinary_extension_reference_revision']
        if mutation == 'pin':
            entry['value'] = '0' * 40
        elif mutation == 'purpose':
            entry['purpose'] += 'general approval'
        elif mutation == 'consumer':
            entry['sources'] = []
        else:
            entry['extra'] = True
        _write_t1_append_json(target, value)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mutation', ['pr', 'branch', 'repository', 'head-repository',
                                      'base', 'head'])
def test_strikeout_extension_rejects_other_actual_event(
    strikeout_extension_fixture: Any, mutation: str,
) -> None:
    """PR192の権限を別PR・別系統・別基線へ広げない。"""
    root, guard, event, _, fetches, _, _ = strikeout_extension_fixture
    fields = dict(vars(event))
    key, value = {'pr': ('number', 194), 'branch': ('head_branch', 'feature/unknown'),
                  'repository': ('repository', 'other/pitchlog'),
                  'head-repository': ('head_repository', 'other/pitchlog'),
                  'base': ('base_sha', '0' * 40), 'head': ('head_sha', '0' * 40)}[mutation]
    fields[key] = value
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_strikeout_ci(root, guard.PullRequestEvent(**fields))
    assert fetches == []


@pytest.mark.parametrize('mutation', [
    'missing', 'author-approved', 'same-author', 'non-independent', 'p0', 'p1',
    'report-head', 'head', 'base', 'diff', 'paths', 'authority', 'api',
])
def test_strikeout_extension_requires_final_independent_public_confirmation(
    strikeout_extension_fixture: Any, mutation: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定数学の一致だけで本人署名・最終独立PO証拠を成立扱いにしない。"""
    root, guard, event, comment, _, _, _ = strikeout_extension_fixture
    evidence = json.loads(comment['body'][len(guard.DELEGATION_COMMENT_MARKER):])
    if mutation in {'missing', 'author-approved'}:
        comment['body'] = '' if mutation == 'missing' else 'author approved'
    elif mutation == 'same-author':
        evidence['candidate_agents'].append(evidence['reviewer_agent'])
    elif mutation == 'non-independent':
        evidence['independent'] = False
    elif mutation in {'p0', 'p1'}:
        evidence['findings'] = [{'severity': mutation.upper(), 'resolved': False,
                                 'detail': '合成未解消'}]
    elif mutation == 'report-head':
        evidence['report']['reviewed_head'] = '0' * 40
    elif mutation in {'head', 'base'}:
        evidence[mutation] = '0' * 40
    elif mutation in {'diff', 'authority'}:
        evidence[{'diff': 'diff_sha256', 'authority': 'authority_sha256'}[mutation]] = '0' * 64
    elif mutation == 'paths':
        evidence['paths'] = []
    else:
        def fail(_: str) -> Any:
            raise guard.GuardError('合成192公開API故障')
        monkeypatch.setattr(guard, '_fetch_delegation_comment', fail)
    if mutation not in {'missing', 'author-approved'}:
        comment['body'] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)


@pytest.mark.parametrize('relation', ['terminal-base', 'terminal-candidate', 'base-reference',
                                      'candidate-reference', 'reference-head', 'base-head',
                                      'candidate-head'])
def test_strikeout_extension_requires_real_two_parent_convergence(
    strikeout_extension_fixture: Any, monkeypatch: pytest.MonkeyPatch, relation: str,
) -> None:
    """並行源をbase→候補と偽らず、個別の真正祖先/実HEAD合流を必須にする。"""
    root, _, event, _, fetches, _, _ = strikeout_extension_fixture
    reference = json.loads((root / checker._STRIKEOUT_REFERENCE_PATH).read_bytes())
    frozen = json.loads((root / 'contracts/tenant_boundary/frozen-inputs.json').read_bytes())
    pin = frozen['frozen_inputs']['pr192_ordinary_extension_reference_revision']['value']
    pairs = {
        'terminal-base': (reference['terminal_accepted_revision'], event.base_sha),
        'terminal-candidate': (reference['terminal_accepted_revision'],
                               reference['candidate_revision']),
        'base-reference': (event.base_sha, pin),
        'candidate-reference': (reference['candidate_revision'], pin),
        'reference-head': (pin, event.head_sha),
        'base-head': (event.base_sha, event.head_sha),
        'candidate-head': (reference['candidate_revision'], event.head_sha),
    }
    original = checker._carry_git_bytes
    def read(repository: Path, args: list[str]) -> bytes:
        if args == ['merge-base', '--is-ancestor', *pairs[relation]]:
            raise checker.HumanReviewSignatureRecordError('合成192非祖先')
        return original(repository, args)
    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='非祖先'):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.fixture
def batted_carry_fixture(ordinary_fixture: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """実正式baseのGit原本と合成196公開proofを供給し、実受理とは区別する。"""
    root, guard, prior, _, _, calls, comment, fetches = ordinary_fixture
    repository = Path(__file__).resolve().parents[1]
    expected = _load_object(repository / 'tests/fixtures/pr196_tenant_source_expected_v1.json')
    revision = expected['formal_base_revision']
    assert type(revision) is str and len(revision) == 40
    base_reader = checker._BattedCarryBaseReader(repository, revision)
    record = base_reader.load_json(checker.GATE6_ORDINARY_PATH, '実base記録')
    paths = {*record['assets'], *checker._ORDINARY_FIXED_INPUTS,
        *checker._ORDINARY_EXECUTION_INPUTS, *checker._STRIKEOUT_EXTENSION_INPUTS,
        *checker._BATTED_METADATA_PATHS,
        str(checker.GATE6_ORDINARY_PATH), str(checker.GATE6_ORDINARY_SCHEMA_PATH),
        'scripts/check_human_review_signature.py',
        'docs/features/mvp-delegated-core-review/policy.json'}
    baseline = {}
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        baseline[path] = base_reader.read_bytes(path)
        target.write_bytes((repository / path).read_bytes())
    # 数学/旧署名は現値から期待を採取せず、実baseを起点に配置する。
    for path in {*record['assets'], *checker._ORDINARY_FIXED_INPUTS,
                 *checker._BATTED_METADATA_PATHS,
                 str(checker.GATE6_ORDINARY_PATH), str(checker.GATE6_ORDINARY_SCHEMA_PATH)}:
        (root / path).write_bytes(baseline[path])
    # 後発197を合成196のhead policyへ持ち込まず、実196 base18の単一追記にする。
    policy_path = root / guard.DELEGATION_POLICY_PATH
    policy = base_reader.load_json(guard.DELEGATION_POLICY_PATH, '安打base policy')
    policy['targets'].append({'pr': 196, 'branch': 'feature/mvp-batted-hits'})
    _write_t1_append_json(policy_path, policy)
    url = 'https://github.com/masaki1025/pitchlog/pull/196#issuecomment-196'
    event = guard.PullRequestEvent(revision, prior.head_sha, 'PO-DELEGATION-EVIDENCE: ' + url,
        196, prior.repository, prior.head_repository, 'feature/mvp-batted-hits')
    evidence = {'authority_sha256': hashlib.sha256(
        (root / guard.DELEGATION_POLICY_PATH).read_bytes()).hexdigest(),
        'pr': 196, 'base': event.base_sha, 'head': event.head_sha,
        'diff_sha256': guard._delegation_diff(root, event),
        'paths': guard.changed_paths(root, event.base_sha, event.head_sha),
        'reviewer_agent': 'batted-carry-nonauthor', 'candidate_agents': ['batted-carry-author'],
        'independent': True, 'verdict': 'approved', 'findings': [],
        'report': {'task': 'batted-carry-nonauthor', 'reviewed_head': event.head_sha,
                   'text': '合成196proofによる局所試験。実公開確認・本人署名ではない。'}}
    comment.clear()
    comment.update({'id': 196, 'html_url': url,
        'issue_url': 'https://api.github.com/repos/masaki1025/pitchlog/issues/196',
        'author_association': 'OWNER', 'user': {'login': 'masaki1025'},
        'body': guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)})
    committed = {path.relative_to(root).as_posix(): path.read_bytes()
                 for path in root.rglob('*') if path.is_file() and path.name != '.git'}
    original = checker._carry_git_bytes

    def read(repository: Path, args: list[str]) -> bytes:
        if args[0] == 'show':
            commit, _, path = args[1].partition(':')
            if commit == event.base_sha and path in baseline:
                return baseline[path]
            if commit == event.head_sha:
                if path not in committed:
                    raise checker.HumanReviewSignatureRecordError('合成196head欠落')
                return committed[path]
        return original(repository, args)

    monkeypatch.setattr(checker, '_carry_git_bytes', read)
    return root, guard, event, comment, fetches, baseline, committed, calls


def test_batted_carry_checks_real_base_history_and_own_public_proof(
    batted_carry_fixture: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧generic失敗を保持し、192 eventを合成せず196の実base全bodyを通す。"""
    root, _, event, _, fetches, _, _, _ = batted_carry_fixture
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='base数学9資産'):
        checker._ordinary_ci(root, event, new_acceptance=False)
    assert fetches == []

    def forbidden(*_: object, **__: object) -> Any:
        raise AssertionError('PR192 CI eventへ変換してはならない')

    monkeypatch.setattr(checker, '_ordinary_strikeout_ci', forbidden)
    assert 'PR196 carry: HISTORICAL ordinary33/PR191/PR192 PRESERVED' in (
        checker.validate_gate6_ci_event(root, event))
    assert fetches == ['196']


_BATTED_CARRY_TEST_PATHS = sorted({
    *_ordinary_test_materials(REPOSITORY_ROOT)[0]['assets'],
    str(checker.GATE6_ORDINARY_PATH), str(checker.GATE6_ORDINARY_SCHEMA_PATH),
    str(checker.ORDINARY_PINS_PATH), str(checker._TERMINAL_REFERENCE_PATH),
    str(checker._STRIKEOUT_REFERENCE_PATH),
    'tests/fixtures/pr192_tenant_source_expected_v1.json',
    'contracts/state-transition/input_axes_descriptor_v1.json',
})


@pytest.mark.parametrize('path', _BATTED_CARRY_TEST_PATHS)
@pytest.mark.parametrize('location', ['base', 'head', 'missing-base'])
def test_batted_carry_rejects_every_protected_change(
    batted_carry_fixture: Any, path: str, location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """古い署名値を更新せずbase数学改変・head差分・原典欠落を全byteで拒否する。"""
    root, _, event, _, fetches, baseline, _, _ = batted_carry_fixture
    if location == 'base':
        baseline[path] += b' '
    elif location == 'head':
        (root / path).write_bytes((root / path).read_bytes() + b' ')
    else:
        original = checker._carry_git_bytes

        def missing(repository: Path, args: list[str]) -> bytes:
            if args == ['show', event.base_sha + ':' + path]:
                raise checker.HumanReviewSignatureRecordError('実base原典欠落')
            return original(repository, args)

        monkeypatch.setattr(checker, '_carry_git_bytes', missing)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('key', sorted(checker._BATTED_CARRY_FROZEN_KEYS))
def test_batted_carry_rejects_changed_historical_registration(
    batted_carry_fixture: Any, key: str,
) -> None:
    """後発登録全体ではなく旧191/192の必要entry全値をbaseへ固定する。"""
    root, _, event, _, fetches, _, _, _ = batted_carry_fixture
    path = root / 'contracts/tenant_boundary/frozen-inputs.json'
    value = _load_object(path)
    value['frozen_inputs'][key]['purpose'] += ' altered'
    _write_t1_append_json(path, value)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('change', ['pr', 'bool-pr', 'branch', 'repository', 'fork',
    'base', 'head', 'nonancestor', 'base-head', 'checkout'])
def test_batted_carry_rejects_foreign_event_or_git_binding(
    batted_carry_fixture: Any, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    """専用入口を別PR/branch/repoや自己申告版へ一般化しない。"""
    root, guard, event, _, fetches, _, _, _ = batted_carry_fixture
    fields = vars(event).copy()
    if change == 'pr':
        fields['number'] = 197
    elif change == 'bool-pr':
        fields['number'] = True
    elif change == 'branch':
        fields['head_branch'] = 'feature/unapproved'
    elif change == 'repository':
        fields['repository'] = 'other/pitchlog'
    elif change == 'fork':
        fields['head_repository'] = 'other/pitchlog'
    elif change in {'base', 'head'}:
        fields[change + '_sha'] = '0' * 40
    else:
        original = checker._carry_git_bytes

        def broken(repository: Path, args: list[str]) -> bytes:
            if (change == 'nonancestor' and args[:2] == ['merge-base', '--is-ancestor']
                    or change == 'base-head' and args == [
                        'merge-base', '--is-ancestor', event.base_sha, event.head_sha]
                    or change == 'checkout' and args == ['rev-parse', 'HEAD']):
                raise checker.HumanReviewSignatureRecordError('版結合拒否')
            return original(repository, args)

        monkeypatch.setattr(checker, '_carry_git_bytes', broken)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_batted_carry_ci(root, guard.PullRequestEvent(**fields))
    if change == 'pr':
        with pytest.raises(checker.HumanReviewSignatureRecordError):
            checker.validate_gate6_ci_event(root, guard.PullRequestEvent(**fields))
    assert fetches == []


@pytest.mark.parametrize('change', ['head', 'base', 'pr', 'self-review', 'P1',
    'publisher', 'missing', 'api'])
def test_batted_carry_requires_own_final_public_evidence(
    batted_carry_fixture: Any, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    """歴史bodyの成功で公開proof不正を隠したりlocalへfallbackしない。"""
    root, guard, event, comment, fetches, _, _, _ = batted_carry_fixture
    evidence = json.loads(comment['body'][len(guard.DELEGATION_COMMENT_MARKER):])
    if change in {'head', 'base'}:
        evidence[change] = '0' * 40
    elif change == 'pr':
        evidence['pr'] = 192
    elif change == 'self-review':
        evidence['candidate_agents'].append(evidence['reviewer_agent'])
    elif change == 'P1':
        evidence['findings'] = [{'severity': 'P1', 'resolved': False, 'detail': '未解消'}]
    elif change == 'publisher':
        comment['user']['login'] = 'other'
    elif change == 'missing':
        event = guard.PullRequestEvent(**{**vars(event), 'body': ''})
    else:
        def fail(_: str) -> Any:
            raise guard.GuardError('公開API取得故障')
        monkeypatch.setattr(guard, '_fetch_delegation_comment', fail)
    comment['body'] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    with pytest.raises(checker.HumanReviewSignatureRecordError) as error:
        checker.validate_gate6_ci_event(root, event)
    if change not in {'missing', 'api'}:
        assert fetches == ['196'], str(error.value)


@pytest.mark.parametrize('path', _BATTED_CARRY_TEST_PATHS)
def test_batted_carry_rejects_joint_base_and_head_changes(
    batted_carry_fixture: Any, path: str,
) -> None:
    """base/headを同時追随させても旧受理の固定数学・原典へ連動変更を通さない。"""
    root, _, event, _, fetches, baseline, _, _ = batted_carry_fixture
    baseline[path] += b' '
    (root / path).write_bytes(baseline[path])
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.fixture
def batted_metadata_fixture(batted_carry_fixture: Any) -> Any:
    """独立採用済みmetadata5の原本を置き、実base/旧数学を変えない。"""
    root, _, _, _, _, _, committed, _ = batted_carry_fixture
    repository = Path(__file__).resolve().parents[1]
    for path in checker._BATTED_METADATA_PATHS:
        raw = (repository / path).read_bytes()
        (root / path).write_bytes(raw)
        committed[path] = raw
    _write_batted_handoff_metadata(root)
    committed[checker._BATTED_HANDOFF_PATH] = (root / checker._BATTED_HANDOFF_PATH).read_bytes()
    return batted_carry_fixture


def test_batted_metadata_local_and_actual_196_modes(
    batted_metadata_fixture: Any, capsys: pytest.CaptureFixture[str],
) -> None:
    """localは閉射影のみ、実196 modeだけが最終公開proofを検査する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    assert checker.main(['--root', str(root), '--gate6-carry']) == 0
    assert 'TECHNICAL ONLY; final delegation NOT CHECKED' in capsys.readouterr().out
    assert fetches == []
    assert 'DELEGATED VERIFIED' in checker.validate_gate6_ci_event(root, event)
    assert fetches == ['196']


def _write_batted_metadata_counterfactual(root: Path, descriptor: dict[str, Any]) -> None:
    """未知差分でも公式digestと4参照を追随し、hashだけの拒否へ逃がさない。"""
    path = root / checker._BATTED_METADATA_DESCRIPTOR
    old_digest = _load_object(path)['digest']
    limit = checker.descriptor_checker.load_descriptor_criteria(
        _load_object(path)).safe_integer_limit
    canonical = checker.descriptor_checker.canonicalize_json(
        {k: v for k, v in descriptor.items() if k != 'digest'}, limit)
    descriptor['digest'] = 'sha256:' + hashlib.sha256(canonical).hexdigest()
    _write_t1_append_json(path, descriptor)
    for name in checker._BATTED_METADATA_BINDINGS:
        target = root / name
        old = json.dumps(old_digest).encode()
        assert target.read_bytes().count(old) == 1
        target.write_bytes(target.read_bytes().replace(
            old, json.dumps(descriptor['digest']).encode(), 1))

    _write_batted_handoff_metadata(root)


@pytest.mark.parametrize('mutation', ['third-word', 'missing-word', 'duplicate-word',
    'navigation-order', 'other-source', 'criteria', 'top-field', 'old-history',
    'extra-record', 'missing-record', 'record-pr', 'record-series', 'record-prior',
    'record-new', 'record-before', 'record-after', 'extra-change', 'unapproved-fact',
    'unapproved-by', 'human-by', 'date', 'record-unknown'])
@pytest.mark.parametrize('mode', ['local', 'ci'])
def test_batted_metadata_rejects_hash_following_unknown_changes(
    batted_metadata_fixture: Any, mutation: str, mode: str,
) -> None:
    """2語/1record以外は全参照digestが自己整合してもlocal/CI双方で閉拒否する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    descriptor = _load_object(root / checker._BATTED_METADATA_DESCRIPTOR)
    declaration = descriptor['freezeBaseline']
    record = declaration['history'][-1]
    audit = declaration['scope']['sourceLiteralAudit']['permittedComparisonLiteralsBySource']
    navigation = audit['scripts/check_input_axes_descriptor.py'][
        'json-object-member-name-used-only-for-navigation']
    if mutation == 'third-word':
        navigation.append('unknown-keyword')
    elif mutation == 'missing-word':
        navigation.remove('allOf')
    elif mutation == 'duplicate-word':
        navigation.append('anyOf')
    elif mutation == 'navigation-order':
        navigation.reverse()
    elif mutation == 'other-source':
        audit['scripts/check_gap_register.py'][
            'json-object-member-name-used-only-for-navigation'].append('unknown')
    elif mutation == 'criteria':
        declaration['criteria']['gapRegister']['schemaVersion'] = 2
    elif mutation == 'top-field':
        descriptor['unknown'] = True
    elif mutation == 'old-history':
        declaration['history'][0]['fact'] += ' changed'
    elif mutation == 'extra-record':
        declaration['history'].append(copy.deepcopy(record))
    elif mutation == 'missing-record':
        declaration['history'].pop()
    elif mutation == 'record-pr':
        record['acceptanceId'] = 'masaki1025/pitchlog#197'
    elif mutation == 'record-series':
        record['series'] = 'unknown'
    elif mutation == 'record-prior':
        record['priorIdentity']['values'][0]['identity'] = 'sha256:' + '0' * 64
    elif mutation == 'record-new':
        record['newIdentity']['values'][0]['identity'] = 'sha256:' + '0' * 64
    elif mutation == 'record-before':
        record['changes'][0]['before']['value']['identityCriterionId'] = 'unknown'
    elif mutation == 'record-after':
        record['changes'][0]['after']['value']['identityCriterionId'] = 'unknown'
    elif mutation == 'extra-change':
        record['changes'].append(copy.deepcopy(record['changes'][0]))
    elif mutation == 'unapproved-fact':
        record['fact'] = '未承認(PR #196 のレビュー待ち)'
    elif mutation == 'unapproved-by':
        record['approvedBy'] = '未承認(PR #196 のレビュー待ち)'
    elif mutation == 'human-by':
        record['approvedBy'] = '山田正輝'
    elif mutation == 'date':
        record['approvedDate'] = '2026/11/05'
    else:
        record['unknown'] = True
    _write_batted_metadata_counterfactual(root, descriptor)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('path', sorted(checker._BATTED_METADATA_BINDINGS))
@pytest.mark.parametrize('mutation', ['other-field', 'missing-reference', 'wrong-reference',
    'formatting', 'dirty-head'])
def test_batted_metadata_rejects_dependency_delta_beyond_exact_one(
    batted_metadata_fixture: Any, path: str, mutation: str,
) -> None:
    """subject2/schema2の指定const以外は全JSON値と元byte書式を保持する。"""
    root, _, event, _, fetches, _, committed, _ = batted_metadata_fixture
    target = root / path
    value = _load_object(target)
    if mutation in {'missing-reference', 'wrong-reference'}:
        parent = value
        pointer = checker._BATTED_METADATA_BINDINGS[path]
        for key in pointer[:-1]:
            parent = parent[key]
        if mutation == 'missing-reference':
            del parent[pointer[-1]]
        else:
            parent[pointer[-1]] = 'sha256:' + '0' * 64
        _write_t1_append_json(target, value)
    elif mutation == 'other-field':
        value['unknown'] = True
        _write_t1_append_json(target, value)
    elif mutation == 'formatting':
        target.write_bytes(target.read_bytes() + b' ')
    else:
        committed[path] += b' '
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
def test_batted_metadata_rejects_replayed_third_navigation_word(
    batted_metadata_fixture: Any, mode: str,
) -> None:
    """engine replay/全identity/digest/4参照が正しくても第三語を有限層で拒否する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    descriptor = _load_object(root / checker._BATTED_METADATA_DESCRIPTOR)
    declaration = descriptor['freezeBaseline']
    navigation = declaration['scope']['sourceLiteralAudit'][
        'permittedComparisonLiteralsBySource']['scripts/check_input_axes_descriptor.py'][
            'json-object-member-name-used-only-for-navigation']
    navigation.append('unapproved-keyword')
    record = declaration['history'][-1]
    record['changes'][0]['after']['value'] = copy.deepcopy(declaration['scope'])
    engine = checker.descriptor_checker.freeze_checker
    record['newIdentity']['values'] = engine.current_identities(declaration)
    prior = checker._BattedCarryBaseReader(root, event.base_sha).load_json(
        checker._BATTED_METADATA_DESCRIPTOR, '実base')['freezeBaseline']
    assert engine.validate_append_only_transition(declaration, prior) == ('freezeDefinition',)
    _write_batted_metadata_counterfactual(root, descriptor)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('side', ['before', 'after'])
@pytest.mark.parametrize(('path', 'value'), [
    (('engineExpectedValues', 'schemaVersion'), True),
    (('engineExpectedValues', 'schemaVersion'), False),
    (('engineExpectedValues', 'schemaVersion'), 0),
    (('selectionRule', 'knownDirectComparisonDispositions', 0, 'observedValue'), True),
    (('selectionRule', 'knownDirectComparisonDispositions', 0, 'observedValue'), False),
    (('selectionRule', 'knownDirectComparisonDispositions', 0, 'observedValue'), 0),
])
@pytest.mark.parametrize('mode', ['local', 'ci'])
def test_batted_metadata_rejects_record_scope_leaf_type_confusion(
    batted_metadata_fixture: Any, side: str, path: tuple[Any, ...], value: Any, mode: str,
) -> None:
    """実scopeの単一leaf型混同をdigest/全4参照追随後も厳格に拒否する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    descriptor = _load_object(root / checker._BATTED_METADATA_DESCRIPTOR)
    declaration = descriptor['freezeBaseline']
    change = declaration['history'][-1]['changes'][0]
    target = change[side]['value']
    for key in path[:-1]:
        target = target[key]
    assert type(target[path[-1]]) is int
    target[path[-1]] = value
    if side == 'before' and path == ('engineExpectedValues', 'schemaVersion') and value is True:
        prior = checker._BattedCarryBaseReader(root, event.base_sha).load_json(
            checker._BATTED_METADATA_DESCRIPTOR, '実base')['freezeBaseline']
        assert checker.descriptor_checker.freeze_checker.validate_append_only_transition(
            declaration, prior) == ('freezeDefinition',)
    # before反例は全prior/new identityが真正。afterも真正identityを保持し、
    # record内1leafとdescriptor digest/参照だけを変える。
    _write_batted_metadata_counterfactual(root, descriptor)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize(('path', 'left', 'right'), [
    (('engineExpectedValues', 'schemaVersion'), True, 1),
    (('engineExpectedValues', 'schemaVersion'), False, 0),
    (('selectionRule', 'knownDirectComparisonDispositions', 0, 'observedValue'), False, 0),
])
def test_batted_metadata_scope_serialization_distinguishes_python_equal_types(
    path: tuple[Any, ...], left: Any, right: Any,
) -> None:
    """実scope形の1leafでPython同値のbool/intを厳格JSON比較が分離する。"""
    descriptor = _load_object(REPOSITORY_ROOT / checker._BATTED_METADATA_DESCRIPTOR)
    before = descriptor['freezeBaseline']['history'][-1]['changes'][0]['before']['value']
    a, b = copy.deepcopy(before), copy.deepcopy(before)
    target_a, target_b = a, b
    for key in path[:-1]:
        target_a, target_b = target_a[key], target_b[key]
    target_a[path[-1]], target_b[path[-1]] = left, right
    # False/0は境界比較の反例。元の採用scopeに0/falseがあったとは主張しない。
    assert a == b
    assert checker._compact_json(a) != checker._compact_json(b)



def _write_batted_handoff_metadata(root: Path) -> None:
    """固定base由来のpath/version/orderを保持し、fixtureの実3raw hashだけ追随する。"""
    path = root / checker._BATTED_HANDOFF_PATH
    handoff = _load_object(path)
    for entry in handoff['artifacts']:
        entry['digest'] = 'sha256:' + hashlib.sha256(
            (root / entry['path']).read_bytes()).hexdigest()
    _write_t1_append_json(path, handoff)


@pytest.mark.parametrize('mode', ['local', 'ci'])
def test_batted_handoff_rejects_stale_digest_metadata(
    batted_metadata_fixture: Any, mode: str,
) -> None:
    """R5 metadata5だけ新しくhandoffが旧値のままなら更新漏れを拒否する。"""
    root, _, event, _, fetches, baseline, _, _ = batted_metadata_fixture
    (root / checker._BATTED_HANDOFF_PATH).write_bytes(baseline[checker._BATTED_HANDOFF_PATH])
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='handoff'):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
@pytest.mark.parametrize('mutation', ['digest0', 'digest1', 'digest2', 'path', 'version',
    'order', 'duplicate', 'extra', 'missing', 'handoff-version', 'other-field',
    'typed-field', 'formatting'])
def test_batted_handoff_rejects_non_digest_changes(
    batted_metadata_fixture: Any, mutation: str, mode: str,
) -> None:
    """正しい3digestが揃っていてもpath/version/order/全他fieldはbaseから変えない。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    path = root / checker._BATTED_HANDOFF_PATH
    document = _load_object(path)
    if mutation.startswith('digest'):
        document['artifacts'][int(mutation[-1])]['digest'] = 'sha256:' + '0' * 64
    elif mutation == 'path':
        document['artifacts'][0]['path'] = (
            'contracts/state-transition/ordinary_pitch_vectors_v1.json')
        document['artifacts'][0]['digest'] = 'sha256:' + hashlib.sha256(
            (root / document['artifacts'][0]['path']).read_bytes()).hexdigest()
    elif mutation == 'version':
        document['artifacts'][0]['version'] = 'unapproved_v2'
    elif mutation == 'order':
        document['artifacts'].reverse()
    elif mutation == 'duplicate':
        document['artifacts'][1] = copy.deepcopy(document['artifacts'][0])
    elif mutation == 'extra':
        document['artifacts'].append(copy.deepcopy(document['artifacts'][0]))
    elif mutation == 'missing':
        document['artifacts'].pop()
    elif mutation == 'handoff-version':
        document['handoffVersion'] = 'unapproved_v2'
    elif mutation == 'other-field':
        document['receiverTaskId'] += '-altered'
    elif mutation == 'typed-field':
        assert type(document['consumerBindings'][0]['schemaVersion']) is int
        document['consumerBindings'][0]['schemaVersion'] = True
    else:
        path.write_bytes(path.read_bytes() + b' ')
    if mutation != 'formatting':
        _write_t1_append_json(path, document)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='handoff'):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
@pytest.mark.parametrize('math_path', [str(checker.STATE_TRANSITION_CONTRACT_PATH),
    'contracts/state-transition/ordinary_pitch_vectors_v1.json'])
def test_batted_handoff_digest_following_cannot_change_mathematics(
    batted_metadata_fixture: Any, mode: str, math_path: str,
) -> None:
    """実raw SHAを正しく追随しても別の数学/期待変更を許可へ変換しない。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    path = root / math_path
    document = _load_object(path)
    if math_path == str(checker.STATE_TRANSITION_CONTRACT_PATH):
        before = document['cases'][0]['expected']['plateAppearanceEnded']
        assert type(before) is bool
        document['cases'][0]['expected']['plateAppearanceEnded'] = not before
    else:
        before = document['cases'][0]['expected']['value']['plateAppearanceEnded']
        assert type(before) is bool
        document['cases'][0]['expected']['value']['plateAppearanceEnded'] = not before
    _write_t1_append_json(path, document)
    _write_batted_handoff_metadata(root)
    # handoffは正しく導出済み。数学拒否は元の有限metadata/歴史bodyが担う。
    base = checker._BattedCarryBaseReader(root, event.base_sha)
    assert checker._batted_handoff_delta(root, base) is None
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


def test_batted_handoff_requires_committed_head_bytes(batted_metadata_fixture: Any) -> None:
    """正しいworktreeのhandoffでも最終headに未反映なら公開proofより先に拒否する。"""
    root, _, event, _, fetches, _, committed, _ = batted_metadata_fixture
    committed[checker._BATTED_HANDOFF_PATH] += b' '
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
def test_batted_handoff_rejects_duplicate_json_member(
    batted_metadata_fixture: Any, mode: str,
) -> None:
    """JSON通常decoderが同値へ潰す重複memberもbase raw完全比較で拒否する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    path = root / checker._BATTED_HANDOFF_PATH
    raw = path.read_bytes()
    line = next(line for line in raw.splitlines(keepends=True) if b'"handoffVersion"' in line)
    duplicate = raw.replace(line, line + line, 1)
    assert json.loads(raw) == json.loads(duplicate)
    path.write_bytes(duplicate)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='handoff'):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
def test_batted_current_carry_actual_file_authority_change_is_rejected(
    batted_metadata_fixture: Any, mode: str,
) -> None:
    """decoder注入なしの実current carry改竄も公開入口で拒否する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    path = root / checker.GATE6_CARRY_PATH
    document = _load_object(path)
    document['authority']['sha256'] = '0' * 64
    _write_t1_append_json(path, document)
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='current旧固定byte'):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
@pytest.mark.parametrize('path', sorted(checker._ORDINARY_FIXED_INPUTS
    - checker._BATTED_PROJECTION_PATHS))
def test_batted_current_legacy_documents_are_all_raw_frozen(
    batted_metadata_fixture: Any, mode: str, path: str,
) -> None:
    """actual headの旧9文書は署名/日付/sheet/schema/record全byteで保持する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    target = root / path
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(checker.HumanReviewSignatureRecordError, match='current旧固定byte'):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert fetches == []


@pytest.mark.parametrize('mode', ['local', 'ci'])
@pytest.mark.parametrize('mutated', [False, True])
def test_batted_current_carry_existing_decoder_boundary_is_observed(
    batted_metadata_fixture: Any, monkeypatch: pytest.MonkeyPatch, mode: str, mutated: bool,
) -> None:
    """現subjectを古くせず、既carry読取境界の正例/変異だけを実公開入口で検査する。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    path = root / checker.GATE6_CARRY_PATH
    document = _load_object(path)
    if mutated:
        document['boundary']['personalReviewClaimed'] = True
    original = checker.descriptor_checker.load_json
    observed = []

    def read(candidate: Path, label: str) -> object:
        if candidate == path:
            observed.append(candidate)
            return copy.deepcopy(document)
        return original(candidate, label)

    monkeypatch.setattr(checker.descriptor_checker, 'load_json', read)
    if mutated:
        with pytest.raises(checker.HumanReviewSignatureRecordError, match='current旧JSON読取値'):
            if mode == 'local':
                checker.validate_gate6_subject_carry(root)
            else:
                checker.validate_gate6_ci_event(root, event)
        assert fetches == []
    elif mode == 'local':
        checker.validate_gate6_subject_carry(root)
        assert fetches == []
    else:
        assert 'DELEGATED VERIFIED' in checker.validate_gate6_ci_event(root, event)
        assert fetches == ['196']
    assert observed


@pytest.mark.parametrize('mode', ['local', 'ci'])
@pytest.mark.parametrize('path', sorted(checker._BATTED_PROJECTION_PATHS))
def test_batted_projection_preserves_actual_metadata_decoder_boundary(
    batted_metadata_fixture: Any, monkeypatch: pytest.MonkeyPatch, mode: str, path: str,
) -> None:
    """rawが正しくてもmetadata既読取値の変異を無視してbaseへ射影しない。"""
    root, _, event, _, fetches, _, _, _ = batted_metadata_fixture
    target = root / path
    document = json.loads(target.read_bytes())
    document['unauthorized-decoded-field'] = True
    original = checker.descriptor_checker.load_json
    observed = []

    def read(candidate: Path, label: str) -> object:
        if candidate == target:
            observed.append(candidate)
            return copy.deepcopy(document)
        return original(candidate, label)

    monkeypatch.setattr(checker.descriptor_checker, 'load_json', read)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        if mode == 'local':
            checker.validate_gate6_subject_carry(root)
        else:
            checker.validate_gate6_ci_event(root, event)
    assert observed
    assert fetches == []


@pytest.fixture
def pr197_gate6_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Any, Any, dict[str, Any]]:
    """固定51bと実Git headを隔離し、公開commentだけを合成する。"""
    import subprocess

    root = tmp_path / "pr197"
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", str(REPOSITORY_ROOT), str(root)],
        check=True,
    )
    guard = _load_module("pr197_candidate_core_guard", root / "scripts/core_guard.py")
    monkeypatch.setattr(checker, "_carry_core_guard", lambda _root: guard)
    expected = json.loads(
        (root / "tests/fixtures/pr197_tenant_source_expected_v1.json").read_bytes(),
    )
    base = expected["formal_base_revision"]
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
    ).strip()
    url = "https://github.com/masaki1025/pitchlog/pull/197#issuecomment-197"
    event = guard.PullRequestEvent(
        base, head, "PO-DELEGATION-EVIDENCE: " + url, 197,
        "masaki1025/pitchlog", "masaki1025/pitchlog",
        "feature/mvp-stats-native-foundation",
    )
    _, digest = guard._load_delegation_policy(root, head)
    evidence = {
        "authority_sha256": digest, "pr": 197, "base": base, "head": head,
        "diff_sha256": guard._delegation_diff(root, event),
        "paths": guard.changed_paths(root, base, head),
        "reviewer_agent": "synthetic-pr197-reviewer",
        "candidate_agents": ["synthetic-pr197-author"],
        "independent": True, "verdict": "approved", "findings": [],
        "report": {
            "task": "synthetic-pr197-reviewer", "reviewed_head": head,
            "text": "隔離合成proof。実公開確認・本人署名ではない。",
        },
    }
    comment = {
        "id": 197, "html_url": url,
        "issue_url": "https://api.github.com/repos/masaki1025/pitchlog/issues/197",
        "author_association": "OWNER", "user": {"login": "masaki1025"},
        "body": guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence),
    }
    monkeypatch.setattr(guard, "_fetch_delegation_comment", lambda _id: comment)
    return root, guard, event, comment


def test_pr197_gate6_success_uses_existing_typed_e_and_real_git_event(
    pr197_gate6_candidate: tuple[Path, Any, Any, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧記録を書き換えず51bから数学9/旧49を保ち公開委任を照合する。"""
    root, guard, event, _ = pr197_gate6_candidate
    value = checker.validate_gate6_ci_event(root, event)
    assert "PR197 carry: HISTORICAL ordinary33/PR191/PR192/PR196 PRESERVED" in value
    assert "not a personal signature" in value
    monkeypatch.setattr(guard, "load_pull_request_event", lambda: event)
    assert checker.main(["--root", str(root), "--gate6-carry", "--ci"]) == 0


def test_pr197_formal_ledger_binding_successor_is_exact() -> None:
    """正式台帳の検査器束縛以外を同時変更した候補を拒否する。"""
    import subprocess

    root = REPOSITORY_ROOT
    source_revision = json.loads(
        (root / "tests/fixtures/pr197_tenant_source_expected_v1.json").read_bytes()
    )["source_revision"]
    path = "contracts/authz/frozen-baselines.json"
    source = subprocess.check_output(
        ["git", "show", source_revision + ":" + path], cwd=root,
    )
    head = (root / path).read_bytes()
    head_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
    ).strip()
    checker._pr197_formal_ledger_binding_successor(root, source, head, head_sha)
    for mutation in ("second-code", "extra-history", "changed-reason"):
        altered = json.loads(head)
        if mutation == "second-code":
            altered["implementation_bindings"]["code_assets"][1]["sha256"] = "0" * 64
        elif mutation == "extra-history":
            altered["history"].append(altered["history"][-1])
        else:
            altered["history"][-1]["reason"] += " 未確認"
        with pytest.raises(checker.HumanReviewSignatureRecordError):
            checker._pr197_formal_ledger_binding_successor(
                root, source, (json.dumps(altered, ensure_ascii=False, indent=2) + "\n").encode(),
                head_sha,
            )


@pytest.mark.parametrize("mutation", [
    "wrong-pr", "bool-pr", "wrong-branch", "wrong-repository", "wrong-base",
    "math-worktree", "math-commit", "typed-pin", "typed-and-fixture",
    "typed-new-value",
    "policy-worktree", "ledger-worktree",
    "coreguard-worktree", "unknown-scope", "unknown-math-path", "missing-proof",
    "self-review", "publisher", "unresolved-p1",
])
def test_pr197_gate6_rejects_event_scope_and_public_proof(
    pr197_gate6_candidate: tuple[Path, Any, Any, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """PR番号skipやbase/head同時追随、未知path、署名流用を閉拒否する。"""
    import subprocess

    root, guard, event, comment = pr197_gate6_candidate
    fields = vars(event).copy()
    if mutation == "wrong-pr":
        fields["number"] = 198
    elif mutation == "bool-pr":
        fields["number"] = True
    elif mutation == "wrong-branch":
        fields["head_branch"] = "feature/other"
    elif mutation == "wrong-repository":
        fields["repository"] = "other/pitchlog"
    elif mutation == "wrong-base":
        fields["base_sha"] = event.head_sha
    elif mutation == "math-worktree":
        path = root / "contracts/state-transition/state_transition_contract_v1.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "typed-pin":
        path = root / "contracts/tenant_boundary/frozen-inputs.json"
        value = json.loads(path.read_bytes())
        value["frozen_inputs"]["pr197_expectation_revision"]["value"] = "0" * 40
        path.write_text(json.dumps(value))
    elif mutation == "typed-and-fixture":
        path = root / "contracts/tenant_boundary/frozen-inputs.json"
        value = json.loads(path.read_bytes())
        value["frozen_inputs"]["pr197_expectation_fixture_sha256"]["value"] = "0" * 64
        path.write_text(json.dumps(value))
        fixture = root / "tests/fixtures/pr197_tenant_source_expected_v1.json"
        fixture.write_bytes(fixture.read_bytes() + b" ")
    elif mutation == "typed-new-value":
        path = root / "contracts/tenant_boundary/frozen-inputs.json"
        value = json.loads(path.read_bytes())
        value["frozen_inputs"]["stats_native_old_registry_sha256"]["value"] = "0" * 64
        path.write_text(json.dumps(value))
    elif mutation in {"policy-worktree", "ledger-worktree", "coreguard-worktree"}:
        path = root / {
            "policy-worktree": "docs/features/mvp-delegated-core-review/policy.json",
            "ledger-worktree": "contracts/authz/frozen-baselines.json",
            "coreguard-worktree": "scripts/core_guard.py",
        }[mutation]
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "unknown-scope":
        monkeypatch.setattr(
            checker, "_ORDINARY_FIXED_INPUTS",
            checker._ORDINARY_FIXED_INPUTS | {"contracts/state-transition/unknown.json"},
        )
    elif mutation in {"unknown-math-path", "math-commit"}:
        path = root / (
            "contracts/state-transition/pr197-unknown.json"
            if mutation == "unknown-math-path"
            else "contracts/state-transition/state_transition_contract_v1.json"
        )
        path.write_bytes(path.read_bytes() + b" " if path.exists() else b"{}\n")
        subprocess.run(["git", "-C", str(root), "add", str(path.relative_to(root))], check=True)
        subprocess.run([
            "git", "-C", str(root), "-c", "user.name=Candidate",
            "-c", "user.email=candidate@local.invalid", "commit", "--quiet",
            "-m", "test: 数学未知pathを追加",
        ], check=True)
        fields["head_sha"] = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
        ).strip()
    else:
        evidence = json.loads(comment["body"][len(guard.DELEGATION_COMMENT_MARKER):])
        if mutation == "missing-proof":
            fields["body"] = ""
        elif mutation == "self-review":
            evidence["candidate_agents"].append(evidence["reviewer_agent"])
        elif mutation == "publisher":
            comment["user"]["login"] = "other"
        elif mutation == "unresolved-p1":
            evidence["findings"] = [{"severity": "P1", "resolved": False, "detail": "未解消"}]
        comment["body"] = guard.DELEGATION_COMMENT_MARKER + json.dumps(evidence)
    if mutation not in {"missing-proof", "self-review", "publisher", "unresolved-p1"}:
        def forbidden_fetch(_: str) -> Any:
            raise AssertionError("旧scope失敗より前に公開commentを取得した")
        monkeypatch.setattr(guard, "_fetch_delegation_comment", forbidden_fetch)
    with pytest.raises(checker.HumanReviewSignatureRecordError) as error:
        checker.validate_gate6_ci_event(root, guard.PullRequestEvent(**fields))
    if mutation == "unknown-scope":
        assert "旧49path" in str(error.value)
    if mutation in {"unknown-math-path", "math-commit"}:
        assert "数学path" in str(error.value)


@pytest.mark.parametrize("mutation", ["prior", "extra-key", "placement"])
def test_pr197_old_policy_origin_rejects_mutated_ledger_predecessor(
    pr197_gate6_candidate: tuple[Path, Any, Any, dict[str, Any]],
    mutation: str,
) -> None:
    """後発19から旧18を求める際も台帳の直前identityと配置を閉じる。"""
    root, guard, _, _ = pr197_gate6_candidate
    path = root / checker._ORDINARY_BASELINE_LEDGER_PATH
    ledger = json.loads(path.read_bytes())
    tail = ledger["history"][-1]
    if mutation == "prior":
        tail["prior_identity"]["values"][0]["value"] = "0" * 40
    elif mutation == "extra-key":
        tail["unreviewed"] = True
    else:
        tail["placement_change"]["after"] = []
    path.write_text(json.dumps(ledger))
    pins = checker._ordinary_pins(root)
    anchor = checker._OrdinaryAcceptedReader(root)
    with pytest.raises(checker.HumanReviewSignatureRecordError):
        checker._ordinary_policy_origins(root, guard, anchor, pins)
