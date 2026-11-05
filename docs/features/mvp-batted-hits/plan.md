---
feature: mvp-batted-hits
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-05T00:56:04+09:00、対象SHA 32f33ba0ee64f6a0d1ca82b934bfd69eed98680e4de5bfa27f67b221deae9330）
重さ分類: コア領域
branch: feature/mvp-batted-hits
created: 2026-11-05
計画レビュー周回: 1
確定ゲート周回: 0
---

# 無走者の単打・二塁打・三塁打・本塁打

## 目的・基点

[TSK544 T1](../tsk544-t1-state-calculation/plan.md)、[三振](../mvp-strikeout-pitches/plan.md)、[BB/HBP](../mvp-terminal-pitches/plan.md)の次の操作単位。全体計画/旧レビュー/未達ゲートを作り直さない。専用WT feature-mvp-batted-hitsは固定候補702948fc8d26f7d4319e48eb5d0188176ec9d3c0から作成した候補枝で、正式develop起点・正式受理済みとは扱わない。元#192WTとdirtyを変更しない。

走者なしの4安打を、実際の打球観測から唯一T1核・T2・履歴・既同期の同TX保存・GET・実画面reloadまで接続する。数学だけで完成としない。在塁打球・失策併発・進塁/アウト併発・妨害・交代・取消/訂正等を全MVPから除外せず、この単位の成功入力にはしない。

## 意味・観測の閉範囲

規範は要件FR-003/004/005/020、付録E-1/E-2の4結果、付録A-1の23flags、RBI-06、D07の限定行。D07は二死二三塁の単打だけであり、今回の無走者へ自動進塁観測を輸入しない。spike41d7175d/b2ed1905は再利用候補であって規範ではない。

| 対象 | 初回の閉条件・出力 |
| --- | --- |
| 入力状態 | runners=empty、outs0..2、S0..2/B0..3、top/bottom、正のinning、打順1..9、両side cursor各1..9かつactiveとbefore打順一致、未終了、初回は非TB。score/boardの対応得点は一致し非負bigint |
| 入力観測 | eventKind=batting-result、pitchEventKind=pitch-event、結果はsingle/double/triple/home-runの4IDだけ。公式記録no-error・妨害裁定not-required・走塁上書き/付随アウトなしは利用者の確定観測として渡す。欠落/未確認を既定値で埋めない |
| 打球情報 | 座標/種類/強さ/捕球選手/球種等は保存境界の既schemaの必須性/null許容と利用者入力に従う。数学が不要な値を捏造せず、その欠落を結果IDから推定しない。座標変換/捕球選手推定は既共有実装へ委譲する |
| 単打/二塁打/三塁打 | batterDestination=reachのbase1/2/3、after runner=first/second/third。得点/RBI0、hits+1、count reset、PA終了、旧攻撃側cursorだけ次打順へ。outs/half/inning不変 |
| 本塁打 | batterDestination=score、after empty、攻撃側のscore/board得点+1、RBI1、hits+1。count/PA/cursor/out/half処理は同じ。得点側はbefore.halfで決まり、side交換を行わない |
| 23flags | 非HRは投球数/被安打/打席/打数/安打/塁打の6true・17false。HRは被本塁打/本塁打/失点/得点/打点もtrue（11true・12false）。塁打flagを数値へ変えず、数値1/2/3/4の唯一供給はresult IDからの正式成績primitive側が所有 |
| 走者/履歴 | before3塁ともnot-applicable/null。単打等の打者到達と既走者のdefault advanceを混同しない。history全count before/after、after全state/board/両cursorを返し、入力/旧historyを書き換えない |
| 拒否 | 在塁、非pitch-event、未知result、未確認/欠落/矛盾観測、失策/妨害/併発走塁、終了/TB、cursor不整合、負値/範囲外/score不一致を閉拒否。三振/BB等へfallbackしない |

T2は真正before/after/有効得点と本塁打事実を既終了規範へ渡す。halfCompleted=false/outsUnchanged=trueだけからno-endを決めない。サヨナラ/コールド/最終回/延長/TBを未評価のまま受理しない。終了検知lockと正式終了宣言を分ける。初回TB拒否は未提供状態を明示し、既MVP要件を縮小しない。

## 単一計算と再利用

現state.tsのapplyCountRuleがcount reset/打順/両cursor/履歴/boardの共通核。これを新moduleへコピーしない。新battedHit.tsは4結果の閉rule・観測型/適格性だけを持ち、state.tsに入口deriveBattedHitと共通核の最小hit/HR効果を追加する。既ordinary/BB/HBP/Kの全挙動は維持。spikeのbase別出塁、hit/HR flags、得点/RBIの前進式を選別再利用し、包括的STATE_RULESや未観測進塁の仮確定は輸入しない。共有API/artifact/保存/UIに同じ算術を書かない。

## 有限ステップと編集所有

| ステップ | 内容 | 採否・成立条件 |
| --- | --- | --- |
| 1 | 4安打の実前進計算を完成。新frontend/src/domain/battedHit.ts・battedHit.spec.ts、既frontend/src/domain/state.tsのexact3 | root計画採用後に開始。全before/after/23flags/history/board/両cursor/拒否、独立手例と交差、既ordinary/BB/HBP/K回帰、重複0を固定して停止 |
| 2 | 閉JSON ABI/唯一artifact/固定Python caller・独立操作契約 | 下記共有path候補をrootが直列採否。型/十進数/全出力/旧ABI拒否不変、実hostを使った全入力出力比較と独立期待。数学の複製なし |
| 3 | prefix/T2/真正source・入力観測/責任帰属/物理投影を接合 | 契約/観測fieldの完全性・保存payloadの唯一producerをrootが確定。T2未評価成功禁止、旧variant/再送識別/真正artifact証拠保持 |
| 4 | 同TX保存/GET/再送/原子性/越境 | rootとownedPG時間調整。event/PlayRow/PlayRunner/history/checkpoint/ledger/両cursor・責任投手を不可分保存。単打等のafter checkpointは打者到達塁へ1runner、HRはempty。物理PlayRunnerは既方式どおりbefore各塁（本単位の初期無走者では0行）で、次球のbeforeで新走者を記録する。元D5再送/ACK喪失/故障rollback/別tenant拒否と実GET完全値 |
| 5 | 実画面の打球入力→保存→復元と最終統合 | 4結果を各新規試合で実入力しbefore/after/得点/安打/次打順・reloadを照合。HTTPS/実app/認証/実DB/実artifact。最終正式値/CLI/CI/非作者確認はrootが所有 |

