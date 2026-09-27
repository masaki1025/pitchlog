---
feature: product-rls-boundary-tests
type: design
date: 2026-09-27
---

# 裁定シート: 最低要求 4 件の線引き(TSK-344 / 7 節 #3)

**敵対レビュー 2 周目 P0-2 が「未決のまま承認してはいけない」と判定した項目の裁定материал。**
**判断は人間が行う。** 本書は**実測した事実**と**選択肢**を並べるだけで、結論を書かない。

**すべての事実は 2026-09-27 に `origin/develop` 上で実測した。**

## 0. 一行でいうと

**① は実在する。②③④ の対象となる製品の越境関数は 1 つも存在しない。**
**したがって「全件」は現時点で定義できない。** 決めるのは**代表の取り方**と**依存の exact-set**である。

## 1. 最低要求 4 件とは(計画書 4 節ステップ 3 の逐語)

| # | 要求 |
| --- | --- |
| ① | アプリ用ロールが**関数を経由せず**他テナント行を読めない |
| ② | **`PUBLIC` が越境関数を実行できない** |
| ③ | **`search_path` の乗っ取りが効かない** |
| ④ | 対象側が非共有なら**要求元が付与していても返らない** |

**帰属**(`../tenant-boundary-enforcement/design.md` 8-1 節):

| 主体 | 持つもの |
| --- | --- |
| **TSK-424** | ロール / RLS / 許可プロファイル / **最低要求 ①** |
| **U-C1 / U-C3** | **共有・グループ経路**の越境関数 / **②③④ のうち共有関数に係る分** |
| **U-A2** | **システム管理経路**の管理関数 / **②③④ のうち管理関数に係る分** |
| **TSK-344**(本タスク) | **揃った 4 件の実スキーマ再実行** |

## 2. 実測 — ① は実在する

`contracts/authz/product/ddl-elements.staged.json`(**A1 で develop へ着地済み**):

- **RLS ポリシー 32 件**(すべて `permissive`)
- 例: `POLICY:team_records:tenant_owned` / `profile: tenant_owned` / `command: ALL` /
  `role_ids: ["pitchlog_app"]` / `using_predicate_id: PREDICATE:TENANT` / `using_column: tenant_id`
- ロール 4 件: `pitchlog_owner` / `pitchlog_app` / **`pitchlog_shared_fn_owner`** / **`pitchlog_management_fn_owner`**

**→ ① は「`pitchlog_app` が RLS を越えて他テナント行を読めない」として、実スキーマで直ちに測れる。**

## 3. 実測 — ②③④ の対象関数は 0 件

製品資産の `functions` は **38 件**あるが、**越境関数は 1 件も無い**:

| 種別 | 件数 | 例 |
| --- | --- | --- |
| `prevent_*`(不変条件トリガ) | 36 | `prevent_players_identity_update()` |
| その他のトリガ | 1 | `protect_recording_generations_updates()` |
| 内部ヘルパ | 1 | `authz_private.tenant_has_effective_membership(uuid, boolean)` |
| **越境関数(`SECURITY DEFINER`)** | **0** | — |

**`SECURITY DEFINER` の出現は 0 件**(製品資産の全文走査)。

**所有ロールだけ先に存在する** — `pitchlog_shared_fn_owner` / `pitchlog_management_fn_owner` は
ロール定義にあるが、**それが所有する関数がまだ無い**。

## 4. 実測 — probe 側に 3 件あり、これが形の雛形になる

`contracts/authz/ddl-elements.json`(probe):

| 関数 | `function_class` | `public_execute` | `search_path` | `execute_role_ids` | 所有ロール | 対応する製品側の所有 |
| --- | --- | --- | --- | --- | --- | --- |
| **`authorized_shared_rows`** | `shared_read` | **`false`** | `pg_catalog, authz_private, pg_temp` | `app_role` | `shared_fn_owner` | **U-C1 / U-C3** |
| **`read_control_resources`** | `control_read` | **`false`** | 同上 | `app_role` | `shared_fn_owner` | **U-C2** |
| **`apply_representative_grant_change`** | `representative_management_operation` | **`false`** | `pg_catalog, management_private, pg_temp` | `management_caller` | `management_fn_owner` | **U-A2** |

