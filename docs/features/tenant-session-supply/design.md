---
feature: tenant-session-supply
type: design
date: 2026-09-26
---

# 詳細設計: Session の供給 + トランザクション単位(TSK-444)

> **行番号の基準**: 断りのない限り **`origin/develop` = `b4ae7394`** 時点。確認は `git show b4ae7394:<path>`。
> **本書は詳細設計。契約と実装ステップは [plan.md](plan.md) が正。**

## 1. 束縛のライフサイクル(最初に効く制約)

**1 つの `Session` は生涯 1 回しか束縛できない**(実測):

```
backend/src/pitchlog/repositories/binding.py:14  _BOUND_TENANT_INFO_KEY の定義
backend/src/pitchlog/repositories/binding.py:60  存在チェック(拒否)
backend/src/pitchlog/repositories/binding.py:65  書き込み
```

**`pop` / `del` / クリアは `backend/` `tests/` のどこにも無い。** しかも `:60` は
**tenant_id を比較せずキーの存在だけ**で拒否するので、**同一テナントの再入も落ちる**。
**rollback しても印は消えない。**

### 帰結

| | |
| --- | --- |
| **トランザクション単位の形** | **1 Session = 1 トランザクション = 1 束縛 = N operation** |
| **印を消す設計** | **取らない**。`data-model.md:326-327` が「リクエストごとに Session を作り、テナント横断・リクエスト横断で共有しない」と定めている |
| **再試行が要る場合** | **試行ごとに新しい `Session` が要る**。だから供給は **factory** にする(下記 2) |

## 2. Session の供給の形

**`create_database_engine()` は `Engine` を返すだけ**(`backend/src/pitchlog/db/engine.py:426`・`:447`)。
`backend/src` に `sessionmaker` / `Session(` は **0 件**。

### 2-1. factory にする理由

**再試行を本タスクの射程に入れないが、後から可能な形にしておく**(plan.md 4-1 の裁定 5)。
**1 リクエスト 1 Session を固定すると、再試行のたびに新しい Session を作れない**(1 節の帰結)。
よって供給は「**呼ぶたびに新しい `Session` を返す factory**」とし、
**誰がいつ呼ぶか(リクエスト単位か、試行単位か)は呼び出し側が決める**。

### 2-2. 生の `Session` を公開しない

U-T1 の確定事項(`../tenant-boundary-enforcement/plan.md:174`):

> 基底の**公開シンボルが exact-set**(生の `Session`・任意クエリを公開しない)

→ **factory は `repositories` パッケージの内部に置き、`__all__` へ出さない。**
公開されるのは**トランザクション単位の入口だけ**で、その署名は
**生成済みの閉じた operation token だけを受ける**。

### 2-3. 迂回検査との関係(実測)

- `sqlalchemy.orm.Session` のコンストラクタは `db-api-inventory.json` の
  **`receiver_factories`(`:121-124`)にあり `apis` には無い** → **呼び出し自体は TB005 にならない**
- ただし返り値は provenance `db` になり、以後の `.begin()` / `.execute()` / `.commit()` は
  **許可シンボル外なら TB005**
- → **factory と トランザクション単位を `allowed_symbols` へ登録する**(plan.md ステップ 5)
- **使う API は既存 ID の範囲に収める**(`SQLA_SESSION_BEGIN` / `SQLA_SESSION_CONNECTION` /
  `SQLA_SESSION_EXECUTE` / `SQLA_TEXT`)。**`db-api-inventory.json` は触らない**(plan.md 4-1 の裁定 7)

## 3. トランザクション単位の形

### 3-1. 署名の制約(U-T1 が固定済み)

`../tenant-boundary-enforcement/plan.md:174` の逐語:

> **実行器は非公開**とし、公開面は**生成済みの閉じた operation token だけを受ける署名**に限る。
> **`Any` / callable / SQLAlchemy の statement・model・table を引数に取らない**

`backend/tests/test_authz_repository_contract.py:250` が **`public_methods == {"execute"}`** を固定しているので、
**公開メソッドを増やせば必ず red**。資産(`repository-contract.json` の `public_surface`)と
生成モジュールを同時に動かす(plan.md ステップ 5)。

### 3-2. 前段の結果を見て後段を中止する方法

**複数表の不変条件は「読んでから書く」なので、前段の結果を後段の実行可否に使えないと意味がない。**

**採る形**: **呼び出し側が operation を 1 件ずつ実行し、結果を見て次を決める**。
トランザクション単位は「**束縛済みのトランザクションを開いたまま、複数回の実行を受け付ける**」文脈を提供する。

```
with <トランザクション単位>(context) as tx:
    rows = tx.run(<判定 token>)          # 前段
    if <rows から中止を判断>:
        raise <中止の例外>               # → ロールバック
    tx.run(<更新 token>)                 # 後段
# ここで 1 回 commit
```