**初回writerは専用WTのexact3だけ**。共有state.tsの小差分はrootから計画採用後の担当許可を受けて行う。各ステップで止まり、次段のexact scope採用を受ける。新moduleの純計算成功を保存/画面成功へ読み替えない。

ステップ2以降の共有候補はrootのみが直列採否・正式writerを決める: frontend/src/domain/publicApi.ts、frontend/src/domain/playPrefixContinuation.ts、backend/src/pitchlog/domainrt/batted_hit.py（新）、backend/tests/test_batted_hit.py（新）、contracts/state-transition/batted_hit_v1.d.ts・batted_hit_schema_v1.json・batted_hit_cases_v1.json（新3）、既state_transition_contract_v1.json/input_axes_descriptor_v1.json/branch_row_mapping_v1.jsonと必要な一意artifact/manifest。source/payload/SQL/UIの候補は既ordinary_pitch_execution.py、terminal_pitch_payload.py、terminal_pitch_projection.py、terminal_pitch_write_stamp.py、started_games.py、frontend GameScreenOrdinaryPitchProvider.ts/Controller.ts/OrdinaryPitch.vue。この列挙自体では編集許可しない。正確な差分を前段成果から閉じて提示し、rootが同期保存/認可/SQL登録と一緒に受理する。共有台帳/正式assets/refsを作者が更新しない。

## 検証と停止点

手例は4結果×両half×打順境界1/9を中心に全応答を独立に固定。O0..2/S0..2/B0..3/両half/active9/inactive9/4結果の23,328交差、2^53超の得点/inning/hits、counterfactualな在塁・観測欠落/矛盾・未知ID・cursor/board不整合を確認する。期待を実装出力から生成しない。正式契約の無走者single/double/triple各代表とHRのRBI-06規範を根拠にし、既正式HR代表が満塁であることを無走者手例の正式登録済みと偽らない。追加契約/正式値は次段rootの採否で追随する。

frontend Vitestと型/lint、既計算全回帰を範囲相応に実行し、packetへ候補全SHA/差分/旧結果保持/未検証を固定。両共有DSNはunset、SSDtmpだけを使う。DBは事前時間調整した自己所有PGだけ。元署名/期待値の緩和/仮成功/無制限許可なし。本人署名/P6blind/全NFR完成を主張しない。基点の未統合#191/#192候補との正式接合はrootが保持する。

## ステップ2の閉ABI・唯一artifact・型caller追補候補（2026-11-05）

ステップ1 cdcc7ec3は非作者REPORT1d2c154500a0a6c3939c5a0793b2f101f4a9f31d8b42f2b54157cd3db75c4e96の独立72/23,328交差・正式23flags・重複0確認を根拠にrootがPO委任採用。次の追補は**PO委任による主担当/root採用済み**（2026-11-05、対象SHA03032d44…）。新全体計画/数学の作り直しを行わず、既新module/state核を公開境界へ接続する。基点由来38failのSourcePosition/実行pin修復はrootの別#192成果であり、この単位へ混ぜない。

### exactpath・所有

実装候補exact7（作者はroot採否後に担当）:

1. frontend/src/domain/publicApi.ts — 新deriveBattedHit操作。既evaluatePitchの閉before/history/codec/derivedJsonを再利用する有限variant。旧入口のkey/型/成功/拒否は不変。
2. frontend/src/domain/publicApi.spec.ts — 旧11操作の順序/全値を保ち、新1操作だけを登録するexact-set追随。
3. frontend/src/domain/battedHitAbi.spec.ts（新）— 独立契約全応答をsource/Node VM/ブラウザ同一artifactへ渡す比較、旧ABI不変、型/重複/閉拒否。
4. frontend/public/domain/pitchlog-domain.js — 既build.mjsが生成する唯一IIFE。手編集/別打球artifact禁止。
5. frontend/public/domain/pitchlog-domain.json — 同builder生成の唯一artifact宣言、実byte/SHA/再現一致。
6. backend/src/pitchlog/domainrt/batted_hit.py（新）— 不変Pydantic DTO・厳密decode・evaluate_batted_hit。既open_domain_hostの固定製品pathとhost.call('deriveBattedHit', JSON)を一回だけ使用する。別計算/expected lookup/任意artifact path/API設定を公開しない。
7. backend/tests/domainrt/test_batted_hit.py（新）— 正式候補の全応答/交差/型/読取専用/実host到達・一回call・未知/壊れた応答拒否。実成功を固定戻り値に差し替えない。

閉操作契約候補exact3は**rootが直列採否・正式ゲート/編集所有を決める**:

- contracts/state-transition/batted_hit_v1.d.ts
- contracts/state-transition/batted_hit_schema_v1.json
- contracts/state-transition/batted_hit_cases_v1.json

この3契約は現実装/実host/生成artifact出力から期待を採取して作らない。要件E-1/E-2・RBI-06と既schema/型の十進数/履歴表現を再利用し、独立16手例の全expectedと負例を先に固定する。d.ts/schemaは閉キー・必須/optional・unknown拒否の同じ形を持たせる。必要な7.7受理・既state_transition_contract/descriptor/branch-map/required-setの正式登録はrootが基準/手順を確認して所有する。新3fileを置いただけで正式発効/全NFR成立とはしない。

