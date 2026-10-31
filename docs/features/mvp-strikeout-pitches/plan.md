---
feature: mvp-strikeout-pitches
status: active
承認: 済（PO委任によるCodex主担当判断・操作単位契約作成のステップ1のみ）
重さ分類: コア領域
branch: feature/mvp-strikeout-pitches
created: 2026-10-31
計画レビュー周回: 1
確定ゲート周回: 0
---

# 正規捕球した三振・第3アウトの操作単位

## 1. 目的と既存計画

[TSK544 T1](../tsk544-t1-state-calculation/plan.md)・[四球/死球](../mvp-terminal-pitches/plan.md)の次操作だけを具体化する最小子計画。基点1fa8f21aからbackendの既CI書式だけを意味不変で追随した7646daab。全MVP計画・既承認・既レビュー/失敗・P6封印/曝露履歴を変更しない。旧四球/死球の承認を本数学核の開始承認に代用しない。

通常捕球した見逃し三振/空振り三振で打席を終え、第3アウトで両チームの打順を保持して攻守交代、反対側の投球・再読込へ接続する。spike41d7175dの共有核を選別再利用し、旧側の次打順を相手側へ渡す欠陥は輸入しない。実画面/実API/実DB/正式統合の成立は別に証明する。

## 2. 範囲と開始条件

SO-01/02、FR-003/005/020、XC-03、第3アウト共通後処理、既game_end_contractの248caseを規範とする。正規捕球の明示called-strikeout/swinging-strikeout、batting-result/pitch-event、S2/B0..3、outs0..2、両half、打順1..9、塁8配置、既有効回/得点/boardを扱う。振逃げ/K3/三振ゲッツー/併発走塁は今回成功へfallbackしないがMVP全体から外さない。

通常三振out1/PA/count reset/6true・17false/走者hold。第3outは旧攻撃側cursorだけ進め、新側の保持cursorをafterへ選ぶ。beforeの走者実結果/責任投手とafter emptyを混同しない。両チームcursorは独立したreadonly入力で、active before打順との一致を検査する。inactive cursorも1..9交差/境界/独立性を含め、偶然afterのactive scalarが同値でも旧側cursor更新とhistoryを落とさない。

契約24手例のfullresponse/履歴/23flags、3456のactive交差と独立両cursor31,104交差・大整数/拒否の根拠を別非作者へ渡す。P-1〜P-9の本単位の既成立/適用/依存/未成立を具体化しroot採否後に核実装へ進む。T2/Port/HTTP/DBの完成を計算本体の追加着手条件にしない。通常非作者確認をP6新blindや全体成立に読み替えない。

## 3. 正本・編集所有・初回path

正本requirements/design/ADR/development/opsの新設・版上げなし。既意味の操作限定実装。必要な意味の空白を発見したら具体入力/根拠/未決結果だけrootへ返し推測で決めない。契約/正式登録/共有台帳/coreの最終writerはroot、作者は本WTの許可pathに一本化する。

ステップ1 exact8:

- 新contracts/state-transition/strikeout_pitch_v1.d.ts
- 新contracts/state-transition/strikeout_pitch_schema_v1.json
- 新contracts/state-transition/strikeout_pitch_cases_v1.json
- 既contracts/state-transition/state_transition_contract_v1.json
- 既contracts/state-transition/input_axes_descriptor_v1.json
- 既contracts/state-transition/branch_row_mapping_v1.json
- 既contracts/state-transition/state_transition_manual_fixtures_v1.json
- 既tests/test_state_transition_contract_schema.py

