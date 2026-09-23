---
feature: product-authz-surface
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域           # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc
branch: feature/product-authz-surface
created: 2026-09-24
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TSK-424 製品認可面の確定

## 1. 背景・目的

- Notion: [TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)(U-T1〔TSK-390〕から 2026-09-17 に分離 — 人間の裁定・山田正輝)
- 調査: [research.md](./research.md)(2026-09-24・4 並列)/ 詳細設計: [design.md](./design.md)
- 要件: [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)(チーム間データ分離・初日から全機能)/ [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)(越境テスト)/ [NFR-014](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-014)(シークレット)/ [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034)(認可行列)/ [FR-038](../../requirements/requirements-pitchlog-2026-07-22.md#FR-038)(移行)。機構の正は `docs/design/data-model.md` 3 章(RLS の採否は同書の設計判断 — `:139-149`)

**なぜやるか**: 製品の DB には、RLS・ロール・ACL がまだ 1 つも無い(`backend/migrations` に 0 件、`contracts/authz/product/` は未作成)。
いまある認可資産は、機構の検証用の probe(`product_schema: false`)だけである。
このため、越境テストの再実行ゲート(TSK-344)の通過条件 ①「RLS のポリシーとロールの DDL が実スキーマへ適用されている」(`data-model.md:2529`)が、**適用する DDL そのものが無い**という理由で満たせない。
帯 2 の単位(U-M1・U-D1 ほか)も、製品表への操作を開く capability を、表分類が確定するまで足せない(`../tenant-boundary-enforcement/plan.md:87`)。

本単位は、**全 45 表の許可プロファイル・製品 authz DDL 資産・probe ↔ 製品の写像・移行バッチ用ロールのライフサイクル**を確定し、使い捨てクラスタで適用して検査するところまでを行う。
**実スキーマへの適用は TSK-344、ランタイム契約の切り替えは PR B(別タスク)が行う。**

### 計画の前提とした判断(承認の対象 — 本計画の承認をもって確定する)

| # | 判断 | 典拠 |
| --- | --- | --- |
| ★1 | **移行バッチ用ロールのライフサイクル契約・実行器・使い捨てクラスタでの検査は、本単位が製品資産として持つ**。TSK-349 は取り下げず、「FR-038 の移行実行器が本資産を使うこと・本番での実証・スキーマの食い違いの解消の窓口」へ射程を書き換える。TSK-349 の旧方式(凍結 probe 資産への追加と `--reseal-oracle`)は採らない | design.md 8-4 |
| ★2 | **TSK-382(SP-06 の字面衝突)の射程は踏まない**。本単位は製品トラフィックを受ける配備先に適用せず、SP-06・12-4 の non-serving 宣言・12-6 の受け取り先表のいずれも変えない。「実スキーマ」の意味も定義しない | design.md 12 節 |
| ★3 | **移行バッチ用ロールの書き込み先は、導出集合(`import_batch_id` を持つ表 ∪ `migration_runs` の 19 表)と完全に一致させ、例外を置かない**。監査は手順の側(管理接続)が書き、移行バッチ用ロールには監査の表の権限を与えない。`event_slots` が取り込みバッチ識別子を持たない食い違い(正本 12-3 不変条件 1 とスキーマ)は、スキーマを持つ単位と TSK-349 へ申し送る | design.md 8-1・8-2 |
| ★4 | **正本 3-2 節 `:296` の監査根拠(NFR-012)は本単位では直さない**。approved の正本にある典拠の誤りで、実装追随ではないため。次の `data-model.md` 改訂の射程へ申し送る | design.md 11 節 |
| ★5 | **物理プロファイルは 5 種**(`tenant_owned` / `self_tenant_row` / `effective_group_control` / `global_read_only` / `function_only`)。カードが求めた「親表経由」「認証前グローバル可変」は、直接アクセスを許さない `function_only` に倒し、到達経路の理由として記録する(正本はこの 2 表の RLS を定めていない)。**Notion の DoD の字面を書き換える** | design.md 1-2 |
| ★6 | **制御資源 4 表は、正本 3-0・3-5 節どおり「実効グループ ∧ 実効参加」の RLS ポリシーで守る**。再帰と他テナントの有効状態の問題は、真偽値だけを返す補助関数(`SECURITY DEFINER`・所有者 `pitchlog_shared_fn_owner`)で解く。U-T1 design の P3 の記述(終了済みグループも見え続ける)は正本と矛盾していたので是正する | design.md 1-3 |
| ★7 | **capability は空のまま残す**。本単位が出すのは、capability を導くための表分類資産まで | design.md 10 節 |
| ★8 | **PR を 2 本に分ける**(人間の承認 2026-09-24)。**本計画 = PR A**(ステップ 1〜14 と正本の追随。TSK-431 を待たない)。**PR B**(ランタイム契約の切り替え・暫定資産の削除)は TSK-431 のマージ後に、別タスク・別ブランチ・別計画書で行う。PR A の間、製品 DDL 資産は `ddl-elements.staged.json` に置き、U-T1 の二状態テストを発火させない | design.md 3-2・9 節 |

## 2. スコープ

### やること(PR A)

1. **資産指定オブジェクト**で authz ツールチェーンを一般化する(design.md 5 節)
2. **全 45 表の表分類資産**と、固定 oracle・意味の不変条件による検査(design.md 1 節)
3. **製品 authz DDL 資産**(`ddl-elements.staged.json` と `function-bodies/`)。ロール 4 種・DB とスキーマの所有と ACL・全表の `ENABLE` + `FORCE`・ポリシー・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪・制御資源の補助関数(design.md 1〜3 節)
4. **製品の適用器**(migration の後に 1 トランザクション・`SET LOCAL ROLE`・membership は辺ごと `REVOKE`)と、使い捨てクラスタでの適用・カタログ検査・再適用と往復(design.md 2-2・4 節)
5. **実 DB 試験**(design.md 6 節)
6. **probe ↔ 製品の写像資産**と、両方向 exact-set の検査(design.md 7 節)
7. **移行バッチ用ロールのライフサイクル資産・実行器・回収処理**と、使い捨てクラスタでの試験(design.md 8 節)
8. **capability の誤開放を防ぐ検査**(design.md 10 節)
9. **正本の追随**: `data-model.md` 12-8 の分割・変更履歴・`docs/README.md`(design.md 11 節)
10. **申し送り**の記録(Notion と PR 本文): TSK-349 の射程の書き換え / PR B のタスク起票 / `event_slots` の食い違い / 3-2 節の典拠 / TSK-344 への運用契約(往復の non-serving 区間・孤児ロールの定常検出)/ TSK-250 への写像資産の正の所在

### やらないこと

| やらないこと | 行き先 |
| --- | --- |
| **ランタイム契約の切り替え・暫定資産の削除・7.7 の削除記録** | **PR B**(TSK-431 のマージ後。別タスクとして起票する — ★8) |
| **実スキーマへの適用と、越境テストの再実行** | TSK-344(`data-model.md:2846`・裁定 A-2) |
| **越境関数の本体・その ACL・`search_path`**(補助関数 1 個を除く) | U-C1 / U-C2 / U-C3 / U-A2(`../product-impl-unit-split/plan.md:224-227`) |
| **認証・レート制限・管理経路の関数**(`function_only` 表への到達経路) | U-A1 / U-A2 |
| **制御資源の列の粒度の制限**(テナント名のみ・`admin` のみの列) | U-C2 のアプリ層(正本の二重構成 — `data-model.md:137`) |
| **capability の中身(製品表への操作を開くこと)** | 経路を持つ単位(U-01 ほか — ★7) |
| **実運用の移行実行・`event_slots` の食い違いの解消** | TSK-349(★1・★3) |
| **正本 3-2 節 `:296` の典拠の訂正** | 次の `data-model.md` 改訂(★4) |
| **probe 資産(`contracts/authz/` 直下)の変更** | 変更しない(封印 — `contracts/authz/oracle-seal.lock.json:40-88`) |
| **SP-06・12-4 の non-serving 宣言・12-6 の受け取り先表・3-5 節の述語の変更** | 変えない(★2・★6) |
| **`scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` の変更** | 触れない(TSK-431 と PR B の射程) |
| **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の変更** | 変えない(差分 0 行) |
| **HTTP の入口を開くこと** | 開かない。12-4 の判定記録には「対象入口なし」と書く(`data-model.md:2534`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8 節(`:2844-2846`) | TSK-317 行を分割し、TSK-424(PR A で landed)/ U-C1・U-C2・U-C3・U-A2(越境関数と最低要求 ②③④ の残り — 残件)/ TSK-344(実スキーマでの再実行 — 残件)/ PR B のタスク(ランタイム契約の切り替え — 残件)に割り当てる。**「解消済み」にしない** | PR レビュー(7.6-3 前段・実装追随の節更新) |
| `docs/design/data-model.md` 変更履歴 | 上を追記する。**版は上げない** | PR レビュー(同上) |
| `docs/README.md` | 索引を現行化する(`contracts/authz/product/` の新設) | PR レビュー |
| `docs/design/data-model.md` 3-2 / 3-5 / 12-4 / 12-6 / 12-9 | **反映なし**(★2・★4・★6) | — |
| `docs/requirements/` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(7.6・7.7 に従う側) | — |
| `docs/adr/` | **反映なし**(ADR-004 の適用単位の判定に従う側) | — |

## 4. 実装方針

詳細設計は [design.md](./design.md)。

**重さ分類 = コア領域**。根拠: **テナント分離**(設計書 6.3 の境界定義)の中核である。RLS・ロール・ACL を製品に初めて置き、`contracts/authz/*`・`backend/src/pitchlog/authz/*`・`backend/tests/db/*`・`backend/tests/db_fixtures.py` に触れる。どれも `tenant-isolation` の paths に含まれる(`.claude/core-areas.json:295`・`:306`・`:311`・`:350`)。移行バッチ用ロールは**データ移行**の領域にもかかる。
→ 実装は ADR-001 の対応表どおりのモデル、敵対レビュー必須、**人間の逐行確認必須**(PR 作成者以外)。

**守る不変条件**(全ステップ共通):

- `contracts/authz/` 直下の probe 資産の差分 0 行(`oracle-seal.lock.json` の封印を動かさない)
- `contracts/authz/product/ddl-elements.json`(最終パス)を**作らない**(U-T1 の二状態テストを発火させない — ★8)
- `backend/pyproject.toml` / `backend/uv.lock` / `backend/tests/conftest.py` の差分 0 行
- `scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` の差分 0 行
- `backend/migrations/` に `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` / `GRANT` が 0 件(`D7`)
- **既存の `test_*.py` の差分 0 行**。変えてよい既存ファイルは、各ステップの合格条件に列挙したものに限る(design.md 5 節)
- 資産にパスワード・接続文字列を書かない(NFR-014)
- **期待値は固定 oracle と manifest の事実から導き、表分類資産から導かない**(design.md 1-5)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **資産指定オブジェクト `AuthzAssetSpec` と `PROBE_SPEC`**(`backend/src/pitchlog/authz/asset_spec.py` を新設)。生成器 `ddl.py` と body 検査器 `scripts/check_authz_function_bodies.py` が spec を受け取る。既定は `PROBE_SPEC` | 変える既存ファイルは `ddl.py` と `check_authz_function_bodies.py` だけ。`backend` と `harness` の pytest がすべて green。`ddl.py` の AST 検査(`backend/tests/test_authz_ddl.py:181`)が green のまま。**spec の取り違えで red**: probe 以外の scope 値を `PROBE_SPEC` で読むと拒否。probe 資産の差分 0 行 |
| 2 | **適用器・DB カタログ検査・DB fixture を spec 対応にする**(`provisioning.py` / `catalog.py` / `backend/tests/db_fixtures.py` / `backend/tests/db/conftest.py`)。操作種別の閉じた集合を spec ごとに持つ | 変える既存ファイルは上の 4 つだけ(`conftest.py` は再エクスポートの追加のみ)。既存の DB 試験がすべて green。**操作種別の集合が spec ごとに閉じている**(probe spec に製品の種別を渡すと拒否 — その逆も)。`requires_db` の収集件数が減っていない |
| 3 | **静的検査 `scripts/check_authz_catalog.py` の scope 検査を spec 対応にする**。probe 固有の閉じた検査は probe spec のときだけ走らせる | 変える既存ファイルは `check_authz_catalog.py` だけ。既存の `tests/test_check_authz_*.py` が差分 0 行で green。**product spec で probe 資産を読むと拒否・probe spec で product scope の資産を読むと拒否**。probe spec での検査の件数と結果が変更前と一致する(変更前後の出力を比較する試験) |
| 4 | **表分類資産 `contracts/authz/product/table-classification.json`**・**固定 oracle**(試験モジュール内の定数)・**意味の不変条件**(design.md 1-4・1-5) | 45 表が 5 プロファイルへ割り当てられ、**oracle と exact-map で一致**。母集合は `Base.metadata` と manifest の両方から導き、両者の一致も検査。**変異で red**: `admin_credentials → global_read_only` / `tenant_auth_subjects → tenant_owned` / 制御資源の表 → `tenant_owned` / 未割り当て / モデルの追加 / 秘密の列の列挙から 1 つ消す / `function_only` の `access_path.reason` を消す / 所有単位を列挙の外にする |
| 5 | **製品 DDL 資産(1)ロールとスキーマ**: `contracts/authz/product/ddl-elements.staged.json` と `function-bodies/`・`manifest.json`・**`PRODUCT_SPEC`**。ロール 4 種と `pitchlog_owner` の期待属性(design.md 2 節)・`public` と `authz_private` の所有と ACL・全 45 表の `ENABLE` + `FORCE` | `PRODUCT_SPEC` で生成器・body 検査器・静的検査が green。`contracts/authz/product/ddl-elements.json` が存在しない。**変異で red**: 1 表の `FORCE` を外す / `pitchlog_app` に `BYPASSRLS` を足す / `public` の `CREATE` の剥奪を消す。資産に `password` と接続文字列が 0 件 |
| 6 | **製品 DDL 資産(2)ポリシーと表 ACL**: `tenant_owned` 24 表・`self_tenant_row`・`global_read_only` のポリシー(述語は 1 要素から展開し、展開結果を固定)・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪 | **表分類と DDL の一致**を静的に検査(プロファイルごとのポリシーの有無・ACL・コマンド・roles・`USING`・`WITH CHECK` の exact-set。期待値は oracle から)。**変異で red**: ポリシーを 1 本消す / `WITH CHECK` を消す / `DELETE` を足す / `function_only` の表に ACL を足す / `::UUID` を `::BIGINT` に変える / 展開結果を手で書き換える(digest 不一致) |
| 7 | **製品 DDL 資産(3)制御資源の補助関数とポリシー**(design.md 1-3): `authz_private.tenant_has_effective_membership`・4 表のポリシー・関数 ACL | 静的検査が green。**関数の属性が exact**: `SECURITY DEFINER` / `STABLE` / 所有者 `pitchlog_shared_fn_owner` / `search_path` の末尾に `pg_temp` / 本文の表参照がすべてスキーマ修飾 / `PUBLIC` からの剥奪と `pitchlog_app` への `EXECUTE` が作成と同じトランザクション。**変異で red**: `pg_temp` の明示を外す / `PUBLIC` に `EXECUTE` を与える / 「実効グループ」の条件を外す / 「参加テナントが有効」の条件を外す / `group_invitations` の `admin` 条件を外す |
| 8 | **製品の適用器と使い捨てクラスタでの適用**(design.md 2-1・2-2・4-1・4-2): fixture `provisioned_product_catalog`(DB の所有者 = `pitchlog_owner` → `alembic upgrade head` → 製品 DDL を 1 トランザクションで適用)と**カタログ検査** | **カタログが資産と exact-set**(全 45 表の `relrowsecurity` と `relforcerowsecurity`・`pg_policy`・表 / スキーマ / 関数の ACL・ロール属性・DB とスキーマの所有者)。**`pg_auth_members` の辺が exact-set**(危険ロールへの `SET` / `INHERIT` / `ADMIN` の辺が 0 本)。**commit 後と rollback 後の両方で `current_user = session_user = provisioner`**。**失敗点 5 箇所**(design.md 4-2)で故障を注入し、カタログが適用前と一致。33 個のトリガ関数がすべて `SECURITY INVOKER`。**変異で red**: `SET LOCAL ROLE` を `SET ROLE` に変える / membership を `ADMIN` だけ残す / `SECURITY DEFINER` のトリガ関数を 1 つ混ぜた migration |
| 9 | **再適用と往復**(design.md 4-3) | 製品 DDL を 2 回適用しても、2 回目の後のカタログが 1 回目と一致。**製品 DDL の適用 → `downgrade base` → `upgrade head` → 再適用**の後のカタログが、初回の適用後と一致。既存の `backend/tests/db/test_migration_round_trip.py` は差分 0 行 |
| 10 | **実 DB 試験(1)`tenant_owned` 24 表**(design.md 6-1)。試験は固定 oracle からパラメタ化して生成する | 24 表**すべて**で: **最低要求 ①**(他テナントの行が 0 行)/ `WITH CHECK` 違反が `42501` / 未束縛が 0 行 / 不正 UUID が `22P02` / `DELETE` が `42501`。**変異で red**: 1 表のポリシーを外す・`FORCE` を外す・`WITH CHECK` を `true` にする |
| 11 | **実 DB 試験(2)その他のプロファイルと横断の観点**(design.md 6-2・6-3) | `self_tenant_row` / `global_read_only` / `function_only` 11 表(**`42501` であって 0 行ではない**)/ **制御資源の正負行列の全セル**(実効参加の `member` と `admin`・非参加・離脱・**グループ終了**・**参加テナントの無効化**・存在しないグループ)/ トリガの発火 / FORCE / 危険終点の交差が空 / **最低要求 ②**(`PUBLIC` が補助関数を実行できない)/ **最低要求 ③**(一時スキーマの乗っ取りが効かない)/ `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が補助関数 1 個だけ。**変異で red**: `function_only` の表に `SELECT` を与える / 補助関数の条件を 1 つずつ外す |
| 12 | **probe ↔ 製品の写像資産 `contracts/authz/product/probe-product-map.json`** と、その検査(design.md 7 節) | `probe の全原子要素 = mapped ∪ explicit_non_mapping` と `製品の全原子要素 = mapped の像 ∪ product_only` が**両方向 exact-set**。理由コードは閉じた列挙で、種別ごとに使えるコードが固定(`deferred_to_owning_unit` には `owner_unit` が必須)。`read_control_resources` が `owner_unit: U-C2`、`app_role` の `DELETE` が `forbidden_by_canon`。**変異で red**: probe 要素の写像を 1 つ消す / 製品要素を 1 つ足して写像しない / 列挙外の理由コード / 種別に合わない理由コード / 許可していない 1 対多 |
| 13 | **移行バッチ用ロールのライフサイクル**(design.md 8 節): 資産 `contracts/authz/product/migration-batch-lifecycle.json`・実行器と回収処理(`backend/src/pitchlog/authz/` に新設)・使い捨てクラスタでの試験 | 正本の 6 条件を全部検査(design.md 8 節の表)。**`write_targets` が導出集合 19 表と exact-set**(表 ID と権限の組)。**故障注入**(プロセスの強制終了): 有効化の commit 直後 / 投入の commit 後・監査の前 / 退役の途中 — **いずれも回収処理の後にロールが存在せず、監査行が期待どおり閉じている**。投入の途中の故障で、監査行「開始」「失敗」「退役」が残り、投入行が 0 件。`VALID UNTIL` の経過後に接続できない。定常の適用結果に `BYPASSRLS` を持つ `LOGIN` ロールが 0 件(孤児を残した状態でカタログ検査が不合格)。**変異で red**: `write_targets` に表を 1 つ足す / `DELETE` を足す / 退役を省く / 監査を投入と同じトランザクションで書く / 移行バッチ用ロールに監査の表の権限を与える |
| 14 | **capability の誤開放を防ぐ検査**(design.md 10 節)。capability の集合そのものは空のまま | `function_only` の表を対象にした capability を 1 つ足す変異で red。`effective_group_control` の表を対象にした書き込みの capability で red。`direct` の表を対象にした capability は検査を通る(**試験の中だけで足し、製品のパッケージには収載しない**)。`backend/src/pitchlog/repositories/repository_contract.py:57-59` の 3 集合が空のまま |

**ステップの順序と並行性**:

- 1 → 2 → 3 は順に依存する。4 は 1 と独立(表分類は spec を使わない)なので、**4 を先に入れて帯 2 へ早く渡す**ことができる
- 5 → 6 → 7 → 8 → 9 → 10 → 11 は順に依存する(5 は 1〜4 の後)
- 12 は 7 の後、13 は 8 の後、14 は 4 の後ならいつでもよい
- **TSK-431 とは衝突しない**(本計画は `scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` に触れない)
- **U-T1 の後続単位との衝突面**は `backend/tests/db/conftest.py`(再エクスポートを足すだけ)と `contracts/authz/product/`

**正本の追随**(3 節)は、ステップ 14 の後に /sync-docs で行い、PR A に含める(Claude が書く。委任しない — 設計書 7.6-2)。

## 5. DoD(受け入れ基準)

Notion カードの DoD を ★1〜★8 に合わせて書き換えたもの。**承認後に Notion を同期する**。

- [ ] **全 45 表に物理プロファイルが排他で割り当てられ、未割り当てが 0 件**(母集合は `Base.metadata` から導出。割り当ては明示メタデータ。**固定 oracle と一致**)。**プロファイルは 5 種で確定**し、カードが求めた「親表経由」「認証前グローバル可変」は `function_only` の到達経路の理由として記録した(★5)
- [ ] **全表が `ENABLE` + `FORCE ROW LEVEL SECURITY`**(正本 3-2 節の「全テーブルへ FORCE」を変えない)
- [ ] **全表で `{プロファイル, ACL, コマンド, roles, USING, WITH CHECK}` が exact-set**(静的検査とカタログ検査の両方)
- [ ] **制御資源 4 表が、正本 3-0・3-5 節の「実効グループ ∧ 実効参加」で守られている**(グループ終了・参加テナントの無効化で見えなくなることを含む — ★6)
- [ ] **使い捨てクラスタで、製品 migration と製品 authz DDL の適用、カタログ検査、再適用と往復、実 DB 試験が green**。最低要求 ① を 24 表すべてで、②③ を補助関数で表明した。④ は対象が無いことを表明した
- [ ] **ロールの membership が `ADMIN OPTION` まで exact-set**。適用後に provisioner の `current_user` が戻っている
- [ ] **probe ↔ 製品の写像が両方向 exact-set**(非写像の理由コードと `owner_unit` が全件に付く)
- [ ] **移行バッチ用ロールのライフサイクル 6 条件が検査されている**(書き込み先は導出集合と exact-set・成功時と失敗時とプロセス停止時の退役・監査が失敗時も残る・孤児の回収と定常検出)
- [ ] **capability は空のまま**で、`function_only` の表から capability を作ると red になる
- [ ] **12-8 節に残件・所有者(U-C1 / U-C2 / U-C3 / U-A2 / TSK-344 / PR B のタスク)・発効条件を記録した**
- [ ] **`contracts/authz/` 直下の probe 資産の差分 0 行**(`oracle-seal.lock.json` の封印を動かさない)
- [ ] **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の差分 0 行**
- [ ] **PR に 12-4 の判定記録を残した**(「対象入口なし」)
- [ ] **申し送りを Notion と PR 本文に記録した**: TSK-349 の射程の書き換え(★1)/ PR B のタスクの起票(★8)/ `event_slots` の食い違い(★3)/ 3-2 節の典拠(★4)/ TSK-344 への運用契約 / TSK-250 への写像資産の正の所在
- [ ] pytest / ruff / ty green(`backend` と `harness` の両方)
- [ ] **コア領域として敵対レビューと、人間の逐行確認(PR 作成者以外)を通した**

## 6. テスト計画

| NFR-019 の種別 | 足すもの | ステップ |
| --- | --- | --- |
| **単体** | 資産指定オブジェクトと spec の取り違え・表分類の oracle と意味の不変条件・DDL 資産と表分類の一致・補助関数の属性・写像の両方向 exact-set・capability ガード | 1・2・3・4・5・6・7・12・14 |
| **越境**(NFR-019(b) の DB 層) | 最低要求 ① を 24 表すべて・`WITH CHECK`・未束縛・`function_only` の `42501`・制御資源の正負行列・最低要求 ②③・危険終点(使い捨てクラスタ・`requires_db`) | 10・11 |
| **故障系** | 適用の失敗点 5 箇所での原子性・`SET LOCAL ROLE` の復帰・不正 UUID の `22P02`・移行バッチのプロセス停止 3 箇所と回収・投入途中の故障と監査の残存 | 8・10・13 |
| **一致性** | 述語の展開結果と要素の digest・再適用の収束・往復後のカタログの一致 | 6・9 |
| **E2E** | **対象外**(入口を開かない。HTTP の越境テストは入口を開く単位が同じ PR に含める — ADR-004 D-2) | — |

- **各ステップの合格条件に、変異で red になることを入れた**(改変前の green を assert してから変異させる)
- DB 試験は既存の `requires_db` マーカーに乗せる。収集 0 件でセッションを失敗にする既存の仕組み(`backend/tests/db/conftest.py:83-119`)に守られる
- CI では `backend` ジョブ(`.github/workflows/ci.yml:210-260`)が走る。使い捨てクラスタは既存の `disposable_postgres_cluster` と同じ `docker run` 方式で起動する
