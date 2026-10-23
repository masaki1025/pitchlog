---
feature: mvp-integration-lead
status: active
承認: 未
重さ分類: コア領域
worktree: ../../..
notion: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01
branch: feature/mvp-integration-lead
created: 2026-10-23
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画: MVP引受とO5コアパス登録

## 1. 背景・目的

POの2026-10-23 /goalに基づき主担当を移管する。初回MVP-NFR-009と既存NFR-019の同期故障系資産O5をコア検出対象にする。#176は元ステップ1/1を公開済みのため、追加2ステップはこの独立plan/前提PRへ分割する。旧「#176内完結」は今回の計画承認・統合順委任で変更し、元履歴を改変しない。

## 2. スコープ

実装は `scripts/core_guard.py` の領域別宣言、`tests/test_core_guard.py` の対応試験、`.claude/core-areas.json` の完全一致1パス登録だけ。引受台帳は本featureに一つ置く。fixture本文、製品コード、既存コア検出、権限、共有DB、凍結値を変更しない。MVP委任を受け付けるguard手続きは別の限定計画で扱い、本2ステップに混ぜない。本人逐行確認の代記・CI失敗の合格扱いをしない。

## 3. 影響する正本

反映なし。`docs/development/dev-harness-design-2026-08-07.md`6.1の独立計画・ステップ規律、6.3⑤の承認済みパス追加を適用する。同期正本の意味・O5 fixtureは変更しない。

正本体系外: 上記3実装パスと本featureのplan・引受台帳。既存#176の追補文書は別途方針変更を記録するが、既存レビュー回数をリセットしない。

## 4. 実装方針

コア領域（同期プロトコル資産の検出経路）。登録対象は `sync-protocol` に `tests/fixtures/sync-protocol-population_v1.json` の1件。宣言とJSONを別コミットにして親版の宣言固定を実検査する。game-state/tenant-isolationの既存宣言・登録は維持する。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | O5 fixtureパス宣言とguard負例試験 | JSON据置き。合成登録検出、未宣言・誤領域・既存削除・未確認拒否、既存層不変。対象pytest、Ruff、ty成功 |
| 2 | 実JSONへ完全一致パスを登録 | 宣言コミットの後に1件だけ登録。実設定でfixture検出・未確認PR拒否。基線検査、対象pytest、Ruff、ty成功 |

## 5. DoD

- [ ] 独立計画レビュー後、対象版・判断者・日時・根拠付きでPO委任によるCodex判断を記録する。
- [ ] 二つのステップが順番に別コミットで存在し、既存検出・拒否能力が維持される。
- [ ] 独立実装レビューと最終HEADの必要CIを確認する。人間確認または別途独立レビュー済みの限定委任手続きが成立するまで通常マージしない。
- [ ] #176はこのPR実統合後に取り込み、O5製品runner未完を保持する。

## 6. テスト計画

`uv run pytest tests/test_core_guard.py` で合成Git履歴・実設定・拒否を検証。`uv run ruff check .`、`uv run ty check`、文書検査を実行。root全件は実装区切りで実施し、frontend一時ファイル生成と並行しない。製品DB/HTTPのO5成功はここで主張しない。
