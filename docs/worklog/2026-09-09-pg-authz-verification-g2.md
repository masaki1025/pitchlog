---
date: 2026-09-09
topic: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群(TSK-317 — TSK-270 計画の改訂 2)
branch: feature/pg-authz-verification-g2
---

# 作業ログ: 2026-09-09 PostgreSQL 認可構成の実機検証 第 2 群(TSK-317)

## やったこと

- `/task-start 317` — worktree `../pitchlog-worktrees/feature-pg-authz-verification-g2` を
  `origin/develop`(`1424d67`)から作成。Notion TSK-317 を `進行中` へ。
- `/investigate` — 調査サブエージェント 3 本(要件突合 / 決定経緯 / 資産実測)+ 原典の直接確認。
  `research.md`(401 行)に統合。
- `/plan` — 計画書と詳細設計を起草し、**コア領域の敵対レビューを 5 周**通した。
- **PO 裁定 8 件**(`D-1`〜`D-8`)を取得。

## 決定

- **feature ディレクトリは新設した**(`pg-authz-verification-g2`)。
  当初は `docs/features/pg-authz-verification/` の再利用を試みたが、**現在地導出が縮退した**ため撤回。
  `scripts/feature_status.py:1491-1503` の `expected_feature_slug` は **plan の期待パスをブランチ名から導出する**
  ため、期待パス以外に `branch:` が一致する plan があると `plan 重複` になる。旧ブランチが残っていて
  同名を切れないので、TSK-335・TSK-342 と同じ **1 タスク = 1 ディレクトリ**へ揃えた。
- **前計画書の内容を複製しない**(設計書 7.1-1)。`R-1`〜`R-8` と第 1 群の実測は
  `../pg-authz-verification/plan.md` が正で、1 節から相対リンクで参照する。

### PO 裁定(2026-09-09・山田正輝)

| # | 論点 | 裁定 |
| --- | --- | --- |
| `D-1` | 第 2 群の射程 | 凍結資産の全量をやる(cut set だけに絞らない) |
| `D-2` | `search_path` の P0 の直し方 | 本タスクの先頭ステップで直す → **`D-5` が置き換えた** |
| `D-3` | DDL 適用器の実装手段 | **psycopg 直書き**(TSK-343 を待たない) |
| `D-4` | oracle の裁定待ち 2 件 | **frozen 値を確定として承認**(8 と 29)+ 要件の「7 操作」との 1:N 写像を明示 |
| `D-5` | 正本側の未処理 3 件 | **TSK-348 として v0.2 の改訂ゲートを 1 本立てる**(本タスクの射程外) |
| `D-6` | 187 件の status 変更と oracle の封印の衝突 | **統合ステップへ集約**(コミット構造は `S-1` が置き換えた) |
| `D-7` | 正本の同一トランザクション要求と資産の 03/04 分割 | **適用器側で同一 TX に収める**(資産も正本も変えない) |
| `D-8` | 計画レビューが収束しない(7.3-6 の発火) | **第 2 群をさらに分割** — 承認範囲をステップ 1〜21 とし、引き渡しと封印は改訂 3 へ |

## 計画レビューの採否記録(敵対レビュー 5 周・全 53 件採用・不採用 0 件)

| 周 | 判定 | 前周修正起因 | 採否 | 主な反映 |
| --- | --- | --- | --- | --- |
| 1 | 要修正 P0×7 / P1×8 | 0 / 15 | **全 15 件採用** | 正本改訂のゲート区分を確定ゲート事項と認めて射程外へ / body の自己 oracle 化 / 返却契約の三者不一致 / 移行バッチロールの無所有 / **1 トランザクション契約の撤回** / `R-4` の弱体化を戻す / reseal の順序 |
| 2 | 要修正 P0×2 / P1×11 / P2×1 | **10 / 14** | **全 14 件採用** | **`auth-catalog` は `input_assets` で `oracle_commit` に固定** / 正本の同一 TX 要求 vs 資産の分割 / **`AUTH-*` は実在しない** / `contract_only` の受取先は本タスク自身 / 失敗注入点と 6 前提の資産を新設 / DSN を増やさない |
| 3 | 要修正 P0×2 / P1×8 / P2×1 | **8 / 11** | **全 11 件採用** | **`source_commit` の自己参照が構築不能** / `enforcement_test_owner.id` は pytest node ID でない / `req-universe.json` に `list_item` が 0 件 / 失敗注入点は `step_id` だけでは重複可 / MC/DC の判定母集合が自己申告 → **7.3-6 が発火し `D-8` で分割** |
| 4 | 要修正 **P0×0** / P1×10 | **9 / 10** | **全 10 件採用** | 凍結資産不変の判定基準を `origin/develop...HEAD` の 15 パス列挙へ / **MC/DC の主張を撤回**(注記の網羅性は機械では閉じない)/ 失敗注入点を exact-set から実在 + 重複禁止へ / `R-3` の封鎖方式を戻す / claim 158 行 vs 一意 ID 152 個 / `S-2` の射程拡大 / `S-9` 追加 |
| 5 | 要修正 P0×0 / P1×4 /(B) 0 件 | 3 / 4 | **全 4 件採用** | `P1-2` の反映漏れ(`[機械]` に注記網羅性が残っていた)/ **`S-9` の件数は 178**(158 + probe_executable 20)/ ステップ番号の残存 5 箇所 / 検証コマンドの `cd` 二重パス |

