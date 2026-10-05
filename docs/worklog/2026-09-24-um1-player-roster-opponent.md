---
date: 2026-09-24
topic: U-M1 選手・在籍・対戦相手チーム(TSK-393)
branch: feature/um1-player-roster-opponent
---

# 作業ログ: 2026-09-24 U-M1 選手・在籍・対戦相手チーム(TSK-393)

## やったこと

- **着手**(/task-start)。`origin/develop` = `bf8ba5b` 起点で worktree を作成。TSK-393 は担当者・プロジェクトが揃っていたため起票せず、進行中への遷移とブランチ名のコメント記録のみ
- 依存 U-T1(TSK-390)が**完了**済みであることを Notion で確認

## 追記: 計画段階の調査(/investigate)

調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列委任し、
**結論に効く事実はすべて当方が原典で再実測**して [research.md](../features/um1-player-roster-opponent/research.md) へ統合した。
並行して進行管理セッションから検証済みの申し送りを受領し、**相互に原典で突き合わせた**(2 件の相互訂正が発生)。

### 判明した重大事項

1. **U-T1 の公開面は空で、U-M1 は現時点で DB に到達できない** — operation registry・製品 capability・
   越境関数 registry・`TenantContext` 製品 allowlist がすべて空(実測)。埋める所有者は **TSK-424**。
   **依存は正本上「U-T1」だけだが実効的に TSK-424 を含む**
2. **マージは TSK-344 待ち** — 12-4 ゲートの通過条件①(RLS DDL の実スキーマ適用)が未充足
   (`backend/migrations` に該当 DDL 0 件 — 実測)
3. **コア判定はカードより正本が新しい** — 機械判定でコア確定・**降格条件は消えている**。
   **TSK-394 でも同一の古い記述を確認**(葉 6 本が同型と見られる)
4. **TB004 が `change_roster_status` / `roster_status_change` を禁止**(`base-allowlist.json:196`)—
   在籍区分変更を主所有する U-M1 の自然な命名に直撃する。識別子設計に先に効く
5. **U-01 は「型」までで「中身」は葉に残されている** — ページサイズの上限・`limit` の既定値・
   カーソル書式は U-M1 が決める側。TSK-346 従属の暫定規約として記録する(U-00 の前例に倣う)

### 相互訂正(原典で裁定した)

- 当方の「U-M1 の一覧は U-01 の型に乗る」→ **不正確**。型は確定・中身は葉(`u01-dto-base/design.md:150`・`:152`)
- 進行管理側の「降格は 6.3 の確定ゲートでしか起きない」→ **撤回**。降格条件は既に消滅(`product-impl-unit-split/plan.md:313`)

### 扱わないと決めたもの

旧資料間の矛盾 3 件(`game_lineup_snapshot` の有無ほか)は、裁定 `RQ-07`(`data-model.md:2634`)が
「存在しなければ移行 0 件で終わるだけ」として処理済みのため **U-M1 では扱わない**。

## 追記: 計画書の起草と敵対レビュー(反映周 1 周目)

計画書・詳細設計を起草してコミット(`0bb9950`)し、**敵対レビュー**(コア領域 = `gpt-5.6-sol` xhigh・
`codex_run.py review adversarial` 経由)を回した。**判定は否決**(P0 16 件・P1 6 件・P2 1 件)。

### 原典で裁定した重要指摘 2 件 — どちらもレビューが正しかった

- **製品 operation token 型の先行定義は U-T1 契約違反**。`tenant-boundary-enforcement/plan.md:174`(ステップ 9)
  「製品 capability 集合と越境関数 registry は初期値ともに空集合とし…**製品表操作は TSK-424 の表分類から
  生成する capability を受けて初めて有効化する**」、同 `design.md:321`「**ステップ 9 の製品 capability も
  TSK-424 の出力契約に含める**」。→ **実装ステップから token 型の定義を削除**
- **入口と経路の混同**。`data-model.md:2438-2441` が「入口 = method と path の組」「経路 = 同じ `route_id` を
  持つ入口の集合」「**判定・測定・記録の単位は入口**」と定める。→ **「経路表」を「入口表」へ改め、
  分割判定は `route_id` 付与後まで保留**

### レビューを 1 件訂正した

**P0-10(フロントエンド未被覆)は言い過ぎ**。`product-impl-unit-split` の plan.md・design.md に
「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。レビューが引いた `:60` は**やらないこと**の表で、
各単位へ送っているのは **UI の「設計正本」**であって実装ではない。→ **正本は帰属について沈黙している**と整理し、
**U-M1 は射程外**の線を引いて受け皿の空席を人間へ上げる形にした。

### 正本に答えがあった 1 件

**越境テストのファイル名と core paths の衝突**(P0-14)は衝突ではなかった。
`product-impl-unit-split/plan.md:61`「**`.claude/core-areas.json` への paths 登録 | 各核単位が自 PR で行う**」。
→ 名前は `test_roster_boundary.py` のままにし、**paths へ明示登録する**。
**副作用**: U-M1 は `core-areas.json` を編集するので **#74 の `verify_area_path_baseline()` が掛かる** →
**ステップ 1 を単独コミットにする**。

## 決定

