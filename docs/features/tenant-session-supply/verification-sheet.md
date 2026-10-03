---
feature: tenant-session-supply
type: design
date: 2026-09-26
---

# 逐行確認シート: トランザクション単位の供給(TSK-444 / PR #82)

**機械生成**(`origin/develop...HEAD` の差分 + 契約資産 + AST 抽出)。**判定は人間が行う。**
コア領域(テナント分離)のため設計書 6.3 により逐行確認は必須で、**PR 作成者以外が実施する**。

**本 PR の性質**: **新しい公開経路を 1 本増やす案件**である。既存の防御は 1 行も変えていない。
したがって**「増えた入口が既存入口と同じ強さか」が、この確認の本題**である。

## 0. 見る順序

**この順序には理由がある。** 初版の PR 本文は「`base.py` / `binding.py` が無変更であること」を
**第 1 項**に置いていた。**差分ゼロは事実のまま、敵対レビューが P0 を 3 件出した** —
新しく足した経路が、その 2 ファイルの中の防御を**通らずに** DB へ届いていた。
**無変更の確認を先に置くと、確認者は「守られている」と読んでしまう。** よって最後に置く。

| 順 | 節 | 量 | なぜここを見るか |
| --- | --- | --- | --- |
| 1 | **A. 到達経路の対比** | 2 経路 × 5 検査 | **ここだけで PR の是非が決まる**。以下はすべてこの表の裏取り |
| 2 | **B. ハンドルから Session へ到達できないか** | 4 行 | P0-1 の核心。**改名は機構ではない** |
| 3 | **C. 失効** | 2 経路 | P0-2 の核心。**終了後に SQL が出ないか** |
| 4 | **E. 凍結基準の受理記録** | 承認 3 通 + 識別値 7 件 | 記録が事実か。**推定値が混じっていないか** |
| 5 | D / F | 表 | 落ちてはいけないものが落ちていないか |
| 6 | **G. 無変更の確認** | 6 ファイル | **最後に見る**(上記の理由) |

## 1. 機械が担保しない範囲(なぜ目視が要るか)

| # | 範囲 | 根拠 |
| --- | --- | --- |
| 1 | **`db-api-inventory.json` に `Session` の「構築」が登録されていない** | 登録は `Session.add` / `.execute` などメソッドだけ(当方が全 92 エントリを列挙して確認)。**葉が `Session(engine)` を作っても迂回検査に当たらない**。本 PR はハンドルに Session を渡せなくすることで塞いだが、**inventory の母集団が「呼び出し」に偏っている可能性は残る**。裁定 7 で inventory は射程外 |
| 2 | **公開面 exact-set は `_` 始まりを除外する** | 既存テストが `__init__` と `_session` を**構造的に見ていなかった**ことが P0-1 の検出を遅らせた。本 PR は除外しない走査を 1 本足したが、**「到達グラフ」の定義自体はテストが決める** |
| 3 | **凍結基準の受理は「射影が動いたこと」を検証するが、動いた中身の是非は見ない** | 7.7 の検査は識別値の連続性と履歴 1 件だけを見る。**`allowed_symbols` に足した対象が妥当かは人間の判断** |
| 4 | **承認コメントは編集・削除できる** | `reason` に comment id と `created_at` を記録しているが、**本文の content-addressed snapshot は取っていない**(敵対レビュー P2-9)。**後日 GitHub 側が変わると再検証できない** |
| 5 | **Engine・接続プールの所有と破棄が未決** | scope ごとに新しい Engine を作り dispose していない(敵対レビュー P1-7)。**別タスクへ起票済み**で本 PR の射程外 |
| 6 | **書き込み契約が未確定** | `run()` は `Select` 以外を拒否する。**registry へ `insert`/`update` が入る日には、この拒否ごと設計し直す必要がある** |

## 1-b. 機械が担保している範囲(欠落変異で実測)

**新設・変更した各検査について「テストがその検査を本当に見ているか」を変異で測った。**

