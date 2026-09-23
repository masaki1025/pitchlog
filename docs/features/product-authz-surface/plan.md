---
feature: product-authz-surface
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域           # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc
branch: feature/product-authz-surface
created: 2026-09-24
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TSK-424 製品認可面の確定

## 1. 背景・目的

- Notion: [TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)(U-T1〔TSK-390〕から 2026-09-17 に分離 — 人間の裁定・山田正輝)
- 調査: [research.md](./research.md)(2026-09-24・4 並列)/ 詳細設計: [design.md](./design.md)
- 要件: [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)(チーム間データ分離・初日から全機能)/ [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)(越境テスト)/ [NFR-014](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-014)(シークレット)/ [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034)(認可行列)。機構の正は `docs/design/data-model.md` 3 章(RLS の採否は同書の設計判断 — `:139-149`)

**なぜやるか**: 製品の DB には、RLS・ロール・ACL がまだ 1 つも無い(`backend/migrations` に 0 件、`contracts/authz/product/` は未作成)。
いまある認可資産は、機構の検証用の probe(`product_schema: false`)だけである。
このため、越境テストの再実行ゲート(TSK-344)の通過条件 ①「RLS のポリシーとロールの DDL が実スキーマへ適用されている」(`data-model.md:2529`)が、**適用する DDL そのものが無い**という理由で満たせない。
U-T1 のランタイム(PR #72)も、期待アプリロール名と保護対象を暫定資産から読んでいる(`backend/src/pitchlog/authz/runtime_contract.py:7-8`)。

本単位は、**全 45 表の許可プロファイル・製品 authz DDL 資産・probe ↔ 製品の写像・移行バッチ用ロールのライフサイクル**を確定し、
使い捨てクラスタで適用して検査するところまでを行う。**実スキーマへの適用は TSK-344 が行う。**

### 計画の前提とした判断(承認の対象 — ★ は本計画の承認をもって確定する)

| # | 判断 | 典拠 |
| --- | --- | --- |
| ★1 | **移行バッチ用ロールは本単位が製品資産として持つ。TSK-349 は取り下げて吸収する**。TSK-349 の方式(凍結 probe 資産へ追加し `--reseal-oracle`)は採らない。「本番の移行実行の中で確かめること」は FR-038 の移行タスクへ移す | design.md 8-3・research.md 未解決 1 |
| ★2 | **TSK-382(SP-06 の字面衝突)の射程は踏まない**。本単位は実スキーマへ適用せず、SP-06(12-9)・12-4 の non-serving 宣言・**12-6 の受け取り先表**のいずれも変えない | design.md 12 節 |
| ★3 | **移行バッチ用ロールの書き込み先**は「`import_batch_id` を持つ表 ∪ `migration_runs`」を導出規則とし、それを超える表(`event_slots` / `medical_note_versions` / `admin_operation_logs`)には閉じた理由コードを付ける | design.md 8-1 |
| ★4 | **正本 3-2 節 `:296` の監査根拠を NFR-012 → 裁定 A-3 に直す**。引用の訂正で契約は変えないので、7.6-3 前段(PR レビュー)で扱う | design.md 11 節 |
| ★5 | **物理プロファイルは 4 種**(`tenant_owned` / `self_tenant_row` / `global_read_only` / `function_only`)。カードが求めた「親表経由」「認証前グローバル可変」は、直接アクセスを許さない `function_only` に倒し、到達経路の理由として記録する。**Notion の DoD の字面を書き換える** | design.md 1-2 |
| ★6 | **制御資源 4 表は `function_only`**。U-T1 design の P3(直接アクセスの RLS ポリシー)は、正本 3-0 / 3-5 節の述語(実効グループ ∧ 実効参加)と矛盾していたので是正する。読み取りは U-C2、操作は U-C1 の関数経由 | design.md 1-3 |
| ★7 | **capability は空のまま残す**。本単位が出すのは、capability を導くための表分類資産まで | design.md 10 節 |
| ★8 | **ランタイム契約の切り替え(暫定資産の削除)は最後のステップにし、TSK-431(7D の是正)のマージを待つ**。7D を開けたまま削除しない | design.md 9-1 |

## 2. スコープ

### やること

1. **資産指定オブジェクト**で authz ツールチェーンを一般化する(生成器・body 検査器・適用器・カタログ検査・静的検査・DB fixture)。既定は probe で、既存テストは無改変で green に保つ(design.md 5 節)
2. **全 45 表の表分類資産**(`contracts/authz/product/table-classification.json`)と、その静的検査(design.md 1 節)
3. **製品 authz DDL 資産**(`contracts/authz/product/ddl-elements.json` と `function-bodies/`)。ロール 4 種・`public` スキーマの ACL・全表の `ENABLE` + `FORCE`・ポリシー・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪(design.md 2・3 節)
4. **製品の適用器**(migration の後に 1 トランザクションで適用)と、使い捨てクラスタでの適用とカタログ検査(design.md 4 節)
5. **実 DB 試験**: 最低要求 ①・`USING` / `WITH CHECK`・未束縛・不正 UUID・`DELETE`・プロファイルごとの期待 SQLSTATE・トリガ関数・FORCE・危険終点(design.md 6 節)
6. **probe ↔ 製品の写像資産**と、両方向 exact-set の検査(design.md 7 節)
7. **移行バッチ用ロールのライフサイクル資産**と、使い捨てクラスタでの有効化 → 投入 → 退役の試験(design.md 8 節)
8. **capability の誤開放を防ぐ検査**(`function_only` の表から capability を作ると red)(design.md 10 節)
9. **ランタイム契約の切り替え**(製品資産の `runtime_contract` → 生成モジュールの作り直し → 暫定資産の削除と 7.7 の記録)(design.md 9 節)
10. **正本の追随**: `data-model.md` 12-8 の TSK-317 行の分割、3-2 節 `:296` の引用の訂正、変更履歴、`docs/README.md`(design.md 11 節)

### やらないこと

| やらないこと | 行き先 |
| --- | --- |
| **実スキーマへの適用と、越境テストの再実行** | TSK-344(`data-model.md:2846`・裁定 A-2) |
| **越境関数の本体・その ACL・`search_path`**(最低要求 ②③④ の対象) | U-C1 / U-C2 / U-C3 / U-A2(`../product-impl-unit-split/plan.md:224-227`)。本単位は「関数 0 件」を宣言し、関数が足されたら red になる試験を置く |
| **認証・レート制限・管理経路の関数**(`function_only` 表への到達経路) | U-A1 / U-A2 |
| **capability の中身(製品表への操作を開くこと)** | 経路を持つ単位(U-01 ほか)。本単位は空のまま残す(★7) |
| **実運用の移行実行**(FR-038) | 移行タスク |
| **probe 資産(`contracts/authz/` 直下)の変更** | 変更しない(封印 — `contracts/authz/oracle-seal.lock.json:40-88`) |
| **SP-06・12-4 の non-serving 宣言・12-6 の受け取り先表の変更** | TSK-382(★2) |
| **`data-model.md` 3-5 節の述語の変更** | 変えない。本単位は制御資源を `function_only` に倒すだけで、述語は U-C1 / U-C2 の関数が満たす |
| **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の変更** | 変えない(差分 0 行) |
| **TSK-431 の 7A〜7E の是正** | TSK-431(★8。本単位は待つだけ) |
| **HTTP の入口を開くこと** | 開かない。12-4 の判定記録には「対象入口なし」と書く(`data-model.md:2534`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8 節(`:2844-2846`) | TSK-317 行を分割し、TSK-424(本 PR で landed)/ U-C1・U-C2・U-C3・U-A2(越境関数と ②③④ — 残件)/ TSK-344(実スキーマでの再実行 — 残件)に割り当てる。**「解消済み」にしない** | PR レビュー(7.6-3 前段・実装追随の節更新) |
| `docs/design/data-model.md` 3-2 節(`:296`) | 監査の根拠の引用を `NFR-012` → 裁定 `A-3` に訂正する(★4)。契約は変えない | PR レビュー(同上) |
| `docs/design/data-model.md` 変更履歴 | 上の 2 件を追記する。**版は上げない** | PR レビュー(同上) |
| `docs/README.md` | 索引を現行化する(`contracts/authz/product/` の新設) | PR レビュー |
| `docs/requirements/` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(7.7 には従う側。条文は変えない) | — |
| `docs/adr/` | **反映なし**(ADR-004 の適用単位の判定に従う側) | — |
| `docs/design/data-model.md` 12-4 / 12-6 / 12-9 / 3-5 | **反映なし**(★2・3-5 の述語は変えない) | — |

## 4. 実装方針

詳細設計は [design.md](./design.md)。

**重さ分類 = コア領域**。根拠: **テナント分離**(設計書 6.3 の境界定義)の中核である。RLS・ロール・ACL を製品に初めて置き、
`contracts/authz/*`・`backend/src/pitchlog/authz/*`・`backend/tests/db/*`・`contracts/tenant_boundary/*` に触れる。
どれも `tenant-isolation` の paths に含まれる(`.claude/core-areas.json:295`・`:306`・`:311`・`:352`)。
移行バッチ用ロールは**データ移行**の領域にもかかる。
→ 実装は ADR-001 の対応表どおりのモデル、敵対レビュー必須、**人間の逐行確認必須**(PR 作成者以外)。

**守る不変条件**(全ステップ共通):

- `contracts/authz/` 直下の probe 資産の差分 0 行(`oracle-seal.lock.json` の封印を動かさない)
- `backend/pyproject.toml` / `backend/uv.lock` / `backend/tests/conftest.py` の差分 0 行
- `backend/migrations/` に `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` / `GRANT` が 0 件(`D7`)
- **既存テストのファイルを変えずに green**(ステップ 1 の後方互換。変える場合は、そのステップの合格条件に理由とともに列挙する)
- 資産にパスワード・接続文字列を書かない(NFR-014)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **資産指定オブジェクト `AuthzAssetSpec` の導入**(`backend/src/pitchlog/authz/` に新設。生成器 `ddl.py`・適用器 `provisioning.py`・カタログ検査 `catalog.py`・body 検査器・静的検査 `check_authz_catalog.py` の scope 検査・DB fixture が spec を受け取る。既定は `PROBE_SPEC`)。製品 spec はまだ置かない | **既存テストのファイル差分 0 行**のまま `backend` と `harness` の pytest がすべて green。**spec の取り違えで red** になる負例(probe 以外の scope 値を probe spec で読むと拒否・操作種別の集合が spec ごとに閉じている)。`ddl.py` の AST 検査(`backend/tests/test_authz_ddl.py:181`)が green のまま。probe 資産の差分 0 行 |
| 2 | **表分類資産 `contracts/authz/product/table-classification.json`** と、その静的検査(design.md 1-4・1-5) | 45 表が 4 プロファイルへ**両方向 exact-set** で割り当て済み(未割り当て 0・重複 0・存在しない表 0。母集合は `Base.metadata` と manifest の両方から導き、両者の一致も検査)。負例 5 種で red: ① モデルを 1 つ足す ② `tenant_id` を持たない表に `tenant_owned` ③ `function_only` なのに `access_path.reason` が無い ④ 所有単位が閉じた列挙の外 ⑤ 既定プロファイルの暗黙適用 |
| 3 | **製品 authz DDL 資産**(`contracts/authz/product/ddl-elements.json`・`function-bodies/`・`manifest.json`)と **`PRODUCT_SPEC`**。ロール 4 種(design.md 2 節)・`public` の ACL・全 45 表の `ENABLE` + `FORCE`・`tenant_owned` 24 表と `self_tenant_row`・`global_read_only` のポリシー・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪。**述語は 1 要素から展開**し、展開結果を資産に固定する | `PRODUCT_SPEC` で生成器・body 検査器・静的検査が green。**表分類資産と DDL 資産の一致**(プロファイルごとのポリシー有無・ACL・コマンド・roles・`USING`・`WITH CHECK` の exact-set)を静的に検査。負例で red: ポリシーを 1 本消す / `WITH CHECK` を消す / `DELETE` を足す / `function_only` の表に ACL を足す / 述語の `::UUID` を `::BIGINT` に変える / 展開結果を手で書き換える(digest 不一致)。資産に `password` / 接続文字列が 0 件 |
| 4 | **製品の適用器と、使い捨てクラスタでの適用**(migration → 製品 DDL を 1 トランザクションで適用。fixture `provisioned_product_catalog` を新設)と**カタログ検査** | 使い捨てクラスタで `alembic upgrade head` → 製品適用 → **カタログが資産と exact-set**(全 45 表の `relrowsecurity` と `relforcerowsecurity`・`pg_policy`・表 / スキーマ / 関数の ACL・ロール属性)。**R-5 の失敗点**(ロール作成後・ポリシー作成後・ACL 正規化の途中)に故障を注入し、**カタログが適用前と一致**。provisioner が `product_table_owner` へ `SET` できない。**33 個のトリガ関数がすべて `SECURITY INVOKER`**(`SECURITY DEFINER` を 1 つ混ぜた migration の変異で red) |
| 5 | **実 DB 試験**(design.md 6 節の表を全行)。試験は表分類資産からパラメタ化して生成する | 全行が期待どおり: **最低要求 ①** — `tenant_owned` 24 表すべてで他テナントの行が 0 行 / `WITH CHECK` 違反が `42501` / 未束縛が 0 行 / 不正 UUID が `22P02` / `DELETE` が `42501` / `self_tenant_row` と `global_read_only` の読み書き / `function_only` 15 表の `SELECT` が **`42501`(0 行ではない)** / `PUBLIC` 剥奪後もトリガが発火 / FORCE(表所有者でも未束縛で 0 行)/ 危険終点の交差が空 / `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件。**変異で red**: 1 表のポリシーを外す・`FORCE` を外す・`WITH CHECK` を `true` にする・`function_only` の表に `SELECT` を与える |
| 6 | **probe ↔ 製品の写像資産 `contracts/authz/product/probe-product-map.json`** と、その検査(design.md 7 節) | `probe の全原子要素 = mapped ∪ explicit_non_mapping` と `製品の全原子要素 = mapped の像 ∪ product_only` が**両方向 exact-set**。理由コードは閉じた列挙で、種別ごとに使えるコードが固定されている(`deferred_to_owning_unit` には `owner_unit` が必須)。`read_control_resources` が `owner_unit: U-C2`、`app_role` の `DELETE` が `forbidden_by_canon`。負例で red: probe 要素の写像を 1 つ消す / 製品要素を 1 つ足して写像しない / 列挙外の理由コード / 許可していない 1 対多 |
| 7 | **移行バッチ用ロールのライフサイクル資産 `contracts/authz/product/migration-batch-lifecycle.json`** と、使い捨てクラスタでの試験(design.md 8 節) | 正本の 6 条件(`data-model.md:290-297`)を全部検査: 退役後にロールが無いか `NOBYPASSRLS` かつ `NOLOGIN`(**成功時と失敗時の両方**)/ `pitchlog_app` と関数所有ロールから到達しない / どのオブジェクトの所有者でもない / 表 ACL が `write_targets` と exact-set / `write_targets ⊇ 導出集合` で差分の各表に理由コード / **投入の途中で故障を注入しても、監査行「開始」「失敗」が残り、投入行が 0 件** / 定常の適用結果に `BYPASSRLS` を持つ `LOGIN` ロールが 0 件。負例で red: 退役を省く / `write_targets` に理由コードの無い表を足す / 監査を投入と同じトランザクションで書く |
| 8 | **capability の誤開放を防ぐ検査**(design.md 10 節)。capability の集合そのものは空のまま | `function_only` の表を対象にした capability を 1 つ足す変異で red。`direct` の表を対象にした capability は検査を通る(**試験の中だけで足し、製品のパッケージには収載しない**)。`backend/src/pitchlog/repositories/repository_contract.py:57-59` の 3 集合が空のまま |
| 9 | **ランタイム契約の切り替え**(design.md 9 節)。**TSK-431 のマージ後に着手する** | 製品資産の `runtime_contract` から `runtime_contract.py` を作り直し、`PROVISIONAL = False` / `SOURCE_ASSET` = 製品資産 / `SUPERSEDED_BY = None`。**暫定資産を削除**し、`backend/tests/test_authz_runtime_contract.py` の二状態検査が製品状態で green。**7.7 の記録**: 削除記録が追記のみで残り、TSK-431 が直した検査器(7D)が削除を検査して green。`FROZEN_BASELINE_ASSETS` などのソースに旧資産の値が残っていない。`PROTECTED_TABLES` が manifest の 45 表と exact-set。U-T1 のロール真正性検査(`backend/src/pitchlog/db/engine.py:159`)が製品の期待値で green |

**ステップの順序と並行性**:

- 1 → 2 → 3 → 4 → 5 は順に依存する。6 は 3 の後ならいつでもよい。7 は 4 の後。8 は 2 の後
- **9 だけが TSK-431 のマージを待つ**。TSK-431 とは、ステップ 1〜8 の間は衝突しない(TSK-431 が触るのは `scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*.json` で、本単位はステップ 9 まで触らない)
- **U-T1 の後続単位との衝突面**は `backend/tests/db/conftest.py`(再エクスポートを 1 行足すだけ)と `contracts/authz/product/`

**正本の追随**(3 節)は、ステップ 9 の後に /sync-docs で行う(Claude が書く。委任しない)。

## 5. DoD(受け入れ基準)

Notion カードの DoD を、★5〜★8 に合わせて書き換えたもの。**承認後に Notion を同期する**。

- [ ] **全 45 表に物理プロファイルが排他で割り当てられ、未割り当てが 0 件**(母集合は `Base.metadata` から導出。割り当ては明示メタデータ)。**プロファイルは 4 種で確定**し、カードが求めた「親表経由」「認証前グローバル可変」は `function_only` の到達経路の理由として記録した(★5)
- [ ] **全表が `ENABLE` + `FORCE ROW LEVEL SECURITY`**(正本 3-2 節の「全テーブルへ FORCE」を変えない)
- [ ] **全表で `{プロファイル, ACL, コマンド, roles, USING, WITH CHECK}` が exact-set**(静的検査とカタログ検査の両方)
- [ ] **使い捨てクラスタで、製品 migration と製品 authz DDL の適用、カタログ検査、実 DB 試験が green**。最低要求 ① を 24 表すべてで表明した。最低要求 ②③④ は対象が空であることを表明した
- [ ] **probe ↔ 製品の写像が両方向 exact-set**(非写像の理由コードと `owner_unit` が全件に付く)
- [ ] **移行バッチ用ロールのライフサイクル 6 条件が検査されている**(成功時と失敗時の両方で退役・監査が失敗時も残る)
- [ ] **ランタイム契約が製品資産に切り替わり、暫定資産が削除されている**。7.7 の削除記録が残っている(TSK-431 のマージ後)
- [ ] **capability は空のまま**で、`function_only` の表から capability を作ると red になる
- [ ] **12-8 節に残件・所有者(U-C1 / U-C2 / U-C3 / U-A2 / TSK-344)・発効条件を記録した**。3-2 節の引用を訂正した
- [ ] **`contracts/authz/` 直下の probe 資産の差分 0 行**(`oracle-seal.lock.json` の封印を動かさない)
- [ ] **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の差分 0 行**
- [ ] **PR に 12-4 の判定記録を残した**(「対象入口なし」)
- [ ] **TSK-349 を取り下げ、吸収した DoD と FR-038 へ移した DoD を Notion に記録した**(★1)
- [ ] **TSK-250 へ、写像資産の二重正本の解消(本資産が正)を申し送った**
- [ ] pytest / ruff / ty green(`backend` と `harness` の両方)
- [ ] **コア領域として敵対レビューと、人間の逐行確認(PR 作成者以外)を通した**

## 6. テスト計画

| NFR-019 の種別 | 足すもの | ステップ |
| --- | --- | --- |
| **単体** | 資産指定オブジェクト・spec の取り違え・表分類の静的検査・DDL 資産と表分類の一致・写像の両方向 exact-set・capability ガード | 1・2・3・6・8 |
| **越境**(NFR-019(b) の DB 層) | 最低要求 ① を 24 表すべて・`WITH CHECK`・未束縛・`function_only` の `42501`・危険終点・越境関数 0 件の表明(使い捨てクラスタ・`requires_db`) | 5 |
| **故障系** | R-5 の失敗点での原子性・不正 UUID の `22P02`・移行バッチの投入途中の故障と監査の残存・退役の失敗時 | 4・5・7 |
| **一致性** | 生成モジュール `runtime_contract.py` と製品資産の一致(二状態検査)・述語の展開結果と要素の digest | 3・9 |
| **E2E** | **対象外**(入口を開かない。HTTP の越境テストは入口を開く単位が同じ PR に含める — ADR-004 D-2) | — |

- **変異で red になることを、各ステップの合格条件に入れた**(改変前の green を assert してから変異させる)
- DB 試験は既存の `requires_db` マーカーに乗せる。収集 0 件でセッションを失敗にする既存の仕組み(`backend/tests/db/conftest.py:83-119`)に守られる
- CI では `backend` ジョブ(`.github/workflows/ci.yml:210-260`)が走る。使い捨てクラスタは既存の `disposable_postgres_cluster` と同じ `docker run` 方式で起動する
