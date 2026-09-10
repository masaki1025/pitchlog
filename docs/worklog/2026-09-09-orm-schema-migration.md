---
date: 2026-09-09
topic: ORM 導入(SQLAlchemy 2.x・Alembic)と models・migration — TSK-343
branch: feature/orm-schema-migration
---

# 作業ログ: 2026-09-09 ORM 導入と models・migration(TSK-343)

## やったこと

- **/task-start**(2026-09-09): Notion [TSK-343](https://app.notion.com/p/3d593b75e68781469990ca4e61fca9d2) を取得し、
  ブランチ `feature/orm-schema-migration` + worktree `../pitchlog-worktrees/feature-orm-schema-migration` を
  `origin/develop`(`1424d67`)から作成。計画書雛形 `docs/features/orm-schema-migration/plan.md` と本 worklog を作成。
- **開始条件の充足を確認**: TSK-342 の成果 `docs/design/data-model.md` は frontmatter `status: approved`
  (確定ゲート 13 周・PO 承認 2026-09-09)。PR #50 が develop へマージ済み(`1424d67`)。
- **/investigate**(2026-09-09): 調査サブエージェント **4 並列**(既定 3 本 = spec-checker / legacy-analyst /
  decision-tracer + 衝突 5 箇所の実測 1 本)。結果を
  [`docs/features/orm-schema-migration/research.md`](../features/orm-schema-migration/research.md) へ統合した。
  **エージェント報告の食い違い・誤りは原典を自分で読んで 7 件裁定した**(research.md 6 節)。
  主な裁定: ① 88 列の正本は `docs/legacy/research/data-layer.md`(`docs/design/data-layer.md` は**存在しない**)
  ② 接続 URL の統一で配線検査が壊れるという「深刻度 高」の報告は、**範囲を切れば消える罠**
  (テスト用 DSN は `psycopg.connect()` / `conninfo_to_dict()` に渡る libpq conninfo で、
  SQLAlchemy URL 形式 `postgresql+psycopg://` を入れてはいけない)
  ③ NFR-019 の種別は **4 種**((a) 一致性 /(b) 越境 /(c) E2E /(d) 同期故障系)で「単体」は列挙に無い。

- **/plan の完了と承認**(2026-09-10): 敵対レビュー **6 周**・指摘 **67 件を全件採用**(不採用 0)。
  指摘総数の推移 **18 → 14 → 10 → 10 → 6 → 9**。**4 周目で収束方針を「述語の弱化」へ転換**し、
  レビュー側も「妥当」「より強い exact-set への復帰は要求しません」と評価した。
  **6 周目で打ち切り、人間が承認**(`承認: 済(2026-09-10・山田正輝)`・承認コミット `3ecf4a2`)。
  **28 実装ステップ / DoD `D1`〜`D18` / 申し送り `S-1`〜`S-7`。**
- **承認前条件 2 件を履行**: **TSK-354**(FR-018 のロック方式)・**TSK-356**(FR-031 の 88 列往復)を起票。
  どちらも**正本が実装計画へ送りながら送り先を名指ししておらず所有が空白だった穴**。
- **develop の取り込みと引用の整理**(2026-09-10): TSK-348 が **PR #51** でマージされ
  `data-model.md` が **v0.1 → v0.2 approved** になったため、v0.1 基準の行番号引用が **+2〜+5 ずれた**。
  **実装ステップ表と DoD の 20 トークン(57 出現)を節番号 + 要求 ID へ貼り替え**、
  **台帳引用を安定 ID `H-nn` へ寄せ**、**説明文中の 182 件は基準を明記**した。
  **v0.1 → v0.2 のずれ計算で 273 行参照のうち 272 件が完全一致**することを機械照合で確認
  (不一致 1 件 = TSK-348 がまさに是正した 3-2 節の `search_path` 契約)。
- **他セッションとの直接調整**(2026-09-10): `pitchlog-89`(TSK-317)・`tsk235-dsl`(TSK-235)・
  `fable`(相談役)と直接やりとりし、**共有資産の所有・マージ順序・技術的実測**を相互確認した。
  結果は計画書 **4-14 節**。

## 決定

- **slug は `orm-schema-migration`**(タスク名由来の `data-model-schema-orm` は使わない)。
  **理由**: `docs/features/data-model-schema-orm/plan.md` は TSK-342 が使用済みで、`scripts/feature_status.py` は
  plan の期待 slug をブランチ名から導出する(`expected_feature_slug` — `feature/<slug>` の `<slug>`)ため、
  同名にすると現在地導出が「plan 重複」になる。
- **重さ分類 = コア領域(テナント分離)**。Notion タスクの制約欄どおり — `sol xhigh`・敵対レビュー・
  人間の逐行確認必須(PR 作成者以外)。frontmatter に反映済み(根拠は計画書 4 節で明記する)。
- **`tests/test_ci_wiring.py:1272` は 10.1 改訂と同一 PR・同一コミットで運ぶ**(人間決定 2026-09-09)。
  **理由**: Notion タスクが「② 依存追加は ① と同一コミット必須」と定めており、分けると依存追加の瞬間に
  旧形の assert が必ず落ちる red の中間コミットができる。設計書 6.1 の段階実装は各ステップに合格条件を
  要求するので、その中間状態には合格条件が書けない。裁定 `R-2`(models と 10.1 改訂を同一タスクに保つ)とも整合。
  → **1 コミットの内容** = 設計書 5.1 の ORM 留保解除 + 10.1 の「ORM は入れない」改訂 +
  `backend/pyproject.toml`・lock の依存追加 + `test_psycopg_is_exact_product_dependency_without_orm_packages` の更新。
- **/investigate**(2026-09-09)の結果を受けた人間の裁定 4 件(**2026-09-09・山田正輝**)。
  詳細な典拠は [research.md](../features/orm-schema-migration/research.md) の該当節を参照する(本 worklog に複製しない)。

  | ID | 事項 | 裁定 |
  | --- | --- | --- |
  | **`Q-1`** | 設計書 5.1・10.1 の改訂のゲート水準(`R-5` の受け皿が消滅) | **(A) 設計書自身を `/finalize-doc` で回す**(7.6-3 後段)。**版を v1.14 へ繰り上げる** |
  | **`Q-2`** | 「型を損失なく受け取る境界」の定義が正本に無い | **本タスクで線を引く** — 既存の型分離の型(**原本事実をそのまま保持 + 解決結果は別の nullable 列**)を 88 列側へ一般化する |
  | **`Q-3`** | DoD の 2 条件(exact-set テスト / `downgrade`)に典拠が無い | **両方維持し「正本の典拠なし・本計画の自主基準」と明記する** |
  | **`Q-4`** | マージ順序 | **TSK-348 → TSK-317 → 本タスク**(当初の原案どおり) |

- **`Q-1` は裁定 `R-5` の変更である**(記録しておく)。`R-5`(TSK-335・2026-09-08)は
  「**版は上げず**、差分を確定ゲートの敵対レビュー対象に含める」という折衷だったが、
  相乗り先の `data-model.md` の `/finalize-doc` が TSK-342 の approved 化で閉じたため受け皿が消滅した。
  **本裁定は「版は上げず」を外して 7.6-3 後段(版繰り上げ + 7.3 の確定ゲート)を採る**もので、
  `R-5` より**厳しい側**へ寄せた判断である。
  → **帰結**: 設計書の変更履歴表へ **v1.14** 行を追記し、`docs/README.md`(索引)を現行化する。
  `/finalize-doc` の**反映周コミットは `反映<r>周目` 記法**(ステップ記法を付けない — 設計書 6.1)。
- **`Q-4` の副作用(有利な方向)**: 本タスクが最後になるので、**TSK-317 のマージ済み `conftest.py` の上に
  自由に追記できる**。実衝突として唯一残っていた `backend/tests/db/conftest.py` の競合が**順序で解消する**。
  `.claude/core-areas.json` も TSK-317 の改訂 3 と逐次になるので競合しない。

- **/plan**(2026-09-09〜09-10): 計画書 6 節を記入し、密度が高いので
  [design.md](../features/orm-schema-migration/design.md) へ詳細設計を分離した。
  **敵対レビュー(コア領域 = sol xhigh)を 3 周**回した。

  | 周 | 日付 | 指摘 | 採用 | 判定 |
  | --- | --- | --- | --- | --- |
  | 1 周目 | 2026-09-09 | `P0` 4・`P1` 11・`P2` 3 = **18 件** | 全件(不採用 0) | 差し戻し |
  | 2 周目 | 2026-09-10 | `P0` 3・`P1` 8・`P2` 3 = **14 件** | 全件(不採用 0) | 差し戻し |
  | 3 周目 | 2026-09-10 | `P0` 2・`P1` 5・`P2` 3 = **10 件** | 未反映 | 差し戻し |

  **指摘総数の推移 18 → 14 → 10**(`P0` は 4 → 3 → 2)。
  **1 周目の 18 件は 2 周目で 12 件が閉鎖**、**2 周目の 14 件は 3 周目で 7 件が閉鎖・3 件が部分解決・
  3 件が未解決・1 件が「妥当だが未履行」**(FR-018 の起票)。

- **3 周目レビューの総括(原文)**: 「**中心問題は、正本に対する独立した全数集合がまだ作れていない**ことです。
  3層、manifest、不変列、ライフサイクルの各定義を**増やしただけでは閉じず**、
  正本から生成した期待集合または明示的な逐行受入証跡が必要です」。
  内訳の自己申告は **「設計が破れるもの」8 件 / 「定義の言い換えによる残滓」2 件**。

- **`areas[].paths` は完全列挙ではなく glob にする**(2026-09-10 の是正)。
  **当初「完全列挙」を要求していたのは誤りで、しかも脆い側だった** —
  完全列挙だと**後から足したファイルが黙って未登録**になり、台帳 `H-12`
  (コードを入れたのに paths が未充填で非発火)の再発型を自分で作る。
  **根拠 3 つ**: ① `scripts/core_guard.py:222-227` は `guard_paths` = 完全一致 /
  `areas[].paths` = `fnmatch`(**`*` が `/` を跨ぐ** — 実証済み)の 2 系統
  ② **既存の慣行に glob がある**(`tenant-isolation` に 4 件・`sync-protocol` に 1 件)
  ③ 設計書 `:368` の規則④「**過剰包含は…含む側に倒す**(fail-closed)」。
  **完全列挙が必要なのは `guard_paths` のみ**(完全一致集合なので glob が効かない)。
  **本タスクは `guard_paths` を増やさない。**
- **設計書 10.1 は本タスクが単独で改訂する**(裁定不要で確定)。
  TSK-317 の「`backend` 行に 1 行足す」提案は**同タスク自身の DoD「10.1 の差分が 0」を破る**ため
  指摘し、**撤回された**。**実測でそもそも追加配線が不要**とも判明
  (`ci.yml` の `backend` ジョブは既に postgres サービスとロール DSN 2 本を持ち、
  使い捨てクラスタは Docker CLI 経由)。**10.1 を触るのは本タスク(v1.14 の改訂)と
  TSK-235(版据え置きの実装追随・本タスクの変更履歴行の下に追記)の 2 者。**
- **`core-areas.json` の集約は行わない**。TSK-317 の `guard_paths` 追加(改訂 3 の `S-8`)と
  本タスクの `areas[].paths` 登録は**別配列で衝突しない**。集約の利点は
  「人間の逐行確認が 1 回で済む」だけなので**人間の判断待ちにする**。
- **DB テストの罠の台帳起票は TSK-317 が担う**(実例 4 回分と復旧手順を持つため)。
  **本タスクの `/pr` では参照に留め、重複起票しない。**

## 未決・次の一歩

> **以下 3 件は 2026-09-10 に完了した**(記録として残す)。
> ① 「/plan までで止める」→ **/plan 完了・計画承認済み** ② 「人間が `/plan` を実行する」→ **実行済み**
> ③ 「計画書で明示的に書くこと」5 項目 → **全項目を計画書へ反映済み**
> (競合の所有 = 3 節の別枠宣言 / 同一コミットの理由 = 4-2 節 / マージ順序 = 4-6 節 /
> `Q-1`〜`Q-3` = 4-3・4-4 節 / 裁量 4 点 = design.md 2・4・5・6 節)。
>
> **現在の次の一歩は本節末尾の「起床した人間へ」を見る。**
- **競合 7 箇所**(5 箇所は人間の申し送り・6 番目は本調査・7 番目は TSK-235 のタブからの申し送りで判明):
  `tests/test_ci_wiring.py:1272`(改訂 3 とのみ衝突)/ 設計書 10.1(**衝突なし** — TSK-317 が手放し済み)/
  `backend/tests/db/conftest.py`(**唯一の実衝突**。`Q-4` の順序で解消)/
  `backend/tests/db/environment-expectations.json`(**衝突なし** — TSK-317 の合格条件が「差分 0」)/
  **`backend/uv.lock`**・`backend/pyproject.toml`(**衝突なし**。なおルート `uv.lock` も実在するが ORM 検査の対象外)/
  **`.claude/core-areas.json`**(申し送りに無い潜在衝突。**その後の実測で TSK-317 は `guard_paths` 側・本タスクは `areas[].paths` 側と判明し別配列で衝突しない**)/
  **設計書 10.1 の後続改訂**(**TSK-235 も触る**。TSK-317 は撤回 — 計画書 4-14 節)
- **依存 TSK-344**(越境テスト再実行ゲートの実行 — 実スキーマ適用後の再実行・TSK-342 の裁定 `A-2`)。
  `docs/design/data-model.md` 12-4 節(2439 行)の**通過条件は「① RLS のポリシーとロールの DDL が実スキーマへ
  適用されている ② その実スキーマに対して越境テストが green である」**(原文を確認済み)。
  **① の「実スキーマ」は本タスクの migration の成果**であり、**RLS の DDL 自体は本タスクの射程外**(裁定 `A-2`)。
  したがって TSK-344 は **本タスク(スキーマ)と TSK-317(RLS DDL)の両方**が入らないと通過判定ができない。
  → マージ順序の決定に直結する。
- **関係タスクの実状**(Notion 実測 2026-09-09): TSK-342 = 完了 / TSK-348(`data-model.md` v0.2 の改訂ゲート・
  search_path 契約の是正 1 件)= 未着手だが worktree `feature/data-model-v0-2` は実装完了・/pr 前 /
  TSK-317 = 進行中(7/21)/ TSK-344 = 未着手 / TSK-250 = 進行中。

## 起床した人間へ — 裁定事項 2 件と申し送り

**メインタブは存在しない**(`ListAgents` に見当たらず、`fable` は担当タスク無しの相談役セッション)。
**この節が申し送りの確定場所である。**

### 裁定事項(急ぎではない)

| # | 事項 | 状況 |
| --- | --- | --- |
| **①** | **`scripts/feature_status.py` の `S-7` の 1 行修正を起票するか** | **修正は 1 行**(`:999` の allowlist へ `merge_allowed` を足す)。**分類漏れであって仕様ではない**(直上に `merge_unknown` 専用の分岐が別にある)。**`fable` も独立に実測して同じ結論**。**develop への変更なのでタスク起票 + 人間承認が要る**ため、3 セッションとも着手していない。**実例**: 本 worktree(マージ `51bf73b` を持ち「実装状況: 不明」)と `feature/data-model-canonical`(マージ `128be83`) |
| **②** | **`core-areas.json` の登録を TSK-317 の改訂 3 と集約するか** | **集約しなくても衝突しない**(別配列)。利点は**逐行確認が 1 回で済む**ことだけ。**双方とも保留で合意済み** |

### 本タスクの現況

- **計画承認済み・実装未着手。** 着手条件は **TSK-317 の本体 PR のマージ**(裁定 `Q-4`)。
  **TSK-317 は 14/21**(残り 17・20・21 が重く、そのあと改訂 3)。**待ち時間は短くない。**
- **裁定待ちの事項は残っていない**(設計書 10.1 は上記のとおり解消)。
- **着手時にやること**: ① **衝突 6 箇所の差分を再調査**(基準が動くため)
  ② **`S-1` の未反映 2 件**(6 周目の指摘のうち Claude が出力の末尾のみ保存して本文を落とした分)を
  **計画レビュー 1 周で再取得**。

### マージ順序

`TSK-348(済・PR #51)→ TSK-317(14/21)→ **TSK-343** → TSK-235(TSK-355 待ちで停止)→(TSK-317 改訂 3)`

### 他タブから受けた実測(実装時に効く)

- **`ALTER TABLE ... OWNER TO` は対象表へ触った接続が 1 つでも `idle in transaction` で残っていると永久に待つ**
  (ACCESS EXCLUSIVE 待ち。読み取りだけの接続でも同じ)。TSK-317 は 1 点 10 分 48 秒の「処理時間」が
  実は待ち時間だったと `pg_blocking_pids` で確定。診断は `pg_stat_activity` × `pg_blocking_pids(pid)` ×
  `state = idle in transaction`。→ 申し送り `S-6`
- **DB テストの強制終了で使い捨てクラスタのコンテナと `pitchlog_test_role` が残り、以後の全 DB テストが error**
  (fixture が fail-closed で弾く)。復旧は `docker rm -f` → `DROP OWNED BY` → `DROP ROLE`
  (**順序が逆だと依存で失敗**)。**TSK-317 が 2026-09-10 に 4 回踏んだ。** → 同 `S-6`
- **`fnmatch` の `*` は意図より広く当たる** — `backend/*conftest.py` は将来
  `backend/src/pitchlog/conftest.py` にも当たる。**glob 新設時は意図した集合と実際に当たる集合の差分を確認する。**
  → ステップ 28 の合格条件

### 他タブの待ち状況(2026-09-10 時点)

| タブ | タスク | 状態 | ブロッカ |
| --- | --- | --- | --- |
| `pitchlog-89` | **TSK-317** | 実装中 **14/21** | なし(ステップ 15 のロック待ちを修正中)。**残り 17・20・21 が重く、そのあと改訂 3** |
| **`tsk343-orm`(本タブ)** | **TSK-343** | **承認済・着手待ち** | **TSK-317 の本体 PR のマージ** |
| `tsk235-dsl` | **TSK-235** | 停止(記録の確定まで) | **TSK-355(移行状態の条文化)が未着手** |
| `fable` | — | 相談役(担当タスク無し・develop 上・変更 0 件) | — |

**`TSK-355` を `/task-start` する新しいタブが要る** — TSK-235 のクリティカルパスはこれだけになった。
**1 タスク = 1 worktree の規律があるので既存タブでは開けない**(TSK-235 のタブもそう判断している)。

## ステップ 1 完了と DB テストの切り分け(2026-09-10)

**ステップ 1(`71c3d86`)を完了した。** 合格条件 6 件はすべて worktree で実測確認した
(「ORM は入れない」0 件 / 「設計フェーズで最終確定」0 件 / 5.1 の採用理由と却下案 3 件 /
変更履歴の最大版 v1.14 = `docs/README.md` / lock ↔ pyproject 一致で SQLAlchemy major = 2 /
ORM 契約テスト 6 passed)。`/check` はルート `ruff`・`ty` green で pytest **1188 passed**、
backend は `ruff format` 35 files unchanged・`ruff check` green・`ty check` green・非 DB **60 passed**。

### 罠 1 — DSN のスキームが DB 必須テスト 102 件を全滅させていた

`tests/db` が **102 件すべて setup error** になっていた。原因は環境変数
`PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN` のスキームが `postgresql+psycopg://` で、
これは **SQLAlchemy の URL 形式であり libpq の conninfo ではない**こと。psycopg の
`conninfo_to_dict` が `missing "=" after ...` で弾いていた。**`research.md` 4-3 節が
文書化した罠がそのまま発火した。**

スキームを外すだけで通る(値の他の部分は正しい。PostgreSQL 17.11 へ実接続して確認済み):

```
PITCHLOG_TEST_ADMIN_DSN="${PITCHLOG_TEST_ADMIN_DSN/+psycopg/}" \
PITCHLOG_TEST_ROLE_DSN="${PITCHLOG_TEST_ROLE_DSN/+psycopg/}" \
uv run pytest -c pyproject.toml tests/db -q
```

→ **102 setup error が消え、100 passed まで到達した。** 詳細設計 7-2 節へ追記した。

### 罠 2 — その setup error が develop の既存 red 11 件を隠していた

102 件が消えた結果 **11 failed** が露出した。**すべて TSK-317 の認可テスト**で、
develop でも同じ 11 件が失敗する(**失敗テスト ID を diff して差分 0** で確定)。

**単一原因**: TSK-317 PR #1(#52)の `14973f6` が凍結 body へ判定注記
`MANAGEMENT_TARGET_GRANT_GROUP_MATCH` を追加し body 側を **8 件**にしたが、
exact-set の相手側 2 箇所が **7 件のまま**。

| 資産 | 注記の件数 |
| --- | --- |
| `contracts/authz/function-bodies/functions/apply_representative_grant_change.sql` | **8**(`:30` に GROUP_MATCH) |
| `backend/tests/db/test_authz_management_probe.py:331` `_AUTHORIZATION_FAILURE_CASES` | **7** |
| `backend/tests/db/test_authz_toctou.py` の 2 文 mutant SQL | **7** |

`_assert_failure_case_contract`(probe:370-378)と `_assert_mutant_decision_set`(toctou:515-528)が
どちらも `_decision_ids_from_body()` と exact-set 比較するので 8 対 7 で必ず red。
`git log -S'MANAGEMENT_TARGET_GRANT_GROUP_MATCH' -- backend/tests/db/` は **0 件**で、
テスト側には一度も入っていない。manifest 再導出(`8a72a93`)と MC/DC 写像(`573fb63`)は
追随済みなので、**この 2 ファイルだけが取り残された**。

**修正は TSK-317 の所有範囲**(3 節の所有境界で `backend/tests/db/` は TSK-317)なので触らない。
**`pitchlog-89` へ報告済み**(スキームの誤診の訂正も併せて — 同タブは「サンドボックスから
PostgreSQL に到達できない」と判断していたが、実際は DSN のスキームだった)。
申し送り **`S-9`** として計画書 4-12 節へ記録した。

### 構図として記録すべきこと

`14973f6` のコミット本文は「機構は設計どおり動き、人手が漏れた」と書いている。
今回はその**二段目**が見えた — **機械の exact-set は片側を増やしたことを正しく捕まえていたのに、
その red が DSN スキーム起因の setup error に隠れて誰にも見えなかった**。
**fail-closed な setup error は、その先の実体的な red を全部飲み込む。**
→ 症状の見分け方を詳細設計 7-2 節へ書いた(setup error が 102 件そろっていればスキームの疑い、
個別の `AssertionError` なら実体の red。前者は後者を隠すので前者を先に消す)。

### 他タブの待ち状況の更新(2026-09-10)

| タブ | タスク | 状態 | ブロッカ |
| --- | --- | --- | --- |
| `pitchlog-89` | **TSK-317** | **PR #1(#52)マージ済 → PR 段階** | **develop に red 11 件を残している**(本タブから報告済) |
| **`tsk343-orm`(本タブ)** | **TSK-343** | **実装中 ステップ 1/28 完了** | なし(`S-9` の 11 件は除外して進める) |
| `tsk355-transition` | **TSK-355** | 着手済(別タブが起票された) | — |
| `tsk235-dsl` | **TSK-235** | 停止 | **TSK-355** |
