---
feature: mvp-undo-native-connection
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-05、原案SHA 03a8bf7ee9fd835ae3d2502358ba23ba8e11fbfcbfb93606a237f1e16528aac2、非作者敵対7221cc2bc5f0f1891a4bed6aecd7651fdc49d5c4c09e085eddfb815a956977ce）
重さ分類: コア領域
branch: feature/mvp-undo-runtime-integration
created: 2026-11-05
計画レビュー周回: 1
確定ゲート周回: 0
---

# 実装計画書：取消の正式接続

- 状態：非作者敵対レビュー7221cc2b…を経てPO委任Codex /rootが計画採用。本体は閉契約3先置き・別非作者確認後に成立操作から着手する。
- 予定枝：`feature/mvp-undo-native-connection`。
- 固定基線：依存候補 `feature/mvp-batted-hits-final-candidate@1ea9fdeed984f644c3f6fe052f1516238361b9e4`。正式develop提供とは区別し、#196通常統合後に必要差分のみ追随する。
- 参照spike：`feature/mvp-undo-connection-spike@ae3298afa988f7ee6949ba1e7e4687f2182aa223`。全35pathは不採用。非作者REPORT `4ca9b0e92449a191bc50d0247ee5d6d310af96a5615ecc280c690e16c2fd1829`のP1全5件を保持する。
- 目的：実画面で新規作成→開始→2球→取消→連続取消→次球→サーバー再取得/reload。通常同期・結果不明・再起動・原子性・tenant/権利・成績/CSVへの取消反映をMVPから外さない。

## 1. 既決の根拠と非目標

要件FR-006、NFR-018/019(a)、付録E-1 HistoryEffect、ADR-003 D-6/D-8/D-11と採用済T1操作単位計画が正。取消対象は直前の取消可能な1件で、undo自身を積まない。空履歴はnothing-to-undo。pop後の完全stackを次回入力にする。Dは検査範囲で実行時の深さ上限でない。同期済/未送信で取消方式を分けない。監査行を物理削除しない。状態補正FR-040は既採用根拠の範囲だけ扱い、今回新採用しない。

spikeの暫定wire/flag/専用GET/手組み投影・tail-only範囲を製品規範へ昇格しない。仮Port/固定応答/常時成功する資格を用いない。51dの安打/D01を744で上書きしない。P6/P7全成立・実PG・正式7.7/CIを部品検査から先取りしない。

## 2. 3実装単位

| step | 作業と到達条件 | 開始条件・依存 | 独立して進められる範囲 |
|---|---|---|---|
| 1/3 | 唯一51d系artifactへ純undo核と閉ABIを接合。旧全operation/全値/安打D01を保持。契約10行、v3cursor、current/head一致拒否、実host全応答一致、旧回帰・pin/manifest整合まで | 本計画採用。本操作の入力/結果/拒否の閉契約をrootが先に凍結・非作者確認。既P1全5を接合の採用条件へ残す | DB/Port/HTTP完成を着手条件に追加しない。純計算・codec・境界対向は先行可 |
| 2/3 | 正式P1で真正現状態/完全stackを同TX取得・一度計算・一度保存。event/slot/D3/ledger/current checkpoint/history/source Sとinvalidationsを不可分更新。正式readと次球へ接続 | step1実host契約。正式undo V7/V8/target/ACK、projectionとevent-watermark/physical-play区別を照合・最小追補。D5/拒否順・結果不明/後着遮断の既契約維持 | 既schema/source履歴/権限の調査、入力/投影対向の準備はstep1と並行可。採用前に仮wireを保存しない |
| 3/3 | 既queue/ACK/epoch/排他へ接続。実画面新規→2球→undo→undo→次球→再取得/reload。未送信/ACK消失/再起動/越境/権利/故障と同要求再送を実測 | step2正式API/read。既queueの同D5/body/attempt保持・結果照会/不明バリア。操作ごとの採用範囲を表示 | UI部品・既queue境界の確認/試験準備は並行可。画面成功扱いは実API/実PG/同候補の実測後 |

ステップ単位で対象版・前後SHA・非作者レビュー・検査・委任採用を固定する。コミットは通常日本語Conventional Commits＋正確な`(ステップ k/3)`を1個。次stepのsourceへ無断拡張せず、rootの既委任による採用後に進む。

## 3. unit1の閉契約（起案。root固定→非作者確認後にsourceへ）

- 操作名 `applyUndo`。入力exact2：`current`と`history`。currentは既正準stateFields/scoreboard、v3ではbattingOrderBySide。historyはexact1のstack。全整数は十進文字列、任意精度、既有限値域を保持。欠落/余剰/未知/重複キー/不正decimal/非有限値/JS numberを拒否し、補完で観測を作らない。
- 最初の適用範囲は既確定プレイ履歴（既23flag・既state/board差分・任意v3cursor差分）。他既知kindは未対応を明示、未知kindを成功させない。空stackは現状態/board/cursorを不変、pops0、nothing-to-undo。
- 非空stackでは**各提示差分のafterとcurrentの対応する実値が全て一致**することを逆適用前に要求する。state/board/cursor全て。currentにcursorがないのにheadにcursor差分がある等は拒否。差分未提示のフィールドを推測で埋めない。tailは全値・順序を保持して1件popする。入力不変。
- 一致しない入力は既エラー`INVALID_REQUEST`へ、未知操作範囲は既`UNSUPPORTED_T1_SCOPE`等の使用可能性を根拠照合して閉定義する。新拒否順やD5消費意味は純ABIへ持ち込まない。
- 成功値はexact5：`operationResult/after/stateEffect/historyEffect/historyContext`。stateEffectはADR D-8の全比較面（state/board/23flags/historyAndResult）を欠落させない。spikeの4key応答は未採用なので後方互換の製品契約とはしない。failure envelopeは既domain error shape。型/schema/Python decoderを完全一致させる。
- `delta/set`の表示分類は既規範・10行の拘束で決まる入力だけ採用する。不足する分類へローカル規約を無言で広げない。数値復元が一致することだけでstateEffect一致を代替しない。

