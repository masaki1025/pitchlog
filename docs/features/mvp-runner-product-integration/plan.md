---
feature: mvp-runner-product-integration
status: planning
branch: feature/mvp-runner-product-integration-20261107
承認: 未（PO委任内の接合、固定版の独立計画確認後にroot採用）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# 走塁候補を通常配置と唯一artifactへ接続する

起点はroot正常0048候補 `71e3eebe436349f8a9ee3869132e785bfd5baa07`。純196件成功、正常起動の実DBはpre-full完全値照合で拒否され診断中であり、成立とはしない。元WTを固定したまま、別WTで既走塁作者 `aa8a538535fa4336c1fbc84324129ad7d803dbc6` の35path（packet SHA c430b2f7aecf70801110286f572cba0de0feeae4fc18efd43ba5565e48f00654）を再利用する。元枝・共有台帳の編集はrootだけ。計画の作り直しや野球意味の再裁定は行わない。

| # | 実装単位 | 成立条件 |
|---|---|---|
| 1 | 走塁の既核・SDK・画面・41列・T5・CSVを同候補へ接合 | aa8と後発修復を固定し正常merge、全競合を記録。SO05の親主結果と子観測の相反P1は修復必須、入力書換/cast/常時拒否を完成扱いにしない。共通型f290の限定採用と新作者源の非作者確認を別記 |
| 2 | 公式builderによる唯一artifactと現行pin/manifestを一括追随 | 前後SHA・生成入力・再現buildを固定。現行execution metadataとその派生値だけを正式生成経路で追随、prior/legacy/archiveや数学期待値を掃引しない。D11/SQL本文が変わる場合は同factoryから全値導出し、未知旧版を補修しない |
| 3 | 同版の実画面・実認証・記録権・同TX保存で走塁を通す | 新規作成/開始→投球/走塁/非投球→ACK/サーバーGET/reload、同D5/attempt再送非二重、越境拒否、故障全取消。正常0048の未成立はroot元WTで先に解消。共通owned PG lock/DSNunset/実source前後/cleanupを維持し、正式7.7/CI/merge/実機と分離 |

rootが本WTの唯一writer。編集対象は元35pathと後発同scope、唯一artifact/public宣言・現行execution pin/専用D11 manifest・既generated wrapper、および接合の専用試験と本計画。認可sourceの変化は既root0048と同publisherで行い、共有catalogの正式追記・受理は直列化する。元WTは実DB診断のsource凍結を維持し、このWTを成功へ読み替えない。

非投球の打席非該当は既XC-05/XC-07を保存し、CSV17/61/62は根拠付きNULL、半回/終了は既保存T2。盗塁複数塁など未対応、球種未取得の断中NP、一般併殺/失策/妨害等のMVP残件は単位成功と別に残す。単一実装/認可/記録権/原子性/冪等/再送/結果不明保証を省略せず、新しい意味判断だけを既判断票へ集約する。
