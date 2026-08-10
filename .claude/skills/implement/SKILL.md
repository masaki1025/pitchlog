---
description: 承認済み実装計画書に基づき Codex へ実装を委任し、検証まで一気通貫で行う(ラッパー経由のみ)
argument-hint: "<plan.md のパス>"
disable-model-invocation: true
---

# 実装の Codex 委任(設計書 6.1 / 9.2 / 9.4 / 12.1)

Codex の起動は必ず **`.claude/scripts/codex_run.py`** 経由(生の `codex exec` は codex_guard がブロックする)。ラッパーが計画承認・worktree・sandbox・モデル対応表(ADR-001)を機構検証する。

## 手順(ステップ実装ループ — 一括実装しない・設計書 6.1 段階実装)

計画書 4 節「実装ステップ(コミット単位)」を上から 1 ステップずつ処理する: **1 委任 = 1 ステップ → 検証 → 1 コミット**。全ステップを 1 プロンプトで一括委任しない(ラッパーはステップ表の無い計画書を拒否する)。

1. **プロンプト構築**(ステップ単位。codex:gpt-5-4-prompting の知見に沿う): 当該ステップの内容と合格条件(計画書の表)/ 変更してよい範囲(**計画にない範囲へ触れない**+**このステップの範囲で止まり、次のステップへ進まない**ことを明記)/ テスト要求(計画書 6 節の該当分)。AGENTS.md は Codex が自動で読むため重複させない
2. **実行**(モデル・effort は計画書 frontmatter の重さ分類からラッパーが自動選択)。最初のステップは新規実行:

```bash
python .claude/scripts/codex_run.py implement docs/features/<slug>/plan.md - <<'EOF'
<ステップ 1 のプロンプト>
EOF
```

   2 ステップ目以降と差し戻しは `--resume`(同じ Codex セッションを継続 — セッション ID はラッパーが feature 単位で保存済み):

```bash
python .claude/scripts/codex_run.py implement docs/features/<slug>/plan.md --resume - <<'EOF'
<ステップ N または修正指示のプロンプト>
EOF
```

3. **ステップ検証**: 差分が当該ステップの範囲内か / ステップの合格条件 / 関連するテスト・lint。NG なら同じステップを `--resume` で差し戻す(次のステップへ進まない)
4. **ステップコミット**: **Codex はコミットしない** — Claude が `git -C <worktree>` でコミットする(Conventional Commits・日本語要約・**1 ステップ = 1 コミット**)。件名には完全トークン **`(ステップ <k>[/<N>][ 付記])`** を**ちょうど 1 個**含める(`/<N>` と付記は任意・全半角括弧可・k は計画書ステップ表の番号 — feature_status.py が進捗導出に使う。承認・起票などステップ外のコミットには付けない)
5. 次のステップへ(2 に戻る)。全ステップ完了で総合検証へ

- ネットワークが必要な例外(12.1)は、理由を人間へ報告して了承を得てから `PITCHLOG_ALLOW_NET=1` を付けて実行する

## 総合検証(全ステップ完了後 — 合格まで差し戻しを繰り返す)

- /check を worktree で実行(存在する品質ゲートすべて)
- 差分レビュー: 計画スコープ外の変更がないか / NFR-018 のコピー実装がないか / DoD を満たすか
- 要件との突合が必要なら spec-checker に委任

## 完了処理

- 変更ファイル一覧・**ステップごとのコミット一覧**・テスト結果・DoD 充足状況を報告し、次の導線(/sync-docs → /pr)を案内する

## fast path(軽微変更 — 設計書 6.1。人間の事前 OK 必須)

非コア(`.claude/core-areas.json` に該当しない)かつ小差分(目安 50 行以下)かつ正本影響なしの変更は、**計画書の承認・ステップ表なし**で `python .claude/scripts/codex_run.py fast -`(worktree 内で実行、terra medium 固定)。/task-start が作った計画書雛形は**メタデータとして保持**する(status: active のまま。/pr・/task-done が frontmatter の branch・notion を参照する)。**fast 適用時(人間の事前 OK 取得後)は雛形 frontmatter を `実行方式: fast` に更新する**(現在地導出が「fast path 実装中」と正しく識別する — feature_status.py)。PR は **/pr の fast path 分岐**を使い、本文に短縮計画(目的/変更/確認方法/人間の事前 OK への言及)を書く。
