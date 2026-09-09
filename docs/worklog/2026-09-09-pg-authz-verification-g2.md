---
date: 2026-09-09
topic: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群(TSK-317 — TSK-270 計画の改訂 2)
branch: feature/pg-authz-verification-g2
---

# 作業ログ: 2026-09-09 PostgreSQL 認可構成の実機検証 第 2 群・第 3 群(TSK-317)

## やったこと

- `/task-start 317` — worktree `../pitchlog-worktrees/feature-pg-authz-verification-g2` を
  `origin/develop`(`1424d67`)から作成。Notion TSK-317 を `進行中` へ。
- 計画書雛形 `docs/features/pg-authz-verification-g2/plan.md` と本 worklog を新設。

## 決定

- **feature ディレクトリは新設する**(`pg-authz-verification-g2`)。
  当初は `docs/features/pg-authz-verification/` の再利用を試みたが、**現在地導出が縮退した**ため撤回した。
  - **機構の制約(実測)**: `scripts/feature_status.py:1491-1503` の `expected_feature_slug` は
    **plan の期待パスをブランチ名から導出する**(`feature/<slug>` → `docs/features/<slug>/plan.md`)。
    期待パス以外に `branch:` が一致する plan があると `:1590-1602` が **`plan 重複`** として縮退させる。
    旧ブランチ `feature/pg-authz-verification` がローカル・リモートに残っており同名を切れないため、
    **ブランチ名だけを変えてディレクトリを再利用する運用は機構的に成立しない**。
  - **前例と一致**: TSK-335 → `data-model-handoff-revision`、TSK-342 → `data-model-schema-orm` と、
    このリポジトリの実運用は **1 タスク = 1 ディレクトリ**である。
- **前計画書の内容を複製しない**(設計書 7.1-1)。第 1 群の実測・凍結 oracle・満たすべき要件 `R-1`〜`R-7` は
  `../pg-authz-verification/plan.md` が正で、本書 1 節から相対リンクで参照する。
  **本書がその 5 節「改訂 2 で確定する(第 2 群・第 3 群)」が予告した改訂 2 である**ことを 1 節に明記した。

## 未決・次の一歩

- **前計画書 5 節の前方参照の始末**: 旧 `plan.md` は「第 2 群・第 3 群の DoD は計画改訂 2 で確定する」と
  書いたまま宛先が無い。**本書へのポインタ 1 行を旧計画書へ足すかを `/plan` で判断する**
  (`docs/features/**` は一時作業域であり正本ではないため、ゲートは不要)。
- `/investigate` — 第 1 群で凍結した資産の現況を実測する。着手前に確認が必要な既知事項:
  - `contracts/authz/ddl-elements.json` が `status: candidate_probe_only` /
    `product_schema: false` / `second_group_approval_required: true`
    (**候補 probe であり、通った構成の確定ではない**)
  - `contracts/authz/auth-catalog.json` の entries 187 件は**第 1 群で凍結済み** — 書き換えない
  - `.claude/core-areas.json` への登録は**第 2 群の射程**(第 1 群では意図的に未登録)
  - 新設する資産が `tenant-isolation.paths` / `guard_paths` に載るか(6.3 規則⑤ — 台帳 `H-12` の再発回避)
- `/plan` — 実装ステップ表を第 2 群・第 3 群として作り(整数連番・枝番を作らない)、DoD を確定する。
- **本タスクはマージゲートの本体である** — `docs/design/data-model.md` 12-4 節が
  「RLS のポリシー / ロール DDL の適用と、実スキーマに対する越境テストが green になるまで、
  DB を利用する製品機能をマージまたは有効化しない」と定める。通過条件 ① が本タスク、
  ② の実スキーマでの再実行が TSK-344。
- **コア領域(テナント分離)** — `sol xhigh`・敵対レビュー必須・**人間の逐行確認必須**(PR 作成者以外)。
  逐行確認は並列化できないため、他タスクと確認待ちを重ねない(TSK-317 カードの注意書き)。
