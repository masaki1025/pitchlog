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

## ステップ1の固定証拠

旧Git blob `177de16a` の artifact SHA `4e8b3252…` と現 `ce622726…` は、同一要求で v2 56/56、lineup 34/34、初球87/87 の**全応答**が一致する。初球の旧期待82/87と一致しない残5は旧・現の双方で同じ不正例である。打球の直前 `94ba8fa0` artifact SHA `9ae9d16d…` と現も19/19全応答・既期待19/19が一致する。比較script/resultは cache `stats-lifecycle-read-diagnostic-20261106/compare-fe-artifacts.cjs` と `fe-artifact-comparison.json`、打球比較は同一Git blob/現byteを使う。

現行fixture四つは旧fixtureを残したまま追加した。v2の変更は56×実行pin3＋自己echo2=280欄、lineupは34×実行pin3＋wire-head内pin2＋wireDigest1＋自己echo2=272欄。自己digestは既Python正式 `play_prefix_wire_digest`/`lineup_wire_digest` から再導出し、他の数学/観測/参加者/V8/priorを変更しない。初球102、打球38のpin文字列は可逆置換で旧file byteを復元できる。派生script/proofは cache `fe-baseline-repair-20261106/{derive_metadata.py,metadata-proof.json}`。原典との差分pathを固定したtestと対象84 Vitest、FE型/ESLintが通過。旧共有fixture/正本・正式7.7受理は変更していない。
