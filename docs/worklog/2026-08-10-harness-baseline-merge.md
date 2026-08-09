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
- /finalize-doc 開始。確定ゲート敵対レビュー 1 周目(review adversarial・sol xhigh): **否決 — P0×0 / P1×3**(アンカー欠落〔Phase 3 後・v1.2 統合前の develop 更新が対象に混入し得る〕/「改めて PO 判断」がゲート外の再発行経路/対象 SHA の worklog 記録が実行不能〔記録コミット自体が develop を進めて条件を自壊〕)。全件採用して 6.4 の統制を改稿

## 決定

- **PO 判断(2026-08-10)**: 「ハーネス完成 = 設計書 13 章 Phase 3 完了」と定義。プロダクト初回リリースに先立ち `develop → main` のベースラインマージを 1 回実施する(**リリース非該当** — /release・DoD 8 項目・vX.Y.Z タグは適用外。実施完了をもって例外は失効)
- 実施順: 6.4 の例外追記が develop へマージされてから main への PR を作る(規約と矛盾した状態でマージしない)
- 当初の「版繰り上げなしの 1.1 追記(7.6-3 の節更新)」方針は**撤回**(反対側レビュー P1-1 採用): fast path は「正本への影響なし」(6.1)が条件で不適用・v1.0 の frontmatter 追加行は「本文の内容変更なし」のため先例にならない → **v1.2 への版繰り上げ + 確定ゲート(7.3・/finalize-doc)** へ切替(frontmatter・索引を in-review 化)
- **対象 SHA の固定と失効**(反対側レビュー P1-2 + 敵対レビュー 1 周目 P1×3 採用): ハーネス完成アンカー = Phase 3 統合 `ce100aac97a625d6eab3559a522075b8557c041f`。対象は v1.2 統合マージコミット 1 点で**第一親 = アンカー**が成立条件(先行統合の混入・逸脱時は**未使用のまま失効**)。当該 PR 1 件のマージで失効し、再実施・対象変更は **v1.3 以降の版繰り上げ + 7.3 確定ゲート必須**(PO 判断のみでは不可)。実施証跡の正は**ベースライン PR 本文 + Notion**(worklog への事後追記は任意の別 feature PR — 記録コミットが develop を進めて条件を自壊させないため)
- 機構上の狙い: ci.yml が既定ブランチ main に載ることで gitleaks 全履歴スキャン(workflow_dispatch)が Actions から起動可能になる(現在はローカル docker 監査で代替中 — github-setup.md 4 章〔参照節の訂正 = レビュー P2〕)

## 未決・次の一歩

- 確定ゲートの収束(敵対レビュー 2 周目)→ PO 承認(採用/不採用一覧の提示)→ approved 化 → /pr
- develop マージ後: v1.2 統合マージコミットの**第一親 = アンカー**を確認 → その SHA を head とする `develop → main` ベースライン PR(本文に対象 SHA・アンカーを記録)→ CI 確認 → 人間マージ → main 側マージコミット SHA を PR 本文・Notion に記録 → workflow_dispatch 起動確認 → /task-done
