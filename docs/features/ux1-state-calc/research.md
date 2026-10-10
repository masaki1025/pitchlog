---
feature: ux1-state-calc
type: research
date: 2026-10-10
---

# 調査メモ: U-X1 状況計算核 — 計画書の前提となる現況・境界・射程

基準: develop `f79c14e0`(2026-10-10)。要件書 v2.10 approved(`docs/requirements/requirements-pitchlog-2026-07-22.md:2`)。
以下、略記 `req` = 要件書、`ADR3` = `docs/adr/ADR-003-domain-calc-method.md`、`設計書` = `docs/development/dev-harness-design-2026-08-07.md`、
`C/` = `contracts/state-transition/`、`R/` = `docs/legacy/research/`。調査は spec-checker / decision-tracer / legacy-analyst / Explore の 4 並列。
エージェント間の食い違いは主セッションが原典で裁定した(「裁定」と明記)。

## 問い

1. U-X1 の実装を止めている条文は何で、解除には何が要るか
2. U-X1 の計画書が決めてよいこと・決めてはいけないこと(TSK-509 / TSK-510 / 発効条件タスクとの境界)
3. 主所有 13 FR + 分担(FR-007/011 下流再計算)の射程と、対象計算 / 周辺の切り分け
4. 段階① の検査基盤とベクタの実測現況
5. 旧システムの実挙動のうち、ベクタに入っていないもの

## 結論(要約)

- **凍結の根拠は ADR3 帰結 1 の段階順(`ADR3:929`「この段階では対象計算のコードを追加しない」)と 設計書 `:1145`。** 計画書を先に書く根拠は 設計書 `:1144`(「本章は製品実装の開始条件を定めない — 着手可否は 6.1 の実装計画書ゲートで判断する」)。**後者は ADR ではなく設計書の文言**(申し送りの出典は誤り)。
- **解除には 2 つの独立した前進が要る**: (A) **段階① の完了** = TSK-235 と **TSK-236〜239 の合流**(`docs/features/domain-calc-dsl/plan.md:96`)。**TSK-237(付録A)・238(領域シード・座標系)・239(移行)は計画書なし・未了**。(B) **D-2 の発効** — 現行は **D-1**(発効日の記録なし。`ADR3:681-682`「記録が唯一の発効の印」)。**D-1 では表現不能 5 件(C3/C4/C10/C12/C13)があり U-X1 の中核を書けない**(`ADR3:519-531`)ので、実質的に D-2 発効待ち(推論)。
- **解凍条件の書き方が 2 通りある**: 「段階① の完了」(`product-impl-unit-split/plan.md:386`)と「方式決定を待つ」(`adr003-d2-switch/plan.md:34`)。**TSK-510 のステップ 5 がこの裁定を PO へ上げる予定**(`feature/adr003-stage2-owner` の plan.md:123 — 未 push の作業ブランチ)。U-X1 計画書はこの裁定を前提として扱い、決めない。
- **U-X1 が決めるのは「段階 2 の 1 対象 = 1 変更」の中身だけ**: 正本・生成物・製品経路の呼び出し部・3 層検査を同一の変更に入れ、当該対象の全検査緑をマージ条件とする(`ADR3:930-931`)。BOOT-GRANT 免除は効かない(D-7 `ADR3:363-368`)。
- **13 FR はすべて対象計算(a)と周辺(b)の両方を含む。** ベクタは**状態遷移 96 case + 終了判定 170 case = 266 case が 2 ファイルにあるだけ**で、**FR-021/022/023/040 と FR-007/011 下流再計算はベクタ皆無**、どの実行体にも流れていない。
- **既存の状況計算コードは frontend/backend とも 0 件** — コピー実装の心配は無い。

## 詳細と典拠

### 1. 凍結と解除の条件

