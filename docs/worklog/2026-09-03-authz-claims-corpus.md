---
date: 2026-09-03
topic: TSK-270 要件主張母集合のマージ後レビュー P0 7 件の是正(TSK-312)
branch: fix/authz-claims-corpus
---

# 作業ログ: 2026-09-03 TSK-270 要件主張母集合のマージ後レビュー P0 7 件の是正(TSK-312)

## やったこと

### /task-start — 着手

- Notion TSK-312 を起票(https://app.notion.com/p/3d093b75e68781d894cac8a869bea666 — 優先度 高・コア領域〔テナント分離〕・TSK-278 ステップ 10 のブロッカと明記)
- worktree `../pitchlog-worktrees/fix-authz-claims-corpus`・ブランチ `fix/authz-claims-corpus` を `origin/develop`(41884a9)起点で作成

## 決定

### /investigate — 調査(3 サブエージェント並列 + 本体で外部 4 方向)

- 結果は `docs/features/authz-claims-corpus/research.md` に統合(典拠つき)
- **P0 7 件の一次記録は現存しない**ことを 4 方向(リポ内文書・GitHub PR #33・Notion TSK-270 全コメント・git log 本文)+ 過去セッション scratchpad で確定 → **再列挙(敵対レビュー再実施)を計画へ**
- 既知 3 カテゴリの構造的裏付け・採取欠陥の原因箇所(`_table_cells` :229-232)・digest 連鎖の全経路・reseal 2 段制約を現物で確認

## 未決・次の一歩

### /plan — 計画書の記入と PO 事前裁定(2026-09-03)

- PO 裁定 2 件: **H-85 案②③ = 見送り・別起票** / **例外表 2 セルのゲート区分 = 7.6-3 前段で確定**(TSK-233 判断の再確認)
- 計画書を記入し敵対レビューへ(コア領域)

### 計画レビュー 1 周目 — 否決(P0×2・P1×7・P2×1)・全件採用

1. P0 再列挙の対象から派生・oracle 資産が欠落(結線は経路レジストリ側にしかない) → 対象を contracts/authz 全資産へ
2. P0 oracle 6 資産の追随ステップが欠落(--reseal-oracle は内容を生成しない・oracle_context.oracle_commit の一致必須) → ステップ 6 として独立化
3. P1 §4-(2) のステップ番号ずれ → 2/3/5/6 へ統一・裁定範囲を 2〜6 へ
4. P1 独立照合が件数のみで相殺を許す → ID の exact-set 突合 + python 直接計数(checker 出力に依存しない)+ 機械可読保存へ具体化
5. P1 計画改訂トリガーが閉じていない → §2 に衝突規則(黙って範囲へ入れない・(a) 別起票 / (b) 計画改訂の PO 裁定)を新設
6. P1 ステップ 3 が未確定の是正を 1 コミットに束ねる → 既知分(ステップ 3)と裁定由来(ステップ 4・複数意味論なら計画改訂で分割・0 件時は記録コミット)へ分離
7. P1 red の中間状態が機械的に限定されていない → §4-(2) にステップごとの想定 red と --skip-oracle の使い分けを明記
8. P1 「1:1 対応」が成立しない(1 指摘対複数レコードが既知) → 帰属表(全帰属・帰属なし 0)へ再定義
9. P1 DoD に「採用裁定の全件反映・未反映 0」がない → 追加
10. P2 research/worklog の PO 裁定記録が未同期 → 現行化(本記録)

### 計画レビュー 2 周目 — 否決(P0×3・P1×8・P2×1)・全件採用

1. P0 変更履歴 1 行追記も全数採取対象(total 1063・table_row +1)なのに追随列挙から漏れ → §2-4・ステップ 5・research の件数予測へ明記(分類既定 = out_of_scope・観点⑦へ)
2. P0 exact-set の意味混同(指摘 ID と全 ID) → 「母集団全 ID リスト(走査の全数性)」と「指摘 ⊆ 母集団(帰属)」の 2 検査へ分離
3. P0 独立列挙の対象が oracle 資産・seal を含まない → 全 15 資産の主キー集合の機械列挙へ拡大
4. P1 4a・4b 枝番は feature_status が整数連番のみ認識 → 整数連番の振り直しによる分割改訂へ
5. P1 衝突規則の (b) の戻し先が §4-(5) 限定・(a) の P0 起票が宙に浮く → (b) を通常の計画改訂へ一般化・(a) に後続の扱い(/task-done 前提か TSK-278 ブロッカ昇格か)の同時裁定を必須化(DoD にも追加)
6. P1 reseal 手順が一意でない → ①--reseal --skip-derived --skip-oracle ②派生更新 ③--reseal-derived --skip-oracle の実行順を §4-(2) に固定
7. P1 ステップ 5 後の想定 red に :300(引数なし実行が oracle 到達)が漏れ → 「委任前に失敗テスト ID の完全列挙を実測して固定」方式へ + 見込み 2 本を明記
8. P1 oracle 追随の写像が閉じていない → §4-(6) 新設(参照フィールド機械抽出 → 交差列挙 → checker 整合への最小追随・新規判断は委任先に行わせない)
9. P1 oracle の review_policy(変更時の再レビュー + 人間確認)が計画に不在 → ステップ 6 に差分敵対レビュー + 人間確認を必須化
10. P1 ステップ 4 の新検査に負例 red→green が未要求 → 検査ごとの負例を合格条件・テスト計画へ
11. P1 帰属表の定義が不完全 → §4-(4) に保存先(attribution.json)・基準コミット(41884a9)・抽出単位(エントリ/hunk)・帰属先 3 分類を固定
12. P2 Notion DoD 同期の監査不能 → 承認時に Notion 本文 DoD を §5 と同一内容へ更新し worklog へ記録する規定を追加

### 計画レビュー 3 周目 — 否決(P0×5・P1×3)・全件採用

1. P0 帰属表の全帰属条件が達成不能(feature 文書・自己ファイルで再帰) → 帰属対象を成果物差分(contracts/authz・検査器・tests・要件書・README)に限定
2. P0 pytest -x は初回失敗で停止し完全列挙にならない → 全件実行(-q --no-header)へ
3. P0 「委任前後の集合一致 = 回帰」規則が意図した遷移と矛盾 → 比較基準を「当該ステップ完了後の期待失敗集合」へ再定義
4. P0 変更履歴行はステップ 1 時点で未存在なのに観点⑦・母集団に含めていた → 母集団から除外し、分類既定 + ステップ 5 検査 + PR 総合レビューで担保
5. P0 ID 集合に名前空間がなく lock の未走査を検出できない・主キーなし部分が列挙外 → `<資産>:<主キー>` 名前空間 + トップレベルキー単位の列挙へ
6. P1 oracle 追随の交差判定が依存閉包を表さない → 追随対象の判定を checker の fail に委譲(最小追随・新規判断禁止は維持)
7. P1 差分レビュー後に oracle_commit を変えるとレビュー対象とバイト列が乖離 → 順序を「内容追随 → commit 差し替え(最終形確定)→ レビュー → reseal」へ是正
8. P1 分割改訂の本文波及・総数接尾辞の危険 → 本文参照の一括更新規定 + ステップコミットは `(ステップ k)` のみ(総数 /N を付けない)

### 計画レビュー 4 周目 — 否決(P0×1・P1×4)・全件採用

1. P0 全数走査の exact-set が 15 資産のみで検査器・要件書が未走査でも合格できる → 母集団へ `check_authz_catalog.py:<関数名>`・要件書 `<heading_id>`(125 件)を追加
2. P1 §2-4「観点にも含める」が前周 P0-4 の反映(§4-(3) の除外)と競合 → §2-4 を除外側へ統一
3. P1 checker は最初の CatalogError で停止し fail 集合を一括で得られない → 「fail → 最小追随 → 再実行」の反復規則へ
4. P1 ステップ 5 の「固定列挙 2 本と一致」が実測確定規定と競合(裁定次第で超える) → 正 = 委任前に固定した期待失敗集合へ統一
5. P1 帰属なし 0 の検査がステップ 5 のみでステップ 6 の oracle・seal 差分が漏れる → ステップ 7 に最終 diff との全件再照合を追加
- 指摘の過半が前周反映箇所への深掘り(H-22 型)— 5 周目の扱いを PO へ提示

### 計画レビュー 5 周目(差分限定・最終周 — PO 裁定 2026-09-03)— 否決(P0×1・P1×3)・全件採用

1. P0 検査器の母集団が関数・クラスのみで認可判定を規定する定数群(CLASSIFICATIONS・ROUTE_CLASSES・REQUIRED_* 等)が漏れる → モジュールレベル定数を母集団へ追加
2. P1 ステップ 1 合格条件が「全 15 資産」のままで §4-(3) の拡張と不一致 → 「全対象」へ統一
3. P1 変更履歴行の分類検査が集計分布のみで誤適用を検出できない → レコード単位の個別照合をステップ 5 合格条件へ
4. P1 最終再照合が片方向 → 双方向(diff→帰属表・帰属表→diff の両差集合 0)へ
- **P0 例外の適用**: 差分限定の確認周をもう 1 周のみ実施(6 周目 — 反映 4 箇所の差分限定・P0 再発時のみ継続)

### 計画レビュー 6 周目(差分確認周)— 承認可・指摘なし → 収束

- 総括: レビュー 6 周(反映 5 周 + 収束確認 1 周)・指摘 39 件(P0×9・P1×25・P2×2)**全件採用・不採用 0**。計画レビュー周回 = 5

### 計画承認(2026-09-03・山田正輝)

- **承認: 済** — frontmatter 更新・承認コミット
- Notion へ計画書リンク・承認日をコメントし、本文 DoD を計画 §5 と同期(P2-12 の規定 — 同期実施を本記録で監査可能化)

## 未決・次の一歩

- /implement ステップ 1(P0 の再列挙 — 敵対レビュー再実施)から実行

## 実装(2026-09-03〜)

### ステップ 1 — 全対象の敵対レビュー再実施(P0 の再列挙)

- 敵対レビュー(sol xhigh)実施 — **P0×14・P1×2(16 件)**。旧要約 3 カテゴリとの対応: 分類 6 / closed-world 2 / 結線 4 / 新規 4(当時の「7 件 + ほか」と整合する規模)
- **H-53 統制の機械検査(両方合格)**: ①走査の全数性 = レビュアーの母集団 3,920 件(per-asset 件数 + sorted リスト sha256 `6aa7908f…`)が Claude 独立列挙 `review-universe-claude.txt` と**完全一致**(レビュアー側の保存は read-only sandbox で不可 — sha256 申告で代替)②指摘 ⊆ 母集団 = 対象 ID 48 件すべて帰属・混入 0
- **PO 裁定(2026-09-03・全指摘に裁定・未裁定 0 — 正は `step1-rulings.json`)**: 採用 12(F2〜F8・F12〜F16)+ 部分採用 3(F1 分割のみ / F9 disposition のみ / F10 contract_only 化のみ)+ 別起票 1(F11 全体)。衝突規則 (a) 該当 4 件の後続の扱い: F1 の client location = 通常起票(ブロッカにしない)/ F9・F10・F11 の新設系 = **TSK-250 の開始条件へ紐付け**(ステップ 7 で起票)。F8 は「帰属訂正であり design-origin 再設計と衝突しない」と裁定し採用
- **§4-(5) 発動**: 採用項目が検査意味論 6 単位((i)罠実効化 (ii)closed-world 構造 (iii)結線閉包 (iv)DDL 意味検査 (v)主張分割 schema (vi)probe_executable 判定)にまたがる → ステップ 4 を整数 6 ステップへ分割する計画改訂(差分レビュー 1 周)を次に実施
- 成果物: `step1-findings.md`(指摘全文)/ `step1-rulings.json`(裁定リスト = ステップ 2 以降の確定範囲)/ `review-universe-claude.txt`(母集団 3,920 件)/ `enumerate_universe.py`(列挙規則の正)

### 計画改訂 1(分割 — §4-(5) 発動・2026-09-03)

- ステップ 4 を検査意味論 6 単位(ステップ 4〜9)へ分割し、旧 5/6/7 → 10/11/12 へ繰り下げ。本文のステップ番号参照 21 箇所を一括更新(§2・§3・§4-(2)(3)(5)(6)・§5・§6)
- ステップ 12 の起票へ裁定 (a) 分 4 件(F1 client location・F9 cache 行列・F10 管理経路 universe・F11 シナリオ行列 — 後者 3 件は TSK-250 開始条件へ紐付け)を追加
- 次: 分割改訂の差分レビュー 1 周(§4-(5) の規定)

### 計画改訂 1 の差分レビュー(1 周・§4-(5) 規定)— P1×1・採用

1. P1 F12・F13(oracle 資産 = ddl-elements・attack-tree)の是正がステップ 10 に誤配置・攻撃木が 10/11 へ重複 → F12・F13 をステップ 11 へ一意に配置(ステップ 10 から除去)
- 計画レビュー周回 = 6。改訂 1 はこれで確定 — 実装をステップ 2 から再開

### ステップ 2 — 要件書 NFR-018 例外表の 2 セル更新

- 開始状態: `uv run pytest tests/` **844 passed(全 green)**を実測
- 変更: 検証テストセル(未整備 → `courseCoordinateContract.spec.ts`)/ 状態セル(有効化待ち → 有効)/ 変更履歴 1 行(版 2.4 のまま・7.6-3 前段の根拠を記載)/ README 最終更新日。他セル・他行はバイト単位で無変更
- **期待失敗集合(委任前固定)**: `test_repository_catalog_covers_the_entire_requirements_file` の 1 本(source_blob_digest 不一致)— **実測一致**(derived/oracle への推移なし・53 passed / 1 failed)

### ステップ 3 — 採取器のインデント表対応 + 負例(codex 委任)

- テスト先行: 負例フィクスチャ `indented-tables.md`(1 スペース・4 スペース・タブ × ヘッダ/区切り/データの機械列挙)+ `test_indented_table_rows_are_extracted_by_kind` — **是正前 red(paragraph に落ちる実出力)→ `_table_cells` の lstrip 対応(kind 判定のみ・source_text は原文保持)→ green** を実出力つきで確認
- 回帰: `tests/test_check_authz_catalog.py` 54 passed(意図的 red の統合テスト 1 本のみ除外)・ruff green
- 期待失敗集合: 変わらず catalog 統合テスト 1 本(想定どおり)

### ステップ 4 — 意味論(i) 分類規則の罠の実効化(F5・codex 委任)

- テスト先行: 負例 `empty-auth-rule.json`(適用条件全空の AUTH 規則)→ **是正前 red(returncode 0 で素通り)→ `_parse_classification_rules` へ「AUTH 規則は適用条件を最低 1 つ」検査を追加 → green** を実出力つきで確認
- フィクスチャの AUTH 規則へ適用条件を最小追加(lock digest 追随含む — tests/fixtures 範囲内)。回帰 55 passed(意図的 red 1 本除外)・ruff green

### ステップ 5 — 意味論(ii) closed-world 専用構造(F6・codex 委任)

- スキーマ確定: claims の任意フィールド `closed_world = { universe_kind(resource|route|operation の閉集合), member_source_ids(実在主張 ID との exact-set・空不可), default_disposition(deny) }`。decision digest・lock に含める(決定の一部)
- テスト先行: 負例 3 種(member 不一致・空 universe・列挙外 kind)red → 実装 → green を実出力つきで確認。正例フィクスチャ追加。回帰 56 passed・ruff/ty green
- 実資産への宣言付与はステップ 10(本ステップは任意フィールドのため実資産の失敗理由は増えない)

### ステップ 6 — 意味論(iii) 結線の閉包(F7 + F9 採用分・codex 委任)

- スキーマ確定: route-registry へ `claim_dispositions[]`(source_id・location〔http|cache〕・disposition〔routed|out_of_registry〕・reason_code〔design_pending_task|cache_matrix_pending〕)。逆向き閉包 = HTTP 主張は結線か disposition の**ちょうど一方**・cache 主張は必ず明示 disposition・二重登録と未知 ID を拒否
- テスト先行: 負例 3 種 red → 実装 → green。正例(routed/http disposition/cache disposition)追加・route lock へ disposition を独立 entry 化
- **期待失敗集合の更新(完全列挙)**: 既知 1 本 + 新規 3 本(`test_repository_derived_assets_are_valid`・`test_all_db_claim_correspondences_reject_one_entry_removal`・`test_all_registry_matrix_links_reject_either_side_removal`)= 計 4 本 — いずれも実資産の claim_dispositions 未追随由来で想定内(ステップ 10 で解消)。除外回帰 55 passed・ruff/ty green

### ステップ 7 — 意味論(iv) DDL 意味検査(F14・codex 委任)

- policy の command を閉じた値域(SELECT/INSERT/UPDATE/DELETE/ALL)・role_ids を roles 実在参照・predicate を資産内 `predicates` 定義への参照(恒真を宣言できない形)で検査。関数 owner の依存基表 ACL・caller の schema USAGE を exact-set 化
- テスト先行: 負例 5 種 red → 実装 → green(実出力つき)。フィクスチャへ ddl-elements 最小正例を新設
- **期待失敗集合の更新(完全列挙・計 6 本)**: 既知 4 本 + 新規 2 本(`test_repository_oracle_assets_are_valid`・`test_all_cut_set_elements_reject_one_element_removal` — 実資産 ddl-elements の predicates 未追随由来・ステップ 11 で解消)。全スイート 6 failed / 845 passed・ruff/ty green

### ステップ 8 — 意味論(v) 主張分割の schema(F1 採用分・F2・F3・F4・codex 委任)

- スキーマ確定: claims の任意フィールド `atomic_claims[]`(`atomic_id = <source_id>#<識別子>`・行内/全体で一意・source_id と衝突不可)。分割行の layer/decidable_at は **atomic 側が正**(行本体は classification: auth_claim の代表値のみ・rule_id は atomic 側に実在する代表値)。**分割行は下流で行 ID を参照できず atomic_id 参照が必須**(曖昧さの排除)。決定投影・lock に包含。client 系 location は新設せず(F1 裁定どおり)
- テスト先行: 負例(重複 atomic_id・値域外・行本体矛盾・未知参照)red → 実装 → green(実出力つき)。下流参照つき正例フィクスチャ追加
- 全スイート 6 failed / 847 passed — **red の増減なし**(期待どおり)・ruff/ty green

### ステップ 9 — 意味論(vi) probe_executable 判定規則(F10 採用分・codex 委任)

- probe_executable の宣言に実行面の裏付け(route/management_operation 結線 or DDL 実行対象への対応)を必須化。裏付けのない主張は `contract_only` + 閉じた理由コードの宣言を強制(無宣言・裏付けなしは fail)
- テスト先行: 負例 red → 実装 → green(実出力つき)。回帰 59 passed(既知 red 6 本除外)・全スイート 6 failed / 849 passed — **新規 red なし**(claim-mutant-map への新エラーは DDL 検査が先に停止するため未表面化 — ステップ 11 の追随対象)・ruff/ty green
- 意味論ステップ(4〜9)完了 — 検査器の強化は全 6 単位が負例 red→green つきで導入済み

### ステップ 10(1 回目委任)— Codex がブロッカーとして正しく停止・計画改訂 2

- 検査器 `check_authz_catalog.py:1879` の「legacy route は design origin 必須」強制が F8 の帰属訂正と矛盾(--skip-oracle でも必ず到達)。Codex は資産を変更せず停止(green を無理に作らない — 正しい挙動)
- **この強制自体が F8 が指摘した誤帰属の焼き込み**であり、是正は F8 採用裁定の従属変更(新しい独立意味論ではない・checker は §2 の変更対象集合に含まれる)。**計画改訂 2(軽微)**: ステップ 10 の記述へ従属変更を明記(「要件由来 origin + 既定拒否主張への結線必須」へ・負例 red→green つき)。PR の総合敵対レビューで最終確認する

### ステップ 10 — 実資産の一括追随(codex 委任・従属許可 3 件を経て完了)

- 委任は 4 往復: ①F8 と検査器の legacy-origin 強制の矛盾で正しく停止(→計画改訂 2)②変異回帰 4 本の走査一般化の許可 ③execution-support helper の ID 整合の許可 ④完了
- **資産追随の内訳**: 分割適用(F1〜F4・F15 — atomic 11 件・判定単位 184 行 → 195)/ F8 帰属訂正(13 routes = requirement origin + FR-034 既定拒否行へ結線・検査器の誤強制を「要件由来 + 結線必須」へ是正〔負例 red→green〕)/ F6 closed-world 宣言 3 件(route/resource/operation universe・deny)/ claim_dispositions 185 件(http design_pending_task 165・cache cache_matrix_pending 20)/ F5 規則値 = 使用実績から機械導出 / 採取追随(NFR-018 3 行 → table 系 ID)/ 変更履歴行の採取(total 1063)/ manifest.commit = d485abc / reseal 実行順どおり(--reseal → --reseal-derived・各 --skip 付き)/ 期待件数更新(変異母集合は判定単位 195 の機械列挙へ一般化)
- **Claude 独立検証(全合格)**: `--skip-oracle` green を自ら実行 / python 直接計数(total 1063・auth 184・out 879・kind 分布が research 予測と一致・判定単位 195・db 187/http 195/cache 20)/ 変更履歴行 `CHANGELOG/table_row-028` = OUT_DOCUMENT_METADATA(既存 29 行と同一規則 — 個別照合合格)/ **帰属表 `attribution.json` = 568 変更単位・帰属なし 0**(生成器 `gen_attribution.py`・基準 41884a9)
- 期待失敗集合: oracle 起因 3 本のみ(catalog 統合〔oracle 到達〕・oracle 統合・cut_set 変異 — いずれも ddl-elements の predicates 未追随由来。ステップ 11 で解消)— 全スイート 3 failed / 853 passed・ruff/ty green