既state.ts/battedHit.ts/battedHit.spec.ts、host.py、既contract/schema、builder/checkerをこの候補では変更しない。追加が不可分なら先に根拠/exactpathをrootへ返す。

### 要求JSONと応答JSON

新操作名は `PitchlogDomain.deriveBattedHit(requestJson: string): string`。数学入力はstep1のものだけ。全整数は正準十進**文字列**、JS Number/浮動小数/指数/先頭0/+符号/-0を受理しない。既parseDecimalInteger/formatDecimalInteger・readState/readBoard/orderJson/derivedJson/validateHistoryEntryを共有する。

要求のトップキーは次の9個だけで、全必須:

```json
{
  "eventKind": "batting-result",
  "resultId": "batting-result.single",
  "pitchEventKind": "pitch-event",
  "officialScoringPayload": "no-error",
  "interferenceRuling": "not-required",
  "runnerAdvanceOverrides": "not-applied",
  "thirdOutObservation": "none",
  "before": {
    "stateFields": {
      "state.half": "top", "state.count.strikes": "2", "state.count.balls": "3",
      "state.outs": "2", "state.runners": "empty", "state.battingOrder": "9",
      "state.tiebreakActive": false, "state.gameEnded": false, "state.inning": "7",
      "state.score": {"home": "3", "away": "5"}
    },
    "scoreboard": {
      "inningScores": {"home": "3", "away": "5"}, "hits": "12", "errors": "2",
      "strikeouts": "4", "walks": "3"
    },
    "battingOrderBySide": {"away": "9", "home": "6"}
  },
  "history": {"stack": []}
}
```

4観測タグはstep1の**確定済み有限観測**の写しで、完全なFR-004公式記録payloadや保存sourceを代替する型ではない。producerが事実を確認しないままno-error等を補完してはならない。完全payload/原本との照合はstep3が所有し、任意タグを送れば保存できるAPIをこの段階で増やさない。

resultIdだけ4安打へ閉じ、before/historyは旧codecの表現を保持。stackは必須・有限配列、過去entryは既差分外形を全field検査し、後方tailを全値保持。両cursorは必須でactiveとbeforeの一致を唯一核で検査する。DTOが数学を再計算せず型/形だけを保証し、型の正しい範囲外は実artifactの非成功へ渡す。

成功は `{"ok":true,"value":{...}}`、valueのexact8キーはcountEffect/plateAppearanceEnded/batterDestination/runnerDefaultAdvance/outEffect/statFlags/after/historyContextとする。countEffectは両方`{"kind":"reset"}`でvalue数値を残さない。打者destinationはreach/base"1".."3"またはscore（baseなし）。runnerDefaultAdvance3塁はnot-applicable/null、outEffectはcount"0"/targets[]、flagsは全23boolean、afterはstateFields/scoreboard/battingOrderBySideのexact3。afterでcount0・active cursorだけ次打順、HRはbefore攻撃側得点+1、hits+1を返す。

historyContextは新entryを先頭に一つ追加し旧stackの全entry/順序を保持する。entryは既`{kind:"confirmed-play",difference}`を使い、differenceはstateFields/scoreboard/statFlagsと任意のbattingOrderBySideを持つ。変化した値だけbefore/afterを記載し、変化しないcount/cursorをnullや同値pairで補完しない。HR得点・hits・塁・打順・countを既derivedJsonの比較で出力し、APIで差分を別再計算しない。数値RBI/塁打やT2/保存/成功ACKを新fieldとして足さない。

失敗は既exact `{"ok":false,"error":{"code":...}}` の4語彙だけ。壊れたJSON/重複key=INVALID_JSON、必須/未知key/構造/Number/boolean不正=INVALID_REQUEST、非正準/負の整数文字列=INVALID_DECIMAL_INTEGER、型の正しい在塁/TB/終了/観測矛盾/結果範囲外/cursor不一致=UNSUPPORTED_T1_SCOPE。既入口の分類を動かさず新variantだけへ適用する。

### 独立比較・実host・旧保持

契約16全expectedを先に固定してから実装し、source/Node VM/ブラウザartifact/固定Python hostの全応答を比較する。O/S/B/両half/独立cursorの23,328交差は既手例の規範効果・独立NEXT表から展開し、生成物をoracleにしない。huge integers・空/非空history・入力不変・閉拒否を比較。型decoderは余剰/欠落/重複/非有限/型変換/省略差分→null補完を拒否する。応答4結果のshape/6または11true/after runner/count/out型を完全に検査し、壊れた応答を成功へしない。

実評価はopen_domain_hostを使う正常ケースでactual artifactへ到達し要求operation/JSONとcall回数1を確認する。故障注入はその実callへ先に委譲した後で応答を試験内だけ改変する。製品hostには例外逃がし・固定成功・二重計算を入れない。旧ordinary/BB/HBP/Kと旧host/runtime対向を同artifactで再実行し、root別修復中の38caseは基点既失敗として対応集合を保存する。builderの同source再buildでartifact全byte/SHA一致を検査する。新公開口だけを除いた旧operation集合・順序を完全保持する。

### root専有D-11/sharedmanifestへの要求（作者編集なし）

新計算ID候補`batted-hit-empty-v1`を、唯一source（state.ts共通核+battedHit.tsの静的依存）・単一IIFE・公開deriveBattedHit・Python固定caller・root採用契約の全期待へ束縛する。新backend/domain/batted-hit-manifest.jsonとproperty-catalog/schemaが必要ならroot所有で作成/採否し、既manifest/check-sets/required-cases・入力descriptor/branch-map・core/tenant/frozen登録への影響はrootが有限scopeに閉じる。元全計算・旧契約ID/期待/署名/履歴を保持する。public-source、artifact、Python呼出し、正負vectors、差分検出、未知caller/任意artifact拒否の各役割をD-11の該当層へ登録する。step2局所比較をD-11/7.7全体成立に読み替えない。

### ステップ2の編集指示（2026-11-05）

