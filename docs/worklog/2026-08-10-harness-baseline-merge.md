---
date: 2026-08-10
topic: ハーネス確定ベースラインを main へ反映(設計書 6.4 例外追記)
branch: feature/harness-baseline-merge
---

# 作業ログ: 2026-08-10 ハーネス確定ベースラインを main へ反映

## やったこと

- /task-start: Notion タスク起票(優先度 高・DoD 3 点)→ `feature/harness-baseline-merge` ブランチ + worktree 作成(origin/develop 起点)→ 計画書・本 worklog 作成
- ステップ 1〜2 をコミット(計画書・worklog 起票 → 設計書 6.4 例外追記)。check_docs_status.py green・diff は宣言範囲のみ
- 反対側レビュー 1 周目(review normal・terra max): **P0×0 / P1×2 / P2×1 — 判定「要修正」**。全件採用して反映(ステップ 3)

## 決定

- **PO 判断(2026-08-10)**: 「ハーネス完成 = 設計書 13 章 Phase 3 完了」と定義。プロダクト初回リリースに先立ち `develop → main` のベースラインマージを 1 回実施する(**リリース非該当** — /release・DoD 8 項目・vX.Y.Z タグは適用外。実施完了をもって例外は失効)
- 実施順: 6.4 の例外追記が develop へマージされてから main への PR を作る(規約と矛盾した状態でマージしない)
- 当初の「版繰り上げなしの 1.1 追記(7.6-3 の節更新)」方針は**撤回**(反対側レビュー P1-1 採用): fast path は「正本への影響なし」(6.1)が条件で不適用・v1.0 の frontmatter 追加行は「本文の内容変更なし」のため先例にならない → **v1.2 への版繰り上げ + 確定ゲート(7.3・/finalize-doc)** へ切替(frontmatter・索引を in-review 化)
- **対象 SHA の固定**(反対側レビュー P1-2 採用): ベースラインの対象は本改訂の develop 統合マージコミット SHA 1 点。それ以降の develop 更新は対象外(Phase 3 後に混入した未リリース変更が DoD なしで main に入る抜け道の閉鎖)。当該 PR 1 件のマージで例外失効・PR URL/head SHA/マージコミット SHA を worklog・Notion に記録
- 機構上の狙い: ci.yml が既定ブランチ main に載ることで gitleaks 全履歴スキャン(workflow_dispatch)が Actions から起動可能になる(現在はローカル docker 監査で代替中 — github-setup.md 4 章〔参照節の訂正 = レビュー P2〕)

## 未決・次の一歩

- /finalize-doc(敵対レビュー → PO 承認 → approved 化)→ /pr
- develop マージ後: 統合マージコミット SHA を記録 → その SHA を head とする `develop → main` ベースライン PR → CI 確認 → 人間マージ → PR URL/SHA 記録 → workflow_dispatch 起動確認 → /task-done
