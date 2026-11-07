---
feature: mvp-d03-normal49-http
status: active
branch: feature/mvp-d03-normal49-http-20261107
承認: PO委任によるCodex/root判断（2026-11-07、既通常49計画step4内の試験準備・接合として担当指示を採用根拠）
重さ分類: 試験（コア境界の実接合証拠）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 正常49だけから実出場と成績・CSVを検証する

起点9f7e4ad882557a0434e31fd4bc086f0d9dc68471。親計画mvp-d03-current-startupのstep4の実施票であり意味・機能・正式資産は変更しない。編集は新DB/pure試験、既test_stats_appearance_http.pyの純script共通化、本計画/進捗だけ。候補DDL/権限差込・製品/正本/assets/共有台帳は非編集。

| # | 実施単位 | 成立条件 |
|---|---|---|
| 1 | r20純scriptを共通関数へ抽出し、新normal49同一試合のdriver/原本観測を作る | 旧script全byte一致。開始0球出場→通常3球→0球relief/同D5再掲→終了v1→再開中公式除外→追加4球目→再終了v2→GET/reload/試合・season all/practice/双方CSVで2投手各登板1、official空。初期全試合0球の成績未供給は0補完しない |
| 2 | 固定HEADをrootへ渡し、共通lockの指定後続でowned1回を実行する | CURRENT49/fullcatalog/5helper owner/PUBLIC・app/actor EXEC拒否/主要3hookを事前読取確認。候補installなし。start/交代前後のentry/native版S/source IDs/slot/CPはhost read-only観測。v1失効/v2の真正pointerをDB/API/CSVへ照合。DSN unset/source前後SHA/cleanup。故障・越境の既対向は残し本証拠へ過剰拡張しない |

新PG前にrootへ通知しrecovery先行・既network共通lockを守る。成功期待から原本を書かず、fixtureの名簿/語彙以外のデータ供給を足さない。失敗は停止位置を固定して修正根拠のある次版だけを再実行する。実HTTP/owned PGを実ブラウザ/実機/P3/全MVPへ読み替えない。


実施固定: step1=9e3fce868570a3c99cb50130d1c0716ea0114eb3、step2は同sourceでowned1passed216.80秒。2864source前後SHA同一/cleanup、候補installなし、実v1失効/v2・交代0球原本・両API/season/CSV各1を確認。別tenantの既対向も実行された。新producer故障/不正receipt注入、ブラウザ/実機/P3/全試合0球/MVP全体は未成立のまま。rootへ最終非作者確認と通常候補への再利用を渡す。詳細と生証拠はprogress/cacheへの参照で一元化する。
