---
feature: product-rls-boundary-tests
type: design
date: 2026-09-27
---

# 裁定シート: 最低要求 4 件の線引き(TSK-344 / 7 節 #3)

**敵対レビュー 2 周目 P0-2 が「未決のまま承認してはいけない」と判定した項目の裁定材料。**
**判断は人間が行う。** 本書は**実測した事実**と**選択肢**を並べるだけで、結論を書かない。

## 0. 本書は一度誤った — 初版の撤回

**初版(2026-09-27)は 2 つの事実を誤って書いた。3 周目の敵対レビューが両方を指摘し、原典で確認して撤回した。**
**初版に基づく裁定(同日)も保留へ戻した。**

| 初版の記述 | 誤りの内容 | 正しい事実 |
| --- | --- | --- |
| **製品の `SECURITY DEFINER` は 0 件** | **検索語が違っていた**(`grep "SECURITY DEFINER"` は 0 だが、**資産のキーは `security_mode: "definer"`**) | **1 件実在する** — `authz_private.tenant_has_effective_membership(uuid, boolean)` |
| **`route-registry.json` にシステム管理経路が 0 件だから U-A2 の代表を取れない** | **論法が誤り。** `route-registry.json` の射程は **「既に契約がある範囲(020〜032・041)」**(`../product-impl-unit-split/plan.md:519` ④)であり、**U-A2 の FR-035/037 が載っていないのは射程どおり**。**不在は非存在を意味しない** | **結論(U-A2 に probe 代表が無い)は別の資産で裏が取れた** — 下記 4 節 |

**教訓**: **否定形の主張(「0 件」)を、1 つの検索語の結果だけで書いた。**
**資産のスキーマを先に見ていれば防げた。**

## 1. 最低要求 4 件とは

| # | 要求 | 帰属(`../tenant-boundary-enforcement/design.md` 8-1 節) |
| --- | --- | --- |
| ① | アプリ用ロールが**関数を経由せず**他テナント行を読めない | **TSK-424** |
| ② | **`PUBLIC` が越境関数を実行できない** | **②③④ の共有分 = U-C1 / U-C3 / 管理分 = U-A2** |
| ③ | **`search_path` の乗っ取りが効かない** | 同上 |
| ④ | 対象側が非共有なら**要求元が付与していても返らない** | 同上 |
| — | **揃った 4 件の実スキーマ再実行** | **TSK-344**(本タスク) |

## 2. 実測 — ① は実在し、測れる

`contracts/authz/product/ddl-elements.staged.json`(**A1 で develop へ着地済み**):

- **RLS ポリシー 32 件**(すべて `permissive`)。例: `POLICY:team_records:tenant_owned` /
  `role_ids: ["pitchlog_app"]` / `using_predicate_id: PREDICATE:TENANT` / `using_column: tenant_id`
- ロール 4 件: `pitchlog_owner` / `pitchlog_app` / `pitchlog_shared_fn_owner` / `pitchlog_management_fn_owner`

## 3. 実測 — ②③ は**既に対象があり、TSK-442 が試験している**(初版の誤りの是正)

製品資産に **`security_mode: "definer"` の関数が 1 件**ある:

```
FUNCTION:authz_private:tenant_has_effective_membership(uuid, boolean)
  function_kind: rls_helper          owner_role_id: pitchlog_shared_fn_owner
  security_mode: definer             search_path: [pg_catalog, pg_temp]
  revoked_acl_expectations: PUBLIC の EXECUTE / pitchlog_app の EXECUTE
```

**TSK-442 のステップ 9 が、これを最低要求 ②③ の対象として既に試験している**(逐語):