## 4. unit1 writer exact9（新WTのみ、rootが計画採用後）

| path | 許可変更 |
|---|---|
| frontend/src/domain/undo.ts | spike核を選別移植。current/head全対応一致の検証・純逆適用。野球前進計算のコピーなし |
| frontend/src/domain/undo.spec.ts | 既undoRows10をそのまま消費、全比較面。liveness-onlyは既schemaの無視範囲だけ。v3と不整合current拒否/入力不変 |
| frontend/src/domain/publicApi.ts | applyUndoのみ追加。既helperの既operation分岐不変。閉ABI・正準整数/構文・全結果5key |
| frontend/src/domain/publicApi.spec.ts | 新閉ABI対向を追記。旧全test/期待を保持 |
| frontend/src/domain/undoArtifact.spec.ts | 同一ビルド済artifactを実行し規範照合・前進出力→取消の往復/完全履歴/連続取消・cursorを検証 |
| frontend/src/domain/firstPitchContinuationArtifact.spec.ts | 旧公開キー全順序を保持し新applyUndoだけ追加、旧期待全値不変 |
| frontend/src/domain/ordinaryPitchContinuationArtifact.spec.ts | 同上 |
| frontend/src/domain/strikeoutPitchArtifact.spec.ts | 同上 |
| frontend/src/lib/generated/wrappers/domainArtifact.ts | 有限operation unionへapplyUndoのみ追加。認可/保存資格にしない |

writerは上記9以外へ書かない。state.ts/stateTypes.tsは既型を読取利用し変更しない。追加scopeが必要なら根拠を返しrootが計画追補/所有を直列確定する。共有schema/descriptor/生成物への勝手な追随、旧期待の更新、spike専用HTTPの移植は禁止。

## 5. unit1 root専有の共有proposal（writerはcache候補のみ返す）

固定可能な新規scopeは次の通り。旧共有ファイルの全更新集合はrootがGit差分で**先に列挙して凍結**し、別writerと重ねない。

- 新閉契約3：`contracts/state-transition/undo_v1.d.ts`、`undo_schema_v1.json`、`undo_cases_v1.json`。期待は既undoRows規範/独立手例/実前進出力由来の往復試験を区別。ランタイム出力採取をgoldenへしない。legacy10行がfull currentを持たない事実/既D+1矛盾を記録し、試験側補完を新規範成立に読み替えない。
- host decoder2：新`backend/src/pitchlog/domainrt/undo.py`、`backend/tests/domain/test_undo_host.py`。計算式なし、唯一artifactを1回呼出し、全成功値/失敗を厳格decode。型やJSON値を保存資格にしない。hostエラーを内容拒否に潰さない。
- 配布2：`frontend/public/domain/pitchlog-domain.js/.json`は唯一`pnpm build:domain`からrootが2回再現生成。旧12公開operation保持＋applyUndo1（個数は基線実体の閉集合から算出し、推測で固定しない）。
- D11新manifest/実host規範/property/mutation/collector・schema登録・trace、既manifest/directTarget参照、保存payload vectorのartifactSha、execution pin/compatibilityはrootが公式helperと全前後集合で直列提案/反映。新`backend/domain/undo-manifest.json`/専用catalogの必要性を既D11方式と照合する。
- 既artifact用pinを盲目的置換しない。旧全操作の規範・全応答差分・現自己互換の有限witnessを再生し、旧→新を包括互換と主張しない。source/body/意味が変わるものだけ必要な正式値を再導出する。

root側共有proposalはunit1実装に属するが、最初のwriter9へ混ぜない。契約/host decoderは9と物理パスが異なるため、閉schemaを先行固定後に並行実装できる。全候補の最終版は別非作者レビューを受ける。

## 6. unit1検査・採用条件

1. 旧10規範の件数/全値/ignoredOutputPathsを固定。新full-state独立例は空/1/2/D/保証外D+1を区別し、旧矛盾を期待書換えで隠さない。
2. 真正前進出力のafter/全historyをそのままundoへ渡す往復を、通常球・安打4・第3アウト・延長/v3cursorで実施。連続2popの全状態/board/cursor/history一致。未実装前進操作をfixture成功で提供済みにしない。
3. 各state/board/cursorのhead.afterだけを1項目変える対向、欠落/余剰/unknown/number/重複キー、破損成功応答、再入/入力改変拒否。
4. sourceとbuilt artifact両方で旧operation全規範/全応答、特に既D01 walk-offと新安打/既BB/HBP/K/ordinary/座標を保持。旧期待変更0。型/lint/生成差分/2build再現。影響範囲中心→統合候補で必須全件を行う。
5. host round-trip/D11/collector等の根拠全SHAとscopeを固定。DB/正式7.7/本体同期/画面はunit1完了に含めず、後段の必要条件として明記。

## 7. 判断票へ出すもの（現時点でPO回答を新たに要求しない）

