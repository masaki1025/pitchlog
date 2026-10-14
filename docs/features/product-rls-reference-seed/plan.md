---
feature: product-rls-reference-seed
status: active
承認: 済(2026-10-14・利用者、採る案と射程を承認)
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/fix-product-rls-reference-seed
branch: fix/product-rls-reference-seed
created: 2026-10-14
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: 実スキーマ経路で移行 seed の参照行が消える問題の修正

## 1. 背景・目的と所有

**12-4 の越境テスト再実行ゲートが、現在 develop で通らない。**

2026-10-14 に PR #119(U-A1 δ)が専用インスタンスに対して runner を回したところ、
48 node 中 1 件が落ちた。**同じ対象で develop(`b81ae1ac`)を対照に回しても同一 node が落ちる**ため、
#119 起因ではない。

```
tests/db/test_product_authz_cross_cutting.py::test_force_rls_applies_to_owner_with_unbound_context
```

| 実行 | 生成 ID | 結果 |
| --- | --- | --- |
| #119 | `20261014T045647Z-423c9e25fe8ce22e` | 48 node / 47 passed・1 failed |
| develop(対照) | `20261014T052012Z-a8d4c3c7a2e0d4dd` | 48 node / 47 passed・1 failed(同一 node) |

**所有は [TSK-479 / PR #122](https://github.com/masaki1025/pitchlog/pull/122)**(`feature/game-type-seed`・2026-10-13 マージ)。
`a3d07713`「所有者限定RLSで試合区分seedを往復検証 (ステップ 3/4)」が当該テストの期待を書き換えた。
**担当セッションは稼働していないため、本 fix が代行する**(人間の指示 2026-10-14)。

**これは #119 だけの問題ではない。** 12-4 のゲートは**入口を開くすべての PR**に掛かるので、
通るまで誰も通過条件②を満たせない。

## 2. 何が起きているか(実測済みの連鎖)

| # | 事実 | 典拠 |
| --- | --- | --- |
| 1 | migration `0030_seed_game_type.py` が `system_vocabularies` へ試合区分 **5 行**を seed する | 当該ファイル `:27-39` |
| 2 | `contracts/authz/product/table-classification.json` の 45 表に `system_vocabularies` が含まれる(profile `global_read_only`) | 同資産 |
| 3 | `_clear_product_data` がその 45 表を `TRUNCATE TABLE ... RESTART IDENTITY` する | `backend/tests/db_fixtures.py:535-542` |
| 4 | **この TRUNCATE は外部供給(runner)経路でだけ走る** | 同 `:1073`・`:1092` |
| 5 | 結果、**移行が入れた 5 行が消えてから**テストが始まる | 1〜4 の帰結 |
| 6 | 当該テストは「所有者に試合区分 **5 行がちょうど見える**」と表明する | `test_product_authz_cross_cutting.py` の当該関数 |

**使い捨て DB(外部供給なし)では fixture がクラスタを作り直すので TRUNCATE 経路を通らず、5 行が残る。**
**実測**: 使い捨て Postgres に対し runner と同一の起動・同一の順序で 3 ファイルを回すと **48 passed**(182 秒)。

**製品の欠陥ではない。** テナント分離に穴は無く、**試験基盤と移行 seed の両立の問題**である。

## 3. 採る案と、採らない案

### 採る案 — TRUNCATE 後に参照行を復元する

**移行済みの対象が持っていた `global_read_only` 4 表の内容を、供給の開始時に 1 度読み取って控え、
各 TRUNCATE の後に書き戻す。**

対象 4 表(`table-classification.json` の `global_read_only`):
`game_type_rule_defaults` / `system_vocabularies` / `admin_vocabularies` / `system_settings`

**seed の定義を fixture へ複製しない** — 移行済みの対象そのものから読む。
**NFR-018(単一実装)を踏まない**のがこの形を採る理由である。

### 採らない案

| 案 | なぜ採らないか |
| --- | --- |
| `global_read_only` を TRUNCATE 対象から外す | **テスト間の分離が壊れる。** あるテストが足した語彙が次のテストへ残る |
| テスト側で 5 行を前提にしない | **#122 が入れた往復検証の意図を失う。** 「所有者限定 RLS で試合区分 seed を往復検証する」という表明そのものを弱める |
| seed の内容を fixture へ書き写す | **移行と二重定義**になる(NFR-018)。移行が増えるたびに追随が要る |

## 4. スコープ

**変更するのは `backend/tests/db_fixtures.py` だけ。**

| 変更しない | 理由 |
| --- | --- |
| `backend/migrations/` | 移行は正しい。seed は入っている |
| `backend/tests/db/test_product_authz_*.py` | #122 の表明は正しい |
| `contracts/authz/product/table-classification.json` | 45 表の分類は正しい(凍結資産) |
| `scripts/product_rls_real_schema/` | runner の手順は正しい。**#97 以降 1 行も動いていない** |
| `.claude/core-areas.json` / `scripts/core_guard.py` | **触らない。** 既存 glob(`backend/tests/db/*`・`backend/tests/db_fixtures.py`)に該当済み |
| PR #119 の worktree | 所有が別。本 fix の差分は #119 へは持ち込まない |

**試験の削除・skip・検査の緩和はしない。**

## 5. 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | **供給の開始時に `global_read_only` 4 表の内容を控え、`_clear_product_data` の後に書き戻す。** 控えは外部供給経路でだけ作り、非供給経路の挙動は 1 行も変えない | backend の既存 DB 試験が従来どおり / 非供給経路の全件実行が前後で同一 / ruff・ty green |

**1 ステップ = 1 委任 = 1 コミット**(設計書 6.1)。

## 6. 検証(end-to-end)

| # | 検証 | 実行者 |
| --- | --- | --- |
| 1 | `uv run ruff check .` / `uv run ty check`(root・backend) | Claude |
| 2 | 使い捨て Postgres に対し runner と同一の起動で 3 ファイル **48 passed**(回帰がないこと) | Claude |
| 3 | **専用インスタンスに対して runner が 48 node 全件 passed**(= 12-4 の通過条件②) | **人間**(接続情報は環境変数・NFR-014) |

**3 が本 fix の DoD である。** 2 だけでは**この問題を再現できない**(問題は供給経路にしかない)。

## 7. 重さ分類

**コア領域**(テナント分離)。`backend/tests/db_fixtures.py` は `tenant-isolation` の paths に該当する。
→ ADR-001 により **敵対レビュー必須・人間の逐行確認必須**。

## 8. 申し送り

1. **12-4 のゲートが #97(2026-10-07)以来回っていなかった。** その間に DB 層の期待が変わり、
   本件が作り込まれた。**ゲートが実際に回っていれば 2026-10-13 に捕まっていた。**
   「**入口を開く PR で 12-4 の記録が落ちる**」型として master へ共有済み(PR #95 にも判定記録が無い)
2. **`pg_isready` は認証の成否を見ない。** 専用インスタンスが `healthy` でも使えないことがある
3. **`POSTGRES_USER` / `POSTGRES_PASSWORD` は initdb の 1 回きり。** 変数を変えてもボリュームは変わらない
4. **runner は `-p pitchlog` が要る。** worktree から既定で叩くと別プロジェクトが立つ