| 変異 | 落ちたテスト | 実出力 |
| --- | --- | --- |
| 束縛 SQL を `yield` 後へ移動 | `:407` | 先頭が読み取り SQL になった |
| `run` に第 2 の `TenantContext` 引数 | `:572` | 引数列に `context` が増えた |
| 未登録 token を registry 先頭へフォールバック | `:660` | 既存拒否理由と不一致 |
| 例外情報を渡さず transaction を終了 | `:734` | `rollback` でなく `commit` を観測 |
| `CursorResult` を直接返却 | `:804` | 戻り値の exact 型検査 |
| `Session.close()` を削除 | `:919` | close 回数が `[0, 0]` |
| モジュール共有 `Session` を再利用 | `:1212` | 生成数が 1 のまま |
| 改竄済み文脈で scope 本体へ到達 | `:445` | `改竄済み文脈で scope 本体へ到達した` |
| `TenantContext` 派生型で scope 本体へ到達 | `:489` | `TenantContext 派生型で scope 本体へ到達した` |
| 束縛後の context 改変を許す | `:533` | `DID NOT RAISE TenantBindingError` |
| 契約から `TenantTransaction` を解決 | 契約テスト | `has no attribute 'TenantTransaction'` |
| 生成モジュールに古い定数を残す | 契約テスト | `Extra items in the left set: 'TRANSACTION_HANDLE_TYPE'` |

**検査器(`scripts/`)は変異させていない**ので、台帳 sha256 の更新実験は発生していない。

---

## A. 到達経路の対比 — **本題**

**判定基準**: 新しい入口が、既存入口と**同じ検査を同じ強さで**課しているか。

| # | 検査 | 既存: `TenantRepositoryBase.execute` | 新規: `tenant_transaction_scope` | 判定 |
| --- | --- | --- | --- | --- |
| A1 | **文脈の型** | `base.py:178` `type(context) is not TenantContext`(**exact**) | `transaction.py:145` `type(self._context) is not TenantContext`(**exact**) | ☐ |
| A2 | **発行証跡** | `base.py:180` `context._has_valid_integrity_proof()` | `transaction.py:147` 同左 | ☐ |
| A3 | **検査の時点** | SQL 発行前 | **`Session` 生成前**(`transaction.py:145-148` が `:155` の `Session(...)` より前) | ☐ |
| A4 | **例外型** | `TenantBindingError` | `TenantBindingError`(`transaction.py:146` `:148`) | ☐ |
| A5 | **束縛後の改変** | (単発実行なので発生しない) | `transaction.py:100` `:103` が **`run()` ごとに再照合** | ☐ |

**`binding.py:58` は `isinstance` しか見ない**(派生を許し、発行証跡を見ない)。
**差し戻し前は新経路がここを直接呼んでいたため、A1 と A2 の両方が抜けていた**(P0-3)。
**`binding.py` は 1 行も変えず、新経路の側に検査を足して揃えた**ことを確認する。

**☐ A6**: `transaction.py:145-148` の 2 つの検査が、**`Session` を作る行(`:155`)より前**にあること。
順序が逆なら、弾かれる入力でも接続が消費される。

---

## B. ハンドルから `Session` へ到達できないか(P0-1)

**改名は機構ではない。** `_TenantTransaction` という名前は規約にすぎず、
`__slots__` は属性を隠さず、`@final` は実行時の生成・継承を禁止しない。
**是正の実体は「ハンドルが `Session` を持つのをやめた」こと**である。

| # | 見るもの | 期待 | 判定 |
| --- | --- | --- | --- |
| B1 | `transaction.py:26` `__all__` | `('tenant_transaction_scope',)` **のみ**。ハンドル型が入っていない | ☐ |
| B2 | `transaction.py:37` `__slots__` | `('_state_key', '_context', '_bound_tenant_id', '_bound_integrity_proof')` — **`_session` が無い** | ☐ |
| B3 | `transaction.py:44` `__init__` | **`Session` を引数に取らない**。`creation_token` がモジュール私有センチネルと一致しなければ `:65` で例外 | ☐ |
| B4 | `transaction.py:115` `session.execute` | `session` は**引数でも属性でもなく、私有レジストリから `_state_key` で引いた値** | ☐ |

