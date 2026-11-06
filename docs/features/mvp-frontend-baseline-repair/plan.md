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

## ステップ2の限定追随

取消旧4 sample は旧Git artifact `4e8b3252…` と現 `ce622726…` の全応答4/4一致、旧期待4/4一致を先に確認した。現行取消fixtureは各sampleの実行pin三欄と、実保存CP contentの正準SHAから導くdigest三欄の計24欄だけを変更し、旧fixtureを保存した。可逆数学差分試験と取消対象51試験が通過。派生再現は cache `fe-baseline-repair-20261106/derive_native_undo_metadata.py`。

現単一artifact公開口は lifecycle1＋旧13＋交代4の18口を `Object.keys` 完全一致で閉検査し、未提供の訂正等は加えていない。通常球commitは現C2で要求nonceに一致する応答mockだけを成功にし、ACK/排他の18試験が通過。warm authは同提示tokenの通信断でverifiedとauthEpochを維持し、記録/作成の保存成功や自動POST再掲へ変換しない。既401・別tenant・別epochの拒否試験も保持する。準備中詳細404/403の復元入口にある端末条件checkboxは記録入力と分け、GameScreen・記録select/入力/書込ボタンの閉鎖は継続確認した。

旧 v2 成績fixtureにはBF原本がないため、現27欄の派生率入力では `batters_faced` を `UNSUPPORTED_SOURCE_VARIANT` の source_unavailable と明記する。0や実装計算結果で旧OPS期待を作らず、旧18例の比・実分母・表示全値を維持して25対象試験が通過。新v3 BF期待と旧数学goldenは編集しない。生成関数の例外文言「閉26項目」は現27欄に対し古い表記であり、生成sourceを手編集していない。

## ステップ3の固定検査と留保

基線 `b48a909d…` から本枝の編集は計画と frontend の試験/現行fixtureだけであり、製品実装・共有正本・旧fixture・生成assetは変更していない。旧Git hostと現 `ce6227…` の同要求全応答は v2 56/56、lineup 34/34、初球87/87、打球19/19、取消4/4が一致する。初球5例は元々閉拒否を含むため旧期待とは82/87一致で、旧/現同値を確認した。比較再現は cache `fe-baseline-repair-20261106/{compare_host_families.cjs,host-compatibility.json}`。

現行版の全FE Vitestは174 file/3631 pass/0 fail。段階2の影響15 file/414 pass、FE `vue-tsc --noEmit` と対象 ESLint も通過。数学golden値を実装出力で再生成せず、各現行fixtureの旧原典からの差分欄を固定した。7.7の正式受理、実HTTP/DB/画面実測、製品全MVP完成、人間逐行確認/P6 blindはこの試験で主張しない。生成例外文言の項目数追随は別源generatorの表記残件である。
