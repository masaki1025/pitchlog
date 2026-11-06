---
feature: mvp-frontend-baseline-repair
status: active
branch: feature/mvp-frontend-baseline-repair
承認: PO委任によるCodex/root指示（2026-11-06、結合版 b48a909d の既存 FE 基線赤を専用 WT で追随）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 統合版フロントエンド基線修復

基線 `b48a909da33f74b4a59f2d3df2e080169b17637b`。root 実測 `offline-recording-frontend-all-r1.log` は169 file/3516 pass/117 fail。旧 LC afd の代表 firstBallWire/startedGame 2 赤も記録済み。現唯一artifactの採用数学、真正認証/C2、原文/attempt、閉公開operationの意味を維持し、旧期待・fixtureの追随だけで緑化できない差を凍結してrootへ返す。旧歴史fixture/7.7/数学goldenを実装出力で書き換えない。

| ステップ | 範囲 | 完了条件 |
|---|---|---|
| 1 | 117赤を原典と基線で分類し、pin/selection/wire SHAのうち数学全値一致が証明されたmetadataだけを公式手順で追随 | 対象新旧全値照合、旧歴史期待保持、関連Vitest/型 |
| 2 | 既採用verified/C2/同epochと未認証/401/別scopeの両対向、公開operationの閉集合、undo/commit の真正fixture・現契約追随 | 拒否対向保持、対象試験と同源実装の一致、部分一致/skipなし |
| 3 | FE全件を再実行し、未解消の数学・正式7.7・実HTTPは留保を明記して独立reviewへ渡す | 全件結果/差分/固定SHA、段階commit、元WT/共有資産/DB無変更 |

frontend試験と必要な有限fixture/metadata、対応する本計画のみ編集する。新計算核の複製、未知operation許可、認証成功の偽造、閉拒否の緩和をしない。実DB/browserは不要。rootは別WTで製品接合を継続し、本WTは委任された作者が唯一writer。