主担当rootが追補SHA03032d44af9282a9c010712bd203fbc1d6a4845cbfeb01499013edf8b83d5359をstep1非作者確認済みの数学/16手例・既codecへ照合し、要求exact9/応答exact8/4拒否の閉ABIをPO委任採用する。作者pr192_resume_auditへ専用WT内exact7の編集を許可。新閉契約3fileは作者がcache候補を先に固定しrootへ渡し、rootが直列照合・適用する。既正式契約/旧期待/descriptor/共有manifestは作者編集不可。候補契約の規範からの全値を先に固定してから公開ABIを書き、実出力採取で期待を埋めない。API/source/実hostを結んだ後、コードと閉契約一単位の非作者レビューで採否する。新タグを保存APIの認可/原本証明として流用しない。正式D11/7.7・保存・画面は後続。

公開集合の既試験追随（2026-11-05、PO委任による主担当root判断）: 唯一artifactの新deriveBattedHit公開により旧exact11期待の3試験が停止した。frontend/src/domain/{firstPitchContinuationArtifact.spec.ts,ordinaryPitchContinuationArtifact.spec.ts,strikeoutPitchArtifact.spec.ts}を作者へ追加許可する。旧11名/順序のliteral期待を全保持して新1名だけを明示追加し、実artifactから期待集合を生成しない。旧ABI/全応答・拒否条件は不変更。基点38失敗とは別の後発3件として根拠と全前後を固定し非作者へ渡す。

### 三振の保存成立候補へ追随する（2026-11-05）

公開ABI13pathは非作者8886e822…の全SHA/実host23,328交差/型・故障対向を根拠に11b3acd2へ保存した。正式D11/現在pin接合とstep3 source/T2は残る。重複配線を避けるためrootが三振候補97d39c5（実DB成功3caを含み、正式191/eb8履歴へ追随）を本枝へ取り込み、既v3の参加者/両cursor/責任/一回frame/保存境界を再利用する。三振の実画面sourceは別WTで実装中で、この追随には未commit GUIを含めない。source/既数学値が同じことを照合し、配布物は唯一builderで再確認、実行pinと既wire自己echoだけを正式規則からrootが後続追随する。候補の数学成功を打球保存/画面の成功にしない。

D11の最小正式登録（2026-11-05、PO委任による主担当root判断）: root所有で新backend/domain/batted-hit-manifest.json・batted-hit-property-catalog.json・batted-hit-property-catalog.schema.json、contracts/state-transition/batted_hit_d11_vectors_v1.json、backend/tests/domainrt/test_batted_hit_d11.pyのexact5を作成する。計算ID batted-hit-empty-v1、唯一state.ts/battedHit.ts依存・公開deriveBattedHit・固定evaluate_batted_hit・実単一IIFEへ、先行採用16の全request/expectedを包絡する。既manifest schema/collectorと同じ実factory/direct比較traceを用い、期待を実装出力から作らない。現artifact07554…の新旧34+56応答と既互換40保持/新15組は別cacheで実証して同時に現在pin13へ追随する。mutation profileは必要対象を宣言し、未計測を成功にしない。新equivalenceの測定だけで全D11/BOOT/正式7.7/実保存を完成扱いしない。最終差分は別非作者へ渡す。


## ステップ3のv3接合指示（2026-11-05、PO委任によるCodex /root判断）

基点b52547ac、step2の新D11/pin19は非作者0a8cdfa9…の全SHA/旧90数学/互換13,170全応答を照合し採用保存済み。未実mutation/全D11/BOOT/保存/UIは残す。次は既v3に無走者4安打を閉variantとして接続する。旧exact4のT1入力を全保持し、新batted-hit exact8（既4入力+既採用4確定観測タグ）だけを追加、未知/未確認/在塁等は拒否する。新v4/別artifact/重複算式は作らない。

作者batted_prefix_connectionのexact9 source: frontend/src/domain/lineupPlayPrefixContinuation.ts、publicApi.ts、新battedHitPrefixContinuation.spec.ts、backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py、lineup_prefix_source.py、新backend/tests/domainrt/test_batted_hit_prefix.py、既test_lineup_prefix_source.py、backend/src/pitchlog/sync/terminal_pitch_payload.py、新backend/tests/test_batted_hit_prefix_payload.py。唯一builderのfrontend/public/domain/pitchlog-domain.js/.jsonの再生成2を加え計11。rootはこの11を並行編集しない。

公開deriveLineupPlayPrefixWithContinuationから既唯一evaluatePitchのbattedHit入口へ委譲し、T2は既終了核へ。到達baseは実T1 batterDestinationから取り、double/tripleをbase1に固定しない。HRは既確定score/RBI事実と保存観測を比較、サヨナラ/コールド等を未評価noendへしない。旧FirstBallObservations variantを保持し、新打球だけ明示観測/打球情報/result IDとT1を全比較。利用者観測を4タグから推測/生成しない。

契約schema/d.ts/新cases候補は作者が承認済batted規範と既v3からcacheへ先置き（runtime生成期待不可）、rootが実path/SHAを照合して直列反映する。新意味を増やさない型接合をroot委任で具体化し、不足があれば閉拒否・対象外理由を記録する。共有pin/manifest/正式受理/DB/UIはroot後続。非作者の全応答/旧回帰/入力欠測拒否/元source確認を必要とし、step3候補を保存成功やMVP完成へ昇格しない。

ステップ3の既決D01=B整合追補: decision-sheet（2026-10-29採用記録、主担当台帳の現記録）により9回裏サヨナラ/コールド同時成立はwalk-offで既決。既endConditionCore.tsにcold先行が残るため、作者scopeへ同fileとendConditionCore.spec.tsのexact2を追加する（計13）。新規裁定ではなく既採用方針への最小修復。単独walk-off/単独cold/同時の3対向を規範から先置きし、E08の通常終了対cold、表完了のx-mark、OUT3有効得点先行、非本塁打余剰得点切捨て、正式終了を自動成立させない条件を保持。境界.completedHalf=top等の既通常終了を単なるafter.half=bottomでwalk-offへ誤変換しない。契約/coverage差分が不可分なら先にrootへ列挙し正式資産を勝手に書かない。新artifactに意味差が生じる1競合は互換全同値扱いせず適用範囲/既決根拠と新旧差を明記し、独立確認を要する。

