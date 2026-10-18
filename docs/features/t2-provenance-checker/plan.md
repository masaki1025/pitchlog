---
feature: t2-provenance-checker
status: in-review
承認: 済(2026-10-17・山田正輝)
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

## 2026-10-18の計画追補（候補実装の限定許可）

本会話でPOが所有受諾・HEAD `ca1c5df4`・限定是正レビュー0/0/0を受領し、引継ぎ確認待ちを解除した。
**既承認裁定に意味を追加しないP-8追随の計画追補・候補実装・試験・ローカルコミット**を許可した。
新しい意味規則、独立期待値の確定、正本/凍結資産の正式変更、再署名、P-6受理、push/PRの包括承認ではない。

- 元の4ステップと過去コミット/レビュー回数を保持する。ステップ3に「再署名/正式受理へ提出する候補資産と能動検査」を追補する。元のD1〜D4によるprovenanceだけの再署名材料は保持し、実質変更の材料と混同しない。
- 候補の保存先は本feature配下の`candidates/`。正式な`contracts/state-transition/`、正本、署名記録には適用しない。
- E12の相関要求を既存導出器/被覆検査器の明示的な候補経路へ追加し、候補schema・拒否/非拒否case・欠落/改竄試験を既存の`tests/test_game_end_contract_schema.py`へ置く。現行の単一軸invalid境界/validationErrorsの12件は変更しない。
- E08/E06/E04の具体入力と、既承認のE02/E10の出力部分、E09の操作許可部分を候補へ収容する。未裁定のoutcome/公開入力型やE14の拒否境界は候補検査の保証外に明記し、人間判断を要する行だけを提示する。
- E11=A/E07=Bの既存行/単一値を保持し、GAP-05表示検証の候補は具体的なセル入力/期待表示を持つ。候補作成者による期待値はP-6独立検証済みと扱わない。
- develop取込みでは先行受理履歴を保持する。10失敗の各原因/担当/正式受理待ちを記録し、承認済み基盤の取込み不整合と検証環境を是正して影響試験を再実行する。
- 詳細な変更対象とP-6影響は[判断表](p8-followup-scope-candidate-2026-10-18.md)。同表の「未承認」は正式資産への適用・未確定の設計判断を指し、今回許可された候補作業を再承認待ちには戻さない。

この追補は新規の計画レビュー枠を作らず、既存の2回/使い切りを保持する。候補実装の独立レビューは既存差分是正レビューと対象を区別し、枠を超える場合は対象と使用済み回数を提示して追加判断を求める。


## 1. 背景・目的

- PO 裁定(2026-10-17・山田正輝 — master 経由): 「T2 provenance は 538/236 の所有側で、schema・検査器の最小改訂案と拒否系試験計画を作成する。既存 T1 検査を保持し、T2 の未記載・不正署名も検出対象にする。正式な資産変更は所定ゲートで判断する」
- PO 裁定(同日): 本タスクは「Claude の実装・レビューで代替 + 追認」の対象(律速 3 件の 1 つ)
- 発見: T1(状況判定)契約は由来記録(provenance)が schema で必須で、検査器もある。**T2(終了判定)契約は schema が provenance を禁止し(`additionalProperties: false`)、検査器も T1 しか読まない**。そのため U-X1 の着手条件 P-6(独立期待値)の署名の置き場が T2 に無く、欠落は CI で沈黙する
- 関係: ADR-003 D-14-m(T1/T2 限定の発効前経過措置)・U-X1 計画 `docs/features/ux1-state-calc/design.md` の P-6・NFR-019
- Notion: https://app.notion.com/p/3fc93b75e687812d83bdd45890f4844a
- 改訂案と調査: [research.md](research.md)


## 2. スコープ

### やること

