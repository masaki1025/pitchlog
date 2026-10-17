---
feature: t2-provenance-checker
status: active
承認: 未
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3fc93b75e687812d83bdd45890f4844a
branch: feature/t2-provenance-checker
created: 2026-10-17
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: T2(終了判定)契約の由来記録の器と検査器


## 1. 背景・目的

- PO 裁定(2026-10-17・山田正輝 — master 経由): 「T2 provenance は 538/236 の所有側で、schema・検査器の最小改訂案と拒否系試験計画を作成する。既存 T1 検査を保持し、T2 の未記載・不正署名も検出対象にする。正式な資産変更は所定ゲートで判断する」
- PO 裁定(同日): 本タスクは「Claude の実装・レビューで代替 + 追認」の対象(律速 3 件の 1 つ)
- 発見: T1(状況判定)契約は由来記録(provenance)が schema で必須で、検査器もある。**T2(終了判定)契約は schema が provenance を禁止し(`additionalProperties: false`)、検査器も T1 しか読まない**。そのため U-X1 の着手条件 P-6(独立期待値)の署名の置き場が T2 に無く、欠落は CI で沈黙する
- 関係: ADR-003 D-14-m(T1/T2 限定の発効前経過措置)・U-X1 計画 `docs/features/ux1-state-calc/design.md` の P-6・NFR-019
- Notion: https://app.notion.com/p/3fc93b75e687812d83bdd45890f4844a
- 改訂案と調査: [research.md](research.md)


## 2. スコープ

### やること

- T2 契約の schema(`contracts/state-transition/game_end_contract_schema_v1.json`)に provenance の器を置く。`$defs` は **`$defs.provenance` から `$ref` で到達する閉包**(現状 5 つ: `provenance`・`provenanceSource`・`provenanceAttestation`・`provenanceIndependentReview`・`provenanceReviewEvent`)を T1 と同一の内容で写す。policy も T1 と同一で、T2 固有は `subjectKinds` だけ
- 検査器(`scripts/check_provenance.py`)を、契約種別の登録表と 3 状態(未記載・未実施・実施済みの主張)の判定に拡張する。**未実施の記録でも schema・典拠参照・`subjectKind`・充足典拠は全件検証し、免除するのは独立性・宣誓・`independentReview` だけ**。予約値 `not-performed` は閉じた形と完全一致する場合に限る(research.md 2 節)
- T2 契約に、未実施の形の provenance を入れる(中身は 545 の起案 — 10/20)
- 波及先: 既存の T2 schema 試験の期待値・両 runner の読み込み器のキー集合・引き渡し契約の digest・読み込み器の変異 fixture と両 runner の変異適用器(L1 のための `remove` 操作)
- 拒否系試験(research.md 4 節)
- gate6-game-end の再署名の材料(D1〜D4 の出力)と、PO の明示の再署名を受けた署名記録の転記

### やらないこと

- T1 の schema・契約・既存の試験ファイル(`tests/test_state_transition_contract_schema.py`)の変更(**T1 不変** — 1 バイトも変えない)
- T2 の規範行・case の変更(545 の子カード (e) の射程。同居させると D2 が崩れる)
- PO の明示の再署名が無いままの署名記録の変更(署名の偽造になる)
- 署名検査器(`check_human_review_signature.py`)の改訂
- ci.yml の変更(凍結 corpus の受理を避ける。配線は pytest 経由 — harness ジョブが `pytest tests/` を流し、harness は必須チェック)
- `.claude/core-areas.json` の変更(新しい試験ファイルを作らず、登録済みの試験ファイルへ置く — 4 節)
- D1〜D4 の道具の資産化(出力を PR 本文と worklog に貼るだけにする — 4 節)
- L2・L3(トップレベル未知キーの変異)— **PO 判断「L1〜L3 の射程」で入れる場合はステップを足す**
- P-6 の独立検証そのもの

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| (反映なし) | docs/ の正本体系(要件書・ADR・設計書・ops・development)には触れない | — |

正本体系外だが同一 PR で更新するもの:

