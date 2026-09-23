---
feature: product-authz-surface
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域           # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc
branch: feature/product-authz-surface
created: 2026-09-24
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
帯 2 の単位(U-M1・U-D1 ほか)も、製品表への操作を開く capability を、表分類が確定するまで足せない(`../tenant-boundary-enforcement/plan.md:87`・`../tenant-boundary-enforcement/design.md:321`)。

本単位は、**全 45 表の許可プロファイル・製品 authz DDL 資産・probe ↔ 製品の写像・capability カタログ・移行バッチ用ロールの資産**を確定し、使い捨てクラスタで適用して検査するところまでを行う。
**実スキーマへの適用は TSK-344、ランタイム契約の切り替えは PR B(別タスク)が行う。**

### 計画の前提とした判断(承認の対象 — 本計画の承認をもって確定する)

| # | 判断 | 典拠 |
| --- | --- | --- |
| ★1 | **移行バッチ用ロールは、本単位が「書き込み先の資産・有効な間の形・定常の不変条件」を持ち、ライフサイクルの実行(退役・接続監査・孤児回収・同時実行・状態の収束)は TSK-349 が持つ**(人間の判断 2026-09-24)。TSK-349 は取り下げず、射程を書き換える。TSK-349 の旧方式(凍結 probe 資産への追加と `--reseal-oracle`)は採らない | design.md 8 節 |
| ★2 | **TSK-382(SP-06 の字面衝突)の射程は踏まない**。本単位は製品トラフィックを受ける配備先に適用せず、SP-06・12-4 の non-serving 宣言・12-6 の受け取り先表のいずれも変えない。「実スキーマ」の意味も定義しない | design.md 12 節 |
| ★3 | **移行バッチ用ロールの書き込み先は、導出集合(`import_batch_id` を持つ表 ∪ `migration_runs` の 19 表)と完全に一致させ、例外を置かない**。監査の表は含めない(監査は移行実行器の管理接続が書く — TSK-349)。`event_slots` が取り込みバッチ識別子を持たない食い違い(正本 12-3 不変条件 1 とスキーマ)は TSK-349 へ申し送る | design.md 8-1 |
| ★4 | **正本 3-2 節 `:296` の監査根拠(NFR-012)は本単位では直さない**。approved の正本にある典拠の誤りで、実装追随ではないため。承認後に専用の Notion タスクを起票し、その ID を 12-8 と DoD に記録する | design.md 11 節 |
| ★5 | **物理プロファイルは 5 種**(`tenant_owned` / `self_tenant_row` / `effective_group_control` / `global_read_only` / `function_only`)。カードが求めた「親表経由」「認証前グローバル可変」は、直接アクセスを許さない `function_only` に倒し、到達経路の理由として記録する(正本はこの 2 表の RLS を定めていない)。**Notion の DoD の字面を書き換える** | design.md 1-2 |
| ★6 | **制御資源 4 表は、正本 3-0・3-5 節どおり「実効グループ ∧ 実効参加」の RLS ポリシーで守る**。再帰と他テナントの有効状態の問題は、真偽値だけを返す補助関数(`SECURITY DEFINER`・所有者 `pitchlog_shared_fn_owner`)で解く。U-T1 design の P3 の記述(終了済みグループも見え続ける)は正本と矛盾していたので是正する | design.md 1-3 |
| ★7 | **capability は「記述」と「登録」に分ける**。本単位は表分類から導いた **capability カタログ**(開けてよい操作の閉じた一覧)を出す。**登録(公開 registry)は空のまま残し**、経路を持つ単位が行う。カタログに無い capability の登録は red | design.md 10 節 |
| ★8 | **PR を 2 本に分ける**(人間の承認 2026-09-24)。**本計画 = PR A**(ステップ 1〜16 と正本の追随。TSK-431 を待たない)。**PR B**(ランタイム契約の切り替え・暫定資産の削除)は TSK-431 のマージ後に、別タスク・別ブランチ・別計画書で行う。PR A の間、製品 DDL 資産は `ddl-elements.staged.json` に置く。**「未発効」の第三状態として明示し、新しい試験で検査する**。正本 12-8 と Notion には「資産は確定・未発効」と書き、TSK-424 は PR B のマージまで完了にしない | design.md 3-2・9 節 |