**打ち切りと承認**: 5 周目は P0×0 かつ **(B) 分類 0 件**で、4 件はすべて**反映漏れと誤記**(方式の分岐なし)。
是正して**人間の承認を取得**(2026-09-09・山田正輝)。**周回は 5**(5 周目も反映を伴ったので計上)。

### 実測が 4 周連続で記述を覆した

**凍結資産を実測しないと分からない事実**が毎周出た。字面と設計の突合だけでは足りなかった。

| 周 | 実測 |
| --- | --- |
| 2 | `TX:PROVISIONING.atomic` は **`false`** / `AUTH-*` は **0 件**(全 187 件が `CATALOG:*`)/ `auth-catalog` は `input_assets` で `oracle_commit` 上の blob との一致まで要求される |
| 3 | `enforcement_test_owner.id` は **`::` を 0 件**(pytest node ID でない)/ `req-universe.json` に `list_item` は **0 件** |
| 4 | `contract_only` の claim 158 行に対し一意な `runtime_test_owner.id` は **152 個**(6 組が共有) |
| 5 | `receiving_task_id: TSK-270-GROUP-2` は **178 件**(`contract_only` 158 + `probe_executable` 20) |

### 正本側に見つかった欠陥(TSK-348 へ)

1. **【P0】`data-model.md` 3-2 節の `search_path` 契約が、実測で「誤り」と判定された記述のまま**
   — `REJ-003` の `candidate_statement_status: incorrect` / `observed_result:
   temporary_relation_hijack_returned_attacker_rows`。反証は 2026-08-31(PR #33)にあり、正本の approved は
   2026-09-09 で、**9 日古い実測が反映されていなかった**。TSK-342 の確定ゲート 13 周が捕まえなかった理由は
   反証が `contracts/authz/` にあってレビュー射程外だったことと、**正本側が `pg_temp` という語を 1 度も
   使っていない**こと(実測 0 件)。**台帳 `H-79` の型**。
2. **越境関数の返却契約が三者不一致** — 正本 3-6 節は「返す列を集計値に限定」と「集計は関数に書かない」を
   併記し、凍結資産は `aggregation_contract: none`(業務行を返す)。
3. TSK-342 の打ち切りで残した、定義の言い換えによる重複。

## 起票した Notion タスク

| ID | 内容 |
| --- | --- |
| **TSK-348**(高) | `data-model.md` v0.2 の改訂ゲート — 上記 3 件。**本タスクのマージの前提**(DoD 項目) |
| **TSK-349**(中) | 移行バッチ用ロールの実機検証と退役検査 — `data-model.md:289` の検査の所有者を実 ID で閉じた |

## 未決・次の一歩

- **`/implement` でステップ 1 から委任する。** 承認範囲は**ステップ 1〜21(実体を作る)**。
- **ステップ 4 以降は実 PostgreSQL が必要** — `PITCHLOG_TEST_ADMIN_DSN` と `PITCHLOG_TEST_ROLE_DSN` の
  実値が要る(未設定は skip ではなく `pytest.fail`)。実測で `docker compose config` が `POSTGRES_USER`
  欠落で失敗し、`psql` は未導入。**実値の用意は人間の作業**(`NFR-014`・設計書 12.1)。
  ステップ 1〜3 は SQL とコードだけなので DB 無しで進められる。
- **改訂 3 が満たすべき要件 `S-1`〜`S-9`** を計画書 4 節に記録済み(3 周分の指摘を失わないため)。
  ステップ 21 が終わった時点で `status` を `active` のまま改訂し、再レビューを通す。
- **申し送り(/pr で起票)**: ADR-003 `D-12` と `contracts/authz/` の位置づけ / アプリ用ロールの `DELETE` /
  `H-57` のジョブ行 / **`AUTH-*` と `CATALOG:*` の ID 体系の食い違い**(TSK-250 の計画書が `AUTH-*` を期待) /
  `closure-handoff-data-model.json` の「作成」と正本 `:2750` の「作成・実行」の差。
- **ハーネス運用評価台帳への追記の判断は `/pr` のクローズ処理で行う**(本タスクの経過は候補が複数ある —
  とくに「**凍結資産を実測しない計画レビューは 4 周連続で誤った前提を通す**」型と
  「**自作の母集合は自己申告になり、機械で縛ろうとすると無限後退する**」型)。


## TSK-235 のタブからの申し送り(2026-09-10)— 受領と実測

**申し送り B(TSK-317 宛)の 3 件を受領し、すべて実測で確認した。**

### 【1】`guard_paths` への未登録 — **指摘は 4 本だが実測は 6 本**

申し送りはステップ 9 までの 4 本を挙げていたが、**ステップ 14 で 2 本増えて 6 本**である。

| 未登録のパス | 新設したステップ |
| --- | --- |
| `scripts/check_authz_function_bodies.py` | 2 |
| `tests/test_check_authz_function_bodies.py` | 2 |
| `scripts/check_shared_preconditions.py` | 9 |
| `tests/test_check_shared_preconditions.py` | 9 |
| `scripts/check_failure_injection_points.py` | 14 |
| `tests/test_check_failure_injection_points.py` | 14 |

**現行の `guard_paths` は 30 件**で、**`check_design_propagation` / `check_doc_coverage` /
`check_processing_stages` をスクリプトとテストの対で個別列挙**している。
**命名規約上この 6 本も入る系列**であり、**未登録のままでは凍結資産を検査するスクリプトを
弱めても逐行確認が発火しない**(台帳 `H-12` の型)。

→ **計画書の `S-8`(改訂 3 の要件)へ実測 6 本を明記した。**
**`guard_paths` 追加は 6.3 規則⑤(敵対レビュー + 人間承認)**なので改訂 3 の射程である。

### 【2】harness の予算基線 — 測定条件を記録する

申し送りが「run id 付きで残してほしい」と要求しているので、**測定条件を明記して記録する**。

| 項目 | 値 |
| --- | --- |
| **測定値** | **1171 passed**(ステップ 14 時点) |
| **コミット** | `a9f28fa` |
| **測定日** | 2026-09-10 |
| **実行環境** | **ローカル**(WSL2 / Linux 6.6.114.1-microsoft-standard-WSL2)。**CI runner ではない** |
| **コマンド** | `uv run pytest tests/`(worktree のルートで) |
| **run id** | **なし**(ローカル実行のため)。**CI の run id は本タスクの PR 作成後に付く** |
| root tests への増分 | **+691 行**(`test_check_authz_function_bodies.py` 256 / `test_check_shared_preconditions.py` 204 / `test_check_failure_injection_points.py` 231) |

**申し送りが引いていた基線は 1144 passed / 285.07s @ `75b6cd3`**(TSK-235 のブランチ)。
**本タスクのマージ後に失効する**という見立てのとおりである。
**CI の run id 付きの数値は PR 作成時に記録する。**

### 【3】`auth-catalog.json` の owner は 2 種だった — **私の TSK-250 宛の申し送りを訂正する**

**実測**:

| owner | status |
| --- | --- |
| **`catalog_test_owner`** | **187 件すべて `implemented`** |
| **`enforcement_test_owner`** | **187 件すべて `planned`**(`TSK-270` 169 / `TSK-312` 18) |

**私が TSK-250 へ送った申し送り【3】は後者だけを見ていた。**
申し送り B の指摘どおり、**TSK-250 の計画書ステップ 19 の合格条件
「全 `AUTH-*` に DDL 要素とテスト ID がある」は、文字面では前者(既に `implemented`)で
通ってしまう**。

ただし同計画書 5 節(B の信頼境界・3 周目 `P0-3` の採用)が exact-set を
**「要件安定 ID → AUTH 主張 → 関数の全シグネチャ・ロール・期待結果 → テスト ID」**と定義しており、
**「期待結果」まで結ぶ以上これは enforcement 側**である。

→ **私が「開始条件 B が改訂 3 まで完了を意味する可能性がある」と書いた点は、
計画書の文言から支持される読みへ格上げできる。**
→ **計画書の `S-2` へ owner 2 種の実測を追記し、受取側が enforcement 側を見ることを
`S-6` の受取契約で固定する**ことにした。

