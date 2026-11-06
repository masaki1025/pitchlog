---
feature: mvp-game-operations-product
status: active
承認: 済（PO委任Codex主担当/root、2026-11-06。2時間の実接続優先試行）
重さ分類: コア領域
branch: feature/mvp-game-operations-product
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-game-operations-product
created: 2026-11-06
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 残る試合操作を既計算核と製品経路へ接続する

POの「統合候補までまとめて実装し、その固定版をまとめてレビュー・検査」「今から2時間その方法」を根拠に、既採用MVP内の実装を進める。独立レビューは候補固定後に実施、正式統合前の全件/認可/耐久性/正式値ゲートは維持する。本人逐行確認や新意味の採用は代記しない。

固定基線67218adb（候補、正式developではない）。最優先は走者あり打球・走者アウト/併殺/失策等の未対応操作を既単一T1核へ実装し、同じhost/同期/保存/再取得へ接続する。既feature/mvp-runners-batted-spike@fdab2a64等の素材を再利用し、全差分一括採用はしない。契約・正本から確定しない得点/RBI/第3アウトの因果を推測しない。

## 編集所有

この専用WTのfrontend/src/domain/**、関連frontend/src/apiの打球・走塁境界、GameScreenBattedHitObservation/OrdinaryPitch/Provider/Controllerと専用spec/実画面試験、backend/src/pitchlog/domainrt/lineup_prefix_source.py・lineup_play_prefix_continuation.pyの閉wire型・同期terminal_pitch_payload/projectionと関連専用試験、専用docsを担当する。唯一artifactは公式builderで生成し、正式pin/manifest/認可契約への必要差分は別patchでrootへ渡す。共有台帳・他WT・正式contracts/正本/DDL/認可資産を直接編集しない。rootは取消/終了再開/正式資産のwriterを保持する。

## 実装ステップ

| # | 単位 | 到達条件 |
|---|---|---|
| 1 | 既正本/閉型の操作を唯一T1核へ実装 | 未対応操作を列挙し、観測入力を明示。既23flag/OUT3/RBI/状態の正負対向、旧回帰、型の検査。新意味が必要な箇所だけ具体例で留保し他を継続 |
| 2 | 既製品HTTP/画面/保存へ接続 | 正式既認可/記録権/同TX/再送/結果不明を維持して同じ候補の再取得まで進む。仮Port/固定結果/生イベント独自集計を作らない |
| 3 | 固定候補の独立レビュー・実結合検査 | 全差分/原典/検査/未達をrootへ引渡し。正式資産/必須CI/通常PRはrootが直列管理し、不成立を完成としない |

2時間の開始は2026-11-06 18:37:31 JST、評価時刻20:37:31 JST。作業上限/停止命令ではなく製品成果を評価する区切りであり、MVP全目標を縮小しない。


root接合候補反映（2026-11-06 19:46 JST、PO委任Codex/root判断）: actual LC a7ae1d40へsource2bdfを通常mergeした後、最終overlay patch SHA57556d3cf1ecba5aa51775c7c5dfa99ccb07766289839167971e55ed75941b08の25path全before/after SHAを照合して適用。正式schemaと唯一artifact fbcf253bの結合、有限v2旧host互換witness、公式SQL body/manifestの候補を揃える。過去数学期待217件を保持した作者証拠、独立clone再適用25/25、旧profile54・正式FE schema6成功を根拠とするが、root最終独立確認/全ハーネス/正式受理は未了。source単体merge後はroot backend107件/FE型成功。終了再開cache/交代は未合成であり、MVP全体/正式提供と記録しない。