## 2. スコープ

### やること(PR A)

1. **資産指定オブジェクト**で authz ツールチェーンを一般化する(design.md 5 節)
2. **全 45 表の表分類資産**と、固定 oracle(7.7 に従う凍結資産)・意味の不変条件による検査(design.md 1 節)
3. **製品 authz DDL 資産**(`ddl-elements.staged.json` と `function-bodies/`)。ロール 4 種・DB とスキーマの所有と ACL・全表の `ENABLE` + `FORCE`・ポリシー・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪・制御資源の補助関数(design.md 1〜3 節)
4. **製品の適用器**(migration の後に 1 トランザクション・固定の 6 手順・`SET LOCAL ROLE`・membership は宣言と exact-set)と、使い捨てクラスタでの適用・カタログ検査・再適用と往復(design.md 2-2・4 節)
5. **実 DB 試験**(design.md 6 節)
6. **probe ↔ 製品の写像資産**と、両方向 exact-set の検査(design.md 7 節)
7. **移行バッチ用ロールの資産**(書き込み先・有効な間の形)と、有効な間の形の試験・定常の不変条件(design.md 8 節)
8. **capability カタログ**と、登録の検査(design.md 10 節)
9. **正本の追随**: `data-model.md` 12-8 の分割・変更履歴・`docs/README.md`(design.md 11 節)
10. **申し送り**の記録(Notion と PR 本文): TSK-349 の射程の書き換え / PR B のタスク起票 / `event_slots` の食い違い / 3-2 節の典拠 / TSK-344 への運用契約(往復の non-serving 区間・移行ロールの定常の不変条件)/ TSK-250 への写像資産の正の所在

### やらないこと