- T2 契約の schema(`contracts/state-transition/game_end_contract_schema_v1.json`)に provenance の器を置く。`$defs` は **`$defs.provenance` から `$ref` で到達する閉包**(現状 5 つ: `provenance`・`provenanceSource`・`provenanceAttestation`・`provenanceIndependentReview`・`provenanceReviewEvent`)を T1 と同一の内容で写す。policy も `subjectKinds` を含めて T1 と完全一致(545 が既存の種別 `normative-branch-or-state-effect` を再利用すると決めた — 2026-10-17)
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
| 1 | **(依存なし — 545 の起案を待たずに着手)** 検査器の拡張: 登録表 `CONTRACTS`・`validate_provenance` の `contract_kind`(既定 = T1)・`classify_provenance`(未実施でも schema・典拠・`subjectKind` は全件検証、予約値の偽装は赤)・`check_repository`・`main()` の種別判定。T2 は合成 schema で試験し、試験は `tests/test_game_end_contract_schema.py` に置く | `tests/test_state_transition_contract_schema.py` が無変更で全件緑(P1)。research.md の P2・P4・S1〜S10・**S8'〜S10'(未実施の記録の上の偽の典拠)**・S11・S11a〜S11c(予約値の判定キーのうち 3 か所の各単独。検証者 ID だけの偽装は確認経緯の actorId の照合で必ず赤になるため単独の負例は置かない)・S4'・S12・N7・N8・N6 と 4-6 の変異確認が期待どおり。harness 全件(コア領域の参照検出 `tests/test_core_guard.py` を含む)・`uv run ruff check .`・`uv run ty check` が緑 |
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

## 2026-10-19追補: PO採用5件の候補実装

POは本会話で次の5件の候補実装・検証を承認した。旧判断表の5行は解決済みで、再承認待ちにしない。
宣言直前のdetected/lock/outcome保持、明示phase、表示契約へのGAP-05収容、共有投影のプレイ前後得点観測、kind/payload不整合の正規化拒否である。
具体型・責任境界・試験・受領条件は[candidates/adopted-boundaries-2026-10-19.md](candidates/adopted-boundaries-2026-10-19.md)に固定する。
候補schema/bundleの版1へ境界証拠digestを加え、別の人工fixture `p8_boundary_evidence_v1.json` と既存検査器内の候補正規化・再生・表示比較経路を追加する。正式契約・署名・製品計算核には適用しない。

基本コードレビュー2回（0/1/0→是正0/0/0）の履歴・計画レビュー2回・確定ゲート0回を保持する。
今回のPO明示許可は、反映後に固定した候補HEADと直接の影響箇所に対する独立コードレビュー追加1回である。
HEADと`76037523`以降の差分SHA-256を固定して依頼し、P-6独立期待値とは別に記録する。追加枠の無断増設はしない。
正式正本確定、凍結資産7.7、再署名、P-6、担当受理、push/PR許可は別途未成立として追跡する。

## 2026-10-19 Draft提出の追補

POが表示結合是正と直接影響の追加レビュー第2回（今回1回）、通常push/Draft PR、544/545/表示への送付を明示許可した。基本2回+追加第1回を保持し、追加第2回は60825a0f/diff SHA 1b1bcaa0…で0/0/0。正式変更/署名/P-6/担当受理は許可に含めない。545の着手前の公開契約/責任境界受理と実装後のreceiverDoDを分離し、P-1〜P-9/T1マージという既存条件を維持する。詳細は[受渡しとゲート](handoff-and-gates-2026-10-19.md)。

本Draftはステップ3の候補・署名確認材料のレビュー提出であり、ステップ4やDoD全成立の記録ではない。既知の署名不一致を明記してDraftを作成することはPOが本会話で許可済み。

## 2026-10-19 #153統合範囲の照合

POの指示で、新規PRを増やさずTSK-564として既存#153を継続する。最新develop015dfa9d（#155）の544候補受領・対象別開始条件を取り込み、[統合残ゲート一枚](pr153-merge-gates-onepage.md)を現行索引とする。#153は承認済みのprovenance器/候補/検査/受渡しを対象とし、正式P-8収容・P-6独立期待値・本人行為を完了としない。DRAW/GAP正式収容はTSK-564の継続責任を保持し、後続の実施担当/正式ゲートを明示して記録する。旧計画/レビュー履歴と署名前提はリセットしない。

## 2026-10-19 P-6引継ぎ・本人確認材料の限定追補

PO指示に基づき、未関与Codex担当が直ちに受け取れるT2の固定入力/原典hash/集合/再計算手順/提出先を`p6-transfer/`へ準備する。これは入力抽出と手順の固定であり、作者がP-6を実施した記録ではない。既存8行/248case/拒否12入力と、評価文脈・プレイ前得点不足・未正式P-8を分離する。正式契約/署名/独立宣誓を変更しない。山田正輝が本人確認者として指定されたことのみ記録し、確認は未実施。[本人確認依頼](human-review-request.md)に条文/対象資産別の統合前要否と最終差分の固定方法を示す。545/523は既存主担当へ集約して重複照会しない。