- 既delta/set・D+1履歴合成矛盾のうち原典から一意に閉じない**実入力**だけ、旧caseID/実前後/選択肢/影響を既判断票へ集約する。未決行を暫定規約で成功させず、成立した空/整合確定プレイの単位から実装する。
- FR-040採用状況、取消後の物理play/論理prefix/current S保存の既契約を照合し、既決はroot委任で正本追随。新しい得点/打点/取消範囲・D5/拒否順変更が本当に必要な場合だけPO判断を求める。
- DTO/列名/新wire形式版/配置・検証環境は既委任内の技術具体化としてrootが対象版/根拠を記録する。spikeのP1全5を閉じるために新しい人間承認待ちを増やさない。

## 8. 完了記録

各step終了時にrootが単一台帳へ「新たにできる操作／提供版／実証／残る依存」を追記。採用者はPO委任rootと明示し本人確認/署名を代記しない。候補環境と正式develop、UI/API/DB、emulation/実機、故障例/実観測を分離。3step完了もMVP全体の完成判定ではなく、残る全操作・訂正・終了/再開・成績CSV・閲覧・オフライン/引継ぎ・性能/運用/対象実機を維持する。


## 採用記録（2026-11-05、PO委任Codex /root）

原案03a8bf7e…/scope2d626c83…/packet202906ae…を非作者7221cc2b…（P0/P1/P2=0）で確認し採用。原案からの差はfrontmatter/状態/この採用記録のみ。固定点1ea9fdeeの新専用WTを作成し、元spike ae3298afと#196候補を変更しない。最初の許可はroot専有の閉契約3候補起案・非作者確認で、unit1 writer9の本体開始はその成立後。認可/DB/HTTP完成や全操作契約を追加開始条件へしない。既10の期待/留保・5P1・全3段とMVP条件は維持、人間署名/P6blindとは記録しない。


## unit1閉契約3の限定受理（2026-11-05、PO委任Codex /root）

原案packet27ab055b…/初回非作者4000878e…のP0=0/P1=1/P2=0を保持し、Signed数値の末尾LF誤受理だけを反映1packet ed8ea2cd…で是正。非作者5c7d6e760c13c6c5269cd7c0842f3a12f2dfe97b85fb1427704a9ae991f14effが1field差分、req/res24改行否定/整数型文法/5001桁/旧10+10/新14全値/257履歴/tscを独立再確認しP1解消1・残存0。初回のreq/res全体疑いはUnsigned/Positive既strict・Signedだけへ精密化した履歴も保持する。schema40bb46c0…/d.tscca60b55…/cases1f01f39a…を純計算operation単位の閉契約として受理する。casesのstatusだけをrootがcandidate-not-accepted→accepted-unit1-pure-contractへ更新する承認メタデータ追随を行い、期待/入力/規則/原典SHAの全値は不変更。正式D11全成立/P6/P7/実Port/DB/画面を受理したとはしない。

body開始条件の本操作分は成立。writer9は既規範で閉じた空/整合確定playの一般構造・field逆適用から実装する。fixture/caseID lookupや固定結果は不可。delta/set未分類3/旧D+1矛盾固有行は未提供留保し、深さや桁数で実行上限を作らず全MVP後続で解決する。旧23flag/4比較面・旧全公開operation/安打D01を保持。DB/全操作契約を追加前提へしない。


## unit1源本/hostの接合採用（2026-11-05、PO委任Codex /root）

TS9初版packet81c99aa1…とhost反映1（外部resource拒否P1を非作者b17cac7d…で解消）を全候補非作者f08e9041…へ渡し、既決errorOrderに対する15複合不正の拒否順逆転P1=1を固定した。rootは同許可9内のpublicApi.ts/spec.tsだけを反映1し、同値spanを全shape/range/decimal検査後の別passへ移した。型/範囲の先行・数学・規範・期待の全値を不変更。非作者9c5504dee028bd6854b16593984aa321270a54dafe516925f50fa52702e2b0eb（初P1解消1/残存0、元21対向21一致、追加未知/型12、host52/FE30、空192/旧1878有限4操作、独立公式build再現）で源本9＋host2＋公式生成2を採用する。author unionはTS9 batted_hits/閉契約pr191・root/host・境界反映root、全候補reviewer undo_unit1_whole_independentは非作者。P6blind/本人署名/人間逐行確認とは記録しない。

root全domain25file822成功34.81秒、同新artifactの実Nodehost52成功2.59秒、公式2buildは4f4544e13434af17fa10a36426e195c70ec36e15f3d84c8b65953718f8a8f0e4/75600byteで一致。旧1878は4操作の有限一致で、12公開操作の全入力包括互換とは主張しない。元12公開キー順序保持＋applyUndo1、旧publicApiのimports10/functions31全文保持。

本採用はunit1の計算/閉境界の途中成果でありunit1全完了ではない。正式D11/全pin/自己互換witness/全操作往復・後続複合/reset分類・全CIは残る。先行51dを固定した参照はrootが全更新集合を先に列挙し、古い互換/原典pinを保持して正式helperで必要分だけ追随するまで、枝を正式提供/通常統合済みとしない。step2同TX/P1/read/成績invalidationsとstep3queue/ACK/画面・MVP全範囲を維持し、仮Port/固定成功へ置換しない。


## unit2の最初の縦断契約とunit1共同受入（2026-11-05、PO委任Codex /root）