**☐ B5**: 私有レジストリ(`_TRANSACTION_RUNTIMES`)へ**書くのは scope だけ**で、
キーは scope が生成した `object()` であること。**葉が外から引ける経路が無い**こと。

**☐ B6**: `:598` `test_transaction_handle_is_not_publicly_constructible` と
`:633` `test_transaction_handle_does_not_expose_session` が、
**`_` 始まりを除外しない走査**で到達グラフを見ていること(既存 exact-set の穴を埋めた分)。

---

## C. 失効(P0-2)

**差し戻し前は、scope 終了後の `run()` が例外にならず、束縛文なしで SQL が通った**
(当方の実 DB プローブ: `NO_RAISE` / 束縛文の発行なし)。
`Session.close()` は**リセットであって使用不能化ではない**ため、新しいトランザクションが自動で始まる。

| # | 経路 | 見るもの | 判定 |
| --- | --- | --- | --- |
| C1 | **正常終了** | `transaction.py:187` `__exit__` が `handle._expire()` を呼び、レジストリから `pop` する | ☐ |
| C2 | **入口の失敗** | `transaction.py:137` `__enter__` の except 経路でも**同じく失効**させる | ☐ |
| C3 | **失効後の `run()`** | `transaction.py:94` `:98` で例外。**SQL を 1 件も発行しない** | ☐ |
| C4 | テスト | `:1085` `test_handle_cannot_run_after_scope_exit` / `:1125` `test_handle_is_invalidated_when_scope_entry_fails` | ☐ |

**☐ C5**: レジストリから `pop` しているので、**失効したハンドルの実行状態が残らない**こと。

---

## D. その他の防御(P1-4 / P1-5 / P1-6)

| # | 見るもの | 期待 | 判定 |
| --- | --- | --- | --- |
| D1 | `transaction.py:110` | `isinstance(spec.statement, Select)` で**`execute` の前に**拒否。`Select` は型注釈だけでは実行時の保証にならない | ☐ |
| D2 | `:697` `test_non_select_operation_is_rejected_before_execute` | **DML 発行数 0・行状態不変**を観測しているか | ☐ |
| D3 | `:970` `test_transaction_exit_precedes_close` | 観測列が **`["commit","close"]` / `["rollback","close"]`** と**順序つき**で固定されているか | ☐ |
| D4 | `:1038` `test_close_failure_preserves_primary_exception` | close が失敗しても**元例外が伝播**するか | ☐ |
| D5 | `tests/fixtures/.../transaction.py` | **実装と同じ呼び出し形**か(registry 解決と `_materialize_rows` を通るか) | ☐ |
| D6 | `:857` `test_run_rejects_attached_orm_value` | 定義されながら未使用だった `_orm_read_operation()` を**実際に registry へ登録**しているか | ☐ |

---

## E. 凍結基準の受理記録(7.7)

### E-1. 承認の出所 — **推定値が 1 つも無いこと**

**3 通取り直している。** 非公開化で許可シンボルのパスが変わり、2 通目が指す対象が消えたため。

| # | comment id | created_at | 対象 | 状態 |
| --- | --- | --- | --- | --- |
| 1 | `5844655199` | 2026-09-26T08:36:30Z | `tenant_transaction_scope` | 取り違え |
| 2 | `5844686316` | 2026-09-26T08:41:56Z | `TenantTransaction.run` | 非公開化で消滅 |
| 3 | **`5846446071`** | **2026-09-26T12:56:08Z** | **`_TenantTransaction.run`** | **有効** |

**☐ E1**: `history[3].approved_by` = `山田正輝` / `approved_on` = `2026-09-26` が
**3 通目の本文と逐語一致**すること(`gh api repos/masaki1025/pitchlog/issues/comments/5846446071`)。

**☐ E2**: `reason` に**3 通すべての id と `created_at`**、および
**それぞれが何を承認しなぜ差し替わったか**が書かれていること。

**☐ E3**: 予約 marker(`PENDING` / `TODO` / `TBD` / `未承認` / `未定` / `レビュー待ち`)が**無い**こと。