- 契約: `contracts/state-transition/game_end_contract_schema_v1.json`・`game_end_contract_v1.json`・`appendix_e_consumer_handoff_v1.json`
- 検査器: `scripts/check_provenance.py`
- 読み込み器: `backend/src/pitchlog/domaincheck/runners/handoff.py`・`frontend/src/testing/handoffLoader.ts`
- 試験: `tests/test_game_end_contract_schema.py`(既存の期待値の追随と、T2 provenance の試験の置き場)・`tests/domain/runners/fixtures/handoff-loader/mutations.json`・`tests/domain/runners/test_handoff_loader.py`・`frontend/src/testing/handoffLoader.spec.ts`(`remove` 操作の追加)
- 署名記録: `docs/features/adr003-stage2-runtime/signatures/gate6-game-end.json`(**PO の明示の再署名を受けた転記だけ** — 4 節)

## 4. 実装方針

- **重さ分類 = コア領域**: 変更対象の契約・検査器・試験は `core-areas.json` の game-state・sync-protocol に、読み込み器(`handoff.py`・`handoffLoader.ts`)は game-state・data-migration に登録済み(署名記録 `gate6-game-end.json` はどの領域にも属さない — 計画レビュー 2 回目の観察)。とくに試験は、両領域に登録済みの `tests/test_game_end_contract_schema.py` に置く(**新しい試験ファイルを作ると**、`reference_discovery` が `contracts/state-transition` を参照する Python として検出し、両領域の paths に無いため harness が赤になる — `tests/test_core_guard.py:1127-1180`・`:2973-3007`。登録には `AREA_PATH_ADDITIONS` の二層契約と設計書 6.3 の paths 落とし込み規則のゲートが要るので、既存の glob で済ませる)。T1 側の検査器の試験は `tests/test_state_transition_contract_schema.py` に既にあり、そこは触らない
- **実装とレビューの主体(PO 裁定 2026-10-17 による逸脱)**: 実装は Claude(538)。`codex_run.py review normal` と PR 段階の `review adversarial` は、**実装に関与していない Claude サブエージェント**で代替する。計画レビューも同じく代替する(master の読み — PO へ確認中。違っていれば追認の対象が増える)。代替の条件は次の 4 つ:
  1. 依頼文は Codex に出すときと同じものを使う(検証観点と受理範囲を省かない)
  2. 自己レビューを 1 周に数えない
  3. worklog と PR 本文に「Codex 敵対レビューの代替として Claude で実施」と明記する
  4. 重大度の定義は設計書 6.1(計画レビュー)・6.3(コア領域 PR)のまま
- **追認**: 代替でレビューした版(計画と PR)を Codex で 1 回追認する。期限は master 提案で 10/28(確定は PO)。worklog・PR 本文・Notion に残し、追認が済むまで「完了」にしない
- **署名記録の扱い**: 署名は PO の行為。PO が D1〜D4 の出力と差分を確認し、本セッションで明示に再署名したときだけ、Claude がその内容を署名記録へ転記してコミットする(前例 `22cf696f` — TSK-538 ステップ 34 で同じ形)。転記で守る条件: `artifactAuthorId` は `codex` のまま・`recordedReviewerId` は `山田正輝`・`reviewScope` に逐行確認シートの SHA-256(`tests/test_human_review_signature.py:166-167` が要求)を残し、「provenance の追加だけ。規範行と派生 case は 2026-10-15 の確認から不変(D2 で機械照合)」を追記・`recordedOn` は再署名の日。provenance ブロック自体の作成者(Claude・545)は `reviewScope` に書く
- **D1〜D4 の道具**: 資産にしない(scripts/ に置くとコア領域の参照検出と登録が要る)。資産外の試作を、リポジトリのルートを引数で受け、`safeIntegerLimit` を署名 schema の policy から読む形に直して使い、出力を worklog と PR 本文に貼る。正規化は署名検査器の `compute_subject_digest` を呼ぶので照合と同一
- **依頼文で名指しして問う軸**(2026-10-15 にサブエージェントが P0 を取り逃がした実測を織り込む):
  - NFR-018 のコピー実装(provenance の `$defs` を T2 へ複製すること自体は schema の重複 — 照合試験 D1〜D3 で縛れているか)
  - NFR-023・シークレット・テナント分離の迂回(該当なしの確認を含む)
  - **新しい検査器が「自分の射程外を沈黙で通す」穴を別の形で作っていないか**(登録表の閉包・未実施判定の閉じ方・`main()` の種別判定・`check_repository` の列挙漏れ)
  - 「未実施」の閉じた形が緩すぎて、不正署名や偽の典拠を未実施として通さないか(半署名の各形・予約値の偽装・未実施の記録の上の S8〜S10)
  - T1 の挙動が変わっていないか(既定引数・SCHEMA_PATH・例外文言)
  - 波及の漏れ(T2 契約を読む全スクリプト・runner・試験・期待値の固定・コア領域の参照検出)
  - **引用と原典の一致**(独立の軸): 計画書・research.md・試験・契約の `sources` が条文やコードを引いている箇所について、引用が原典と一致しているか。要件書は条項 ID(`req:FR-…` など)で引き、行番号では引かない(`unresolved-report.md` の `REQ:nnn` が現行の要件書とずれている実測あり — 545・master が再現)。コードの `ファイル:行` は基準コミットを添える