既case/ID/期待/規範/到達集合/未充足を保持し新24例と真正参照だけを追加する。inactive cursorもdescriptor/contextの写像とpropertyへ含める。新consumer/pathが不可分なら先にrootへexact集合を返す。新3契約は既core宣言contracts/state-transition/*によりgame-state/sync-protocolへ捕捉済み（root core-path-proof.json）、不要な宣言重複/対象縮小をしない。

将来の核候補はstate.ts/stateRules.ts/stateTypes.ts/publicApi.tsと既spec・新strikeout spec、唯一artifact、固定Python caller/test。まだ編集指示しない。prefix/T2/保存/UIの正確なpathは契約shape採用時に既対応pathから閉列挙する。main/develop直commit/push、共有DB、秘密情報、旧stashは扱わない。

## 4. 有限ステップ

| ステップ | 内容 | 成立条件 |
| --- | --- | --- |
| 1 | 操作単位契約24例・types/schema/参照 | 全応答/履歴/両cursor/23flags、独立交差/拒否・既case不変、非作者とP-1〜P-9事項別採否 |
| 2 | 唯一T1核/閉ABI/固定host | 旧37/BB/HBP全値保持、31,104交差/大整数/不正拒否、artifact再現/pin・独立確認 |
| 3 | prefix/T2/qualified source | 下記真正source/終了判定/旧variant保持・未評価拒否、非作者確認 |
| 4 | 同TX保存/GET/故障/越境 | PlayRow/runner/event/ledger/history/checkpoint/水位/両cursor/実参加者を不可分保存・復元 |
| 5 | 実画面で攻守交代/次半回復元 | 三振3PA→反対側通常球、元D5/ACK喪失、正式値/最終HEADレビュー/必須CI/通常統合 |

閉source extensionで両cursorと両チーム9打順/実投手/捕手を渡し、artifactがafterから次攻撃/守備側を選ぶ。BE/UIに2outからのside/打順計算を複製しない。cursorは数学では未信頼提案、保存では初期roster＋真正PA履歴/既checkpointから独立導出して照合する。旧Source shapeは別variant保持、追加fieldのwire-head commitmentも明示する。

T2の現halfCompleted=false/outsUnchanged=trueを第3outへ流用しない。真正half完了factsを既終了規範へ接続し、検知lockと正式終了宣言を分ける。最終回/コールド/延長/TB/XMARKの未評価をno-end成功へ上げない。PlayRow/三振/投球回outはbefore打者/投手、次sourceは新守備側の実投手/捕手。PA開始参照はeventId、playIdではない。履歴/保存source不足を打順1や現在投手で補わない。

## 5. DoDと検証

- [ ] ステップ1全比較面と手例24、active3456/独立cursor31,104・大整数/拒否・既case保持の非作者確認
- [ ] 唯一核/閉ABI/固定Python host/再現artifact/履歴・型・旧回帰
- [ ] T2/真正source/wire-head/旧variant保持の接続検証
- [ ] owned PGの正常/同D5再送/各段階故障全取消/別tenant・owner拒否/GET
- [ ] 同一候補実HTTPSの攻守交代/次半回/元要求再送/ACK喪失/reload
- [ ] 必要正式7.7/最終HEAD/必須CI/通常統合

重検査はrootが所有したDB/port/tempだけで直列化、共有DSNはunset。数学cache成功を実保存/Ready/ACKへ上げない。全MVPには在塁時BB/HBP・全打球/走塁/交代/取消/訂正/終了/再開・全操作offline/交代/閲覧・成績/CSV/負荷/復旧/実機/運用HTTPSを引続き含む。

## 6. 初回採用（2026-10-31、PO委任によるCodex /root判断）

作者ready-v2 filesd3b4afcf912d09797f7140e36f81bc7cd7cc36099113ff0fd8f1ab5ab49bc345、追補90bd6943964ae666cf562975acf231878b9f4b9edebaf22e181f93c935984acbと、非作者REPORT8f109109297bf2e8d87c40c2909a9c188e0e3fad05af427a1442c1b4008b4cf0（P0/P1=0）を照合し本操作の計画を採用。子plan/branchを分離し、inactive cursorの独立性/履歴の具体化を反映した。契約schemaのファイル名は既terminalと揃えてstrikeout_pitch_schema_v1.jsonとする実装選択。許可は上記ステップ1の契約作成のみ、核/公開ABI/保存/T2/UIは単位契約採否後。旧失敗/レビュー通算/P6留保は保持。山田正輝本人の実値確認・署名ではない。


ステップ1の不可分CLI整合追補（2026-10-31、PO委任によるCodex /root判断）: descriptor/branch-map/normalization404caseの正規CLI通過後、required-setの旧SO2代表行を保持した16配置別新rowが既identityに重複すると実測した。既required/covered/missingを減らさず、新row自身の行要求区分を追加するexact5を許可する。contracts/state-transition/required_set_row_rules_v1.json（SO各8新partition）、required_set_coverage_declaration_v1.json（旧identityと新16rowの真正観測）、scripts/check_required_set_coverage.py（_ordinary_case_id_migrationsの既117＋terminal15を全保持し新canonicalSO24の有限exact unionだけ）、既tests/test_required_set_coverage.py（未知/重複/旧保持の対向）、contracts/state-transition/game_end_coverage_declaration_v1.json（normalCaseCounts.stateTransition132→156）。旧SO2case/期待/既normative/旧missing5を削らない。required56/covered51/missing5→72/67/5は候補算定で、実CLI・非作者が値を照合するまで受理値にしない。

同じ新24caseに必然なcontracts/state-transition配下既JSONのcount/source digest/真正参照だけは、実CLI依存閉包に限り機械追随できる。具体path/field/完全前後/算出元SHAを最終manifestへ必ず固定する。semantic predicate/未充足/旧期待/unknown拒否/過去履歴/正本/正式受理・sealの変更は含めない。checkerは登録済み新24caseの有限集合だけを受け、任意new caseや不正migrationを通す一般化は禁止。mathematics/ABI/T2/DB/UIの正式実装はまだ指示しない。


JSON型比較P1の是正（2026-10-31、PO委任によるCodex /root判断）: 非作者が新SO応答の23flag全てをtrue→1/false→0へ置換しても既schema consumerと全応答testが通る偽positiveを再現。要件/標準schema/野球意味ではなく、既check_input_axes_descriptor._json_equalのdocstring『booleanとintegerを混同せず』をnested object/arrayで満たさない実装不具合である。新SO testの型保存fullresponse/flag型対向は維持した上で、scripts/check_input_axes_descriptor.pyと既tests/test_input_axes_descriptor.pyのexact2を追加許可する。現type一致条件は保ち、dictキー/array長と各値を再帰的に同じ規則で比較する最小修復とする。const/enumの既拒否を緩めず、nested boolean/integer・array/object・null/string・samevalueを対向に含め、全23flag/history/request boolの実schema拒否を検査する。他の_json_equal関数へ無関係な伝播をしない。schema/期待/受入を緩める変更は0。既descriptor全test/正規CLIとSO局所をまとめて実行し、旧合法例が維持されることを非作者へ渡す。


## ステップ1の本操作限定受理とステップ2指示（2026-10-31、PO委任によるCodex /root判断）

固定14manifest4a3a9e328e441c387bcb0b6d93331728b95c6f5eb9ad0f2a2d9d529436bfe4ab/diff34d961b4a5feb111d6beb922b817963e7eaf6df1bca1a4b4b9039bf84d76bf7dと非作者REPORTec491621e379620c24d47f78dd3b7d696f5ba1e5f82065801a8bce8c71fb85beを全byte照合して採用。初回nestedbool/int P1は実schema/実24consumer全23fault拒否で閉鎖。作者58/descriptor52、独立39/24full/31,104/90桁24/192配置/readonly型/CLI4成功。旧51/132/全operation-undo・旧missing5を保持、新required72/covered67/宣言missing5。旧33failと不採用symlink対照・未達は保全する。

P1-P9はcache strikeout-root-stage1-approval-20261031/receipt.json SHA e2e5ce54eed46cbc81edf0210e6b0a2cbae25007185a16627d2ef9fe2bdfe120 で項目別受理。P6は通常非作者の数学射影/履歴比較資格だけを受領し、旧封印/曝露留保・新blind未成立・全P6未了を保持する。全T1/正式共有資産7.7/全CIを成立扱いしない。数学source/artifact/hostは次段成果であり、T2/実Port/DB完成を着手前へ循環追加しない。

ステップ2の編集はfrontend/src/domain/{state.ts,stateRules.ts,stateTypes.ts,publicApi.ts,publicApi.spec.ts,terminalPitch.spec.ts}、新strikeoutPitch.spec.ts/strikeoutPitchArtifact.spec.ts、新backend/src/pitchlog/domainrt/strikeout_pitch.py/既対応dirのtest_strikeout_pitch.py、配布frontend/public/domain/pitchlog-domain.js/.jsonに限る。既firstPitchArtifact/firstPitchContinuationArtifact/ordinaryPitchArtifact/ordinaryPitchContinuationArtifact/initialGameRosterArtifact/courseQuantizationArtifact各.spec.tsは既公開口全保持＋新deriveStrikeoutPitch一名の完全集合追随だけを許可する。旧操作の意味/期待・未知拒否を緩めない。build scriptや追加sourceが不可分なら先にexact path/必要差分を返す。

state/stateRulesの単一核へcache候補を選別統合し、履歴生成は実before/after/flags/両cursorから一回。Pythonに算式/履歴差分を複製せず固定host一回、JSONの未知/余剰/duplicate/nonfinite・alias/coercion拒否を守る。旧全ABI/37/BBHBP・新24fullresponse/31104/90桁/tail/変造を実artifactへ通す。生成artifactの実shaをrootへ渡し、contracts内pin/正式宣言はrootだけが追随する。公開ABI/typed caller/再現build/三層・非作者source確認をこれから実施し、step3のT2/qualifiedsource/wire/save/UIはまだ実装指示しない。本人逐行確認/署名は代記しない。


### ステップ2の不可分な実行pin・D11・旧保存互換の追補

2026-10-31、PO委任によるCodex /root判断。唯一artifactへ新公開操作を追加したため、既実行pin7path（backend/domain/manifest.json、terminal-pitch-manifest.json、play-prefix-manifest.json、backend/tests/fixtures/first_ball_payload_vectors_v1.json、contracts/state-transition/play_prefix_v2_cases.json、play_prefix_v2_d11_vectors.json、play_prefix_v2_payload_vectors.json）の現在実行SHAだけを新実byteへ追随する。旧priorArtifactSha256・既互換7行・既意味値を保持し、派生sourceSha256/sourceCasesSha256は実source byteから再計算する。cache strikeout-root-artifact-pins-20261031 は全field/逆比較を固定し、旧Git artifactと新artifactで56全応答の一致を確認済み。fixture照合を実HTTP/DB成功とはしない。

旧保存互換はplay_prefix_v2_source_compatibility_v1.jsonの既7行を保持し、新executionとの有限組だけを追加候補にする。各旧artifactを実Git blob/SHAからロードし、該当sourceFormatの全既受理ベクタ・historyTail・宣言操作を新artifactと全応答比較してwitnessを固定する。新artifact自身への保存互換も旧受理済artifactとの比較を根拠とし、自己比較で可決しない。不一致の組を許可せず、未知SHA/未知format/操作欠落の拒否を維持する。新三振の保存互換はステップ3以後の別契約であり今回追加しない。

D11は新backend/domain/strikeout-pitch-{manifest.json,property-catalog.json,property-catalog.schema.json}、contracts/state-transition/strikeout_pitch_d11_vectors_v1.jsonを既manifest schemaに整合して追加し、backend/tests/domainrt/test_strikeout_pitch.pyの全24比較を実消費/JUnit traceへ結ぶ。同testの数式/期待生成/旧拒否を変更しない。rootだけが正式JSONを編集し、作者14path固定後のtest追補はrootが所有する。独立レビューで新manifest・全pin・witness・三層比較を確認後に実装ステップ2を採否する。全T1/P6/共有7.7や保存/画面の完了を意味しない。


ステップ2 pin後のwire自己echo追随（同PO委任によるroot判断）: 全VitestでterminalPitchWireの56全値＋小数観測1が失敗し、実行SHAだけ置換したpayloadのnextCheckpoint.digest/nextPrefixRef.checkpoint.digestが旧wire-head hashのままと確定。数学契約56の期待を変えず、play_prefix_v2_payload_vectors.jsonの自己echo112欄だけを既正式play-prefix-wire-head-v2の正準SHA規則から再導出する。Python実consumerと独立field列挙/JSON正準化の一致を確認し、同T1/T2/差分V8/観測/参加者・旧priorを維持する。wire-head fieldや検証関数/拒否の変更は0。未変更metadataと関係ない期待を候補出力で更新しない。frontendのhandoff-loader依存3失敗は別に現固定契約byte/依存OID/versionへ照合し、実値が変わった登録だけに限定して追随する。全件失敗・修復前source26レビューと後発修復を区別し、追加非作者確認後に採否する。
