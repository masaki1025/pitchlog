# U-F8 統合後 core-guard 試験前提修正（2026-10-14）

## 対象と所有

- PR #125 は `ef5c8711` で `develop` に統合済み。PR #126 の harness は 28,935 件通過・2 件失敗。いずれも `tests/test_core_guard.py` が実 `origin/develop` を U-F8 登録前と仮定した失敗。
- PR #126 は文書のみのまま。別fixブランチ `fix/core-guard-uf8-postmerge-tests` の専用worktreeで候補を準備した。
- PR #127 は U-F5 担当の Draft。所有worktree `/tmp/pitchlog-uf5-team-player-management` と共有3ファイルには触れていない。#127 は #125 統合前の `2a456828` から分岐し、同じ `test_product_rls_paths_remain_in_develop_baseline` を変更するため、#127 担当側でマージ前に最新developを取り込み、U-F8とU-F5両方の登録・試験を維持する必要がある。

## 候補差分と検査

- 失敗2件を、登録済み実基線と実設定の一致を確認する試験へ追随した。RLS・ADR・U-M1・U-F2・U-F6の登録順は残す。
- 既存の隔離リポジトリ試験を同一履歴の「未登録→宣言のみ→登録済み」まで進める。不正追加・削除・同時変更拒否の試験は削除・skipしない。`scripts/core_guard.py` と `.claude/core-areas.json` は不変。
- ローカルの失敗2件は 2/2、`tests/test_core_guard.py` は 235/235、Ruff・ty・docs-status・`check_plan_docs_sync.py`・`git diff --check` は成功。修正は計画コミット`29cf20ff`とステップ1コミット`6fa1a357`に分離した。修正PRのCIは作成後に確認する。

## 独立計画レビューの採否

| 周 | 結果 | 採否と反映 |
| --- | --- | --- |
| 1 | P0 1 / P1 3 / P2 0 | P1 3件を採用し、同一隔離履歴試験、PR #127のマージ前確認、計画必須項目を追加。P0の計画承認区別は2周目で再指摘され、未承認へ修正 |
| 2 | P0 4 / P1 1 / P2 0 | 全採用。正式承認待ち、規約上のworktree配置、正確な重さ分類・ステップ表、Notion/要件書リンクに修正 |
| 3（P0限定） | P0 1 / P1 0 / P2 0 | 採用。計画書ディレクトリとfeature値をブランチslugへ一致させた。修正後の`check_plan_docs_sync.py`は成功。追加レビューは自動実施しない |

開発規約6.1・6.3により、3周目後の最終修正差分と本採否記録を人間が確認する必要がある。利用者は 2026-10-14 に両者を実装計画として正式承認した。slug の最終P0修正は独立再レビュー未実施であり、その事実を了承した承認である。コードの独立レビューと人間逐行確認、PRマージ判断は別ゲート。

## Claude への引継ぎ

このfix PRの統合後、最新 `origin/develop` 上で `tests/test_core_guard.py` 全件と harness CI を実測し、登録済みU-F8の5領域・段階登録試験・不正変更拒否が通ることを確認する。次に文書のみの PR #126 が最新developを取り込み、CIを再実行する。PR #127はU-F5担当が最新developを先に取り込み、U-F8とU-F5双方の宣言・登録・試験を保つ。詳細コマンドと判定基準は同featureの `claude-handoff.md` に記録する。

ハーネス運用評価台帳への追記は行わない。本件はPR #125統合後の試験前提1件の追随で、検査器・CI構成・運用規範の変更や反復傾向の確定を含まないため。