### E-2. 識別値と履歴

| 資産 | develop | HEAD | 判定 |
| --- | --- | --- | --- |
| `base-allowlist.json` | `contract_revision:16` | **`17`** | ☐ |
| `repository-contract.json` | `contract_revision:5` | **`6`** | ☐ |
| `cache-invalidation-contract.json` | `4` | `4`(据え置き) | ☐ |
| `db-api-inventory.json` | `inventory_revision:6` | `6`(据え置き) | ☐ |
| `negative-fixtures.json` | `fixture_set_revision:8` | `8`(据え置き) | ☐ |
| `runtime-authz-contract.json` | `runtime_contract_revision:4` | `4`(据え置き) | ☐ |
| `tenant-context-allowlist.json` | `contract_revision:7` | `7`(据え置き) | ☐ |

**☐ E4**: 履歴は **4 件**(`(v1)` / `#78` / `#80` / **`#82`**)。**5 件目を足していない**こと
(同一受理で 2 件追記は red)。

**☐ E5**: **既存 3 件が `origin/develop` と 1 文字も違わない**こと(機械照合では `True`)。

**☐ E6**: `history[3].previous_baseline_identifiers` == `history[2].new_baseline_identifiers`。

**☐ E7**: `change.aspect` = `['asset_snapshots', 'declaration']` が
**実差分から `derive_aspects` が導出する集合と exact-set 一致**すること。

**☐ E8**: snapshot は **2 件追加のみ**(`0afbcc…a046` / `3a9d39…f305`)。
**develop 由来の 55 件は削除・変更とも 0 件**(HEAD の総数 57 = 55 + 2)。

> **補足(履歴を書き直した経緯)**: 本 PR は一度 `TenantTransaction.run` で 4 件目を書き、
> 差し戻し後に**同じ 4 件目を書き直した**。5 件目を足していない。
> **4 件目は develop に存在しない我々のレコード**なので、書き直しても比較元の prefix は壊れない。
> **`contract_revision` を 17 / 6 のまま据え置いた**のも同じ理由で、
> **develop は 17 / 6 を一度も見ていない**(develop 側は 16 / 5)。**正味の移動は変わらない。**
> 最初に書いた snapshot 2 件は**削除**した(未マージなので孤児にしてよい)。

### E-3. 許可シンボル

**☐ E9**: `allowed_symbols` は **6 件**で、本 PR が足したのは**最後の 1 件だけ**:

| symbol | allowed_api_ids |
| --- | --- |
| `pitchlog.db.engine.create_database_engine` | `SQLA_CREATE_ENGINE` |
| `pitchlog.db.engine._verify_application_role_connection` | `PSYCOPG_*` 3 件 |
| `pitchlog.repositories.context.TenantContext.__init__` | (なし) |
| `pitchlog.repositories.binding._tenant_transaction` | `SQLA_SESSION_BEGIN` `_CONNECTION` `_EXECUTE` `SQLA_TEXT` |
| `pitchlog.repositories.base.TenantRepositoryBase._execute_operation` | `SQLA_SESSION_EXECUTE` |
| **`pitchlog.repositories.transaction._TenantTransaction.run`** | **`SQLA_SESSION_EXECUTE`(1 件のみ)** |

**☐ E10**: `signature` が実装(`transaction.py:79`)と**文字列完全一致**:
`run(self, operation: TenantOperationToken) -> TenantOperationResult`

**☐ E11**: `allowed_api_ids` が **`SQLA_SESSION_EXECUTE` だけ**であること。
`Session.close`(`:222` `:228`)は `db-api-inventory.json` に**未登録**なので許可不要。
`Session(create_database_engine())`(`:155`)の `create_database_engine` は**それ自体が許可シンボル**。

---

## F. 契約資産と生成モジュール(P2-8)

**今回これが実害として出た。** `TenantTransaction.run` が実装から消えても、
**契約テストは `42 passed` で green のままだった**(文字列一致しか見ず、シンボルを解決しない)。
**気づいたのは迂回検査だけ。** 生成スクリプトは**リポジトリに存在せず手で同期している**ので、
**この一致テストが唯一の追随の担保だったが、担保になっていなかった**。

