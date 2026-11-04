---
feature: mvp-strikeout-pitches
status: active
承認: 済（PO委任によるCodex主担当判断・ステップ1〜3の契約/計算/型付き呼出し/純source検証機構を限定採用、実保存/UI未了）
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

上記handoff追随のexact1はcontracts/state-transition/appendix_e_consumer_handoff_v1.jsonのartifacts中state_transition_contract_v1.jsonのdigest一欄。SO24追加後の実SHA-256へ再計算し、出自OID/version/consumerBindings/未受理・消費pending/他artifact2と拒否検査を変更しない。受理や曝露の更新ではなく現実byte参照の修復である。


## ステップ2の採用保存（2026-10-31、PO委任によるCodex /root判断）

source27 manifest592d8e3de04def872e02824e68ed58f27d23047b9c6c5a4cf1c72ff826726dc1を全byte照合し採用。非作者REPORT03234246f36b02ad193b58fa17c88ebd4f8c9f641a8e4527d0538f71dc04dbb1、後発r2 REPORT4e9eb001a90bf44ecb122e81d974f7c4ca7507d04fca0687ee917263e551fdd1で新P0/P1=0。作者核14＋root pin7/互換1/D11期待包絡・宣言/実consumer/handoff1を一単位で保存する。数学24/独立cursor31,104/大整数/全拒否・旧回帰、実Git旧artifactとの互換9組7536全応答、旧7行/旧prior不変、artifact再現BFB492ec…43004Bを確認。D11新equivalence1の五判定/hash成立、wholeJUnitComplete=false/旧91除外・全mutation/BOOT未完は保持する。

全FE初回60failed/2813passed（wire自己echo112/旧handoff参照1）を保存し、期待値や検査を緩めず正式hash規則から機械修復。非作者独立wirehead56/FE88/BEseal59、root修復後全FE135files/2873passed133.92秒、BE数学D11旧92passed38.91秒・pin影響610passed5.25秒・backend全体ty/関連ruff成功。数学sourceは後発2JSON修復前後不変。これらはSO計算/固定hostの完成であり、SO保存・画面/全T1/P6新blind/正式7.7/CI/通常mergeの完成ではない。ステップ3は次の真正source/T2/両チーム実参加者への接続単位として続ける。

主担当判断receipt: cache strikeout-root-artifact-pins-20261031/root-step2-approval.json SHA5a88bc9713c9dd2d90ee4c087989e5aaae005341aca5dbe48393106ffa3ad09c。PO本人の逐行確認/実値確認/署名は代記しない。


## ステップ3の最小具体化（2026-10-31、PO委任によるCodex /root判断）

cache strikeout-pitches-step3-connection-20261031/CONNECTION.md SHA734f78adb247ecba28c808367e7863877c7b4547c7b580f286a2f958588f4109、非作者REPORT-step3.md SHAe121f56e718abf50076deb1fc3b32fe391f2fed5ea9b823892181392e165fcb7（阻害P0/P1=0）を照合し、本節の有限接続を承認する。全体計画/旧意味の再裁定ではない。

最初の実経路は真正started top1/両cursor1/1→三振を含む投球3打席→bottom1（away保持4/home1）→相手の通常球。両9枠・実投手/捕手は既InitialRosterProjectionから供給し、唯一artifactがafter側の参加者を選択する。Python/UIにcursor・半回・打順・進塁の算式を複製しない。Pythonは実sourceの署名/anchor/順序/全field照合と同artifactによる再生結果を確認する。初期1/1を任意の旧v2へ補完しない。旧v2 bridgeは真正全履歴から半回未完了・交代/取消等なしを証明した場合のみ別途接続し、その完成/実DB/TB開始を初期started経路の数学実装前提へ追加しない。

旧derivePlayPrefixWithContinuation/version2/source/private/wireは閉shapeのまま保持し、新deriveLineupPlayPrefixWithContinuation・version3/scope play-prefix-v3を追加する。新source/応答は両cursor・両roster/投捕digest・真正PA開始eventId・source position/ref・before実参加者・after実参加者・T2 facts/decisionを明示拘束する。自己echo2だけ除いたwire-head-v3を正準hashし、prior/source/履歴digestを落とさない。PlayRow/flags/責任/runnerはbefore、次参加者はafter。V8は実history差分を保持する。現v2 ABIへoptional fieldを黙って追加しない。

T2はT1本体の新意味範囲ではなく、既承認終了規範への接続依存として主担当が供給責任を引き受ける。現evaluateEndConditionNoEndは部分核のみであり、新endConditionCoreへの単なる移設で全6outcome実装済みとはしない。同一coreを一般化し、既wrapperは旧全応答/拒否を保持、既game_end_contract248/validation12をdescriptorの具体入力へ写して実核へ通す。期待lookup/期待からの出力生成/別Python計算は禁止。0/1out SOもoutsUnchanged=false、第三outはhalfCompleted=true。検知lockと明示終了は分離し、TB開始FR009が未提供なら次投球資格を拒否する。未評価をno-end成功へ上げず、数学上のSO範囲を初回top1だけに縮小しない。