ステップ3の不可分root正式資産追随: payload math定義と新full観測の連動に必要なcontracts/state-transition/lineup_play_prefix_payload_schema_v1.jsonと同payload_v1.d.tsをroot所有candidateで採否する。旧観測5/旧34全値を保持し、新12観測と新T1/resultをschema/型の両方で閉相関させる。初回型/schema直積P1は独立反例を保全して反映周を重ねる。唯一artifact51d4d0f…60923bytesへの既execution pin/正準自己echoはroot cache batted-prefix-shared-pins-20261105/files.jsonのexact16（旧13+新battedmanifest/D11包絡/prefix19）で明示849fieldだけ追随する。旧34/56と新19の数学/終了/履歴/選手/責任/positions期待を変えない。D01競合の新旧実行差は適用根拠を別記し、全旧入力互換を仮定しない。compat追加/正式7.7/全D11/DB/UI成立とは分離する。

ステップ4の走者保存表現の明確化（2026-11-05、PO委任Codex /root判断）: 既正式191のrunner_physical_rowsはbefore各塁のhold結果を保存し、after占有はcheckpoint/sourceへ別保存する。data-model5-2の(プレイ,塁)行・進塁状況・責任投手と整合する既方式を維持し、上表の1runnerはafter checkpointを指すと明記した。打者到達塁/責任投手を欠落させたり物理before表へafter行を混入させない。初期無走者安打の物理0/after1、次通常球の物理before1/after継続1と帰属投手、HRのafter emptyを同版実DB/GETで検証し、既BB/HBP/三振の保存結果は不変とする。新意味の裁定やMVP機能削減ではない。


## ステップ4の同TX保存指示（2026-11-05、PO委任Codex /root判断）

step3source13はf93c46c1、非作者6c964c35…を根拠に採用済み、DB成功にはしない。作者batted_prefix_connectionへexact5を委任する: backend/src/pitchlog/sync/ordinary_pitch_physical.py、backend/src/pitchlog/authz/terminal_pitch_write_stamp.py、新backend/tests/test_batted_hit_physical.py、新backend/tests/test_batted_hit_storage_boundaries.py、新backend/tests/db/test_batted_hit_storage.py。rootはこの5を並行編集しない。既v3/frame/Port/token/署名/HTTP/reader/41列mapperを再利用し、余分な新公開operation/CAP/table/app grantを作らない。

新full観測のbatted6列を既物理列へ保存し、event_kindは既正本/DB制約どおりpitchを維持、数学eventKindのbatting-resultと混同しない。hitX/Yは既保存の正規化0..1と正準十進/Doubleの形式変換だけ（非有限/範囲外拒否）、既採用codecがあれば再利用し、計算/座標推定をPythonへ複製しない。新NFR-018例外が不可分なら既検出を緩めずexact追加根拠をrootへ返す。

既署名prepare_play_prefix_projection本文1の新安打branchだけで元V7/V8/全41値/4結果/12観測/真正守備側fielding参加者・語彙category/disabledを同TXで比較する。DH/相手/別tenant野手や無効語彙を拒否し、既成功/全取消/記録権/元D5/水位/履歴/責任/reader再計算を保持。SQL資産はcache候補としてrootへ返す（本文1、FnOwner限定7列SELECT、既FORCE RLSを維持するSELECT policy2）。rootが有限ACL/生成モジュール/正式入力を直列採否する。推測nullable/結果からの観測補完/固定資格は禁止。

owned PGはrootと調整し、実ASGI新規POST作成/開始→4結果各安打→可能な次通常球→GET/再取得/元D5再送/途中故障全取消/越境/語彙/野手拒否を実測する。物理before0→次球before1とafter checkpointの到達塁/責任投手、HR得点/RBI/empty/終了検知lockを区別して検査。端末実画面/正式統合/1試合/MVP全体をこのAPI候補の成功へ拡張しない。

ステップ4の正式producer最小追補（PO委任root判断）: 新SQLのFnOwner限定7列/SELECT policy2はcache宣言だけでなく既canonical producerの閉集合へ登録する必要がある。rootがbackend/src/pitchlog/authz/terminal_pitch_product.pyと新backend/tests/test_batted_hit_product_declarations.pyのexact2をpr191_residual_independentへ委任し、batted_prefix_connectionのsource5と分離する。candidate_declarationsへ採用f44e31cd…と完全同値の9宣言/9bodyだけを追加し、旧全宣言/関数8bodyを保持する（prepare1のSQL変更は別author source既採用）。契約/checkerの未知/余剰/誤role/privilege拒否を一般緩和せず、first_ball_productの既_activate_ordinary_profileで同じBODIESへ生成する。正式DDL/body manifest/runtimeはrootがこのproducerと公式derive/renderから直列再導出し、手で生成Pythonを書かない。新CAP/関数署名/table/app grantなし。

正式producerの不可分回帰追随: 既backend/tests/test_terminal_pitch_product.pyは旧policy4/column19・非runner2表をexact固定するため、pr191_residual_independentへこの1pathを追加（producer委任exact3）。旧全19列/4policyの全値とapp直接runner権限なしを保持し、新7列/2policyだけをexact追加した6/26と新参照表2を検査する。旧拒否/期待の削除・partial一致による緩和をしない。


### ステップ4の実保存境界追補（2026-11-05、PO委任Codex /root判断）