read-only REPORT6e9fb6b78ce8414d453574c2f2bfe795fa47b73d4f67ed56c0df6e70f428d4e6/paths6460478a99f9a906c3150196c15049008d5ef8c7fccb196f5d735abd8040c9b1/contract案10afc07b1d6be09ee7707b9cc416881f9bb6179b1052beeebe9fda20530cfbb0を根拠に、共通prefix橋の最初の操作を2球→undo→undo→次球へ固定する。D3/event head、projection head、未取消active play headを区別し、空activeでもD3>0を正当に表す。既event/state_diffが原典、物理play行は論理取消で保持し次物理番号は再利用しない。全nonplay skip、fake play admission、started/D3=0偽装、逆計算コピーを禁止。

最初のcache-only起案をcontracts/state-transition/nonplay_prefix_bridge_v1.d.ts、nonplay_prefix_bridge_schema_v1.json、nonplay_prefix_bridge_cases_v1.jsonのexact3へ許可する。既V5=undo、own D2/V6/V8なし、V10対象、V7新閉版/expected checkpoint/実artifact計算要求結果の対応を既sync U1-U8/DI規範と照合し、不整合を成功へ緩めない。2球/2pop/次球の全state/board/flags/history/原本と再送・既取消別D5・非先頭・別tenant/世代・改変・未知control/本当gapの対向を入力から手で導出し、製品出力を期待に採取しない。独立レビュー後rootが契約を受理、本体/DB許可は次のexactpath追補で行う。調査担当pr192がcacheだけに作成し、sharedsource/refs/正式資産/台帳/DBはrootが専有する。

unit1の数学単位は成立済み、実appからのcollector到達は現undo未接続なので未成立。unused CLI/console scriptを作って到達済みにせず、unit1/2接続固定点で正式composition/比較/negative登録・実到達を共同受入する。pin更新16path/現在参照902箇所はread-only a7bc8da347ba0fe7f4c5e1fbda31825b8f1038e56df9a9b33892c5c2e996e5e5へ束縛し、旧互換57/旧witness/原典pinを保持、current供給分だけを公式再生成する。registry.schemaのrunner/CIjob閉2field追随も別の非作者を要する。これをunit1完了や品質条件削除とはしない。

再開は既FR007/4.0-4からオンライン操作であり、未採用game_reopenを断中Must7へ追加しない。後続online-control CAS/終了確定版/再開後追記/再終了/成績S連動はMVP必須のまま、本2球取消の開始前提へ全操作待ちを追加しない。未知操作・複合/reset未解決は明示未対応とし、MVP完成から外さない。


## unit2閉prefix契約3の採用（2026-11-06 JST、PO委任Codex /root）

作者packet4f6dc4ee9a86c2c0bc1509338d0468baeab45fbd974192b27e153ceb2c33c7d1を非作者REPORTf1295e78a40ee9e5090cd4732d96490bacb1df2de9893532279bf5326843a136/checks9d6c7e46114cabe59635f7762a3c4d048187ef93ad8bfa6436d824923d7675dc（P0/P1/P2=0）で採用する。原典U1-U8/DI3/DI5、2球→2pop→次球の全6状態・既unit1純request/response全値2一致・nominal11/余剰key834/EOS型56/shape10拒否/strict tscを独立確認。37対向中semantic16/runtime11は仕様例であり実製品の拒否実証ではない。ownD4と真正連結されたtargetD4は異なり得る既意味を保持し、現_validate_v10の等置不足は本体で是正する。任意過去世代の許可ではなく実連結/先頭/原本/資格を検査する。

rootはexact3を前後SHA照合して反映し、cases.statusだけcandidate-not-acceptedからaccepted-unit2-prefix-contractへ変更する承認metadata追随を行う。他の入力/期待/留保/原典参照全値は保持する。相殺carrierは初期成功Sourceから外された未提供referenceであり、既kernelU2/同TX両D5結果/水位/原典監査の義務を変更しない。全取消/相殺/空/世代跨ぎ・既規範の完成は後続のMVP必須として維持する。新3headは全nonplay skipを許可せず、旧playを物理削除しない。これは本体開始の操作単位契約であり、P1/真正Port/DB/HTTP/成績S/D11/画面成功やP6blind/本人逐行確認/署名を成立扱いにしない。


## unit2本体の実装許可：真正source→単一host→同TX投影（2026-11-06 JST、PO委任Codex /root）

閉契約3を97ed8a33で採用し、既unit1 host/唯一artifact4f45を本体へ接合する開始条件が本操作分で成立した。作者pr192へcache-onlyで新source exact6と対応test exact6を許可する。sourceはbackend/src/pitchlog/sync/{undo_payload,undo_execution,undo_ports,nonplay_prefix_bridge}.py、backend/src/pitchlog/repositories/nonplay_prefix.py、backend/src/pitchlog/authz/nonplay_prefix_sql.py。testsはbackend/tests/{test_undo_payload,test_undo_execution,test_undo_ports,test_nonplay_prefix_bridge,test_nonplay_prefix,test_nonplay_prefix_sql}.py。既source/生成物/正式assets/共有台帳/refsへ作者は書かない。rootは共有kernel/registry/HTTP/既GET/SQLスタンプとactual D11/pin/正式派生のwriterを継続する。