作者の編集許可は次の有限集合。新契約6はexact shape/key/type/provenance/wire/対向を先に固定しrootへ渡す。その契約の非作者確認後に同ステップのsource実装へ続行する。共有正式登録/pins/core/台帳はrootが直列管理し、作者は無関係な共有資産へ書かない。

- contracts/state-transition/lineup_play_prefix_v1.d.ts、lineup_play_prefix_schema_v1.json、lineup_play_prefix_cases_v1.json、lineup_play_prefix_payload_v1.d.ts、lineup_play_prefix_payload_schema_v1.json、lineup_play_prefix_payload_vectors_v1.json。
- frontend/src/domain/endConditionCore.ts、endConditionCore.spec.ts、firstPitchContinuation.ts、lineupPlayPrefixContinuation.ts、lineupPlayPrefixContinuation.spec.ts、publicApi.ts、publicApi.spec.ts。
- backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py、lineup_prefix_source.py、backend/tests/domainrt/test_lineup_play_prefix_continuation.py、test_lineup_prefix_source.py、tests/test_state_transition_contract_schema.py。
- 生成frontend/public/domain/pitchlog-domain.js/.json。既firstPitchArtifact/firstPitchContinuationArtifact/ordinaryPitchContinuationArtifact/initialGameRosterArtifact/ordinaryPitchArtifact/courseQuantizationArtifact/strikeoutPitchArtifact各.spec.tsは公開口exact集合へ新一口の追随だけ。

DB読取・lock・真正sourceの実供給/bridge一回consume・SQL/ACL/token登録/保存/GETはステップ4の不可分依存であり、このpure source verifierの成功で代替しない。repositories/play_prefix.pyの実DB変更はまだ許可しない。必要な追加pathは不可分な理由とexact差分を先にrootへ返す。新意味空白だけ具体入力/既条文へ起票し、新しい人間承認待ちをtechnical namingだけから増設しない。未実装操作を成功へfallbackしない。


ステップ3前半の新閉ABI採用（2026-10-31、PO委任によるCodex /root判断）: r2 files869a5688…全新6byteと非作者REPORT24e690e4…を照合し採用。全34full/旧SO24数学不変/真正started手順10/明示wire32field、102schema/782flag型拒否/1088wire変異/272request拒否/strict型を確認。DHtrueで投手が打順1と重なるP1は実BFB名簿核の旧拒否→9打順外の投手ID修復後受理で閉鎖。before/after参加者/責任/roster-layout/wire依存だけ機械追随しT1/T2/history全34不変。他の型指摘は旧Participantsが既catcher必須4欄と判明して誤認撤回、変更0。作者初稿/失敗/撤回を保全、回数reset0。root-shape-approval.json SHA14c58617d53563db9d3496d7e3f31c56fab19ebf3749f624910322d21f93131dへ実判断対象/日時/根拠を記録。これは契約shapeの採用であり、新公開口・T2全6outcome/実source/DB/UI・P6blind/7.7の成立ではない。次に前節の有限source/host/T2一般化を実装する。新artifactのcurrent実行SHA/wire自己echo/旧保存互換は実build後にrootが再導出する。旧v2 ABI・検知終了/宣言分離・未供給TB次投球拒否を保持する。


ステップ3唯一核の不可分exact1追補（2026-10-31、PO委任によるCodex /root判断）: frontend/src/domain/state.tsを作者許可へ追加する。既applyCountRuleだけが両cursor更新を持ち、旧ordinary/terminal公開口は旧Snapshot shapeのためcursorを受けない。新内部deriveLineupPitchで既scope判定を共有し、同applyCountRuleを一回だけ呼んで新v3の両cursorを得る。publicApi/Pythonへcursor算式を複製しない。旧export・旧scope/拒否・旧ABI/返値/全ベクタを保持、新たな載塁BB等の未実装操作を成功へ拡張しない。stateRules/stateTypesの無関係変更は許可しない。最終source差分と一回計算/旧全値不変の独立レビューへ含める。


ステップ3の実artifact参照とwire派生（2026-10-31、PO委任によるCodex /root判断）: author pin-request cd85f221…の現在実行653欄に加え既firstball v7Json内86欄を明示追随する。cache lineup-root-artifact-pins-20261031に対象11path/1120全leaf前後を固定。旧v2/新v3の自己echoを正式選択field26/32から再導出し、実Python selector/hash90例と実818e artifactの旧v2全56/新v3全34全応答へ照合した。数学T1/T2/history/カーソル/参加者/IDは全不変。started chain02〜10だけは実前v3出力のexecutionをpriorへ結び、前sealed nextCheckpointのdigestをrequest/source/provenance/previousRefへ順次受継いでwireを再導出する。初回startedのBFB priorと旧互換16行・他の歴史的priorは保持する。一括prior置換/期待から数学出力生成/成功仮応答0。これは数学とwireの機械整合で実DB/HTTP/記録権資格/全T1/P6成立ではない。旧保存互換の新execution有限witnessと新D11登録/最終sourceレビューはこれから別に固定する。


