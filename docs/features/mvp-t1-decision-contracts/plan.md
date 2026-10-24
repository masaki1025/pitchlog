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

既認可の意味を変えない通常生成追随として `contracts/authz/shared-preconditions.json` のsource_documentsにある要件正本git_blob_digestだけ、採用済みD07本文の実byteへ更新する。抽出条文/全preconditions/mapping/型/認可の判定は不変。

## 3. 影響する正本とゲート

正本の有限対象パス: `docs/requirements/requirements-pitchlog-2026-07-22.md`、`docs/design/sync-protocol.md`、`docs/design/data-model.md`、`docs/adr/ADR-003-domain-calc-method.md`（直接影響がある場合だけ）、`docs/README.md`。編集対象自体は§2と既承認のままであり、機械突合に必要な節3への再掲である。ADRの実在basenameは着手前に照合し、別ADRや未宣言正本へ拡張しない。

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


## 正式接合候補の有限pathと互換表現

新たな意味判断ではなく、既D06/B・D07/A一配置の正式接合に必要な候補scopeを固定する。作者initial_scope_plan_reviewのcache handoff bd46d9574a23bd2f94972c645450cc630ec0de622e6f7059baeb0838eea6c99c／未適用patch c88932f0e9bb1ea9a21f876e239533f707c8eee191f1051b77f1a19f0025c373が対象。rootが固定28pathの実core包含（sync/game-state両方）を確認した。ここで正式assetsを適用せず、非作者の意味/型/旧保証/全前後値確認と既順序の7.7受理を先行する。正式不足15/P6/P7・計算本体は未成立。

旧42row/109case/27fixtureの要素byteと旧行/要求IDを保持し、新D07の2観測caseだけを追加する。自然keyを全行で変換する案は採用しない。既複合前提digestを新原観測selector行だけに明示追記するcriteriaと、既identity規則へのadditionalPartitionsの有限追記で旧IDを保持する。旧行や必須caseを除外せず、未宣言selector/重複/不一致/欠損を拒否する。

新9観測selectorは既structured payloadのT1観測refinementとしてconsumer写像を有限明示する。T2の旧軸を除外せず全4656要求identity/順序を維持し、不要な新raw観測の直積を加えない。includedAxisIds/observationOnlyAxisIdsは全実軸を重複なく分割し、既T2軸の省略・観測専用への移し替えを受理しないことを検証する。これをF-1/野球意味やT2 DRAW/GAP-05の成立に拡張しない。新4P7参照は原典exact readonly外殻だけ、Ready真正性/完全prefixを捏造しない。D06のnullable等価表現は型が排他的なunionだけで、未確定取消をunconsumedへ変換しない。

正式root対象は下の28pathと既plan/research・正本追随・必要な既凍結受理資産の実影響に限定する。作者はcache-only、rootは完全前後値/元記録を保全して新対象版だけ受理。unsigned測定結果を公式CLI成功とせず、旧識別値/未受理criteriaによる公式redを根拠なく消さない。356成功/11除外は候補局所結果で、除外11を最終正式検査へ戻し、受理後にdescriptor/三点/gap/coverage/fixtureの全正式検査を実施する。

- `contracts/state-transition/branch_row_mapping_v1.json`
- `contracts/state-transition/clause_branch_register_v1.json`
- `contracts/state-transition/coverage_row_binding_policy_v1.json`
- `contracts/state-transition/d06_priority_author_expected_v1.json`
- `contracts/state-transition/d06_priority_inputs_v1.json`
- `contracts/state-transition/d06_priority_schema_v1.json`
- `contracts/state-transition/d06_priority_v1.d.ts`
- `contracts/state-transition/game_end_contract_schema_v1.json`
- `contracts/state-transition/game_end_contract_v1.json`
- `contracts/state-transition/gap_register_v1.json`
- `contracts/state-transition/input_axes_descriptor_v1.json`
- `contracts/state-transition/manual_fixture_branch_coverage_v1.json`
- `contracts/state-transition/required_set_coverage_declaration_v1.json`
- `contracts/state-transition/required_set_row_rules_schema_v1.json`
- `contracts/state-transition/required_set_row_rules_v1.json`
- `contracts/state-transition/state_transition_contract_schema_v1.json`
- `contracts/state-transition/state_transition_contract_v1.json`
- `contracts/state-transition/state_transition_manual_fixture_schema_v1.json`
- `contracts/state-transition/state_transition_manual_fixtures_v1.json`
- `contracts/state-transition/t1_observation_binding_rules_v1.json`
- `contracts/state-transition/t1_out3_input_schema_v1.json`
- `contracts/state-transition/t1_p7_reference_shells_schema_v1.json`
- `contracts/state-transition/t1_p7_reference_shells_v1.d.ts`
- `scripts/check_deriver_dependencies.py`
- `scripts/check_gap_register.py`
- `scripts/check_input_axes_descriptor.py`
- `scripts/check_required_set_coverage.py`
- `tests/test_state_transition_contract_schema.py`