目的はpayloadの形検査だけで止まらず、既実E1/記録権・handle/session/topTX/source/lease境界を再利用して実checkpoint/active原本を読み、既undo hostを一回だけ実行し、一回opaque frameから固定SQLへ同TX投影する接続候補を作ること。単なるJSON/ref/hashやcaller boolでsource/frame資格を作らず、既getterのsource identity/nonce/lifetimeと結ぶ。渡された全historyを信用せず、実reader原本と全値照合する。形不正/内容拒否と、真正source/host/DB不可用・結果不明を区別し、例外をFalse/成功へ変換しない。全D5順序/連番/認可/初期権/故障原子性・既kernelU2を保持する。

SQLは既正式Table/列/CASの実在形を照合して最小私有function familyとして生成し、実accepted ledger/event/slot/target/現在head/世代連結/physical max+1を再検査する。旧play admissionへfake play_row_id/source_d2を入れたりCHECKをoptional化しない。旧物理play/履歴原本を論理取消し、3head/active空/D3>0/新checkpointとS invalidationを不可分に更新する。実SQL登録が未了なら明示閉拒否し、成功stub/仮DB/専用spike GETで提供済みとしない。既tableだけで真正資格を実装できないと判明した場合、必要な私有admission1表/migration/固定schema/権限と不可分exactpathを返しrootが限定追補する。一般role昇格/任意SQL/共有DB/新秘密発行は不可。

source6/test6と実hook不足のexact契約を一緒に固定し非作者へ渡す。rootが不可分共有hookと正式登録を同じ統合候補へ接合し、owned2球→2pop→次球/同D5再送/越境/世代・非先頭/途中故障全原状・canonical Sと既GETで実測する。source試験のdoubleや手例はruntime/PGの成功と区別する。unit1のpin/D11未完を数学開始の新条件に戻さず、実到達はunit1/2の共同固定点で受入する。全取消/相殺/訂正/終了再開/成績CSV等のMVP義務は維持する。


## unit2契約の実wire fingerprint接合反映1（2026-11-06 JST、PO委任Codex /root）

本体接続時に、EventSource.fingerprintを一般Digestのraw64へ束縛した旧契約が実E1のwire-v1:64を拒否するP1を発見した。作者と初回非作者の未検出履歴を初回P1=1として保持し、既ordinary Prefix Fingerprintの許可集合に合わせる最小反映を採用する。作者packeta02b343f9f8935e17dad7666530c0f0a0e804768ad6c8f75e31934e7a8d68b9a、非作者013cf20b45409507bdf9909266eb9381d45a909a0f04c0b929bf6af94a25af14/checks9a550f5740c9506cb4e39a1a9935267c52d537c93a10d8fad96c4dbf435e40b5（P1解消1/残0）を確認。schema新Fingerprint定義＋当該field参照、d.ts alias/説明と既cases保持＋scalar2肯定16否定だけ。独立実wireの旧拒否→新受理・既型との46入力採否一致/受理原値保持・無関係Digest拒否・strict tscを根拠とする。タグstrip/再hashや実ledgerとの不一致を成功へ変換しない。反映対象は既exact3だけ、以降も形の成功を真正source/資格/PG/全操作の成功へ拡張しない。


## 隔離接続候補の固定とadmission不足の限定追補（2026-11-06 JST、PO委任Codex /root）

最終#196候補3ecc85ab（実CI初回backend1case結果不明/他全success・原因未確定、同HEAD実PG単体成功後failedjob1回再確認中）と、成績v2実API/実read/故障3caseが同版で成立したbcee3dec、および取消純計算/契約e633e011を、専用WT/branch feature-mvp-undo-runtime-integrationへ依存合成した。元各枝/PR/証拠は保存し、正式develop/通常統合済みとしない。本branchは連続取消の単位に必要な依存だけの隔離接続用であり、全旧成果の一括移植ではない。以後本planの実runtime writerはrootの当該WT、原pure WTは保全する。

stats合成時の4生成衝突は、#196の既history/identityを保持し、incoming statsの3登録集合が既集合の真supersetであることを全値照合後、公式asset_digest/runtime derive/render/rederiveだけで描画した。catalog test衝突は両群の全定義を保持する和で解決し、拒否を削除しない。recipeと全根拠はcache undo-runtime-integration-20261106/resolve-stats-dependency.py。正式7.7/独立composition確認/全CI/新pin/D11/実接続は未成立。

作者の実DB形照合で、ordinary admissionのevaluated/consumed CHECKはplay_row_id/source_d2必須、既writerbindingだけではundo評価/target/CPの独立一回資格を保存できないと判明した。fake play/CHECK弱化を避け、private nonplay_write_admissions一表だけのcache-only実装を追加許可する。exact5追加はbackend/src/pitchlog/db/writer_binding/nonplay_models.py、同__init__.pyの登録、backend/migrations/versions/0042_nonplay_write_admission.py、backend/tests/test_nonplay_admission_model.py、backend/tests/db/test_nonplay_admission_schema.py。親revisionは既検証済み0041_stats_fact_versionsで固定し、0041の重複枝や汎用head upgradeを作らない。新source/root共有登録への書込は従来どおり別scope/別writer。

新表は同tenant/game/実writer binding/SessionトップTX/currentXID/nonce/一回phaseと、真正undo原本/target/世代連結/CP before-after/frame/artifact/restore/history根拠へ閉じる。own D2は作らず、準備→評価→消費の状態遷移を有限CHECK/制約/固定SQLで再確認する。自由JSON/bool/IDだけの資格、caller任意SQL、任意phase遷移、過去資格再使用、app直書込、RLS免除、物理削除は不可。owner/既roleの最小列権限・FORCE RLS/defaultdenyとtenant複合参照を含む採用根拠を先置きし、実PGschema/移行/原子性/越境はrootのowned環境で別受入する。shared DB適用/有料/運用公開/新秘密発行なし。新表宣言と旧ordinary全CHECK/source不変を非作者が確認する。