ステップ3 current再導出とD11の有限追加（2026-10-31、PO委任によるCodex /root判断）: 共有T2 COLD03のcompleted-bottom有効得点境界（R9/cold7点7回/7回裏2out→有効home7点＋thirdout→8回表）の欠落を唯一coreの同loopへ修復し、818eを未採用中間として保全、実7dcへ同11path/1120leafを再導出した。新34/旧56実artifact全値と実Python wire90例が再一致、旧wrapper boundary=nullでは返値拒否不変。COLD03一般境界をSO/実保存到達へ拡張しない。新D11はrootのみがbackend/domain/lineup-prefix-manifest.json・lineup-prefix-property-catalog.json・lineup-prefix-property-catalog.schema.json、contracts/state-transition/lineup_play_prefix_d11_vectors_v1.json、新backend/tests/domainrt/test_lineup_prefix_d11.pyを作る。採用済み34の全期待値を包絡し実34typed/direct host/実hashを一つのequivalence traceへ記録、別testをroot専有して作者既testの並行書込みを避ける。未計測mutation/全BOOT/P6/DBを登録だけで成立扱いにしない。root旧保存互換は未採用818eを追加せず、旧16全行保持＋実旧Git artifactとの新execution有限11witnessだけを独立比較後に追記する。


step3境界P1の有限修復（2026-10-31、PO委任によるCodex /root判断）: 非作者が実7dcのCOLD05（R9/cold7点7回、away7点優位の7回裏thirdout→8回表）でcold-end/recorded-scoreを確認したのに、新Decision契約がx-markだけを許していた。既COLD05/完了裏COLD03に対する型宣言漏れで新意味判断は不要。root writerが新d.ts/新schema/新payloadschemaのexact3にcold-end/recorded-scoreの同literalflag variantだけを追加、既8variant/34math/wire/7dc byteは不変。Python側は作者が同閉variantを合わせ、既Decisionのoutcome/flag偽装受理P1も全enum・bool対向で閉じる。検査を緩める一般bool/任意xMark許可はしない。cache lineup-cold-decision-shape-repair-20261031に完全前後を保全し、最終非作者closureを確認する。


## ステップ3接続数学・typed/source検証機構の採用保存

2026-10-31、PO委任によるCodex /root判断。source18 files0df2ccac0cbeae3c44a4a87e532881e58df007fbed7671510ed1846dd82e0e9b/patchb5096675…とroot後発を含むsource39 manifest0684b89c…を全byte照合。非作者REPORT5716f64c9d7434e7133f9a516ae81f7af97dbbbafd66e47ddd41096ea5eb24d0/独立combined c524917f…は同39byteと完全一致し未解消P0/P1=0。Decision偽装・COLD05 recorded-score型漏れ・prior beforeInning=0の3件を実対向で閉鎖、旧DH P1とParticipants誤認撤回・自己echo48更新漏れ・中間818e/7dcを保全し回数reset0。最終唯一artifact4cf1eceb…/57405Bの再build一致。

作者BE154/FE582/契約2、独立BE63/FE310、root全frontend136files/3180passed137.19秒が成功。独立旧no-end wrapper66,560全返値/null一致、一般248/12のadapterは規範位置から境界を形成し期待decisionから入力逆算しない。cold14境界、384Decisionの合法9/拒否375、schema不正2163leafの公開口成功0、新34/旧56artifact全応答、wire90全field/hash、旧Git5から新有限11互換9414全応答を確認。actual互換27は旧16全保持＋最終4cf11で、未採用818e/7dcを歴史的priorへ追加しない。

D11の新34はnormative包絡/実factory34/direct34を実消費し、公式collectorで新equivalence1の五判定/hash/値連鎖が成立（対象testだけのcomplete、全BOOT/全D11/全mutationは未成立）。数学T1/T2/履歴/カーソル/参加者・旧ABIは機械pin追随以外不変。fresh Chromiumの新34/旧56は純数学検査でHTTP/DB/画面ではない。

初期/2/8/9prefixと第三out→相手ordinaryを実artifact再生するpure source verifierは成立したが、これはDB資格・実Port/tenant/fence/anchor/lock/ページングを発行しない。これらを提供するreader/同TX保存/GET/ACK/画面はステップ4/5の未提供依存として残す。全T1/全MVP/P6blind/正式7.7/必須CI/通常mergeを成立扱いしない。次は既v2実接続を再利用した実reader・SQL/token/ACL・one-use frame・同TX原子的保存へ進む。

主担当判断receipt: cache lineup-root-artifact-pins-r4-20261031/root-step3-approval.json SHAb78a5202f3440a461c7d176c99918e03d316b1d72188341186cf4b7fe119cb24。本人逐行確認/実値確認/署名を代記しない。


ステップ4の独立先行不具合修復（2026-10-31、PO委任によるCodex /root判断）: 計画非作者が実psycopg dialectで既prefix read系のBIGINT generation署名をINTEGER bindへ狭める既存不具合を再現した。新origin/ACL起案の完了を待たず、既契約に合う修復をbackend/src/pitchlog/repositories/function_operations.pyと既backend/tests/test_function_operations_boundary.pyのexact2へ許可する。既再利用4prefix tokenの正規SQL署名を実assetから照合し、必要な有限BigInteger型登録/bindだけを直す。2^31境界/2^63-1と負数・bool・範囲外/unknown関数の拒否を維持し、新SQL/役割/自由関数名/新origin登録はこの先行修復に含めない。作者一名にこの2pathを専有させて非作者差分確認後に保存し、旧v2/承認済み派生値を無関係に再裁定しない。全step4の正式起動はoriginの最小ACL/RLS閉包・exact登録の反映r2を確認してから行う。


