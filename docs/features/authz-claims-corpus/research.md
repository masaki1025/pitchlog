---
feature: authz-claims-corpus
type: research
date: 2026-09-03
---

# 調査メモ: TSK-270 要件主張母集合のマージ後レビュー P0 7 件の是正(TSK-312)

## 問い

1. P0 7 件の一次記録(個別列挙)はどこにあるか
2. 母集合と派生資産の現物構造・検査系・再生成導線はどうなっているか(是正の連鎖範囲)
3. TSK-233 申し送り(NFR-018 例外表 2 セル・インデント表の採取欠陥)の現物と適用可否
4. TSK-278 の甲-1 裁定との順序制約はどう解くか

調査体制: decision-tracer / spec-checker / Explore の 3 並列 + Claude 本体による GitHub PR #33・Notion TSK-270 コメント・git log 本文・過去セッション scratchpad の横断確認。

## 結論(要約)

1. **P0 7 件の個別列挙の一次記録は現存しない**(リポ・GitHub PR #33〔コメント 0 件〕・Notion TSK-270 コメント 5 件・git log 本文・過去セッション scratchpad のすべてで不在を確認)。耐久記録は要約 1 箇所のみ: 「分類と `decidable_at` の誤り・closed-world 文の落ち・経路レジストリと要件行の結線ほか」(worklog 2026-09-01 :266-267)。→ **本タスクは母集合への敵対レビューを再実施して P0 を全数列挙し直す**(既知 3 カテゴリとの突合つき)
2. 3 カテゴリの構造的裏付けは現物で確認済み: ①分類の罠が無力(`allowed_source_kinds: []` = 制約なし)②closed-world 文に専用フィールドなし ③http 判定可能 184 件中 **166 件が経路レジストリ未結線**・cache 17 件は下流資産ゼロ(db のみ exact-set)
3. インデント表の採取欠陥は `scripts/check_authz_catalog.py` の `_table_cells`(:229-232 — 行頭を strip せず判定)が原因。対象はリポ全体で要件書 :904-906 の 3 行のみ。修正すると source_id 3 件 → lock → 派生 3 資産 → oracle-seal へ連鎖
4. 順序制約: **TSK-312 は develop の要件書 v2.4 blob(digest `38a9bc67…`)に対して是正**し、先にマージする。TSK-278(未マージ・v2.6 approved 済み)のステップ 10 が TSK-312 マージ後の母集合を起点に v2.6 blob へ 1 回だけ追随する(甲-1)。母集合更新は `_verify_manifest_commit` の制約により**複数の基準コミットを順に作る 2 段構え**(新 blob コミット → seal 更新)

## 詳細と典拠

### 1. P0 7 件の一次記録 — 不存在の確認(4 方向)

| 探索先 | 結果 | 典拠 |
| --- | --- | --- |
| リポ内文書(worklog・plan・台帳・features 横断) | 集計数+3 例示+「ほか」のみ。個別列挙なし | `docs/worklog/2026-09-01-course-coordinate-contract.md:266-267`(唯一の内容記述)/ `docs/development/harness-evaluation.md:752`・`:766` / `docs/features/course-coordinate-contract/plan.md:177` |
| GitHub PR #33 | コメント 0 件・レビュー 0 件(`gh pr view 33` / `gh api pulls/33/reviews` 実測) | PR https://github.com/masaki1025/pitchlog/pull/33(2026-08-31 マージ) |
| Notion TSK-270 コメント(全 5 件・resolved 含む) | 申し送り(P0 候補 8 件目)と経過記録のみ。7 件の列挙なし | コメント id `3cd93b75-e687-81ce-8a35-001de470607a` ほか |
| git log 本文(origin/develop・2026-08-30 以降) | 該当 1 件 = `12b4121` の合流根拠(要約のみ) | `git log --grep='P0 7'` 実測 |
| 過去セッション scratchpad(/tmp 4 セッション) | 母集合レビュー出力なし(該当ゲート出力はハーネス設計書のもの) | /tmp/claude-1000/-home-ymdms-projects-pitchlog/ 実測 |

なお worklog :348 の「P0 候補 8 件目」という表現から 1〜7 件が Notion 側で管理されている可能性を検討したが、TSK-270 の全コメントを取得して確認した結果、列挙は存在しなかった。**マージ後敵対レビューの出力は当時のセッションの scratchpad にのみ存在し、消失した**と判断する。

**帰結**: 7 件の復元は不可能であり、**再列挙(母集合への敵対レビューの再実施)が唯一の正攻法**。再実施は当時より条件がよい — ①既知 3 カテゴリを観点として持てる ②本調査で構造的裏付け(下記 2)が取れている ③要件書は develop の v2.4 のまま(blob 一致)で凍結時と同一入力。

### 2. 既知 3 カテゴリの構造的裏付け(現物)

| P0 カテゴリ(要約より) | 現物の確認結果 | 典拠 |
| --- | --- | --- |
| 分類と `decidable_at` の誤り | 全 AUTH 分類規則の罠が `allowed_source_kinds: []` / `forbidden_source_text_patterns: []` で、`_validate_rule_applicability` は空集合を「制約なし」と解釈(= 罠が無力)。実例: 例外表の区切り行 `NFR-018/paragraph-002` が `OUT_NON_AUTH_REQUIREMENT`(本来は構造行) | `scripts/check_authz_catalog.py:633-642` / `contracts/authz/requirement-claims.json`(該当レコード) |
| closed-world 文の落ち | 全域性宣言(例 `FR-034/heading-002/paragraph-003`「この3つで制御資源の認可は全域である」)が通常の `auth_claim` と区別されるフィールドを持たない — 全域性が検査に使われない | `contracts/authz/requirement-claims.json` 実測 |
| 経路レジストリと要件行の結線 | 結線は `source_claim_ids`(片方向)のみで、検査は未知 ID の拒否だけ(母集合側からの閉包検査なし)。**http 判定可能 184 件中 166 件が未結線**。cache 17 件はどの派生資産にも流れない。db のみ `validate_auth_catalog` が exact-set(177 件) | `scripts/check_authz_catalog.py:1159-1173`(`_validate_source_claim_ids`)/ `:1601-1607`(exact-set)/ 件数は Explore 実測 |
| (8 件目候補)インデント表の採取欠陥 | 下記 3 | — |

### 3. インデント表の採取欠陥(P0 候補 8 件目)

- 原因: `_table_cells`(`scripts/check_authz_catalog.py:229-232`)が `line.startswith("|")` で判定し行頭空白を strip しない → `_source_kind`(:278-300)の table 系判定をすべて外れて :300 の `paragraph` フォールバックに落ちる
- 対象: リポ全体でインデントされた表行は**要件書 :904-906 の NFR-018 例外表 3 行のみ**(`grep -c '^[[:space:]]\+|'` = 3。3 行とも半角 4 スペース)
- 現在の採取結果: `NFR-018/paragraph-001`(ヘッダ)/ `paragraph-002`(区切り — `OUT_NON_AUTH_REQUIREMENT`)/ `paragraph-003`(データ行 — `OUT_AUTHZ_CONTEXT_ONLY`)
- 修正の連鎖: kind が変わると `source_id` が変わる(`extract_source` :344)→ 母集合 3 レコード + lock 3 決定 + aggregate digest → 派生 3 資産の `input_manifest`(blob digest 2 件)→ 派生 3 lock → oracle-seal の `input_assets` 8 件。`item_counts_by_kind` は paragraph 32→29 / table_header 24→25 / table_delimiter 24→25 / table_row 192→193
- 一次記録: `docs/worklog/2026-09-01-course-coordinate-contract.md:282-292` / `docs/features/course-coordinate-contract/plan.md:184-189`

### 4. NFR-018 例外表 2 セルの申し送り(TSK-233)

- 現物: 要件書 :904-906(全行 4 スペースインデント)。データ行 1 行のみ。検証テスト = 「**未整備**(…)」/ 状態 = 「有効化待ち」
- 申し送り内容: 検証テスト → `frontend/src/lib/courseCoordinateContract.spec.ts` / 状態 → `有効`。**終了証跡・失効判定者・対象シンボル・対応する契約値はバイト単位で無変更**。版は上げない(7.6-3 前段)(`docs/worklog/2026-09-01-course-coordinate-contract.md:300-309`)
- 適合判定(spec-checker): テストは実在し契約値との一致を固定(`frontend/src/lib/courseCoordinateContract.spec.ts:7-13` / `contracts/display_geometry_263_v1.json:3`)。(c) 柱書 :902 の例外成立条件を満たす。有効化と失効(卒業 = TSK-275)は別事象で終了証跡欄未記入と整合(`docs/adr/ADR-003-domain-calc-method.md:391`)
- **要注意(計画で扱う)**: :902 が「本書の改訂を要する」と列挙するのは**追加・削除・失効の 3 つだけ**で、「有効化待ち → 有効」の状態更新は列挙外。状態欄の値定義も要件書にない。ゲート区分(7.6-3 前段でよいか)の根拠条文が要件書側になく、TSK-233 の人間判断(2026-09-01・版を上げない)が現時点の根拠
- 母集合への影響: 当該行は `NFR-018/paragraph-003` として `source_text` に**先頭 4 スペースを含めて**格納(`contracts/authz/requirement-claims.json:11167`)。セルを 1 文字変えると digest 連鎖が発火(H-85)。**採取欠陥の修正(kind 変更)と同時に行うと source_id ごと変わる**ため、両是正は同一ステップで扱うのが合理的

### 5. 資産地図と検査系(Explore 実測 — 現状は全 green)

- `contracts/authz/` 15 ファイル = 層 A 母集合(`requirement-claims.json` 1,062 件 + lock)/ 層 B 派生 3 資産 + 3 lock(routes 37・management_operations 8・auth-catalog 177・cells 12)/ 層 C oracle 6 資産 + `oracle-seal.lock.json`(input 8 blob + sealed 6)
- 主張レコード: 共通 7 フィールド + auth_claim のみ `layer`・`decidable_at[]`(location ∈ {db,http,cache}・basis_rule_id・test_owner)。スキーマ強制は `_validate_claim`(:692-760)
- 件数: total 1062 / auth 184 / out 878 / db 177 / http 184 / cache 17。**`tests/test_check_authz_catalog.py` が件数を多数ハードコード**(:320・:567-569・:600-601・:631-633・:678-679・:720・:903-908・:1279-1297 ほか — H-85 の対応案③「件数を資産から読む」は未対応・TSK-270 計画改訂 2 の射程だった)
- `_verify_manifest_commit`(:3718-3751): 「`commit` の指す blob が `source_blob_digest` と一致」を要求 → **正本の変更と母集合追随を同一コミットにできない**(H-85)。oracle-seal は同制約を `oracle_commit`(現在 `38a37ce`)にも課す(:3487-3496)
- 再生成導線: `--reseal` / `--reseal-derived` / `--reseal-oracle`(同時使用不可・:3643-3715)。**母集合 JSON を要件書から生成する機能はない**(分類は人手/委任)。`_build_oracle_seal` は `oracle_commit` を更新しない — **新 8 資産のコミットを先に作り、`oracle_commit` を手で差し替えてから `--reseal-oracle`** の 2 段
- CI: `check_authz_catalog.py` の直接配線はなく、`uv run pytest tests/` 経由の統合テスト 3 本(:300・:885・:1279)。:300-324 は「通常実行で lock 4 本が bytes 不変」まで検査
- 凍結の現在値: `input_manifest.commit = c14ef75` / `source_blob_digest = 38a9bc67…`(**作業ツリーの要件書と一致 — develop は v2.4 のまま**)

### 6. 順序制約(甲-1 との接続)

- 甲-1 裁定(2026-09-03・山田正輝): 本タスク(母集合修正)が先。完了が TSK-278 ステップ 10 の実施前提(`../pitchlog-worktrees/feature-adr003-display-primitives/docs/features/adr003-display-primitives/plan.md:62`)
- **版の視界の裁定**: spec-checker は「v2.6 は存在しない」と報告したが、これは develop 視点。v2.6 は未マージの `feature/adr003-display-primitives` 上で approved 化済み(コミット `1827294`・2026-09-03)。**矛盾ではなく視界の違い** — TSK-312 は develop の v2.4 blob に対して是正し、v2.6 への追随は TSK-278 ステップ 10 の仕事(こちらが本 PR より後にマージされる)
- マージ順: **TSK-312 → TSK-278**。TSK-278 側は develop 上の是正済み母集合を起点に v2.6 blob へ追随する(TSK-278 plan :268 の合格条件「派生資産と lock の digest がステップ 9 の blob と整合」)

### 7. H-53 の教訓(委任設計への制約)

- 「負例 6 種」列挙 → 93% すり抜け /「全数で回せ」→ 委任先が母集合を選ぶ /「**対象集合をファイルから機械列挙・件数を定数で持つな**」→ すり抜け 0(`docs/development/harness-evaluation.md:973-977`)
- → 本タスクの委任プロンプトは**母集合の決め方を機構で縛り**、PR 作成者(Claude)が**件数を独立に数えて照合**する

## 未解決・申し送り

- **P0 の再列挙は本タスクの実装ステップで行う**(計画に「母集合への敵対レビュー再実施 → 全数列挙 → PO 提示」のステップを置く)。既知 3 カテゴリ + 8 件目候補が観点の下限であり、7 件との件数一致は要求しない(当時の 7 件は復元不能 — 再列挙の結果が新しい正)
- 例外表 2 セル更新のゲート区分 = **7.6-3 前段で確定(PO 裁定 2026-09-03)** — TSK-233 の人間判断を再確認のうえ踏襲(「本書の改訂を要する」列挙は追加・削除・失効の 3 つで有効化は列挙外)
- H-85 対応案②(digest 連鎖の 1 段化)・③(件数の非ハードコード化)は「TSK-270 計画改訂 2 の射程」と記録されている(`docs/development/harness-evaluation.md:761-764`)。**PO 裁定 2026-09-03: ②③とも本タスクでは見送り・別起票**(③はハードコードが「資産が黙って変わらない」凍結の役割を兼ねるため、設計未確定のまま P0 是正へ相乗りさせない — 計画ステップ 7 で起票)
- 経路レジストリ未結線 166 件・cache 17 件の扱い: 「結線の閉包検査を入れる」か「未結線を仕様として明記する」かは再列挙の結果と合わせて計画で確定する
