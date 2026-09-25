---
feature: product-rls-boundary-tests
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d593b75e687811f8ad5f5da4a8af046
branch: feature/product-rls-boundary-tests
created: 2026-09-24
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 製品テーブルの RLS 適用と越境テスト(TSK-344)

<!-- 本文は /plan で起草する。以下は /task-start が Notion カードと申し送りから転記した着手時点の与件 -->

## 1. 背景・目的

- Notion タスク: [TSK-344 越境テスト再実行ゲートの実行 — 実スキーマ適用後の再実行](https://app.notion.com/p/3d593b75e687811f8ad5f5da4a8af046)(優先度 **高**)
- 前タスク: TSK-342(データモデル設計の正本化)。**裁定 `A-2`(2026-09-08・山田正輝)= 「定義は TSK-342・実行は本タスク」**
- **計画段階の調査**: [research.md](research.md)(調査サブエージェント 3 本 + 当方の原典実測)。**本書が事実を述べるときは正本を直接引く**
- 正本: `docs/design/data-model.md` **12-4 節**(ゲートの定義・non-serving 宣言・マージ停止条件)/ **12-8 節**(射程宣言)/ 3-2・3-6・8-2-B 節

### ⚠ 射程の訂正(調査 — [research.md](research.md) 1・2 節)

**着手時に本節へ書いた「実体 = RLS を製品テーブル 20 数枚へ展開する + 製品テーブルの越境テストを新規に書く」は誤りだった。**
既決は次のとおりで、**作成と初回実行は本タスクの射程ではない**。

| 範囲 | 受け取り先 | 典拠 |
| --- | --- | --- |
| RLS ポリシー・ロールの DDL の実機確定**と越境テストの作成・実行** | **TSK-317** →(5・6 周目の裁定で)**TSK-424** | `../../design/data-model.md:2845` / `../tenant-boundary-enforcement/design.md:335` |
| 越境テスト再実行ゲートの**実行**(**実スキーマに対する再実行**) | **TSK-344** | 同 `:2846` |

[`../tenant-boundary-enforcement/design.md`](../tenant-boundary-enforcement/design.md)`:341-345` の逐語:

> **「再実行」である以上、作成と初回実行はこちら側にある** … → **本単位: 使い捨てクラスタで作成・実行 / TSK-344: 実スキーマで再実行。** 矛盾しない。

TSK-424 の計画書も「やらないこと」に「**実スキーマへの適用と、越境テストの再実行** → TSK-344」と書いている。

**→ 本タスクの実体 = 「TSK-424 が作った資産と試験を、実スキーマに対して適用・再実行し、12-4 の判定を記録する」。**

**あわせて適用経路も訂正する**(同 `design.md:327-333`):

> ## 4. 適用経路 — migration ではない
> 裁定 `A-2` により alembic migration は `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` を **0 件**に保つ…
> → 製品の RLS・ロール DDL は migration の外で適用する。適用器は既存の `apply_authz_ddl` を…使う。

**→ 本タスクは `backend/migrations/` の差分 0 行を不変条件に置く。**足すと TSK-343 の `D7` と U-T1 の設計判断の双方に逆行する。
したがって**重さ分類の根拠も「migration = 5 領域すべてのコア paths」ではない** — `contracts/authz/*`(`tenant-isolation` のコア)に触れることが根拠になる。

**着手時に「条文に矛盾が埋まっている」と書いたのは誤りだった**(**1 周目 P0-2・P0-6 の是正**):
`../../design/data-model.md:2845-2846` は**作成・初回実行と再実行を分けており**、
その後の決定が `../tenant-boundary-enforcement/design.md:341-345` で
**作成・初回実行 = TSK-424 / 再実行 = TSK-344** へ移管している。**分担は確定済み**で、裁定は要らない(7 節 #1)。

### 引き継ぐ PO 裁定 2 件(TSK-381 は取り下げ済み・2026-09-13)

- **射程 = DoD 全体の見直し**(カードが書いている「4 と 6」に限定しない)
- **DoD 6 は「条文への写像」に留める** — `non-serving` の字面衝突は **TSK-382 の所有**なので踏まない

TSK-381 の調査成果は [research-dod-revision.md](research-dod-revision.md)(274 行・全事実に典拠つき)として本ブランチへ持ち込み済み
(出所: ブランチ `feature/tsk344-dod-revision` のコミット `cb889a8`。同ブランチは 2026-09-24 に origin へ push 済み)。

## 2. スコープ

**本タスクの実体**(1 節の訂正 + **1 周目の敵対レビュー P0-1 の是正**より):
**実環境の運用契約を決め、TSK-424 が作った製品 authz 資産と試験を実スキーマへ適用・再実行し、12-4 の判定を記録する。**

> **【1 周目 P0-1 の是正】** 着手時のステップ 1・2 は `disposable_postgres_cluster` 上の
> migration と製品 DDL 適用だけで、**それは TSK-424 PR A2(TSK-442)が作る `provisioned_product_catalog` と
> 同じ初回試験**だった(`product-authz-surface@58d48b7:plan.md:149-157`)。
> **使い捨てクラスタの green を実スキーマの証跡として誤認する**形になっていた。
> TSK-424 が本タスクへ申し送ったのは**実環境の運用契約**であり、下の 1〜3 がそれである。

### やること

1. **実環境の適用主体を決める** — 製品 DDL は **superuser 相当の外部主体が 1 トランザクションで適用する**ことまでが
   TSK-424 の契約で、**実環境で誰が適用主体になるかは本タスクの射程**と明記されている
   (`product-authz-surface@58d48b7:design.md:280`)
2. **non-serving 区間の実環境手順を定める** — 区間は
   **取り外しを始める前に、新しい接続を止め、既存のアプリの接続が 0 件であることを確かめた時点**から、
   **再適用の commit の後に、カタログ検査と越境の試験が green になった時点**まで。
   **途中で失敗したら serving に戻さない**(downgrade / upgrade / 再適用のどれでも)。
   **実環境の手順は TSK-344 が持つ**(同 `:396`)
3. **実スキーマへ製品 authz DDL を適用する** — 12-4 通過条件①(`../../design/data-model.md:2529`)
4. **最低要求 4 件を実スキーマに対して再実行する**(同 `:2530`)。あわせて
   **8-3 の「定常の不変条件」(移行を行っていない定常状態の条件)が実スキーマの再実行でも走る**
   (`product-authz-surface@58d48b7:design.md:517`・`:638`)
5. **12-4 の判定を PR へ記録する**(`../../design/data-model.md:2534` の 4 項目。**入口を開かないので「対象入口なし」と書く**)
6. **DoD を現行化する** — TSK-381 の成果([research-dod-revision.md](research-dod-revision.md))を反映。
   **DoD 1 と 3 が不変、2・4・5・6 が変わる**([research-dod-revision.md](research-dod-revision.md)`:50`)。
   PO 裁定により**本タスクの PR の中で行う**

### やらないこと

| 項目 | 行き先 | 典拠 |
| --- | --- | --- |
| **製品 authz DDL 資産の作成**(`contracts/authz/product/*`)・**表分類**・**capability カタログ** | **TSK-424 PR A1** | `../tenant-boundary-enforcement/design.md:315-322`(**1 周目 P0-6 の是正** — 旧引用 `:253-258` はファイル配置しか定めていない) |
| **適用器の一般化・probe↔製品写像・使い捨てクラスタでの初回試験**(= 越境テストの**作成と初回実行**) | **TSK-424 PR A2 = TSK-442** | 同 `:335-345` / `product-authz-surface@58d48b7:plan.md:149-157` |
| **使い捨てクラスタ上の fixture の新設**(`provisioned_product_catalog`)と**その上での初回実行** | **TSK-442**(**1 周目 P0-1 の是正** — 本タスクが重複して持っていた) | `product-authz-surface@58d48b7:design.md:409-423` |
| **認証・レート制限テーブルの RLS と表分類** | **TSK-424**(`tenant_credentials` / `rate_limit_counters` を **`function_only`** と分類済み。関数側は **U-A1**) | `product-authz-surface@58d48b7:design.md:35-45`・`:640-643`(**1 周目 P0-3 の是正** — 着手時の前提 B は撤回) |
| **`backend/migrations/` への RLS / ロール DDL の追加** | **しない**(差分 0 行) | 同 `:327-333` / `../orm-schema-migration/plan.md:848` の `D7` |
| **越境関数の本体・ACL・`search_path`**(最低要求 ②③④ の関数側) | **U-C1 / U-C3 / U-A2** | 同 `design.md:575-581` |
| **`SP-06` と 12-4 の字面衝突の解消**・**non-serving 第 1 項に終期を与える作業** | **TSK-382** | `../../adr/ADR-004-merge-gate-scope.md:44` |
| **`data-model.md` 12-8 節の実装追随** | **TSK-424** | `../tenant-boundary-enforcement/plan.md:79`・`:125` |
| **HTTP の入口を開くこと** | **開かない**(判定記録は「対象入口なし」) | `../../design/data-model.md:2534` |

### 本書が依る既決(**1 周目の敵対レビューで前提 A・B を撤回した**)

- **既決 1**(旧・前提 A): 製品テーブル向けの越境テストは **TSK-424 PR A2 = TSK-442 が作り、使い捨てクラスタで初回実行する**。
  本タスクはそれを**実スキーマで再実行する**(`../tenant-boundary-enforcement/design.md:341-345`)。
  **ただし TSK-424 は A1・A2・B・C のすべてがマージされるまで完了にしない**
  (`product-authz-surface@58d48b7:plan.md:43`)。**A1 + A2 だけでは着手できない** — PR A1・A2 の DDL は
  `ddl-elements.staged.json` のままで、最終パスへの切替は **PR B** である(同 `design.md:305-322`・`:586-599`)
- **既決 2**(旧・前提 B の撤回): **認証テーブルの RLS と表分類は TSK-424 が持つ**。
  `tenant_credentials` と `rate_limit_counters` は **`function_only`** として既に分類済みで、
  到達経路の関数は **U-A1** が所有する(`product-authz-surface@58d48b7:design.md:35-45`)。
  **本タスクは `contracts/authz/product/*` を変更しない**ので、前提 B のままでは実装できないか、
  実装すれば TSK-424 の射程を重複する
- **既決 3**(旧・前提 C): 最低要求 4 件のうち **本タスクが持つのは「実スキーマでの再実行と判定」**であり、
  **関数側の実装は持たない**。**最低要求 ④ は TSK-424 A2 の時点では対象関数が無く、
  各単位が関数を足した時点で試験を足す**設計である(同 `design.md:480`)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` | **反映なし**。12-4 の定義は変えない(**4 件の文言は変えない** — `:2531`)。**12-8 節の実装追随は TSK-424 の射程** | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/adr/` | **新設なし**(既決の制約の実行であり新しい決定を持たない) | — |
| **`.claude/core-areas.json`** | **追加しない**(**1 周目 P1-1 の是正**)。予定ファイルは**すでに全部コア判定対象**である — `backend/tests/db/*`(`.claude/core-areas.json:323`)/ `backend/tests/db_fixtures.py`(同 `:362`)/ `contracts/authz/*`(同 `:307`)。旧入力も paths 追加不要と明記(`../tenant-boundary-enforcement/design.md:260`) | — |
| `contracts/authz/product/*` | **変更しない**(TSK-424 の資産を**読むだけ**) | — |
| **Notion カード TSK-344 の DoD** | **現行化する**(PO 裁定 — カードは正本ではない) | — |

## 4. 実装方針

<!-- 重さ分類の根拠を明記。コア領域に触れるかを必ず判定 -->

**重さ分類 = コア領域**。根拠は **`contracts/authz/*`**(`.claude/core-areas.json:307` — `tenant-isolation`)に触れること。
**`backend/migrations/*` ではない** — 本タスクは migration に DDL を足さない(1 節の訂正)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**着手は TSK-424 の A1・A2・B・C がすべてマージされた後**(8 節。**1 周目 P0-2 の是正** — 旧記述「A1 + A2 の着地後」は
`product-authz-surface@58d48b7:plan.md:43` と食い違う)。**総数が変わりうるためステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。

**各ステップは 1 論理変更 = 1 コミットとして成立させる**(**1 周目 P1-3 の是正** — 旧ステップ 4 は生成物も更新ファイルも
実行コマンドも指定していなかった。設計書 6.1)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **実環境の適用主体と non-serving 区間の手順を運用文書として決める** — 適用主体(superuser 相当の外部主体が誰か)/ 新規接続の止め方 / 既存アプリ接続 0 件の確かめ方 / 失敗時に serving へ戻さない扱い。**置き場は `docs/ops/` に新設する運用手順書**(ファイル名はステップ着手時に `docs/README.md` の索引規則に従って決める) | 運用手順書が 4 項目を持つ。`product-authz-surface@58d48b7:design.md:280`・`:396` の逐語と対応がつく。**コードの差分 0 行** |
| 2 | **TSK-442 の `provisioned_product_catalog` を実スキーマ向けに再実行する経路を通す**(**fixture を新設しない** — **1 周目 P1-2 の是正**)。`backend/tests/db/conftest.py` が `db_fixtures.py` の fixture を明示 import / re-export する形(`backend/tests/db/conftest.py:6`)に合わせる | 製品資産に対する適用が成功し、`inspect_authz_catalog` が資産と一致する(ポリシーの `command` / `role_ids` / `policy_mode` / `USING` / `WITH CHECK` の exact 照合)。**適用が冪等**であること。**`backend/tests/conftest.py` の差分 0 行** |
| 3 | **最低要求 4 件と 8-3 の定常の不変条件を実スキーマに対して再実行する** — ① アプリ用ロールが関数を経由せず他テナント行を読めない ② `PUBLIC` が越境関数を実行できない ③ `search_path` の乗っ取りが効かない ④ 対象側が非共有なら要求元が付与していても返らない + **移行を行っていない定常状態の条件**(`product-authz-surface@58d48b7:design.md:517`) | 4 件 + 定常の不変条件すべて green。**期待 SQLSTATE**(`WITH CHECK` 違反 = `42501` / P5 アクセス = `42501` / 不正 UUID = `22P02` / `USING` で見えない = 0 行)で判定する |
| 4 | **12-4 の判定記録を生成する** — `docs/ops/` の運用手順書へ**判定記録の様式**(誰が・いつ・どの実スキーマに対して green を確認したか・どの入口について判定したか)を置き、本 PR ぶんの記録を**埋めて**コミットする。**入口を開かないので「対象入口なし」と書く** | 記録の 4 項目が揃い、**項目を省いていない**(`../../design/data-model.md:2534`)。PR 本文へ同じ内容を転記する |
| 5 | **DoD を現行化する**(**1 周目 P1-3 の是正** — 実装ステップが無かった)— 本計画書 5 節の DoD を [research-dod-revision.md](research-dod-revision.md) の結論へ揃え、**Notion カード TSK-344 の DoD 欄も同じ文面へ更新する**(カードの更新自体はステップ外・リポジトリ側の証跡は本計画書) | 5 節の DoD が `research-dod-revision.md:50`・`:63`・`:131` と一致する。**DoD 1 と 3 は変えない** |

## 5. DoD(受け入れ基準)

<!-- Notion カードの DoD を転記。ただし PO 裁定により「DoD 全体の見直し」が本タスクの射程に含まれる -->

> **【1 周目 P0-4 の是正】** 変わるのは **DoD 2・4・5・6** で、**DoD 1 と 3 は不変**である
> ([research-dod-revision.md](research-dod-revision.md)`:50`〜`:57`)。着手時に書いた
> 「追随不要なのは DoD 3 だけ」は誤りだった。

- [ ] **【DoD 1・不変】RLS のポリシーとロールの DDL が実スキーマへ適用されている**(カード自身が「**これが律速**」と記載)
- [ ] **【DoD 2・変わる】その実スキーマに対して越境テストが green である**(NFR-019(b))。
      **②の green は「適用単位」の範囲で判定する** — **判定の対象は当該 PR が開く入口の集合に限り、
      当該 PR が開いていない入口を理由に不合格と判定しない**(`../../design/data-model.md:2528`・`:2529`。
      [research-dod-revision.md](research-dod-revision.md)`:63`)
- [ ] **最低要求 4 件**を覆っている(**②③④の所有は U-C1 / U-C3 / U-A2 にある** — 線引きは 7 節 #3) — ① アプリ用ロールが関数を経由せず他テナント行を読めない ② `PUBLIC` が越境関数を実行できない ③ `search_path` の乗っ取りが効かない ④ 対象側が非共有なら要求元が付与していても返らない
- [ ] **測定経路の要求は空である**ことを確認した — **本タスクの PR は入口を 1 つも開かない**(現在の HTTP 入口は `/health` と `/version` の 2 本で、いずれも DB へ到達しないため `data-model.md:2494` により「開かない」)。**空であることは要求の免除ではなく、要求を当てる対象が無いこと**(同 `:2532`)
- [ ] **通過判定を PR に記録した** — 誰が・いつ・どの実スキーマに対して green を確認したか・**どの入口について判定したか**。**入口を 1 つも開かないので「対象入口なし」と書く(項目を省かない)**(同 `:2534`)
- [ ] **【DoD 6・変わる】12-4 の「越境テスト再実行ゲート」を通ったことを記録した**。
      **「non-serving 宣言の解除」ではない** — 新版の第 2 項は
      「**DB を利用する製品機能のマージまたは有効化は、本節の越境テスト再実行ゲートを通ることを条件とする**」
      という **PR ごとの継続的条件**へ変わり、**一回性の契機(=「解除」と読める条文)が消えた**。
      **「non-serving 宣言の解除」という語は正本に 1 件も無い**(全数確認 —
      [research-dod-revision.md](research-dod-revision.md)`:131`〜`:152`)。
      **第 1 項に終期を与える作業は TSK-382 の所有**であり、本タスクで解除した扱いにしない
- [ ] **DoD 自体の現行化**(TSK-381 の成果を反映 — **DoD 1 と 3 が不変、2・4・5・6 が変わる**)

## 6. テスト計画

**NFR-019 の「越境」に当たる。**合否は「越境が 1 件でもあれば fail」ではなく
**「FR-034 の認可行列どおりに通り、行列外はすべて 404」**で判定する(要件書 `:933`)。
ただし**本タスクは HTTP 入口を持たない**ので、判定は **DB 層(ロール・関数 ACL・`search_path`)**で行う
(最低要求 4 件は HTTP 経路への要求を 1 件も含まない — `../../design/data-model.md:2531`)。

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| 製品スキーマへの authz DDL 適用 | 故障系 + 正例 | `backend/tests/db/test_product_authz_application.py`(新設) | 適用の成功・冪等性・カタログ照合の一致 |
| 最低要求 ① | 越境 | `backend/tests/db/test_product_boundary.py`(新設) | アプリ用ロールが関数を経由せず他テナント行を読めない(**0 行**) |
| 最低要求 ② | 越境 | 同上 | `PUBLIC` が越境関数を実行できない(**`42501`**) |
| 最低要求 ③ | 越境 | 同上 | `search_path` の乗っ取りが効かない(`pg_temp` が末尾に 1 回) |
| 最低要求 ④ | 越境 | 同上 | 対象側が非共有なら要求元が付与していても返らない |
| `WITH CHECK` | 越境 | 同上 | 越境 `INSERT` と `tenant_id` 書換 `UPDATE` が **`42501`** |
| P5 `app_denied` | 越境 | 同上 | `AdminCredential` 等へのアクセスが **`42501`**(「0 行」ではない) |

**新設する DB テストは、名前によらずコア判定対象である**(**1 周目 P1-1 の是正**)—
`backend/tests/db/*` が `.claude/core-areas.json:323` に登録済み。着手時に書いた
「`test_authz*` を避けないと偶発的にコアになる」という説明は誤りで、**回避の必要も paths 追加の必要も無い**。

**fixture は新設しない**(**1 周目 P1-2 の是正**)— TSK-424 A2 が作る **`provisioned_product_catalog`** を再利用する。
新しい fixture を足すなら `backend/tests/db/conftest.py:6` の明示 import / re-export への登録が要り、
それが無いと注入が成立しない。

**実行手順**(`backend/` で。CI と同じ順 — `.github/workflows/ci.yml:253-258`):

```
docker compose up -d
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -c pyproject.toml --cov      # DB 必須テストの 0 件収集・0 件実行は TESTS_FAILED になる
```

**`--cov` は機械契約が `comparison: "exact"` で固定している**(**1 周目 P0-5 の是正** —
`backend/tests/db/environment-expectations.json:163` の `single_command.expected` /
`.github/workflows/ci.yml:258`)。着手時に書いた `--cov` 無しのコマンドは契約違反だった。

**pytest の呼び出しは 1 回のまま**(`environment-expectations.json:146-194` が
`marker_selection_argument_allowed: false` / `expected_backend_pytest_invocation_count: 1` を固定)。

## 7. 人間の裁定が要る事項

| # | 事項 | 状態 |
| --- | --- | --- |
| **1** | **本タスクの実体をどう確定するか** | **解消**(**1 周目 P0-2・P0-6 の是正**)。`data-model.md:2845-2846` は**作成・初回実行と再実行を分けており**、その後の決定が `../tenant-boundary-enforcement/design.md:341-345` で **TSK-424 / TSK-344** へ移管している。**確定済みの分担**であって未決ではない |
| **2** | **認証テーブルの RLS の帰属** | **解消**(**1 周目 P0-3 の是正**)。**TSK-424 が所有**し、`tenant_credentials` と `rate_limit_counters` を **`function_only`** と分類済み(`product-authz-surface@58d48b7:design.md:35-45`)。**関数側は U-A1**(同 `:640-643`)。着手時の見立て(本タスクが持つ)は**撤回した** |
| **3** | **最低要求 4 件の線引き** — `../tenant-boundary-enforcement/design.md:575-581` は **① = TSK-424 / ②③④ の共有関数分 = U-C1・U-C3 / 管理関数分 = U-A2 / 揃った 4 件の実スキーマ再実行 = TSK-344** と分けている。**加えて制御情報読み取り 4 経路の制限関数 = U-C2**(同 `:596`)・**認証とレート制限の関数 = U-A1**(`product-authz-surface@58d48b7:design.md:640-643`) | **未決** — **最低要求 4 件に使う具体的な関数を決め、その関数の所有タスクを依存として固定しないと、ステップ 3 の実行可能時点を判定できない**(**1 周目 P1-4**) |

## 8. 依存(すべて TSK-424 の下流)

| # | 要るもの | 所有 | 状態 |
| --- | --- | --- | --- |
| 1 | 表分類・製品 authz DDL 資産(`contracts/authz/product/*`)・capability カタログ | **TSK-424 PR A1** | 計画レビュー中。`contracts/authz/product/` は develop に未存在 |
| 2 | **適用器・実 DB 試験・probe↔製品写像・`provisioned_product_catalog`** | **TSK-442**(PR A2。**TSK-431 の 7C の後**) | 未着手 |
| 3 | **ランタイム契約の切り替え**(`ddl-elements.staged.json` → 最終パス) | **TSK-443**(PR B。**7D の後**) | 未着手。**これが着地しないと DDL は staged のまま**(`product-authz-surface@58d48b7:design.md:305-322`・`:586-599`) |
| 4 | **Session の供給** | **TSK-444**(PR C。**7C の後**) | 未着手 |
| 5 | 最低要求 ②③④ の関数側(共有) | **U-C1 / U-C3** | 未着手 |
| 6 | 制御情報読み取り 4 経路の制限関数 | **U-C2** | 未着手(`../tenant-boundary-enforcement/design.md:596`) |
| 7 | 管理関数 | **U-A2** | 未着手 |
| 8 | 認証・レート制限の関数(`function_only` 2 表の到達経路) | **U-A1** | 未着手(`product-authz-surface@58d48b7:design.md:640-643`) |

**→ 本タスクは 424 の完全な下流**であり、**TSK-424 は A1・A2・B・C のすべてがマージされるまで完了にしない**
(`product-authz-surface@58d48b7:plan.md:43`)。**A1 + A2 だけで着手すると、最終パスへ切り替わっていない DDL と、
実体の無い最低要求④を相手にすることになる**(**1 周目 P0-2**)。
**計画段階は並行して完走できる。**

## 9. 踏んではいけない他タスクの射程

| 範囲 | 所有 | 典拠 |
| --- | --- | --- |
| **`SP-06` と 12-4 の字面衝突**・**non-serving 第 1 項に終期を与える作業** | **TSK-382**(着手可) | `../../adr/ADR-004-merge-gate-scope.md:44` |
| **`data-model.md` 12-8 節の実装追随** | **TSK-424** | `../tenant-boundary-enforcement/plan.md:79`・`:125` |
| 表分類・プロファイル割り当て | **TSK-424** | 同 `design.md:595` |

**DoD 6 は「12-4 のゲートを通ったことを PR に記録した」という条文への写像に留める**(PO 裁定)。
`non-serving` の「解除」は**正本に対応条文が無い**(全数確認 — research.md 6 節)。

## 10. 本タスクが開けるもの

**帯 2 の葉 6 本 + 帯 3 の 6 本 = 12 単位のマージ路**(`../product-impl-unit-split/plan.md`)。
これらは「入口を開く単位」なので 12-4 ゲートの対象で、**実装はできるがマージできない**状態にある。

**ただし単独では開かない** — 入口を開くには製品 CRUD 経路を表す `route_kind` も要る。
着手時は**所有者が空席**だったが、**2026-09-24 に TSK-446 として起票し、`record_and_aggregate` を実装した**
(`scripts/check_authz_catalog.py:92` の `ROUTE_KINDS` — **1 周目 P0-6 の是正**:
この行が示すのは値域が閉じていることだけで、所有者の不在は示さない)。