既登録prefix4の期待追随（同PO委任によるroot判断）: 先行binder修復の影響7moduleは338成功/4失敗、同4は修復前にも再現した。既registry期待が16件のまま・既PLAY_PREFIX4追加後もdevice-stateを末尾と仮定したことが原因。backend/tests/test_sync_apply_function_registration.py exact1を同workerへ追加許可、既boundary試験の閉全16＋正規4literal=20と旧7＋新4objectsの全11identityを厳格に固定し、device-state実位置と全20tupleで検証する。未知/余剰拒否・元全16項目を保持、actual自己参照で期待を生成/部分比較へ緩和しない。元candidate3d90…/4fail/新対向7failを保全、影響全件と非作者確認後に保存する。


## ステップ4：真正reader・実Port・同TX保存・GETの起動

2026-10-31、PO委任によるCodex /root判断。cache step4 r2 CONNECTION7b8e7fbe…/paths62dc9eb3…と非作者REPORT-r2 7617d99d…を照合、旧P1二件は有限署名/BigInteger/実最小ACLとRLSへ反映した。残る同2表9列の個別SQL9pathだけを機械追記した反映r3をstep4-paths.jsonへ正本化し、他全field不変・root正式writer25→34を検証した。これは既採用方針/実装選択の範囲で新PO意味裁定・新全体計画ではない。

作者の許可23製品/15既試験とroot正式writer34は同JSONのexact集合。function_operations.py/test_function_operations_boundary.pyと、先行期待修復のtest_sync_apply_function_registration.pyはprefix_generation_bind_fixの専有を独立採用handoffまで維持、それ以外の新reader/Port/源泉・private v3/GETを担当pr188_final_reviewへ許可する。rootがproducer由来SQL/manifest/DDL/role・columnACL/RLS/CAP/正式runtime/repositoryとsource説明/源泉wireの最小追補を直列管理、作者は仮SQL/stubで成功経路を作らない。必要追加pathは不可分理由とexact差分を返す。

started-game tagのeventIdは実成功開始原本のstart_request_idへ技術binding、confirmed-playはOperationEvent.idのまま。成功attemptが複数でも同tenant/game/start_request_id/historicalDeviceなら同一logical origin、0/異なる原本2つは拒否しlatest/min選択0。歴史Aのdeviceと現在Bのwriter認可/epoch/fenceは別、origin取得はrequests4列＋attempts5列だけ、FnOwner専用SELECT policy2と既FORCE RLSを保持。app新直接grantやgames/lineups/delivery新権限は追加しない。秘密nonce/credential/暗号文は取得/露出しない。現在game/roster/rules等は既同TX readerから供給する。

zero論理refはid=実start_request_id/rev1/history0、自己循環なしinitial-wire-head別tagを実zero原本から正準hashする（private content digestと別）。旧None readerを黙ってouterrowへ変えず新exact origin read token/一行関数を追加。既SQL初回coalesce0+1との差はv3初回1→2/次2→3と物理history epochの区別を対向に含める。fixture a…digestは真正値にしない。

新v3 private checkpointに両cursor/lineup実投捕/PA参照/after/T2/走者/元before物理投影/前wire/last event+ledger/全digestを保存。以後は同TX locked CP＋直近accepted event/ledger/PlayRow41/PlayRunner10/history1を全照合→同artifact一回再数学、毎球startedから全履歴を再取得しない。旧pure全再生をnative fastpathへ黙って読替えずEvidence別variantを置く。旧v2 bridgeは別依存でinactive1補完0、履歴は既keyset25/max100/水位・epoch・tenant/game/generationに束縛する。

既D06/認可/device/元D5内容一致と連番・内容拒否の先行順、結果不明を新D5/新bodyへ置換しない保証を維持。新D5の実source lock→実一回artifact/loadedhash/fullcompare→私有ready frame→既kernel event/ledger→同writerで一回consume→SQL prepare/PlayRow/runner/history/checkpoint/水位/admission→RG1最終確認/commitを不可分にする。T2/T4/runner/history/checkpoint途中故障は全取消を実証、成功boolを外から受けない。

物理PlayRow/flags/責任とPlayRunnerはbefore（第三outのbefore走者を消さない）、after checkpointは反対側実投捕/次打者。T2検知lock後newpitchは拒否し旧D5再送は解決、gameEnded自動true0。未供給終了宣言/再開/TB開始をnoend成功へ補完しない。別device拒否試験はwrite資格を対象とし、同team viewerのGET閲覧権を不必要に塞がない。oldDTO/reader保持＋v3別DTO/読取を提供する。

実owned PGの実POST作成/開始/初期権→zeroGET→三振3PA→反対側ordinary→GET/再読込を通す。同D5/故障全取消/別tenant・write device・失効epoch/nonce二重消費/歴史A→B/lock後newD5拒否を検証する。事前投入試合/常時成功/仮Port/数学fixtureを原本にしない。新reader/SQL/実DB/GETはこれから、正式7.7/最終CI/通常merge・全MVPは未成立。UIの接続はステップ5へ残す。

