---
date: 2026-10-15
topic: state-transition 凍結試験のマージ後反転の是正
branch: fix/state-transition-freeze-post-merge
---

# 作業ログ: 2026-10-15 state-transition 凍結試験のマージ後反転の是正

## やったこと

- develop(`e2e78cfb`)で `tests/test_state_transition_freeze.py` の 3 件の失敗を再現した(master の実測と一致)。原因は計画書 1 章
- 試作(scratch)で、検査器を変えずに直せることを確かめた: 末尾記録を戻した base が受理される / 末尾記録の PR 番号で受理・別番号で拒否 / `history[-1]` の書き換えで「書き換えまたは削除」
- 計画書を作成

### 計画レビュー 1 回目(2026-10-15・全文)

- **Codex 停止中の代替(PO 裁定 2026-10-15・裁定 (b))**: Codex の `review adversarial` の代わりに、Fable のサブエージェントで敵対レビューを行った(ADR-001 からの逸脱)。受理範囲 3 種(正本違反 / ステップが緑にできない / DoD と成果物の不対応)を明示
- レビュアーは 4 状態(develop そのまま 7 件 / descriptor を変えるブランチ 8 件 / マージ後の develop 8 件 / 同一 PR の連続 2 件 9 件)を scratchpad で模擬し、合格条件が成立することを実測
- 判定: **可決**(P0 0 / P1 0 / P2 4)

| # | 重大度 | 範囲 | 要旨 | 採否 | 反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P2 | 2 | 戻し方が `scope`・`criteria` だけで、トップレベルの `acceptance`・`identitySpec`・`schemaVersion` を戻さない。末尾記録の `freezeDefinition` 変更が `engineExpectedValues` を含むと、base が `validate_declaration`(`scripts/state_transition_freeze.py:211-215` ほか)で落ちる | 採用 | 2 章に、定義の基準を戻すときは `before.value["engineExpectedValues"]` からトップレベルの 3 項目も戻すことを明記 |
| 2 | P2 | 2 | 拒否側の番号や :409 の表明が固定値だと、末尾記録がその番号になった時点で反転する。repository も固定 | 採用 | 2 章: repository と番号を末尾記録から導き、拒否側は番号 + 1。:409 は形式に加えて「後続 PR の受理 ID と異なる」ことを表明 |
| 3 | P2 | 3 | `before.present` が偽(末尾記録で基準を新設)の扱いが計画書に無い(試作にはある) | 採用 | 2 章に「`criteria` から外す」を明記 |
| 4 | P2 | 3 | ステップ 1 の合格条件と 6 章は 3 状態なのに、DoD 1 は 2 状態 | 採用 | DoD 1 に「マージ後の develop の模擬」を足した(Notion の DoD も同期する) |

- レビュアーの付記: 同日、Claude サブエージェントのレビューが同じ差分で P0 を取り逃がした実測があるため、本レビューは Codex の敵対レビューの代替としては弱い前提で、人間の逐行確認を行うこと

### ステップ 1(`93df07be`)と確認

- 実装は Claude が直接書いた(Codex 停止中 — PO 裁定 2026-10-15)
- 確認(`tests/test_state_transition_freeze.py`): develop 起点 21 passed / descriptor を変えるブランチの模擬(仮の受理記録 #140 を 1 件)で対象 3 件は通過し、範囲外の `:70` の 1 件だけが `#140 != #131` で落ちる(想定どおり)/ マージ後の develop の模擬(clone で `origin/develop` を是正コミットへ付け替え)21 passed / #140 を足した PR がさらにマージされた後の模擬 21 passed
- ハーネス全件: 29,533 passed・3 failed(`tests/domain/mut/` の 3 件。新しい worktree に `backend/.venv` が無いことによる環境由来 — `uv sync` の後に 3 件とも passed)→ 実質 29,536 passed・失敗 0

### 実装分の代替レビュー(2026-10-15)

- `codex_run.py review normal` の代わりに、Fable のサブエージェントで敵対レビュー(ADR-001 からの逸脱 — PO 裁定 2026-10-15・裁定 (b))
- レビュアーの実測: 7 状態(develop 起点 / 記録 1 件のブランチ / 定義の基準を含む 2 changes の記録 / 同一 PR の 2 件 / マージ後 / マージ後にさらに #140 / その後の後続ブランチ)で、対象の試験はすべて通過。ハーネス全件 29,536 passed・2 skipped
- 変異検査(検査器を一時改変した clone): 受理 ID の照合を無効化すると拒否側の試験だけが落ちる / 履歴の前方一致を無効化すると改竄試験が落ちる → 検出は恒真の表明や別検査の偶然に置き換わっていない
- 判定: **可決**(P0 0 / P1 0 / P2 2)

| # | 重大度 | 要旨 | 採否 | 反映 |
| --- | --- | --- | --- | --- |
| 1 | P2 | 改竄試験は、基準の検査器 source を増減するブランチでは、履歴の比較より手前(`validate_implementation_correspondence`)で落ちる。path の集合を作業ツリーの宣言から取り、中身を `origin/develop` から取るため(`tests/test_state_transition_freeze.py:355-372`)。本コミット以前からの前提で、ブランチ内に限られ、マージ後の develop は赤にならない | 不採用(射程外) | 計画の原因・合格条件に含まれない(計画 2 章「やらないこと」と同じ扱い)。下の申し送りに追記 |
| 2 | P2 | `_declaration_before_latest_record` は history が 1 件のとき assert で止まる(真の逆は「比較元に descriptor なし」)| 不採用 | 履歴は追記専用で既に 7 件あり、到達しない。前提は assert の文言で明示済み |

## 決定

## 未決・次の一歩

- **次に descriptor へ受理記録を足す PR への申し送り**: `_repository_acceptance_context()` の `number=131`(`tests/test_state_transition_freeze.py:70`)を、その PR の番号へ書き換える(ブランチ内で完結し、マージ後の develop は赤にならない — レビュー 1 回目で確認)
- **検査器の source を増減する PR への申し送り**: `test_asset_cannot_self_report_comparison_source_across_two_commits` は、基準の検査器 source を新設・削除するブランチでは履歴の比較へ届かず落ちる(実装分レビュー P2-1)。ブランチ内で、`_copy_audited_sources` の path 集合を `origin/develop` の宣言から取る形へ直す(数行)
