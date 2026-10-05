---
date: 2026-10-04
feature: minimum-requirement-4-note
task: TSK-474
branch: feature/minimum-requirement-4-note
base: origin/develop = d6f5f3c9
---

# 調査メモ: 12-4 の最低要求 ④ の「現時点での満たし方」

調査サブエージェント 3 本(spec-checker / decision-tracer / Explore)を並列で実行し、
報告の食い違いは原典で裁定した。**すべての事実に典拠(ファイル:行)を付ける。**

## 結論 — カードが推す案は、そのままでは採れない

Notion カード TSK-474 が推している案:

> **越境関数が 0 件の間は、0 件であることの表明をもって ④ を満たしたと記録する**

**3 つの独立した理由で成立しない。**

| # | 理由 | 典拠 |
| --- | --- | --- |
| **1** | **根拠にしている「番人」が、主張どおりには働かない** | 下記 §2 |
| **2** | **「0 件」の事実認定が不正確**(集合が違う・probe 側には 1 件ある) | 下記 §3 |
| **3** | **「満たした」と書く形が、プロジェクト自身の先例と逆** | 下記 §4 |

---

## 1. 条文の現況(spec-checker)

**最低要求 4 件**(`docs/design/data-model.md:2596`・12-4 節「越境テスト再実行ゲート」):

> ① アプリ用ロールが関数を経由せず他テナント行を読めないこと
> ② `PUBLIC` が**越境**関数を実行できないこと
> ③ `search_path` の乗っ取りが効かないこと
> ④ **対象側が非共有なら要求元が付与していても返らないこと**(3-2 節・3-6 節の契約に対応)

**「4 件の文言は変えない」は実在する**(`:2597`)。**ただしカードの行番号 `:2533` は誤り。**

> 4 件の文言は変えない — 12-7 (1) が実機確定タスクへの要求として同じ 4 件を列挙しているため、
> 本節だけで書き換えると両者が食い違う

**★ その理由が既に部分的に破れている。** 12-7 (1)(`:2829`)の ② は
「`PUBLIC` が**関数**を実行できないこと」で、**「越境」の 2 文字が無い**。
末尾の括弧書きも違う(12-4 =「3-2 節・3-6 節の契約に対応」/ 12-7 (1) =「NFR-019(b) の越境テスト」)。
**意図か書き漏れかの記録は無い(不明)。**

**④ の要件上の根拠**:
- **FR-034 の認可行列**(`requirements-pitchlog-2026-07-22.md:634`)— 「相手が付与 ∧ 要求元も付与」、満たさなければ「除外(結果に現れない)」
- **NFR-010**(`:848`)・**NFR-019(b)**(`:933`)
- **②③ は要件書に典拠が無い**(`search_path` / `PUBLIC` / `SECURITY DEFINER` は要件書に 0 件)。**設計書だけの要求**

**★ ④ の所有者は既に条文にある。** `data-model.md:2911`(12-8 の表):

> 越境関数と最低要求 ②③④ の残り = **U-C1・U-C3・U-A2**
> TSK-442 で確認したのは ②③ まで。**未発効**
> 解消済みにはしない — 製品の資産はまだ実スキーマへ適用されていない(適用は TSK-344)

**カードの「いつ・誰が満たすかの記述が無い」は誤り。** 所有者も未発効も既に書かれている。

**3-6 節の要求**(`:568`・カードの `:555` は誤り):

> **とくに「対象側は非共有・要求元だけ付与」の組み合わせ — P0-2 で落としていた経路**

---

## 2. ★ 「番人」は主張どおりには働かない(Explore — 反証が出た)

カードの根拠(`docs/features/product-authz-surface/design.md:482`):

