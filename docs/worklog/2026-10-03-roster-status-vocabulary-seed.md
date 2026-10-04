---
date: 2026-10-03
topic: TSK-475 在籍区分キーの値と system_vocabularies の seed
branch: feature/roster-status-vocabulary-seed
---

# 作業ログ: 2026-10-03 TSK-475 在籍区分キーの値と system_vocabularies の seed

## やったこと

- 計画レビュー **7 周**(1〜6 周は否決。6 周とも当方の読み落としか作りすぎを機械が拾った)+ **スパイク 2 本**で承認(2026-10-04)
- 実装(ステップ 1〜7): research の未解決欄の確定 → シード資産 → **7.7 準拠の限定許可**(宣言資産 + 検査器 + 更新記録)→ seed revision → 実 revision 負例 3 件 → 三者一致検査 → 実 DB の FK/NOT NULL

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

## 未決・次の一歩

- ステップ 8 の起票 4 件(試合区分 seed / **`category` 強制** / `disabled` と「変更しない」の張力 / 正本 `:2421` と DML 禁止検査の食い違い)
- ステップ 9 の正本反映、ステップ 10 の U-M1 申し送り、ステップ 11 の敵対レビュー