## 取消後の次球へ同一artifactを接合するscope（2026-11-06 JST、PO委任Codex /root）

新3head Sourceは既v3 Sourceと同じlast_source.D1=D3前提を持たないため、単にv3/startedへ偽装できない。作者batted_hitsへcache-onlyのexact6を許可する: frontend/src/domain/lineupPlayPrefixContinuation.ts、同spec.ts、contracts/state-transition/lineup_play_prefix_v1.d.ts、同schema_v1.json、backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py、backend/tests/domainrt/test_lineup_play_prefix_continuation.py（実既存pathをrootが照合済み）。新nonplay-prefix-source-v1だけを閉unionとして追加し、既T1/T2/forward計算を再利用する。旧Source3/全公開operation/旧1878有限4操作の入力出力とsourceを保持し、新Python/TS逆計算コピーを作らない。

CPのrestored/activeDepth/historyVersion/物理next番号を真正source値として別々に供給し、空active/D3>0でもbeforeをinitialに偽装しない。次の1球のnewHistoryEntry/contextは既計算が返すものを使い、targetD4/自世代/実世代連結を混同せず、未知controlや不正cross-fieldは閉拒否する。shapeは資格にならず、実source/nonce/TX/ACKはruntime側の必要条件と分離する。既prefix/opaque getterをcaller rawJSONで代用しない。

root専有artifact2/全pin16/互換witness/manifest/正式D11は作者が実assetへ書かず、必要後値を自分cacheの公式buildから提出する。基線は隔離integration eb5842de（後発planだけ追加）、新契約反映1のFingerprintをそのまま保持。次球公開範囲が閉じた時点でnative source17と合成・非作者確認・official build/pinを一周にまとめ、owned2球→2pop→次球/既GET/reloadで実接続する。数学単位やfixturesの成功を実Port/DB提供済みとしない。

unit2 runtime17反映1の限定採用（2026-11-06 JST、PO委任Codex /root判断）: 作者初版6600bdc3のP1（content hook boolとPort2列tuple不一致）/P2（非標準cwdのimport検査10診断）を保全し、反映1packet6a812fbca0fb7d942a26e3905438cba6a590c26134206a0af61ee729795a9b64を非作者926f39acdf6d2e6d56257e10e05ee98026e2714bcdb1436cafff4ecadbb5eafe/checks649dce1c13724a9f346e73a914867c0734be0eab9f61f3f066a632c64fe55646で採用する。新123（作者122＋独立1）/標準backendRuff/型0/SQL6・PLpgSQL6・DDL10構文成功。実code2/test2/import-only5の反映で、旧3888blob/他非import ASTを保持。hook自体がexact tuple[bool,str|None]と唯一有限理由を返しPortが検証、root便宜変換や仮成功で補わない。原wire再構成hashを捨て、同qualified CTE/readloan/同handle/TX/lifetimeとimmutable accepted ledger/consumed admission/全保存列/physical/historyのDB保存証拠profileへ明示的に分離、fingerprint原値/tagは維持。旧回帰399/1はarchive祖先だけでなく真のGitでwitness51d/現4f pin未接合へ進む事実を保持、400成功にしない。rootは初版before→反映1after全17を照合して接合候補へ反映する。ROOT-CALL dd8f8de3…の共有hook/actor/registry/canonical S/歴史初球semantic_event_json/genCP/GET/次球/pinD11/実PGはまだ別のroot接続工程であり、本採用だけで実提供済みとしない。

取消後次球Source6反映1の限定採用（同日、PO委任Codex /root判断）: authorpacketc7e1bc79d46d234fe02fc699e8b82c50d9b10857c42475e9eb51e4e321383288を非作者010aadb2f02ba4775a51d01ed2f71dcac224eb698c1e334908a1e45306207bf2/checks16da9de0712f3926fe236a903f86afd09ad6cd5107d9cebe34a798c7b6726fccで採用する。初回P1（世代跨ぎのD1大小を誤拒否）を保持し、同世代内だけ比較へ修正。独立元反例回復/Source21context全値派生/host12/TS75/135schema-host・122VM未知拒否/Vue型/公式2build4e8b32524b52ed1aee79737a62d2bdd0ddc28681079b24cee54512dd7bbbbef1・95274byteが成立。元手例DH=false等の不足は真正名簿派生の境界へ明示し、名簿/観測を推測したsourceへしない。旧1878真要求配列未取得の独立未実施は保持し、他成立条件からsource6の着手停止条件へ足さない。actual6はreflection1の変更3＋初版不変3の全後SHAを照合、rootが唯一artifactを1回公式生成して後SHAを確認する。正式全pin16/互換witness/D11と実Source17供給/同TX/HTTP/queue/ACK/reloadの接続は別条件、未実装操作を成功にしない。

