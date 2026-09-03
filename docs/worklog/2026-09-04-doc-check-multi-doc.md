---
date: 2026-09-04
topic: TSK-269 文書検査機構の多文書対応 — 保留解除・再開
branch: feature/doc-check-multi-doc
---

# 作業ログ: 2026-09-04 TSK-269 文書検査機構の多文書対応 — 保留解除・再開

## やったこと

### /task-start(再開)— 二重着手せず既存 worktree を再利用

- TSK-269 は 2026-08-31 に着手済み(worktree `../pitchlog-worktrees/feature-doc-check-multi-doc`・
  計画書雛形 `docs/features/doc-check-multi-doc/plan.md`〔承認: 未〕・調査メモ `research.md`)で、
  人間の判断により **TSK-270 先行のため保留**(Notion `ブロック中`)されていた
  → 前回 worklog: [2026-08-31-doc-check-multi-doc.md](2026-08-31-doc-check-multi-doc.md)
- **保留理由の解消を確認**: TSK-270(PostgreSQL 認可構成の実機検証)は 2026-08-31 完了(PR #33)。
  追補の TSK-312(TSK-270 マージ後レビュー P0 7 件の是正)も 2026-09-03 完了(PR #39)
- ブランチを `origin/develop`(f92b5f8 — PR #41 マージ後)へ **rebase**(184 コミット遅れを解消)。
  ブランチ固有の変更は新規 3 ファイル(plan.md / research.md / 前回 worklog)のみで競合なし
- Notion TSK-269 を `ブロック中` → `進行中` へ遷移し、再開の経緯をコメント

### /investigate — 前回調査メモの再検証(develop 24adeb2 → f92b5f8)

- 調査サブエージェント **3 本**を並列(コード差分監査〔general-purpose・Opus〕/ decision-tracer / spec-checker〔受け渡し契約の突合〕)。
  重い主張は Claude が原典で直接確認し、`research.md` に **6 節「再検証(2026-09-04)」** を追記(1〜5 節は原文のまま残す)
- **確認した事実の要点**
  - 検査機構本体(`check_design_propagation.py` / `check_doc_coverage.py` / `design_relations/` 4 資産 / `codex_run.py`)は
    **md5 一致 = 無変更**。1〜2 節の行番号は全部有効。変わったのは `core-areas.json`(guard_paths 18→24・area paths 8→34)・
    `test_core_guard.py`(辞書完全一致)・`test_ci_wiring.py`(81→1,148 行・pytest コマンド exact オラクル)・`ci.yml`(`-c pyproject.toml`)
  - **P0 MT-01 は事実**: `defects.json:471` の scope `1節` に対応する `## 1.` が同期正本に無く、`冒頭` も 61 文字しか切り出していない。
    1-4 節の故障モードが**一文書目で既に部分発生**している
  - **第 3 の検査機構** `scripts/check_authz_catalog.py`(5,019 行)が develop に入った。CI docs-lint には未配線
  - TSK-250 計画書は develop 未マージ・未改訂(`承認: 済 2026-08-31`・26 ステップ)。**ステップ 22「明示引数」との衝突は継続**。
    **4 検査の入力契約は TSK-250 側も未定義**。`AUTH-*` という ID はリポに 0 件で、TSK-270 実資産(`CATALOG:`/`POLICY:` 前置き・probe スキーマ限定)と体系が違う
  - `has_step_table` は誤記で実名 **`has_filled_step_row`**(`codex_run.py:62-78`・問題行 `:71`)。core-areas.json のどちらの集合にも無く、起票も未履行
  - 新たに効く手続: 7.3-1〜7.3-8・6.1 反映周コミット・6.3 実施記録行・H-85/H-87/H-88
- **基準線を再測定**: pytest **875 passed** / 3 検査 green / ruff・ty クリーン。**node ID 875 件を `baseline-node-ids-f92b5f8.txt` に固定**
  (P1「784 件以上は既存テスト削除でも達成できる」への対応資産)

## 決定

- 新規ブランチ・worktree は切らない(前回保留時の裁定「worktree とブランチは残す」に従う)
- 調査 3 本の観点は「要件 / 旧システム / 決定」の既定から**「コード差分 / 決定 / 受け渡し契約」へ振り替え**た
  (本タスクは既存コードの一般化で、旧システムは射程外。受け渡し契約が事実上の要件)

## 未決・次の一歩

- **/plan へ**。計画レビュー 1 周目の **P0 6 件・P1 7 件**+ 再検証で増えた論点 4 件の反映(対応表は `research.md` 6-7 節)。
  **人間の裁定が要るもの**: ① MT-01(oracle 改訂 / 意味型の分離 / warning 化)② `has_filled_step_row` を射程に含めるか起票か
  ③ `check_authz_catalog.py` を多文書対応の対象に含めるか ④ guard_paths 登録・H-78/H-79 追記の A/B 分担
- 前提のずれは `research.md` 6-2 節で現行化済み(/plan 冒頭の再確認は不要)
