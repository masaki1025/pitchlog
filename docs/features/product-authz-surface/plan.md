---
feature: product-authz-surface
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域           # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc
branch: feature/product-authz-surface
created: 2026-09-24
計画レビュー周回: 9        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
| ★6 | **制御資源 4 表は、正本 3-0・3-5 節どおり「実効グループ ∧ 実効参加」の RLS ポリシーを持つ。そのうえでアプリ用ロールには表の権限を与えず、読み取りを U-C2 の制限関数に一本化する**(列と対象の行の制限を迂回させないため — 7 周目)。再帰と他テナントの有効状態の問題は、真偽値だけを返す補助関数(`SECURITY DEFINER`・所有者 `pitchlog_shared_fn_owner`)で解く。U-T1 design の P3 の記述(終了済みグループも見え続ける)は正本と矛盾していたので是正する | design.md 1-3 |
| ★7 | **capability は「記述」と「登録」に分ける**。本単位は表分類から導いた **capability カタログ**(開けてよい操作の閉じた一覧)を出す。**登録(公開 registry)は空のまま残し**、経路を持つ単位が行う。カタログに無い capability の登録は red | design.md 10 節 |
| ★8 | **PR を 4 本に分ける**(人間の承認 2026-09-24)。**本計画 = PR A1 と PR A2**。**PR A1** = ステップ 1〜12(spec の汎化・表分類・capability カタログ・製品 DDL 資産と静的検査)と正本の追随。**`backend/src` に DB 呼び出しを増やさない**ので、TSK-431 を待たずにマージできる。**PR A2** = ステップ 13〜21(適用器・カタログ検査・実 DB 試験・移行ロール・写像)。**`backend/src/pitchlog/authz/` に DB 呼び出しを足すので、迂回検査の `allowed_symbols`(凍結基準 `contracts/tenant_boundary/base-allowlist.json`)への追加が要り、TSK-431 の 7C の後に出す**。**PR B**(ランタイム契約の切り替え・暫定資産の削除)は TSK-431 の 7D の後、**PR C**(Session の供給 — PO 裁定)は `allowed_symbols` を足すので 7C の後。B と C は別タスク・別ブランチ・別計画書。PR A の間、製品 DDL 資産は `ddl-elements.staged.json` に置き、「未発効」の第三状態として検査する。**TSK-424 は PR A1・A2・B・C のすべてがマージされるまで完了にしない** | design.md 3-2・9 節・11 節 |
| ★9 | **製品 DDL は外部の適用主体(superuser 相当)が 1 トランザクションで適用する**。製品ロールに接する membership の辺は 0 本(正本 3-2 の「誰にも `GRANT` しない」を全製品ロールへ広げる)。振る舞いの試験は superuser でない接続で行う。実環境での適用主体は TSK-344 が決める | design.md 2-2・2-3 |
| ★10 | **表分類の自己充足の残余を受容する**(人間の判断 2026-09-24)。機械検査は、分類・露出の事実・ACL のどれか 1 つだけの変更を検出する多重防御とする。3 つを同じ PR で整合的に弱める変更は、コア領域の人間の逐行確認が止める。露出の事実は正本の文言を典拠に引き、引用が正本に実在することを機械で検査する | design.md 1-5 |

## 2. スコープ

### やること(PR A1・A2)