owned PG r2/HEAD c74e00c7は対象game作成/開始後、最初の安打投影でrepositories/ordinary_pitch_operations.py::_rowの旧first-ball全nullable常時None条件によりOrdinaryPlayRowErrorを返した。実安打6観測を保存へ渡す契約と実SQLは既採用済みであり、新しい意味判断ではない。exact2をbackend/src/pitchlog/repositories/ordinary_pitch_operations.pyと新backend/tests/test_batted_hit_play_row_operations.pyへ追加し、PlayPrefixPlayRowInsertTokenかつ既閉4安打の原観測6列だけを許容する。旧Ordinary token/旧投球は既NULL条件を全保持、全41列実型/UUID/finite/範囲/既原本・ledger・nonce・同frame照合は保持する。未知結果/他nullable/負値・範囲外/不正tokenを拒否する対向を付ける。作者はこのexact2だけ、SQL/正式資産/台帳はroot所有。非作者確認後に保存し同owned PGを再検証する。r2の第2fixture authority起動45秒timeoutは別の環境失敗であり成功へ読替えず製品timeoutを緩めない。


### ステップ4採用と画面基線の接合（2026-11-05、PO委任Codex /root判断）

同86f720b9のowned PG r4は2pass357.59秒、実新規作成4安打＋次球/再送/GET・再取得/途中T2T4全取消と6拒否（全0/水位0）を最終世代照合まで確認。runtime22全SHA/HEAD不変・owner除去をcache db-r4-diagnostic.json（700d2e47…f3c37f）へ固定し本保存単位を採用。画面/正式7.7/全MVPの受入ではない。rootは#192実画面候補37e29859を通常mergeして既v3入力画面/queue/ACK/復元/認証を再利用する。merge-treeで競合0を確認、既batted唯一artifact/数学/実保存source/producerを保持し、sourceの後発差分だけを検証する。#192の最終GUI再現性block/positive fixture/全CI未了を引き継ぎ、正式統合済みとは扱わない。次担当はstep5の最小UI閉型/原観測入力/既provider接合のexact scopeを提示し、root指定後その範囲だけ実装する。共有台帳/正式資産/refsのwriterはrootのまま。


### ステップ5画面writerの限定指示（2026-11-05、PO委任Codex /root判断）

cache step5-scope-proposal.json c9f7a6ef…を基に、作者batted_prefix_connectionへ次を許可する。既source5: frontend/src/api/terminalPitchWire.ts・lineupPrefixWire.ts、screens/GameScreenOrdinaryPitchProvider.ts・GameScreenOrdinaryPitch.vue、新GameScreenBattedHitObservation.vue。対応test7は同proposalの既6 spec＋新GameScreenBattedHitObservation.spec.ts。さらに新frontend/src/api/battedBallOptions.tsと同spec.tsのexact2を追加（計14）。rootはこれらを同時編集しない。既Controller本体/GET41列validator/backend/正式資産/refs/台帳は作者変更禁止。

共有schema interpreterはallOfの全ANDと型省略properties制約を正式JSONschemaどおり検証し、未知constructを成功化しない。旧wireを全保持し閉4結果と12原観測の相関を検証する。既v3/一意artifact/queue/D5/ACK/re-read・実fielding rosterを再利用、在塁/TB/終了/併発・観測未確定は成功にしない。新componentは4結果と各6 nullable観測/公式記録条件の確認・修正を明示し、自動チェック/推測/既定観測を作らない。hitX/Yは既0..1の正準十進を直接入力し新座標計算/丸めを複製しない。

語彙キーの手入力を製品導線にせず、rootが同認証/C2でGET /vocabularies/batted-ballsを供給する。既pitch-typesと同じ閉Page(key,display_name; next_cursor)、limit1..100/cursor、DB側category=batted_ball/disabled=falseとkeyset有限読取。type/strengthは現正本/保存SQLの同admin categoryを消費し、未裁定groupを勝手に作らない。新FE APIも既transport/閉検証/paging/認可失効を再利用。未供給/失敗を固定候補や未観測へ自動置換せず、利用者が明示した未観測NULLと区別する。rootのbackend/token/正式登録・認可/DB検証は別直列writerで後続し、本FE成功だけで実画面保存成立にしない。作者は純検査/全SHA/旧比較を固定し非作者確認前にcommitやブラウザPGを開始しない。


### ステップ5実語彙readの担当分離（2026-11-05、PO委任Codex /root判断）

FE14と分離しstats_csv_next_unitへ新exact4: backend/src/pitchlog/api/schemas/batted_ball_options.py、同routers/batted_ball_options.py、repositories/batted_ball_options.py、backend/tests/test_batted_ball_options.pyを許可。前節endpoint/閉Page/実認証C2/tenant scope/keysetを満たす実callerを実装する。既SQLが受理するglobal admin_vocabulariesのcategory=batted_ball・disabled=falseだけの固定function readを候補にし、tokenはCAP:recording_vocabularies:read、関数はrecording_vocab_api.read_batted_ball_options。外部category/tenant/任意SQL/固定選択肢を受けず、上限101・正準cursor・key順/表示名・未知/改竄・越境を閉検証する。SECURITY DEFINERのsession_user/current_user・app.tenant_id一致/最小column ACL/EXECUTE・SQLbodyと共有app/registry/正式producerへの登録差分はcacheだけへ候補提示しrootが別途直列採否・反映する。作者は上記4だけを編集し、FE14/正式資産/共有code/台帳/refs/DBを変更しない。独立確認と正式登録前の純成功を製品read提供済みへ拡張しない。


### root共有登録/索引の最小接合（2026-11-05、PO委任Codex /root判断）

語彙readは非作者8b7f1019…によりauthor4/shared候補採用可、生成repository_contract.py手編集は除外し正式JSONから公式再導出する。root共有writerはapi/app.py・tenant_access.py、repositories/function_operations.py・operation_registry.py、authz/first_ball_product.py・新recording_vocabulary_product.pyと新tests/test_recording_vocabulary_product.py。既role/schema/fn再適用規約へ新role collision guard/schema所有者guard/function owner+ACLをcanonical producerに補い、public USAGEを既全文保持で派生する。stable readのメタデータを旧一律volatileと誤照合しないよう、正式volatility宣言からs/v/iを導出し旧全行不変を検査する。正式assets/生成moduleは公式publisher/deriveのみ、通常push前に後発差分も独立確認する。

