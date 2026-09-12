---
feature: operation-event-immutability
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-12・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)
notion: https://app.notion.com/p/3d993b75e68781798b23e74aa4bc8edc
branch: fix/operation-event-immutability
created: 2026-09-12
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 確定済みイベントの書き換えを防ぐ(不変列の宣言漏れと種別条件 CHECK の不足)

## 1. 背景・目的

**TSK-343(ORM 導入)はマージ済み**(PR #55 `5b928cb` / 追随の #56 `9c4791a`、develop は green)。
**マージ後に敵対レビューを実施し `P0` 3 件 / `P1` 6 件を検出した。** 本計画は **`P0` 3 件**を直す。

**Notion**: https://app.notion.com/p/3d993b75e68781798b23e74aa4bc8edc

### 直す欠陥

**`P0-1` / `P0-2`** — `operation_events` の 21 列中 **9 列**が `immutability` の
`protected_columns` にも `allowed_update_columns` にも入らず、`BEFORE UPDATE` トリガの保護外。

- **`is_tombstone` を `false` へ更新すれば墓標を通常イベントへ書き換えられる**
- **`target_generation` / `target_d1` / `expected_version` を別の有効なスロットへ更新すれば、
  確定済みの変更イベントを別イベントへ付け替えられる**(FK も対の NULL 性 CHECK も通る)

正本 `data-model.md:946` の **`W1`**「**確定済みイベントの修正・削除は、新しい変更イベントとして
追記する。既存イベントを書き換えない**」に反する。

**`P0-3`** — 正本 5-3 節「履歴文脈(`C12`)」が
「**`V2`・`V3`・`V6`・`V8`・`V9`・`V10`・`V11` は種別条件付きなので `NOT NULL` にできない。
→ 種別ごとの `CHECK` 制約で必須性を表す**」と定めるが、現行の CHECK 8 本は一部しか表していない。
**選手交代・タイブレーク開始・試合終了宣言で `D2` が NULL のまま通り、undo が状態差分を持て、
undo が対象参照なしで通る。**

### 調査で分かった構造(レビューの指摘より広い)

| 事実 | 実測 |
| --- | --- |
| 未分類列がある表は **24 / 45**(`play_rows` 36 列・`games` 15 列・`participation_intervals` 10 列ほか) | manifest を走査 |
| **`players` は `protected_columns=["id"]` を宣言しているのにトリガが存在しない** | 全 36 トリガを migration から抽出して突合 |
| 不変列マトリクスの検査の母集団は **5 表の名前列挙**(`test_immutability_matrix.py:55-61`) | 同ファイル冒頭が「全数ではない」と明記 |
| **「宣言漏れ」も「トリガと `protected_columns` の全表突合」も検査が存在しない** | テスト・モデル・CI を走査 |
| 現行 C-7 と C-8 は **`event_kind='play_input'` の墓標行で同時に満たせない** | C-7 が `state_diff IS NOT NULL`、C-8 が `state_diff IS NULL` を要求 |

**未分類 = 欠陥ではない。** `games.status` の遷移も `play_rows` の再投影も正本が許している。
**欠陥なのは「正本が書き換えを禁じた表で未分類」**であり、それは `operation_events` である。

## 2. スコープ

### やること

1. **`Immutability` の表現力拡張** — `conditional_update_columns` / `coverage`(**既定値なし**)/
   `unclassified_handoff` を追加し、全 45 表に宣言させる
2. **`players` の `BEFORE UPDATE OF id` トリガ新設** — 宣言と実装の乖離の解消
3. **全表の「宣言 ⇒ 強制」突合検査の新設**
4. **`operation_events` の 9 列分類とトリガ拡張**(9 → 18 列)
5. **`C12` の種別条件マトリクス**(12 参加区分 × 7 値 = 84 セル)と、そこから生成する CHECK

### やらないこと(受け取り先つきで送る)

| 送る先 | 内容 | 理由 |
| --- | --- | --- |
| **follow-up A** | 23 表の未分類列の解消 | 各表の可変性は正本の読解が要り、**実装が正本の判断を代行することになる**。`coverage=PARTIAL` + 受け取り先 ID で可視化する |
| **follow-up B** | `V10` 禁止 6 セルと墓標の `V10` 必須 | **改訂版(#9)に識別列が無く** `event_kind` だけでは通常版と区別できない。墓標の `V10` の物理表現も正本が定めていない |
| 既存 `P-58` の受け取り先 | 状態補正(#7)の採否と列挙 CHECK への追加 | `data-model.md:833`「Must 前提として組み込まない」 |
| 正本改訂タスク | 墓標行の `event_kind`(`D-1` の結果を 5-3 節へ) | 本計画は正本を改訂しない |
| **follow-up C** | 挙動負例(実 UPDATE)の全表化 | 表ごとの FK グラフを満たす行 fixture が要る。**本計画は構造突合を全 45 表・挙動負例を 7 表に限り、それを宣言する** |

**`P1` 6 件は別 follow-up。** うち受入証跡 4 行の再判定は**本計画の後**でないとできない
(`C12` の CHECK を足すと `N7` 028・030 の判定が変わる)。

## 3. 影響する正本

| 正本・資産 | 変更内容 | ゲート |
| --- | --- | --- |
| すべての正本 | **反映なし**(`docs/design/` は読むだけ) | — |
| [ハーネス運用評価台帳](../../development/harness-evaluation.md) | **`## 候補` へ 1 件追記**(**offline 検証が実 DB の失敗を隠す** — revision ID 33 文字が `alembic_version.version_num VARCHAR(32)` に入らず 実 DB テスト 29 件を落としたが、`upgrade` の DDL は流れるため offline SQL 生成では green になった)+ 変更履歴表へ 1 行 | **PR レビューで可**(7.6-3 前段。**`H-*` の新規採番はしない・版は上げない**) |

| [ドキュメント索引](../../README.md) | **台帳行の要約を現行化**(候補 1 件の追記に追随。版は据え置き) | **PR レビューで可**(7.6-3 前段) |

**正本体系外だが同一 PR で運ぶもの**: `contracts/db/schema-manifest.json` /
`backend/src/pitchlog/db/` / `backend/migrations/versions/` / `backend/tests/` /
`.claude/core-areas.json`(新設資産の登録) /
`docs/features/orm-schema-migration/acceptance-sheets/`(`N3`・`N7` の再生成)。

## 4. 実装方針

**重さ分類は コア領域**。`operation_events` は同期プロトコル領域で
`.claude/core-areas.json` の `sync-protocol` に登録済み。**敵対レビュー + 人間の逐行確認が要る。**

### 決定事項(2026-09-12・山田正輝)

| # | 争点 | 決定 |
| --- | --- | --- |
| **D-1** | 墓標行の `event_kind`(**正本に記述なし**) | **置換した版の種別を引き継ぐ。** `#1`〜`#7` の種別条件に **`NOT is_tombstone` を行述語**として付ける。正本への申し送りにする |
| **D-2** | `migration_unverified` の可変性 | **保護**(fail-closed)。検証フローが要るなら新イベントか別表で表す |
| **D-3** | 射程 | **ラチェット型**。`coverage` を全 45 表に宣言させ、全表突合の検査を新設する |

**`D-1` の根拠**: `sync-protocol.md:591`(`K5`)は墓標を「同じ `D1`・**空の内容**・新しい `D5`・
未送信状態へ不可分に置換」と定める。`payload = '{}'` と `state_diff IS NULL` は「空の内容」の
写像であり、**種別条件は内容ではなく参加区分に掛かる**。墓標は参加区分 **#8** であって #1 ではない
(`data-model.md:834`)。「`play_input` の墓標を禁止する」解は、`K5` が内容起因で拒否された
**任意の** `D1` スロットに墓標を生成すると定めているため、**最頻ケースで実行不能になる**。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

単一 head。`0023_play_runner_status_source` → `0024` → `0025` → `0026`。
**`CREATE POLICY` / `CREATE ROLE` / `create_all()` を使わない。DDL と DML を混ぜない。**

| # | 内容 | 合格条件 |
| --- | --- | --- |
| 1 | **`Immutability` の表現力拡張**(宣言のみ・DDL なし)。`model_metadata.py` に 3 キーを追加し、全 45 モデルと manifest へ `coverage` を機械的に付与(未分類 0 の **21 表** = `EXHAUSTIVE`、**24 表** = `PARTIAL` + 受け取り先 A)。`recording_generations.conditional_update_columns={"confirmed_watermark"}` | `__post_init__` が「3 集合の重複」「`PARTIAL` なのに受け取り先なし」「`EXHAUSTIVE` なのに受け取り先あり」を拒否する負例が green / **DDL 差分ゼロ** / 受入証跡 `N3`・`N7` を再生成し再判定 |
| 2 | **`players` のトリガ新設**(`0024`)。`0005` の `prevent_*_update` と同形・`ERRCODE='23514'` | `players.id` の UPDATE が 23514 で落ち他列は通る / `downgrade` でトリガと関数が消える / `pg_get_triggerdef` 全文が期待値と一致 |
| 3 | **全表の「宣言 ⇒ 強制」突合検査**(`backend/tests/db/test_immutability_enforcement.py` 新設)。`test_immutability_matrix.py` の 5 表列挙と `conditional_columns` を廃し、挙動負例だけ残す | **母集団件数 == manifest の表数 == 実 DB のユーザ表数**(空洞化自体を検査)/ 負例 `N-1`〜`N-5` が red / **ステップ 2 を revert すると red になることを実測して記録** |
| 4 | **`operation_events` の 9 列分類 + トリガを 18 列へ拡張**(`0025`)。9 列すべて `protected`(`D-2` により `migration_unverified` も)。`coverage=EXHAUSTIVE`(18 protected + 3 allowed = 21) | `is_tombstone` の `true→false` が 23514 / `target_*`・`expected_version` の付け替えが 23514 / `d2`・`replaced_at`・`retired_at` は通る / ステップ 3 の検査が green に戻る / **分類だけでは red になることを実測ログで示す** |
| 5 | **`C12` マトリクスの新設**(`event_kinds.py`。CHECK 生成は行うが `__table_args__` へ未接続)。84 セルに「要求区分・行述語・担い手・典拠」を持たせる | 未宣言セル 0 / 表現不能セルに理由と受け取り先 ID / **正本 5-3 表の `自身の D2` 列をパースして `V6` 行と exact-set 一致** / 負例 `N-6`・`N-9`・`N-10` が red / **DDL 差分ゼロ** |
| 6 | **生成式の DDL 反映**(`0026`)。既存 2 本を生成式へ置換し、`d2` / `target` / `expected_version` の種別条件 CHECK を新設。**`0005` 由来の無名 CHECK 4 本には触れない** | **真理値表オラクル**(`N-8`)で「旧が通す集合 △ 新が通す集合」が意図した 2 集合と exact-set 一致 / セルごとの DB 負例が `parametrize` で自動展開 / **墓標 × `play_input` が挿入できる**(`D-1` の矛盾解消を正例で示す)/ manifest と ORM と実カタログが一致 |
| 7 | **登録と記録**。`.claude/core-areas.json` へ新設資産を登録。worklog 追記。申し送り 5 件を起票 | `core_guard.py` green / `check_plan_docs_sync.py` green / **受け取り先タスク ID が実在し `unclassified_handoff` の値と一致** |

**ステップ 4 と 6 は敵対レビュー + 人間の逐行確認の対象**(コア領域)。

### 再利用する既存資産(自前で書き直さない)

| 資産 | 使い方 |
| --- | --- |
| `backend/tests/db/test_alembic_migrations.py:1723-1756` | `tgattr` を列名へ展開するヘルパ。**全表突合でそのまま再利用** |
| `backend/tests/test_operation_event_kind_contract.py:31-58` | 正本 5-3 節の参加区分表のパーサ。**`C12` の母集団をここから取る** |
| `backend/src/pitchlog/db/sync_protocol/event_kinds.py` | 参加区分 ↔ リテラルの対応表。**12 種を手で列挙しない** |

### 母集団の作り方(人が列挙しない)

| 検査 | 母集団 | 空洞化耐性 |
| --- | --- | --- |
| 宣言 ⇒ 強制 | manifest 全 45 表 × 各表の `columns` 全数 | **母集団件数 == 実 DB のユーザ表数**を検査に含める |
| 網羅性 | `coverage` 宣言(**既定値なし**なので新表は必ず宣言) | **「未分類 0 なのに `PARTIAL`」を red にするラチェット** |
| `C12` | 12 参加区分 × 7 値 = 84 セル。区分は正本 5-3 表からパース | 正本が区分を増やせばセルが増え、未宣言で red |

**版管理の差分・ブランチ・実行文脈に依存しない**(2026-09-12 の空洞化の再発防止)。

## 5. DoD

- `operation_events` の 21 列すべてが保護か許可更新に分類され、トリガが宣言どおり強制する
- **全 45 表で「宣言 ⇒ 強制」を突合する検査があり、`players` 型の乖離が red になる**
- **ステップ 2 を revert すると検査が red になることを実測ログで示した**
- 種別条件が 84 セルのマトリクスから生成され、**未宣言セル 0**
- **真理値表オラクルの差集合が意図した 2 集合と exact-set 一致**
- **墓標 × `play_input` が挿入できる**(`D-1` の矛盾解消)
- 実 DB(PostgreSQL 17)で `backend/tests/db` 全件通過 / `alembic check` 差分 0 / 単一 head
- 敵対レビュー + 人間の逐行確認

## 6. テスト計画(NFR-019)

| 種別 | 追加するもの |
| --- | --- |
| **単体** | `Immutability` の `__post_init__` の負例 3 種(重複 / `PARTIAL` に受け取り先なし / `EXHAUSTIVE` に受け取り先あり) |
| **単体** | `C12` マトリクスの未宣言セル 0・表現不能セルの理由と受け取り先・正本 5-3 表との exact-set 一致 |
| **越境** | **全 45 表の「宣言 ⇒ 強制」突合**(トリガの `OF` 列集合 == `protected ∪ conditional`・`tgenabled`・関数が `23514` を投げる) |
| **故障系** | `N-1`〜`N-10`(トリガ `DROP` / 宣言と実装の不一致 / 母集団が空 / セル削除 / 生成式の項落とし / 正本改訂への追随) |
| **故障系** | **`N-8` 真理値表オラクル** — 288 組を `VALUES` で並べ旧式と新式を PostgreSQL で評価し、差集合を exact-set 照合 |
| **越境** | `operation_events` の保護 18 列すべての UPDATE 拒否(現在は 9 列しか検査していない) |
