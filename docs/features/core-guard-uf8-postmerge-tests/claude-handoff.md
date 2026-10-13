# Claude向け引継ぎ: U-F8統合後のcore-guard試験修正

## 状態

- 基点はPR #125統合済みの`origin/develop`（`ef5c8711`）。PR #126はU-M2ステップ4の文書のみを維持する。
- PR #126のharness失敗は`tests/test_core_guard.py`の2件。実基線に`GameScreen*`が5領域登録済みなのに、未登録を期待していた。
- 本fixは上記2件と同一隔離履歴の「未登録→宣言→登録」試験だけを変更する。検査器`scripts/core_guard.py`、登録資産`.claude/core-areas.json`、製品コードには触れない。
- 計画の独立敵対レビューは3周。3周目のslug P0を修正した後の独立再レビューは未実施。2026-10-14に利用者が最終計画・採否記録を正式承認した。コードレビュー・人間逐行確認・マージ判断は別途。

## 統合後の実測

1. fix PRが人間により`develop`へ統合された後、最新`origin/develop`を取得し、そこを基点とする検証環境で`uv run pytest tests/test_core_guard.py`を実行する。失敗2件、隔離履歴の段階登録、部分追加・削除・同時変更拒否を含む全件通過を確認する。
2. そのdevelop HEADのharness CIをGitHub Actionsで確認し、run URL・HEAD SHA・件数・失敗有無を記録する。PR上の成功結果だけを統合後の実測と扱わない。
3. PR #126へ最新developをmergeで取り込み、差分が計画書・作業ログの文書だけであることを確認してCIを再実行する。全必須チェックが通るまで#126をマージしない。
4. PR #127担当にはfix統合後のdevelopを取り込んでもらい、U-F8の`GameScreen*`5領域とU-F5のチーム画面3パターン・2領域、および各段階登録試験が共存することを確認する。PR #127の所有worktreeは本fixから変更しない。

## 本fixのローカル検査

- `tests/test_core_guard.py`: 235件通過。
- Ruff、ty、`check_docs_status.py`、`check_plan_docs_sync.py`、`git diff --check`: 通過。
- Draft fix PRは [#130](https://github.com/masaki1025/pitchlog/pull/130)。PR #126 のファイルは変更していない。PR #127 担当への申し送りは [コメント](https://github.com/masaki1025/pitchlog/pull/127#issuecomment-6150461510) に記録した。
- 独立コード敵対レビュー1回目は P0 0 / P1 1 / P2 0。未登録初期状態の受理 assertion を追加し、2回目の差分レビューは P0 0 / P1 0 / P2 0。修正後も `tests/test_core_guard.py` 235/235、`git diff --check` 成功。レビュー側は一時ファイル制限で試験未実行。
- CIは修正コミットのpush後に最終結果を確認する。人間逐行確認の実施記録とマージ判断は確認者本人が行う。
