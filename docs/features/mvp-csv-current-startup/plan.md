---
feature: mvp-csv-current-startup
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-07、既CSV原本の正規配置）
重さ分類: コア領域
branch: feature/mvp-csv-current-startup
created: 2026-11-07
計画レビュー周回: 0
確定ゲート周回: 0
---

# 毎球CSVを通常起動と同じ製品候補へ接続する

旧候補6a424a30の唯一S・88列producer・実read/ZIPを再利用し、復旧正規起動8deb51e1を起点とした別WTで接合する。既候補/作者WTは不変更。旧130依存と各限定レビューを維持し、この接合を全依存の受理へ拡張しない。運用/共有DBには適用しない。

| # | 実装単位 | 成立条件 |
|---|---|---|
| 1 | CSV候補を通常mergeし、直近の起動0046・復旧と同居させる | 実全path差/由来/5競合を記録し、原本/認可/起動検査を失わない。一般の生成値を手修正しない |
| 2 | 正規0047 migration・閉型/全構造indexと正式provider/catalogの候補配置を接続する | 記録時88列producer/唯一S readの同TX/RR/RO資格を維持。試験後付DDLに依存せず標準起動へ供給。正式7.7は別ゲート |
| 3 | 同版実UI新規開始→記録→取消→再入力→ZIP/reloadと故障/越境を検証する | fixture投入だけの200を製品成功とせず、同source実行/DB完全値/独立確認/未了条件を固定 |

編集範囲は既候補の正規merge、CSV tableの新0047 migration/専用model、current_product_startupと対応試験、authz/正式catalog候補原本・公式生成派生/registry/CSV repositoryの必要最小接合と本計画。根拠packetはcsv-effective-root-connection-20261107/final-intake/checks.json。新しい野球意味や独自T1集計を加えず、P3 snapshot・終了再開/成績CSVの未接合を無理に補完しない。formal/全MVP/実機の未了を維持し、PO本人の確認/署名を代記しない。