- 引用の現況(2026-10-17・`188acf83`): 本計画書と research.md は要件書を行番号で引いていない(0 件)。コードの `ファイル:行` は計画レビュー 1・2 回目で照合し、範囲のずれ(`handoff.py` の `CONTRACT_KEYS` — 正しくは `:156-184`)を直した
- 詳細は [research.md](research.md) の 3 節(改訂案)・3-5(D2)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **(依存なし — 545 の起案を待たずに着手)** 検査器の拡張: 登録表 `CONTRACTS`・`validate_provenance` の `contract_kind`(既定 = T1)・`classify_provenance`(未実施でも schema・典拠・`subjectKind` は全件検証、予約値の偽装は赤)・`check_repository`・`main()` の種別判定。T2 は合成 schema で試験し、試験は `tests/test_game_end_contract_schema.py` に置く | `tests/test_state_transition_contract_schema.py` が無変更で全件緑(P1)。research.md の P2・P4・S1〜S10・**S8'〜S10'(未実施の記録の上の偽の典拠)**・S11・S11a〜S11c(予約値の判定キー 4 か所の各単独)・N6 と 4-6 の変異確認が期待どおり。harness 全件(コア領域の参照検出 `tests/test_core_guard.py` を含む)・`uv run ruff check .`・`uv run ty check` が緑 |
| 2 | **(前提: 545 の起案〔10/20 予定〕を受領。遅れてもステップ 1 は止まらない)** T2 の器の着地: schema の `properties`・`required`・`$defs` の閉包 5 つ・policy、T2 契約の provenance(未実施の形・545 の起案)、`tests/test_game_end_contract_schema.py` の既存の期待値(`required` の 8 キー固定 `:455-464`・最小契約 `_minimal_contract` `:382-398`)の追随、読み込み器 2 つのキー集合、両 runner の変異適用器への `remove` 操作と L1 の変異(期待 code `UNKNOWN_FIELD`)、引き渡し契約の digest、照合試験 D1〜D3・N1〜N5・P3・P5 | gate6 の署名照合(`test_repository_gate6_signature_records_match_current_contracts`)以外が緑(harness・backend・frontend の該当試験)。D2 の出力(provenance を除いた digest == `3514e1c6…`)を worklog に記録 |
| 3 | 再署名の材料: D1〜D4 の出力・新しい digest・`reviewScope` の追記案を worklog にまとめる(署名記録はまだ変えない) | D1〜D4 がすべて成立。PO へ提出できる形になっている |
| 4 | **(前提: PO の明示の再署名)** 署名記録の転記: `gate6-game-end.json` の `subject.digest`・`recordedOn`・`reviewScope` を 4 節の条件どおりに更新する | `test_repository_gate6_signature_records_match_current_contracts` を含め、**core-guard(人間の逐行確認チェック)以外の必須チェックが緑**(P6)。CI の全緑は人間の逐行確認の後 |

