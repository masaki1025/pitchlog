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

ステップ1固定c4be7454の実merge差分は起点8deb比236path（計画1を含み、依存取込235path）。CSVの旧130依存だけでなく、197正式候補の祖先/凍結archiveも含む。cache csv-current47-startup-root-20261107/merge-intake.json・merge.patch SHA f5a360a4f90da76986cc1affa06cdf55322eeef9fccb0f6ec292398e848c2f0aへ実集合/5競合/解消を固定。CURRENT46とその起動unit/DB試験は8debと全byte不変、C2はrecoverとCSV両operationを保持、旧lifecycle画面検証履歴も保持。旧130/13レビューを236全体の受理にしない。正式197の最後0debのRG1 fixture追随は後続基線mergeで保持する。

ステップ2初段: 新0047は既候補と同じ10列/5制約/3監査索引を正規migrationへ分離し、RLSを有効/FORCE・PUBLIC/app権限を撤去した状態で止める。policy/grant/四関数はsource publisherから正式適用へ別接合し、migrationに混在させない。専用型元db/play_export/models.pyを追加し、実upgradeの全列/default/制約/indexとのpure照合1件とRuff/Ty成功。namespace付きbuiltinの表示差は試験の既知jsonb_typeof/nowだけを正規化、任意SQLを同値扱いにしない。CURRENTは46のままで、この初段だけで47正規起動の成立を主張しない。

ステップ2接合: 専用play_export/startupが10列/default/全制約/全snapshot索引とplay/event監査索引の全属性を実catalogへ照合する。CURRENT47へ進め、認可適用の前後に構造を閉検査。source publisher6f684be1（限定独立REPORT78e0cbfd…）を再利用し、旧全宣言/本文を維持したまま26宣言/本文だけを型元から候補catalogへ供給。whole first_ball.validateは既read_play_export_primitivesを除外せず旧/新全bodyを完全比較し、未知PUBLIC/app ACLも正確なtable identityで拒否する。既12不合格は部分publisherをwholeへ適用した境界違いであり、source修復後226成功、旧関数/未知ACL対向追加後227passed72.78秒。Ruff/Ty成功。実PG正常/故障は次段、正式seal/7.7は未成立。