先行BIGINT修復の採用（2026-10-31、PO委任によるCodex /root判断）: actual既3pathはcache r2と全byte一致、独立REPORT341c878b…/checks21246bc9…（P0/P1/P2=0、独立309成功）と作者342成功を区別して確認した。有限PLAY_PREFIX登録集合のORだけを既BigInteger条件へ追加し、3関数9bindの型を正す。他16関数/prepareのSQL・拒否条件は保持、strict20登録期待と全11binding objectを照合。root-approval.jsonへ実版/各SHA/判断時刻を固定し、commit後に実接続writerへ当該3pathの所有を移す。実DB・三振保存成功とはしない。

実core到達に必要な有限追加（2026-10-31、PO委任によるCodex /root判断）: 実prefix_pathのmode検出/実Port exact型から_bind_ordinary_pitch_executionへの呼出と、applyのPort資格選択に新v3が未登録であるため、`backend/src/pitchlog/sync/prefix_path.py`と`backend/src/pitchlog/sync/apply.py`の既2pathをステップ4へ追加する。新LineupPort2/mode3の閉じた分岐だけを既経路に接続し、旧認可・D06/D5・再送先行・拒否順・未実装操作拒否を変えない。既23productは25になる。他file/未知modeの開放はしない。候補最終差分の非作者確認で旧経路不変を検査する。

実プロトコル位置への整合修復（2026-10-31、PO委任によるCodex /root判断）: 実Portの正規source.positionは今回D1/今回D2/既appliedWatermarkであり、初回1/1/0となる。新v3数学が全3値同一とstarted D1=0を要求したのは既SourcePosition語彙との接合不具合で、偽値による回避を禁止する。既`frontend/src/domain/lineupPlayPrefixContinuation.ts`と対応既specを実装writerへ追加し、D1=applied+1/正規D2正値と実source・coreのactual D2一致/started1,1,0へ有限修復する。root契約34のposition/sourcePositionと該当包絡seal/pinは真正要求値から導出し、T1/T2/履歴/打順/参加者の期待は変えない。既v1/v2仕様の意味は不変、後発差分と位置不正反例を非作者確認へ渡す。artifact/sourceShaの実変更は正規全pin/互換/D11をまとめて追随し、旧実証4cfの成功を新SHAの保存/UI実証へ読み替えない。

正式登録の生成counterpart追補（2026-10-31、PO委任によるCodex /root判断）: 新originの有限function登録/既repository JSONを追随すると、生成済み`backend/src/pitchlog/repositories/repository_contract.py`のrevision/source_digest/operation token/function/capability各定数と、`backend/tests/test_authz_repository_contract.py`の全有限集合期待も不可分に変わる。旧terminalの正式生成手順に従い既2pathをroot専有のステップ4へ追加する。新originのCAP/token/functionだけを実registry/catalogから導出し、旧全値・順・拒否条件を保持、期待を部分集合にしない。sourceの未知要素/基線承認をこの追補で受理済みにせず、全前後を別非作者へ渡し、7.7正式受理/最終CIは後続として区別する。


ステップ4再開時のnative再生負例是正（2026-11-04、PO委任によるCodex主担当判断）: 最新HEAD9457099bとdirty39をcache pr192-resume-audit-20261104/manifest.json（SHA26975f040c94ca660497c7c588657084f646827a0c5c439babf43ddcbb46f44a）で保全照合し、旧後発2fileは11/1監査と同byteと確認した。まず既native修復の試験としてbackend/tests/test_ordinary_pitch_native_evidence.py exact1のみを担当pr192_resume_auditへ移管する。旧test_host_replay_mismatch_rejectedは前段wire sealで停止しhost再生の比較を検証できないP2があるため、元のseal拒否対向は保持し、正常Evidenceから実host.callへ到達した回数/要求を明示確認したうえで再生結果の不一致を閉拒否する対向へ是正する。必要なfault injectionは試験内だけで実artifactの呼出を保持し、成功応答/仮Portを製品へ供給しない。実DB/HTTP成功とは扱わない。他38path/source/契約/artifact/refs/共有台帳は変更禁止。両共有DSN unsetのpure試験/型lint、候補作成に関与していないレビュー後に採否し、本体reader/正式SQL/全pin/owned PGの既step4を継続する。

## 2026-11-04 主担当再開：191接合候補でステップ4を完了する

PO委任によるCodex主担当/root判断。原WT `feature-mvp-strikeout-pitches`のHEAD421621c9と保全dirty39（38追跡+native1）を変更せず、隔離WT `feature-mvp-strikeout-integration`/同名feature branchを作り接合する。旧候補を巨大な別成果集約へ移植せず本#192の履歴・操作範囲を維持し、最終PRは#192へ通常統合する。候補基線22437086は#191の画面3系列成功/非作者95c025d3通過版だが、実CIのcore有限層修復と正式mergeは未了。正式#191が統合されたらその差分だけ追随し、候補成功と正式developを区別する。