| 項目 | 内容 | 典拠 |
| --- | --- | --- |
| 凍結(実装順序) | 段階 1「検査基盤を先に確定する(この段階では対象計算のコードを追加しない)」 | `ADR3:929` |
| 凍結(設計書側) | 「NFR-018 の対象計算に触れる実装は ADR-003 の導入順序に従う — 検査基盤の未整備を理由に対象計算のコードを先に追加することはできない」 | 設計書 `:1145`(v1.13 `:77`、見出し `:1140`) |
| 計画書を先に書く根拠 | 「本章は製品実装の開始条件を定めない — 着手可否は 6.1 の実装計画書ゲート(人間承認)で判断する」 | 設計書 `:1144`(**ADR3 ではない** — 申し送りの出典誤り) |
| 段階 2 の変更単位 | 対象計算 1 件ごとに 正本・生成物・製品経路の呼び出し部・3 層検査を「同一の変更」(片側だけのコミットを作らない) | `ADR3:930` |
| マージ条件 | 当該対象について全検査が緑 | `ADR3:931`(後続タスク表 `:942`) |
| BOOT-GRANT 免除 | 段階 2 の変更が実在集合へ加えようとする対象計算の不合格は免除されない | D-7 表 `ADR3:363-368`、req `:962` |
| 段階 1 の完了条件 | TSK-235 と TSK-236〜239 の合流 | `docs/features/domain-calc-dsl/plan.md:96` |
| 解凍条件(単位分割) | 「ADR-003 段階① の完了まで — 条文の帰結」 | `docs/features/product-impl-unit-split/plan.md:386`・`:367` |
| 解凍条件(別記述) | 「U-X1 は本 ADR の方式決定を待っている」 | `docs/features/adr003-d2-switch/plan.md:34`・`:66` |
| 方式の現行 | D-1。v0.5(D-2 への切り替え)は 2026-10-10 approved だが発効日の記録なし | `ADR3:9-10`・`:666`・`:671`・`:681-682` |
| 発効手続き | (i)〜(iv) を条文化し確定ゲート approved(計画書・worklog に書いただけでは満たさない `:679`)+ 要件書の追随版 approved(`:680`)+ **PO が発効日を記録**(`:681`) | `ADR3:668-682` |

**凍結根拠の行番号ずれ**(単位分割計画書の引用が古い): `plan.md:234` の「req `:915`」は現在空行、`:134`/`:396` の「req `:891` fail-closed」は現在 NFR-011、`:396` の「ADR3 `:388`」は現在 `:929`。現行の位置は fail-closed `req:934`、正解ベクタの発効 `req:964`、着手順序 `ADR3:929`。fail-closed は未分類計算の条項で、凍結そのものの根拠ではない。

### 2. 境界 — U-X1 が決めないこと

| 決めないこと | 持ち主 | 典拠 |
| --- | --- | --- |
| 方式・発効 | PO の記録のみ | `ADR3:671`・`:682`・`:698` |
| 発効条件 (i)〜(iv) の条文化・要件書の規範追随 | 「別タスク」(**担当 TSK ID は不明**) | `docs/worklog/2026-10-09-adr003-d2-switch.md:1368`・`:1407`、`adr003-d2-switch/plan.md:95`・`:118` |
| 段階 2 の実行経路(D-2 なら JS 実行基盤、D-1 なら生成器)・段階 2 受取タスクの起票 | TSK-510 が射程案を作り PO 裁定 → 起票 | `feature/adr003-stage2-owner` の plan.md:41・:119-124(承認済 2026-10-10・active・**develop 未合流**) |
| D-6・D-12 の改訂 | TSK-338・TSK-275 | `ADR3:9`・`:732` |
| Q1 由来の是正 2 件(付録E の入力イベントに修正・挿入・削除が無い / D-8 比較面に帰属が無い) | **送り先不明** | `ADR3:900-906` |
| 整数符号化での回避 | 禁止 | `ADR3:828` |
| `.claude/core-areas.json` の paths 変更 | 設計書 6.3-⑤(敵対レビュー+人間承認) | 設計書 `:404` |

