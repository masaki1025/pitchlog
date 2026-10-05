---
date: 2026-10-03
topic: TSK-475 在籍区分キーの値と system_vocabularies の seed
branch: feature/roster-status-vocabulary-seed
---

# 作業ログ: 2026-10-03 TSK-475 在籍区分キーの値と system_vocabularies の seed

## やったこと

- 計画レビュー **7 周**(1〜6 周は否決。6 周とも当方の読み落としか作りすぎを機械が拾った)+ **スパイク 2 本**で承認(2026-10-04)
- 実装(ステップ 1〜10): research の未解決欄の確定 → シード資産 → **7.7 準拠の限定許可**(宣言資産 + 検査器 + 更新記録)→ seed revision → 実 revision 負例 3 件 → 三者一致検査 → 実 DB の FK/NOT NULL → 射程外 4 件の起票 → 正本反映 → U-M1 への申し送り
- **実装の敵対レビュー 8 周**(ステップ 11)→ 総合検証 → **クローズ処理**(ステップ 12)

## 決定

- **在籍区分キーは `active` / `other` / `ob`。** `active` は既存記述(要件書 `:505` `:996` `:1177` / `data-model.md:526`)に合わせて据え置いた
- **二段構成**(`contracts/seeds/roster-status.json` が正 → `op.bulk_insert()` で DB へ)。正本 `data-model.md:1946` `:2421` に合わせた
- **限定許可は宣言資産へ外出し**(設計書 7.7-1)。検査器のソースに revision のパス・表名・キー・行数を 1 つも置いていない
- **`category` 強制は本タスクの射程外**(7.6-3 のスキーマ変更に当たり、かつ書き込み経路が未開通)

## 実測・記録

### ① 在籍キーを `game_type_key` に入れられてしまう(**本タスクが作った欠陥ではない**)

`system_vocabularies` の FK は `key` 単独で、**`category` を拘束していない**
(`0010_vocabularies_settings.py:98-141` — `fk_players_roster_status` / `fk_games_game_type` /
`fk_game_type_rule_defaults_type` のいずれも参照列は `["key"]`)。

そのため **`games.game_type_key = 'active'` が DB を通る。** 本タスクが `active` を投入したことで
**この経路は直ちに成立する。** 逆向き(選手に `official`)は、本計画が `game_type` を 0 行に保つため
いまは成立しない。

**ステップ 7 ではこれを検査しない。** 検査を書けば現状の DB では red になるからで、
**`category` 強制は確定ゲート案件として別タスクへ起票する**(ステップ 8)。
その DoD の着地条件は「**試合区分の seed と、`games` / `game_type_rule_defaults` を含む
全参照元の書き込み開始のいずれよりも前**」。

### ② 往復テストの付け替え(ステップ 4)

seed した `active` を参照したまま `0027` を downgrade すると FK 違反になるため、
往復 4 本の選手を**テスト専用キー `roster-roundtrip`** へ付け替えた。

- **付け替えなし**: 4 本すべて failed(`Key (key)=(active) is still referenced from table "players"`)
- **付け替えあり**: 4 本すべて passed・同ファイル全 **21 passed**
- **掃除順では閉じない** — `pdf_export_records` と `player_move_records` が選手を参照し、
  その削除を migration のトリガが拒否する(`0009:230` / `0013:178`)。順序をどう定めても選手行を消せない
- 付け替えで失う検査面(`active` を参照した状態での往復)は、**ステップ 7 の実 DB 試験が別に持つ**

### ③ seed の実測(一時 DB・計測後に撤去)

`alembic upgrade head` 後に **`roster_status` 3 行・`game_type` 0 行**、表示名は 現役 / その他 / OB。
`downgrade 0026` でこの 3 行だけが消えた。

### ④ 射程外 4 件の起票(ステップ 8)

