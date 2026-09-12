---
date: 2026-09-12
topic: 確定済みイベントの書き換えを防ぐ — 不変列の宣言漏れ 9 列と種別条件 CHECK の不足
branch: fix/operation-event-immutability
---

# 作業ログ: 2026-09-12 確定済みイベントの書き換えを防ぐ

TSK-343(ORM 導入)のマージ後に実施した敵対レビューで検出した **P0 3 件**を直した。
Notion: TSK-365。計画書: `docs/features/operation-event-immutability/plan.md`。

## やったこと

### 直した欠陥

| # | 欠陥 | 直し方 |
| --- | --- | --- |
| **P0-1 / P0-2** | `operation_events` 21 列中 **9 列**が `protected_columns` にも `allowed_update_columns` にも入らず、`BEFORE UPDATE` トリガの保護外だった。`is_tombstone` を `false` にすれば墓標が通常イベントへ化け、`target_generation` / `target_d1` / `expected_version` を書き換えれば確定済みの変更イベントが別イベントへ付け替わった(FK も対の NULL 性 CHECK も通る) | 18 protected + 3 allowed = 21 列の `coverage=EXHAUSTIVE` にし、`0025` でトリガを 9 → 18 列へ拡張 |
| **P0-3** | 正本 5-3 節「履歴文脈(`C12`)」が種別条件を CHECK で表すと定めるのに、現行 8 本は一部しか表していなかった。選手交代・タイブレーク開始・試合終了宣言で `D2` が NULL のまま通り、undo が状態差分を持て、undo が対象参照なしで通った | 12 参加区分 × 7 値 = 84 セルのマトリクスを宣言し、`0026` で CHECK 5 本へ落とした |

正本 `data-model.md:946` の `W1`「確定済みイベントの修正・削除は、新しい変更イベントとして
追記する。既存イベントを書き換えない」に反する経路を塞いだ。

### 調査で分かった、レビューの指摘より広い構造

- **`players` は `protected_columns=["id"]` を宣言しているのにトリガが存在しなかった**
  — 全 36 トリガを migration から抽出して突合して判明。`0024` で新設した
- **「宣言漏れ」も「トリガと `protected_columns` の全表突合」も検査が存在しなかった**
  — 不変列マトリクスの検査の母集団が 5 表の名前列挙だった
- 未分類列がある表は **24 / 45**。ただし**未分類 = 欠陥ではない**。欠陥なのは
  「正本が書き換えを禁じた表で未分類」であり、それは `operation_events` だった

### 射程(ラチェット型)

`Immutability` に `coverage`(**既定値なし**)・`conditional_update_columns`・
`unclassified_handoff` を足し、**全 45 表に宣言を強制**した。既定値を持たせないので、
**新しい表は必ず宣言しないと通らない**。全表突合の検査を新設し、
**母集団件数 == manifest の表数 == 実 DB のユーザ表数**を検査自体に含めた
(2026-09-12 の core-areas 母集団の空洞化の再発防止 — 版管理の差分・ブランチ・
実行文脈に依存しない形にした)。

### 実測で示したこと

計画が要求した「検査が効いているか」の実測を、すべて使い捨て PostgreSQL クラスタで取った。

**ステップ 3 の検出力**(ステップ 2 を戻すと red になるか):

```
[落とす前]   表数=45 違反=[]
[落とすトリガ] trg_players_identity_immutable on players
[落とした後]  違反=['players: BEFORE UPDATE OF トリガ本数が不一致: expected=1, actual=0']
```

**ステップ 4 の分類と DDL の結合**(宣言だけでは red になるか):

```
[宣言 18 + DDL 18] 違反=[]
[宣言 18 + DDL  9] 違反=['operation_events: tgattr 列集合が不一致:
                        expected=[… 18 列 …], actual=[… 9 列 …]']
```

**ステップ 6 の真理値表オラクル(N-8)**: 288 組を `VALUES` で並べ、旧式と新式を
PostgreSQL 自身に評価させた。期待集合は 84 セルの要求区分と値の有無だけから
別実装で導き、CHECK 式生成器を経由しない。対称差は **89 行**で、意図した 2 方向だけ:

| 方向 | 行数 | 内訳 |
| --- | --- | --- |
| 旧のみ(塞いだ穴) | 87 | `substitution` 16 / `tiebreak_start` 16 / `game_end_declaration` 16(論理位置を持つのに `D2` なしで通っていた)/ `undo` 17(状態差分を持て、対象参照なしで通っていた)/ `player_registration` 16(同期順のみなのに `D2` を持てた)/ `play_input` 6 |
| 新のみ(矛盾解消) | 2 | `play_input × is_tombstone=true` |

正当な undo(`target` 有・`expected_version` なし・`d2` なし・`state_diff` なし)は
対称差に現れず、旧も新も通す。逆方向の副作用が出ていない証拠。

実 DB `tests/db`: **203 passed**。

## 決定