実keyset queryのC比較順を支える非一意partial indexだけを、既db/tenant_isolation/models.py・新migrations/versions/0040_batted_vocabulary_index.py・contracts/db/schema-manifest.jsonに追加する。category=batted_ball/disabled=false・key COLLATE C、既列/PK/FK/role/RLSは不変。既design11-3の「実クエリに基づく索引」の実装で新意味仕様なし。実PGで索引/EXPLAINを別途検証し、sharedDBへ適用しない。develop0039の次は本0040を使い、別stats枝の未公開/隔離のみ0040_stats_fact_versionsは本0040採用後の正常基線追随で0041へ再採番しdown_revisionを直列接合する。旧stats隔離PG成功を新採番の適用成功へ読み替えず、30候補のうち変更したmigration境界だけを改めて照合する。


実PGカタログ診断によるexact2接合追補（2026-11-05、PO委任Codex /root判断）: 3633f95dのowned実migration0040/製品DDLは適用できるがfullprofile照合で新recording_vocab_api関数1件がactual集合に欠落する。診断reportでは旧全lifecycle関数値は一致し、新schemaがproduct_catalog.pyの固定読取SQL対象外だった。backend/src/pitchlog/authz/product_catalog.pyの_LIFECYCLE_FUNCTION_DETAILS_QUERYへ既新schema一名だけを追加し、backend/tests/test_recording_vocabulary_product.pyへ新schemaが実queryで読まれ旧schema全保持する回帰を追加する。期待を削除せず、DBで既関数と同じowner/SECDEF/volatility/body/search_path/EXECUTE照合を受けるための読取範囲追加。実PG診断の原report/拒否は保持し、通常検査のskip/結果差替え・権限追加は行わない。exact2を独立確認後、同版の非診断owned PGで再実証する。


実語彙HTTP/索引の検証単位（2026-11-05、PO委任Codex /root判断）: 新backend/tests/db/test_batted_ball_options_http.py exact1をrootへ追加する。既真正owned vertical fixture/実認証app UID/実PGを再利用し、参照語彙だけを準備する。実GETのページ境界/重複欠落なし/無効と異category除外/未認証拒否/認証tenant不一致拒否/改竄cursor拒否、app直接table SELECT拒否、新SECDEF資格と既fullprofile再適用/partial index実在を検証する。固定成功/仮Port/共有DB/新secretは使わず、global admin語彙にtenant別owned dataがあるとは仮定しない。新索引EXPLAINは有界keysetとplanner条件を区別して記録する。製品関数/認可失敗を試験で補わず、失敗時は同版診断→新差分を確認する。実HTTP成功は画面保存の実証や正式7.7へ読み替えない。


実HTTP試験の前提訂正（2026-11-05、PO委任Codex /root判断）: vocab-http-r1は2failed294秒。新試験がappのadmin_vocabularies直接SELECT拒否を期待したのはrootの誤りで、既正式ACL:admin_vocabularies:pitchlog_app/global_read_onlyはSELECTを採用済み（旧e2b72672と現候補で当該ACL全byte/全値不変）。既決の公開語彙readを禁止へ再裁定せず、同test exact1はsession_user/current_user=appを確認し、既SELECT成功を維持しつつUPDATE WHERE falseの拒否でreadonlyを実証する。権限を変更せず、既有限HTTP全assert/負対向は保持する。この訂正を非作者へ再照合し、HTTPだけ先にowned再検証する。旧4安打の再検証は第二系列の故障要求時binding_closeでLedgerUnavailableとなった別失敗として保存し、r4過去成功で相殺しない。lease/finishの安全条件や故障期待は変更せず、非秘密の終結診断を次の限定単位で行う。


安打4種の実画面縦断単位（2026-11-05、PO委任Codex /root判断）: 新frontend/src/screens/GameScreenBattedHits.e2e.ts・GameScreenBattedHits.playwright.config.ts・backend/tests/db/test_batted_hits_screen_e2e.pyのexact3を専有writerへ委任する。既screen start/lineup E2Eの実認証・画面新規POST作成・端末登録・実start・唯一controller/queue/ACK/GET/復元、ownedPGと実HTTPS補助を再利用する。4試合を画面で新規作成し、無走者の単打/二塁打/三塁打/本塁打を各1回→次球ball→同要求再送→reloadからafter/history/41保存値/runner before/afterを確認する。試合/記録の事前投入やtest-only API保存、画面fetch成功応答のmockは不可。参照選手/球種/結果/打球語彙のみowned準備し、実語彙endpointと実fieldingrosterから明示選択、観測6欄と裁定4確認を揃え、未観測も明示操作する。期待は既承認golden無走者4安打/次球の値を引用し、画面へ野球算式や別計算実装を置かない。新schema/frontend runtime/既E2Eは変更しない。既authority故障の結果不明は本画面成功で相殺せず別追跡、運用信頼TLS/実機成功へ拡張しない。作者は構文/型/対象lintまで、実PG/HTTPS実行はroot直列所有し、別非作者確認後に同候補で実測する。

実登録の期待追随（2026-11-05、PO委任Codex /root判断）: 成績接続候補の関連検査で、既batted語彙readの先頭登録1件がbackend/tests/test_function_operations_boundary.pyの全operation期待と親5objectのsliceへ未反映で2件失敗した。既全21operationの順序/値を保持し先頭の正式新1件だけを期待へ追加、親5objectのidentity照合は[4:9]→[5:10]へ移動する。実registry/認可/SQL/型検査/登録数を緩めず、当該exact1のoperation全集合・token全集合・親identityの3assertだけを是正して独立レビューする。