> `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件であることを表明する。
> **各単位が関数を足すと red になり、④ の試験を足すよう促す**

**検査は実在する**(`backend/tests/db/test_product_authz_cross_cutting.py:543-569`)。
母集団は `prosecdef` **かつ `has_function_privilege(pitchlog_app, …, 'EXECUTE')` が真**。

### 裏が取れたこと

- **skip 経路は無い。** `requires_db` に skip 実装は 1 件も無く、DSN 欠落は `pytest.fail`
  (`backend/tests/db_fixtures.py:184-185`)、Docker 欠落は error。さらに
  **「DB テストが 0 件なら session ごと赤」**の二重ガードがある(`backend/tests/db/conftest.py:98-128`)
- **別ロール経由・PUBLIC 既定・後からの付与**はいずれも捕まる

### ★ 反証(通り抜けが 2 つ。うち 1 つは現行資産そのもの)

**(A) `SECURITY DEFINER` のトリガ関数は EXECUTE 無しで発火する。**
**このリポジトリ自身が試験で確定させている** —
`test_all_trigger_functions_fire_without_app_execute_privilege`
(`backend/tests/db/test_product_authz_cross_cutting.py:278-332`)が
「`pitchlog_app` の `has_function_privilege` が **37 件すべて false**」のまま発火することを示す。

**(B) RLS ポリシー式からだけ呼ぶ形も EXECUTE 不要。**
**現行の唯一の `SECURITY DEFINER` 関数がまさにこの形** —
`authz_private.tenant_has_effective_membership` は
`REVOKE ALL … FROM PUBLIC, pitchlog_app`(`backend/src/pitchlog/authz/product_control_access.py:168-170`)
されているのに、`POLICY:sharing_grants:effective_group_control.sql` から呼ばれて SELECT を通す。

→ **検査が「0 件」を返しているのは「関数が 0 件だから」ではなく
「`pitchlog_app` に直接 `EXECUTE` が無いから」。**
**将来の越境関数も、同じ設計(ポリシー経由 / トリガ経由)で足せば同じく見えない。**

補強検査も届かない。`PRODUCT-CATALOG:FUNCTIONS` の観測クエリは
`AND routine.proname = ANY(%s)`(`backend/src/pitchlog/authz/product_catalog.py:211`)で
**資産に載っている名前だけに母集団を絞る**ため、新しい名前の関数は観測されない。
**網羅的な棚卸しは probe 側にしか無い**(`backend/src/pitchlog/authz/catalog.py:1382-1393`)。

### もう 1 つ — この PR では番人が走らない

`backend` ジョブには **path filter** が付いている(`.github/workflows/ci.yml:286-301`。
`backend/**` / `contracts/**` / `.github/workflows/ci.yml`)。
**本タスクは `docs/` だけの改訂なので、この PR の CI でこの番人は 1 度も走らない。**

対照的に `nfr021-append-only` と `tenant-boundary-bypass` は
**「paths filter は付けない: フィルタ自体が誤ると検査が黙って通り fail-closed に反するため」**
と明記して常時実行にしている(`ci.yml:179-181` `:196-198`)。**④ の番人はその方針の外側にいる。**

**正確な射程**: 「どの単位が関数を足しても red」ではなく
**「どの単位が `pitchlog_app` へ直接 `EXECUTE` を与える関数を足せば red」**。

---

## 3. 「0 件」の事実認定(Explore)

| | 実測 |
| --- | --- |
| 製品資産 `contracts/authz/product/ddl-elements.staged.json` | 関数 **38 件**。うち `security_mode = "definer"` は **1 件**(`tenant_has_effective_membership`・`rls_helper`)。残り 37 件は `migration_trigger` |
| **共有集計・越境の関数** | **製品側は 0 件**(カードの主張どおり) |
| **probe 資産** `contracts/authz/ddl-elements.json` | **`authorized_shared_rows`(`shared_read`・definer)が 1 件ある** |

→ **「越境関数 0 件」は製品 DDL 資産に限った言明。** 文書化の際に**「製品側」と明記しないと
12-7 (1) の probe 記述と食い違う。**

**相互性を表す述語はどこにも無い**(裏が取れた):
- `POLICY:sharing_grants:effective_group_control.sql` は `FOR SELECT` のみ・`WITH CHECK` 無し。
  ヘルパの 4 条件は status / enabled / `tenant_id` の一致だけで、**`grant_flags` を参照しない**
- seed の `grant_flags` は **6 ケース全件 `{}`**(`backend/tests/product_authz_other_profiles_cases.py:244-249`)。
  **非空を投入する試験は 1 件も無い**

→ **④ を試す素材が現時点で存在しない**ことは事実。

---

## 4. ★ 「満たした」と書く形は、プロジェクト自身の先例と逆(decision-tracer)

**同じ 12-4 節の中に、同じ状況の先例がある。そこでは「満たした」と書いていない。**

| 典拠 | 逐語 |
| --- | --- |
| **`data-model.md:2598`** | **「空であることは要求の免除ではなく、要求を当てる対象が無いことである」** |
| `:2600` | 入口を 1 つも開かない PR は**「対象入口なし」と書く** — 項目を省かない |
| ADR-004 D-2(`:80`) | 同型 |

**否定側の先例**:

| 典拠 | 逐語 |
| --- | --- |
| **要件書 `:933`**(NFR-019(b)) | **「実体が無いものについて判定を下さない」** |
| ADR-003 `:316` | **「これをもって (b)② を満たしたとはしない」** |
| ADR-003 `:147` `:433` | 「D-5 をもって ② を満たしたと宣言することはできない」(対象範囲の縮小の禁止) |
| 要件書 `:918` BOOT-NO-CLAIM | **「CI の緑は充足を意味しない」** |
| ADR-003 `:381-387` | **「対象が存在しない」という言い方を禁じ、「新規に加わる対象が 1 件も無い」を使う** |
| ADR-004 `:124` | 「最低要求 4 件を満たすことは下限の充足にすぎず」 |

**「0 件の表明をもって満たしたと記録する」と同じ形の先例は 1 件も見つからなかった。**

---

## 5. ④ の由来と TSK-382 との境界(decision-tracer)

**4 件は 2026-08-22 の同じ裁定で入った**(TSK-248 候補案の打ち切り)。
**④ だけ由来が違う** — 1 周目の P0「共有関数の認可条件から対象テナント側の付与が抜けていた」
(`docs/features/product-data-model-design/design.md:308-314`)。
①②③ は 3・4 周目の DB 機構の誤り(`SECURITY DEFINER` と RLS の混同・関数 ACL)から。

TSK-378 の分類(`docs/features/merge-gate-api-cycle/design.md:182-187`):
① = DB ロール / ② = 関数 ACL / ③ = セッション設定 / **④ = 関数の返却契約**。

**ADR-004 `:122` は 4 件を「DB ロール・関数 ACL・`search_path`・関数の返却契約」と書くが、
`data-model.md:2597` は「DB ロール・関数 ACL・`search_path`」だけで返却契約が抜けている**
(文言のずれ)。

### TSK-382 との境界 — 字面では射程外。ただし接点が 3 つ

受領範囲の逐語(`docs/worklog/2026-09-13-merge-gate-clause.md:201`):
**「この 3 者の衝突だけ」**(SP-06 `:2764` / 射程外宣言 `:2571` / non-serving `:2574`)。

**接点**:
1. **12-6 受け取り先表**(`:2791`)が「要求するテスト 4 件は 12-7 節 (1)」と参照しており、
   TSK-424 はこの表を「TSK-382 が扱う 3 箇所の 1 つ」と書いている
   (`docs/features/product-authz-surface/design.md:644`)。**この表に手を入れると衝突する**
2. **TSK-382 は 12-7 節の矛盾も受け取っている**。**注記を 12-7 (1) にも置くと、
   TSK-382 が未処理の節に入る**
3. 下流のタスクが TSK-382 の射程を広く読んでいる

---

## 6. 整合の判定

**一致するもの**: 2026-10-03 の人間の裁定 A の文言そのもの / TSK-424 の設計意図 /
U-T1 8-1 の所有割り当て / `data-model.md:2911` の残件記録。

**矛盾し得るもの**:

1. **要件書 `:933` の「実体が無いものについて判定を下さない」** — 「満たしたと記録」は
   実体の無い対象に合格を下す形。**同じ 12-4 が同じ状況を「対象が無い」と書いている**(`:2598`)
2. **ADR-003 D-4 / BOOT-NO-CLAIM の型** — 代わりの検査で充足を宣言しない
3. **`data-model.md:2597`** — 注記が「書き換え」に当たるかは条文から決まらない(**PO の判断事項**)。
   12-4 だけに置くと 12-7 (1) との非対称が生まれ、12-7 (1) にも置くと TSK-382 の節に入る
4. **前提の言い方** — 「越境関数 0 件」と、試験が見ている
   「`pitchlog_app` が EXECUTE できる SECURITY DEFINER 0 件」は**同じ集合ではない**

---

## 7. 人間の裁定が要る論点

**A. ④ をどう書くか**(本タスクの核心)

| 案 | 形 | 先例との整合 |
| --- | --- | --- |
| **案 1**(カード) | 0 件の表明をもって**満たしたと記録する** | **先例と逆**(`:2598` `:933` ほか) |
| **案 2** | **「対象なし」と書き、満たしたとはしない**。所有者(U-C1/U-C3/U-A2)と未発効を名指す | **12-4 自身の先例(`:2598`)と揃う** |

**B. 番人の射程をどう書くか** — 「0 件」と書くなら
**「`pitchlog_app` が直接 `EXECUTE` できる」「製品側の」**の 2 つの限定が要る。
**トリガ経由・ポリシー経由は番人の外側**であり、**現行資産が既にその形**。

**C. 置き場所** — 12-4 だけか、12-7 (1) にも置くか(**後者は TSK-382 の節に入る**)。

**D. 番人を常時実行にするか** — `backend` ジョブの path filter は、
`nfr021-append-only` / `tenant-boundary-bypass` が明示的に拒んだ設計と逆。**本タスクの射程外だが申し送り候補**。
