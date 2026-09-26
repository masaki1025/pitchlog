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

## 関門 2 の下調べ(2026-09-26・PR #78 の head `20ef5fd` 時点 — マージ版で再確認する)

- **記録形式は research.md 1 の見込みどおり**: 置き場 = `base-allowlist.json` の `baseline_control.history`(`history_authority: true` はこの資産だけ)/ v2(`declaration`・`movement_policy`・`external_snapshots`・`aspect` は実差分から機械導出して exact 一致)/ `acceptance_id = {repo}#{PR番号}`・PR 受理モードは検査器が強制 → **draft PR で番号を先に確定**(`docs/features/tenant-boundary-baseline/design.md` D1〜D4)
- **外部ファイル(`external_files`)は 3 つ**: `scripts/check_tenant_boundary_bypass.py`・`scripts/frozen_history.py`・`.github/workflows/ci.yml`。**正例 fixture は入っていない** → A2 はこの 3 つに触れないので、新しい history-snapshot は要らない見込み
- **`contract_revision` は PR #78 で 15**(research.md の「13→14」は古い)。A2 は 16 へ
- **PR #80(TSK-440・迂回検査の条件 5・2 の射程)が先にマージされる** → 検査器が変わるので、マージ後に末端 2 関数の判定(TB005)への影響を確かめる
- 現時点で計画の改訂を要する差は無い

## 実装(2026-09-26)

- **関門 1**: PR #78(7C)がマージ(`b4ae739`・下調べと同じ head `20ef5fd`)→ origin/develop へ rebase し、HEAD がマージコミットを含むことを確認。7C 版の検査器で迂回検査 ok・凍結基準の不変量 OK。**関門 2**: 記録形式は下調べどおりで、計画の改訂は不要。Codex はサービス障害から復旧(疎通確認 OK)
- **順序の判断(人間 2026-09-26)**: PR #80(TSK-440)がまだ OPEN で、#80 も A2 も `base-allowlist.json` に凍結基準の記録を足す(後からマージする側が記録を作り直す)→ **ステップ 1 だけ先に進め、ステップ 2 以降は #80 のマージ後**
- **ステップ 1**(7ea87953): `application-steps.json`(適用 7 手順・逆順の取り外し・製品専用の操作種別)と `AuthzAssetSpec.application_steps_path` と静的検査。Codex が委任の前に「A1 の試験 `test_authz_product_staging.py` も `operation_handlers == ()` を表明しているのに変更許可に無い」と範囲の矛盾を報告 → **`operation_handlers` は空のまま残し(probe の適用器では製品資産を適用できない性質を保つ)、製品の操作種別は `AuthzAssetSpec` の別フィールドに持たせる**方針にして、既存の試験に触れずに収めた。コミット後の迂回検査で TB007 が 2 件(`Path.is_absolute`・`Path.relative_to`)→ 是正して amend(A1 に続き 3 回目 — **Codex の「迂回検査 green」は未コミットの報告なので当てにならない**。コミット後に必ず走らせる)
