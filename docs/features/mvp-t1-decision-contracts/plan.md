---
feature: mvp-t1-decision-contracts
status: active
承認: 済（PO委任による有限技術手順確認、本文参照）
重さ分類: コア領域
branch: feature/mvp-t1-decision-contracts
created: 2026-10-24
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 採用済みD06/D07の有限正式反映

## 1. 根拠と目的

正式起点4b2db6907f329c3dde113c3b7e1c3515600fb915、承認済みTSK544計画7d6ce544のステップ1の部分単位。全体計画・既承認・レビュー回数を作り直さない。POの2026-10-24実回答はlead e4ef090aに記録され、D06=B、D07=A（二死二三塁の単打1配置だけ）。技術具体化・正式値受理・通常統合は既PO委任に従う。人間の実値確認・署名を代記しない。

D06は既認可/DI2・DI3/連番/内容拒否を先行維持し、状態前提拒否とO4の同時成立だけO4優先。全取消を確認できなければD5未消費とは扱わない。結果照会・旧要求終結/耐久後着遮断・同D1/同内容/新D5の不可分置換を閉じ、故障想定と実DB実証を分ける。既存B+D/依存交代除外A/P3や取消範囲を変更しない。

D07は単打/二死/二三塁だけsecond optional→3・third optional→4、first不在not-applicable/nullの確認可能候補。表示だけで観測済みとせず、利用者確認修正の実結果を優先し、第3アウト時機/RBI因果を推定しない。他の未掲載単打配置へ拡張しない。

## 2. 編集範囲

rootが正式共有資産の唯一のwriter。作者はcache候補のみ、非作者レビューはrepo/DB非書込。正式パスは要件書FR-003/FR-009/E-1/ADV、sync-protocol 6-2/6-3/6-4/7-1/7-2、data-model 5-3/5-4の直接必要箇所、ADR-003 D-8/D-11の直接影響が実在する場合だけ、docs/README.mdの版表示、本plan/research。

契約はcontracts/state-transition/の既state_transition_contract/schema/manual_fixtures/manual_fixture_schema、追加t1_out3_input_schema_v1.json、input_axes_descriptor、game_end_contract/schemaの共通参照値、branch_row_mapping/manual_fixture_branch_coverage、normalization_schema_examples、required_set_input_coverage_declaration/coverage、required_set_coverage_declaration/row_rulesを直接影響だけ変更する。旧109case/42row/27fixtureと原封印は保持し、新2case/2row/2fixtureは既存値と分離する。D06の新閉型/caseの正式配置は候補pathとcore包含を固定後に本書へ有限追記する。未登録の新pathへ書かない。

検査は既tests/test_state_transition_contract_schema.pyへ影響範囲の正負例を追加し、既checker/runnerは採用済み閉型の必要な対応だけ。本単位でT1計算本体・別計算器・仮Port/DB/HTTP・署名発行・core拒否条件緩和を行わない。新しい基準や全体手続きの再設計を行わない。

## 3. 影響する正本とゲート

上記採用意味の反映だけを7.6により同じPRへ含める。要件改訂/スキーマ構造の変更部分は7.3の独立敵対レビューを行い、対象版と採否を記録した上で既PO委任によるroot判断として確定する。実回答を候補全実値の人間承認に拡張しない。7.7は全前後値・9projection/8source等の実影響を導出し、固定対象版・根拠・非作者照合後に主担当が受理する。旧記録/同一無関係基線の受理を再実施しない。

## 4. 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 採用意味の正本最小追補を固定 | 原典と実回答を照合、独立敵対レビュー/採否/既委任判断を記録。確認済み範囲だけapproved化し、既採用部分/未実証を混同しない。正式contractsは不変 |
| 2 | 既契約への有限候補と純入力/対向caseを固定 | cacheにschema/型/2case6面/D06分岐の正負例を固定。既値保持と範囲外拒否を確認。P6段階Aの固定範囲と未検証範囲を記録。必要な新blindは純入力/規範だけ、封印後比較。作者の45/62検査を独立導出としない |
| 3 | 正式値受理後の契約・共通参照・派生整合 | 544の順序を守り7.7前後値受理後に正式assetsを反映。P6段階B/必要再検証と所有側受理、P7項目別残件、独立coreレビュー、影響検査/最終必須CIを記録。本部分を全T1着手条件完了としない |

指定ステップごとにコミットし、反映周は独立カウンタを引き継ぐ。新たな意味判断が必要と判明した差分だけ既判断票へ集約し、依存しない作業は続ける。

## 5. DoD

採用D06/BとD07/A一配置が正本/正式契約/ケースに一致し、未確認取消・同D5後着・改内容置換・範囲外単打・観測推定を拒否する対向例がある。正式固定HEAD/差分SHA/独立レビュー/前後値受理/提供状態を一台帳から追跡可能にする。P6/P7/P8/7marker/G6/T2共有参照の未閉鎖はそのまま残し、計算本体開始を偽らない。

## 6. 検査

作業中は局所schema/原典対応/既値保持・双方向負例、descriptor checker/three-way parity、gap/branch mapping検査。最終はfrozen/census/規範整合・型・root検査・必須CI。重い検査とDBは所有slotを分離。故障比較例の通過は実DB実証ではない。実Port/DB/HTTP完成は計算契約整備の新しい前提にしない。


## PO委任による有限手順の確認

2026-10-24T05:11:30.496225+00:00、Codex主担当/rootは既PO委任に基づきdda06f76の本plan/researchを544既承認ステップ1の有限手順として確認する。非作者rights_replacement_reviewによる限定写像レビュー0/0/0、証拠 /home/ymdms/.cache/pitchlog/reviews/d06d07-formal-plan-dda06f76-independent-20261024/evidence.json（SHA256 210d450f6e34a51e296a4d918050ebd8cc7849af6c86f9ac2f169ac22b21c1d8）、標準diff80f8fb6a4e733445a0dd6dc42e8a9e574e869005509f75c9324303865e31cdfcを根拠とする。ステップ1の新規採用差分を原典と照合して7.3へ進める。9projection/8source等は既検査の実影響を求める例示であり固定数の新条件ではない。段階A固定結果/未検証範囲受領→候補core/所有側受理→7.7→正式反映→段階B/必要再検証/受理を保持する。実回答の意味を再承認したものでも、人間の逐行確認/実値署名の代行でもない。
