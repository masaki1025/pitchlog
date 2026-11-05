---
feature: mvp-undo-native-connection
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-05、原案SHA 03a8bf7ee9fd835ae3d2502358ba23ba8e11fbfcbfb93606a237f1e16528aac2、非作者敵対7221cc2bc5f0f1891a4bed6aecd7651fdc49d5c4c09e085eddfb815a956977ce）
重さ分類: コア領域
branch: feature/mvp-undo-native-connection
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
