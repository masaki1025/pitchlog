---
date: 2026-08-10
topic: feature 現在地の導出機構(plan frontmatter 拡張 + feature_status.py + SessionStart 注入)
branch: feature/feature-status
---

# 作業ログ: 2026-08-10 feature 現在地の導出機構

## やったこと

- /task-start: Notion タスク TSK-203(既存起票・優先度 中)を取得 → `feature/feature-status` ブランチ + worktree 作成(origin/develop 起点)→ 計画書雛形・本 worklog 作成。着手条件「ci-foundation 完了後」は PR #2 マージ済みで充足を確認
- PO 追加要望(2026-08-10): `docs/features/<slug>/` に作る plan.md の内容密度が今後高くなりすぎる見込みのため、役割別に 3 ファイル程度へ分割する案を本タスクの検討に含める(影響範囲・修正箇所の調査から始める)
- /investigate: spec-checker・decision-tracer・Explore の 3 並列(legacy-analyst は接点なしのため除外 — ci-foundation と同判断)→ 主要典拠を原典再確認の上 `docs/features/feature-status/research.md` に統合。主要発見:
  - 3 分割は DoD「新ファイルを作らない」と矛盾しない(射程は保存型 state.yaml の禁止。補助資料は設計書 6.1 が許容済み)
  - ただし frontmatter + 実装ステップ表は plan.md 1 ファイルに残すことが機構上の必須条件(codex_run.py が単一ファイル引数で機構検証)
  - **P0 発見**: session_context.py は plan.md 先頭 800 文字しか読まないため、frontmatter 拡張で進行中 feature が無言消失する経路がある(残余 ≒ 350 文字)— 拡張と同一 PR で読み取り改修 + 回帰テスト必須
  - 欠落規定 2 点(Notion 不一致の裁定・非対話時の縮退方向)は /plan で決定要
  - 事実訂正: Notion タスク本文の「v0.15 P1-4」は v0.10 P1-4 の取り違え

## 決定

- **A 案「役割分担」採用(PO 指示 2026-08-10)**: plan.md = 機械可読の契約(frontmatter + 6 節骨格)を維持し、詳細設計を design.md(新設・補助資料枠)へ、調査は research.md(既存)。パーサ・スキル無改修で成立。B 案(6 節の物理分配)は v1.3 + /finalize-doc + 20 超ファイル改修のため不採用
- /plan: 計画書 6 節記入 + design.md 新設(A 案の最初の実例)→ **review normal 11 周で収束(判定: 要修正 ×10 → 承認可)**。全指摘採用。主な設計確定:
  - 拡張キー 3 個(計画レビュー周回・確定ゲート周回・実行方式)— 末尾配置・整数/列挙検証・不正値顕在化。周回キーは本計画自身で運用開始(ドッグフーディング — レビュー 11 周のうち指摘反映 10 周 = `計画レビュー周回: 10`)
  - ステップ進捗導出: コミット件名の完全トークン規約化(`(ステップ k[/N] 付記)`・1 コミット 1 トークン)+ 表検証最優先 + 計画系コミット除外(パス 1 件以上・全件 feature/worklog 配下。空集合・マージは実装系へ保守的に)。承認・起票コミットはステップ表の外(記法なし)
  - stage 判定 10 分岐 + 差し戻し往復ライフサイクル(再開 = active へ戻す/修正完了 = in-review へ。「実装中(差し戻し修正)」は base..HEAD の in-review 痕跡から導出 — 保存キー追加なし)
  - Notion 期待値は notion-map transitions 参照(MERGED+worktree 現存 = pr_created 状態維持 + /task-done 待ち表示・CLOSED = 人間判断・破損 = 未取得)。スクリプトは Notion を呼ばない・書き換えない
  - 縮退の出力契約: worktree 列挙失敗/git 失敗/frontmatter 解析失敗/実行方式不正 — すべて「未取得(理由)」で顕在化・exit 0 維持
  - guard_paths 接触が 1 箇所発生(pr/SKILL.md 差し戻し往復手順)→ PR で core-guard 逐行確認チェックが発火する旨を 4 節に宣言

## 未決・次の一歩

- 計画書の**人間承認待ち**(承認後: frontmatter 済化 → 起票コミット → Notion へ計画書リンク + 承認日コメント → /implement ステップ 1 から)
- 設計書のゲート判定(3 節宣言 = 実装追随の節更新・版繰り上げなし・PR レビュー)は PO が PR レビュー時に最終判断(構造的変更と見なす場合は /finalize-doc + v1.3 へ切替)
