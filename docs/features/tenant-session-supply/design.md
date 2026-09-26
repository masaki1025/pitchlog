---
feature: tenant-session-supply
type: design
date: 2026-09-26
---

# 詳細設計: トランザクション単位(TSK-444)

> **行番号の基準**: 断りのない限り **`origin/develop` = `b4ae7394`** 時点。確認は `git show b4ae7394:<path>`。
> **本書は詳細設計。契約と実装ステップは [plan.md](plan.md) が正。**

## 1. 束縛のライフサイクル(最初に効く制約)

**1 つの `Session` は生涯 1 回しか束縛できない**(実測):

```
backend/src/pitchlog/repositories/binding.py:14  _BOUND_TENANT_INFO_KEY の定義
backend/src/pitchlog/repositories/binding.py:60  存在チェック(拒否)
backend/src/pitchlog/repositories/binding.py:65  書き込み
```

**`pop` / `del` / クリアは `backend/` `tests/` のどこにも無い。** `:60` は
**tenant_id を比較せずキーの存在だけ**で拒否するので、**同一テナントの再入も落ちる**。**rollback しても印は消えない。**

→ **1 Session = 1 トランザクション = 1 束縛 = N operation**。印を消す設計は取らない
(`data-model.md:326-327` が「リクエストごとに Session を作り、テナント横断・リクエスト横断で共有しない」と定めている)。

## 2. 【2 周目 P0-2 の是正】Session を返す factory を作らない

初稿は「内部モジュールに置き `__all__` へ出さない factory」としていたが、**これは新しい到達路になる**。

**実測で確かめられた性質**(調査 5 節):
`sqlalchemy.orm.Session` のコンストラクタは `db-api-inventory.json` の **`receiver_factories`(`:121-124`)にあり
`apis` には無い** → **`return Session(engine)` だけの関数は迂回検査に 1 件も引っかからない**。
**生の Session を戻り値として別層へ漏らすこと自体を検出する検査が無い。**

→ **Session を返す関数を作らない。** **トランザクション単位が Session の生成・束縛・commit/rollback・close をすべて所有する。**

**close の所有者も明示する**: 既存の `_tenant_transaction`(`binding.py:37-76`)は commit / rollback はするが
**`Session` を close しない**。よって**トランザクション単位が `finally` で close する**。

## 3. 【2 周目 P0-1 の是正】公開面の確定

### 3-1. 新設するもの

**新しいモジュール `backend/src/pitchlog/repositories/transaction.py`** を置く。

| シンボル | 種別 | 署名 |
| --- | --- | --- |
| `tenant_transaction_scope` | **公開関数(context manager)** | `tenant_transaction_scope(context: TenantContext) -> AbstractContextManager[TenantTransaction]` |
| `TenantTransaction` | **公開型(`@final`)** | 公開メソッドは **`run` のみ** |
| `TenantTransaction.run` | **公開メソッド** | `run(self, operation: TenantOperationToken) -> TenantOperationResult` |

```python
__all__ = ("TenantTransaction", "tenant_transaction_scope")
```

### 3-2. `TenantContext` を `run` が受け取らない理由

**トランザクション単位の生成時に 1 回だけ受け取り、`run` は受け取らない。**

これは **U-T1 の「token だけを受ける署名」**(`../tenant-boundary-enforcement/plan.md:174`)を満たすと同時に、
**同一トランザクションへ異なる `TenantContext` を混ぜることを構造的に不可能にする**。

> **【2 周目 P0-1 の指摘への回答】** レビュアーは「混在の負例を公開 API 経由で構成できない」と指摘した。
> **そのとおりで、それが意図**である。**負例は「混在を試す」ではなく「混在させる口が無い」ことを固定する形**にする
> ([plan.md](plan.md) ステップ 2 の②へ差し替え)。

### 3-3. `TenantTransaction` が生の `Session` への到達路にならないこと

- `__slots__ = ("_session", "_context")` — **公開属性を持たない**
- `@final` — 継承で穴を開けられない
- 公開メソッドは `run` **だけ**。`commit` / `rollback` / `connection` / `session` を持たない
- **`run` の戻り値は既存の `TenantOperationResult`**(`repositories/tokens.py:32-36`)。
  `repository-contract.json` の `return_contract`(**`:86-124`** — **2 周目 P2-1 の是正**。初稿は `:106-124` と書いていた)が
  **完全実体化済みの immutable 値 / DTO** に限っている

### 3-4. 既存の `execute` 経路を触らない(**設計上の重要な帰結**)

`_OPERATION_REGISTRY` は**モジュール変数**(`base.py:60-62`)で、operation token は自己完結している。
**リポジトリのインスタンスは `self._session` を運ぶためだけに存在する。**

→ **トランザクション単位は自分で Session を持つので、リポジトリのインスタンスを必要としない。**
→ **`base.py` の `execute` / `_execute_operation` / `_session` を 1 行も変更しない。**

**これにより 2 つの問題が同時に消える**:

1. **`public_methods == {"execute"}`**(`backend/tests/test_authz_repository_contract.py:250`)**が red にならない**
   — `TenantRepositoryBase` に公開メソッドを足さないため
2. **変異テストの literal アンカーが壊れない**(`tests/test_check_tenant_boundary_bypass.py:644-652` が
   `"            execution_result = self._session.execute(\n"` を参照している)
   — **`base.py` を触らないため**(初稿の 4-3 の懸念は消える)