歴史初球bootstrapの不可分root追補（2026-11-06 JST、PO委任Codex /root判断）: unit2 ROOT-CALLが要求する旧first-ball-play-v1原本のframe供給を進める。既真正getter/同handle/source/TX貸与の契約に基づきcache-only作者pr192へexact2を許可する: backend/src/pitchlog/repositories/recorded_snapshot.py、backend/tests/test_nonplay_first_ball_snapshot.py（新）。actual/source/正式assetsのwriterはrootのまま。既public _read_recorded_calculationとtry_readのD3=1/全event・slot・play各1/tenant/lifetime/全41列/開始名簿/実Node/破損vs非提供の意味を維持し、新private _read_nonplay_first_ball_frame(handle,event,source,*,source_event_id,generation,d1)をopaqueな歴史貸与からだけ到達させる。実getter _read_historical_first_ball_evidenceを同scopeで一回消費、自由JSON/偽handle/D3=1偽装/初期D3=0readerの転用は禁止。既既定before・実保存rules・actual lineups/player/originの既readを再利用し、現在artifactのvalidateInitialGameRoster/deriveFirstPitchWithContinuationで保存初球を独立再評価、旧artifact参照は既qualified compat witnessが必要で未知を通さない。accepted ledger/consumed admissionによるDB保存証拠profileと原wireを区別し、意味列のraw-wire再生成hashは禁止。

戻りはfrozen/slots HistoricalFirstBallFrameのsource_event_id/generation/d1/frame_json/semantic_event_json/stored_fingerprint/physical_json/expected_physical_json。scope貸与・全識別・fingerprint原値/tag/保存全41列・空runner原本・名簿/ルールを照合し、frameのbefore/afterContext・lineup/cursors/participants/responsibilityは既initial_lineup_source等と実t1.history_context/difference/afterを再利用する。新たな逆算/進塁/得点計算をPythonへコピーしない。必要な共通化はprivateなデータ読取・照合だけ、旧APIのguardを緩めない。型変換はDB column型に基づくJSON→UUID/aware datetime/finite scalar等の機械変換で、未知column/値の修復や補完をしない。実actor/DB未接合は試験doubleと区別し、未知legacy witnessや追加tokenが不可分ならsource成功を偽装せずrootへ根拠を返す。候補2は別非作者レビュー後rootがactual採否し、pin/registry/共有SQL/運用DBへ作者は書かない。

歴史初球bootstrap exact2の採用（2026-11-06 JST、PO委任Codex /root判断）: 作者packetac8c37bb7f197f172bb2ec7bc3ab3294bea757b32b8b904a38e2e38bcd60e0dbを非作者3a0c624dd055d3fc65ecc85c53ea78f3fefc1ef331dc55a10d73e452843e5afb/checksc84dad71834e991ca08613478406c8c3b3e6ceb07ed4c30eb2dc188b50c4ee92で限定採用する。新74＋旧263の337成功14秒、追加13成功/RuffTy0、旧12宣言はprivateデータhelper2の機械inlineで全AST一致・旧import/constant/他3904blob保持を独立確認。旧firstballとv3のT2型差は同実hostの既roster/旧firstball/新nonplay数学3callで解消し、Pythonで新T2を捏造しない。歴史初球D2=1024を1へ付替えず、真正startと実貸与で証明した歴史beforeだけを局所の数学proposal(d3zero/active空)へ包み、currentDB水位や保存CP/資格とは区別する。旧V8/history/FP原値/全41列の照合と各call前後のlive確認を保持。D2=0は既Source6の明示負例のため本private数学profileでは不可用、旧publicの非負値受理は変えないという限定留保を残す。native allocator1024の最初の実経路を提供する単位であり、全歴史D2/全訂正状態の完成ではない。Source17のlegacy-v3互換gate欠落P1・正式pin/D11・実actor/SQL登録/S/genCP/GET/PGは別の未成立として残す。rootは2全SHA確認後actual反映し同新版で検査する。


legacy-v3資格P1の限定是正採用（2026-11-06 JST、PO委任Codex /root判断）: 作者packeta29590562d25c1d3a940a20e3bc4963962a191b3735d5c128a4360d9e5368bd3を非作者1f509ac2d440347537ca39fe63403399e6c958d896fe1eba830c5fccdba4d824/checks665233e99b1b82b8f6740ef0373390a0d189e2d5c41f7fb222f5c7558ac27555でexact2採用する。初回Source17の未検出P1履歴と既修復を保持し、旧v3原本をcurrentへ投影する直前に実shared有限互換gateを必須呼出する。同currentを含むv3は未宣言の現段階では不可用であり、常時拒否をlegacy提供完成としない。current pure rigだけ実artifact自己pinと独立正規CPdigestへ追随し、原契約・数学・履歴・rawFPを保持する。非作者126成功と旧受理2→新拒否2を確認、実PG/Port/HTTPの成功ではない。正式v3有限宣言・witness・pin/D11・actor/GET/S/次球接続を後続で成立させる。新PO意味判断待ちや全操作待ちを追加しない。


legacy-v3有限提供のroot限定追補（2026-11-06 JST、PO委任Codex /root）: gate欠落是正e8902b55を実採用しruntime7module126成功6.84秒。未宣言v3の閉拒否を提供完成とせず、cache-only作者pr192にexact5を許可する。backend/src/pitchlog/repositories/play_prefix.py、backend/tests/test_play_prefix.py、contracts/state-transition/play_prefix_v2_source_compatibility_v1.json、新contracts/state-transition/nonplay_v3_compatibility_witness_v1.json、backend/tests/test_nonplay_prefix.py。旧2形式のruntime判定を保持し、旧57行/全旧witnessをbyte保持する。v3だけderiveLineupPlayPrefixWithContinuationのexact1operationと旧51d→現4e/現4e自己の有限2pairを宣言、fixed witnessの実bytes/SHA/metadata/pairを実行時照合する。53規範（lineup34＋batted19）の旧新実VM全応答と許可metadata正規化を独立固定する。未知hash/形式/operations/witness改変は不可用、自己SHAだけのshortcutは作らない。旧57/51d全assertは真正historical3ecc85abのGit文脈で原条件保持、新currentの正常成立を先に確認した後に欠落/改変負例を検査する。旧負例が現基線では常に失敗する状態を検査成功へ読み替えない。非作者レビュー後rootが正式assetを書き、実PG/全操作互換/P6blindへ本有限提供を拡張しない。1878は旧4f→4eの別4operation根拠だけでv3/全13の証明にはしない。