| # | 争点 | 決定(2026-09-12・山田正輝) |
| --- | --- | --- |
| **D-1** | 墓標行の `event_kind`(正本に記述なし) | **置換した版の種別を引き継ぐ。** `#1`〜`#7` の種別条件に `NOT is_tombstone` を行述語として付ける。正本への申し送りは **TSK-376** |
| **D-2** | `migration_unverified` の可変性 | **保護**(fail-closed)。検証フローが要るなら新イベントか別表で表す |
| **D-3** | 射程 | **ラチェット型**。`coverage` を全 45 表に宣言させ、全表突合の検査を新設する |

`D-1` は既存 CHECK の矛盾を解消した。決定前は `C-7`(`play_input` は
`state_diff IS NOT NULL`)と `C-8`(墓標は `state_diff IS NULL`)が
`event_kind='play_input'` の墓標行で同時に満たせなかった。真理値表オラクルの
「新のみ 2 行」がその解消そのものである。

## 途中で見つけた別の欠陥

### revision ID の 33 文字超過(実 DB でしか出ない)

`0025` に当初付けた `0025_operation_event_immutability` は **33 文字**で、
`alembic_version.version_num VARCHAR(32)` に入らない。`head` まで上げた時点で
**実 DB テスト 29 件が落ちた**。

**`upgrade` の DDL 自体は流れて `alembic_version` の UPDATE だけが落ちるため、
offline SQL 生成では検出できない。** Codex が「offline upgrade/downgrade SQL 生成:
双方成功」と報告した根拠がそこにあり、実機に回して初めて red が出た。

既存の最長は `0003_games_lineups_participation` の **32 文字ちょうど**で、
これまでも余裕はなかった。長さの検査はリポジトリのどこにも無かった。
`backend/tests/test_migration_hygiene.py` に全数走査の検査を新設した。上限は
`MigrationContext.version_table_impl()` が作る `version_num` の型定義から取り、
マジックナンバーを置かない。

### 改訂版(#9)の行述語が「置換された旧版」を指していた

`C12` マトリクスの初版が `#9` の行述語に `replaced_at IS NOT NULL` を置いていた。
正本 `data-model.md:835`「旧版は置換済み」のとおり、`replaced_at` が入るのは
**置換された旧版**であって改訂版そのものではない。参照する行が逆だった。

生成式へ実際に行を通して実害を測った:

```
行: 改訂された play_change の旧版
  V2: ★落ちる  V3: ★落ちる  V11: ★落ちる
行: 改訂されていない play_change(同じ行・replaced_at だけ NULL)
  V2: 通る    V3: 通る    V11: 通る
```

`#10` が `expected_version IS NOT NULL` を、`#9` が `IS NULL` を要求して充足不能。
**今直している `C-7` × `C-8` の矛盾とまったく同じ型のものを新しく作っていた。**

直し方は計画書の中にあった。follow-up B を立てた理由「改訂版に識別列が無く
`event_kind` だけでは通常版と区別できない」が `#9` の行全体に効く。7 セルすべてを
`表現不能` + `TSK-373` にして矛盾を消した。

## 未決・次の一歩

### 起票した申し送り 5 件

| 受け取り先 | タスク |
| --- | --- |
| `TSK-372` | 不変列の未分類を解消する — `coverage=partial` の 23 表 |
| `TSK-373` | 改訂版を名指す列を決める — `C12` の表現不能 15 セル(`V10` と `#9`) |
| `TSK-374` | 不変列の挙動負例を全 45 表へ広げる — 現状は 7 表 |
| `TSK-375` | 状態補正(`#7`)の採否を決める — `FR-040` と `P-58` の実装側の受け皿 |
| `TSK-376` | 正本改訂: 墓標行の `event_kind` を 5-3 節へ明記する |

**タスク ID の実在は 2026-09-12 に Notion の「✅ タスク」DB で確認した**(採番結果を
読み戻して照合)。コード側は `TSK-<数字>` の形式だけを機械で縛り、実在性は
機械検証しない(ネットワークに出るため)。

### 宣言した射程の限界

- **挙動負例(実 UPDATE)は 7 表**。`test_immutability_matrix.py` の docstring が
  そう宣言していて、**暗黙に全表被覆を主張しない**。全表化は `TSK-374`
- **`C12` の 84 セル中 15 セルが `表現不能`**。内訳は改訂版 7 + `V10` 6 +
  墓標の `V10` 1 + 状態補正の `V6` 1。いずれも**正本が物理表現を定めていない**ことが
  理由で、受け取り先 ID つきで可視化してある

### P1 6 件

敵対レビューの P1 6 件は別 follow-up。うち **`core-areas.json` の登録を導出型の検査で
閉じる**は他セッションが **TSK-370** として起票済みだったので重複起票しなかった。

### ハーネス運用評価台帳への追記

**該当する。** 「offline 検証が実 DB の失敗を隠す」型を候補として追記した
(revision ID 33 文字の件)。従来から追跡している「母集団を人が列挙する検査」とは
別の型で、**検証手段の選択そのものが検出力を落とす**という形である。