**裁定(食い違い)**: decision-tracer は「`docs/features/adr003-stage2-owner/` は存在しない」と報告、Explore は「未合流ブランチにある」と報告。**原典確認の結果、ローカルブランチ `feature/adr003-stage2-owner`(worktree `../pitchlog-worktrees/feature-adr003-stage2-owner`、`1fc6e0dd`、origin に未 push)に存在する。develop には無い**。

### 3. 発効条件 (i) 未確定の影響 — どの検査層が定まらないか

- D-1 下では (i) は決まっている: 比較相手は (α) の Python 生成物と TS 生成物(`ADR3:240`・`:365`)
- D-2 発効後は **プロパティ層②「実行体どうしの等価性」の比較相手が未定**(`ADR3:718-722`)。D-7 差分テスト行(`:364`)も影響(推論)
- (ii) 未定 → manifest への登録条件が未定(`ADR3:724-727`)
- (iii) 未定 → 正規化規則・表示経路の担保が未定(`ADR3:729-731`)
- ベクタ層の方式非依存部分は不変(`ADR3:701`)。変異層は (i)〜(iv) に名指しされず読み替え対象(`:699`)
- (iv) は (β) 専用。ただし **FR-021/022 のシーズン通算は (β)③**(`req:933`・`:481`)なので U-X1 にも掛かる(**申し送りの「U-X1 には直接掛からない」は不正確**)

### 4. 13 FR の射程(対象計算 = a / 周辺 = b / 判断不能 = c)

対象計算の正は NFR-018 の列挙のみ(`req:931` 「本項の列挙を正」 — 状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定)。(α) `:932`、(β)①〜⑧ `:933`。**「実在集合」は `req:962` で使われるだけで定義が無い**(ADR3 にも定義文なし)。

| FR | 要件書 | a(対象計算) | b(周辺) | ベクタ |
| --- | --- | --- | --- | --- |
| 002 | `:208-216` | 座標変換・内外角(`:932`) | 必須検査・球速欠損・永続化 | **なし**(`contracts/display-geometry/` 不在。直下に `display_geometry_263_v1.json` のみ)。既存 `frontend/src/lib/courseInputView.ts` は NFR-018 (c) 例外表(`req:959`) |
| 003 | `:218-227`、付録E `:1333-1620` | 状況判定 | 手動上書き UI・永続化 | ST-MATRIX 42・ST-COVERAGE 47 ほか。OUT3 は GAP-06 open |
| 004 | `:229-239`(`:234` に「NFR-018 の対象」) | 走者イベント・捕球選手推定 | 記録 UI | 走者系あり。**捕球選手推定なし**(`contracts/field-regions/` 不在) |
| 005 | `:241-252`、F-1 `:1636-1679` | 攻守交代・終了判定 | ロック表示 | 終了判定 170。walk-off 未充足・X 表記なし(`C/game_end_coverage_declaration_v1.json:21-27`・`:244-259`) |
| 006 | `:254-261` | undo 層 | キュー・べき等適用(U-S1) | ST-UNDO 1 件のみ(空履歴)。適用側未充足(`C/state_transition_contract_v1.json:5245`) |
| 007/011 下流 | `:263-274`・`:298-309` | ①再導出 =(α)合成 / ②再集計 =(α)(β)合成 | ③編集そのものは対象外 | **なし**(D-14-l `ADR3:863-908`、`:900-906`) |
| 009 | `:283-288` | タイブレーク開始・継続 | キュー | 継続のみ。**開始の操作行なし**(段階 2 へ送付 `C/required_set_input_coverage_declaration_v1.json:12-19`) |
| 010 | `:290-296` | 終了宣言時の確定 | 同期・バッジ(U-G1) | 操作行 2 件。**「FR-010 の自動判定」という語は計画書・設計書に無い**(自動検知は FR-005 `:247`・F-1 `:1679`) |
| 014 | `:346-355`、付録F `:1623-1692` | スナップショットを入力とする終了判定 | 保存・帰属・スナップショット / c: 適用優先・保存時検証 | validationErrors 12 件。`:354` の例「コールド適用回＞規定イニング」が DRAW-01〜03 と DB CHECK に無い |
| 020 | `:439-466` | スコアボード・X 表記 | 鮮度表示 | scoreboardFieldEffects。XMARK は GAP-01/05 open。付録A ベクタなし |
| 021 | `:468-474` | 当日成績(α)/ **シーズン通算(β)③** | 注記 | **なし** |
| 022 | `:476-484` | 当日打席結果(α)/ **シーズン通算(β)③** | — | **なし** |
| 023 | `:486-491` | 球種表示名・割合・球数 | — | **なし** |
| 040 | `:357-366`(**Should**) | 補正を跨いだ再計算 | キュー | **なし**。除外宣言済み(`C/required_set_input_coverage_declaration_v1.json:20-27`)。採否は段階 2 で manifest に宣言(`C/appendix_e_consumer_handoff_v1.json:165-170`) |