既再開調査packet `pr192-step4-integration-preparation-20261104/REPORT.md` SHA256 `2f94ce6c4a19a20df91004f69b3cfad0b5418a8553130131b1feaaa4f82070f7`の実4競合（consumer handoff/coverage件数/required set/schema試験）を解消し、#191の全旧119+terminal15=134へSO24を加えた158case/67matrix行を保持する。旧49ID/自然ID/3coverage負例/履歴原典/閉schemaを落とさない。必要なmanual fixture schemaにはSOだけの閉分岐を加え、全操作の既定値を一般許可しない。

次に保全38patch+native test1を有限適用し、追加3競合（started route/operation registry/terminal stamp test）を解消する。テキスト適用可能でもv3 DTOには既#191のrecovery alias/共有assert_prefix_matchesを伝播し、routerは直接3reader分岐を保持。旧SQL比較pinの正式登録を旧literalへ戻さない。原native修復a15578f…の独立P2採用3efa74db…はexact1に限り、全source受理へ広げない。

SQL22候補は12新規/10既存before/全after SHAが新基線と一致する。既backport済BigIntegerは重ねて実装せず、既20関数/拒否と新LINEUP origin1の正式登録・ACL/CAPを実物から照合する。既ステップ4の固定登録/3層/全同TX/故障対向/真正source・同artifactの順で完了し、独立レビュー後にowned PGの9SO→反対側通常球/再送/全取消/越境を通す。coreの次lineup有限層は#191の最小修復を継承して宣言・負例を先行し、未登録のままpushしない。ステップ5画面は4の採用後に開始する。新たな野球意味/仮成功/認可や耐久保証の弱化を許可するものではない。

### 2026-11-05 統合候補のartifact再生成と実行pin接合

702948fcの実sourceで唯一artifactを再buildしcda0b594…/57468bytesとなった。既ステップ2/3/4で許可済みの実行pin13と既first_ball_payload_vectors_v1.jsonをrootが専有追随する。execution/hashと明示first-ball artifactSha256だけを新実byteへ更新し、旧prior/互換の全既行は不変。v3の同一chain内だけは前行で実際に生成するcheckpoint/prior artifactへ連結し、v2/v3自己echoは既正式wire-head規則から再導出する。T1/T2/履歴/参加者/走者の数学期待を実装出力で生成せず全値保持する。sourceSha/sourceCasesShaは実byteから導出し、旧Gitとの完全応答比較証拠が成立した組だけ新互換行を追記する。全前後と後発差分を非作者へ渡し、固定候補/局所比較と実保存/画面/正式受理を分離する。

### 2026-11-05 実PG初回の制約停止診断

owned PGの既BB/HBP2系列は成功、新v3系列は初球のafter_t4_projection故障注入より前にIntegrityErrorとなった（全2pass1fail222.80秒）。assert/故障要求を保持し、backend/tests/db/test_terminal_pitch_storage.py exact1だけでSQLSTATEと固定schema/table/column/constraint名の診断を保全し、失敗時の構造化結果をJSON文字列で出力する。SQL本文/原値/資格は出さず、例外を成功へ変えない。既test/共有base scriptは変更しない。主担当のPO委任で本step4原因確認を進め、同じ失敗を無根拠に再実行せず新診断版の新v3対向だけをowned環境で再現する。

診断版43.04秒の実再現でSQLSTATE23503・fk_play_rows_batting_resultを特定した。旧ordinaryテスト関数自身はcalled-pitch語彙をowned DBへ登録するが、新v3テストは同準備を呼ばず、参照先がないまま見逃し9球を送っていた。FK/認可/保存処理を緩めず、新v3テストexact1のowned admin準備へ同じ固定called-pitch語彙1件だけを追加する。試合や保存済みプレイは投入せず実POST作成を維持。診断版の制約名出力も残し、新候補固定後に同v3対向のみ再実証する。

語彙修復後のowned実測は初回保存/全取消/次球まで進み、3球目の数学で停止した（56.43秒）。試験がcalled-pitchを9回送っていたが、正式V3-STARTED-CHAIN-03/06/09はcalled-strikeoutを明示要求する。固定artifactでS2のcalled-pitch拒否と正式called-strikeout成功を実再現した。核のscopeを広げず、test入力列を既正式契約どおり[called-pitch,called-pitch,called-strikeout]×3へ修復し、参照語彙にcalled-strikeout1件を追加する。10球目ball、故障/再送/越境/保存後全assertは不変。これは既採用操作の検証入力修復であり新たな意味裁定ではない。

### 2026-11-05 ステップ5：v3実画面接続の有限単位（PO委任で主担当採用）

候補基線は隔離HEAD3ca52e24。#191候補224を含むが正式develop統合済みとは扱わない。rootのowned実API検証は新規POST作成/開始→[called-pitch,called-pitch,called-strikeout]×3→反対側ball、同D5、T2/T4故障全取消、越境、有界GET再読込が1pass126.84秒。旧BB/HBP2系列と併せ、実source9b76・source80の非作者e0829693/試験入力f5ac387aの成立範囲を継承する。実画面の証拠には読み替えない。