**②③ はこの 2 フィールドがそのまま合格条件になる** — `public_execute: false` が ②、
`search_path` の固定が ③。**④ は `authorized_shared_rows` の `dependency_table_ids`**
(`probe_business_rows` / `probe_groups` / `probe_memberships` / `probe_grants`)が示す
**共有判定の意味論**に対応する。

## 5. 実測 — 再利用できる上流テスト

| 関数 | 参照ファイル数 | 主なもの |
| --- | --- | --- |
| `authorized_shared_rows` | **7** | `backend/tests/db/test_authz_runtime_positive.py` / `test_authz_runtime_negative.py` / `test_authz_trust_boundary.py` / `test_authz_precondition_matrix.py` / `backend/tests/db/authz/mutation_execution.py` |
| `read_control_resources` | **2** | `test_authz_runtime_negative.py` ほか |
| `apply_representative_grant_change` | **2** | `backend/tests/db/test_authz_management_probe.py` ほか |

**いずれも probe に対する試験である。** **製品側の同型試験は存在しない**(製品関数が無いため)。

## 6. 決めていただきたい 6 項目と選択肢

### 6-1. 代表 1 件なのか、該当関数の全件なのか

| 案 | 内容 | 帰結 |
| --- | --- | --- |
| **A** | **クラスごとに代表 1 件**(`shared_read` / `control_read` / `representative_management_operation` の 3 クラス) | probe の構造と 1 対 1。**依存は U-C1 または U-C3・U-C2・U-A2 の 3 本**。**今すぐ書ける** |
| **B** | **該当関数の全件** | **現時点で定義できない**(関数 0 件)。U 系が実装してから数が決まるため、**計画に書けるのは「全件」という語だけ**になり、**2 周目 P0-2 が問題にした「判定不能」が残る** |
| **C** | **① のみを本タスクの射程とし、②③④ は U 系の各タスクが自分で実スキーマ再実行する** | **本タスクの射程が 1/4 になる**。8-1 節の帰属(「揃った 4 件の実スキーマ再実行 = TSK-344」)と**食い違う**ので、**8-1 の改訂が要る** |

### 6-2. `U-A1` を依存の exact-set に入れるか

**8-1 節の帰属表に U-A1 は無い。** 一方、計画書 7 節 #3 は
`product-authz-surface@58d48b7:design.md:640-643` を引いて
「**認証とレート制限の関数 = U-A1**」を挙げている。

| 案 | 内容 |
| --- | --- |
| **A** | **入れない** — ②③④ は**越境関数**の話であり、認証・レート制限の到達経路は別問題。8-1 の帰属表に従う |
| **B** | **入れる** — `tenant_credentials` / `rate_limit_counters` は `function_only` 分類で、**関数を経由しないと到達できない**。その関数も「関数経由の到達」という点で ① の裏返しにあたる |

### 6-3. 残る 4 項目(2 周目 P0-2 の要求)

**6-1 で A を採れば、残りは機械的に決まる。**

| # | 項目 | A を採った場合 |
| --- | --- | --- |
| 1 | 表・関数名・シグネチャ | **製品関数が生まれるまで確定しない**。**probe の 3 件を「形の契約」として固定**し、製品側は `function_class` で対応づける |
| 3 | 所有タスクと必須マージ条件 | **U-C1 または U-C3**(shared_read)/ **U-C2**(control_read)/ **U-A2**(management)。**各タスクの PR が develop へマージ済みであること** |
| 4 | 再利用する上流テスト | 5 節の表。**probe 試験を製品側へ写す形**になる |
| 5 | 正例・拒否例 | **②**: `PUBLIC` で `EXECUTE` → 拒否(`42501`)/ `app_role` で `EXECUTE` → 通る。**③**: `search_path` を差し替えて呼ぶ → 効かない。**④**: 非共有の対象に対し要求元が付与 → **0 行** |

## 7. 本書が答えていないこと

- **U-C1 と U-C3 のどちらが `shared_read` を持つか** — `product-impl-unit-split` を読んでいない。
  **6-1 で A を採る場合、ここも決める必要がある**
- **製品側の越境関数がいつ生まれるか** — U-C1 / U-C2 / U-C3 / U-A2 は**すべて未着手**
- **6-1 で C を採る場合の 8-1 節の改訂案** — 本書の射程外