**却下した案**: token の列を一度に渡す形(`run_all([t1, t2, ...])`)。
**前段の結果を見て後段を止められない**ので、FR-018 型の不変条件に使えない。

### 3-3. 戻り値の制約

`repository-contract.json` の `return_contract`(`:106-124`)と
`../tenant-boundary-enforcement/plan.md:174` が、
**完全実体化済みの immutable な値 / DTO** に限っている。
**接続中の ORM instance・`Result`・`ScalarResult`・query・遅延 generator を返さない。**
`tx.run()` の戻り値は既存の `TenantOperationResult`(`repositories/tokens.py:32-36`)をそのまま使う。

### 3-4. 例外の扱い

- **中止の例外**: 呼び出し側が投げる。トランザクション単位は**握り潰さず**伝播させ、**ロールバックする**
- **`TenantBindingError`**: 束縛が成立しないときに既存どおり投げる
- **未登録 token**: `_operation_spec()`(`backend/src/pitchlog/repositories/base.py:129-142`)が既に拒否する。
  トランザクション単位でも**同じ経路を通す**(独自の検査を作らない)

## 4. U-M1 への受け渡し契約

**本タスクは機構だけを提供する**(plan.md 4-1 の裁定 1)。U-M1 が使えるように、**次を本タスクで確定させる**:

| # | 渡すもの | 本タスクで決める | U-M1 が決める |
| --- | --- | --- | --- |
| 1 | **トランザクション単位の入口の署名** | ✅ | — |
| 2 | **前段の結果で後段を中止する方法**(3-2) | ✅ | 中止条件そのもの |
| 3 | **戻り値の型**(3-3) | ✅ | — |
| 4 | **中止時のロールバックの保証**(3-4) | ✅ | 中止の例外型 |
| 5 | **述語 SQL**(紐づけ判定・進行中試合の判定) | — | ✅ |
| 6 | **`insert` / `update` の operation token の登録形式** | — | **登録する単位が registry と一緒に定める**(`../product-authz-surface/design.md:618`) |
| 7 | **FR-018 の並行性**(判定後に紐づいた場合に失敗させる機構) | — | **本タスクの射程外**(plan.md 4-1 の裁定 3)。**U-M1 単独でも閉じない**(5 節) |

## 5. 【重要】FR-018 の並行性がなぜ本タスクで閉じないか

**要件**(要件書 `:391` の逐語):

> Given 削除と同時に別端末が当該選手のプレイを記録 / When 削除確定 /
> Then **紐づけ判定と削除が同一トランザクションで行われ、判定後に紐づいた場合は失敗する**

### 5-1. `SERIALIZABLE` では成立しない(**当方の実測に基づく**)

PostgreSQL の SSI が中断するには **rw-アンチ依存の閉路**が要る。この場面では:

- 削除側 D: `play_rows` を**読み**、`players.hidden_at` を**書く**
- 紐づけ側 L: `play_rows` に**挿入する**。**`players.hidden_at` を読まない**

**D→L の辺はできるが、L→D の辺ができない。閉路にならないので両方 commit する。**

### 5-2. `FOR UPDATE` でも成立しない

**論理削除は行を消さない** — `hidden_at` 列の更新である(実測: `backend/src/pitchlog/db/game_state/models.py:142` ほか)。
D が `players` 行を `FOR UPDATE` でロックしても、L 側の FK 検査(`FOR KEY SHARE`)は
**待たされた後そのまま成功する**。行は存在し続けるため。

### 5-3. 成立させるには紐づけ生成側の協力が要る

**「紐づけを作る側が選手の `hidden_at` を読む」**ことが必要になる。
その経路は**本タスクでも U-M1 でもない**(プレイ記録 = 同期適用経路)。

→ **FR-018 の並行性は、単位を跨ぐ設計判断として別に扱う。**
plan.md 2 節の「やらないこと」に置き、**申し送り先を明示する**。

## 6. 分離レベルを扱わない理由(裁定 5 の補足)

FR-018 の並行性を射程外にしたので、**本タスクに `SERIALIZABLE` を要求する根拠が無くなった**。

なお**後から入れる場合の制約**は調べてある(申し送り):

- PostgreSQL は**最初の query / DML の後に `SET TRANSACTION ISOLATION LEVEL` を実行できない**
- SQLAlchemy では **トランザクション開始直後・他の操作より前に**
  `Session.connection(execution_options={"isolation_level": ...})` を取る方法がある
- **束縛文より前に分離レベルの SQL が出ると、U-T1 の「先頭が束縛文」に違反する**おそれがある。
  **ドライバレベルの発行位置まで観測して確かめる必要がある**