## 旧軸固定とcold監査の有限追補

既28pathに下記3pathを加え31pathとする。旧T2軸をcurrent descriptorだけから自己照合しないため、正式4b2時点のdescriptorを読み取り専用baseline資産へ固定し、監査policyと既三点parityのreadonly束へ明示する。既coreのsync/game-state両境界に3pathが含まれることをrootが確認した。Pythonへのbaseline SHA/commit直書きや走査除外を加えない。

- `contracts/state-transition/deriver_dependency_policy_v1.json`
- `contracts/state-transition/t2_coordinate_baseline_snapshot_v1.json`
- `scripts/check_input_axes_three_way_parity.py`

初回通常レビューP2-01は反映1のbaseline分離で終結。第2回は新processでcodec初回読込が依存監査に拒否されるP1-02を検出。rootは全採用し、PO委任の限定追加レビュー判断によりcold初期化・監査範囲・派生値影響だけへの追加非作者確認を1回認める。レビュー系列/回数をリセットせず、追加の意味承認を求めない。反映2はproduction module初期化で必要codecだけを先に解決し、依存監査のrepo外読込拒否/宣言5path制限を維持する。正式資産31path以外の拡張はしない。

反映2固定handoff SHA411e194fbddd96972fcde774f815efd72828730a23f971fad698010913516a12、全patch SHA40d05b617d345dc171d9151c37fdc20e313e80ac060165de4e7e0df723517bb7。rootのPO委任確認対象はこの有限技術追補で、非作者最終所見受領前にP1終結/正式7.7受理とは扱わない。339成功/11未検証は作者局所値で、正式検査時は全対象を戻す。D06/B・D07/Aの採用意味と旧4656要求identity/順序・旧42行/109case要素byteを保持する。


## 正式反映前の実接合漏れへの有限追随

2026-10-24、rootは既PO委任の通常不具合是正/正式値整合として、31path候補の実CLIで検出した既資産の接合追随を含め合計39pathへ具体化する。既T2 consumerが新9観測軸をrawへ補う不一致は、共有game_end_coordinate_axis_idsだけを再利用し、旧248case/4656要求の全要素・順序を保持して修正する。別の選択意味/独自計算を作らない。明示されたreadonly入力3pathは既deriverからexpander/outer検査へ有限伝播し、未知pathの拒否を保持する。

既31pathに追加する既存8pathは以下。game_end_manual_fixturesは未承認bootstrapの値追随のみ、inputcoverageは旧153全保持→170/既履歴保持の1追記、game_end_coverageはT1実ケース数と実読取入力の追随のみ。閉入力のIDを表示へ読む既readerは語彙正本から解決し、純入力/旧case/未知ID拒否を変えない。

- `contracts/state-transition/game_end_manual_fixtures_v1.json`
- `contracts/state-transition/required_set_input_coverage_v1.json`
- `contracts/state-transition/game_end_coverage_declaration_v1.json`
- `tests/test_required_set_coverage.py`
- `scripts/expand_game_end_cases.py`
- `contracts/state-transition/expander_dependency_policy_v1.json`
- `tests/test_expander_dependencies.py`
- `tests/test_input_axes_three_way_parity.py`

rootの初回7.7提案は非作者確認で3P1（placement欠落・比較literal57未宣言・履歴追加後digest4参照未再導出）を検出し全採用、未受理のまま保全する。反映1ではscope/freezeDefinitionを含む全前後、旧7履歴保持、追加1記録、最終digestを固定し、上記source後発差分を別の非作者へ限定追加レビュー/値再照合する。元reviewerはT2 consumer追補作者となったため最終独立確認から外す。既回数/採否をリセットしない。正式7.7・段階B・全P6/P7受理はまだ成立しない。