| # | 見るもの | 期待 | 判定 |
| --- | --- | --- | --- |
| F1 | `repository-contract.json` の `public_surface` | **7 キー**。`transaction_scope_entry` を追加し、**`transaction_handle_type` は入れていない**(非公開型を「公開面」に宣言しない) | ☐ |
| F2 | `repository_contract.py` | JSON と**逐語一致**。`TRANSACTION_HANDLE_TYPE` が**残っていない** | ☐ |
| F3 | `test_authz_repository_contract.py` の `_generated_snapshot()` | 固定辞書が F1 と一致 | ☐ |
| F4 | 新設 `test_declared_repository_symbols_resolve` | **宣言したシンボルが実際に解決できる**ことを見ているか | ☐ |
| F5 | 新設 `test_allowed_repository_symbol_signatures_match_runtime` | **解決したオブジェクトの署名が契約と一致**するか | ☐ |
| F6 | 新設 `test_generated_repository_constant_surface_is_exact` | **生成モジュールに契約外の定数が残っていない**(exact-set) | ☐ |

---

## G. 無変更の確認 — **最後に見る**

**この節を先に見てはいけない。** 冒頭に書いたとおり、初版は「無変更であること」を
第 1 項に置き、**差分ゼロのまま P0 が 3 件出た**。
**「触っていない」は「迂回されていない」を含意しない。**
A〜F を終えたうえで、**既存の防御が減っていないこと**の確認としてここを見る。

| # | ファイル | 差分 | 判定 |
| --- | --- | --- | --- |
| G1 | `backend/src/pitchlog/repositories/base.py` | **0 行** | ☐ |
| G2 | `backend/src/pitchlog/repositories/binding.py` | **0 行** | ☐ |
| G3 | `contracts/tenant_boundary/db-api-inventory.json` | **0 行**(裁定 7) | ☐ |
| G4 | `contracts/tenant_boundary/tenant-context-allowlist.json` | **0 行** | ☐ |
| G5 | `scripts/check_tenant_boundary_bypass.py` | **0 行** | ☐ |
| G6 | `scripts/frozen_history.py` | **0 行** | ☐ |

**☐ G7**: `PRODUCT_CAPABILITY_IDS` / `PRODUCT_OPERATION_TOKEN_TYPES` / `CROSS_TENANT_FUNCTIONS`
が **3 つとも空のまま**であること(製品経路を開いていない)。

---

## H. 変更ファイル全 15 件(取りこぼし確認)

| ファイル | 節 |
| --- | --- |
| `backend/src/pitchlog/repositories/transaction.py` | A / B / C / D |
| `backend/src/pitchlog/repositories/repository_contract.py` | F |
| `backend/tests/db/test_tenant_transaction_scope.py` | A / B / C / D |
| `backend/tests/test_authz_repository_contract.py` | F |
| `contracts/tenant_boundary/base-allowlist.json` | E |
| `contracts/tenant_boundary/repository-contract.json` | E / F |
| `contracts/tenant_boundary/history-snapshots/0afbcc…a046` | E8 |
| `contracts/tenant_boundary/history-snapshots/3a9d39…f305` | E8 |
| `tests/fixtures/tenant_boundary/positive/…/transaction.py` | D5 |
| `docs/features/tenant-session-supply/plan.md` | (文書) |
| `docs/features/tenant-session-supply/design.md` | (文書) |
| `docs/features/tenant-session-supply/research.md` | (文書) |
| `docs/worklog/2026-09-26-tenant-session-supply.md` | (文書) |
| `docs/development/harness-evaluation.md` | (文書・台帳) |
| `docs/README.md` | (文書・索引) |

---

## 実施記録

PR 本文のチェック行の直後に記入する(設計書 6.3)。

```
- 実施記録: 対象= 範囲= 方法=
```

**方法**は `目視` / `突合シート` / `その他`。本シートを使った場合は `突合シート`。
**確認した本人が記入する。** 上 3 項が空欄のままならマージ不可(github-setup 2 章)。
