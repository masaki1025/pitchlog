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