#192正式統合112f771eへの追随と#196最終登録（2026-11-05、PO委任Codex /root判断）: 実mergeの衝突はpayload fixture1件だけで、87case/全期待/v8/新artifactを保持し正式不正duplicate raw1件を復元した（599ec5be、runtime/数学/SQL/DDL7root不変、R5旧37record全保持）。関連4moduleは395pass/6fail/2errorで、新語彙1/owner1/schema1/3policy/11column ACLの旧固定期待未追随を確認。backend/tests/test_product_authz_catalog.py・test_authz_repository_contract.py・test_product_authz_provisioning.py・tests/db_fixtures.pyのexact4を有限期待追随writerへ移管する。旧全宣言/全schema/637原文/固定root43pinを保持し、新1CAP/1token/1operation・新schema/ownerUSAGEと宣言deltaに限って追加する。前段保留集合・public schemaの既追加/削除検査を緩めず、新要素を同じ閉検査へ入れる。実#196受理/正式module/source/censusはrootが公式helperで最終source固定後に直列再導出する。公開Draftの初回CIは準備中であり、最終成功の根拠にしない。

旧供給証拠の後発SQL拡張（2026-11-05、PO委任Codex /root判断）: 非作者67571a03で確認したbackend/tests/test_sync_apply_product_supply.pyと新backend/tests/fixtures/batted_source_extension_reference_v1.jsonを採用する。正式112fの688文と既採用immutable3633の705文を全値で束縛し、新17とpublic/prepareの2変更だけを別根拠へ照合、旧43pin/637文/31文原典を保持する。数学同等や旧人間署名の拡張ではない。併せてcontracts/tenant_boundary/frozen-inputs.jsonの旧24外部pathにこの2pathだけを追加し、tests/test_check_tenant_boundary_bypass.pyのexact期待にも同2を追随する。.claude/core-areas.jsonのsync-protocol pathsへ新fixture1を明示追加し、既検出/拒否/全pathは維持する。rootが全source固定後に公式#196単一受理・source/census/生成module/公開最終証拠と全CIを成立させる。exact6以外の一般的callback許可/署名免除・検査削減はしない。


#196 source後発登録の最小追補（2026-11-05、PO委任Codex /root判断で採用・本体未着手）: 正式112f771eと安打6965088bの4sourceを、旧pr191/pr192/90site/旧metadata/署名を全保持した別pr196層へ束縛する。実15tuple（lineup旧2ownerの6、ordinary旧8の行移動、固定Indexのtext1）と2owner successorだけを前置別Git期待Eから読む。identity sentinel2を許可siteへ変換しない。scripts/check_tenant_boundary_bypass.py、新tests/fixtures/pr196_tenant_source_expected_v1.json、新tests/test_pr196_tenant_source_registration.py、既tests/test_pr192_tenant_source_registration.py・test_check_tenant_boundary_bypass.pyの5を作者候補範囲とし、base-allowlist.json/frozen-inputs.jsonの正式2assetとcensus-baseline.json/tests/test_census_baseline_check.pyの後段2はrootが直列専有する。assetはcontracts/tenant_boundary配下。固定source/期待祖先/全byte・全tuple・型・旧登録不変・偽Contract拒否を要求し、hash追随だけ/一般DB API許可/旧期待上書きは不可。非作者調査77288229…の前後根拠を参照し、前置fixture分類の別人レビュー後にPO委任のroot判断で採用記録→Eを固定→本体を正式委任する。新core意味・野球結果・権限の追加ではなく、既採用差分の有限登録に限る。


前置分類の採用記録: 対象source6965088b9353dfa89643528531c22b340e9f4c72、fixture SHA52d056f109df66c29fea8f32ab900a2830d210efa6ff8985c3d5ca6bd6bedc7b、作者資料5df8c0eb…、非作者分類87e1089243de4aa19bd0ac41f43e5810514e64123af78c4733837287338ede6cを照合し採用する。旧pr191は全51（後継45/不変6）、pr192は全90（旧45/新45）を区別し、models旧49を新許可へ含めない。判断者Codex /root、2026-11-05 JST、PO既委任による技術的具体化であり本人署名/P6blind/旧人間確認の拡張ではない。Eのfull SHAは本fixture前置commit後に正式frozen入力へ束縛し、未確定文字列を受理値へ入れない。コアpathsは新fixture/test2だけtenant-isolationへ明示追加する最小追随を別非作者確認し、既検出を保持する。


source登録の採用記録: 作者cache source4（checker7a6c9a4c…/新196test ed7131c2…/旧192test cc7d619d…/旧checktenanttest257dfdc7…）と正式追加候補2を非作者f0a1ae8b57885132df0ac893dab7450dc43f0d56dc5ed6dedd46db9e03cdd0b2で照合し採用した。actual root回帰409pass31.84秒、旧fixture3と追加偽型対向を独立確認。判断者Codex /root、2026-11-05 JST、PO既委任による判断。E0f75/fixture52d056/旧51・90/11maps16frozen/37履歴は保持、本人署名/P6blindの拡張ではない。正式2assetは識別値と射影の公式更新・単一#196受理がまだ必要な候補であり、current source診断0や回帰を正式7.7/CLI/CI成功へ読み替えない。後段census source1は別非作者確認中。


census追随の採用記録: 作者7f37309b…/source bfe3c4f7…を非作者fb144d3a30a67496836b834b802ef1eccdde604fb5546fe547661aa62c423616（独立69成功、shadow CLI exit0）で照合して採用する。判断者Codex /root、2026-11-05 JST、PO既委任による技術追随判断。旧全180定義/78test、歴史90/37・現在84/37・新15とsentinel2を区別、models旧49・署名範囲保持。正式census JSONは新proof6leafとinventory6だけを追加し旧全値を保持した候補で、識別値/射影/単一#196受理/正式CLI/CIは後段で閉じる。本人確認/P6blind/実PGの成立へ拡張しない。
