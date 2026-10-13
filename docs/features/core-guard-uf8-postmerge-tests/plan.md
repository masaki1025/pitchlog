---
feature: core-guard-uf8-postmerge-tests
status: in-review
承認: 済(2026-10-14・利用者、最終計画と採否記録を正式承認)
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/fix-core-guard-uf8-postmerge-tests
branch: fix/core-guard-uf8-postmerge-tests
created: 2026-10-14
計画レビュー周回: 3
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-F8 統合後の core-guard 試験前提修正

## 1. 背景・目的と所有

PR #125 の `GameScreen*` 登録は `ef5c8711` で `develop` に統合済み。PR #126 の harness は 28,935 件通過・2 件失敗し、`tests/test_core_guard.py` の2試験が `origin/develop` に U-F8 登録がないという旧前提で失敗した。PR #126 は文書のみを維持する。本fixは [U-F8（TSK-523）](https://app.notion.com/p/3f493b75e68781b49976fc6c5ed970d5) のコア領域登録検査と[要件書 NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md) の試験継続に対応し、[U-M2（TSK-394）](https://app.notion.com/p/3da93b75e687813d95faef7fdc65722a) の文書PRを通す前提を回復する。本fixは新しい機能カードではなく、PR #125 統合後のCI回帰修正であり、DoDは本書5節を正とする。製品の FR や認可仕様は変更しない。

PR #127 は U-F5 担当の Draft で、同じ `tests/test_core_guard.py` と `scripts/core_guard.py`・`.claude/core-areas.json` を変更中。担当 worktree `/tmp/pitchlog-uf5-team-player-management` には触れない。#127 は PR #125 統合前の `2a456828` から分岐し、U-F8 の5領域登録を含まない。#127 の担当側はマージ前に最新 `develop` を取り込み、U-F8 と U-F5 の宣言・登録・試験の両方を維持する必要がある。本fixの同関数の変更は #127 担当へ PR 差分として申し送り、所有者の worktree では解消しない。

## 2. スコープ

`tests/test_core_guard.py` の失敗2件と既存の隔離履歴試験1件、計画書・作業ログ・Claude向け引継ぎ文書だけを変更する。`scripts/core_guard.py`、`.claude/core-areas.json`、製品コード、U-M2 の PR #126、PR #127 の担当 worktree は変更しない。試験削除・skip・検査器の緩和はしない。

## 3. 影響する正本

| 正本 | 反映 |
| --- | --- |
| 要件書・設計書・ADR・開発ハーネス設計書・運用文書 | 反映なし。既存のコア領域登録規則と NFR-019 の試験を維持する |

実装追随の試験と本計画・作業ログ・Claude向け引継ぎ文書に限る。

## 4. 実装方針

`tests/test_core_guard.py` は `scripts/core_guard.py` の検査経路であり、5領域の登録判定に関わるため重さ分類はコア領域。利用者は別fixで失敗2件を直す作業を許可し、3回の独立計画レビュー後の最終計画と採否記録を 2026-10-14 に正式承認した。slug の最終P0修正は独立再レビュー未実施であり、人間がその差分を承認した。コードの独立レビューと人間逐行確認は残る。

### 実装ステップ（コミット単位）

| ステップ | 変更 | 合格条件 |
| --- | --- | --- |
| 1 | `tests/test_core_guard.py` の失敗2件を統合後の基線へ追随させる。既存 RLS・ADR・U-M1・U-F2・U-F6 の順序を保ち、U-F8 登録が基線・実設定の双方に存在することを確認する。隔離リポジトリの宣言試験を同一履歴の登録まで進める | 失敗2件、同一履歴の「未登録→宣言→登録」、不正変更拒否、`tests/test_core_guard.py` 全体、Ruff・ty、文書検査が成功する |

## 5. DoD

- 失敗2件と全 core-guard 試験が通過し、登録済み実基線を検査する。
- 隔離履歴で未登録・宣言のみ・登録済みを順に受理し、不正な追加・削除・同時変更は引き続き拒否する。
- Ruff・ty・文書検査と修正PRのCI結果を記録する。
- PR #127 との同一関数の競合と取り込み前提をPR本文で明示する。
- コア検査経路の独立レビューと人間逐行確認をPRで行い、人間判断までマージしない。

## 6. テスト計画

| NFR-019 種別 | 検査 |
| --- | --- |
| 単体 | 失敗2件の直接再実行、登録済み基線・実設定の一致 |
| 境界・故障 | 同一隔離履歴での未登録・宣言のみ・登録済み、および既存の部分追加・削除・同時変更拒否 |
| 回帰 | `tests/test_core_guard.py` 全体、root Ruff・ty、docs-status、PR CI |

レビュー1周目（独立 Codex 敵対レビュー）は P0 1 / P1 3 / P2 0。P1 は3件とも採用し、同一履歴試験、#127 マージ前確認、6.1 必須構成に反映した。2周目は P0 4 / P1 1 / P2 0。指摘を全採用してworktree・重さ分類・ステップ表を機械ゲートの文法へ合わせ、Notion・要件書リンクを付けた。自動追加の3周目は P0 1 / P1 0 / P2 0。計画書のディレクトリ名とブランチ slug の不一致を採用し、`core-guard-uf8-postmerge-tests/` と `feature` 値を揃えた。この最後の修正に独立再レビューは実施していない。利用者は2026-10-14に最終計画と採否記録を正式承認した。コードの独立レビュー・人間逐行確認・PRマージ承認は別途必要。修正PR統合後に PR #126 へ最新 `develop` を取り込み、CI を再実行する。
