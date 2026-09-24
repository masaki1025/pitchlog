---
feature: product-authz-surface
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-24・山田正輝) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域           # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc
branch: feature/product-authz-surface
created: 2026-09-24
計画レビュー周回: 12        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TSK-424 製品認可面の確定 — PR A1(資産と静的検査)

## 1. 背景・目的

- Notion: [TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)(U-T1〔TSK-390〕から 2026-09-17 に分離 — 人間の裁定・山田正輝)
- 調査: [research.md](./research.md)(2026-09-24・4 並列)/ 詳細設計: [design.md](./design.md)
- 要件: [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)(チーム間データ分離・初日から全機能)/ [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)(越境テスト)/ [NFR-014](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-014)(シークレット)/ [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034)(認可行列)/ [FR-038](../../requirements/requirements-pitchlog-2026-07-22.md#FR-038)(移行)。機構の正は `docs/design/data-model.md` 3 章(RLS の採否は同書の設計判断 — `:139-149`)

**なぜやるか**: 製品の DB には、RLS・ロール・ACL がまだ 1 つも無い(`backend/migrations` に 0 件、`contracts/authz/product/` は未作成)。
いまある認可資産は、機構の検証用の probe(`product_schema: false`)だけである。
このため、越境テストの再実行ゲート(TSK-344)の通過条件 ①「RLS のポリシーとロールの DDL が実スキーマへ適用されている」(`data-model.md:2529`)が、**適用する DDL そのものが無い**という理由で満たせない。
帯 2 の単位(U-M1・U-D1 ほか)も、製品表への操作を開く capability を、表分類が確定するまで足せない(`../tenant-boundary-enforcement/plan.md:87`・`../tenant-boundary-enforcement/design.md:321`)。

TSK-424 全体は、**全 45 表の許可プロファイル・製品 authz DDL 資産・probe ↔ 製品の写像・capability カタログ・移行バッチ用ロールの資産**を確定し、使い捨てクラスタで適用して検査するところまでを行う(詳細設計 [design.md](./design.md) が全体の設計の正)。
**本計画書はそのうち PR A1**(spec の汎化・表分類・露出の事実・capability カタログ・製品 DDL 資産と静的検査)**だけを扱う**。PR A2(適用器・実 DB 試験・移行ロール・写像)・PR B(ランタイム契約の切り替え)・PR C(Session の供給)は、それぞれ別タスク・別計画書で行う。**実スキーマへの適用は TSK-344 が行う。**

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
| ★8 | **TSK-424 を PR 4 系統に分ける**(人間の判断 2026-09-24)。**本計画 = PR A1** = spec の汎化・表分類・露出の事実・capability カタログ・製品 DDL 資産と静的検査。**`backend/src` の DB 呼び出しを増やさない**ので TSK-431 を待たない。**PR A2**(適用器・カタログ検査・実 DB 試験・移行ロール・写像)は、迂回検査の `allowed_symbols`(凍結基準 `base-allowlist.json`)への追加が要るので TSK-431 の 7C の後。**PR B**(ランタイム契約の切り替え)は 7D の後。**PR C**(Session の供給 — PO 裁定)は `allowed_symbols` を足すので 7C の後。**A2・B・C は別タスク・別ブランチ・別計画書**(起票済み: **PR A2 = TSK-442 / PR B = TSK-443 / PR C = TSK-444**。正本 3-2 節の典拠の訂正 = **TSK-445** — 2026-09-24)。PR A1 の間、製品 DDL 資産は `ddl-elements.staged.json` に置き、「未発効」の第三状態として検査する。**TSK-424 は A1・A2・B・C のすべてがマージされるまで完了にしない**(上位カードとして保持) | design.md 3-2・9 節・11 節 |
| ★9 | **製品 DDL は外部の適用主体(superuser 相当)が 1 トランザクションで適用する**。製品ロールに接する membership の辺は 0 本(正本 3-2 の「誰にも `GRANT` しない」を全製品ロールへ広げる)。振る舞いの試験は superuser でない接続で行う。実環境での適用主体は TSK-344 が決める | design.md 2-2・2-3 |
| ★10 | **表分類の自己充足の残余を受容する**(人間の判断 2026-09-24)。機械検査は、分類・露出の事実・ACL のどれか 1 つだけの変更を検出する多重防御とする。3 つを同じ PR で整合的に弱める変更は、コア領域の人間の逐行確認が止める。露出の事実は正本の文言を典拠に引き、引用が正本に実在することを機械で検査する | design.md 1-5 |

## 2. スコープ

### やること(PR A1)

1. **資産指定オブジェクト**で authz ツールチェーンを一般化する(design.md 5 節)。DB 呼び出しは増やさない
2. **全 45 表の表分類資産**と、正本の文言を典拠に引く**露出の事実の資産**・割り当ての条件の検査(design.md 1 節)
3. **capability カタログ**と、登録の検査(design.md 10 節)
4. **製品 authz DDL 資産**(`ddl-elements.staged.json` と `function-bodies/`)と静的検査。ロール・DB とスキーマの ACL・全表の `ENABLE` + `FORCE`・ポリシー・表 ACL・トリガ関数の `PUBLIC` 剥奪・制御資源の補助関数(design.md 1〜3 節)。未発効の第三状態の検査
5. **正本の追随**: `data-model.md` 12-8 の分割(A1 の範囲だけを確定と書く)・変更履歴・`docs/README.md`(design.md 11 節)
6. **申し送り**の記録(Notion と PR 本文)と、**A2・B・C・3-2 節の典拠の訂正・FR-014 の到達経路の各タスクの起票**

### やらないこと

| やらないこと | 行き先 |
| --- | --- |
| **適用器・カタログ検査(DB)・適用の原子性・再適用と往復・実 DB 試験・移行バッチ用ロールの資産と試験・probe ↔ 製品の写像** | **PR A2**(TSK-431 の 7C の後。別タスク・別計画書 — 4 節の引き渡し) |
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
| **`scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*` の変更** | 触れない(TSK-431・PR A2・PR B の射程) |
| **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の変更** | 変えない(差分 0 行) |
| **Session の供給**(`TenantRepositoryBase._session` を満たす手段) | **TSK-424 の PR C**(PO 裁定 2026-09-24。別の計画書・別ブランチ。`allowed_symbols` を足すので TSK-431 の 7C の後。PR A2 と並行できる。U-T1 の基底の公開面の exact-set と、束縛文の順序を守る) |
| **HTTP の入口を開くこと** | 開かない。12-4 の判定記録には「対象入口なし」と書く(`data-model.md:2534`) |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` 12-8 節(`:2844-2846`) | TSK-317 行を分割し、TSK-424 PR A1(**表分類・露出の事実・capability カタログ・製品 DDL の静的資産は確定・未発効**。適用・実 DB 検査・移行ロール・写像は**確定と書かない**)/ TSK-424 PR A2(適用器・実 DB 検査・移行ロールの資産・写像 — 残件)/ TSK-349(移行ロールのライフサイクルの実行 — 残件)/ 3-2 節の典拠の訂正タスク(残件)/ U-C1・U-C2・U-C3・U-A2(越境関数と最低要求 ②③④ の残り — 残件)/ U-A1(認証・レート制限の関数 — 残件)/ U-C2(制御情報の読み取りの制限関数 — 残件)/ FR-014 の所有単位(規則セットの関数と帰属の列 — 残件)/ TSK-344(実スキーマでの再実行 — 残件)/ PR B のタスク(ランタイム契約の切り替え — 残件)/ PR C のタスク(Session の供給 — 残件)に割り当てる。**「解消済み」にしない** | PR レビュー(7.6-3 前段・実装追随の節更新) |
| `docs/design/data-model.md` 変更履歴 | 上を追記する。**版は上げない** | PR レビュー(同上) |
| `docs/README.md` | `data-model.md` の行の最終更新日と変更の概要を、12-8 の追随に合わせて現行化する(README は正本の版と状態の索引であり、contracts の資産は載せない — 11 周目 11-P2-2) | PR レビュー |
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
- **`backend/src` の DB 呼び出しの違反を増やさない**(迂回検査が green)
- `backend/migrations/` に `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` / `GRANT` が 0 件(`D7`)
- **既存の `test_*.py` の差分 0 行**。変えてよい既存ファイルは、各ステップの合格条件に列挙したものに限る(design.md 5 節)
- `.github/workflows/` と `tests/test_ci_wiring.py` の差分 0 行(CI の配線は変えない)
- 資産にパスワード・接続文字列を書かない(NFR-014)
- **安全性の期待値は、露出の事実(正本の文言が典拠)と manifest から導き、表分類資産から導かない**(design.md 1-5)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**本計画は PR A1 だけを扱う**(人間の判断 2026-09-24 で PR A を A1 / A2 に分けた。A1 と A2 を 1 本の計画書・1 本のブランチで扱うと、A1 のマージ後に進捗の導出が欠番になり、A1 単独の DoD も立たない — 10 周目 10-P1-1)。
**A1 のどのステップも、`backend/src` の DB 呼び出しの違反を増やさない**(迂回検査を `--base-ref origin/develop` で走らせて green)。

**ステップ 1 を始める前の外部の前提**(承認の後に済ませる — 12 周目 12-P2-1): ① PR A2・PR B・PR C・3-2 節の典拠の訂正の Notion タスクを起票し、ID を得る(ステップ 7 の `pending_switch` が PR B のタスク ID を使う)② **FR-014 の到達経路の所有単位を確定する**(ステップ 1 の `function_only` の所有単位の閉じた列挙に使う)。**U-G1 以外に決まったら、ステップ 1 の前に design.md の 1-4・1-6 と所有単位の列挙を改訂する**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **表分類資産 `table-classification.json`** と**露出の事実の資産 `exposure-facts.json`**(正本の文言を典拠に引く。事実は 7 種: 非テナント・制御資源・所有が混在する規則資源・管理者専用・認証前専用・移行専用・秘密の列)・割り当ての条件の検査(design.md 1-4・1-5) | **正例**: 1-4 の 45 表の割り当てが全条件を満たす。母集合は `Base.metadata` と manifest の両方から導き、両者の一致も検査。**露出の事実の典拠の引用がすべて正本 `data-model.md` に一字一句存在する**。事実の表と列が manifest に実在する。**変異で red**(design.md 1-5-c): `admin_credentials → global_read_only` / `tenant_credentials → tenant_owned` / `analysis_groups → tenant_owned` / `admin_operation_logs → effective_group_control` / `migration_quarantine → global_read_only` / `rate_limit_counters → global_read_only` / **`rule_sets → global_read_only`** / **`tournament_rule_assignments → tenant_owned`**(露出の事実「所有が混在する規則資源」で拒否 — 7 周目 7-P0-2)/ 未割り当て / モデルの追加 / `access_path.reason` を消す / 典拠の引用を正本に無い文言に書き換える / 露出の事実から `password_hash` を消し同時に `admin_credentials` を `global_read_only` にする / **`admin_operation_logs → tenant_owned`・`admin_operation_logs → global_read_only`**(「管理者専用」)/ **`tenant_auth_subjects → tenant_owned`**(「認証前専用」)/ **件数を保つ入れ替え**(露出の事実の無い表を `function_only` にする — 11 周目 11-P0-1)|
| 2 | **capability カタログ `capability-catalog.json`** の導出(design.md 10 節)。**ステップ 1 の表分類を入力にする**(1 → 2) | カタログが表分類から生成器で導出され、導出結果と一致(手書きの変更で red)。`direct` の表だけが載り、`effective_group_control` と `function_only` は 0 件。**capability ID と `(表 ID, 操作種別)` が 1 対 1**(ID の重複・同じ組への 2 つの ID で red)。**1 つの capability は 1 つの表の 1 つの操作だけを表す** |
| 3 | **capability の登録の検査**(design.md 10 節)。登録の集合そのものは空のまま | 登録された operation token の文(`statement`)を解析し、**文が参照する表の集合(FROM・JOIN・サブクエリのすべて)が、ID に結び付いた 1 つの表とちょうど一致**し、コマンドが ID の操作種別と一致することを確かめる。**変異で red**: カタログに無い ID を登録する / 正しい ID を別の表の文に付け替える / 別の操作に付け替える / **正しい主表に、宣言していない表の JOIN を足す** / **宣言していない表を参照するサブクエリを足す** / ID を重複させる / **正しい表の文に、ユーザー定義のスカラー関数の呼び出しを足す** / **表を返すユーザー定義関数を足す**(`pg_catalog` の組み込み関数だけを許す — 11 周目 11-P1-2)/ **`literal_column('authz_private.evil()')` などの不透明な SQL 断片を足す** / **参照されない INSERT・UPDATE・DELETE の CTE を足す**(許す SQLAlchemy のノードの型は閉じた集合 — 12 周目 12-P1-2)(試験の中だけで仮に登録する — 製品のパッケージには収載しない)。`backend/src/pitchlog/repositories/repository_contract.py:57-59` の 3 集合が空のまま。**変える既存ファイルは無い**(検査は新しい試験と、`backend/src` の外の検査モジュールに置く。`backend/src` に置く場合も DB 呼び出しは持たない) |
| 4 | **資産指定オブジェクト `AuthzAssetSpec` と `PROBE_SPEC`**(`backend/src/pitchlog/authz/asset_spec.py` を新設)。生成器 `ddl.py` と body 検査器 `scripts/check_authz_function_bodies.py` が spec を受け取る。既定は `PROBE_SPEC` | 変える既存ファイルは `ddl.py` と `check_authz_function_bodies.py` だけ。`backend` と `harness` の pytest がすべて green。`ddl.py` の AST 検査(`backend/tests/test_authz_ddl.py:181`)が green のまま。**spec の取り違えで red**: probe 以外の scope 値を `PROBE_SPEC` で読むと拒否。probe 資産の差分 0 行 |
| 5 | **適用器・DB カタログ検査・DB fixture を spec 対応にする**(`provisioning.py` / `catalog.py` / `backend/tests/db_fixtures.py`)。操作種別の閉じた集合を spec ごとに持つ | 変える既存ファイルは上の 3 つだけ(`backend/tests/db/conftest.py` は変えない — 製品の fixture と再エクスポートは PR A2 で足す — 10 周目 10-P1-3)。**迂回検査が green**(`backend/src` の DB 呼び出しの違反が増えていない)。既存の DB 試験がすべて green。**操作種別の集合が spec ごとに閉じている**(試験の中で組み立てた、probe ではない試験用の spec で確かめる。本物の `PRODUCT_SPEC` での双方向の負例は `PRODUCT_SPEC` を作るステップで置く — 8 周目 8-P1-3)。`requires_db` の収集件数が減っていない |
| 6 | **静的検査 `scripts/check_authz_catalog.py` の scope 検査を spec 対応にする**。probe 固有の閉じた検査は probe spec のときだけ走らせる | 変える既存ファイルは `check_authz_catalog.py` だけ。既存の `tests/test_check_authz_*.py` が差分 0 行で green。**試験用の非 probe spec で probe 資産を読むと拒否・probe spec で非 probe の scope の資産を読むと拒否**(本物の `PRODUCT_SPEC` での負例は後のステップ)。**既定の呼び出しと、`PROBE_SPEC` を明示した呼び出しの出力が byte 一致**する。**既存の回帰試験の観測範囲を維持する**(差分 0 行の既存試験が green)。**spec で分岐させた probe 固有の検査の一覧**を持ち、**各分岐を誤って無効にする変異で red**(8 周目 8-P2-1)。新しい凍結基準は置かない |
| 7 | **`PRODUCT_SPEC` と、未発効の第三状態**: `ddl-elements.staged.json` の骨組み(scope・`pending_switch`)と、新設の試験 `backend/tests/test_authz_product_staging.py`(design.md 3-2) | **この時点の未発効状態の検査は、状態・パス・`pending_switch` だけを見る**(保護対象の exact-set はステップ 13 — 12 周目 12-P1-1)。**本物の `PRODUCT_SPEC` での双方向の負例**(製品資産を `PROBE_SPEC` で読むと拒否・probe 資産を `PRODUCT_SPEC` で読むと拒否 — 8 周目 8-P1-3)。未発効状態の検査が green(最終パス `ddl-elements.json` が無い / ランタイムは暫定のまま / `pending_switch` がタスク ID を持つ)。**staged と最終パスが両方あると red**。既存の `test_authz_runtime_contract.py` の差分 0 行 |
| 8 | **製品 DDL 資産(1)ロールと membership の宣言**: ロール 3 種の作成・**全製品ロールの 7 属性の肯否**(design.md 2-0)・**恒久の特権主体の許可集合の製品固定部分**(`pitchlog_owner`)・**製品ロールに接する辺 0 本の宣言**(design.md 2・2-2) | `PRODUCT_SPEC` で生成器・body 検査器・静的検査が green(`PRODUCT_SPEC` の manifest は要素とパスの対応表で、凍結しない — design.md 3-2-a)。**変異で red**: `pitchlog_app` に `BYPASSRLS` を足す / 関数所有ロールに `LOGIN` を足す / 宣言から属性を 1 つ消す / 製品ロールへの辺を宣言に足す。資産に `password` と接続文字列が 0 件 |
| 9 | **製品 DDL 資産(2)DB とスキーマの所有と ACL**: DB・`public`・`authz_private` の期待集合(design.md 2-1 の表)。`PUBLIC` の DB の `CONNECT`・`TEMPORARY` と `public` の `USAGE`・`CREATE` の剥奪 | 静的検査が green(`PRODUCT_SPEC` の manifest は要素とパスの対応表で、凍結しない — design.md 3-2-a)。**変異で red**: DB に `PUBLIC` の `CONNECT` を戻す / `pitchlog_app` に DB の `CREATE` か `TEMPORARY` を与える / `public` に `PUBLIC` の `USAGE` を戻す / `public` の `CREATE` の剥奪を消す / `authz_private` に `CREATE` を与える / **`pitchlog_app` に `authz_private` の `USAGE` を与える**(何も与えないのが正 — 8 周目 8-P1-1) |
| 10 | **製品 DDL 資産(3)全 45 表の `ENABLE` + `FORCE`** | 静的検査が green(`PRODUCT_SPEC` の manifest は要素とパスの対応表で、凍結しない — design.md 3-2-a)。表分類と一致(45 表すべて)。**変異で red**: 1 表の `FORCE` を外す / 1 表の `ENABLE` を外す |
| 11 | **製品 DDL 資産(4)表のポリシーと表 ACL・列 ACL**: `tenant_owned` 23 表・`self_tenant_row`・`global_read_only` のポリシー(述語は 1 要素から展開し、展開結果を固定)・表 ACL(**制御資源 4 表にはアプリ用ロールの権限を与えない**) | **作成済みの 3 プロファイル(`tenant_owned`・`self_tenant_row`・`global_read_only`)について**、表分類と DDL の一致を静的に検査(プロファイルごとのポリシーの有無・ACL・コマンド・roles・`USING`・`WITH CHECK` の exact-set。**プロファイルから DDL への対応は、プロファイルの定義〔design.md 1-1〕から導く**)。**全 5 プロファイルの exact-set はステップ 13 で初めて要求する**(6 周目 6-P1-4)。**変異で red**: ポリシーを 1 本消す / `WITH CHECK` を消す / `DELETE` を足す / `function_only` の表に ACL を足す / `::UUID` を `::BIGINT` に変える / 展開結果を手で書き換える(digest 不一致)/ **制御資源 4 表のどれかに `pitchlog_app` の `SELECT` を与える** / 露出の事実で秘密とされた列に、どれか 1 つでもアプリ用ロールの `SELECT` を与える |
| 12 | **製品 DDL 資産(5)トリガ関数 33 個の `PUBLIC` 剥奪**(design.md 3-4) | 静的検査が green(`PRODUCT_SPEC` の manifest は要素とパスの対応表で、凍結しない — design.md 3-2-a)。33 個が関数 ACL の exact-set に入っている。**変異で red**: 1 個の剥奪を消す |
| 13 | **製品 DDL 資産(6)制御資源の補助関数とポリシー**(design.md 1-3): `authz_private.tenant_has_effective_membership`・4 表のポリシー・関数 ACL・**所有者の `{表, 列, 権限}` の exact-set** | 静的検査が green。**staged 資産から導いた保護対象が、暫定資産の保護対象 ∪ 宣言済みの追加分と exact-set**(未発効状態の検査の完成 — 12 周目 12-P1-1)。**`PRODUCT_SPEC` の manifest・body ファイル・DDL 要素資産の 3 者が exact-set で対応し、manifest に `source_commit` が無い**(design.md 3-2-a)(`PRODUCT_SPEC` の manifest は要素とパスの対応表で、凍結しない — design.md 3-2-a)。**全 5 プロファイルについて、表分類と DDL の exact-set が成り立つ**(ここで初めて要求する)。**関数の属性が exact**: `SECURITY DEFINER` / `STABLE` / 所有者 `pitchlog_shared_fn_owner` / `search_path` の末尾に `pg_temp` / 本文の表参照がすべてスキーマ修飾 / `PUBLIC` からの剥奪が作成と同じトランザクション / **`pitchlog_app` に `EXECUTE` を与えない**。**変異で red**: `pg_temp` の明示を外す / `PUBLIC` に `EXECUTE` を与える / `pitchlog_app` に `EXECUTE` を与える / 「実効グループ」「参加テナントが有効」「`admin`」の条件を 1 つずつ外す / 所有者に表単位の `SELECT` を与える・使わない列を 1 つ足す・必要な列を 1 つ欠く |

**ステップの順序と並行性**:

- **ステップは番号順にコミットする**(進捗の導出が `1..最大値` の欠番を不整合とするため — 11 周目 11-P1-3)。**帯 2 へ早く渡す表分類 → capability カタログ → 登録の検査を、ステップ 1〜3 に置いた**(spec を使わないので、spec の汎化〔4〜6〕より先にできる)
- 7 → 8 → … → 13 は順に依存する(7 は 1〜6 の後)
- **TSK-431 とは衝突しない**(`scripts/check_tenant_boundary_bypass.py`・`contracts/tenant_boundary/*`・`.github/workflows/`・`tests/test_ci_wiring.py` に触れない)
- **U-T1 の後続単位との衝突面**は `contracts/authz/product/`

**正本の追随**(3 節)は、ステップ 13 の後に /sync-docs で行い、PR A1 に含める(Claude が書く。委任しない — 設計書 7.6-2)。

### PR A2 へ引き渡す内容(別タスク・別ブランチ・別計画書 — TSK-431 の 7C の後)

PR A2 の計画書は、本計画の承認後に起票するタスクで作る。**設計の正は本 feature の [design.md](./design.md)** とし、A2 の計画書はそれを参照する。A2 のステップは 1 から採番し直す。
A2 に入るのは次の内容で、本計画の旧版(コミット 96d4132 の plan.md)のステップ 13〜21 の合格条件を出発点にする:

- **旧 13**: **(PR A2 の先頭 — TSK-431 の 7C の後)製品の適用器と、使い捨てクラスタでの適用の fixture**(design.md 2-3・4-1・4-2): 外部の適用主体(superuser)が `pitchlog_owner` と DB を用意 → `alembic upgrade head`(`pitchlog_owner`)→ 製品 DDL を **1 トランザクション・固定の 7 手順**(補助関数をポリシーより先に作る — 7 周目 7-P0-3)で適用。fixture `provisioned_product_catalog` を新設(**`pitchlog_owner` を 7 属性どおりに作ってから適用前のカタログを記録する** — 8 周目 8-P2-2)。**再適用のたびに 7 属性を正規化する**
- **旧 14**: **カタログの exact-set 検査**(design.md 2-2・3-4・6-3 の危険終点)
- **旧 15**: **適用の原子性と故障系**(design.md 4-2)
- **旧 16**: **再適用と往復**(design.md 4-3)
- **旧 17**: **実 DB 試験(1)`tenant_owned` 23 表**(design.md 6-1)。試験は manifest の事実からパラメタ化して生成する(分類資産から期待値を導かない)
- **旧 18**: **実 DB 試験(2)その他のプロファイル**(design.md 6-2)
- **旧 19**: **実 DB 試験(3)横断の観点**(design.md 6-3)
- **旧 20**: **移行バッチ用ロールの資産 `migration-batch-role.json`**(書き込み先と有効な間の形)と、**有効な間の形の試験**・**定常の不変条件**(design.md 8-1〜8-3)
- **旧 21**: **probe ↔ 製品の写像資産 `probe-product-map.json`** と、その検査(design.md 7 節)

**A2 で追加で固定すること**: ステップを分ける(適用器 / fixture と `allowed_symbols` の追加は別のステップ。ただし `allowed_symbols` の追加と、それが許す DB 呼び出しは同じ PR に入れる — 10 周目 10-P2-1)。`base-allowlist.json` の `allowed_symbols` への追加は、TSK-431 が直した 7C の形式で 7.7-2 の記録を残す。

## 5. DoD(受け入れ基準)

**PR A1 の DoD**。TSK-424 カードの DoD は、A1・A2・B・C に分けて ★1〜★10 に合わせて書き換える(**承認後に Notion を同期する**)。

- [ ] **全 45 表に物理プロファイルが排他で割り当てられ、未割り当てが 0 件**(母集合は `Base.metadata` から導出。割り当ては明示メタデータ。**全表が、露出の事実と manifest で判定する割り当て条件を満たす**)。**プロファイルは 5 種で確定**し、カードが求めた「親表経由」「認証前グローバル可変」は `function_only` の到達経路の理由として記録した(★5)
- [ ] **露出の事実の典拠がすべて正本に実在する**。残余リスク(★10)と逐行確認の観点を PR 本文に書いた
- [ ] **capability カタログが表分類から導出されている**。ID と `(表, 操作)` が 1 対 1。登録の集合は空のままで、カタログに無い ID・別の表や別の操作への付け替え・宣言していない表の JOIN やサブクエリは red になる
- [ ] **製品 DDL 資産(staged)が静的検査で確定している**(SQL 本体は凍結しない。manifest は要素とパスの対応表 — design.md 3-2-a): 全表が `ENABLE` + `FORCE`・全 5 プロファイルで `{プロファイル, ACL, コマンド, roles, USING, WITH CHECK}` が exact-set・制御資源 4 表のポリシーと補助関数の属性・アプリ用ロールは制御資源に直接触れない・秘密の列はアプリ用ロールの `SELECT` の対象外・全製品ロールの 7 属性が肯否で固定・DB とスキーマの ACL が期待集合と exact-set・製品ロールに接する membership の辺が 0 本の宣言
- [ ] **PR A1 の段階が「未発効」の第三状態として検査されている**(staged と最終パスの二重は red)。`contracts/authz/product/ddl-elements.json`(最終パス)が無い
- [ ] **spec の汎化が既存の回帰試験の観測範囲を保ち**、spec の分岐を無効にする変異が red。本物の `PRODUCT_SPEC` での双方向の負例がある
- [ ] **迂回検査が green**(`backend/src` の DB 呼び出しの違反が増えていない)
- [ ] **12-8 節に、A1 の範囲だけを「確定・未発効」と書き、残件と所有者を記録した**(PR A2 / PR B / PR C の各タスク ID・U-A1 / U-A2 / U-C1〔`analysis_groups` の名称の列を含む〕/ U-C2〔制御情報の読み取りの制限関数〕/ U-C3 / FR-014 の到達経路の所有タスク ID / TSK-344 / TSK-349 / 3-2 節の典拠の訂正タスク)
- [ ] **FR-014 の到達経路(規則セットを読む・大会へ結ぶ関数)と `rule_sets` の帰属の列の所有を、実在する Notion タスク ID で確定した**(確定は単位分割の持ち主〔進行管理・PO〕へ依頼する)
- [ ] **PR A2・PR B・PR C・3-2 節の典拠の訂正の Notion タスクを起票し、ID を 12-8 に記録した**
- [ ] **申し送りを Notion と PR 本文に記録した**: TSK-349 の射程の書き換えと design.md 8-4 の要求事項(★1)/ FR-014 と `rule_sets` の帰属の列(design.md 1-6)/ U-C1 への `analysis_groups` の名称の列 / `event_slots` の食い違い(★3)/ TSK-344 への運用契約(design.md 4-3 の non-serving 区間・8-3 の定常の不変条件)/ TSK-250 への写像資産の正の所在
- [ ] **`contracts/authz/` 直下の probe 資産の差分 0 行**(`oracle-seal.lock.json` の封印を動かさない)
- [ ] **`backend/pyproject.toml` / `uv.lock` / `backend/tests/conftest.py` の差分 0 行**
- [ ] **PR に 12-4 の判定記録を残した**(「対象入口なし」)
- [ ] pytest / ruff / ty green(`backend` と `harness` の両方)
- [ ] **コア領域として敵対レビューと、人間の逐行確認(PR 作成者以外)を通した**

## 6. テスト計画

| NFR-019 の種別 | 足すもの(PR A1) | ステップ |
| --- | --- | --- |
| **単体** | 資産指定オブジェクトと spec の取り違え・spec の分岐の変異・表分類の割り当て条件と露出の事実(典拠の実在)・capability カタログと登録の検査(参照する表の集合)・未発効状態・ロール属性・DB とスキーマの ACL・DDL 資産と表分類の一致・補助関数の属性と所有者の列権限 | 1〜13 |
| **一致性** | 述語の展開結果と要素の digest・capability カタログと表分類の一致 | 2・11 |
| **越境**(NFR-019(b) の DB 層) | **PR A2**(実 DB 試験 — 最低要求 ①②③・`WITH CHECK`・`function_only` の `42501`・制御資源の正負行列) | — |
| **故障系** | **PR A2**(適用の原子性・`current_user`・不正 UUID) | — |
| **E2E** | **対象外**(入口を開かない。HTTP の越境テストは入口を開く単位が同じ PR に含める — ADR-004 D-2) | — |

- **各ステップの合格条件に、変異で red になることを入れた**(改変前の green を assert してから変異させる)
- 迂回検査(`scripts/check_tenant_boundary_bypass.py`)は CI の `tenant-boundary-bypass` ジョブで走る。**A1 の各ステップで、ローカルでも `--base-ref origin/develop` で green を確かめる**
