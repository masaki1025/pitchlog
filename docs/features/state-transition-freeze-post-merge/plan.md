---
feature: state-transition-freeze-post-merge
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-15・山田正輝) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3fa93b75e68781f3af0ee2fe0ec36a8c
branch: fix/state-transition-freeze-post-merge
created: 2026-10-15
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: state-transition 凍結試験のマージ後反転の是正

## 1. 背景・目的

- Notion: [TSK-558](https://app.notion.com/p/3fa93b75e68781f3af0ee2fe0ec36a8c)
- #131(TSK-538)のマージ後、develop(`e2e78cfb`)で `tests/test_state_transition_freeze.py` の 3 件が落ちる(CI では #138 の harness で同じ 3 件)。develop が赤のため #137・#132・#138 がマージできない
- 要件: NFR-019(テスト必須)。対象の検査器は NFR-018 の三点突合(状態遷移契約の凍結基準)を守る機構で、本タスクは**その試験側の前提**だけを直す
- 原因(develop で再現 — 2026-10-15):
  1. `test_asset_cannot_self_report_comparison_source_across_two_commits` は改竄を `history[0]` の `newIdentity` の書き換えで合成する。history が 1 件のときは先頭 = 末尾だったが、#131 で 7 件になり、改竄の検出(「書き換えまたは削除」)より手前で `history[1]` の連鎖検査が落ちる
  2. `_create_changed_baseline_repository`(`test_changed_pr_accepts_matching_acceptance_id`・`test_changed_pr_rejects_acceptance_id_from_another_pr` が使う)は base を `origin/develop` の descriptor、head を作業ツリーの descriptor で作る。**ブランチが descriptor を変えている間だけ両者が異なる**前提で、#131 のマージ後は同一になり `nothing to commit` で落ちる
- 同じ型の潜在箇所: `test_unchanged_followup_pr_keeps_prior_acceptance_id_green` の `history[-1]["acceptanceId"] == "masaki1025/pitchlog#131"`(:409)。**次に descriptor へ受理記録を足す PR がマージされると、develop で同じ反転を起こす**

## 2. スコープ

### やること

- 上記 3 件と :409 の前提を、**どのブランチでも(descriptor を変えるブランチでも変えないブランチでも、マージの前後でも)成立する形**に直す
  - 1: 書き換え対象を `history[-1]` にする(末尾なので後続の連鎖が無く、比較元の履歴との不一致として「書き換えまたは削除」の枝に入る)
  - 2: base を `origin/develop` から取るのをやめ、**作業ツリーの descriptor から末尾の受理記録 1 件を合成的に戻したもの**を base にする。head は作業ツリーの descriptor。戻し方:
    - `history` は `history[:-1]`
    - 末尾記録の `changes[]` ごとに `before` で戻す。`before.present` が偽(末尾記録で基準を新設した)なら `criteria` から外す
    - 定義の基準(`criterionId == scope.identityCriterionId`)を戻すときは `scope` に加えて、トップレベルの `acceptance`・`identitySpec`・`schemaVersion` も `before.value["engineExpectedValues"]` から戻す(`validate_declaration` が両者の一致を検査するため)
    - PR の repository と番号は末尾記録の `acceptanceId` から導く。拒否側は導いた番号 + 1(必ず異なる番号)を使う
  - :409: 固定の PR 番号をやめ、末尾記録の `acceptanceId` が形式に合うこと、かつ後続 PR の文脈の受理 ID と異なることを表明する(「過去 PR の受理 ID」という前提を保つ)
- 受理側の試験で、比較元からの追加記録が 1 件以上ある(= acceptanceId 照合の枝に入る)ことを表明する

### やらないこと

- 検査器(`scripts/state_transition_freeze.py`・`scripts/check_input_axes_descriptor.py`)の規則の変更
- `_repository_acceptance_context()` の `number=131`(:70)。descriptor に受理記録を足すブランチでは、その PR の番号へ書き換えが要る(ブランチ内で完結し、マージ後の develop を赤にしない)。**次に descriptor を動かす PR への申し送り**として worklog に残す
- 他の試験ファイルの同型の走査(`origin/develop:` を読む試験は本ファイルだけ — 2026-10-15 実測 `grep -rln "origin/develop:" tests`)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| (なし) | 反映なし — 試験の前提の是正のみで、正本の規範・記述に触れない | — |

## 4. 実装方針

- **重さ分類 = コア領域**: `tests/test_state_transition_freeze.py` は `.claude/core-areas.json` の登録 paths(同期プロトコル・状況計算の 2 領域)に含まれる。`.claude/core-areas.json` 自体は変えない
- 変更は試験 1 ファイルのみ。合成リポジトリの作り方を「`origin/develop` との差」に依存しない形へ替える。試作(scratch・2026-10-15)で、検査器を変えずに次を確認済み: 戻した base が `validate_declaration` を通る / 末尾記録の PR 番号で受理 / 別番号で「追加受理記録のacceptanceIdがPR eventと一致しない」/ `history[-1]` の書き換えで「書き換えまたは削除」
- **Codex 停止中の扱い(PO 裁定 2026-10-15 — 391・538 と同じ / 裁定 (b))**: Codex は 10/21 14:37 まで使えないため、実装は Claude が直接書き、計画レビューと `review normal` は Claude サブエージェントの敵対レビューで代える(ADR-001 からの逸脱として worklog と PR 本文に明記)。マージ判断は代替レビュー + 人間の逐行確認で行い、10/21 を待たない

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `tests/test_state_transition_freeze.py` の前提を直す: 改竄合成を `history[-1]` に / `_create_changed_baseline_repository` の base を作業ツリーの descriptor から末尾記録を戻して合成し、PR 番号を末尾記録から導く / :409 の固定番号をやめる / 受理側で追加記録が 1 件以上あることを表明 | develop 起点で本ファイル全件 green。**descriptor を変えるブランチの模擬**(作業ツリーの descriptor に受理記録を 1 件足した一時状態)でも 3 件が green。マージ後の develop の模擬(clone で `origin/develop` を synthetic merge に付け替え)でも green。ハーネス全件 green |

## 5. DoD(受け入れ基準)

- [ ] 3 件が develop 起点のブランチで green、かつ descriptor を変えるブランチの模擬・マージ後の develop の模擬でも成立する
- [ ] 改竄検出・受理 ID 照合の枝に実際に入っていることを確認した(検査器の規則は不変)
- [ ] 代替レビューの採否が worklog にある・人間の逐行確認
- [ ] PR の CI 全ジョブが green

## 6. テスト計画

- 単体: 本ファイルの既存試験の前提を直す(試験の追加は、受理側の「追加記録 ≥ 1 件」の表明のみ)
- 故障系: 既存の改竄検出(書き換え)と受理 ID 不一致の拒否を、件数に依存せず成立させる
- 一致性・越境・E2E: なし(検査器と製品コードに触れない)
- 確認の範囲: develop 起点 / descriptor を変えるブランチの模擬 / マージ後の develop の模擬の 3 状態