- **フロントエンド実装は射程外**(受け皿は正本上空席 — 人間へ)
- **在籍区分キーの値と `system_vocabularies` の seed は別タスクへ**。migration は 5 領域すべてのコア paths で、
  契約 3 の「2 領域以上は例外として明示列挙」に U-M1 は含まれない。キーは U-M2・U-C 系も使う共有語彙
- **`route_kind` の値域決定の所有者は空席**。TSK-380 の射程は既存 37 経路の `test_owner` 再割り当てであって値域拡張ではない
- **D1 を D1a(一覧 200)と D1b(一括変更 50)へ分離**。競合特性が違うため同じ定数を流用しない
- **実装着手は外部依存の着地後**。DTO も含めて今は書かない(在籍区分キーが別タスクへ出たため仮置きになる)

## 未決・次の一歩

- **人間の判断を仰ぐ 5 件**(plan.md 8 節): ① フロントエンド実装の帰属 ② FR-015 の同期面の帰属
  ③ `route_kind` の値域決定の所有者 ④ 在籍区分キーと seed の別タスク起票(索引追加も同 PR が筋)
  ⑤ Notion カードの陳腐化(葉 6 本)
- **承認依頼**を上げる。承認後、外部依存(TSK-424 PR A / PR C・TSK-344・値域・U-A1・別タスク)の着地を待って `/implement`
- **製品コード第 1 号への最短路は U-M1 ではなく TSK-424 PR A**(capability カタログ)

## 2026-10-05 ステップ 2(契約資産・検査器・派生 lock)

- 経路 6 本を `route-registry.json`・`http-route-matrix.json` へ追加。派生 lock の entries は registry 230→236・matrix 49→55(各 +6 行)。既存行の判定・digest は不変。`cells` は共有データ経路だけの検査対象なので 12 件のまま
- 新規行の `test_owner.id` は既存行の命名(`TSK-217.http-route.<matrix_route_id>`)に揃え `status: planned`。ステップ 8 で実テストへ結ぶときに見直す
- fixture 側の lock は fixture の JSON が変わらないので更新不要
- 検査器の期待集合を 6 本の独立リテラルへ。負例(期待集合外・導出規則違反〔接頭辞違い・空資源〕)を追加

### 期待失敗(全件実行で確定 — `tests/test_check_authz_catalog.py` 31 失敗 / 129 成功)

**A. oracle 封印の不一致 — ステップ 3・4 で解消を確かめる(2 件)**

- `test_repository_catalog_covers_the_entire_requirements_file`
- `test_repository_oracle_assets_are_valid`
- 通常の `scripts/check_authz_catalog.py` は `contracts/authz/route-registry.json: oracle input blob が不一致` の 1 件で落ちる(`--skip-oracle` では `routes=43 cells=12` で ok)

**B. 本ステップと無関係 — 変更前の HEAD でも同じく落ちる(29 件・抜き取りで確認)**

- 原因: `backend/tests/test_authz_runtime_contract_repository.py:46-73` が `git rev-list HEAD -- contracts/authz/product/ddl-elements.staged.json` で staged 資産の履歴を探すが、本ブランチは staged 資産が生まれる前に develop から分岐し、#87(staged を削除)後の develop を取り込んだため、履歴の単純化で develop 側が辿られず 0 件になる(develop 上では 3 件見つかる)
- PR の CI(merge ref は develop が第 1 親)では辿れる見込み — **推論・未検証**。ブランチの位相に依存する脆さとして別途起票を検討
- `test_product_runtime_contract_mutations_are_rejected[provisional-additions]`
- `test_pending_state_always_runs_only_pending_protected_validation`
- `test_invalid_runtime_contract_state_is_catalog_error`
- `test_provisional_state_has_no_product_ddl_path`
- `test_fixture_has_a_valid_multi_layer_claim`
- `test_mutation_1_deleted_known_clause_is_red`
- `test_mutation_2_unregistered_authorization_clause_is_red`
- `test_mutation_3_added_table_row_is_red`
- `test_mutation_4_added_layer_without_test_owner_is_red`
- `test_mutation_5_auth_claim_moved_to_out_of_scope_is_red`
- `test_mutation_6_deleted_whole_section_is_red_by_heading_manifest`
- `test_additional_mutation_unregistered_plain_paragraph_is_red`
- `test_missing_classification_is_red`
- `test_free_form_classification_reason_is_red`
- `test_empty_auth_rule_applicability_is_red`
- `test_invalid_closed_world_declarations_are_red`
- `test_scalar_decidable_at_is_red`
- `test_missing_layer_is_red`
- `test_line_number_based_stable_id_is_red`
- `test_source_text_digest_drift_is_red`
- `test_source_blob_digest_drift_is_red`
- `test_manifest_start_and_end_must_match_closed_heading_set`
- `test_basis_rule_id_is_a_closed_required_value`
- `test_decision_lock_reports_source_id_and_changed_field`
- `test_normal_validation_never_reseals_a_changed_decision`
- `test_normal_validation_does_not_create_a_missing_lock`
- `test_reseal_updates_decisions_only_with_the_explicit_flag`
- `test_aggregate_decision_digest_detects_a_changed_lock_entry`
- `test_atomic_claim_fixture_is_valid_and_referenced_downstream`
