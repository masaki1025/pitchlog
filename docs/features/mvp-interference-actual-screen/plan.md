---
feature: mvp-interference-actual-screen
status: active
承認: 済（PO委任Codex主担当/root、2026-11-08 23:27 JST）
重さ分類: コア領域
branch: feature/mvp-interference-actual-screen-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-interference-actual-screen-20261108
created: 2026-11-08
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 妨害裁定を実画面から保存し原本へ照合する

限定計画レビュー対象は基点 `6f5f6ab35a9f9d99c8265ccd50edf739f84919b2`、計画原案 SHA256 `15875b26036dd576e416b6b1f5be851065234012f93f8f24dc0ab81cb253f0e7`。root は P0/P1 なしとして上記日時に採用。実装候補の非作者レビューと実 PG 検証は別に行う。

既採用の INT01〜07 と候補 `6f5f6ab35a9f9d99c8265ccd50edf739f84919b2` の閉入力を、真正画面の作成・開始・記録・再送・再読込・DB 原本まで一つの候補環境で検査する。製品接合と正式資産の作成は root が別版で行う。この枝の試験だけを製品成功の証拠にしない。

## 編集所有

新規 `frontend/src/screens/InterferenceRealGame.e2e-support.ts`、`frontend/src/screens/GameScreenInterferenceActual.e2e.ts`、`frontend/src/screens/GameScreenInterferenceActual.playwright.config.ts`、`backend/tests/db/test_interference_screen_e2e.py`、この計画のみ。既 helper は呼び出して再利用する。製品 source、共有 SQL・schema・正式 asset、他 WT・台帳は変更しない。

## 実装ステップ

| # | 単位 | 到達条件 |
|---|---|---|
| 1 | 計画と既 UI/原本の有限照合 | root が対象版・所有範囲を確認。罰則採用、実プレイ採用、走塁妨害、守備側への妨害の画面選択と INT01〜07 の採用済み境界を固定する |
| 2 | 実画面 driver と DB wrapper | 新規 UI create/start、実裁定の全入力、保存・同 D5 同本文再送・reload を操作する。実 host 応答と保存 V7/41列/runner/after/T5 を同じ原本から照合し、steals unavailable と未知裁定を成功に読み替えない。固定 SELECT は実 UI より前に EXPLAIN する |
| 3 | 検査と隔離実測 | TypeScript 型・lint・Playwright compile・pytest collect を先行する。root の同版製品接合通知後だけ共通 lock 全寿命で owned PG/ブラウザを実行し、失敗時も source SHA と部分証拠を保存する |

新規 game は UI でのみ作成し、fixture play や raw HTTP の成功応答を記録の代わりにしない。観測されないアウト・授与・得点/盗塁は推測せず、既 T1/T5 の出力を正とする。実 PG は root の許可まで開始しない。
