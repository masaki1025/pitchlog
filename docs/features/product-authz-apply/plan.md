---
feature: product-authz-apply
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-26・山田正輝)                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e68781f999a1cceeedd22d32
branch: feature/product-authz-apply
created: 2026-09-25
計画レビュー周回: 4        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 製品 authz の適用器・実 DB 試験・移行ロールの資産・写像(TSK-424 PR A2)

## 1. 背景・目的

- Notion: [TSK-442 TSK-424 PR A2](https://app.notion.com/p/3e593b75e68781f999a1cceeedd22d32)(上位カード [TSK-424](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc))
- 調査: [research.md](./research.md)(2026-09-25)/ 詳細設計: **全体の設計の正は A1 の [design.md](../product-authz-surface/design.md)**、A2 の差分は [design.md](./design.md)
- 要件: [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)(チーム間データ分離・初日から全機能)/ [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)(越境テスト)/ [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034)(データ所有権制御)

**なぜやるか**: TSK-424 の PR A1(#79)で、製品の RLS・ロール・ACL の**静的資産**が `contracts/authz/product/` に入った(未発効の staged)。ただし**まだ一度も DB へ適用されていない**。静的検査は資産どうしの整合までしか見ず、PostgreSQL が実際にその組合せで越境を拒むかは実 DB でしか確かめられない(A1 design 6 節)。
本計画 = **PR A2** は、その資産を**使い捨てクラスタへ適用する適用器**と、**適用後のカタログ検査・実 DB 試験**、A1 で残した**移行バッチ用ロールの資産**と **probe ↔ 製品の写像**を置く。**実スキーマへの適用は TSK-344、ランタイム契約の切り替えは PR B = TSK-443** が行う。

**開始条件**: ① TSK-424 PR A1 のマージ(**済** — #79)② TSK-431 の 7C のマージ(**済** — PR #78・`b4ae7394`・2026-09-26)。**両方とも充足済み。** 関門 1(本ブランチの HEAD が 7C のマージコミットを含む)は `git merge-base --is-ancestor b4ae7394 HEAD` が真であることを実測で確認した(2026-09-26)。**関門 2 の照合結果は [research.md](research.md) の追補に置く。**

## 2. スコープ

### やること

1. **製品の適用手順の資産**(`contracts/authz/product/application-steps.json` — 7 手順・1 トランザクション・取り外しの逆順・製品の操作種別)と静的検査
2. **`allowed_symbols` への記号 2 件の追加**と 7.7-2 の記録(7C の形式)・正例 fixture 2 件
3. **製品の適用器と取り外し**(`pitchlog.authz.product_provisioning`)と fixture `provisioned_product_catalog`
4. **製品のカタログ検査**(`pitchlog.authz.product_catalog`)
5. **適用の原子性と故障系**・**再適用と往復**
6. **実 DB 試験**(`tenant_owned` 23 表・その他のプロファイル・横断の観点)
7. **移行バッチ用ロールの資産**(`migration-batch-role.json`)と試験
8. **probe ↔ 製品の写像資産**(`probe-product-map.json`)と検査
9. 正本の追随(3 節)

### やらないこと

| 範囲 | 受け取り先 |
| --- | --- |
| ランタイム契約の切り替え・暫定契約(`runtime_contract.py`)の削除・最終パス `contracts/authz/product/ddl-elements.json` の作成 | **TSK-443**(PR B・TSK-431 の 7D の後) |
| Session の供給と複数 operation のトランザクション単位 | **TSK-444**(PR C) |
| 実スキーマへの適用と越境テストの再実行 | **TSK-344** |
| 移行バッチ用ロールのライフサイクルの**実行**(退役・接続監査・孤児回収・同時実行) | **TSK-349**(A1 design 8-4 の要求事項) |
| 越境関数の本体(認証・管理経路・グループ管理・制御情報の読み取り・共有出力) | U-A1 / U-A2 / U-C1 / U-C2 / U-C3 |
| **probe の適用器・カタログ検査・資産の振る舞いの変更** | 変えない(`contracts/authz/` 直下の差分 0 行 — **例外は `shared-preconditions.json` の digest 1 行**〔design.md 7 節〕・`provisioning.py`・`catalog.py` の既存の DB 呼び出しの行を変えない — research.md 2) |
| staged 資産 `ddl-elements.staged.json` の変更 | 変えない(A1 の exact-set 検査の対象) |
| capability の登録 | 各単位(A1 design 10 節) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8 節 | TSK-424 系の行に、**A2 の範囲を「使い捨てクラスタで確認済み・未発効」**として追記する。**「解消済み」にはしない**(design.md 7 節) | PR レビュー(実装追随の節更新 — 設計書 7.6) |
| `docs/design/data-model.md` 変更履歴 | 上を追記する。**版は上げない** | PR レビュー |
| `docs/README.md` | `data-model.md` の行の最終更新日と概要を現行化する | PR レビュー |
| `docs/design/data-model.md` 3-2 / 3-5 / 12-4 / 12-6 / 12-9 | **反映なし**(TSK-382・TSK-445 の射程を踏まない) | — |
| `docs/requirements/` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(7.7 に従う側) | — |
| `docs/adr/` | **反映なし** | — |

**正本体系外だが同一 PR で更新するもの**: `contracts/tenant_boundary/base-allowlist.json`(`allowed_symbols` と 7.7-2 の記録)・7C のマージ版が要求する場合の `contracts/tenant_boundary/history-snapshots/<sha256>`(変更前後の内容 — 追記のみ)・`tests/fixtures/tenant_boundary/positive/`(正例 fixture)・`contracts/authz/product/` の新設資産 4 つ・**data-model.md の追随に機械的に連動する digest 2 行**(`contracts/authz/shared-preconditions.json` の `mapping_target.git_blob_digest`・`contracts/db/schema-manifest.json` の `canonical_source.sha256` — A1 で人間が承認した例外と同じ。design.md 7 節)。

## 4. 実装方針

**重さ分類 = コア領域**。テナント分離(RLS・ロール・ACL の適用と越境の実 DB 試験)とデータ移行(移行バッチ用ロールの資産)に触れる。`contracts/authz/*` と `contracts/tenant_boundary/*` はコア領域の paths(`.claude/core-areas.json`)。
→ 実装は ADR-001 の対応表どおりのモデル、敵対レビュー必須、**人間の逐行確認必須**(PR 作成者以外)。

**設計**: 全体は A1 の [design.md](../product-authz-surface/design.md)、A2 の差分(DB 呼び出しの置き場・手順の資産・記録点・カタログ検査・`allowed_symbols` の順序)は [design.md](./design.md)。

**実装開始の関門**(承認の後・ステップ 1 の前):

1. **TSK-431 の 7C がマージされ、本ブランチの HEAD がそのマージコミットを含む**(更新済みの `origin/develop` へ rebase または merge した後に `git merge-base --is-ancestor <PR #78 のマージコミット> HEAD` が真)。**検証は worktree 内の 7C 版の検査器と資産で行う**(検査器は HEAD 側を読むので、古い HEAD では旧契約で green になり得る — 計画レビュー 1 周目 P1)
2. **7C のマージ版の全体(記録形式・history-snapshots の置き場・PR 受理モード)を research.md 1 の前提と照合し直す**。違えば、**計画書を改訂し、承認を取り直してから**実装する。history-snapshots の exact な変更パスはこの照合で確定し、ステップ 2 の合格条件に書き足す
3. ステップ 2 の前に **draft PR を作って PR 番号を確定する**(7C の PR 受理モードが番号を要する見込み — research.md 1)

**守る不変条件**(全ステップ共通):

- **変えてよい既存ファイルは、下のステップ表の「変える既存ファイル」に列挙したものと、実装ステップの外で行う正本の追随(/sync-docs — 3 節)の 4 ファイルだけ**(A1 design 5 節の規則 — 計画レビュー 3 周目・4 周目 P1)。**正本の追随の 4 ファイル**: `docs/design/data-model.md`(12-8 節と変更履歴)・`docs/README.md`(data-model.md の行)・`contracts/authz/shared-preconditions.json`(`mapping_target.git_blob_digest` の 1 行)・`contracts/db/schema-manifest.json`(`canonical_source.sha256` の 1 行)。**全ステップで差分 0 行**: `scripts/check_tenant_boundary_bypass.py`・`.github/workflows/`・`tests/test_ci_wiring.py`・`backend/src/pitchlog/authz/provisioning.py`・`backend/src/pitchlog/authz/catalog.py`・`backend/src/pitchlog/authz/runtime_contract.py`・**既存の `test_*.py`**(各ステップに列挙したものを除く)。新設のファイルはこの制限に掛からない

- `contracts/authz/` 直下の probe 資産の差分 0 行(**例外は design.md 7 節の digest 1 行 — `shared-preconditions.json` の `mapping_target.git_blob_digest`。封印 `oracle-seal.lock.json` は動かさない**)/ `contracts/db/schema-manifest.json` は **`canonical_source.sha256` の 1 行だけ**を変える。**両 digest が更新後の `data-model.md` と一致**/ `ddl-elements.staged.json` の差分 0 行 / 最終パス `contracts/authz/product/ddl-elements.json` を**作らない**
- `backend/src` の新しい DB 呼び出しは **design.md 1 節の末端 2 関数だけ**で、**末端関数は任意の SQL を受け取らない**(検証済みの実行計画・閉じた問い合わせ ID だけ)。probe の `provisioning.py`・`catalog.py` の既存の DB 呼び出しの行を変えない。**各ステップのコミットで迂回検査が green**(`uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` — committed の差分しか見ないのでコミット後に走らせる)
- `runtime_contract.py`・`contracts/tenant_boundary/*`(ステップ 2 の `base-allowlist.json` と、関門 2 で確定した history-snapshots のパスを除く)・`backend/pyproject.toml`・**`backend/uv.lock`**・**リポジトリ直下の `uv.lock`**・`backend/tests/conftest.py` の差分 0 行
- **適用主体は `SET ROLE` を使わない**(A1 design 4-2)。**静的**(生成した文に主体を変える文が 0 件)と**動的**(各記録点で `current_user = session_user`)の両方で示す(design.md 1-a)
- 試験の期待値は manifest の事実と staged 資産から導き、**分類資産から導かない**(A1 旧 17)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **製品の適用手順の資産 `contracts/authz/product/application-steps.json`** と、`PRODUCT_SPEC` の製品の操作種別(DB 呼び出しなし — design.md 2 節) | 手順 7 つが 1 からの連番で A1 design 4-2 の順序(**補助関数はポリシーより先**)・`transaction = single`・取り外しが適用の逆順(**ポリシーを補助関数より先に落とす**・`pitchlog_owner` を削除しない)・種別の割り当てが `PRODUCT_SPEC` の要素の節の全部(**`predicates` を含む** — design.md 2 節)の全要素を 1 回ずつ覆う。製品の操作種別は閉じた集合で、**probe の 5 種と交わらない**。**変異で red**: 手順を入れ替える(ポリシーを補助関数より先)/ 要素を 1 つ割り当てから外す / 2 手順に重複して割り当てる / `predicates` を割り当てから外す / probe の種別を 1 つ混ぜる / `transaction` を `per_step` にする。staged 資産と probe 資産の差分 0 行 **変える既存ファイル**: `backend/src/pitchlog/authz/asset_spec.py`(`PRODUCT_SPEC` の操作の対応)・`backend/src/pitchlog/authz/ddl.py`(製品の文の生成に要る最小限 — DB 呼び出しを足さない)・`backend/tests/test_authz_provisioning_spec.py`(A1 が「`PRODUCT_SPEC` の操作の対応は空」を表明している箇所だけ)。 |
| 2 | **`allowed_symbols` への記号 2 件の追加と 7.7-2 の記録**(design.md 1 節・5 節。**7C のマージ版の形式**)と正例 fixture 2 件 | `base-allowlist.json` の `allowed_symbols` に design.md 1 節の 2 記号(完全修飾名・シグネチャ・`allowed_api_ids`)が載り、正例 fixture の集合と一致。7.7-2 の記録が 7C の検査器で受理される(記録 1 件・`contract_revision` の更新・前後の実内容)。**7C のマージ版の実形式(関門 2 の照合で確定 — [research.md](research.md) の追補)**: **① v2 record の必須キーは exact-set**(過不足不可)で、**`new_baseline_identifiers` / `previous_baseline_identifiers` は 7 資産すべてを鍵に持つ map**。**② `change` は `{subject, aspect, before, after}`** で、**`before` / `after` は `{declaration, movement_policy, external_snapshots, asset_snapshots}` の 4 キー**。`declaration` と `movement_policy` は **7 資産分の実内容**、`asset_snapshots` は **7 件**。**`aspect` は実差分からの機械導出値と完全一致**。**③ `contracts/tenant_boundary/history-snapshots/<sha256>` は無条件で必須**で、**既存 47 件を 1 つも変更・削除しない**(追記のみ)。**④ `approved_by` / `approved_on` / `movement_fact` / `reason` / `change.subject` に予約語(`PENDING` / `TODO` / `TBD` / `未承認` / `未定` / `レビュー待ち`)を書けない**。**実在の承認者名と実在する ISO 8601 日付が要る**。**⑤ `contract_revision` は 15 → 16**(`allowed_symbols` は `baseline_value` 軸に入るので追加で必ず movement が起きる)。**⑥ 合格の判定は PR の CI(PR 受理モード)で行う** — **ローカルの `--base-ref origin/develop` は不変量モードで、実内容の突合・`acceptance_id` の突合・merge 形状の検査が走らない**。**変異で red**: `allowed_api_ids` に `PSYCOPG_CONNECTION_COMMIT` を持たない記号で commit を呼ぶ fixture / 記録を消す / fixture を 1 件欠く。迂回検査が green **変える既存ファイル**: `contracts/tenant_boundary/base-allowlist.json`・関門 2 で確定した history-snapshots のパス(新設)。 |
| 3 | **製品の適用器と取り外し** `pitchlog.authz.product_provisioning`(外部の superuser・1 トランザクション・固定の 7 手順 — A1 design 2-3・4-1・4-2・4-3)と fixture `provisioned_product_catalog`(`backend/tests/db_fixtures.py` に新設・`backend/tests/db/conftest.py` で再エクスポート) | 適用が成功し、**commit 後の同じ接続で `current_user = session_user`**。migration は `pitchlog_owner` の接続で走る。fixture は **`pitchlog_owner` を 7 属性どおりに作ってから適用前のカタログを記録する**。**再適用のたびに 7 属性を正規化する**。DB 呼び出しは `_run_product_operation` だけで、**受け取るのは閉じた指示(`APPLY` / `UNAPPLY`)だけ**。**接続が閉じている・autocommit・トランザクションが IDLE でない・superuser でない・`pitchlog_app` のときは、文を 1 つも実行せず commit も rollback もせずに拒否し、別の接続から見たカタログが不変**(変異で red: 各前提の検査を外す)。文・計画・資産の置き場を受け取らず、**文は末端の中で正規の資産から生成する**(design.md 1 節)。**接続が superuser でないか `pitchlog_app` なら実行前に拒否する**。**`_run_product_operation` を参照するコードが `apply_product_authz_ddl`・`unapply_product_authz_ddl` の exact-set**(呼び出しに限らず名前・属性の参照を AST で全数列挙。同一モジュール内の追加・別名への代入も red)。**生成した適用・取り外しの文に主体を変える文が 0 件**、**各記録点で `current_user = session_user`**。**変異で red**: 末端関数に文や資産の置き場を渡す引数を足す / 参照を 1 つ足す / 別名へ代入して呼ぶ / 途中の 1 手順だけ `SET ROLE` と `RESET ROLE` で挟む。既存の `provisioned_catalog` の振る舞いが変わらない。迂回検査が green **変える既存ファイル**: `backend/tests/db_fixtures.py`(fixture の新設)・`backend/tests/db/conftest.py`(再エクスポートの追加)。 |
| 4 | **製品のカタログ exact-set 検査** `pitchlog.authz.product_catalog`(design.md 4 節・A1 design 2-2・3-4・6-3) | 全 45 表の `relrowsecurity`・`relforcerowsecurity`・`pg_policy`・表 / 列 / スキーマ / 関数 / DB の ACL・ロールの 7 属性・DB とスキーマの所有者が**資産と exact-set**。**`pg_auth_members` のうち製品ロールに接する行が 0 件**。**LOGIN できる危険ロールの集合 = 許可集合**(`pitchlog_owner` ∪ 入力で渡す環境の superuser の OID)。**37 個のトリガ関数がすべて `SECURITY INVOKER`**。**変異で red**: `ADMIN` だけの辺を 1 本足す / 製品ロールから出る辺を足す / 許可集合に無い `LOGIN` + `BYPASSRLS` のロールを作る / 入力に無い superuser を作る / `SECURITY DEFINER` のトリガ関数を 1 つ混ぜる。DB 呼び出しは `_fetch_catalog_rows` だけで、**閉じた問い合わせ ID と束縛値だけ**を受け取り、参照するコードは `inspect_product_authz_catalog` の 1 つ(**変異で red**: 未知の問い合わせ ID / 文字列の問い合わせを渡す / 参照を 1 つ足す)。迂回検査が green **変える既存ファイル**: なし(新設だけ)。 |
| 5 | **適用の原子性と故障系**(design.md 3 節・A1 design 4-2)と故障注入点の資産 `contracts/authz/product/failure-injection-points.json` | **失敗点 5 か所**(補助関数の作成の直後・ポリシーの作成の直後を含む)で故障を注入し、**カタログが適用前と一致**。**rollback 後の同じ接続で `current_user = session_user`**。故障注入点の資産が `application-steps.json` と blob digest で結び付き、記録点が資産どおりに存在する。**変異で red**: 手順の途中に commit を挟む / 記録点を 1 つ消す **変える既存ファイル**: なし。 |
| 6 | **再適用と往復**(A1 design 4-3) | 2 回適用しても 2 回目の後のカタログが 1 回目と一致。**適用 → 取り外し → `downgrade base` → `upgrade head` → 再適用**の後のカタログが初回の適用後と一致。**取り外しの後のカタログが適用前と一致**し、取り外しの途中の失敗 2 か所(ポリシーの削除の直後・補助関数の削除の直後)で何も変わらない。**危険な属性からの正規化は別のケース**とし、7 属性に危険な属性を足した状態から再適用すると正規化で消える。既存の `backend/tests/db/test_migration_round_trip.py` は差分 0 行 **変える既存ファイル**: なし(`test_migration_round_trip.py` は差分 0 行)。 |
| 7 | **実 DB 試験(1)`tenant_owned` 23 表**(A1 design 6-1)。manifest の事実からパラメタ化して生成する | 23 表**すべて**で: **最低要求 ①**(他テナントの行が 0 行。**さらに `tenant_id` 列を持つ 28 表すべてで、他テナントの行が 0 行か `42501`** — 分類に依らない)/ `WITH CHECK` 違反が `42501` / 未束縛が 0 行 / 不正 UUID が `22P02` / `DELETE` が `42501`。**変異で red**: 1 表のポリシーを外す / `FORCE` を外す / `WITH CHECK` を `true` にする **変える既存ファイル**: なし。 |
| 8 | **実 DB 試験(2)その他のプロファイル**(A1 design 6-2) | **事前条件として両テナントの対象行が存在することを表明する**(空で偶然通る試験を落とす)。`self_tenant_row`(`tenants` — 自テナント 1 行・他テナント 0 行・`UPDATE` が `42501`)/ `global_read_only`(`SELECT` 可・`INSERT` が `42501`)/ `function_only` 13 表(**`42501` であって 0 行ではない**)/ **`pitchlog_app` は制御資源 4 表を `SELECT` できず、補助関数も呼べない(`42501`)** / **補助関数とポリシーの述語の正負行列の全セル**(rollback する試験のトランザクションの中だけで一時の権限を与え、rollback の後にカタログが exact-set に戻ることも検査 — design.md 6 節。実効参加の `member` と `admin`・非参加・離脱・グループ終了・参加テナントの無効化・存在しないグループ)/ **テナント A と B がそれぞれ大会規則を作った状態(両テナントの行が非空であることを表明)で**、`pitchlog_app` は `rule_sets` と `tournament_rule_assignments` のどちらも読めない(`42501` — A1 design 1-6)。**変異で red**: `function_only` の表に `SELECT` を与える / 補助関数の条件を 1 つずつ外す **変える既存ファイル**: なし。 |
| 9 | **実 DB 試験(3)横断の観点**(A1 design 6-3) | **トリガの発火**(37 個の `PUBLIC` 剥奪の後もトリガが動く)/ FORCE(`pitchlog_owner` でも未束縛で 0 行)/ 危険終点の交差が空 / **最低要求 ②**(`PUBLIC` と、信頼しない `LOGIN` ロール〔`pitchlog_app` を含む〕が補助関数の実効の `EXECUTE` を持たない)/ **最低要求 ③**(`pitchlog_app` は一時表を作れない〔`42501`〕・`TEMPORARY` を持つ試験専用ロールの一時スキーマの乗っ取りが補助関数に効かない)/ `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件 **変える既存ファイル**: なし。 |
| 10 | **移行バッチ用ロールの資産 `contracts/authz/product/migration-batch-role.json`** と、有効な間の形の試験・定常の不変条件(A1 design 8-1〜8-3) | **`write_targets` が導出集合 19 表と exact-set**、かつ**必要な権限の行列**(19 表の `INSERT`・`SELECT`、`retired_at` を持つ表の `UPDATE(retired_at)`、`migration_runs` の許された列の `UPDATE`)と exact-set。**正例**: 資産どおりに作ったロールで最小の `INSERT`・`SELECT`・`retired_at` の更新が通り、**渡された OID に対して**有効な間の形(接する辺 0 本・所有しない・表 ACL が exact・**スキーマ ACL が `{public: USAGE}` と exact**・DB は `CONNECT` のみ・製品スキーマの利用者定義の関数を 1 つも実行できない・属性 — A1 design 8-2)を満たす。**定常の不変条件**(許可集合に無い `LOGIN` + `BYPASSRLS` のロールが 0 件)がステップ 4 のカタログ検査に入り、形のロールを 1 つ残すと不合格。**変異で red**: A1 旧 20 の 10 種(`write_targets` に表を足す / 必要な権限を外す / 表単位の `UPDATE` / `DELETE` / 無関係な `LOGIN` ロールからの辺 / 適用主体からの辺 / 表の所有 / `write_targets` の外へ書く `SECURITY DEFINER` 関数の `EXECUTE` / `PUBLIC` へ `EXECUTE` を戻す / 既定の権限で `EXECUTE` が付く)と、**スキーマ ACL の 3 種**(`public` の `CREATE` / `authz_private` の `USAGE` / `authz_private` の `CREATE`) **変える既存ファイル**: なし(カタログ検査への定常の不変条件の追加はステップ 4 の新設モジュール)。 |
| 11 | **probe ↔ 製品の写像資産 `contracts/authz/product/probe-product-map.json`** と検査(A1 design 7 節) | `probe の全原子要素 = mapped ∪ explicit_non_mapping` と `製品の全原子要素 = mapped の像 ∪ product_only` が**両方向 exact-set**。理由コードは閉じた列挙で、種別ごとに使えるコードが固定。`read_control_resources` が `deferred_to_owning_unit` / `owner_unit: U-C2`。**製品側の母集合は `ddl-elements.staged.json` だけ**(移行バッチ用ロールを含めない)。`app_role` の `DELETE` が `forbidden_by_canon`。**変異で red**: probe 要素の写像を 1 つ消す / 製品要素を 1 つ足して写像しない / 列挙外の理由コード / 種別に合わない理由コード / `read_control_resources` の `owner_unit` を U-C2 以外にする / 許可していない 1 対多 **変える既存ファイル**: なし。 |

**正本の追随**(3 節)は、ステップ 11 の後に /sync-docs で行い、PR A2 に含める(Claude が書く)。

## 5. DoD(受け入れ基準)

- [ ] **実装開始の関門**(4 節)を通した: 7C のマージ・記録形式の読み直し(差があれば計画を改訂し承認を取り直した)
- [ ] **製品の適用手順が資産で閉じている**(7 手順・1 トランザクション・取り外しの逆順・probe の種別と交わらない)
- [ ] **`allowed_symbols` の追加が 7.7-2 の記録つきで 7C の検査器に受理され**、`backend/src` の新しい DB 呼び出しが末端 2 関数だけ。迂回検査が green
- [ ] **使い捨てクラスタで製品 DDL の適用と取り外しが green**(1 トランザクション・`current_user = session_user`・7 属性の正規化・故障注入 5 + 2 か所で適用前と一致・二重適用と往復が一致)
- [ ] **カタログ検査が exact-set**(辺 0 本・危険ロールの許可集合・37 個が `SECURITY INVOKER`)
- [ ] **実 DB 試験で最低要求 ①②③**・`WITH CHECK`・`function_only` の `42501`・制御資源の正負行列が green
- [ ] **移行バッチ用ロールの資産**(19 表・権限の行列)と有効な間の形(**スキーマ ACL `{public: USAGE}` を含む**)・定常の不変条件が検査されている
- [ ] **probe ↔ 製品の写像が両方向 exact-set**
- [ ] probe 資産(**例外は digest 1 行 — design.md 7 節**)・`ddl-elements.staged.json`・`runtime_contract.py`・`backend/pyproject.toml`・**`backend/uv.lock`・リポジトリ直下の `uv.lock`**・`backend/tests/conftest.py` の差分 0 行。`contracts/db/schema-manifest.json` は `canonical_source.sha256` の 1 行だけで、両 digest が更新後の `data-model.md` と一致。最終パス `ddl-elements.json` が存在しない。`backend/src` の新しい DB 呼び出しが末端 2 関数だけで、任意の SQL を受け取らない
- [ ] **12-8 節に A2 の範囲を「使い捨てクラスタで確認済み・未発効」と書いた**(解消済みにしない)。PR に 12-4 の判定記録(「対象入口なし」)
- [ ] **CI の backend・harness ジョブと同じコマンドを同じ場所で流した**(`.github/workflows/ci.yml` — A1 の CI red の教訓): **`backend/` で** `uv python install`・`uv sync --locked --dev`・`uv run ruff check .`・`uv run ruff format --check .`・`uv run ty check`・`uv run pytest -c pyproject.toml --cov`(DB 試験を含む全件・1 プロセス)・`uv run alembic upgrade head`・`uv run alembic current --check-heads`・`uv run alembic check` / **リポジトリルートで** `uv python install`・`uv sync --locked --dev`・`uv run python scripts/check_frozen_baselines.py --ci`・`uv run ruff check .`・`uv run ty check`・`uv run pytest -c pyproject.toml tests/`。あわせて迂回検査(`scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`)
- [ ] **コア領域として敵対レビューと人間の逐行確認(PR 作成者以外)を通した**

## 6. テスト計画

| テスト種別 | 足すもの |
| --- | --- |
| **越境**(NFR-019(b) の **DB 層**。条文の合否基準「認可行列どおりに通り行列外は 404」は API 層で、本単位は HTTP の入口を開かないため当該経路は未発効) | ステップ 7・8・9(最低要求 ①②③・`WITH CHECK`・`function_only` の `42501`・制御資源の正負行列・`tenant_id` を持つ 28 表の全数) |
| **故障系**(**NFR-019(d) は「同期プロトコルの故障系」であって本行とは別物**。本行は DDL 適用の原子性・故障注入) | ステップ 5(適用の失敗点 5 か所)・ステップ 6(取り外しの失敗点 2 か所・危険な属性からの正規化) |
| **一致性**(**NFR-019(a) の対象は NFR-018 区分(α)のドメイン計算であって本行とは別物**。本行はカタログ一致・写像の exact-set) | ステップ 6(二重適用・往復のカタログ一致)・ステップ 11(probe ↔ 製品の写像の両方向 exact-set) |
| **単体**(**NFR-019 の条文に無い種別**。本計画が足す区分) | ステップ 1(手順の資産の静的検査)・ステップ 2(記号と fixture の一致)・ステップ 3・4(拒否の前提・参照 0 件) |
| E2E | 対象なし(HTTP の入口を開かない — 12-4 の判定は「対象入口なし」) |

**DB 試験は使い捨てクラスタで行う**(`disposable_postgres_cluster` — research.md 3)。検証は各ステップで対象の試験を、PR の前に **5 節 DoD の CI と同じコマンドの一覧**を、それぞれ CI と同じ場所で流す(pytest だけでは足りない — ruff・ty・凍結基準検査・Alembic 検査も CI が走らせる)。