| やらないこと | 行き先 |
| --- | --- |
| **ランタイム契約の切り替え・暫定資産の削除・7.7 の削除記録** | **PR B**(TSK-431 のマージ後。別タスクとして起票する — ★8) |
| **実スキーマへの適用と、越境テストの再実行** | TSK-344(`data-model.md:2846`・裁定 A-2) |
| **越境関数の本体・その ACL・`search_path`**(補助関数 1 個を除く) | U-C1 / U-C2 / U-C3 / U-A2(`../product-impl-unit-split/plan.md:224-227`) |
| **認証・レート制限・管理経路の関数**(`function_only` 表への到達経路) | U-A1 / U-A2 |
| **制御資源の列の粒度の制限**(テナント名のみ・`admin` のみの列) | U-C2 のアプリ層(正本の二重構成 — `data-model.md:137`) |
| **capability の登録(製品表への操作を開くこと)** | 経路を持つ単位(U-01・U-M1・U-D1 ほか — ★7) |
| **移行バッチ用ロールのライフサイクルの実行**(退役・接続監査・孤児回収・同時実行・状態の収束)・**実運用の移行実行**・**`event_slots` の食い違いの解消** | TSK-349(★1・★3。申し送りは design.md 8-4) |
| **正本 3-2 節 `:296` の典拠の訂正** | 承認後に起票する専用タスク(★4) |
| **probe 資産(`contracts/authz/` 直下)の変更** | 変更しない(封印 — `contracts/authz/oracle-seal.lock.json:40-88`) |
| **SP-06・12-4 の non-serving 宣言・12-6 の受け取り先表・3-5 節の述語の変更** | 変えない(★2・★6) |
| **`scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` の変更** | 触れない(TSK-431 と PR B の射程) |
| **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の変更** | 変えない(差分 0 行) |
| **HTTP の入口を開くこと** | 開かない。12-4 の判定記録には「対象入口なし」と書く(`data-model.md:2534`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8 節(`:2844-2846`) | TSK-317 行を分割し、TSK-424(**PR A で資産は確定・未発効**)/ TSK-349(移行ロールのライフサイクルの実行 — 残件)/ 3-2 節の典拠の訂正タスク(残件)/ U-C1・U-C2・U-C3・U-A2(越境関数と最低要求 ②③④ の残り — 残件)/ TSK-344(実スキーマでの再実行 — 残件)/ PR B のタスク(ランタイム契約の切り替え — 残件)に割り当てる。**「解消済み」にしない** | PR レビュー(7.6-3 前段・実装追随の節更新) |
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
| 4 | **表分類資産 `contracts/authz/product/table-classification.json`**・**固定 oracle `table-classification.oracle.json`**(7.7 に従う凍結資産・追記のみの履歴と digest の鎖)・**意味の不変条件**(design.md 1-4・1-5) | 45 表が 5 プロファイルへ割り当てられ、**oracle と exact-map で一致**。母集合は `Base.metadata` と manifest の両方から導き、両者の一致も検査。**検査器のソースに割り当ての値が 0 件**(7.7-1)。**変異で red**: `admin_credentials → global_read_only` / `tenant_auth_subjects → tenant_owned` / 制御資源の表 → `tenant_owned` / 未割り当て / モデルの追加 / 秘密の列の列挙から 1 つ消す / `function_only` の `access_path.reason` を消す / 所有単位を列挙の外にする / **oracle だけを履歴なしで変える** / **両方を変えて履歴を足さない** / 履歴の途中の項目を書き換える |
| 5 | **製品 DDL 資産(1)ロールとスキーマ**: `contracts/authz/product/ddl-elements.staged.json` と `function-bodies/`・`manifest.json`・**`PRODUCT_SPEC`**。ロール 4 種と `pitchlog_owner` の期待属性・恒久の特権主体の宣言(design.md 2 節)・`public` と `authz_private` の所有と ACL・全 45 表の `ENABLE` + `FORCE`。**未発効状態の試験** `backend/tests/test_authz_product_staging.py`(design.md 3-2) | `PRODUCT_SPEC` で生成器・body 検査器・静的検査が green。**未発効状態の検査が green**: 最終パス `ddl-elements.json` が無い / ランタイムは暫定のまま / `pending_switch` がタスク ID を持つ / staged の保護対象 = 暫定の保護対象 ∪ 宣言済みの追加分 / **staged と最終パスが両方あると red**。既存の `test_authz_runtime_contract.py` の差分 0 行。**変異で red**: 1 表の `FORCE` を外す / `pitchlog_app` に `BYPASSRLS` を足す / `public` の `CREATE` の剥奪を消す。資産に `password` と接続文字列が 0 件 |
| 6 | **製品 DDL 資産(2)ポリシーと表 ACL**: `tenant_owned` 24 表・`self_tenant_row`・`global_read_only` のポリシー(述語は 1 要素から展開し、展開結果を固定)・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪 | **表分類と DDL の一致**を静的に検査(プロファイルごとのポリシーの有無・ACL・コマンド・roles・`USING`・`WITH CHECK` の exact-set。**期待値は oracle から**)。**変異で red**: ポリシーを 1 本消す / `WITH CHECK` を消す / `DELETE` を足す / `function_only` の表に ACL を足す / `::UUID` を `::BIGINT` に変える / 展開結果を手で書き換える(digest 不一致) |
| 7 | **製品 DDL 資産(3)制御資源の補助関数とポリシー**(design.md 1-3): `authz_private.tenant_has_effective_membership`・4 表のポリシー・関数 ACL・**所有者の表権限** | 静的検査が green。**関数の属性が exact**: `SECURITY DEFINER` / `STABLE` / 所有者 `pitchlog_shared_fn_owner` / `search_path` の末尾に `pg_temp` / 本文の表参照がすべてスキーマ修飾 / `PUBLIC` からの剥奪と `pitchlog_app` への `EXECUTE` が作成と同じトランザクション。**所有者の表権限が exact-set**(`public` の `USAGE` と 3 表の `SELECT` のみ)。**変異で red**: `pg_temp` の明示を外す / `PUBLIC` に `EXECUTE` を与える / 「実効グループ」「参加テナントが有効」「`admin`」の条件を 1 つずつ外す / 所有者に表を 1 つ足す・1 つ欠く |
| 8 | **製品の適用器と、使い捨てクラスタでの適用の fixture**(design.md 2-1・4-1・4-2): bootstrap(superuser → 非 superuser の provisioner → `pitchlog_owner` → DB の所有者)→ `alembic upgrade head` → 製品 DDL を **1 トランザクション・固定の 6 手順**で適用する。fixture `provisioned_product_catalog` を新設 | 適用が成功し、**commit 後の同じ接続で `current_user = session_user = provisioner`**。bootstrap 以後に superuser の接続を使っていない(接続の記録で確認)。既存の `provisioned_catalog` の振る舞いが変わらない |
| 9 | **カタログの exact-set 検査**(design.md 2-2・3-4・6-3 の危険終点) | 全 45 表の `relrowsecurity` と `relforcerowsecurity`・`pg_policy`・表 / スキーマ / 関数の ACL・ロール属性・DB とスキーマの所有者が**資産と exact-set**。**`pg_auth_members` が宣言と exact-set**(製品ロールから出る辺 0 本・provisioner の辺は `ADMIN` のみ・provisioner へ入る辺 0 本)。LOGIN できる危険ロールの集合 = 恒久の特権主体の許可集合。33 個のトリガ関数がすべて `SECURITY INVOKER`。**変異で red**: 宣言に無い `ADMIN` の辺 / 製品ロールから出る辺 / `SECURITY DEFINER` のトリガ関数を 1 つ混ぜた migration |
| 10 | **適用の原子性と故障系**(design.md 4-2) | **失敗点 6 箇所**(ロール作成の直後 / `SET LOCAL ROLE` の直後 / ポリシー作成の直後 / ACL 正規化の途中 / `RESET ROLE` の直後 / `SET` の剥奪の直前)で故障を注入し、**カタログが適用前と一致**。**rollback 後の同じ接続で `current_user = session_user = provisioner`**。**変異で red**: `SET LOCAL ROLE` を `SET ROLE` に変える / `RESET ROLE` を省く / 一時の辺の `SET` を 1 本残す |
| 11 | **再適用と往復**(design.md 4-3) | 製品 DDL を 2 回適用しても、2 回目の後のカタログが 1 回目と一致。**製品 DDL の適用 → `downgrade base` → `upgrade head` → 再適用**の後のカタログが、初回の適用後と一致。既存の `backend/tests/db/test_migration_round_trip.py` は差分 0 行 |
| 12 | **実 DB 試験(1)`tenant_owned` 24 表**(design.md 6-1)。試験は固定 oracle からパラメタ化して生成する | 24 表**すべて**で: **最低要求 ①**(他テナントの行が 0 行)/ `WITH CHECK` 違反が `42501` / 未束縛が 0 行 / 不正 UUID が `22P02` / `DELETE` が `42501`。**変異で red**: 1 表のポリシーを外す・`FORCE` を外す・`WITH CHECK` を `true` にする |
| 13 | **実 DB 試験(2)その他のプロファイルと横断の観点**(design.md 6-2・6-3) | `self_tenant_row` / `global_read_only` / `function_only` 11 表(**`42501` であって 0 行ではない**)/ **制御資源の正負行列の全セル**(実効参加の `member` と `admin`・非参加・離脱・**グループ終了**・**参加テナントの無効化**・存在しないグループ)/ トリガの発火 / FORCE / **最低要求 ②**(`PUBLIC` が補助関数を実行できない)/ **最低要求 ③**(一時スキーマの乗っ取りが効かない)/ `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が補助関数 1 個だけ。**変異で red**: `function_only` の表に `SELECT` を与える / 補助関数の条件を 1 つずつ外す |
| 14 | **probe ↔ 製品の写像資産 `contracts/authz/product/probe-product-map.json`** と、その検査(design.md 7 節) | `probe の全原子要素 = mapped ∪ explicit_non_mapping` と `製品の全原子要素 = mapped の像 ∪ product_only` が**両方向 exact-set**。理由コードは閉じた列挙で、種別ごとに使えるコードが固定(`deferred_to_owning_unit` には `owner_unit` が必須)。`read_control_resources` が `owner_unit: U-C2`、`app_role` の `DELETE` が `forbidden_by_canon`。**変異で red**: probe 要素の写像を 1 つ消す / 製品要素を 1 つ足して写像しない / 列挙外の理由コード / 種別に合わない理由コード / 許可していない 1 対多 |
| 15 | **移行バッチ用ロールの資産 `contracts/authz/product/migration-batch-role.json`**(書き込み先と有効な間の形)と、**有効な間の形の試験**・**定常の不変条件**(design.md 8-1〜8-3) | **`write_targets` が導出集合 19 表と exact-set**(表 ID と権限の組)。使い捨てクラスタで資産どおりに作ったロールが、有効な間の形を満たす(到達しない・所有しない・表 ACL が exact・属性)。**定常の不変条件**(宣言されていない `LOGIN` + `BYPASSRLS` のロールが 0 件)がカタログ検査に入り、資産の形のロールを 1 つ残すと不合格。**変異で red**: `write_targets` に表を 1 つ足す / `DELETE` を足す / ロールに `pitchlog_app` からの辺を足す / ロールに表を 1 つ所有させる |
| 16 | **capability カタログ `contracts/authz/product/capability-catalog.json`** と**登録の検査**(design.md 10 節)。登録の集合そのものは空のまま | カタログが表分類から生成器で導出され、導出結果と一致(手書きの変更で red)。`direct` の表だけが載り、`effective_group_control` は `read` だけ、`function_only` は 0 件。**カタログに無い capability を登録する変異で red**(試験の中だけで仮に登録する — 製品のパッケージには収載しない)。`backend/src/pitchlog/repositories/repository_contract.py:57-59` の 3 集合が空のまま |

**ステップの順序と並行性**:

- 1 → 2 → 3 は順に依存する。**4 は 1〜3 と独立**(表分類は spec を使わない)なので、**4 を先に入れて帯 2 へ早く渡す**ことができる
- 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 は順に依存する(5 は 1〜4 の後)
- 14 は 7 の後、15 は 9 の後、16 は 4 の後ならいつでもよい
- **TSK-431 とは衝突しない**(本計画は `scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` に触れない)
- **U-T1 の後続単位との衝突面**は `backend/tests/db/conftest.py`(再エクスポートを足すだけ)と `contracts/authz/product/`

**正本の追随**(3 節)は、ステップ 16 の後に /sync-docs で行い、PR A に含める(Claude が書く。委任しない — 設計書 7.6-2)。

## 5. DoD(受け入れ基準)

Notion カードの DoD を ★1〜★8 に合わせて書き換えたもの。**承認後に Notion を同期する**。

- [ ] **全 45 表に物理プロファイルが排他で割り当てられ、未割り当てが 0 件**(母集合は `Base.metadata` から導出。割り当ては明示メタデータ。**固定 oracle と一致**)。**プロファイルは 5 種で確定**し、カードが求めた「親表経由」「認証前グローバル可変」は `function_only` の到達経路の理由として記録した(★5)
- [ ] **全表が `ENABLE` + `FORCE ROW LEVEL SECURITY`**(正本 3-2 節の「全テーブルへ FORCE」を変えない)
- [ ] **全表で `{プロファイル, ACL, コマンド, roles, USING, WITH CHECK}` が exact-set**(静的検査とカタログ検査の両方)
- [ ] **制御資源 4 表が、正本 3-0・3-5 節の「実効グループ ∧ 実効参加」で守られている**(グループ終了・参加テナントの無効化で見えなくなることを含む — ★6)
- [ ] **使い捨てクラスタで、製品 migration と製品 authz DDL の適用、カタログ検査、再適用と往復、実 DB 試験が green**。最低要求 ① を 24 表すべてで、②③ を補助関数で表明した。④ は対象が無いことを表明した
- [ ] **ロールの membership が `ADMIN OPTION` まで exact-set**。適用後に provisioner の `current_user` が戻っている
- [ ] **probe ↔ 製品の写像が両方向 exact-set**(非写像の理由コードと `owner_unit` が全件に付く)
- [ ] **移行バッチ用ロールの資産が確定している**: 書き込み先が導出集合 19 表と exact-set・有効な間の形(到達しない・所有しない・表 ACL)が使い捨てクラスタで検査されている・定常の不変条件がカタログ検査に入っている。**ライフサイクルの実行は TSK-349 へ申し送った**(design.md 8-4 の要求事項を TSK-349 のカードに記録)
- [ ] **capability カタログが表分類から導出されている**。登録の集合は空のままで、カタログに無い capability の登録は red になる
- [ ] **表分類の固定 oracle が 7.7 に従う凍結資産になっている**(検査器のソースに値が無い・追記のみの履歴と digest の鎖)
- [ ] **PR A の段階が「未発効」の第三状態として検査されている**(staged と最終パスの二重は red)
- [ ] **12-8 節に残件・所有者(U-C1 / U-C2 / U-C3 / U-A2 / TSK-344 / TSK-349 / PR B のタスク / 3-2 節の典拠の訂正タスク)・発効条件を記録した**。TSK-424 は「資産は確定・未発効」と書いた
- [ ] **`contracts/authz/` 直下の probe 資産の差分 0 行**(`oracle-seal.lock.json` の封印を動かさない)
- [ ] **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の差分 0 行**
- [ ] **PR に 12-4 の判定記録を残した**(「対象入口なし」)
- [ ] **申し送りを Notion と PR 本文に記録した**: TSK-349 の射程の書き換えと design.md 8-4 の要求事項(★1)/ PR B のタスクの起票(★8)/ `event_slots` の食い違い(★3)/ 3-2 節の典拠の訂正タスクの起票(★4)/ TSK-344 への運用契約 / TSK-250 への写像資産の正の所在
- [ ] pytest / ruff / ty green(`backend` と `harness` の両方)
- [ ] **コア領域として敵対レビューと、人間の逐行確認(PR 作成者以外)を通した**

## 6. テスト計画

| NFR-019 の種別 | 足すもの | ステップ |
| --- | --- | --- |
| **単体** | 資産指定オブジェクトと spec の取り違え・表分類の oracle(履歴と digest の鎖)と意味の不変条件・未発効状態・DDL 資産と表分類の一致・補助関数の属性と所有者の権限・写像の両方向 exact-set・移行ロールの書き込み先・capability カタログと登録 | 1〜7・14〜16 |
| **越境**(NFR-019(b) の DB 層) | 最低要求 ① を 24 表すべて・`WITH CHECK`・未束縛・`function_only` の `42501`・制御資源の正負行列・最低要求 ②③・危険終点と membership の exact-set・移行ロールの有効な間の形(使い捨てクラスタ・`requires_db`) | 9・12・13・15 |
| **故障系** | 適用の失敗点 6 箇所での原子性・`SET LOCAL ROLE` の復帰(commit 後と rollback 後)・不正 UUID の `22P02` | 8・10・12 |
| **一致性** | 述語の展開結果と要素の digest・再適用の収束・往復後のカタログの一致・capability カタログと表分類の一致 | 6・11・16 |
| **E2E** | **対象外**(入口を開かない。HTTP の越境テストは入口を開く単位が同じ PR に含める — ADR-004 D-2) | — |

- **各ステップの合格条件に、変異で red になることを入れた**(改変前の green を assert してから変異させる)
- DB 試験は既存の `requires_db` マーカーに乗せる。収集 0 件でセッションを失敗にする既存の仕組み(`backend/tests/db/conftest.py:83-119`)に守られる
- CI では `backend` ジョブ(`.github/workflows/ci.yml:210-260`)が走る。使い捨てクラスタは既存の `disposable_postgres_cluster` と同じ `docker run` 方式で起動する
