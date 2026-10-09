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

## 2026-10-05 ステップ 3(oracle の追随と人間の確認)

- `oracle_commit` 7 箇所(`oracle-seal.lock.json` 1 + `attack-tree` / `boundary-proposal` / `claim-mutant-map` / `ddl-elements` / `rejected-configs` / `verification-evidence`)を `70621e33…` → ステップ 2 の `98ad97de2f796e1e9f12257d848b7c652e6e352a` へ。リポジトリ全体の grep で宣言はこの 7 箇所だけ(台帳中の旧 SHA は履歴値なので維持)
- digest 連鎖: `failure-injection-points.json`(→ `ddl-elements.json` = `ad8cb1b1…`)・`mcdc-map.json`(→ `claim-mutant-map.json` = `f9ef489e…`)。`git hash-object` で一致を確認。`check_failure_injection_points.py` OK(5)・`check_mcdc_map.py` OK(47)
- **N5 の結論: oracle 資産の内容追随は不要**。新 6 経路は `source_claim_ids` 空・`disposition: conditional` で HTTP 行列の `cells` は不変(12)。claim-mutant-map の正例は `cells`、管理主張は `management_operations` から導出(`scripts/check_authz_catalog.py:5709`)、attack-tree は mutant 結果(`:6223`)、boundary-proposal は AUTH catalog と凍結台帳(`:6544`)、verification-evidence は既存 probe の検証結果(`:6674`)を対象とし、いずれも経路集合を入力に取らない
- **敵対レビュー**(`codex_run.py review adversarial`・5 軸 — N5 / oracle_commit の意味論 / digest 連鎖 / 期待失敗 / ステップ 4 への持ち越し): **承認可・指摘 0 件**。持ち越し事項 — ステップ 4 の記録は SHA 移動のみなので `changes: []`・`placement_change` は前後同値・`moved: false`(#77 の「最低 1 件」は後続で訂正済み — `scripts/check_frozen_baselines.py:418`)。`test_normal_validation_never_reseals_a_semantically_valid_drift` は HEAD を clone するので**ステップ 4 のコミット後に再実行**する
- **人間の確認: 2026-10-05・山田正輝**(差分 9 ファイル各 1 行と N5 の結論を確認)

### 期待失敗(ステップ 4 で解消を確かめる)

- `check_authz_catalog.py`: `boundary proposal の oracle_commit が基準版と不一致`(台帳の最新 `oracle_input` が旧 SHA)。seal 直検査では `route-registry.json: oracle input blob が不一致`
- `check_frozen_baselines.py --invariants-only`: `history.oracle_input.new_identity が戦略の導出値と不一致`
- `tests/test_check_authz_catalog.py`: 37 失敗 = ステップ 2 の 31(A 2 件 + B 29 件)+ 新規 6 件 — `test_boundary_owner_population_and_final_values_are_closed` / `test_owner_mutations_pass_when_the_owner_check_is_removed` / `test_boundary_and_review_ids_reject_duplicate_rows_before_folding` / `test_s5_mutations_pass_when_the_decision_check_is_removed` / `test_g_duplicates_pass_when_the_new_multiplicity_checks_are_removed`(boundary-proposal の不一致)・`test_normal_validation_never_reseals_a_semantically_valid_drift`(HEAD の oracle 入力が未封印)
- **N3 の決定(2026-10-05・山田正輝)**: draft PR を先に作って番号を確定する(#77・#87 の前例どおり)

## 2026-10-05 ステップ 4(凍結基準の記録と oracle の再封印)

- `frozen-baselines.json` の `history` へ 1 件: `acceptance_id: masaki1025/pitchlog#95` / series `oracle_input` / `70621e33…` → `98ad97de…` / `changes: []` / `placement_change` 前後同値 / `moved: false` / `approved_by: 山田正輝` / `approved_at: 2026-10-05`(承認値は 2026-10-05 に人間へ提示し了承)
- `--reseal-oracle` で再封印。`check_authz_catalog.py` ok / `check_frozen_baselines.py --invariants-only` OK / `check_failure_injection_points.py` OK / `check_mcdc_map.py` OK / `tests/test_frozen_baseline_*.py` 6 passed / `tests/frozen_negatives/` green
- ステップ 2・3 の期待失敗のうち oracle 系 8 件は解消(うち `test_normal_validation_never_reseals_a_semantically_valid_drift` はコミット後の再実行で確認)。残るのは履歴位相の 29 件(B)のみ

## 2026-10-05 ステップ 5(リポジトリと operation token・7.7-2 の記録・比較 corpus の再封印)

- **契約**: `repository-contract.json` の `product_capability_ids` を 6 件(`CAP:{players,team_records}:{read,insert,update}`)、`product_operation_token_types` を 6 件に。`contract_revision` 9 → 10。既存 history は保持。生成モジュール `repository_contract.py` を同期した
- **権威履歴**: `base-allowlist.json` の `baseline_control.history` へ 1 件(`acceptance_id: masaki1025/pitchlog#95`)。影響する凍結資産 9 件の前後 snapshot(新 `history-snapshots/0ad989ea…`)。承認値は 山田正輝 / 2026-10-05
- **比較 corpus**: manifest の digest を `3174c650…` へ。runner は前版(固定 SHA の detached・清潔な worktree)と現版の両方で 11/11 一致
- **実装の形**:
  - 登録型 `operation_registration.py` と製品登録表 `operation_registry.py` を置いた。基底(`base.py`)は製品の種類を知らない
  - 準備と検査は `_prepare_operation` 1 箇所にまとめ、base と transaction の両方の経路が通る
  - 表定義は ORM の `__table__` を使う
- **実行直前の検査**(登録時と同じ capability 検査器を再利用する):
  - 単一の実表に限る(別名・結合・CTE・入れ子は拒否)
  - 操作の種類が capability と一致する
  - `tenant_id = :tenant_id`
  - UPDATE は `id = :id` が必須
  - 必須の追加条件(チーム操作の `kind = :kind`)
  - 一覧は LIMIT の束縛値の上限が 201(DTO 定数 `ROSTER_PAGE_SIZE_MAX` から導出)
  - UPDATE は token ごとに許可した SET 列に限る(`hidden_at`・`team_record_id` は不可 — 論理削除はステップ 10・11)
- **検査器の補強(計画の範囲内 — 内訳 5「登録文の検証に通す」)**: `backend/src/pitchlog/authz/capability_registration.py`
  - 見落としを直した: Column 経由の別表参照
  - 追加した: 単一の実表に限る形の検査(`_validate_single_target_table_shape`)
  - 検査器自身のテストに負例を足した
- **敵対レビュー 5 周**:
  - 1 周目: P1 2 件・P2 1 件(対象表 / UPDATE の ID 条件 / INSERT の負例)
  - 2 周目: P1 1 件(同じ表の別名で直積 — 他テナントの行を引けることを実測)
  - 3 周目: P1 2 件・P2 2 件(transaction 経路の退行 / kind 条件 / LIMIT / count の誤拒否)
  - 4 周目: P1 2 件(LIMIT の上限 / SET 列)
  - 5 周目: **P0・P1 なし**。ここで収束とした
- **持ち越し(P2)**:
  - ① DTO の `name` は空文字を受理するが token は拒否する → **ステップ 8**(DTO→token の変換を作る入口)で値域を揃える
  - ② SET 列の重複キー(文字列と Column)と、値の出所(`SET name = players.hidden_at`)を検査しない → 将来の組み立て関数変更に対する検出網。現行コードに実害の経路なし
  - ③ `count()` の誤拒否(3 周目)→ 集計を登録する単位で監査して許可する
- **検証**:
  - ルート指定テスト 468 passed
  - backend(DB 不要)240 passed
  - `check_tenant_boundary_bypass` ok / `check_authz_catalog` ok
  - ruff・ty は green
  - **PostgreSQL が要るテスト(`backend/tests/db/test_tenant_transaction_scope.py`・`test_authz_tenant_binding.py::test_repository_base_binds_and_emits_explicit_tenant_predicate` — fixture を登録型へ更新)は手元で未実行**。共有 DB を避け、PR #95 の CI で確認する

## 2026-10-05 夜 ステップ 8 の射程の変化と申し送り(第 3 改訂の入力 — 未改訂)

- **人間の裁定 (b')(2026-10-05・山田正輝)**: U-A1 γ(TSK-469)から、次の 4 つが U-M1 のステップ 8 へ移った(原典は `docs/features/ua1-auth-app-layer/plan.md` 4-7 節・コミット `dd9b6d64`)
  1. `contracts/tenant_boundary/tenant-context-allowlist.json` の `allowed_product_modules` への登録
  2. TenantContext の生成モジュール(γ は検証済みのテナント ID〔UUID〕だけを返す)
  3. `scripts/check_tenant_boundary_bypass.py` の「製品モジュールは 0 件必須」の解除
  4. 7.7 の受理記録と snapshot
  - **要注意**: 受理記録は 1 PR につき 1 件(`intermediate_commits_are_records: false`)。ステップ 5 の #95 の記録を導出し直して、1 件にまとめる
- **TSK-457(TenantContext の実行時の封じ込め)**: 235 タブが担当。分界は「0 件必須の解除」で切る案に同意した。登録・解除・記録・生成箇所は U-M1 のステップ 8 が持ち、先後は 457 が先。**ステップ 8 の外部依存に TSK-457 を入れる**(第 3 改訂)。発行モジュールの登録が 457 の時点で避けられない形になったら、457 の計画承認の前に人間の裁定に上げてもらう
- **TSK-480**: ステップ 8 の前に外部依存として入れる(第 3 改訂)
- **feature_status の「ステップ記法が不正」**: 原因は develop 取り込みのマージ `638b796f` の件名「(ステップ 3・4 が要る…」。push 済みで、後続の oracle の記録が SHA で参照しているので書き換えない。表示だけの影響(`/pr` は転記するだけで止めない)。PR 本文で説明する。台帳の候補: 不正形の検査が `is_develop_integration_merge` の判定より先に走る
- **ステップ 5 の持ち越し P2**(再掲): DTO の `name` の空文字はステップ 8 で揃える

### TSK-457 の射程の裁定(2026-10-05・山田正輝 — 469 master 経由)

- **TSK-457** は機構と検査器までを持つ: 公開 constructor の封じ・capability 型・検査器の新しい規則・負例。`allowed_product_modules` は `[]` のまま
- **U-M1 のステップ 8** は、次の 4 つを持つ(裁定 b' の 4 項目のうち、検査器の改修だけが TSK-457 へ移った)
  - 発行専用モジュールの実体
  - 生成許可(`allowed_product_modules`)への登録
  - TenantContext の生成箇所(発行関数を呼ぶ形。直接構築はしない)
  - 7.7 の受理記録
- **受理記録は 1 PR につき 1 件の課題が戻る**: ステップ 8 は `tenant-context-allowlist.json` の中身を変えるので、テナント境界の凍結記録が動く(457 タブの試算では 1 本 +1)。#95 はステップ 5 で記録を 1 件持っているので、**ステップ 8 で記録を導出し直して 1 件にまとめる**(`intermediate_commits_are_records: false`)
- **第 3 改訂で入れるもの**: ステップ 8 の射程(上の 4 つ)・外部依存 TSK-457 と TSK-480・受理記録の 1 件化
- 所有の現行化(12-8 の「テナント文脈の生成 = TSK-469」)は γ の PR で運ぶ見立てを 469 master へ返した。変更履歴の v0.4 の行は記録なので書き換えない

## 2026-10-07 第 3 改訂(ステップ 8 の射程の取り込み)

- **リクエストの認証の帰属(裁定 2026-10-07・山田正輝)**: Cookie から提示値を取り出し CSRF を検査する部分を、δ(TSK-470)から U-M1 へ移す。計画書の起案中に、選手の入口がリクエストを認証する手段の受け取り先が無いことに気づいて人間へ上げた(H-2 の Cookie と CSRF は δ 宛てで、δ は γ・TSK-344・レート制限の具体設計の後)。選択肢は「δ から切り出す(推奨)/ U-M1 が持つ / δ を待つ」で、人間は U-M1 を選んだ
- **ログアウトの入口は γ が持つ**(利用者の裁定 (ア) — 469 master の連絡)。U-M1 の射程外

### 計画レビュー 1 周目(`codex_run.py review adversarial`)— 否決(P0 2 / P1 2 / P2 0)

| # | 指摘 | 重大度 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | 発行関数が γ の戻り値(`UUID | None`)を受けると、生の UUID と区別できず未検証の ID を渡せる | P0 | **採用**。発行関数の入力を提示値にし、γ の公開入口の呼び出しを発行専用モジュールの中だけに置く。ステップ 8 は γ を呼ばない |
| 2 | 0 件必須の置き換え先の期待値の出所が未指定。検査器への直書きは 7.7-1 に反する | P1 | **採用**。期待値は資産の発行入口のシンボルが属するモジュールから導出する。検査器のソースに名前が無いことを合格条件へ |
| 3 | 登録(旧新 9)が入口の開放(旧新 10)より前のコミットになり、U-T1 の禁止に反する(受理記録の数え方とは別の規律) | P0 | **採用**。登録と入口の開放を同じコミット(新 9)に置き、受理記録を新 10 へ分けた |
| 4 | 12-4 の判定記録に、接続先と世代の識別・判定者と日時・入口ごとの `route_id` と method/path が無い | P1 | **採用**。DoD をゲート表「判定の記録」行と「実スキーマ」小見出しの必須項目に沿って書き直した |

### 計画レビュー 2 周目 — 否決(P0 0 / P1 2 / P2 0)。1 周目の 4 件はすべて終結

| # | 指摘 | 重大度 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | 発行関数が γ の `verify_tenant_id` を呼ぶのに、γ のテストが固定する製品の呼び出し元の集合(`test_authz_app_layer_surface.py` の `_PUBLIC_CALLERS`)の更新がステップ 9 に無い | P1 | **採用**。ステップ 9 で発行関数を呼び出し元として 1 件足す。γ の公開操作の集合は増やさない |
| 2 | 12-4 の判定対象の列挙から選手の削除の入口(`DELETE /players/{player_id}`)が抜けている | P1 | **採用**。判定対象を design.md 3 節の入口表の全行とし、ステップ 12 が削除の入口を開くことを明記 |

### 計画レビュー 3 周目 — 可決(P0 0 / P1 0 / P2 0)。2 周目の 2 件は終結

指摘なしの収束確認周のため、`計画レビュー周回` は数えない(10 のまま)。人間の承認を待つ。
- **第 3 改訂の承認: 2026-10-07・山田正輝**

## 2026-10-08 develop の取り込みとステップ 5 の欠陥(第 4 改訂)

- **取り込み**: `8ada3d9d` で `origin/develop`(`1fdf1eec`)を取り込んだ。衝突 2 件(`base-allowlist.json`・比較 corpus の manifest)は develop 側を採り、#95 の記録と snapshot `0ad989ea…` を外した。authz の oracle 入力・封印対象・`frozen-baselines.json` は develop で不変なので、ステップ 4 の記録は有効(`check_authz_catalog` ok・`check_frozen_baselines --invariants-only` OK)
- **再導出の試行**: Codex が #95 の記録を新しい base に対して作り直した(snapshot は内容アドレスで旧 `0ad989ea…` とバイト一致・runner 前版 `ec02a0d2` / 現版とも 11/11)。しかし迂回検査が **TB005 を 9 件**出した。**作業ツリーの再導出は捨てた**(是正で凍結資産が動くので作り直しになる)
- **原因の特定**: `3a4a7297`(ステップ 5)を当時の base `85fce8a7` に対して検査しても同じ 9 件。取り込みとは無関係。`roster.py` がモジュール直下で `select` / `insert` / `update` を使い、`allowed_symbols` にそれを許すシンボルが無い。**ステップ 5 の「`check_tenant_boundary_bypass` ok」はコミット前の検査**で、`roster.py` は未追跡だったため母集団に入らなかった。**PR #95 の CI は 1 度も走っていない**(`no checks reported`)
- **裁定(2026-10-08・山田正輝)**: 文の組み立て関数を `allowed_symbols` に登録する(他案: 基底へ移す / 目録の対象外にする)

### 計画レビュー(第 4 改訂)1 周目 — 否決(P0 0 / P1 4 / P2 0)

| # | 指摘 | 重大度 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | 現 HEAD の履歴に #95 の記録は無い(取り込みで外した)のに「1 件持っている」前提で書いている。`base-allowlist.json` 自身の `contract_revision`・`current_identifiers` の更新も要る | P1 | **採用**。#96 までを保ち #95 を 1 件追記する手順に直し、自身の識別値の更新を明記 |
| 2 | 是正と記録を別コミットにすると、間のコミットでは検査器が履歴の検証で止まり TB005 の有無を判定できない | P1 | **採用**。変更と記録を 1 コミット(`(ステップ 5 是正)`)にまとめた |
| 3 | 「コミット後に実行」だけでは、検査器が契約資産を作業ツリーから読むので混合状態を検査しうる | P1 | **採用**。作業ツリーが清潔で HEAD が対象コミットであることを確かめてから実行し、SHA を記録する |
| 4 | DoD「5 条件すべてに一致 0」が改訂後の条件 5 と両立しない | P1 | **採用**。「許可側を除いた違反 0」とし、判定方法を明記 |

### 計画レビュー(第 4 改訂)2 周目 — 可決(P0 0 / P1 0 / P2 1)。1 周目の 4 件はすべて終結

| # | 指摘 | 重大度 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | tenant_boundary の受理記録の日時キーは `approved_on`(`scripts/frozen_history.py` の v2 record)で、計画書の `approved_at` は誤り | P2 | **採用**(P0/P1 ゼロの周の P2 として一括反映)。内訳 5 の是正と内訳 10 の 2 箇所を `approved_on` に直した。authz の `frozen-baselines.json` は `approved_at` のまま(原典で両方を確認) |
- **第 4 改訂の承認: 2026-10-08・山田正輝**。#95 の受理記録の承認値は前回どおり 山田正輝 / 2026-10-05 を引き継ぐ(承認時に提示し、変更の指示なし)

## 2026-10-08 ステップ 5 の是正(`b167fff1`)

- **実装**(Codex・`--resume`): `roster.py` の組み立てを `_build_roster_statement(kind, operation)` 1 関数へ集め、`allowed_symbols` へ登録(`SQLA_SELECT` / `SQLA_INSERT` / `SQLA_UPDATE` だけ)。正例 fixture 1 件。`base-allowlist.json` 21→22。権威履歴は #96 までを保ち #95 を 1 件追記(`repository-contract.json` 9→10 と `base-allowlist.json` 21→22 を覆う・承認値 山田正輝 / 2026-10-05)。snapshot 2 件(`0ad989ea…`・`75227a89…`)・manifest `4e139505…`。runner 前版 `ec02a0d2` / 現版 11/11
- **コミット前の敵対レビュー**: 可決(P0 0 / P1 0 / P2 2)。P2 2 件(`kind` と token の取り違えを実行時に拒否する — 実行直前の検査は同一表・同一操作での SET 列と `token.changes` の一致までは保証しない / 正例 fixture の分岐値を実装に揃える)を同じ是正に反映し、署名・記録・manifest を取り直した
- **確定した状態での検証**(第 4 改訂の規律): 作業ツリーが清潔で HEAD = `b167fff17e41551df53788259fbabbbdcc11d857` を確かめてから実行
  - `check_tenant_boundary_bypass.py --base-ref origin/develop` ok / `check_authz_catalog.py` ok
  - ルート 4 ファイル 471 passed / backend 3 ファイル 210 passed / backend ruff・format・ty green
- **backend の非 DB 全件**: 手元のブランチでは 34 failed + 10 errors(`test_authz_runtime_contract_generator.py`・`test_authz_runtime_contract_switch.py`、すべて「HEAD の履歴に staged 製品資産がありません」)。原因は**テストの前提が履歴の形に依存すること**: テストは `git rev-list HEAD -- contracts/authz/product/ddl-elements.staged.json` で過去版を探すが、既定の履歴の単純化は TREESAME の第 1 親だけを辿るので、develop を第 2 親で取り込んだブランチ上では 0 件になる(`--full-history` なら 21 件)。**CI と同じ形(develop を第 1 親にした `--no-ff` のマージコミット)では 1040 passed で全件 green** — 本 PR の欠陥ではない。台帳の候補になりうる(develop を取り込んだ作業ブランチ上で既存テストが偽の赤を出す)
- **push と CI**: `b167fff1` を push。**PR #95 で CI が初めて走った**(10 ジョブ)

## 2026-10-08 第 5 改訂(ステップ 6・7 の paths 登録を glob へ)

- **提案**: 469 master(`AREA_PATH_ADDITIONS` は回転式の窓口で 1 本ずつしか通れない。後続 17 単位の越境テストを glob で 1 回に畳む)。点 1(0 件の glob を許すか)は develop に実例 `backend/src/pitchlog/generated/*` があり許す、点 2(命名規約の置き場)は TSK-485 の射程 — いずれも 469 master の実測
- **裁定(2026-10-08・山田正輝)**: glob `backend/tests/test_*_boundary.py` で登録する
- **当方の実測**: `git ls-files` を `fnmatch.fnmatchcase` で照合して当たる追跡ファイルは 0 件(`backend/tests/test_type_boundary_contract.py` は末尾が `_contract.py`)

### 計画レビュー(第 5 改訂)1 周目 — 可決(P0 0 / P1 0 / P2 1)

| # | 指摘 | 重大度 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | 「後続が揃わなくても当たらないだけ」は言い切れない。`*` は `/` を跨ぐので、規約外のファイルが将来当たりうる | P2 | **採用**(P0/P1 ゼロの周の一括反映)。規約外でも当たりうること・その場合はコア領域が広がる側に倒れることを明記し、TSK-485 への申し送りに後続での実パス照合を含めた |

`計画レビュー周回` は 13 へ(指摘反映を伴う周は可決でも数える — 第 4 改訂の 2 周目〔P2 1 件を反映〕を数え漏らしていたので、あわせて訂正した)。

### 承認(2026-10-08・山田正輝)

第 5 改訂を承認。frontmatter の `承認` と 8 節 14 を更新した。

## 2026-10-08 `b167fff1` の CI(PR #95 で初回)

- **tenant-boundary-bypass は合格**(ステップ 5 の是正が CI でも通った)。backend・consistency・docs-lint・mutation・nfr021-append-only・secrets・frontend も合格
- **core-guard は失敗**(想定どおり — draft の間は逐行確認のチェックが未記入)
- **harness は失敗**(想定外): `scripts/check_frozen_baselines.py --ci` が、`backend/tests/test_roster_repository.py` に是正で足した SQL 形状の sha256 の 16 進文字列 11 件を「走査で見つかったが allow-list にない」として拒否した。64 桁の 16 進文字列はリポジトリ全体で凍結値の候補として走査される。**ローカルではこのスクリプトを回しておらず取り逃がした**(ルートの pytest と迂回検査だけを回していた)
- 対処: 形状の比較をハッシュ値でなく SQL の文字列そのものとの照合に替える(ステップ 5 是正の追補)。以後、是正の後は `check_frozen_baselines.py` も回す

## 2026-10-08 `2040ed8d` の CI と第 6 改訂

- **`2040ed8d`(ステップ 5 是正の追補)**: SQL 形状の照合を sha256 値から SQL 文字列へ替えた。置き換え前に 11/11 件のハッシュ一致を確かめ、旧テスト(HEAD 版を一時ファイルに書き出したもの)と新テストを同じコードに当てて両方合格(113 passed)。清潔な HEAD で `check_frozen_baselines.py --ci` OK・迂回検査 ok
- **CI(`2040ed8d`)**: harness が 2 件で失敗(2680 passed)。ほかは core-guard(想定どおり)を除き全合格
  1. `tests/test_core_guard.py::test_all_schema_contract_assets_match_an_actual_core_area_path` — `backend/tests/test_roster_repository.py`(ステップ 5)がスキーマ契約に触れるのにどの paths にも当たらない
  2. `tests/test_check_authz_catalog.py::test_atomic_claim_fixture_is_valid_and_referenced_downstream` — ステップ 2(`98ad97de`)で期待集合を 6 本にしたが、テスト用 fixture `tests/fixtures/authz_claims/route-registry.json` に 6 本が無い(不足 = 6 本)
- **取り逃がした理由**: ステップ 2・5 の検証が対象テストの部分集合だけで、ルートの全件を回していなかった。#95 の CI は `b167fff1` まで一度も合格しておらず(`3a4a7297`・`a5c5f698` も失敗)、失敗の中身を確かめていなかった
- **ステップ 6 の着手時の確認**: `git fetch` のうえで、`scripts/core_guard.py`・`.claude/core-areas.json`・`tests/test_core_guard.py` を変える未マージの ref を走査した。該当は `origin/fix/oracle-input-baseline`(`35d5fdf4`・PR #63 CLOSED・2026-09-16)だけで、`AREA_PATH_ADDITIONS` には触れていない — 競合なし
- **ステップ 6 の下書き**: Codex が宣言を `("backend/tests/test_*_boundary.py",)` にして表明を直した段階で上の 1 が判明。下書きは scratchpad に patch として退避し、作業ツリーは HEAD に戻した(第 6 改訂の承認後に 2 本で作り直す)
- **裁定(2026-10-08・山田正輝)**: リポジトリのテストの glob `backend/tests/test_*_repository.py` を足して 2 本にする
- **第 6 改訂**: 宣言値・登録値を 2 本へ・遡及の確認の書き換え・ステップ 6 の合格条件の例外・ステップ 2 の是正(1 コミット)・push 前の全件実行の規律

### 計画レビュー(第 6 改訂)1 周目 — 否決(P0 0 / P1 1 / P2 0)

| # | 指摘 | 重大度 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | DoD の paths 登録件数が「merge-base ＋ 1 件」のままで、内訳 7 の 2 件と矛盾する | P1 | **採用**。DoD を「merge-base ＋ glob 2 件(順序つき)」にし、遡及の確認の記録を DoD に足した |

観点 1〜3 は該当なし(片方の glob だけ空振りする状態は検査器・既存テストと矛盾しない / `test_*_repository.py` に当たる本単位以外の 1 件は登録前から `tenant-isolation` / fixture の是正は合格条件と全件実行で確かめられる)。

### 計画レビュー(第 6 改訂)2 周目 — 可決(P0 0 / P1 0 / P2 0)。1 周目の 1 件は終結

`計画レビュー周回` は 14 へ(1 周目の反映ぶん)。

### 承認(2026-10-08・山田正輝)

第 6 改訂を承認。frontmatter の `承認` と 8 節 16 を更新した。

## 2026-10-08 ステップ 2 是正・ステップ 6・ステップ 7

### ステップ 2 是正(`482127c9`)

- `tests/fixtures/authz_claims/route-registry.json` に 6 本を追加(契約資産の 6 行と 6/6 一致)。fixture 内で provenance の参照を閉じるため合成の設計文書 `record-and-aggregate-design.md` を追加。派生 lock の fixture を再導出(18→24 entries・既存 18 は不変)
- Codex の報告: 対象 2 モジュールは 153 passed・29 failed(29 件はすべて既知の「HEAD の履歴に staged 製品資産がありません」)。履歴条件を再現した一時 clone で `test_atomic_claim_fixture_is_valid_and_referenced_downstream` 1 passed。同じ fixture を読む他の 3 テスト 3 passed・spec 21 passed

### ステップ 6(`2a5a0f85`)

- 着手時の未マージ ref の確認: 上の「`2040ed8d` の CI と第 6 改訂」のとおり(競合なし)
- 宣言を `("backend/tests/test_*_boundary.py", "backend/tests/test_*_repository.py")` へ。テストは 344 の宣言の固定を JSON 登録済みの確認へ直し、宣言の期待値をテスト側に独立して持ち、4 種の負例(部分追加 `test_one_of_three_tenant_additions_is_rejected`・並べ替え `test_reordered_tenant_additions_are_rejected`・削除 `test_deleting_baseline_tenant_path_is_rejected`・未宣言の追加 `test_undeclared_tenant_path_addition_is_rejected`)を追加
- 敵対レビュー 可決(指摘なし)。4 種の負例がいずれも層不一致の規則で落ちることをレビュー側でも確認
- **検証(清潔な HEAD = `2a5a0f85`)**: `verify_area_path_baseline(Path('.'), '1fdf1eecdfb698eae1afaf24adb025233d084bbb', '2a5a0f85d4a10a416f07f01a6bef1f7fd767e6d8')` → `1fdf1eecdfb698eae1afaf24adb025233d084bbb`(例外なし)。`tests/test_core_guard.py` 214 passed・1 failed(`test_all_schema_contract_assets_match_an_actual_core_area_path` — 第 6 改訂の 3 の例外)

### ステップ 7(`1bd5e33d`)

- **着手前の未マージ ref の確認**(`git fetch` 後・リモートとローカルの refs/heads を走査):
  - `feature/appendix-e-golden-vectors`(ローカル `d76e2cf5`・origin `1636b170`・PR #81 draft OPEN・2026-10-08 更新)— **`AREA_PATH_ADDITIONS` を書き換え、`tenant-isolation` へ `docs/adr/ADR-001-codex-model-selection.md` を宣言している**。本単位の glob とは重ならない。**回転式の窓口なので、後からマージされる側が develop の取り込み時に宣言を自分の未取り込み分だけへ直す**(順序調整の対象 — 該当タブへの連絡を人間に依頼)
  - `fix/oracle-input-baseline`(ローカル `76e98ff0`・origin `35d5fdf4`・PR #63 CLOSED)— `AREA_PATH_ADDITIONS` には触れない
  - `backup/before-subject-fix-20261004`(`47984a3d`)— `core-areas.json` に差分があるが `tenant-isolation` と宣言には触れない
- `.claude/core-areas.json` の `tenant-isolation.paths` 末尾へ 2 本を登録(Claude の直接編集 — review normal 可決・指摘なし)
- **遡及の確認**: `git ls-files` を `fnmatch.fnmatchcase` で照合し、`test_*_boundary.py` は 0 件、`test_*_repository.py` は `backend/tests/test_roster_repository.py`(本単位)と `backend/tests/test_authz_runtime_contract_repository.py`(merge-base の `tenant-isolation.paths` の `backend/tests/test_authz*.py` に当たる)の 2 件だけ
- **独立確認**: `tenant-isolation.paths` が merge-base の列 ＋ 2 本(この順)と完全一致、他の領域・キーは不変(review normal で確認)
- **検証(清潔な HEAD = `1bd5e33d`)**: `verify_area_path_baseline(Path('.'), '1fdf1eecdfb698eae1afaf24adb025233d084bbb', '1bd5e33dcdb24dc8f51ad006bc2ecbd9502400fe')` → `1fdf1eecdfb698eae1afaf24adb025233d084bbb`(例外なし)。`tests/test_core_guard.py` 215 passed(スキーマ契約資産の検査を含む)

### push 前の全件実行(第 6 改訂の 7)

- **CI と同じ形**: 一時 worktree で `origin/develop`(`1fdf1eec`)へ `1bd5e33d` を `--no-ff` マージ(`34b66f8c`)して実行
- `check_frozen_baselines.py --ci`(`GITHUB_EVENT_NAME=push`)OK・迂回検査 ok・`ruff check .` 合格
- ルートの `uv run pytest tests/`: **2930 passed・3 failed**(20 分 55 秒)。失敗は `tests/domain/mut/test_cost_record.py::test_actual_measurement_is_generated_and_passes_both_budgets`・`tests/domain/mut/test_lang_operators.py::test_each_language_mutants_are_actually_killed[sql]`・`::test_sql_mutation_with_unreachable_postgres_is_fail_closed`
- **分類**: 3 件を単独で実行すると、develop(`1fdf1eec`)でも同じマージ状態でも 3 passed。全件実行の負荷の下でだけ落ちる(PostgreSQL と時間予算に依存するミューテーション検査)。本単位の変更(fixture・`core_guard.py`・`core-areas.json`・テスト)とは関係しない。**既知の取り込みトポロジーの偽陽性とは別の種類**として記録し、push する(CI の mutation ジョブで最終確認)

## 2026-10-08 ステップ 8(`5899b9c2`)

- **N6 の値**(design.md 7 節): Cookie `__Host-pitchlog_token`・パス `/`・期限は `Max-Age`(値は δ)/ CSRF の対象 = `GET`・`HEAD`・`OPTIONS` 以外のすべて / カスタムヘッダ `X-Pitchlog-Request: 1` / `Origin` の許可値 = 環境変数 `PITCHLOG_ALLOWED_ORIGINS`(閉じた文法で検証・RFC 6454 の形へ正規化・未設定なら状態を変える要求をすべて拒否)。**δ(TSK-470)への連絡は人間の確認の後**
- **エラー規約**: 要求面の拒否は専用例外で区別し 401 / 403 で返す。認可の拒否の 403 → 404 は不変(資源の参照前・資源に依存しない拒否なので存在は漏れない — design.md 7 節。層 (B)・TSK-346 へ申し送り)
- **敵対レビュー 4 周で可決**:

| 周 | 判定 | 指摘と反映 |
| --- | --- | --- |
| 1 | 否決(P1 2 / P2 1) | `Origin: null` が許可値に入る → 設定値をオリジンとして検証 / import 禁止の構造テストが相対・動的 import を見ない → 解決して検査・合成負例 6 件 / 秘密性テストに `repr` が無い → 追加 |
| 2 | 否決(P1 1) | 大文字・既定ポート付きの設定値がシリアライズ済みの `Origin` と一致しない → 設定値を RFC 6454 の形へ正規化(要求側は完全一致のまま) |
| 3 | 否決(P1 1) | 括弧付きの IPvFuture が括弧を外した DNS 名として許可される → 汎用の URL 解析をやめ、閉じた文法に当たる値だけを許可 |
| 4 | 可決(指摘なし) | — |

- Codex の報告: backend の対象テスト 83 passed・ruff / format / ty 合格・ルートの `tests/test_core_guard.py` 215 passed
- **N6 の値の確認と連絡**: 2026-10-08 山田正輝が「この値で連絡する」と確認。δ(Notion TSK-470「U-A1 δ 認証の HTTP の入口」)へコメントで連絡した(Cookie 名・パス・期限の表現・CSRF の対象メソッド・ヘッダ・`Origin` の許可値の出所と拒否の応答。ログイン等の Cookie が無い入口での CSRF 検査の掛け方は δ が決める旨を付記)
- **push 前の全件実行**(CI と同じ `--no-ff` マージ — `5899b9c2` を `1fdf1eec` へ): `check_frozen_baselines.py --ci` OK・迂回検査 ok・ルート ruff 合格 / backend: format 247 files 合格・ruff・ty 合格・`pytest` **1503 passed・4 skipped** / ルート `pytest tests/` **2933 passed・失敗 0**(前回の負荷依存の 3 件も今回は合格)

## 2026-10-08 ステップ 5 の是正 — UPDATE の実行時 CompileError(`67c4495b`)

- **発見**: 391 タブ(U-S1 — #95 の上に積む)からの連絡。`base._prepare_operation` の UPDATE 文を `Session.execute(statement, parameters)` で実行すると、SQLAlchemy が実行パラメータのキーを column_keys としてコンパイルし、WHERE の `bindparam("tenant_id")`・`("id")`(チーム表は `("kind")` も)が対象表の列名と衝突して `CompileError` になる。**選手・対戦相手チームの更新(更新・在籍区分の適用・論理削除)がすべて実行できない状態だった**
- **当方の確認**: PostgreSQL 方言のコンパイルと SQLite の実 Session の両方で再現(コンパイル段階なので方言に依らない)。INSERT・SELECT は問題なし。`Update.params()` による事前束縛は SQLAlchemy が UPDATE で受けない(NotImplementedError)ので不可
- **見逃した理由**: UPDATE のテストを記録用の偽 session(`_RecordingSession`)で実行していて、実コンパイルを通っていなかった。実 DB の試験(`backend/tests/db/`)に UPDATE の token を実行するものが無い — 越境テスト・DB 試験はステップ 9 以降
- **是正**: UPDATE の WHERE の bind 名を `where_tenant_id`・`where_id`・`where_kind` にし(ORM の全 23 表の列名と非衝突)、`base.py` の UPDATE の検査と束縛を追随。SELECT・INSERT の bind 名と検査は不変。テストは 6 token を Session と同じ column_keys でコンパイル・両 UPDATE を SQLite の実 Session で実行・旧 bind 名と条件欠落の負例。SQL 照合は UPDATE の 3 形状だけ更新(他 8 形状は不変)。契約資産・正例 fixture は不変(契約資産は capability と token 型を宣言し、fixture は組み立て API を検査するため)
- **敵対レビュー 可決**(指摘なし)。旧 bind 名が同じコンパイル条件で `CompileError` になる(是正前なら落ちる)こともレビュー側で確認
- **台帳の候補**: 偽の実行面(記録用 session)だけのテストは、SQL の組み立てが実コンパイルを通ることを保証しない。リポジトリの単体テストに「Session と同じ条件でのコンパイル」を必須にするか — /pr の台帳判断で扱う
- 391 タブへ再現の確認と是正の方針を返信済み(bind 名が変わるので U-S1 は是正後の名前に合わせる)
- **push 前の全件実行**(CI と同じ `--no-ff` マージ — `67c4495b`): 凍結値の走査 OK・迂回検査 ok・ruff / format / ty 合格・ルート **2933 passed**・backend **1518 passed・4 skipped・1 failed** — `tests/db/test_tenant_transaction_scope.py::test_unvalidated_update_is_rejected_before_execute`(実 DB)。探査 UPDATE が旧 bind 名 `tenant_id` のままで、RETURNING の拒否より先にテナント条件で拒否されていた。**是正の取りこぼし**(Codex は DB 必須の試験を実行できず、当方の全件実行で検出)。探査文を `where_tenant_id` へ(Claude の直接編集 — review normal 可決)。同ファイル 18 passed(実 DB)。変更はこの 1 ファイルだけなので、全件は再実行せず、同ファイルと凍結値の走査を清潔な HEAD で取り直した

## 2026-10-09 依存の着地・マージ順・敵対レビューの事後補完

- **依存の再測**: γ #100(03:10Z)・TSK-480 #104(10-08)・TSK-344 #97(10-07)・TSK-475 #94(10-05)がマージ済み。ステップ 9 の着手条件で残るのは TSK-457 #101 だけ。#100 の公開入口 `verify_tenant_id(value, presentation, engine) -> UUID | None` は計画の前提(提示値 → γ → 照合済み ID)と一致する。presentation と engine の供給経路(`app.state.token_presentation` / `create_database_engine()` を想定)は計画書に無く、ステップ 9 の着手時に詰める
- **#95 の分割はしない**(2026-10-09・山田正輝): 469 master から「1〜8 を先にマージ」の提案があったが、計画どおりステップ 13 まで 1 PR とする
- **マージ順と取り込み**(469 master と合意・山田正輝の確定待ち): `#106 → #101 → #81 → #95 → U-S1`。取り込みは #101 着地後(1 回目 — CONFLICTING のまま 5 ステップ進めると CI の run が作られないため、CI の回復が目的)と #81 着地後(2 回目 — 受理値を確定)の 2 回。`base-allowlist.json` の `contract_revision` は #81 の後で 25 の見込み(2 回目に実測)。`source_digest` と配布モジュール 3 本の追随は CI の backend ジョブでしか出ないので、完了判定は MERGEABLE + CI backend で行う
- **敵対レビューの事後補完**: 469 master の指摘(core-guard は敵対レビューの実施を機械検査しない)を受けて証跡を棚卸しした。テナント分離に当たるのに敵対レビューの証跡が無いコミットが 5 本あった — `98ad97de`(ステップ 2)・`2e9fe0cf`(ステップ 4)・`482127c9`(ステップ 2 是正)・`2040ed8d`(ステップ 5 是正の追補)・`5719f664`(review normal のみ)。5 本をまとめて `codex_run.py review adversarial` にかけ、**可決(P0 0 / P1 0 / P2 0)**。観点は認可行列・検査器の弱化・凍結記録・fixture の整合・テストの空洞化。Codex は実 DB 試験を実行できないが、`5719f664` の対象ファイルは 10-08 に実 DB で 18 passed を確認済み
- **台帳の候補**: コア領域の敵対レビューは設計書 6.3 で必須だが、core-guard は逐行確認のチェックしか見ない。ステップ単位で回す運用でも、計画外の是正コミットや Claude の直接編集で抜けが出る(本単位で 5 本)— /pr の台帳判断で扱う

## 2026-10-09 ステップ 9

- **着手時の原典確認**: γ の公開入口は `verify_tenant_id(value: str, presentation: TokenPresentation, engine: Engine) -> UUID | None`。署名器は `create_app()` の `app.state.token_presentation` と `_activate_presentation` により一意化される。TSK-457 の `TenantContext` は `_ISSUANCE_CAPABILITY` の identity を要求し、検査器の `_current_symbol()` は関数内 import の呼び出し元を完全修飾名で照合する。`allowed_product_modules` は発行入口の所属モジュール 1 件と exact-set で一致させる。
- **N7(一次レビュー後)**: 発行専用モジュール `pitchlog.repositories.tenant_context_issuance`、公開関数 `issue_tenant_context_from_presented_token(value, presentation)`。提示値だけを受け取り、接続資源は `create_database_engine()` から得て内部で γ を呼ぶ。署名器は API 依存関数 `pitchlog.api.tenant_access.require_tenant_access` がアプリ状態から渡す。選手ルータは `api/routers/players.py` に置き、`routers/__init__.py` は元の状態へ戻した。
- **名前の全行走査**: `git grep --untracked -n -w issue_tenant_context_from_presented_token`。定義・依存関数からの import と呼び出し・契約値・テスト・設計記録の正当な参照だけ。別定義および無関係な参照は **0 件**。
- **新規ファイルの照合**: `scripts.core_guard.load_core_areas(Path.cwd())` と `matched_paths` で照合する。発行モジュールと境界テストは `tenant-isolation.paths` に一致する。一方、新しい `api/tenant_access.py`・`api/routers/players.py` は現行 paths に一致しない。`.claude/core-areas.json` は本ステップの元の制約では変更しないため、この点は人間へ確認中。
- **未公開メソッド**: `DELETE /players/{id}` は、ステップ 12 で削除の入口を開くまで既存の API 規約どおり 405 を返す。未公開の別パスは 404。
- **ステップ 10 へ残る期待失敗**: `check_tenant_boundary_bypass.py --base-ref origin/develop` は `base-allowlist.json.baseline_control.history: 7 資産の新識別値が不一致`。ルートの指定テストでは `test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path8]` が旧 `contract_revision:11` と新 `:12` の不一致、`test_repository_is_green` が同じ権威履歴の不一致で失敗。権威履歴と比較 corpus は本ステップでは変更しない。
- **実 DB**(Claude が実行): `backend/tests/test_roster_boundary.py::test_real_player_http_boundary_enforces_tenant_and_request_gates` — 実 PostgreSQL の製品スキーマ上で `create_app()` を HTTP から叩き、発行・リポジトリを差し替えない。2 テナントで作成・一覧・取得・更新・他テナントの 404(本文が存在しない ID と同一)・Cookie 欠落/改ざん/失効の 401・CSRF 欠落の 403・PATCH の在籍区分の 422・同番号警告が他テナントを含まないことを確認。関係テスト 272 passed(実 DB を含む)。初回は失効の準備が `tenant_tokens` の CHECK(`expires_at >= last_used_at`)に反して落ちた(HTTP の表明はすべて合格)— 既存の `tests/db/test_authz_verified_tenant.py` と同じ作り方へ直した
- **一次レビュー(Claude)の差し戻し 3 件**: ① 発行の名前と置き場が選手専用に読める — 製品で発行できるモジュールは 1 つだけなので、後続単位も使う汎用の名前へ(後で付け替えると tenant-context-allowlist の受理をもう一度通す)② ルータを `routers/__init__.py` から `routers/players.py` へ ③ 作成時の IntegrityError を一律 404 にしない — 参照先 3 FK の違反だけ 404 へ写す。あわせて越境テストが偽物(`_PlayerStore`)だけで、計画書 6 節「12-4 の判定」行の「実スキーマの上で green」を満たさないため、実 DB で HTTP を叩くテストを足させた
- **敵対レビュー 1 周目 — 否決(P0 0 / P1 3)**: ① 発行入口の `getattr` 参照が TB007 にならない — **不採用**(TSK-457 の保証宣言 `docs/features/tenant-boundary-enforcement/design.md:520-532` と同計画書 4-3 節が人間の裁定で射程外とした線。design.md の N7 節に引き継ぎを明記)② PATCH で在籍区分・ラベルを先行して変更できる — **採用**(ステップ 11 で無効化とともに開くまで 422)③ 作成応答に同番号警告が無い — **採用**(`PlayerCreated.same_number_players`。同一テナント・同番号・現役・未削除・本人除く・DB 側の絞り込み・上限 200)
- **敵対レビュー 2 周目 — 可決(P0 0 / P1 0 / P2 0)**。不採用 ① はレビュー側が取り下げ
- **API の 2 ファイルのコア領域登録**: `api/tenant_access.py`・`api/routers/players.py` は現行のどの paths にも当たらない(API 層はもともとコア領域外)。第 7 改訂で登録すると決めた(下の節)

### ステップ 9 の期待失敗(全件実行で確定 — CI と同じ形: develop `8164c87a` へ `c0aac005` を `--no-ff` でマージ)

- ルート: **40 failed / 28343 passed**。すべてテナント境界の凍結履歴・比較 corpus・センサス基準の検査(受理記録が資産に追いついていないことに由来 — ステップ 10 で解消): `test_census_baseline_check.py` 5(`removed_tb007_matches_declared_relaxations` ほか — 発行モジュールの登録で消える TB007 の減分が宣言済みの緩和で説明できない)・`test_check_tenant_boundary_bypass.py` 2(`test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path8]`・`test_repository_is_green`)・`test_frozen_archive.py` 11・`test_frozen_archive_case_runner.py` 22。`check_frozen_baselines.py --ci` OK・迂回検査は「7 資産の新識別値が不一致」
- backend: **1 failed / 1681 passed / 4 skipped**。`tests/test_api_app.py::test_routers_register_only_meta_routes` — **期待失敗ではない**(ルータが meta だけであることを固定するテストの追随漏れ。計画書は `test_api_conventions.py` の述語 4 だけを挙げていた)。`(ステップ 9 是正)` で直す

## 2026-10-09 取り込み 2 回目(#81)と N4 (ii) の再導出

- **#81(`f833154b`)の取り込み `b7e108f1`**: 21 ファイルが衝突。#81 は authz の封印入力(requirement-claims・route-registry・http-route-matrix)・oracle 資産・凍結基準・tenant_boundary の権威履歴・core_guard の宣言を動かした。衝突は develop 側に揃え、#95 の受理値はここで確定させなかった。**各親との差分**: 第 2 親(develop)に対して基線定義(`core_guard.py`・`test_core_guard.py`)は 0 行、`core-areas.json` は `tenant-isolation.paths` の末尾 2 行(#95 の glob)の追加だけ — 著者が解決したのは JSON の合成だけ
- **`04058d29`(ステップ 6 再導出)**: 宣言を #95 の 2 glob だけへ張り替え(#81 の 5 領域の宣言は merge-base の JSON に入った)。`test_core_guard.py` 230 passed・`verify_area_path_baseline` は merge-base `f833154b` で合格。敵対レビュー 可決(指摘なし)。**469 master の連絡**: develop は #81 の宣言が残ったままで `test_core_guard.py` 2 件が赤(509 タブが fix/ PR で窓口を空へ戻す)。#95 は張り替え済みなので引き継がない。ただし `tests/test_state_transition_freeze.py::test_changed_pr_rejects_acceptance_id_from_another_pr` は develop から引き継いで #95 でも落ちる(391 タブの連絡・当方で再現)— 509 の fix の着地後に取り込んで解消する
- **`cc949c69`(ステップ 2 再導出)**: route-registry・HTTP 行列の lock に #95 の 6 経路を再導出(#81 側の 37 行は不変・route ID は各 43 本で exact-set 一致)
- **`64858d6a`(ステップ 3 再導出)**: oracle_commit 7 箇所を `1f32e12a`(#81)→ `cc949c69`。参照 digest 2 本を追随。N5: 6 経路で oracle の内容追随は不要(HTTP 行列の許可セル 12 のまま)。#81 の `oracle-meaning-change-approvals.json` に新しい行は不要。敵対レビュー 可決(指摘なし)・**人間の再確認 2026-10-09・山田正輝**
- **`c8e53be0`(ステップ 4 再導出)**: frozen-baselines に #95 の oracle_input の記録を #81 の後ろへ 1 件(承認 山田正輝 / 2026-10-09)・`--reseal-oracle`。`check_authz_catalog.py` ok・`check_frozen_baselines.py --ci` OK

## 2026-10-09 第 7 改訂(計画レビュー 5 周 — 1〜4 周目は否決、5 周目で可決)

- **発端**: ステップ 10 で ① 比較 corpus の前版 `ec02a0d2` が #101 の契約拡張を読めず、前版の照合が実行できない(#101・#81 も前版の照合をしていない — develop 自身が条件を満たさない)② センサス基準がステップ 9 の登録で落ちる。Codex は manifest の `comparison_revision` を `c0aac005` へ付け替えていた(依頼外 — develop と同じ値へ戻させた。前版の期待値・`recorded_exit_codes` は develop と同一)
- **裁定(2026-10-09・山田正輝)**: ① 現版だけで判定(前版の付け替えは共有の基準を動かすので不採用)④ API 層の 2 ファイルを `tenant-isolation` に登録する — **当初は当方の推奨で「登録しない」と裁定したが、計画レビュー 1 周目の P0(ハーネス設計書 6.3 の境界定義表はテナント分離に「API 直叩き」を含め、paths の落とし込み規則 ① は強制点を変え得るファイルを含める)を受けて改めた**。当方の推奨は正本を確かめないまま出したもので誤りだった
- **1 周目 否決(P0 1 / P1 5 / P2 1)**: P0 API 2 ファイル — 採用 / P1 取り込みマージが同一コミット禁止を満たさない — 一部採用(マージで基線定義に著者の手を入れず、各親との差分を確かめて記録する手順を足す。履歴は作り直さない — 後続が SHA で参照し人間の再確認済み)→ 2 周目で取り下げ / P1 前版を外した後の保証の明記・内訳 5 の手順の矛盾・センサスのステップ表/内訳 10/6 節への反映・N4 本文への追記 — 採用 / P2 #101 の SHA の帰属 — 採用
- **2 周目 否決(P1 4)**: ステップ 6・7 の合格条件(2 件)と DoD(4 件)の食い違い・計画改訂の承認を 6.3-⑤ の審査として扱った・センサスが 3 節に無い・TSK-485 への申し送りが 8 節に無い — すべて採用
- **3 周目 否決(P1 1)**: 宣言先行の 2 コミットを各 SHA で green にする手順は成立しない(検査器は「merge-base のまま」か「merge-base ＋ 宣言の全件」だけを許す)— 採用。`(ステップ 6 是正)` の SHA は期待どおり赤とした
- **4 周目 否決(P1 2)**: 是正 SHA に内訳 7 の確認は当てはまらない・`matched_paths()` は存在を確かめない — 採用。確認を ①〜④ に分けた
- **5 周目 可決(指摘なし)**。**第 7 改訂の承認: 2026-10-09・山田正輝**。計画レビュー周回 14 → 18

## 2026-10-09 第 7 改訂の是正 2 コミットの敵対レビューと第 8 改訂

- **第 7 改訂に沿った是正**: `e22b141d`(ステップ 6 是正 — 宣言 4 件。期待失敗 2 件だけ: `test_actual_core_area_paths_follow_merge_base_layers`・`test_area_registration` — JSON 77 パス対宣言 79 パス)・`1e45c107`(ステップ 7 是正 — ①〜④ を清潔な HEAD で確認・`test_core_guard.py` 230 passed)。**敵対レビュー**: `e22b141d` 可決 / `1e45c107` 否決(P1 1)— 同じ PR で足し・変えた API 層の強制点 3 ファイル(`request_presentation.py`・`errors.py`・`app.py`)がどの領域にも当たらない。第 7 改訂で 2 ファイルに絞ったのは当方の見落とし
- **裁定(2026-10-09・山田正輝)**: API 層全体を glob `backend/src/pitchlog/api/*` で登録する(3 ファイルを個別に足す案は不採用)。DTO・meta だけを触る PR もコア扱いになることを受け入れる
- **第 8 改訂の計画レビュー**: 1 周目 否決(P1 1 — DoD の「各 SHA が green」が是正 1 本目の期待失敗と矛盾 / P2 2 — ①〜⑤ の参照・承認表の行順)— すべて採用。2 周目 可決(指摘なし)。**承認 2026-10-09・山田正輝**。計画レビュー周回 18 → 19
- 未 push の `e22b141d`・`1e45c107` は捨て、3 件の値で作り直す
- **セッションの中断**: 前のセッションが落ち、/tmp の一時ファイル(レビュー依頼文・CI 相当の一時 worktree)が消えた。作業ツリーとコミットは無事。走っていた push 前の全件実行と第 8 改訂のレビューは止まったので、レビューは依頼文から書き直して流し直した
- **記録**: `64858d6a`(ステップ 3 再導出)の件名に 2 つのステップ記法(「(ステップ 2 再導出) のコミットへ…(ステップ 3 再導出)」)が入り、現在地導出が「1 件名に複数のステップ記法」で不整合を出す。直すには後続 4 コミットの積み直しと worklog の SHA の書き換えが要るので直さない(非ブロッキング — /pr で転記する)

## 2026-10-09 第 8 改訂の是正 2 コミット・取り込み 3 回目・第 9 改訂

- **第 8 改訂の是正**: `9300ff48`(ステップ 6 是正 — 宣言 3 件。期待失敗 2 件だけ: JSON 77 パス対宣言 78 パス)・`37b282fb`(ステップ 7 是正 — ①〜⑤ を清潔な HEAD で確認: paths 完全一致・api/* の追跡 11 件がすべて `matched_paths()` で返り API 層の外は 0 件・`verify_area_path_baseline` 合格・`test_core_guard.py` 230 passed)
- **取り込み 3 回目 `b180f647`**(develop `59f4013c` — #108 core-guard の窓口の是正・#107 Vitest ベクタ runner): 衝突は `tests/test_core_guard.py` の 2 関数だけ(#108 がこのファイルで変えたのもこの 2 関数だけ)。N4 の規律どおりマージでは基線定義に著者の手を入れず本ブランチ側の版を採った。`tests/test_state_transition_freeze.py` は自動マージ(#81 から引き継いだ赤を #108 が解消)
- **`7aa721cd`(ステップ 6 是正)**: #108 の「マージ後に宣言が比較元へ吸収された状態も受理する」考え方を #95 の版へ取り込んだ(吸収済みのときは現設定 = 比較元を求め、件数と #81 の登録の末尾は吸収分を除いて確かめる)。#95 のマージ後に develop の `test_core_guard.py` が赤にならない(#81 で develop が赤になった型)。比較元を現設定に差し替えた模擬で合格。Claude の直接編集 — 敵対レビュー 可決(偽の吸収・比較元の途中の宣言・現設定だけの余分な path を拒否することをレビュー側も確認)
- **是正 2 コミットの敵対レビュー**: `9300ff48` 可決 / `37b282fb` 否決(P1 1 — API 層の契約を検証するテスト 4 本〔`test_request_presentation.py`・`test_api_conventions.py`・`test_api_app.py`・`test_roster_schemas.py`〕がどの領域にも当たらない)。登録が周ごとに外側へ広がったので、打ち切り(TSK-485 へ申し送る)とテスト全体の glob も選択肢として示した
- **第 9 改訂**: 裁定(2026-10-09・山田正輝)= glob 2 本と 1 ファイルを足す。計画レビュー 1 周目で `origin/develop...HEAD` の 78 ファイルを全数照合し、`tests/test_census_baseline_check.py` も足して 7 件(feature 文書の登録の指摘は不採用 — 2 周目でレビュー側が取り下げ)。2 周目 否決(P1 1 / P2 1 — 件数の書き違い・`docs/ops` の列挙漏れ)・3 周目 可決。**承認 2026-10-09・山田正輝**。計画レビュー周回 19 → 21

## 2026-10-10 取り込み 4・5 回目・CI・第 10 改訂

- **第 9 改訂の是正**: `f48c8637`(ステップ 6 是正 — 宣言 7 件。期待失敗 2 件: JSON 78 パス対宣言 82 パス)・`2e2235d7`(ステップ 7 是正 — ①〜⑤ 合格・遡及 9 件)。敵対レビュー 両コミット可決
- **push 前の全件**: ルート 29172 passed / backend 非 DB 1296 passed。backend の DB テスト 386 件は準備段階で ERROR — 共有 DB に被検査ロール `pitchlog_test_role` が前の実行から残っていた(他タブの実行と共有のため手を出さず、CI に任せた)。**CI(run 37944566156)で backend は DB テストを含め green**
- **取り込み 4 回目 `9dd1969e`(#109)・5 回目 `0dff513d`(#110)**: どちらも文書だけで衝突なし。CI の実行中に develop へ #109・#110 が着地し、harness(「HEAD の第 1 親が base.sha と不一致: 期待 `59f4013c` / 実際 `ed4025bd`」・「期待 `ed4025bd` / 実際 `62fc5bfc`」)と tenant-boundary-bypass が 2 回続けて落ちた(コードの欠陥ではない — 509 タブへ実測を渡した)。`0dff513d` の CI(run 37949327295)は core-guard 以外 11 ジョブ green
- **運用の見直し**(利用者の指摘「毎回 CI を通すのは効率が悪くないか」): CI の結果待ちで止まらない・文書だけの develop の進行は追いかけない・backend 全件は CI に任せる
- **共有 DB**: 環境変数ファイルのキー不足で 09-01 以降 docker compose が動いていなかった(山田正輝が補完 — 469 master の連絡)。以後は手元で DB テストを回せる(5 タブで共有 — 長い DB テストは事前に一声)
- **第 10 改訂**(承認 2026-10-10・山田正輝): ステップ 11(在籍区分)は TSK-447(Notion「未着手」・最終更新 09-24)と無効化の記録・配信の仕組み(未実装)を待つ。当初「発火点だけ切り離し入口を #95 で開く」と裁定したが、計画レビュー 1 周目の P0(要件書 6.2・`data-model.md` 11-2 節は在籍区分の変更に無効化を無条件で課し、キャッシュが無くても各操作の受け入れテストに含めると明記)で改め、**旧 11 を丸ごと #95 から外した**(当方の「切り離しても実害なし」は正本を確かめずに出した誤り)。2 周目の P1 でステップ 12(選手の削除 — FR-018)も TSK-459(Notion「着手可」・最終更新 09-26 — 判定後に紐づいた場合の失敗を保証する機構・同期適用経路側)を待つと分かり、**旧 12 も外した**。3 周目の P1(欠番で現在地導出が不整合)で**旧 13(対戦相手チーム)を新 11 に付け替えた**。4〜7 周目は依存表・8 節・各節の古い記述の追随で、5 周目の後に依存表 1〜12 と 8 節を 2026-10-10 の原典で一括現行化、7 周目で初版からの穴(UI 設計正本の工程・FR-039 のリネーム誘導)が出始めたため、冒頭に「現行の正」を明記して打ち切った(裁定 2026-10-10・山田正輝)。計画レビュー周回 21 → 28
- **承認欄の誤記の訂正**: 「承認へ進む」の裁定を受けた時点で、明示の承認より前に承認欄を「済」へ書き換えた。気づいて「未」へ戻し、明示の承認(2026-10-10)を得てから改めて書いた
- **TSK-447 の引き取り**: #95 のマージ後、本タブが TSK-447(意図 ID の規則・原子性の錨・在籍区分の入口と発火点)を 1 つの PR で行う。スパイク(実 DB の使い捨てブランチで一意制約と同一トランザクションを確かめる)から入る(利用者の示唆「必要であればスパイクを」)
- **依存 8 の訂正**: TSK-444 / #82(10-03 マージ)が複数 operation の実行単位を足しており、依存表の「未着手」は古かった。対戦相手チーム(新 11)はこれで着手できる