本単位は、既controller/single-writer/耐久queue/attempt/ACK/原要求再送を共有し、明示的なv3 read/要求/response/wire/source型を追加して三振3PA・攻守交代・反対側1球・reloadを実画面へ通す。次打者/両cursor/outs/相手側投捕/T2は唯一artifact `deriveLineupPlayPrefixWithContinuation` の全応答から採り、UI/providerに野球算式・期待lookupを加えない。旧v1/v2復元/既BB/HBP保存・再送を保持する。v3 GETは `projection=play-prefix-v3` / `read_kind=lineup-prefix` を閉検証する。実readerはzero/native v3限定で旧保存を返さないため、既内部queryへ `recording=play-prefix-v3` を閉追加した明示モード/画面入口で選択する。既v1/v2の入口・読取・復元はそのまま保持する。未知/欠測/破損v3をv2へ降格、旧保存を初期cursor1/1でv3へ補完、通信失敗を旧成功へfallbackすることは禁止。

実装移管のexact19（本planは先行追補のみ、採否後に製品変更）:

- 新規 `frontend/src/api/lineupPrefixWire.ts`、`lineupPrefixWire.spec.ts`、`lineupPrefixGame.ts`、`lineupPrefixGame.spec.ts`、`fixtures/lineupPrefixGame.v3.json`。
- 既 `frontend/src/api/terminalPitchWire.ts`、`terminalPitchWire.spec.ts`。v2の閉判定を維持し、v3でも同じ構造検証・正準JSON/hash primitiveを共有するための有限公開helper追補だけ。
- 既 `frontend/src/screens/GameScreenOrdinaryPitchProvider.ts`、`GameScreenOrdinaryPitchProvider.spec.ts`、`GameScreenOrdinaryPitchController.ts`、`GameScreenOrdinaryPitchController.spec.ts`、`GameScreenOrdinaryPitch.lifecycle.spec.ts`。新v3 discriminantを明示し、pending/ACK喪失・元attempt/D5/body再送・認証世代/記録権の再確認を既経路へ接続する。
- 既 `frontend/src/screens/GameScreenRecordedRestore.ts`、`GameScreenRecordedRestore.spec.ts`、`GameScreenRecordedRestore.vue`、`GameScreenOrdinaryPitch.vue`。有界v3 GET、認証epoch/要求世代に束縛した復元、実after参加者と新三振選択肢・状態表示を接続する。
- 新規 `frontend/src/screens/GameScreenLineupPrefix.e2e.ts`、`GameScreenLineupPrefix.playwright.config.ts`、`backend/tests/db/test_lineup_screen_e2e.py`。既owned screen環境/実HTTPS/app/broker/権限fixtureをimport再利用し、試合・プレイの事前投入/固定成功応答を使わず実画面新規作成から通す。必要な既called-pitch/called-strikeout語彙のowned admin準備だけを許す。

上記は異なるpath19件。generic durableQueue/ACK parser/HTTP client/source/artifact/contracts/共有manifest/台帳は変更しない。閉型の不可分な受け口が別pathにあると判明した場合はその根拠とexact追加をrootへ先に返す。新JSONはAPI形の独立structural fixtureであり、T1/T2/参加者/履歴の数学期待は正式契約の固定例を使う。成功出力から数学期待を生成しない。

型codec→GET/provider→controller/耐久/復元→component→Playwright/owned補助の順に進める。Vitestの実artifact対向と旧v1/v2/BB/HBP回帰、未知/欠測/余剰・scope/tenant/game/ref/roster/participant/position/hash不一致、元要求再送/ACK異常/epoch変更/停止・再起動をpure局所で確認し、対象prettier/eslint/vue-tsc/buildを行う。PG/ブラウザ実行・共有DSN/鍵・app起動はrootが直列所有し、作者は起動しない。rootの採否後に実装し、通常非作者review後、root管理の実画面9球→反対側球・reload/同D5/ACK喪失の実測を完了条件とする。新PO裁定・本人署名・正式#191統合/必須CI/全MVP成立を代記しない。

ステップ5開始判断: rootが追補SHA6ea1153b…と現v3 reader・既controller/queue・操作単位契約を照合し、実PG3ca52e24の1成功126.84秒/非作者e0829693とf5ac387aを根拠にPO委任採用する。exact19をpr191_integration_auditへ移管し、既backend/正式資産の最終受理はroot直列で並行する。内部URLqueryによる閉モード指定は可、利用者へv1/v2/v3/codec等の実装語を選ばせず、入口は記録できる操作を示す日本語とする。旧入口と復元/再送は保持し、旧ゲームを自動v3変換やHTTP失敗から無条件fallbackしない。authorは新コード開始前にrootの191最終候補C4追随完了の通知を受け、同branchの新固定点を使う。

正式route原文の実装追随（2026-11-05、PO委任による主担当判断）: 認可CLIがdesign_provenance[6]の旧started reader原文不一致を検出。既非作者e0829693で審査済みAPI reader全原文だけをAST範囲から抜粋し、contracts/authz/route-registry.jsonの同1fieldと公式build_derived_lock由来route-registry.lock.jsonをroot専有で追随する。HTTP53操作/既認可/C2/claim/decision/entry250を変えず、他provenance全値不変。最終正式差分の非作者照合を保持し、Oracle新受理/全7.7成立へ読み替えない。