| | 件名 | カード |
| --- | --- | --- |
| ① | 試合区分(`game_type`)の seed | TSK-479 |
| ② | **`category` 強制(確定ゲート)** | **TSK-480** |
| ③ | `disabled` と「変更しない」の張力 | TSK-481 |
| ④ | 正本 `:2421` と DML 禁止検査の食い違い | TSK-482 |

**重複でないことを `docs/features/` 全走査と Notion 全文検索の両方で確認した**(結果は計画書 §4-5)。

**使える機構の限界(実測)**: タスク DB に**依存専用のリレーションが無い**(自己参照は `親タスク` / `サブタスク` の対だけ)。
親子を依存へ流用すると階層の意味が壊れるため、**各カードの「依存」欄へ②のページメンション**を置いた。
バックリンクで②から引けるが、**「先に入口を開く」ことを機械的に止めるものではない。**

### ⑤ U-M1 / U-G1 への申し送り(ステップ 10)

**U-M1(TSK-393)のカードへコメントを 1 件残した**(2026-10-05)。内容は 3 点 —
①依存 7 は本タスクで解消 ②依存 5 の「空席」は誤記(TSK-446 / PR #77・2026-09-25 マージ済・値は `record_and_aggregate`)
③**新たな前提**: `players` も `category` 強制の参照元なので、**選手の入口を開く前に TSK-480 が着地している必要がある**。

**U-M1 / U-G1 の両カードの「依存」欄へ TSK-480 のページメンションを置いた。**
**確認先は TSK-480 のバックリンク**(worklog の自己記録ではない)。

> **反映は U-M1 側で行う前提。** U-M1 の計画書は**別 worktree の未統合ブランチ**にあり
> (`origin` にブランチがまだ無い — 344 393 タブからの連絡)、**本ブランチのツリーに
> `docs/features/um1-player-roster-opponent/` は存在しない。** 本 PR では 1 行も触れていない。

### ⑥ 正本反映(ステップ 9)

`data-model.md` 10-3 節へ 2 項追記し、**版は 0.4 に据え置いた**(実装追随 — 設計書 7.6-3 前段)。
**差分は変更履歴 1 hunk と 10-3 節 1 hunk のみで、`:396` には触れていない。**
`docs/README.md` の索引を現行化し、`check_docs_status.py` は 17 documents scanned, 0 violations。

### ⑦ 実装の敵対レビュー(ステップ 11)

| 周 | 判定 | 何が出たか |
| --- | --- | --- |
| **1** | `P0`0 / `P1`5 / `P2`3 | **別名束縛・`getattr` 経由で限定許可をすり抜けられた**(当方の変異試験はこの経路を測っていなかった)/ **シードと revision の双方へ同じ 4 列目を足すと全検査を通った** / **7.7-2 の記録を後から改変できた** / **正本の追記に規範文が混ざっていた** / **既存キー衝突時の方針が無かった** / 件数の直書き / `game_type` 0 行が恒久テストに無い / 逐行確認の対象列挙が不足 |
| **2** | `P0`0 / `P1`3 / `P2`2 | **1 周目で「残余」とした 3 件のうち 2 件は、理由そのものが誤っていた**(レビュアが実測で反証)/ **`game_type` 0 行の恒久試験が TSK-479 を将来落とす** / 白リスト化が `sa.text()` の正当な形を拒否していた |
| **3** | `P0`0 / `P1`1 / `P2`1 | **塞いだ形の外側がまた出た**(`sa.sql.insert` / `from sqlalchemy import insert` / `sa.table(...).insert()` / `op` の別名 import)。**列挙では終わらない型**と判断し、**保証範囲を宣言して止めた** / `op.get_bind()` の全面禁止が読み取り専用の用途も拒否していた |
| **4** | — | **満枠で中断**(掴んだ 2 件のみ処理: `sa.inspect(op.get_bind()).bind.execute(...)` / 履歴の `true` を `1` に変えると通る) |
| **5** | `P0`0 / `P1`1 / `P2`1 | 2 件目以降の記録の**変更前後を宣言と照合していなかった** / `schema_version` を読んでいなかった |
| **6** | `P0`0 / `P1`1 / `P2`1 | **系列を削除しても削除記録なしで通った** / `changes` の他要素の形を見ていなかった |
| **7** | `P0`0 / `P1`1 / `P2`0 | **同一受理の `A → 不在 → B` が通った** → **レビュアから終端条件を引き出した** |
| **8** | **`P0`0 / `P1`0 / `P2`0** | **収束。** 終端条件を満たし、`/pr` へ進んでよいとの判定 |

**2 周とも、当方が「閉じた」と思った面の外側から出た。**
**とくに 1 周目 `P1-1` は、当方のステップ 5 の変異試験 3 件がどれも触れていない経路だった**
(変異は「宣言との不一致」を測っており、「**検査器が呼び出しをそもそも見つけられない**」面を測っていなかった)。

**未反映の `P1` は 1 件だけ** — 3 周目 `P1`(未宣言 revision の DML の網羅)= **TSK-484**。
**2 周目 `P1-2`(7.7-2 記録の append-only)は、人間の判断(2026-10-05)で本 PR へ取り込み、TSK-483 を取り下げた。**
**TSK-484 は人間が「別タスク送りでよい」と明示した記録を証跡とする**(worklog の自己記録では足りない)。

**4 周目以降は「7.7 の台帳の作法」だけが争点だった** — append-only → 変更前後の鎖 → 削除記録 → **1 受理 = 1 記録**。
**7 周目に終端条件を引き出して閉じた**(「受理前後の基準状態と、その受理で追加した記録が表す遷移が一対一で一致すること」)。

> **3 周目で、TSK-483 を送る理由の 1 つ(必須チェックへの配線が要る)が誤りと判明した。**
> 既存の `backend` ジョブは `fetch-depth: 0` で `contracts/**` の変更でも起動するので、**同ジョブへ載せられる**。
> **撤回して計画書 §4-6 に記録した。** 残る理由(外部アンカーが要る / `check_frozen_baselines.py` を触らない決定)は有効。

### ⑧ 総合検証で出た是正 — **コア領域の二層機構が新しい paths を足せない**

ステップ 6 で作った一致検査を `backend/tests/` 直下へ置いたところ、
`tests/test_core_guard.py::test_all_schema_contract_assets_match_an_actual_core_area_path` が red になった
(`SCHEMA_CONTRACT_TOKENS` に `migrations` があり、revision のパスを読むファイルが機械導出で
スキーマ契約資産になる。`backend/tests/` 直下は既存の `paths` に無い)。

> **当方は当初「どの領域にも 1 件も追加できない」と報告したが、これは誤りだった。**
> **U-M1 タブと TSK-344 タブの双方から反証を受け、当方も機構へ直接当てて確認した**(2026-10-05)。

**正しい実測**(`validate_area_path_layers()` へ模擬入力):

| | 結果 |
| --- | --- |
| 据え置き領域へ**宣言を新設**して足す | **OK** |
| 取り込み済みの宣言を**自分の分だけに置換**して足す | **OK** |
| 取り込み済みの宣言へ**累積**する | **NG**(当方が踏んだのはこれ) |
| 宣言なしで JSON に追加 | NG |

**`AREA_PATH_ADDITIONS` は累積する台帳ではなく「いま追加中のものだけを載せる回転式の窓口」。**
**実務上の問題は「足せないこと」ではなく「足す手順が `core_guard.py:29` のコメント 1 行にしかないこと」。**
**[TSK-485](https://app.notion.com/p/3f093b75e68781af9bd4fc3d31b536c5) をその射程で起票し直した。** 両タブへ訂正を送った。

**本タスクの回避策 — 置き場を 2 度動かした**:

| | 置き場 | 結果 |
| --- | --- | --- |
| 当初 | `backend/tests/test_roster_status_seed.py` | **未登録で red** |
| 1 度目 | `backend/tests/db/test_roster_status_seed_contract.py` | **`test_ci_wiring` が red** — **`backend/tests/db/` 配下は全ファイルに `requires_db` の印を要求する**。本テストは DB を使わない |
| **2 度目** | **`tests/test_roster_status_seed_contract.py`**(リポジトリ直下) | **green**。スキーマ契約資産の母集団は **`backend/tests/**` だけ**なので登録の要求が掛からず、必須チェック `harness` で実行される |

**「登録済みの glob だから置ける」とは限らなかった** — `backend/tests/db/*` は **DB を使うテスト専用**だった。
**DB を使わない契約検査の置き場が、`backend/tests/` 直下(= 登録が要る)しか無い**のが実態。
**`areas[].paths` への登録は見送った**(宣言層は TSK-344 と U-M1 が使う。両タブと合意)。**TSK-485 の DoD へ入れた。**

### ⑨ 総合検証で出たもう 1 件 — 正本の digest の取り直し

`tests/test_check_shared_preconditions.py` が red。**`contracts/authz/shared-preconditions.json` が
`docs/design/data-model.md` の blob digest を固定している**ため、ステップ 9 の正本反映で取り直しが要った
(`f93b06e5…` → `d02b09ee…`・**1 行**)。循環は無く(`data-model.md` 側に同資産の digest は無い)、
develop 側の競合も無い(`85fce8a7` → `da5cef8c` で両方未変更。いずれも当方実測)。

**台帳の既知の型「凍結資産が直列化点になり、後続 PR が受理記録の再導出を払う」の実例。**

> **【2026-10-05 追記】上の記述は不完全だった。** **凍結点は 2 つあった**(下記 ⑩)。

### ⑩ CI が出した 2 件 — **ローカルの検証範囲を当方が絞ったために通り抜けた**

**PR #94 の `backend` ジョブが fail**(`harness` を含む他 11 ジョブは pass)。

| | 失敗 | 原因 | 是正 |
| --- | --- | --- | --- |
| ① | `test_manifest_is_bound_to_the_canonical_data_model` | **`contracts/db/schema-manifest.json` も `data-model.md` の SHA-256 を固定していた**。⑨ で `shared-preconditions.json` の blob digest だけを取り直し、**2 つ目を見落とした** | `canonical_source.sha256` を `6f5b6d59…` → `521be209…`(**1 行**) |
| ② | `test_c12_truth_table_and_migration_round_trip` | **`0027` を足したことで head が先へ進んだ**。同試験は `0026` まで戻してから `command.current(check_heads=True)` を呼ぶが、**`0026` はもはや head ではない** | 直前へ `command.upgrade(config, "head")` を **1 行**足し、理由を 3 行のコメントで残した。**試験の意図は変えていない** |

**なぜローカルで出なかったか** — **当方が backend の実行範囲を「影響範囲」として自分で選び、全件を回さなかった。**
**①②はいずれもその外にあった。** **絞った実行は 129 passed で緑・終了コードも 0** なので、**手元の観測からは選び落としが原理的に見えない。**
**当方は PR 本文と Notion へ「/check 全グリーン」と書いた** — **選んだ母集団の中では正しく、外では偽だった。**

**副産物の発見**: **計画書 §4-4 の逐行確認の対象表に、存在しないファイルを指す行が 1 つ残っていた**
(置き場を 2 度動かしたあと、**移動元の行を消し忘れた**)。**人間へ渡す一覧なので機械は何も言わない。**
**表を 12 行へ作り直した。**

**是正後の検証は backend 全件(CI と同じ `uv run pytest -c pyproject.toml`)で行う。**

**台帳へ 3 件追記した**(⑩ の 2 件 + 対象表の件)。


## 結果サマリ(ステップ 12 クローズ処理・2026-10-05)

### 実装したもの

| | 成果物 |
| --- | --- |
| **語彙の正** | `contracts/seeds/roster-status.json`(3 行。表示名は要件書 `:171` から逐語) |
| **DB への投入** | `backend/migrations/versions/0027_seed_roster_status.py`(`op.bulk_insert()` / downgrade は `category` と 3 キーに限った `DELETE`) |
| **凍結基準の宣言**(設計書 7.7-1) | `contracts/migrations/seed-allowlist.json`(限定許可 + **更新記録 1 件**) |
| **検査器** | `backend/tests/test_migration_hygiene.py`(白リスト方式の DML 禁止 + **7.7-2 台帳の 4 検査** — 鎖 / append-only / 削除記録 / **1 受理 = 1 記録**) |
| **三者一致** | `tests/test_roster_status_seed_contract.py`(シード資産 ↔ 実 revision〔AST〕 ↔ 要件書 4.0-3。負例 5 件) |
| **実 DB** | `backend/tests/db/test_roster_status_seed_db.py`(FK / NOT NULL / 往復 / 既存キー衝突) |

### 正本へ反映したもの

| 正本 | 反映 | 版 |
| --- | --- | --- |
| `docs/design/data-model.md` | 10-3 節へ在籍区分 3 キーと誤参照の事実(2 項)+ 変更履歴 1 行 | **0.4 据え置き**(実装追随 — 7.6-3 前段) |
| `docs/development/harness-evaluation.md` | **`## 候補` へ 1 件 + 既存候補 3 件へ実測** | **1.0 据え置き**(`H-*` を与えない) |
| `docs/README.md` | 上記 2 行の最終更新日を現行化 | — |

**正本外で同一 PR が運ぶもの**: `contracts/authz/shared-preconditions.json` の **blob digest 1 行**
(`f93b06e5…` → `d02b09ee…`。`data-model.md` を直したことによる追随 — 下記 ⑨)。

### 台帳への追記の判断(`/pr` 手順 1-3)

**該当する**と判断し、**`## 候補` へ 1 件追記・既存候補 3 件へ実測を追記**した。**`H-*` は与えていない**
(いずれも 1 タスクの観測か、既存候補の事例追加であり、制御目的の典拠が無い)。
内訳は台帳の変更履歴 2026-10-05 行のとおり。

### 最終検証(2026-10-05)

| 検査 | 結果 |
| --- | --- |
| ハーネス `uv run pytest tests/` | **2868 passed / 0 failed** |
| backend 影響範囲 | **129 passed**(`tests/db/test_alembic_migrations.py` は **21 passed**) |
| `ruff format --check` / `ruff check` / `ty check`(backend・ルート) | すべて通過 |
| `check_docs_status.py` | **17 documents scanned, 0 violations** |
| `check_plan_docs_sync.py` | **exit 0** |

## 未決・次の一歩

- **人間の逐行確認が必須**(コア領域 — ADR-001 / 設計書 6.3)。**対象は計画書 §4-4 の 10 行の表**
  — シード資産の全行 / seed 専用 revision の `op.bulk_insert()` と限定削除 / **宣言資産と検査器の変更** /
  三者一致検査 / 実 DB 試験 / `data-model.md` の追記。
  **`tests/test_roster_status_seed_contract.py` は `areas[].paths` に未登録**なので
  機械判定には出ない。**表で明示的に対象へ入れてある**
- **未反映の `P1` は 1 件**(**TSK-484** — 未宣言 revision の DML の網羅)。
  **人間が「別タスク送りでよい」と明示した記録を証跡とする**
- **本 PR 自身の「1 受理 = 1 記録」は比較検査の対象外**(`merge-base` `85fce8a7` に台帳が無く**初回例外**を通る)。
  **正確な言い方は「現行資産には初回記録が 1 件あり、履歴の内部整合を確認した」まで**
- **敵対レビュー 4 周目はレビュア側が満枠(`Selected model is at capacity`)で判定前に打ち切られた**
  (掴んだ 2 件のみ処理)。**「8 周すべてが判定を返した」ではない**
- **`category` 強制(TSK-480)は未着手。** これが着地する前に U-M1 が選手の入口を開くと、`game_*` を在籍区分として保存できる状態が残る