> **最低要求 ②**(`PUBLIC` と、信頼しない `LOGIN` ロール〔`pitchlog_app` を含む〕が補助関数の実効の
> `EXECUTE` を持たない)/ **最低要求 ③**(`pitchlog_app` は一時表を作れない〔`42501`〕・
> `TEMPORARY` を持つ試験専用ロールの一時スキーマの乗っ取りが補助関数に効かない)/
> **`pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件**

**→ ②③ は「対象 0 件」ではない。** **補助関数 1 件に対しては既に対象も試験もある。**
**残るのは「越境関数に対する ②③」であり、そちらはまだ無い。**

## 4. 実測 — 越境関数は未着で、所有は**写像資産が正**(初版の根拠を差し替え)

**`contracts/authz/product/probe-product-map.json`**(TSK-442 ステップ 11 の成果物・**未マージ**)は
**probe と製品を両方向 exact-set で突き合わせる**資産である。**3 越境関数はすべて `explicit_non_mapping`**:

| probe 要素 | `reason` | **`owner_unit`** |
| --- | --- | --- |
| `function:authorized_shared_rows` | `deferred_to_owning_unit` | **U-C3** |
| `function:read_control_resources` | `deferred_to_owning_unit` | **U-C2** |
| `function:apply_representative_grant_change` | `deferred_to_owning_unit` | **U-C1** |
| `acl_privilege:ACL:authorized_shared_rows:app_role:EXECUTE` | 同上 | **U-C3** |
| `acl_privilege:ACL:read_control_resources:app_role:EXECUTE` | 同上 | **U-C2** |
| `acl_privilege:ACL:apply_representative_grant_change:management_caller:EXECUTE` | 同上 | **U-C1** |

**`deferred_to_owning_unit` は計 21 件で、内訳は U-C1: 8 / U-C2: 10 / U-C3: 3。**
**`owner_unit` に `U-A2` は 1 件も現れない。**

**→ U-A2 に probe 代表が無いという結論は正しいが、根拠は「route-registry に経路が無い」ではなく
「両方向 exact-set で検査される写像資産に U-A2 が 1 件も現れない」である。**

**ただしこれは「U-A2 の ②③④ が存在しない」ことを意味しない。**
**probe が FR-035/037 を模していないだけ**の可能性がある。**設計書 8-1 節は U-A2 へ明示的に割り当てている。**
**両者が食い違っているのか、射程が違うだけなのかは、本書では確定できていない。**

## 5. 実測 — 依存の循環は**正本に解がある**

3 周目 P0-1 は「TSK-344 は帯 3 のマージ路を開くが、帯 3(U-C1/C2/C3)は TSK-344 を待つ」閉路を指摘した。

**`../product-impl-unit-split/plan.md:431` の逐語**:

> **入口を開く PR だけがゲートの判定を受ける**(**着手はできる**)。…
> **入口を 1 つも開かない PR には空の要求として掛かる**

**→ U-C1/C2/C3 が「関数だけを作り、入口を 1 つも開かない PR」を先にマージすれば閉路にならない。**
**`U-T1` がまさにその形でマージ済みである。**
**デッドロックではなく、順序契約が計画書に書かれていないだけ。**

## 6. 実測 — 再利用できる上流テスト

| 関数 | 参照ファイル数 |
| --- | --- |
| `authorized_shared_rows` | **7**(`test_authz_runtime_positive.py` / `..._negative.py` / `test_authz_trust_boundary.py` / `test_authz_precondition_matrix.py` / `authz/mutation_execution.py` ほか) |
| `read_control_resources` | **2** |
| `apply_representative_grant_change` | **2**(`test_authz_management_probe.py` ほか) |

**いずれも probe に対する試験。製品側の同型試験は存在しない**(越境関数が未着のため)。

## 7. 決めていただきたいこと

### 7-1. ②③ の射程 — **補助関数分を本タスクが再実行するか**

**TSK-442 が使い捨てクラスタで既に試験している。** 本タスクは**実スキーマでの再実行**が仕事である。

| 案 | 内容 |
| --- | --- |
| **A** | **補助関数分の ②③ を本タスクで実スキーマ再実行する**(越境関数を待たずに**今の資産だけで ①②③ が動く**) |
| **B** | **越境関数が揃うまで ②③ に手を付けない**(8-1 節の「揃った 4 件」を字義どおり取る) |

### 7-2. 越境関数分の代表の取り方

| 案 | 内容 |
| --- | --- |
| **A** | **クラスごとに代表 1 件**(写像資産の 3 件 = U-C3 / U-C2 / U-C1) |
| **B** | **`deferred_to_owning_unit` 21 件すべて** |

### 7-3. U-A2 の扱い — **本書では確定できなかった**

**設計書 8-1 節は U-A2 へ ②③④ の管理関数分を割り当てている**が、
**写像資産の `owner_unit` に U-A2 は 1 件も無い。**

| 案 | 内容 |
| --- | --- |
| **A** | **8-1 節が正** — U-A2 を依存に入れ、**probe に無い分は U-A2 自身が代表を定義する**ことを発効条件にする |
| **B** | **写像資産が正** — U-A2 は ②③④ を持たない。**8-1 節を確定ゲートで改訂する** |
| **C** | **食い違いの解明を別タスクへ送る** — 本タスクは U-C1/C2/C3 だけで閉じ、U-A2 は申し送る |

### 7-4. 順序契約(5 節の循環)

| 案 | 内容 |
| --- | --- |
| **A** | **計画書へ順序契約を明記する** — 「U-C1/C2/C3 は**入口非開放の関数のみ PR** を先にマージし、TSK-344 の後に入口を開く」 |
| **B** | **未マージ候補を検証対象にする**(3 周目 P0-1 が挙げたもう 1 つの案) |

## 8. 本書が答えていないこと

- **8-1 節と写像資産の食い違い**(7-3)— 原典 2 つが違うことを言っているのか、射程が違うだけなのか
- **`function_class` というキーは製品資産に存在しない**(実キーは `function_kind`)。
  **3 周目 P0-3 の指摘どおりで、対応づけの規則は未定義**
- **製品側の越境関数がいつ生まれるか** — U-C1 / U-C2 / U-C3 は**すべて未着手**