**却下した案**: `TenantRepositoryBase` に公開メソッド `transaction` を足す形。
**公開面 exact-set と変異テストの両方を動かす**ことになり、射程が広がる。

### 3-5. 使い方(FR-018 型の不変条件)

```python
with tenant_transaction_scope(context) as tx:
    rows = tx.run(<判定 token>)          # 前段
    if <rows から中止を判断>:
        raise <中止の例外>               # → ロールバックして close
    tx.run(<更新 token>)                 # 後段
# ここで 1 回 commit して close
```

**却下した案**: token の列を一度に渡す形(`run_all([t1, t2, ...])`)。
**前段の結果を見て後段を止められない**ので、FR-018 型の不変条件に使えない。

### 3-6. 例外の扱い

- **中止の例外**: 呼び出し側が投げる。トランザクション単位は**握り潰さず**伝播させ、**ロールバックして close する**
- **`TenantBindingError`**: `_tenant_transaction` の既存経路がそのまま投げる
- **未登録・偽造 token**: `_operation_spec()`(`base.py:129-142`)の**既存経路を通す**。独自の検査を作らない

## 4. U-M1 への受け渡し契約

| # | 渡すもの | 本タスクで決める | U-M1 が決める |
| --- | --- | --- | --- |
| 1 | `tenant_transaction_scope` の署名(3-1) | ✅ | — |
| 2 | 前段の結果で後段を中止する方法(3-5) | ✅ | 中止条件そのもの |
| 3 | 戻り値の型(3-3) | ✅ | — |
| 4 | 中止時のロールバックと close の保証(3-6) | ✅ | 中止の例外型 |
| 5 | 述語 SQL(紐づけ判定・進行中試合の判定) | — | ✅ |
| 6 | `insert` / `update` の operation token の登録形式 | — | **登録する単位が registry と一緒に定める**(`../product-authz-surface/design.md:618`) |
| 7 | **FR-018 の並行性** | — | **本タスクの射程外**。**U-M1 単独でも閉じない**(5 節) |

## 5. FR-018 の並行性がなぜ本タスクで閉じないか

**要件**(要件書 `:391` の逐語):

> Given 削除と同時に別端末が当該選手のプレイを記録 / When 削除確定 /
> Then **紐づけ判定と削除が同一トランザクションで行われ、判定後に紐づいた場合は失敗する**

### 5-1. `SERIALIZABLE` では成立しない

PostgreSQL の SSI が中断するには **rw-アンチ依存の閉路**が要る:

- 削除側 D: `play_rows` を**読み**、選手行の `hidden_at` を**書く**
- 紐づけ側 L: `play_rows` へ**挿入する**。**選手行を読まない**

**D→L の辺はできるが L→D の辺ができない。閉路にならないので両方 commit する。**
`SERIALIZABLE` が保証するのは「成功した並行トランザクション群が**何らかの直列順序と等価**」であって、
「**壁時計順で後から挿入されたら削除を失敗させる**」ことではない。

### 5-2. `FOR UPDATE` でも成立しない(**2 周目 P1-1 で論証を訂正**)

**論理削除は行を消さない** — 選手の `hidden_at` 列の更新である
(**`backend/src/pitchlog/db/tenant_isolation/models.py:195`**。
**初稿が挙げた `game_state/models.py:142` は `Game.hidden_at` で誤りだった**)。

さらに **`PlayRow.batter_id` / `pitcher_id` / `catcher_id` は素の `Uuid` 列で ForeignKey を持たない**
(`backend/src/pitchlog/db/game_state/models.py:618`・`:633`・`:638`)。
**初稿は「L 側の FK 検査が `FOR KEY SHARE` で待つ」と書いたが、そもそも FK が無い経路がある。**

→ D が選手行を `FOR UPDATE` でロックしても、**L は選手行に一切触れないので待たされない**。

### 5-3. 成立させるために必要なこと

**紐づけを作る側、または DB の制約 / trigger が、選手の非表示状態を検証して拒否する**必要がある
(**2 周目 P1-1 の是正** — 初稿は「`hidden_at` を読む」と限定していたが、**手段は読み取りに限らない**)。

**対象は `players` を参照する全列**に及ぶ(`batter_id` / `pitcher_id` / `catcher_id` / `play_runners` 系ほか)。
その経路は**本タスクでも U-M1 でもない**(プレイ記録 = 同期適用経路)。

→ **単位を跨ぐ設計判断として、受け取り先を起票して送る**([plan.md](plan.md) 7 節)。

## 6. 分離レベルを扱わない理由

FR-018 の並行性を射程外にしたので、**本タスクに `SERIALIZABLE` を要求する根拠が無い**。

**後から入れる場合の制約**(申し送り):

- PostgreSQL は**最初の query / DML の後に `SET TRANSACTION ISOLATION LEVEL` を実行できない**
- SQLAlchemy では**トランザクション開始直後・他の操作より前に**
  `Session.connection(execution_options={"isolation_level": ...})` を取る方法がある
- **束縛文より前に分離レベルの SQL が出ると U-T1 の「先頭が束縛文」に違反するおそれ**がある。
  **ドライバレベルの発行位置まで観測して確かめる必要がある**