FR-014 の function_only の申し送り(`docs/features/product-authz-surface/design.md` 1-6)は要件書と整合(`req:348`・`:355`・NFR-010 `:887`)。`rule_sets` 本体の書き込み関数の所有者は不明。

### 5. 段階① の実測現況

| 項目 | 実測 | 典拠 |
| --- | --- | --- |
| `C/` | **37 ファイル**(うち schema 15)。ベクタ(cases)を持つのは 2 本: 状態遷移 **96** case・終了判定 **170** case = **266**。手動 fixture 26+5 | `grep -c '"caseId"'`(主セッション再測で一致) |
| `backend/domain/` | 19 ファイル、**schema は 5 本**(boot-report / manifest / model / path-match / vocabulary)。**model.json・manifest.json 実体なし**(合成 fixture のみ `backend/tests/domain/fixtures/synthetic_dsl/`) | Explore 実測 |
| 生成器 | `backend/src/pitchlog/domaingen/backends/` python 48 / typescript 42 / sql 38 行の固定スタブ(宣言を読まない)。`formatter.py`(789 行)は表示 primitive を実生成 | `ADR3:7` も「固定スタブ」 |
| 検査部品 | runners 6 本・収集器・CI 配線(`ci.yml:116-137`) | Explore 実測 |
| QuickJS | **0**(docs のみ) | — |
| Node | テストで 3 箇所(`tests/domain/gen/test_formatter.py:364`・`tests/domain/mut/test_lang_operators.py:82`・`backend/src/pitchlog/domainmut/cost_record.py:438`)。**D-2 方式の実装は 0** | — |
| 266 case の実行 | **どの実行体にも流れていない**。`consumptionVerification: "pending"`・`receiverTaskId: null` | `C/appendix_e_consumer_handoff_v1.json:180`・`:188` |
| 消費者 | 静的検査スクリプト 3 本以上(`check_state_transition_normalization.py`・`check_required_set_coverage.py`・`check_gap_register.py`)+ 関連スクリプト・pytest 約 19 本。Vitest は合成ベクタのみ | Explore 実測 |
| 状態遷移ベクタの独立検証 | **未実施**(`independentVerifierId: "not-performed"`)— D-6 CI 規則 3 が要求 | `C/state_transition_contract_v1.json:214-229`、`ADR3:334` |
| 既存の状況計算コード | **frontend/backend とも 0**(ORM の保存列のみ `db/game_state/models.py:741`) | Explore grep |
| GAP 状態の不整合 | GAP-03/04 は resolved だが COLD/DRAW 分岐が uncovered に残る | `C/gap_register_v1.json:31-102`、`C/game_end_coverage_declaration_v1.json:119-191` |

段階 1 の残作業:

| タスク | 中身 | 計画書 | 状態 |
| --- | --- | --- | --- |
| TSK-235 | 生成器・マニフェスト・収集器・CI | `docs/features/domain-calc-dsl/plan.md` | PR #74 マージ済 |
| TSK-236 | 付録E + 終了判定 | `docs/features/appendix-e-golden-vectors/plan.md` | #81 で着地 |
| TSK-455 | Vitest runner | `docs/features/vitest-vector-runner/plan.md` | #107 で着地 |
| **TSK-237** | 付録A 固定ベクタ | **なし** | **未了** |
| **TSK-238** | 領域シード・座標系ベクタ | **なし** | **未了** |
| **TSK-239** | 移行ベクタ | **なし** | **未了** |

(TSK-237〜239 の状態は `docs/features/adr003-d2-switch/research.md:165-175` 時点〔2026-10-09〕。Notion の現況は未確認)

### 6. TSK-236 の引き渡し契約

- 本体 `C/appendix_e_consumer_handoff_v1.json`: `receiverTaskId: null`(`:188`)、runner の ID 3 つは null で確定は stage-2(`:50-66`・`:104-120`)、受取側 DoD `:157-164`、FR-040 採否 `:165-170`
- S01〜S34: `docs/features/appendix-e-golden-vectors/unresolved-report.md:52-85`(送り先「段階2受取タスク」・未起票と明記 `:47`)
- U-X1 は契約の消費者に当たる(推論)が、**受取タスクそのものかは原典に書かれていない(不明)**。TSK-510 が甲(実行経路)/ 乙(受取)の 2 案を PO へ上げる

### 7. TSK-405(`docs/features/ux1-game-state-core/`)から引き継ぐもの

- 表現不能 5 件: C3・C4・C10・C12・C13(`docs/features/ux1-game-state-core/research.md:538-546`・`:735`)。全 32 件 = 不能 5 / 未確定 20 / 可能 0 / 不要 7。未確定のうち 10 件は C3 に従属(`:558-570`)
- 要件側 Q2〜Q4 未解消(`:740-746`)

### 8. 旧システムの実挙動(ベクタ未反映分)

旧の状況計算はほぼすべてクライアント内の純関数 `domain/game_state.update_list`(`R/domain-logic.md:103-119`)。DB は 1 球 1 行のスナップショット保存のみ。**契約が旧資料として引くのは `R/input-screen.md` の 14 箇所だけで、`R/domain-logic.md` は未引用**(`C/state_transition_contract_v1.json:141-183`)。

ベクタ・付録E に入っていない暗黙規則(計画書で「踏襲 / 不採用 / 要件側へ送る」を判定する候補):

1. カウント自動昇格 — S=2 の見逃し/空振り → 三振、B=3 のボール・B=3 の無投球ピッチクロック違反 → 四球(`R/input-screen.md:173-175`)。契約は B=0 の代表行のみ(`C/state_transition_contract_v1.json:507-537`・`:3177-3215`)
2. ファールは S<2 のときだけ +1(`R/domain-logic.md:117`)。契約は S=0 のみ(`:416-450`)
3. 切り詰めのみで不変条件の検査なし(`R/domain-logic.md:117`・`:175`)
4. 打席途中の 3 アウトで打順を 1 戻す(`R/domain-logic.md:115`)— 契約側の表現は未確認
5. 走者再配置の衝突検出なし(`:116`)
6. 得点を 2 箇所で独立に数える(`:113`・`:174`)
7. フォースの第 3 アウト時の得点・振り逃げ不成立は警告のみ(`:67`、`R/input-screen.md:163`)
8. 終了検知で走者クリア・自動確定(`R/domain-logic.md:118`)— 新は検知と宣言を分離(`req:247`)
9. 打席継続の判定(`R/input-screen.md:176`)
10. 状況変更範囲・TB 開始回は UI 側の制約(`:115`)

