---
feature: mvp-substitution-stats-connection
status: active
branch: feature/mvp-substitution-stats-connection
承認: PO委任によるCodex/root判断（2026-11-06、既承認交代/成績sourceの隔離結合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 交代・native27成績の同版接合

基線はLC afd74ea9caf7c87055ad77fd33355e80d5c1030c。既feature/mvp-substitution-productとmvp-basic-stats-product計画の対象を拡張せず、別作者固定sourceを同じ隔離候補に接ぐ。0044の供給を待つstatsとnative27を待つ交代の循環を、候補source固定→同版接合で解消する。意味・認可・耐久性を減らさず、正式資産は公式helperで一括再派生し非作者確認/必須CI前に正式提供としない。5秒はPO指示で後段、計測の未達を保持する。

| ステップ | 内容 | 完了条件 |
|---|---|---|
| 1 | 交代作者のbase d335固定packetと全path SHAを照合し、独立交代取り込みcommitに固定 | 本文/digest全値照合、同版で未達/レビュー留保を保存 |
| 2 | stats固定branchを通常mergeし、0044→0045/native27/T5/唯一artifact/D11/ACL/manifestを接合 | 関連型/単体/閉検査、旧版D11不変・新27全値対向、共有生成物の公式再派生 |
| 3 | 同じ版・owned環境で交代→次球→reload、終了→成績/CSV→再開→再終了→最新版を実測 | 実認証/記録権/同TX、重複/越境/故障、非作者最終レビュー。候補と正式受理は別 |

rootがこのWTのsole writer。元の作者WT/cacheをrootから編集しない。実PG/browserは共通lockを全寿命保持、共有DSNをunsetしsource-preflightと前後SHAを保存する。共有DB/秘密発行/公開・main/develop直接変更なし。基線の混在や未解消の赤を成功へ読み替えない。記録後正式派生/7.7/全CI/PR通常統合は後続ゲートを維持する。

## ステップ1の候補固定（2026-11-06）

交代 final-candidate-20261106/candidate.patch SHA 7c8367e025fc9c050f1696f7f3e64a1f4e0a383549c2e5b67df135850b185738、94path manifest245bbd62…をd335共通祖先で3way接合。既LC/B5の実端末資格・schema登録・offline-ready表示を保持。重複したlifecycle import/schema/unionだけを一件化。生成runtime2pathは手修正せず現資産から公式rederive（変更ありexit3）→check成功。function-bodies check成功、backend168/型、frontend57/型成功。backend書式2pathをRuffで追随。source差分根拠はcache mvp-resume-20261104/substitution-root-3way-20261106.json。交代後の次球はstats27未接合のため未実証、旧作者P1留保と正式受理・最終非作者確認は未了。