実artifact呼出しのexact2追補（2026-11-05、PO委任による主担当判断）: frontend/src/lib/generated/wrappers/domainArtifact.tsと同domainArtifact.spec.tsを画面writerへ追加許可する。既唯一wrapperのFirstBallDomainOperation閉unionへ既配布済みderiveLineupPlayPrefixWithContinuation一名だけを明示追加し、実artifact呼出しを検証する。未知操作拒否・旧全operation/順序・型境界を維持し、string cast/別invoke実装/数学複製は不可。artifact/数学source変更は不要。

### v3 sourceの有限登録（2026-11-05、PO委任による主担当判断）

RAW131は非作者調査dcf27b60…で旧site再浮上82/新v3site45/旧原典不一致sentinel4と分類。実製品sourceは非作者e0829693で採用済み固定9b76全byteと同一。新6owner90tupleは旧v2移設45+新v345だけ、旧37site metadataの前後と旧4ownerの検証済supersessionを登録し、旧693/6ownerfixture全値・旧不変2owner・全拒否を保持する。131全免除・path除外・現在木から期待自己生成は不可。

rootが独立分類由来の新fixture tests/fixtures/pr192_tenant_source_expected_v1.jsonを先行commitし、その固定Git全byteへ期待を束縛する。実source9b76と期待fixtureの別固定原典を名前付きfrozen inputへ登録し、宣言+fixture+sourceの同時改変でも不変Gitとの比較を残す。作者pr191_residual_independentへscripts/check_tenant_boundary_bypass.py・contracts/tenant_boundary/base-allowlist.json・新tests/test_pr192_tenant_source_registration.py・既tests/test_check_tenant_boundary_bypass.pyのexact4だけを許可する。新fixture/frozen-inputs/plan/census/受理historyはroot所有で作者非編集。C1旧AST/残るC2/C5/全未知source拒否を保持し、異owner/余剰site/行移動/source+declSHA偽造/原典非祖先/旧fixture改変/不完全supersessionを対向へ含む。新登録自身は作者以外の別非作者がレビューし、正式tenant9受理は最終source固定後にrootが直列再導出する。

旧source回帰のexact1追補（2026-11-05、PO委任による主担当判断）: tests/test_pr191_tenant_source_registration.pyを登録writerへ追加許可する。旧6owner/693 fixture全値・全test/反例を保持し、旧v2 sourceの比較対象だけを不変693と正式eb8旧Contractの歴史viewに明示する。現v3後継の実source検査・旧用途保存と未知拒否は新専用testで追加照合し、歴史viewへ逃がすだけで現sourceを検査しない変更は不可。原典は既名前付き固定Git/固定fixtureから読み、raw literalや現在宣言由来の自己期待を増やさない。


ステップ5の実画面追随（2026-11-05、PO委任によるCodex /root判断）: 同版32b7a035の実POST/GET200後に画面の履歴が消える反例を実測。read validatorがprefix_ref.checkpoint.id（保存wire headのID）をcheckpoint_anchor.id（開始原本由来の保存anchor）と混同している。既planのzero論理ref/物理history区別、play_prefix.pyの初期原本/同doc整合、旧v2 validatorのrevision照合を根拠に、frontend/src/api/lineupPrefixGame.ts/spec.tsと新fixtures/lineupPrefixGame.recorded.v3.json、既GameScreenLineupPrefix.e2e.tsのexact4を修復する。anchorはstorage_anchor/開始originと照合、prefix checkpointはrevision/historyを照合し、無関係IDの同一強制だけを是正する。拒否の削除や応答補完をしない。実GETcaptureは型接合回帰であり数学の期待値原典ではない。新正常・anchor不一致/版不一致の負対向/既旧test保持、非作者確認と同版実画面を要する。

同じステップ5実接合追補: r5では作成201/初球画面復元を通過し2球目GET200で別の拒否を再現した。wire prefix historyVersionは毎球増分、private storage/history epochは同世代のまま（実値2対1）。既native documentとterminal_pitch_projection.pyの保持、旧v2 readerと同じ区別に合わせ、この無関係な同値強制を除き、anchor/storage相互epochとcheckpoint revisionの一致は全保持する。実2球GETを同capture fixtureのlaterValueへ保存し陽性回帰を追加、既負対向を削らない。r4の作成503はr5閉診断で再現せず原因未確定として残す。

ステップ5のACK喪失試験追随: 同版14b9の実画面は9球/三振3PA/攻守交代/元D5再送200/10球目POST200まで到達し、応答喪失後にretry DOM欠落で停止した。既clientはCookie更新不確実を安全に無効化しAppがloginへ移すため、未検証認証のままretryを要求する試験は不正。製品認可/epoch/queueは変えず、既「状態を再確認」操作と実GET /auth/session 200→同tenantの10球GET→reload→元要求再送を実画面試験へ挿入する。新資格発行/POST login再送/認証迂回なし。旧10球原子性・同body/attempt・再送二重保存なしのassertは全保持。全操作offline継続の受入とは分離する。
