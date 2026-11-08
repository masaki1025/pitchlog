---
feature: mvp-batted-operations-schema
status: active
承認: PO委任root明示移管・既gameops step2内の最小追補（2026-11-08）
重さ分類: コア領域
branch: feature/mvp-batted-operations-schema-20261108
created: 2026-11-08
計画レビュー周回: 0
確定ゲート周回: 0
---

# 打球群の閉schemaと実wire-headへの接合

起点c6718e32（公式SH修復71f/new RBI head582含む）。既mvp-game-operations-product step2内、rootから共有schema/d.ts4pathの唯一編集を委任。所有はlineup_play_prefix_schema_v1.json/lineup_play_prefix_payload_schema_v1.json/lineup_play_prefix_v1.d.ts/lineup_play_prefix_payload_v1.d.ts、新専用BE/FE schema正負試験と本docs。SQL/T5/rowgate/pins/正式受理/共有台帳は非編集。

| # | 作業 | 検査 |
|---|---|---|
| 1 | 最終sourceの有限result/公式失策/同塁/DP/RBI閉形と配置intakeを4schemaへ接合 | 旧4hit/空凡打保持、SH全占有者進塁・SF0/1死三塁生還・DP0死一塁・error2結果のみ |
| 2 | 閉WireHeadの旧/Runner/RBI paired variant、d.tsと実FE構造検査を接合 | 未知/余剰/片側欠落・空RBI・UUID・count1以外を拒否、応答Valueは旧2variant保持 |
| 3 | meta/実JS matcher/型/旧正負と新host封印の必要範囲をまとめpacket化 | 未対応keywordを使わず、未供給実環境/正式pinと純成功を区別 |

schemaは構造/既採用SourceIntakeを閉じ、走者実ID/後退/塁衝突/因果を数学で再計算しない。SHは各占有者の明示前進、SFは三塁生還、DPは既0死一塁以外を開かない。旧保存のRBI未提示数学は旧証拠として保持し、現writerの欠測検査を緩めない。正式資産採用/実PG/全MVP成立はroot統合後に別記する。
