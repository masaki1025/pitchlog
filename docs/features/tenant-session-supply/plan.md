---
feature: tenant-session-supply
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-26・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e687817eb0caec8f93d11be5
branch: feature/tenant-session-supply
created: 2026-09-26
計画レビュー周回: 2        # 1 周目(否決・P0 3 / P1 6)と 2 周目(否決・P0 3 / P1 5 / P2 1)の反映を含む
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: TenantRepositoryBase._session を満たす Session の供給(TSK-444 / TSK-424 PR C)

## 1. 背景・目的

**Notion**: [TSK-444](https://app.notion.com/p/3e593b75e687817eb0caec8f93d11be5)(優先度 **高**)
**計画段階の調査**: [research.md](research.md) / **詳細設計**: [design.md](design.md)

> **行番号の基準**: 断りのない限り **`origin/develop` = `b4ae7394`** 時点。確認は `git show b4ae7394:<path>`。

**DB を使う全単位が本タスクを待っている。** `backend/src` に `sessionmaker` / `Session(` は **0 件**で、
`TenantRepositoryBase._session` は抽象プロパティのまま満たす手段が公開されていない
(`backend/src/pitchlog/repositories/base.py:155-158`)。**製品コードに `TenantRepositoryBase` のサブクラスは 0 件**。

### 複数 operation を 1 トランザクションで回す必要は、正本が既に要求している

| 典拠 | 要求 |
| --- | --- |
| 要件書 `:303`(FR-012) | べき等キー記録・イベント保存・prefix 更新・状態遷移が**単一の DB トランザクションで確定する** |
| 要件書 `:391`(FR-018) | **紐づけ判定と削除が同一トランザクション**で行われる |
| `../../design/sync-protocol.md:1258-1264` | **P2 = T1・T2・T3・T4・T5・T6 の 6 要素**を 1 トランザクション |

現行は **1 呼び出し = 1 トランザクション**(`base.py:194` の `with _tenant_transaction(...)` が
`_execute_operation` の内側)なので、**どれも満たせない**。

### 【調査で覆った与件】禁止ではなく未実装だった

- `../tenant-boundary-enforcement/plan.md:173` ①「発行 SQL **列**の先頭が束縛文」— **列**と書いており件数の上限が無い
- `../tenant-boundary-enforcement/design.md:403`「**束縛より前に**他の SQL が出ないこと」— 制約は**前だけ**
- **既存の合格テストが 1 束縛 2 文を正例として固定**している
  (`backend/tests/test_authz_tenant_binding.py:1226`。テスト名は **`..._is_first_...`** であって `is_only` ではない)

## 2. スコープ

### やること

1. **トランザクション単位を製品コードへ置く** — `tenant_transaction_scope(context)` と `TenantTransaction.run(token)`
   ([design.md](design.md) 3-1)。**Session の生成・束縛・commit/rollback・close をこの単位が所有する**
2. **前段の結果を見て後段を中止できる形**にする([design.md](design.md) 3-5)
3. **`allowed_symbols`(凍結基準)への追加**を 7.7-2 に適合する v2 形式で記録する
4. **`repository-contract.json` の `public_surface`** の変更を反映する

### やらないこと

| 項目 | 行き先・理由 |
| --- | --- |
| **FR-018 の並行性**(「判定後に紐づいた場合は失敗する」を成立させる機構) | **射程外。単位を跨ぐ設計判断として別に扱う**(**1 周目 P0-1 の是正** — 詳細は [design.md](design.md) 5 節)。**`SERIALIZABLE` でも `FOR UPDATE` でも成立しない**。成立には**紐づけを作る側、または DB の制約 / trigger が、選手の非表示状態を検証して拒否する**ことが要る(**2 周目 P1-1 の是正** — 手段は読み取りに限らない)。**対象は `players` を参照する全列**に及ぶ。**受け取り先は TSK-459**(7-1) |
| **分離レベル・再試行の方針** | **射程外**(上の帰結)。制約は [design.md](design.md) 6 節へ申し送る |
| **`Session` を返す関数を作ること** | **作らない**(**2 周目 P0-2 の是正**)。`return Session(engine)` だけの関数は**迂回検査に 1 件も引っかからない**(生の Session を戻り値で漏らす経路を検出する検査が無い)。**トランザクション単位が内部で生成し close する** |
| **`base.py` の変更** | **1 行も触らない**(**2 周目 P0-1 の是正** — [design.md](design.md) 3-4)。公開面 exact-set と変異テストの literal アンカーが動かない |
| **FR-018 / FR-039 / FR-017 の述語 SQL と入口** | **U-M1(TSK-393)**。FR-015/017/018/039 の主所有は U-M1(`../product-impl-unit-split/design.md:75`) |
| **capability の登録**(`PRODUCT_CAPABILITY_IDS` を空でなくする) | **経路を持つ単位**(`../product-authz-surface/plan.md:42` ★7)。本タスクは空のまま残す |
| **`insert` / `update` の operation token の登録形式** | **登録する単位が registry と一緒に定める**(`../product-authz-surface/design.md:618`) |
| **`db-api-inventory.json` の変更** | **触らない**(4-1 の裁定 7)。使う API を既存 ID の範囲に収める |
| **`TenantContext` の生成を製品モジュールへ開くこと** | **U-A1(TSK-217)**。`allowed_product_modules` は `[]` のまま |
| **一覧経路・ページング** | **U-01 の所有**(`../tenant-boundary-enforcement/plan.md:174`) |
| **同期プロトコルの T1〜T9 境界の実装** | **同期側**。本タスクは「6 要素を載せられる機構」までで、経路ごとの境界は決めない |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/` | **反映なし**。本タスクは FR を実装しない | — |
| `docs/design/data-model.md` | **反映なし**。3-3 節の規律(`:318-327`)を**守る側**であり変えない | — |
| `docs/design/sync-protocol.md` | **反映なし** | — |
| `docs/adr/` | **新設なし**。既決の制約の実装であり新しい決定を持たない | — |
| **`contracts/tenant_boundary/repository-contract.json`** | `public_surface` へ **`transaction_scope_entry`(`pitchlog.repositories.transaction.tenant_transaction_scope`)のみ**を追加。`contract_revision` **`5` → `6`**・`source_digest` 更新 | **コア領域**(`tenant-isolation`)→ 敵対レビュー + 人間の逐行確認 |
| **`contracts/tenant_boundary/base-allowlist.json`** | `allowed_symbols` へ **`pitchlog.repositories.transaction._TenantTransaction.run`** を追加。`contract_revision` **`16` → `17`**。**v2 履歴を 1 件追記**(**4 件目** — 7 資産の単一検査の authority) | **凍結基準**(7.7)+ 同上 |
| **`contracts/tenant_boundary/history-snapshots/`** | v2 記録の content-addressed snapshot を追加(追記専用) | 同上 |
| `contracts/tenant_boundary/db-api-inventory.json` | **反映なし**(4-1 の裁定 7 — 触らない) | — |
| **`docs/development/harness-evaluation.md`** | **`## 候補` へ追記**: 既存候補「並行ブランチが CI 契約に規則を足すと、先行して設計済みのブランチが後から抵触する」へ **2 例目**(append-only 台帳の prefix が動く型)+ **新設 1 件**(マージ後に必ず赤になるテストの是正タスクは、同型のうち「新シンボルを足すブランチだけで出る」ものを自分の CI で踏めない)。**変更履歴表に 1 行追記**。**`H-*` の採番なし・版は上げない**(7.6-3 前段) | PR レビュー(7.6-3 前段) |
| `docs/README.md` | **台帳行の最終更新日を現行化**(正本の新設・版繰り上げは無い) | PR レビュー |

**正本体系外だが同一 PR で更新するもの**: `docs/features/tenant-session-supply/verification-sheet.md`(**新設** — 設計書 6.3 の逐行確認を支援する機械生成シート)・`backend/src/pitchlog/repositories/transaction.py`(新設)・`repository_contract.py`(生成モジュール)・`tests/fixtures/tenant_boundary/positive/*`・`backend/tests/*`。

**実装で動いた宣言(2026-09-26 の追随)**:

- **版数**: 着手時は `repository-contract` `4` → `5`・`base-allowlist` `15` → `16` と書いていた。**作業中に TSK-440(PR #80)が develop へ入り両方を 1 つずつ上げた**ため、実際は **`5` → `6`・`16` → `17`** になった。履歴も **3 件目まで進んでいた**ので、本 PR の受理記録は **4 件目**である
- **許可シンボル**: 着手時は `tenant_transaction_scope` と書いていた。**誤り**。迂回検査は **DB 呼び出しを囲む関数**と突き合わせ、`Session.execute` は `TenantTransaction.run`(`transaction.py:52`)の中にある。`tenant_transaction_scope` は DB API を直接呼ばないので登録不要。**承認も訂正コメント(`5844686316`)で取り直している**
- **`tests/test_check_tenant_boundary_bypass.py`**: 着手時は更新対象に挙げていたが、**1 バイトも変えていない**(`public_methods` は `TenantRepositoryBase` しか見ないため、新モジュールを足しても検査器側の変更が要らなかった)

**実装後の敵対レビューで動いた 2 点(2026-09-26 の追随)**:

- **許可シンボルが `_TenantTransaction.run` へ** — 敵対レビュー **P0-1**(公開コンストラクタから
  束縛を迂回できる)を受けて**ハンドルを非公開化**したため。**署名と `allowed_api_ids` は不変**。
  **承認を 3 通目(`5846446071`・`2026-09-26T12:56:08Z`)で取り直している**
- **`public_surface` から `transaction_handle_type` を落とした** — **非公開型を「公開面」に
  宣言するのは意味の取り違え**になるため。ハンドル型は `allowed_symbols` 側が固定する

**版数は据え置き**(`17` / `6`)。**develop 側は `16` / `5`** で、本 PR 内で内容を書き直しただけ
なので**正味の移動は変わらない**。**履歴は 4 件目を書き直した**(5 件目を足していない)。

## 4. 実装方針

**重さ分類 = コア領域**。`backend/src/pitchlog/repositories/*` と `contracts/tenant_boundary/*` は
`tenant-isolation` のコア paths。**敵対レビュー + 人間の逐行確認が必須**(設計書 6.3)。
加えて **`base-allowlist.json` は凍結基準**なので 7.7 の更新経路に載る。

**詳細な API 形・束縛ライフサイクル・U-M1 への受け渡し契約は [design.md](design.md)。**

### 4-1. 本タスクで決めること(裁定)

| # | 事項 | 決定 | 根拠 |
| --- | --- | --- | --- |
| **1** | **FR-018 の述語 SQL と入口を誰が決めるか** | **機構は本タスク / 述語 SQL と入口は U-M1**。受け渡し契約は [design.md](design.md) 4 節に 7 項目で固定する | `data-model.md:2033`「具体的なロック方式・SQL は実装計画へ送る」の**委譲先が正本に無い**。FR-018 の主所有は U-M1(`../product-impl-unit-split/design.md:75`) |
| **2** | **複数 operation の束ね方** | **1 Session = 1 トランザクション = 1 束縛 = N operation**。**前段の結果を見て後段を中止できる形**にする | `binding.py:60-61` がキーの存在だけで再束縛を拒否し、**印を消すコードが無い**(実測)。token の列を一度に渡す形は**前段の結果を使えない**ので却下([design.md](design.md) 3-2) |
| **3** | ~~FR-018 の並行性~~ | **【1 周目 P0-1 で撤回】射程外へ送る** | 初稿は `data-model.md:1760` の二択を採ったが、**あれは 9-1 節(FR-041)の裁定**で FR-018(11-1 節)のものではなかった。かつ **`SERIALIZABLE` でも `FOR UPDATE` でも成立しない**([design.md](design.md) 5 節) |
| **4** | **「1 operation = 1 表」** | **緩めない** | `capability_registration.py:1256-1257` が exact-set 比較。**1 トランザクションあたりの operation 数への制約は条文に無い**→ 本タスクと直交 |
| **5** | **分離レベル・再試行** | **射程外**。ただし**後から入れられる形**にする(供給を factory に) | 裁定 3 の撤回に伴い、本タスクに要求する根拠が無くなった。制約は [design.md](design.md) 6 節に申し送る |
| **6** | **savepoint / `begin_nested`** | **使わない** | **言及なし**(`db-api-inventory.json:883` に API 登録があるだけ) |
| **7** | **`db-api-inventory.json`** | **触らない**。使う API を既存 ID(`SQLA_SESSION_BEGIN` / `SQLA_SESSION_CONNECTION` / `SQLA_SESSION_EXECUTE` / `SQLA_TEXT`)に収める | 触ると `inventory_revision` の繰り上げ・`baseline_control.identity.current_identifiers` の同期・v2 記録への旧新識別値の収録・snapshot への収録・allowlist の `inventory.sha256` 更新が連鎖する(**1 周目 P1-3**)。**避けられる複雑さを持ち込まない** |

### 4-2. 検査の実行順(ステップ設計の前提 — **1 周目 P1-2 の是正**)

`scripts/check_tenant_boundary_bypass.py:4105` の `check_repository` は
**`_validate_repository_histories`(`:4137`)を先に呼び、そのあとでソース走査へ進む**。

→ **「迂回検査 green / 凍結履歴 red」という状態は作れない。** 履歴が red ならソース走査へ到達しない。
→ **7 資産は単一検査で `base-allowlist.json` が authority**、かつ**同一受理で 2 件追記は red**
(`../tenant-boundary-baseline/plan.md:115`)なので、**資産の変更と履歴の追記は 1 ステップに収める**。

### 4-3. 【2 周目で解消】変異テストの literal アンカーは壊れない

`tests/test_check_tenant_boundary_bypass.py:644-652` は **`backend/src` の実ソースを文字列置換**して変異を作り、
`"            execution_result = self._session.execute(\n"` などをアンカーにしている。

**本タスクは `base.py` を 1 行も変更しない**([design.md](design.md) 3-4)ので、**アンカーは壊れない**。
初稿は `base.py` の `_execute_operation` を書き換える前提だったため、
「ステップ 4 と同じコミットでアンカーを更新する」としていた。**その必要が無くなった。**

### 4-4. 生成モジュールの更新順序(**1 周目 P1-4 の是正**)

`repository_contract.py` は「生成モジュール」と自称する(`:1`)が、**生成スクリプトはリポジトリに存在しない**(実測)。
**手で同期するしかない**ので、順序を固定する:

1. **`repository-contract.json` を正として先に編集する**
2. **canonical digest を算出**して `source_digest` へ入れる(`canonicalization: json-sort-keys-utf8-v1`)
3. **`repository_contract.py` へ逐語転記**する
4. `backend/tests/test_authz_repository_contract.py:223-230` の一致テストで確認する

### 4-5. 承認記録の出所を着手前に決める

**TSK-446 では承認記録の出所が取れず、敵対レビューが 3 周連続で P0 を出した。**
今回は **TSK-431 の 7C(PR #78・マージ済み)が機械強制**している:

```
scripts/frozen_history.py:39-41   予約 marker を拒否 {"PENDING","TODO","TBD","未承認","未定","レビュー待ち"}
scripts/frozen_history.py:1521    approved_by は非空・approved_on は実在する ISO 日付
```

**プレースホルダは書けない。** よって**ステップ 1 で出所を確定**し、worklog へ記録してから実装に入る。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**各ステップの合格判定は「全件実行」で行う**(TSK-446 の 2 周目の教訓 — 絞り込み実行では 34 本の red を見落とした)。
**総数が変わりうるためステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **draft PR を開いて番号を確定し、承認記録の出所を worklog へ記録する**(**承認後の追記 — 2026-09-26**。凍結基準の v2 記録は `acceptance_id` = `<repo>#<PR番号>`〔`base-allowlist.json:72` の実例〕を要求するので、**番号がステップ 4 より前に確定している必要がある**。承認コメントの投稿先も同じ PR) | PR 番号が確定し**本計画書に記録**されている。worklog に**人間の裁定(7-2)が逐語で**残り、`frozen_history.py:39-41` の予約 marker に当たらない |
| 2 | **負例テストを先に置く** — ① 束縛が先頭でない ② **`TenantContext` を混ぜる口が無いこと**(`run` の署名が token だけ — **2 周目 P0-1 の是正**。「混在を試す」負例は公開 API では構成できないので、**構成できないことを固定する**)③ 未登録・偽造 token ④ 中止の例外で `ROLLBACK` が発行されない・`Session` が close されない(**書き込みは使わない** — 現行 registry は `Select` だけを扱い、`insert`/`update` の登録形式は射程外) ⑤ 戻り値に `Result` / ORM instance が混ざった ⑥ **close されない** | **6 種すべてが red**。red の出力を worklog へ**実出力つきで**残す |
| 3 | **トランザクション単位を追加する** — `backend/src/pitchlog/repositories/transaction.py`(新設)。**Session の生成・束縛・commit/rollback・close を所有する** | ステップ 2 の 6 種が **green**。**期待失敗**: `allowed_symbols` 未登録による **TB005**(**`session.begin()` と `.execute()` を呼ぶため** — **2 周目 P1-2 の是正**。初稿は「factory 未登録で TB005」と書いたが、**純粋に `Session` を返すだけなら違反 0 件**だった)。~~`repository-contract.json` 未更新による契約テストの red~~ — **実測で外れた**(**ステップ 3 の差し戻しで判明**)。`public_methods` は `TenantRepositoryBase` しか見ないので、**新モジュールを足しても契約テストは動かない** |
| 4 | **契約資産・生成モジュール・契約テスト・正例 fixture・凍結履歴を 1 コミットで更新する**(4-2 — 分離できない) — `repository-contract.json` → digest → `repository_contract.py`(4-4 の順序)、**`test_authz_repository_contract.py:158` の `_generated_snapshot()` の固定辞書**(**2 周目 P1-3 の是正**)、`base-allowlist.json` の `allowed_symbols` + `contract_revision`、`tests/fixtures/tenant_boundary/positive/`、**v2 履歴を 1 件**(承認記録はステップ 1 の出所から逐語転記) | `scripts/check_tenant_boundary_bypass.py` が green。`scripts/frozen_history.py` の検査が green。**ここで初めて全件 green が成立しうる** |
| 5 | **故障系テストと欠落変異の確認を足す** — 6 節 | 全件実行で **red 0 件**。**各検査を無効化すると対応する負例が期待する red を失う** |

## 5. DoD(受け入れ基準)

### 5-1. 機械で判定する

- [ ] **`Session` を返す関数を 1 つも作っていない**(**2 周目 P0-2 の是正**)。生成・close は**トランザクション単位の内部**
- [ ] **トランザクション終了時に `Session` が close されている**(接続・identity map を解放する)
- [ ] **`base.py` の差分 0 行**([design.md](design.md) 3-4)
- [ ] **束縛済みのトランザクションの中で、複数の登録済み operation を実行できる**(**テスト専用 registry で検証** — **1 周目 P0-2 の是正**。製品 registry は空のままなので製品経路では検証できない)
- [ ] **前段の結果を見て後段を中止でき、中止するとロールバックされる**
- [ ] **業務トランザクションの発行 SQL 列の先頭が束縛文**である(SQL observer で観測)
- [ ] **公開メソッドが exact-set**。**生の `Session`・`Result`・ORM instance を返さない**
- [ ] **`capability_registration.py` を変更していない**(「1 operation = 1 表」を緩めていない)
- [ ] **`db-api-inventory.json` の差分 0 行**
- [ ] **`tenant-context-allowlist.json` の `allowed_product_modules` が `[]` のまま**
- [ ] **`PRODUCT_CAPABILITY_IDS` / `PRODUCT_OPERATION_TOKEN_TYPES` / `CROSS_TENANT_FUNCTIONS` が空のまま**
- [ ] `scripts/check_tenant_boundary_bypass.py` が green / `scripts/frozen_history.py` の検査が green
- [ ] pytest / ruff / ty green

### 5-2. 人間が確認し、証跡を残す

- [ ] **`allowed_symbols` の追加が 7.7-2 に適合している** — **承認記録の取得元を worklog に明記**し、**台帳へ逐語転記**した(**機械は非空・日付・予約 marker しか見ない** — 逐語一致は人間が確認する。**1 周目 P1-5 の是正**)
- [ ] **コア領域の逐行確認**(設計書 6.3)— **PR 本文の「実施記録: 対象= 範囲= 方法=」に記入**する
- [ ] **横断要求を破っていない** — **物理削除しない** — **`git diff` の字面ではなく**(**2 周目 P1-5 の是正** — `delete(...)` や `Session.delete(...)` を捕まえられない)、**`db-api-inventory.json` の `SQLA_SESSION_DELETE` を含む DB API ID が新シンボルの `allowed_api_ids` に入っていないこと**で確認する。**結果は PR 本文の「実施記録」へ書く**/ テナント分離(上の機械判定で代替)/ 自動エスケープ(本タスクは出力経路を持たない)

## 6. テスト計画

**DB を使う**。`backend/tests/db/` 配下は `requires_db` マーカー付き。

> **NFR-019 の種別は (a) 一致性 / (b) FR-034 越境アクセス / (c) 主要 E2E / (d) 同期プロトコル故障系**
> (要件書 `:923-933`)。**本 PR は製品経路を開かないので (b) は発効しない**(**1 周目 P1-6 の是正** —
> 初稿は束縛先頭性や迂回検査を (b) に分類していたが誤り)。

| 対象 | 種別 | 確認すること |
| --- | --- | --- |
| 束縛の先頭性 | **単体**(NFR-019 外の機構試験) | 複数 operation を回しても**発行 SQL 列の先頭が束縛文**(SQL observer で観測) |
| 複数 operation の原子性 | **単体**(同上) | 2 件目で例外 → **1 件目もロールバック**。commit 後に GUC が空文字 |
| 文脈の混在 | **単体**(同上) | 同一トランザクションへ**異なる `TenantContext`** を混ぜると `TenantBindingError` |
| 未登録・偽造 token | **単体**(同上) | `_operation_spec()` の既存経路で拒否される |
| 戻り値 | **単体** | `Result` / ORM instance / 遅延 generator を返さない |
| factory | **単体** | 呼ぶたびに別の `Session`。テナント横断・リクエスト横断で共有しない |
| 迂回検査 | **機構試験** | 新シンボルの**署名 exact 一致**。`allowed_api_ids` が最小 |
| 欠落変異 | **機構試験** | 各検査を無効化すると対応する負例が**期待する red を失う**。**検査器を変異させると台帳の sha256 検査が先に鳴る**ので、**台帳側も揃えてから実行する**(TSK-446 の申し送り) |

**実行手順**(`backend/` で。CI と同じ順):

```
docker compose up -d
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -c pyproject.toml --cov
```

**`--cov` は機械契約が `comparison: "exact"` で固定**(`backend/tests/db/environment-expectations.json:164-165`)。

ハーネス側(リポジトリルート)は `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/`。
**`ruff format` はハーネス側では走らせない**(AGENTS.md)。

## 7. 裁定(2026-09-26 に確定)

| # | 事項 | 決定 |
| --- | --- | --- |
| **1** | **FR-018 の並行性の受け取り先** | **TSK-459 として起票済み**(2026-09-26・着手可)。受け入れ条件は 7-1。本タスクのマージを待たずに並行できる |
| **2** | **凍結基準の承認記録の出所** | **PR コメントを出所とする**(7-2)。**方式は確定。投稿はステップ 4 の直前に人間が行う** |

### 7-1. 受け取り先タスクの受け入れ条件(#1)

**射程**: **`players` を参照する全列**について、**選手が非表示のときに紐づけを作れない**ことを保証する機構を決める。

- **対象列の全数**: `PlayRow.batter_id` / `pitcher_id` / `catcher_id`(**いずれも ForeignKey を持たない素の `Uuid` 列** —
  `backend/src/pitchlog/db/game_state/models.py:618`・`:633`・`:638`)、`play_runners` 系ほか。**全数の列挙から始める**
- **手段は読み取りに限らない** — 紐づけ生成側の検証 / DB 制約 / trigger のいずれでもよい
- **`SERIALIZABLE` でも `FOR UPDATE` でも成立しない**ことは[design.md](design.md) 5 節で論証済み。**再検討から始めない**
- **所有の候補**: 紐づけを作るのは**同期適用経路**。**U-M1 単独では閉じない**
- **DoD**: 「削除と同時に別端末がプレイを記録 / 削除確定 / **判定後に紐づいた場合は失敗する**」
  (要件書 `:391`)が、**実 DB の 2 接続で再現する試験**で確かめられること

### 7-2. 承認記録の出所(#2)— **方式を確定した**

**背景**: TSK-446 では出所が取れず**敵対レビューが 3 周連続で P0**。原因は
**PR の自己承認を GitHub が拒否する**こと(`Can not approve your own pull request`)で、
**単独メンテナの体制では `APPROVED` review を出所にする統制が原理的に成立しない**。

**確定した方式**: **本 PR へのコメントを出所とする。**
自分の PR にも書け、**`user.login`(認証済み発信者)と `created_at`(GitHub 側のタイムスタンプ)が機械可読**で、
本文に**氏名・日付・対象**を含められる。

**PR 番号**: **`masaki1025/pitchlog#82`**(ステップ 1 で確定・draft)。
凍結基準 v2 記録の `acceptance_id` はここから機械導出する
(導出式は `{repository.full_name}#{pull_request.number}` — `../tenant-boundary-baseline/plan.md:111`)。

**手順**(ステップ 4 の直前):

1. **人間が**本 PR へ次の形のコメントを投稿する:

```
凍結基準 base-allowlist.json の allowed_symbols へ
pitchlog.repositories.transaction.tenant_transaction_scope を追加することを承認する。
承認者: <氏名>。承認日: <YYYY-MM-DD>。
```

2. **当方が** `gh api repos/<owner>/<repo>/issues/<PR>/comments` から**逐語転記**し、
   `reason` に **API パスと comment id と `created_at`** を出所として書く

**推定値を 1 つも入れない。** 取得できなければ **7.7-3 の fail-closed に従い停止する**。

> **規律そのものの見直しは TSK-458 が扱う**が、**本タスクは待たずに個別に決められる**ため確定させた。
