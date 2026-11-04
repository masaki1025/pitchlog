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
| 4 | 同TX保存/GET/再送/原子性/越境 | rootとownedPG時間調整。event/PlayRow/PlayRunner/history/checkpoint/ledger/両cursor・責任投手を不可分保存。単打等は打者到達塁へ1runner、HRはempty。元D5再送/ACK喪失/故障rollback/別tenant拒否と実GET完全値 |
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