新で変えた点: サヨナラの得点上限(`req:249`)、終了の検知/宣言分離(`req:247`)、スコアボード B は四球のみ(`req:449`)、状態補正は履歴付きイベント(`req:362`)。自責点・防御率・勝敗投手・セーブは Won't 維持(`req:102-103`・`:1582`)。

移行(U-X5・FR-038)との接点:
- 状況変更・TB は旧 DB に書かれず、再計算すると不連続が出る(`R/services-shell.md:206`、`req:820`)。**移行試合の状態の正(保存値か再計算か)は不明**
- 責任投手の規則が移行用(`req:824`)と通常運用(`req:1187`)で一致しない
- 移行試合の規則スナップショット「現行判定ロジック相当」(`req:355`・`:829`)が付録 F-2 既定(`req:1684-1688`)と一致しない
- 移行試合の FR-010 宣言イベントの扱いは不明

88 列の入出力: `R/data-layer.md:163-231`(出力 = 回・表裏・得点・SBO・継続 3 列・走者・打順・打者・投捕・スコア配列 / 入力 = 作戦・打者走者状況・プレイ種類・打撃結果・捕球選手・打球タイプ・牽制・エラー選手・スタメン JSON)。

### 9. コア領域

- 重複帰属 game-state × sync-protocol(`docs/features/product-impl-unit-split/design.md:103`)
- 計画書: 敵対レビュー(設計書 `:381`)/ PR: 敵対レビュー + 人間の逐行確認 + 実施記録行(`:383`・`:389`・`:391`)/ 回数: 基本 2 回・P0 例外で自動 1 回・追加は PO 裁定(`:406`)
- `.claude/core-areas.json` game-state の paths(`:316-327`・`:304`)。**D-2 の TS 正本・JS artifact・エンジンの置き場に当たる paths は無い**(推論: 実装時に登録が要る。窓口は回転式 — 計画段階では触らない)

## 未解決・申し送り

1. **解凍条件の 2 通りの書き方**(段階① 完了 / 方式決定)— TSK-510 ステップ 5 で PO 裁定予定。U-X1 計画書の着手条件節はこの裁定に従う
2. **TSK-237〜239 は計画書なし・未了** — 「段階① の完了」が解凍条件なら U-X1 の律速。**U-X1 の対象(状態遷移・終了判定)は TSK-236 で揃っているが、付録A(237)・座標(238)を待つ必要があるか**は、段階 2 が「対象 1 件ごと」(`ADR3:930`)であることとの関係で**解釈が要る**(PO 判断事項)
3. 発効条件 (i)〜(iv) と要件書追随を担当するタスク ID — 不明
4. 段階 2 受取タスクの ID と、U-X1 との関係 — TSK-510 の 2 案待ち
5. Q1 由来の是正 2 件(付録E の修正・挿入・削除イベント / D-8 比較面の帰属)の送り先 — 不明。FR-007/011 下流再計算に直撃
6. FR-040(Should)の採否 — 判断者不明。リハーサル 26 FR に含まれるが要件書 8 章①(`req:1083`)は Must のみ
7. リハーサル 26 FR の導出元 — 要件書 `:1085` に列挙なし。出所は `adr003-d2-switch/plan.md:33`・`frontend-impl-units/design.md:360`・`um1-player-roster-opponent/plan.md:455`
8. FR-021/022 の (β)③ を U-X1 が持つこと — U-X2((β))との境界の明記が無い
9. 状態遷移ベクタの独立検証が未実施(`C/state_transition_contract_v1.json:214-229`)— 段階 2 のマージ条件(全検査緑)に効く
10. 旧の暗黙規則 10 件の踏襲判定 — U-X1 計画書で候補として扱い、要件側の判断が要るものは PO へ
11. 単位分割計画書・Notion カードの凍結根拠の行番号ずれ(`plan.md:134`・`:234`・`:396`)— 是正の送り先未定
