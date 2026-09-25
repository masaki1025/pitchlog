---
date: 2026-09-25
topic: TSK-442 製品 authz の適用器・実 DB 試験(TSK-424 PR A2)
branch: feature/product-authz-apply
---

# 作業ログ: 2026-09-25 TSK-442 製品 authz の適用器・実 DB 試験(TSK-424 PR A2)

## やったこと

- /task-start: worktree 作成、Notion TSK-442 を `進行中` へ、計画書・worklog の雛形作成。カードに DoD 欄が無かったので追加した。重さ分類は**コア領域**(テナント分離・データ移行)。**開始条件の TSK-431 の 7C は未マージ** — 計画の承認までを先に進め、/implement は 7C のマージ後

- /plan: Explore 2 本(TSK-431 の 7C の状態 / 既存の適用器と DB 試験の形)→ [research.md](../features/product-authz-apply/research.md)。A2 の差分の設計を [design.md](../features/product-authz-apply/design.md) に分離(全体の設計の正は A1 の design.md)
- 計画レビュー(sol xhigh・敵対): 1 周目 P0=1 P1=6 → 2 周目 P0=1 P1=3 → 3 周目 P0=0 P1=4 → 4 周目 P0=0 P1=1 → 5 周目(確認周)0 件で収束。**計画レビュー周回 = 4**
  - **P0 は 2 周とも「末端の DB 実行器の転用」**: 1 周目 = 任意の SQL を受け取る実行器が迂回検査を空洞化する → 「検証済みの実行計画の型」を渡す案 → 2 周目 = 型は外から構築でき、手順 ID の一致は文を拘束しない → **末端関数は閉じた指示(`APPLY` / `UNAPPLY`)だけを受け、文の生成を末端の中で正規の資産から行い、資産の置き場も引数にしない**形で閉じた
  - 3 周目以降は、プロセス内の型・モジュールの書き換えを保証の外と明示し(A1 design 10 節と同じ線引き)、閉じた論点の言い換えを P2 以下にした

## 決定

## 未決・次の一歩
- **計画承認(2026-09-26・山田正輝)**。実装は TSK-431 の 7C(PR #78)のマージ後 — 計画書 4 節の関門を通してから /implement に入る
