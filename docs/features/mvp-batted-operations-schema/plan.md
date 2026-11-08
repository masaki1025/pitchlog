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

追加移管（2026-11-08、PO委任root明示指示）: 実71f応答により、走者あり全停止凡打/無得点SHはRBI原観測なしで実RunnerValueの空effectsを返すが、582 headはこれを拒否するP1を発見。rootからBE `domainrt/lineup_play_prefix_continuation.py`、FE `api/lineupPrefixWire.ts` のhead修復と既 `lineupPrefixWire.spec.ts` の旧4hit有限castへの限定修正を追加移管（root非編集）。NoRunはbatted-out/SH＋実Applied観測＋本物RunnerValueの空effects＋得点/打点/失点が厳密false＋score全値不変だけを封印する別閉headとし、RBIを作らない。RBIありは非空effectsとのpair必須、旧headは不変更、既Value/Successは2variantのまま。

## 固定候補と成立範囲

SHは占有者全員の明示前進、SFは0/1死かつ三塁生還、DPは0死一塁のみ、公式失策1件はerror/SH-errorだけ、RBI閉map3値/空不可、outRunnerの実Uuid/base1/force-outを閉じた。SH/SFの配列はsupported const/anyOfで構造上の在塁者と明示先だけを照合し、球場結果/塁衝突/得点因果の数学をschemaへ写していない。未知keyword/integer/minProperties/if等は置かず、V7 error countはJSON primitive const1。JS matcherがtype未記載arrayのitemsを評価しない点を正負で検出し、error枝のarray型を明記してBE/JS一致へ是正した。

36共有構造正負入力＋旧Value完全保持/meta検査38成功。実71fの10入力でBE NodeDomainHost→型decode→seal→公式V7/V8/schemaと、FE実IIFE→head/seal→V7/V8を接続。結果型は無得点FC/error/batted-reach/SH-error/DPが既Value、全停止凡打/無得点SHだけが空typed RunnerValue、得点単打/SFは非空effects付きRunnerValueであり、根拠なくNoRunを他結果へ広げていない。空effectsでもflags/score/入力族/overrideが不正ならBE/FEで拒否、旧head34行は全値保持。

検査: 旧codec込みの初期89成功5.29秒、最終追加込みrunは85成功/7失敗296.72秒で7件すべてnode --versionの2秒起動期限に応答できないNODE_UNAVAILABLE（同時にgitstatusも遅延）。製品期限/検査を変えず、node版probeがv24.16.0/0.0057秒へ戻った新根拠の下、失敗層runtime10件だけ限定再走し10成功3.54秒。単一run全92greenとは記録しない。FE最終2suite62成功2.37秒、Vue型/限定ESLint/BE型/Ruff成功。元の型不整合は旧19hit fixtureの広域result castを既4hit unionへ狭めたtest-only修正で、値/期待を変更していない。既lineupPrefixWire.specのruntime2失敗は起点current fixture0db対実artifact71fの未接合であり、root互換842適用後の接合確認が残る（本所有外のpinを補修しない）。

実PG/認可/同TX/画面/正式受理/CI/P6blindは未実施。新入力fixtureは実hostへ渡す要求だけで、応答expectationsは保存/再採取していない。root非作者確認・互換/pin/SQL/T5/rowgate直列接合後に59play ownedを実測する。

root T5再利用入口（テスト内、資格発行なし）: `backend/tests/test_batted_operations_schema.py::actual_batted_payload(row, host)` は実NodeDomainHost exactを要求し、実行pin一致/再計算/BEhead/両schema/pair負例/V7/V8/current codecを省かずdecoded LineupPitchPlayPayloadを返す。fixture `batted_operations_schema_runtime_requests_v1.json` の10要求を同hostで渡せる。root T5は当該payloadと `UUID(payload.calculation.request.play_identity.event_id)` を唯一native入口へ渡して検査し、元のmath expectationを生成しない。helper抽出後のruntime10件は10passed2.98秒。stats製品実装はrootのみ所有。