1. **資産指定オブジェクト**で authz ツールチェーンを一般化する(design.md 5 節)
2. **全 45 表の表分類資産**と、正本の文言を典拠に引く**露出の事実の資産**・割り当ての条件の検査(design.md 1 節)
3. **製品 authz DDL 資産**(`ddl-elements.staged.json` と `function-bodies/`)。ロール 4 種・DB とスキーマの所有と ACL・全表の `ENABLE` + `FORCE`・ポリシー・表 ACL・トリガ関数 33 個の `PUBLIC` 剥奪・制御資源の補助関数(design.md 1〜3 節)
4. **製品の適用器**(外部の適用主体が migration の後に 1 トランザクション・固定の 7 手順で適用。製品ロールに接する membership の辺は 0 本)と、使い捨てクラスタでの適用・カタログ検査・再適用と往復(design.md 2-2・4 節)
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
| **越境関数の本体・その ACL・`search_path`**(補助関数 1 個を除く) | U-C1 / U-C2(制御情報の読み取りの制限関数)/ U-C3 / U-A2(`../product-impl-unit-split/plan.md:224-227`) |
| **認証・レート制限・管理経路の関数**(`function_only` 表への到達経路) | U-A1 / U-A2 |
| **制御資源の列の粒度の制限**(テナント名のみ・`admin` のみの列)と、**他の参加テナント名の読み取り** | U-C2 の制限関数(design.md 1-3・7 節) |
| **規則セットを読む・大会へ結ぶ関数**と、**`rule_sets` の帰属の列の追加** | FR-014 の所有単位(単位分割計画に未掲載 — 候補 U-G1。design.md 1-6) |
| **`analysis_groups` の名称の列の追加** | U-C1(design.md 1-3) |
| **capability の登録(製品表への操作を開くこと)** | 経路を持つ単位(U-01・U-M1・U-D1 ほか — ★7) |
| **移行バッチ用ロールのライフサイクルの実行**(退役・接続監査・孤児回収・同時実行・状態の収束)・**実運用の移行実行**・**`event_slots` の食い違いの解消** | TSK-349(★1・★3。申し送りは design.md 8-4) |
| **正本 3-2 節 `:296` の典拠の訂正** | 承認後に起票する専用タスク(★4) |
| **probe 資産(`contracts/authz/` 直下)の変更** | 変更しない(封印 — `contracts/authz/oracle-seal.lock.json:40-88`) |
| **SP-06・12-4 の non-serving 宣言・12-6 の受け取り先表・3-5 節の述語の変更** | 変えない(★2・★6) |
| **`scripts/check_tenant_boundary_bypass.py` と、`base-allowlist.json` 以外の `contracts/tenant_boundary/*` の変更** | 触れない(TSK-431 と PR B の射程)。**`base-allowlist.json` の `allowed_symbols` への追加だけは PR A2 のステップ 13 で行う**(7C の後) |
| **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の変更** | 変えない(差分 0 行) |
| **Session の供給**(`TenantRepositoryBase._session` を満たす手段) | **TSK-424 の PR C**(PO 裁定 2026-09-24。別の計画書・別ブランチ。PR A と並行できる。U-T1 の基底の公開面の exact-set と、束縛文の順序を守る) |
| **HTTP の入口を開くこと** | 開かない。12-4 の判定記録には「対象入口なし」と書く(`data-model.md:2534`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8 節(`:2844-2846`) | TSK-317 行を分割し、TSK-424(**PR A で資産は確定・未発効**)/ TSK-349(移行ロールのライフサイクルの実行 — 残件)/ 3-2 節の典拠の訂正タスク(残件)/ U-C1・U-C2・U-C3・U-A2(越境関数と最低要求 ②③④ の残り — 残件)/ U-A1(認証・レート制限の関数 — 残件)/ U-C2(制御情報の読み取りの制限関数 — 残件)/ FR-014 の所有単位(規則セットの関数と帰属の列 — 残件)/ TSK-344(実スキーマでの再実行 — 残件)/ PR B のタスク(ランタイム契約の切り替え — 残件)に割り当てる。**「解消済み」にしない** | PR レビュー(7.6-3 前段・実装追随の節更新) |
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
- `scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` の差分 0 行(**PR A1**)。PR A2 はステップ 13 の `base-allowlist.json` の `allowed_symbols` への追加だけを許す
- **PR A1 は `backend/src` の DB 呼び出しの違反を増やさない**(迂回検査が green)
- `backend/migrations/` に `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` / `GRANT` が 0 件(`D7`)
- **既存の `test_*.py` の差分 0 行**。変えてよい既存ファイルは、各ステップの合格条件に列挙したものに限る(design.md 5 節)
- `.github/workflows/` と `tests/test_ci_wiring.py` の差分 0 行(CI の配線は変えない)
- 資産にパスワード・接続文字列を書かない(NFR-014)
- **安全性の期待値は、露出の事実(正本の文言が典拠)と manifest から導き、表分類資産から導かない**(design.md 1-5)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **資産指定オブジェクト `AuthzAssetSpec` と `PROBE_SPEC`**(`backend/src/pitchlog/authz/asset_spec.py` を新設)。生成器 `ddl.py` と body 検査器 `scripts/check_authz_function_bodies.py` が spec を受け取る。既定は `PROBE_SPEC` | 変える既存ファイルは `ddl.py` と `check_authz_function_bodies.py` だけ。`backend` と `harness` の pytest がすべて green。`ddl.py` の AST 検査(`backend/tests/test_authz_ddl.py:181`)が green のまま。**spec の取り違えで red**: probe 以外の scope 値を `PROBE_SPEC` で読むと拒否。probe 資産の差分 0 行 |
| 2 | **適用器・DB カタログ検査・DB fixture を spec 対応にする**(`provisioning.py` / `catalog.py` / `backend/tests/db_fixtures.py` / `backend/tests/db/conftest.py`)。操作種別の閉じた集合を spec ごとに持つ | 変える既存ファイルは上の 4 つだけ(`conftest.py` は再エクスポートの追加のみ)。既存の DB 試験がすべて green。**操作種別の集合が spec ごとに閉じている**(試験の中で組み立てた、probe ではない試験用の spec で確かめる。本物の `PRODUCT_SPEC` での双方向の負例は `PRODUCT_SPEC` を作るステップで置く — 8 周目 8-P1-3)。`requires_db` の収集件数が減っていない |
| 3 | **静的検査 `scripts/check_authz_catalog.py` の scope 検査を spec 対応にする**。probe 固有の閉じた検査は probe spec のときだけ走らせる | 変える既存ファイルは `check_authz_catalog.py` だけ。既存の `tests/test_check_authz_*.py` が差分 0 行で green。**試験用の非 probe spec で probe 資産を読むと拒否・probe spec で非 probe の scope の資産を読むと拒否**(本物の `PRODUCT_SPEC` での負例は後のステップ)。**既定の呼び出しと、`PROBE_SPEC` を明示した呼び出しの出力が byte 一致**する。**既存の回帰試験の観測範囲を維持する**(差分 0 行の既存試験が green)。**spec で分岐させた probe 固有の検査の一覧**を持ち、**各分岐を誤って無効にする変異で red**(8 周目 8-P2-1)。新しい凍結基準は置かない |
| 4 | **表分類資産 `table-classification.json`** と**露出の事実の資産 `exposure-facts.json`**(正本の文言を典拠に引く)・割り当ての条件の検査(design.md 1-4・1-5) | **正例**: 1-4 の 45 表の割り当てが全条件を満たす。母集合は `Base.metadata` と manifest の両方から導き、両者の一致も検査。**露出の事実の典拠の引用がすべて正本 `data-model.md` に一字一句存在する**。事実の表と列が manifest に実在する。**変異で red**(design.md 1-5-c): `admin_credentials → global_read_only` / `tenant_credentials → tenant_owned` / `analysis_groups → tenant_owned` / `admin_operation_logs → effective_group_control` / `migration_quarantine → global_read_only` / `rate_limit_counters → global_read_only` / **`rule_sets → global_read_only`** / **`tournament_rule_assignments → tenant_owned`**(露出の事実「所有が混在する規則資源」で拒否 — 7 周目 7-P0-2)/ 未割り当て / モデルの追加 / `access_path.reason` を消す / 典拠の引用を正本に無い文言に書き換える / 露出の事実から `password_hash` を消し同時に `admin_credentials` を `global_read_only` にする |
| 5 | **capability カタログ `capability-catalog.json`** と**登録の検査**(design.md 10 節)。**ステップ 4 の表分類を入力にする**(4 → 5)。登録の集合そのものは空のまま | カタログが表分類から生成器で導出され、導出結果と一致(手書きの変更で red)。`direct` の表だけが載り、`effective_group_control` と `function_only` は 0 件。**capability ID と `(表 ID, 操作種別)` が 1 対 1**(ID の重複・同じ組への 2 つの ID で red)。**登録の検査は、登録された operation token の文を解析し、その対象の表とコマンドが、ID に結び付いたカタログの行と一致することを確かめる**。**変異で red**: カタログに無い ID を登録する / **カタログにある正しい ID を別の表の文に付け替える** / **別の操作(読み取りの ID で書き込み)に付け替える** / ID を重複させる(試験の中だけで仮に登録する — 製品のパッケージには収載しない)。`backend/src/pitchlog/repositories/repository_contract.py:57-59` の 3 集合が空のまま |
| 6 | **`PRODUCT_SPEC` と、未発効の第三状態**: `ddl-elements.staged.json` の骨組み(scope・`pending_switch`)と、新設の試験 `backend/tests/test_authz_product_staging.py`(design.md 3-2) | **本物の `PRODUCT_SPEC` での双方向の負例**(製品資産を `PROBE_SPEC` で読むと拒否・probe 資産を `PRODUCT_SPEC` で読むと拒否 — 8 周目 8-P1-3)。未発効状態の検査が green(最終パス `ddl-elements.json` が無い / ランタイムは暫定のまま / `pending_switch` がタスク ID を持つ)。**staged と最終パスが両方あると red**。既存の `test_authz_runtime_contract.py` の差分 0 行 |
| 7 | **製品 DDL 資産(1)ロールと membership の宣言**: ロール 3 種の作成・**全製品ロールの 7 属性の肯否**(design.md 2-0)・**恒久の特権主体の許可集合の製品固定部分**(`pitchlog_owner`)・**製品ロールに接する辺 0 本の宣言**(design.md 2・2-2) | `PRODUCT_SPEC` で生成器・body 検査器・静的検査が green。**変異で red**: `pitchlog_app` に `BYPASSRLS` を足す / 関数所有ロールに `LOGIN` を足す / 宣言から属性を 1 つ消す / 製品ロールへの辺を宣言に足す。資産に `password` と接続文字列が 0 件 |
| 8 | **製品 DDL 資産(2)DB とスキーマの所有と ACL**: DB・`public`・`authz_private` の期待集合(design.md 2-1 の表)。`PUBLIC` の DB の `CONNECT`・`TEMPORARY` と `public` の `USAGE`・`CREATE` の剥奪 | 静的検査が green。**変異で red**: DB に `PUBLIC` の `CONNECT` を戻す / `pitchlog_app` に DB の `CREATE` か `TEMPORARY` を与える / `public` に `PUBLIC` の `USAGE` を戻す / `public` の `CREATE` の剥奪を消す / `authz_private` に `CREATE` を与える / **`pitchlog_app` に `authz_private` の `USAGE` を与える**(何も与えないのが正 — 8 周目 8-P1-1) |
| 9 | **製品 DDL 資産(3)全 45 表の `ENABLE` + `FORCE`** | 静的検査が green。表分類と一致(45 表すべて)。**変異で red**: 1 表の `FORCE` を外す / 1 表の `ENABLE` を外す |
| 10 | **製品 DDL 資産(4)表のポリシーと表 ACL・列 ACL**: `tenant_owned` 23 表・`self_tenant_row`・`global_read_only` のポリシー(述語は 1 要素から展開し、展開結果を固定)・表 ACL(**制御資源 4 表にはアプリ用ロールの権限を与えない**) | **作成済みの 3 プロファイル(`tenant_owned`・`self_tenant_row`・`global_read_only`)について**、表分類と DDL の一致を静的に検査(プロファイルごとのポリシーの有無・ACL・コマンド・roles・`USING`・`WITH CHECK` の exact-set。**プロファイルから DDL への対応は、プロファイルの定義〔design.md 1-1〕から導く**)。**全 5 プロファイルの exact-set はステップ 12 で初めて要求する**(6 周目 6-P1-4)。**変異で red**: ポリシーを 1 本消す / `WITH CHECK` を消す / `DELETE` を足す / `function_only` の表に ACL を足す / `::UUID` を `::BIGINT` に変える / 展開結果を手で書き換える(digest 不一致)/ **制御資源 4 表のどれかに `pitchlog_app` の `SELECT` を与える** / 露出の事実で秘密とされた列に、どれか 1 つでもアプリ用ロールの `SELECT` を与える |
| 11 | **製品 DDL 資産(5)トリガ関数 33 個の `PUBLIC` 剥奪**(design.md 3-4) | 静的検査が green。33 個が関数 ACL の exact-set に入っている。**変異で red**: 1 個の剥奪を消す |
| 12 | **製品 DDL 資産(6)制御資源の補助関数とポリシー**(design.md 1-3): `authz_private.tenant_has_effective_membership`・4 表のポリシー・関数 ACL・**所有者の `{表, 列, 権限}` の exact-set** | 静的検査が green。**全 5 プロファイルについて、表分類と DDL の exact-set が成り立つ**(ここで初めて要求する)。**関数の属性が exact**: `SECURITY DEFINER` / `STABLE` / 所有者 `pitchlog_shared_fn_owner` / `search_path` の末尾に `pg_temp` / 本文の表参照がすべてスキーマ修飾 / `PUBLIC` からの剥奪が作成と同じトランザクション / **`pitchlog_app` に `EXECUTE` を与えない**。**変異で red**: `pg_temp` の明示を外す / `PUBLIC` に `EXECUTE` を与える / `pitchlog_app` に `EXECUTE` を与える / 「実効グループ」「参加テナントが有効」「`admin`」の条件を 1 つずつ外す / 所有者に表単位の `SELECT` を与える・使わない列を 1 つ足す・必要な列を 1 つ欠く |
| 13 | **(PR A2 の先頭 — TSK-431 の 7C の後)製品の適用器と、使い捨てクラスタでの適用の fixture**(design.md 2-3・4-1・4-2): 外部の適用主体(superuser)が `pitchlog_owner` と DB を用意 → `alembic upgrade head`(`pitchlog_owner`)→ 製品 DDL を **1 トランザクション・固定の 7 手順**(補助関数をポリシーより先に作る — 7 周目 7-P0-3)で適用。fixture `provisioned_product_catalog` を新設(**`pitchlog_owner` を 7 属性どおりに作ってから適用前のカタログを記録する** — 8 周目 8-P2-2)。**再適用のたびに 7 属性を正規化する** | 適用が成功し、**commit 後の同じ接続で `current_user = session_user`**(`SET ROLE` を使っていない)。migration は `pitchlog_owner` の接続で走っている。既存の `provisioned_catalog` の振る舞いが変わらない。**変える既存ファイルは `provisioning.py`・`backend/tests/db_fixtures.py`(fixture の新設)・`backend/tests/db/conftest.py`(再エクスポートの追加)・`contracts/tenant_boundary/base-allowlist.json`(`allowed_symbols` への追加と、7C の後の形式での 7.7-2 の記録)**。迂回検査が green |
| 14 | **カタログの exact-set 検査**(design.md 2-2・3-4・6-3 の危険終点) | 全 45 表の `relrowsecurity` と `relforcerowsecurity`・`pg_policy`・表 / 列(`pg_attribute.attacl`)/ スキーマ / 関数 / DB の ACL・ロール属性・DB とスキーマの所有者が**資産と exact-set**。**`pg_auth_members` のうち製品ロールに接する行が 0 件**。**LOGIN できる危険ロールの集合 = 許可集合(製品固定の `pitchlog_owner` ∪ 検査の入力として渡す環境の superuser の OID)**。33 個のトリガ関数がすべて `SECURITY INVOKER`。**変異で red**: `ADMIN` だけの辺を 1 本足す / 製品ロールから出る辺を足す / 許可集合に無い `LOGIN` + `BYPASSRLS` のロールを作る / 入力に無い superuser を作る / `SECURITY DEFINER` のトリガ関数を 1 つ混ぜた migration |
| 15 | **適用の原子性と故障系**(design.md 4-2) | **失敗点 5 箇所**(補助関数の作成の直後・ポリシーの作成の直後を含む)で故障を注入し、**カタログが適用前と一致**。**rollback 後の同じ接続で `current_user = session_user`**。**変異で red**: 手順の途中に commit を挟む |
| 16 | **再適用と往復**(design.md 4-3) | 製品 DDL を 2 回適用しても、2 回目の後のカタログが 1 回目と一致。**製品 DDL の適用 → 製品 DDL の取り外し → `downgrade base` → `upgrade head` → 再適用**の後のカタログが、初回の適用後と一致。**取り外しの後のカタログが適用前と一致**し、取り外しの途中の失敗(ポリシーの削除の直後・補助関数の削除の直後)で何も変わらない。取り外しはポリシーを補助関数より先に落とし、`pitchlog_owner` は削除しない。**危険な属性からの正規化の試験は別のケース**とし、取り外しの前後の一致を求めない(6 周目 6-P1-2・7 周目 7-P0-3)。**7 属性に危険な属性を足した状態から再適用すると、正規化で消える**。既存の `backend/tests/db/test_migration_round_trip.py` は差分 0 行 |
| 17 | **実 DB 試験(1)`tenant_owned` 23 表**(design.md 6-1)。試験は manifest の事実からパラメタ化して生成する(分類資産から期待値を導かない) | 23 表**すべて**で: **最低要求 ①**(他テナントの行が 0 行。**さらに `tenant_id` 列を持つ 28 表すべてで、他テナントの行が 0 行か `42501`** — 分類に依らない)/ `WITH CHECK` 違反が `42501` / 未束縛が 0 行 / 不正 UUID が `22P02` / `DELETE` が `42501`。**変異で red**: 1 表のポリシーを外す・`FORCE` を外す・`WITH CHECK` を `true` にする |
| 18 | **実 DB 試験(2)その他のプロファイル**(design.md 6-2) | `self_tenant_row` / `global_read_only` / `function_only` 13 表(**`42501` であって 0 行ではない**)/ **`pitchlog_app` は制御資源 4 表を `SELECT` できず、補助関数も呼べない(`42501`)** / **ポリシーの述語の正負行列の全セル**(**rollback する試験のトランザクションの中で、`pitchlog_app` に 4 表の `SELECT`・`authz_private` の `USAGE`・補助関数の `EXECUTE` を一時的に与え、rollback の後にカタログが exact-set に戻ることも検査する** — 8 周目 8-P1-2。実効参加の `member` と `admin`・非参加・離脱・**グループ終了**・**参加テナントの無効化**・存在しないグループ) / **テナント A と B がそれぞれ大会規則を作り、`pitchlog_app` は `rule_sets` と `tournament_rule_assignments` のどちらも読めない(`42501`)**(design.md 1-6)。**変異で red**: `function_only` の表に `SELECT` を与える / 補助関数の条件を 1 つずつ外す |
| 19 | **実 DB 試験(3)横断の観点**(design.md 6-3) | トリガの発火(`PUBLIC` 剥奪後)/ FORCE(`pitchlog_owner` でも未束縛で 0 行)/ 危険終点の交差が空 / **最低要求 ②**(`PUBLIC` と、信頼しない `LOGIN` ロール〔`pitchlog_app` を含む〕が補助関数の実効の `EXECUTE` を持たない。関数所有者と環境入力の superuser は負例の母集合から除く)/ **最低要求 ③**(`pitchlog_app` は一時表を作れない〔`42501`〕・`TEMPORARY` を持つ試験専用ロールの一時スキーマの乗っ取りが補助関数に効かない)/ `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件 |
| 20 | **移行バッチ用ロールの資産 `migration-batch-role.json`**(書き込み先と有効な間の形)と、**有効な間の形の試験**・**定常の不変条件**(design.md 8-1〜8-3) | **`write_targets` が導出集合 19 表と exact-set**、かつ**必要な権限の行列(`{表, 列, 権限}` — 19 表の `INSERT`・`SELECT`、`retired_at` を持つ表の `UPDATE(retired_at)`、`migration_runs` の許された列の `UPDATE`)と exact-set**。**正例**: 資産どおりに作ったロールで、19 表への最小の `INSERT`・`SELECT` と、`retired_at` の更新が実際に通る。使い捨てクラスタで資産どおりに作ったロールが、**渡された OID に対して**有効な間の形を満たす(接する辺 0 本・所有しない・表 ACL が exact・DB は `CONNECT` のみ・**製品スキーマの利用者定義の関数を 1 つも実行できない**・属性)。**定常の不変条件**(許可集合に無い `LOGIN` + `BYPASSRLS` のロールが 0 件)がカタログ検査に入り、形のロールを 1 つ残すと不合格。**変異で red**: `write_targets` に表を 1 つ足す / **必要な権限を 1 つ外す** / **表単位の `UPDATE` を与える**(`lineup_memories.lineup`・`medical_notes.content` の `UPDATE` が通るようになる)/ `DELETE` を足す / 無関係な `LOGIN` ロールから辺を足す / 適用主体から辺を足す / ロールに表を 1 つ所有させる / **`write_targets` の外へ書く試験用の `SECURITY DEFINER` 関数の `EXECUTE` を与える** / `PUBLIC` に関数の `EXECUTE` を戻す / 既定の権限で `EXECUTE` が付くようにする |
| 21 | **probe ↔ 製品の写像資産 `probe-product-map.json`** と、その検査(design.md 7 節) | `probe の全原子要素 = mapped ∪ explicit_non_mapping` と `製品の全原子要素 = mapped の像 ∪ product_only` が**両方向 exact-set**。理由コードは閉じた列挙で、種別ごとに使えるコードが固定。`read_control_resources` が `deferred_to_owning_unit` / `owner_unit: U-C2`。**製品側の母集合は `ddl-elements.staged.json` だけから取る**(移行バッチ用ロールを含めない)、`app_role` の `DELETE` が `forbidden_by_canon`。**変異で red**: probe 要素の写像を 1 つ消す / 製品要素を 1 つ足して写像しない / 列挙外の理由コード / 種別に合わない理由コード / `read_control_resources` の `owner_unit` を U-C2 以外にする / 許可していない 1 対多 |

**ステップの順序と並行性**:

- 1 → 2 → 3 は順に依存する。**4 → 5 の鎖(表分類 → capability カタログ)は 1〜3 と独立**(spec を使わない)なので、**先に入れて帯 2 へ早く渡す**ことができる
- 6 → 7 → … → 12 は順に依存する(6 は 1〜5 の後)。**ここまでが PR A1**。PR A1 の各ステップは、**迂回検査を `--base-ref origin/develop` で走らせて green**(`backend/src` の DB 呼び出しの違反が増えていない)であることを合格条件に含める
- **PR A2**: 13 → 14 → … → 19 は順に依存する
- 20(移行バッチ用ロール)は 14 の後。21(写像)は 12 の後で、20 には依存しない(写像は移行ロールの資産を読まない — design.md 7 節)。21 は静的な資産の検査なので、**PR A1 に入れてもよい**(DB 呼び出しを足さない)
- **TSK-431 との関係**: PR A1 は `scripts/check_tenant_boundary_bypass.py`・`contracts/tenant_boundary/*`・`.github/workflows/`・`tests/test_ci_wiring.py` に触れないので衝突しない。**PR A2 はステップ 13 で `contracts/tenant_boundary/base-allowlist.json` を変える**ので、TSK-431(7B が同じ資産を書き換え、7C が記録の形式を直す)のマージ後に出す
- **U-T1 の後続単位との衝突面**は `backend/tests/db/conftest.py`(再エクスポートを足すだけ)と `contracts/authz/product/`

**正本の追随**(3 節)は、ステップ 21 の後に /sync-docs で行い、PR A に含める(Claude が書く。委任しない — 設計書 7.6-2)。

## 5. DoD(受け入れ基準)

Notion カードの DoD を ★1〜★10 に合わせて書き換えたもの。**承認後に Notion を同期する**。

- [ ] **全 45 表に物理プロファイルが排他で割り当てられ、未割り当てが 0 件**(母集合は `Base.metadata` から導出。割り当ては明示メタデータ。**全表が、露出の事実と manifest で判定する割り当て条件を満たす**)。**プロファイルは 5 種で確定**し、カードが求めた「親表経由」「認証前グローバル可変」は `function_only` の到達経路の理由として記録した(★5)
- [ ] **全表が `ENABLE` + `FORCE ROW LEVEL SECURITY`**(正本 3-2 節の「全テーブルへ FORCE」を変えない)
- [ ] **全表で `{プロファイル, ACL, コマンド, roles, USING, WITH CHECK}` が exact-set**(静的検査とカタログ検査の両方)
- [ ] **制御資源 4 表が、正本 3-0・3-5 節の「実効グループ ∧ 実効参加」のポリシーを持ち**(グループ終了・参加テナントの無効化で見えなくなることを含む — ★6)、**アプリ用ロールは 4 表に直接触れない**(読み取りは U-C2 の制限関数)
- [ ] **使い捨てクラスタで、製品 migration と製品 authz DDL の適用、カタログ検査、再適用と往復、実 DB 試験が green**。最低要求 ① を 23 表すべて(と、`tenant_id` を持つ 28 表)で、②③ を補助関数で表明した。④ は対象が無いことを表明した
- [ ] **製品ロールに接する membership の辺が 0 本**(`ADMIN OPTION` を含む)。LOGIN できる危険ロールの集合が、恒久の特権主体の許可集合と一致する(★9)
- [ ] **probe ↔ 製品の写像が両方向 exact-set**(非写像の理由コードと `owner_unit` が全件に付く)
- [ ] **移行バッチ用ロールの資産が確定している**: 書き込み先が導出集合 19 表と exact-set・**必要な権限の行列(`{表, 列, 権限}`)と exact-set で、権限を 1 つ外すと red・19 表への最小の `INSERT`・`SELECT` と `retired_at` の更新が実際に通る**・有効な間の形(到達しない・所有しない・表 ACL)が使い捨てクラスタで検査されている・定常の不変条件がカタログ検査に入っている。**ライフサイクルの実行は TSK-349 へ申し送った**(design.md 8-4 の要求事項を TSK-349 のカードに記録)
- [ ] **capability カタログが表分類から導出されている**。登録の集合は空のままで、カタログに無い capability の登録は red になる
- [ ] **露出の事実の典拠がすべて正本に実在し、秘密の列はアプリ用ロールから読めない**(表単位・列単位とも)。残余リスク(★10)と逐行確認の観点を PR 本文に書いた
- [ ] **全製品ロールの 7 属性が肯否で固定され、再適用のたびに正規化される**。DB とスキーマの ACL が期待集合と exact-set
- [ ] **PR A の段階が「未発効」の第三状態として検査されている**(staged と最終パスの二重は red)
- [ ] **12-8 節に残件・所有者(PR A2 / PR B / PR C の各タスク / U-A1 / U-A2 / U-C1〔`analysis_groups` の名称の列を含む〕/ U-C2〔制御情報の読み取りの制限関数〕/ U-C3 / FR-014 の所有単位〔規則セット〕/ TSK-344 / TSK-349 / PR B のタスク / 3-2 節の典拠の訂正タスク)・発効条件を記録した**。TSK-424 は「資産は確定・未発効」と書いた
- [ ] **`contracts/authz/` 直下の probe 資産の差分 0 行**(`oracle-seal.lock.json` の封印を動かさない)
- [ ] **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の差分 0 行**
- [ ] **PR に 12-4 の判定記録を残した**(「対象入口なし」)
- [ ] **FR-014 の到達経路(規則セットを読む・大会へ結ぶ関数)と `rule_sets` の帰属の列の所有を、実在する Notion タスク ID で確定し、12-8 にその ID を記録した**(抽象的な「FR-014 の所有単位」のままにしない)。確定は単位分割の持ち主(進行管理・PO)へ依頼する
- [ ] **PR C(Session の供給)の Notion タスクを起票し、ID を 12-8 と DoD に記録した**
- [ ] **申し送りを Notion と PR 本文に記録した**: TSK-349 の射程の書き換えと design.md 8-4 の要求事項(★1)/ FR-014 の所有単位の確定依頼と `rule_sets` の帰属の列(design.md 1-6)/ U-C1 への `analysis_groups` の名称の列 / PR B のタスクの起票(★8)/ `event_slots` の食い違い(★3)/ 3-2 節の典拠の訂正タスクの起票(★4)/ TSK-344 への運用契約 / TSK-250 への写像資産の正の所在
- [ ] pytest / ruff / ty green(`backend` と `harness` の両方)
- [ ] **コア領域として敵対レビューと、人間の逐行確認(PR 作成者以外)を通した**

## 6. テスト計画

| NFR-019 の種別 | 足すもの | ステップ |
| --- | --- | --- |
| **単体** | 資産指定オブジェクトと spec の取り違え・spec の分岐の変異・表分類の割り当て条件と露出の事実(典拠の実在)・capability カタログと登録・未発効状態・ロール属性・DB とスキーマの ACL・DDL 資産と表分類の一致・補助関数の属性と所有者の列権限・写像の両方向 exact-set | 1〜12・21 |
| **越境**(NFR-019(b) の DB 層) | 最低要求 ① を 23 表すべて(と、`tenant_id` を持つ 28 表)・`WITH CHECK`・未束縛・`function_only` の `42501`・制御資源の正負行列・秘密の列の `42501`・最低要求 ②③・危険終点と membership の exact-set・移行ロールの有効な間の形(使い捨てクラスタ・`requires_db`) | 14・17・18・19・20 |
| **故障系** | 適用の失敗点 5 箇所での原子性・commit 後と rollback 後の `current_user`・不正 UUID の `22P02` | 13・15・17 |
| **一致性** | 述語の展開結果と要素の digest・再適用の収束・往復後のカタログの一致・capability カタログと表分類の一致 | 5・10・16 |
| **E2E** | **対象外**(入口を開かない。HTTP の越境テストは入口を開く単位が同じ PR に含める — ADR-004 D-2) | — |

- **各ステップの合格条件に、変異で red になることを入れた**(改変前の green を assert してから変異させる)
- DB 試験は既存の `requires_db` マーカーに乗せる。収集 0 件でセッションを失敗にする既存の仕組み(`backend/tests/db/conftest.py:83-119`)に守られる
- CI では `backend` ジョブ(`.github/workflows/ci.yml:210-260`)が走る。使い捨てクラスタは既存の `disposable_postgres_cluster` と同じ `docker run` 方式で起動する