共有同期核の取消接合scope（2026-11-06 JST、PO委任Codex /root）: 既ROOT-CALL dd8f8de3のroot接合を独立cache作者undo_unit1_whole_independentへ単位委任する。本deltaで作者となるため非作者レビューは別主体へ渡す。exact6はbackend/src/pitchlog/sync/{apply,prefix_path,native_ledger_insert}.pyと新backend/tests/{test_undo_e1_kernel,test_undo_prefix_kernel,test_undo_native_ledger_kernel}.py。actual writerはroot、キャッシュ外書込みなし。実E1 qualification/一回frame/内容tuple/予約event ID/同TX投影/投影完了確認を既P1とnative7Aへ接合し、保存済みD5再掲にはfresh資格を前倒ししない。旧認可/連番/再送/内容順とrollbackを保持する。ownD4とtargetD4を等置せず真のtarget.generationとV10を一致させ、真正source/先頭/世代連結は既readerで検証する。取消へfake D2/play/StatsStateを生成せず、S invalidationは別明示hookとする。一般Port登録/SQL/HTTP公開/正式assetは他deltaに分け、供給がなければ成功へ補わない。元fixture/旧test期待を緩めず、同実既kernelの呼出順とdoubleによる限定検査を明示する。実PG/真正記録権成功の証拠は後続同版owned試験とする。


current pin16の限定採用（2026-11-06 JST、PO委任Codex /root判断）: 作者packet527e68bee6fb1835b3ab4232962633b65e57030df36869e50c0aa463c4ff7e86を非作者ceaf0fa5c190430779ec08139a511cdaf696c1d79d61a6258eeaa2bd6bc62b3f/checks18f5dd2d9364bf45e3e48de0ba6092db284ffcdc8818ae940a03b108434d446eによりexact16採用する。既recipeと同一current849pointer＋公式echo/hash392=1241葉だけ、公式producer143を独立再計算して全16JSON/描画bytes一致、raw86の同長stringtoken以外全字句/priorFP415/他3890blobを保持した。旧v3host44＋F1raw拒否22を独立成功、作者関連674成功。rootは全16前後SHAと唯一artifact4e8b3252…95274byte不変を照合して反映する。chain9は旧親4参照/行を原値のまま保持し、freshchainへの再連結は別未採用提案。数学期待を製品出力から生成しておらず、既旧数学へ戻した後値との全等価を確認。新undo/nonplayの正式D11・有限legacywitness・actor/PG/画面は本機械pin追随では成立しない。


nonplay固定関数の実登録scope（2026-11-06 JST、PO委任Codex /root判断）: 既ROOT-CALLの閉6関数を実transactionへ接合するcache-only作者にstats_bf_independentを割当て、このdeltaの非作者レビューは別主体へ渡す。exact8は新backend/src/pitchlog/repositories/{nonplay_function_operations,nonplay_qualification}.py、既同{function_operations,operation_registry,transaction}.py、新backend/tests/{test_nonplay_function_operations,test_nonplay_qualification,test_nonplay_dispatch}.py。固定SQL6はauthz.nonplay_prefix_sqlの実rendererと完全一致するschema/引数/型/行数/decoderだけを許可し、旧全familyへ一般許可を広げない。私有4は真正_qualified_nonplay_callをSQL前に一回消費し、任意caller関数名/SQL/資格boolを受けない。rights2は同scopeの_undo_qualification_activeと実leaseへ束縛し、既device/rights順・RG1・失効・判定中write拒否を維持する。ValidateUndoToken/ProjectUndoTokenの実type/contextにだけ既content tuple/同TXprojection hookを接合、未登録SQL/権限/manifest/PGを成功へ補完しない。native ledger/共有P1 source3は別作者、数学/Source17/有限compat/pin/正式assetsは対象外。rootがactual writerと正式catalog/grants/manifest再導出を担い、登録metadata成功を実Port/PG成功としない。


共有核接合の不可分資格追補（同日、PO委任Codex /root）: kernel作者の反例により、実E1/device family選択で先にV7.formatVersionを要求すると、既D5異内容のDI3分類より先にUnavailableとなる不備を確認した。既exact6へbackend/src/pitchlog/sync/undo_execution.pyとbackend/tests/test_undo_execution.pyのexact2を追加許可する。_undo_qualification_scopeの実source/handle/TX/lease/lifetime/V5=undo検証は保持し、V7 Mapping/format2節だけをfreshの既read_undo_event検査へ委ねる。保存済みD5のdevice/authを維持して再掲/異内容結果を返し、未使用D5の不正V7は既fresh内容検査で拒否する。host/target/新leaseをstoredへ前倒ししない。既拒否優先を変える意味判断ではなく既DI3維持の技術是正として、旧scope全対向保持とstored不正format/fresh不正formatの順序を別非作者へ渡す。