**人間ゲート**(ステップ外):
- 計画承認(PO)
- ステップ 3 と 4 の間: PO が D1〜D4 の出力と差分を確認し、gate6-game-end を明示に再署名する。**ステップ 2 から 4 までは CI が赤**(署名照合)。必須チェックが赤のあいだはマージできないので、同じ PR の中で閉じる
- コア領域 PR の人間の逐行確認(設計書 6.3 — 代替不可)。ステップ 4 の後の最終差分に対して行い、その後に core-guard を含む CI が全部緑になる
- PR 段階の代替レビュー(Claude サブエージェント — 1 回目 = PR 差分全体 / 2 回目 = 反映差分と影響箇所)と採否記録
- PR 後の追認ゲート: Codex による追認 1 回(計画と PR の代替レビュー分 — 期限 10/28 案)

**依存**: ステップ 2 は 545 の起案(10/20 — subjectKinds 1 種・初期の sources)を受けてから。ステップ 1 は依存なし。

**完了見込み**(推論): ステップ 1 は計画承認の直後に着手でき、ステップ 2・3 は 545 の起案(10/20 予定)の後。代替レビュー(Claude)までは 10/21 ごろに詰められる見込み。**Codex の利用枠が 10/22 17:45 まで上限で停止している(562 の報告 — master・538 の実測ではない)ため、追認は 10/22 以降**。10/22〜10/28 に追認・PR 段階のレビューが集中するので、順番は PO が判断する。着地の最後は PO の gate6-game-end 再署名(ステップ 4 の前提)と逐行確認で、日付は PO 次第

## 5. DoD(受け入れ基準)

- [ ] T2 契約の provenance が schema で必須になり、未記載が赤になる(ステップ 2)
- [ ] 検査器が T2 を登録表で扱い、不正署名・予約値の偽装・未実施の記録の上の偽の典拠(research.md 4-2)を赤、未実施の閉じた形を緑(未成立として列挙)にする(ステップ 1)
- [ ] T1 の既存の試験ファイルが無変更で全件緑(ステップ 1・2)
- [ ] 登録表の契約の集合が `contract_size_limit_v1.json` の `contractPaths` と一致することを試験で固定(ステップ 1)
- [ ] 読み込み器(Python・TS)が provenance つきの T2 契約を読み、L1 を `UNKNOWN_FIELD` で拒否する(ステップ 2)
- [ ] D2 が成立する(provenance を除いた digest が署名記録と一致)(ステップ 2・3)
- [ ] PO が gate6-game-end を再署名し、署名記録が転記され、core-guard 以外の必須チェックが緑(ステップ 4)。逐行確認の後に CI が全部緑(人間ゲート)
- [ ] 代替レビュー(Claude サブエージェント)の採否が worklog にあり、PR 本文に代替の明記がある(ステップ外 — 計画段階と PR 段階)
- [ ] 人間の逐行確認(ステップ外 — 人間ゲート)
- [ ] Codex の追認(期限 10/28 案)— 済むまで Notion を「完了」にしない(ステップ外 — PR 後の追認ゲート)

## 6. テスト計画

- 単体: 検査器の 3 状態の判定・登録表・`main()` の種別判定(research.md 4-1〜4-4)— ステップ 1
- 故障系: 未記載・半署名・予約値の偽装・種別の取り違え・器のずれ(N1〜N6・S1〜S10・S8'〜S10'・S11・S11a〜S11c・D1〜D3)— ステップ 1・2
- 一致性: 読み込み器の Python・TS で同じ code(L1 — 既存の対の試験)— ステップ 2
- 変異: 未実施判定の条件を 1 つずつ外す変異と、登録表から game-end を外す変異が負例で落ちる(research.md 4-6)— ステップ 1
- 越境・E2E: なし(テナントの入力が無い・製品経路に触れない)
