# TSK-544 T1 P-8 入力・規範行・case・負例候補 v0

状態: **候補**（2026-10-20）。作成: TSK-544。対象: 付録E-1のT1、FR-003/004/009、A-1 OUT3-01〜05、A-3 RBI、XC-13、ADR-003 D-8/D-11。正本、`contracts/`、正式7.7、独立期待値ではない。承認済み[plan.md](../plan.md)の先行単位で作成し、正式契約の編集・受理は指名済みの所有者が行う。未決の値は`pending`で止め、製品コードへ投入しない。

## 出所と既存版との対応

| 既存資産・版 | 使う既決要素 | この候補が補うもの |
| --- | --- | --- |
| 要件書 v2.15、FR-003/004/009、A-1 OUT3、A-3 RBI、付録E-1、XC-13 | 走者別観測、OUT3の優先、無効得点をRBIへ渡さない、タイブレークの規則条件 | フィールドの閉包、拒否条件、実case |
| `input_axes_descriptor_v1.json` の `stage2ExternalConstraints` | `runnerEventPayload`、`runnerAdvanceOverridesByRunner`、`thirdOutTimingByRunner`、RBI走者別2軸と8種類の未解決制約 | そのうちT1に必要な内部schemaと負例。正式descriptorのdigestは未変更 |
| `state_transition_contract_v1.json` schemaVersion=1 | `matrixRows`/`operationRows`/`undoRows`/`cases`の形式。操作4種と既存tiebreak payload、D+1 liveness-only | 別候補の規範行・case。既存行/caseは変更しない |

## C-1 閉入力の提案（J1/J2/J3）

1. **scopeと参照**: 正規化する1イベントはサーバーが認証した`tenantId`、`gameId`、記録権世代と受理prefixを文脈として受ける。payload内の選手ID・走者IDは同じ試合の確定済み名簿/当該prefixと照合する。欠落・他試合・他tenant・存在しないIDを推測補完しない。どの名簿版を渡すかはU-G1/U-R1の公開型との照合待ちであり、この候補は新しいDB取得経路を許可しない。
2. **操作の判別**: 既存`operationKind`の`substitution`、`game-end-declaration`、`adhoc-registration`、`tiebreak-start`ごとに`payloadShape`を閉じる。共通の不透明objectを許可しない。FR-040の`state-correction`は延期のまま。既存行の`additionalProperties:false`、必須field、列挙値を維持する。`game-end-declaration`のpayloadは空objectのまま。各操作のGiven不成立は内容の推測補正に変えず、U-S1が受理する既存拒否分類へ写す（G6-S08、wire IDは未受領）。
3. **走者イベント**: `runnerEventPayload`と`runnerAdvanceOverridesByRunner`のrunner-keyed集合は起点塁`first`/`second`/`third`に閉じる。打者走者は`batterDestination`で扱い、runner-eventの走者キーへ`batter`を混ぜない。各走者に結果・必要な到達塁/アウト種別を高々1組与え、開始時不在走者、同じ走者への相反する安全進塁/アウト、XC-08の到達可能集合外を拒否候補とする。IDは同一scopeの名簿へ照合する。**重複JSONキーはparse済み`SyncEvent`では検出不能**なので、506の生wire外形検査/端末キュー永続化時に拒否する。T1には重複がないparse済み入力だけを渡す。具体enumは正式schemaの判定待ち。
4. **第3アウト観測**: 第3アウトの記録員観測は「打者走者の一塁到達前」「フォースアウト」「踏み忘れアピール」「その他」の種類と、アウト対象の起点塁または打者に分ける。踏み忘れ塁の保持が別の記録に必要かは所有側が判断し、OUT3-03判定のためだけに過剰な必須入力へしない。`appeal`の前位/後位は観測値でなく**判定対象走者ごとに**走順から導出する。第3アウト対象本人は生還候補から外す。`OUT3-01`〜`03`に該当すれば得点無効を確定する。それ以外で生還候補がいれば既存軸`thirdOutTimingByRunner`の当該走者の`home-before-third-out`/`not-before-third-out`を必須とする。**同時は前ではない**。欠落・矛盾時は拒否し、塁位置や時刻から補わない。正式field名と種別の値集合は正本/契約レビューの対象。
5. **RBI観測**: OUT3で無効となった得点はRBI判定に渡さない。既存descriptorの`officialScoringPayload`、`rbi.doublePlayRelayError`、`rbi.runnerContinuityByRunner`、`rbi.wouldScoreWithoutErrorByRunner`と`interferenceRuling`を組み合わせ、RBI-01〜09の優先順に必要な観測を判定する。どの先行分岐を除外すれば後続観測が必須になるかの閉じた条件は**未完成**であり、欠落を`false`で補わない。23個の`statFlags`は出力であり入力payloadへ入れない。23キー別の必要十分表と規範caseは着手前の正式受理対象として作る。実機接続・検証証跡だけをPR-1a内で得る。現候補には23キー表が未収録のため、この条件は未成立。
6. **タイブレーク**: 既存`operationRows[].payloadShape`の`runnerPlacement`（`first-second`/`second-third`）、`leadoffBatter`（1〜9）、`inning`を維持する。配置する走者の個人IDと打順の対応を追加候補とし、保存済み規則snapshotの発動回・配置条件を基準に照合する。operationの値でsnapshotを上書きしない。回不一致、active中再開始、許容外配置は拒否候補。どの走者IDを指名できるか、再開始拒否の結果ID、R/L snapshot型は所有側の正式レビュー待ち。負例は「回のみ」「配置のみ」「activeのみ」「規則なし」を分け、複合エラーで優先順位を捏造しない。

## C-2 規範行・case・負例（候補。完全な契約出力ではない）

以下は**原典から確定できる射影**だけを書く。case IDは候補IDであり、正式`cases[].caseId`の割当、全10列の`expected`、`historyContext`は所有側ゲートで行う。P-6には入力のみを別パケットで渡す。

| 候補行/case | 原典 | 入力の要点 | 期待する射影・拒否候補と残る型 |
| --- | --- | --- | --- |
| T1-OUT3-01 | A-1 OUT3-01 | 二死三塁、三塁走者が生還、第3アウト=打者走者一塁到達前 | 得点0。時機を入力してもOUT3-01を優先 |
| T1-OUT3-02 | A-1 OUT3-02 | 二死一・三塁、三塁走者生還、一塁走者が二塁でフォース第3アウト | 得点0 |
| T1-OUT3-03 | A-1 OUT3-03 | 二死二・三塁、三塁走者の本塁踏み忘れアピールが第3アウト。三塁走者本人は生還候補外 | 後位二塁走者の得点0、チーム得点0。前位関係は走者ごとに導出 |
| T1-OUT3-04 | A-1 OUT3-04 | 上記3例外でなく、三塁走者が第3アウトより前に本塁到達 | その走者の得点1 |
| T1-OUT3-05 | A-1 OUT3-05 | 上記3例外でなく、三塁走者の到達は第3アウトと同時または後 | その走者の得点0 |
| T1-OUT3-NA | A-1 OUT3対象外 | 一死三塁、三塁走者が生還、打者走者一塁到達前アウトは第2アウトで第3アウトなし | OUT3を適用しない。走者の得点1。第3アウト時機を要求しない |
| T1-OUT3-N1 | A-1 OUT3-04/05 | 例外3種ではない第3アウト、生還候補あり、走者別時機なし | 欠落として拒否。時刻推定しない |
| T1-OUT3-N2 | A-1 OUT3-03、FR-003 | appealを指定し、アピール対象runner IDが欠落 | 観測不足として拒否。前位/後位を観測フィールドへ置かない |
| T1-RBI-N1 | A-3 RBI-05、XC-13 | 無死/一死、三塁走者が有効生還。RBI-01〜04がすべて非該当と確定した打球失策で、失策なしでも得点したかの走者別観測なし | RBIの値を仮定せず拒否する候補。先行分岐を除外できる完全入力は**未完成**なのでP-6配布対象外 |
| T1-S20-HR | A-1 サヨナラ、RBI-06 | 裏の同点、走者二人、本塁打、OUT3による得点無効なし | 打者・全走者の3点、RBI-06の打点3を計上。T2の終了検知をここで実装しない |
| T1-S20-NONHR | A-1 サヨナラ | 裏の同点、本塁打以外の同プレイで2人が順次生還し先の1点が決勝点 | 決勝点までの1点のみ計上する原則は既決。生還順の閉入力が現descriptorにないため、この具体caseの入力形は**未確定**。P-6配布対象外 |
| T1-S20-OUT3 | A-1 OUT3-02・サヨナラ | 裏の同点・二死一三塁、三塁走者が生還した後、一塁走者が二塁でフォース第3アウト | OUT3-02で得点無効。サヨナラ上限に入らず同点のまま |
| T1-PAYLOAD-N1 | ADR D-8/D-11、既存`operationRows[].payloadShape` | `game-end-declaration`の空payloadへ宣言外field | 既存`additionalProperties:false`により拒否。外側envelopeの外形拒否とは別 |
| T1-PAYLOAD-N2 | FR-003/004、ADR D-11 | 不在runnerへのevent/override、他試合ID、同一runnerの安全進塁とアウトの矛盾 | 参照・相反違反として拒否する候補。個々の境界caseを分ける |
| T1-TB-N1 | FR-009、付録F-1 | snapshot許容外の回だけを指定 | snapshotを書き換えず拒否する候補。具体結果IDはU-S1契約待ち |
| T1-TB-N2 | FR-009、付録F-1 | `tiebreakActive=true`で再度開始 | 再適用せず拒否する候補。具体結果IDはU-S1契約待ち |

S20の第1候補は新しいE-1列を足さず、既存の10列で生還候補とアウトを判定した**後**に、共有T1核の得点効果としてサヨナラ上限を評価すること。既存caseの`expected.historyContext[].difference.scoreboard.inningScores`は得点のbefore/afterを表現できる（既存`ST-MATRIX-e7e9f402f1b80eb0`で実在）。この同じ比較面へ上のHR/非HR/OUT3組合せを載せれば、得点0/1/3の最終値を追加列なしで検証できる候補となる。ただし**評価順そのもの**の規範表現が既存schemaで足りるかは契約所有側が検査する。T1は保存済み規則、裏/表、適用前スコアから有効得点と上限後スコアを計算し、T2は**T1の上限後スコア**を受けて終了を判定する候補とする。T2の終了結果をT1の得点計算へ逆流させない。`OUT3-01`〜`05`の評価結果を先に入力し、無効得点へRBI/サヨナラ上限を適用しない。表現不能ならE-1 exact型の最小正本改訂と7.3レビューを別に提示する。無断で第11列を作らない。

## C-3 負例とゲートの対応

| 負例群 | 拒否位置の候補 | 未確定の実値・所有者 |
| --- | --- | --- |
| wire/envelopeの宣言外field・JSON重複キー | 生wireまたはraw importのparse前/時は506/U-F7の外形境界。アプリが既に組み立てたobjectの永続化だけでは重複キーを検出できない。T1に重複を失ったobjectを渡さない | 506/U-F7が各raw byte入口の失敗分類と試験を受理する。T1は重複キー検出の所有者ではない |
| payload内部の宣言外field・参照不能ID・相反指定 | parse済み入力のT1正規化/意味検証。外側envelopeのS-1と分ける | 同一scope名簿版/U-G1・U-R1、拒否原本/結果分類/U-S1、契約受取者 |
| OUT3種別/時機/RBI観測の欠落 | T1意味検証、得点・フラグ確定前 | 観測TS型/U-F8、Port拒否理由とT9対応/U-S1、契約受取者 |
| タイブレーク条件・二重開始 | 保存済み規則snapshot照合後、状態効果前 | snapshot公開型/U-G1、Given拒否結果/U-S1、契約受取者 |

各負例のD5消費、拒否原本保存、混在バッチの前方確定/後方未処理への写像はU-S1既存経路へ照合し、T1独自のACKを作らない。外形S-1と内容拒否の境界が確定しない負例は正式caseに昇格させない。

既存S06/S10/S14/S17/S23〜S26/S30、G6-S09〜S11、23キー別表、FR-010/011/015のGiven拒否、S11/S13/S22のTSK-546裁定は本候補だけで閉じない。[未解決台帳](../../appendix-e-golden-vectors/unresolved-report.md)と逐行比較し、未収録範囲を正式受理済みと数えない。特にD+1 `liveness-only`の既済みcaseを長さ1/2/Dへ一般化しない。

## C-4 正式ゲートへの差分見取り図

| 正式資産 | 必要になる変更候補 | 現在の扱い |
| --- | --- | --- |
| `contracts/state-transition/input_axes_descriptor_v1.json` とschema | deferredの8制約のうち、T1で採用する走者/操作/OUT3/RBI閉入力と軸間制約を解決し、digestを再計算する | **未編集**。fieldの最終名・値域・schemaの正は所有側のレビュー待ち |
| `contracts/state-transition/state_transition_contract_v1.json` とschema | operationのpayloadShape/規範行、OUT3/RBI/S20のcase、negative fixture、requiredSetへの参照 | **未編集**。既済みD+1/tiebreak-start行と受理履歴を保持する |
| `contracts/state-transition/state_transition_manual_fixtures_v1.json`、coverage/branch mapping | 手動fixtureと行/case/原典の対応、双方向負例 | **未編集**。候補と現契約のcaseを重複登録しない |
| `contracts/state-transition/appendix_e_consumer_handoff_v1.json` | 正式版/digest・入力軸射影・runner消費範囲の追随 | **未編集**。`normalizerId`等の実識別子は製品PRで確定する |
| 要件書付録E-1、ADR-003 D-8/D-11 | S20の既存10列表現が不能な場合だけ最小改訂を提案。具体型の新条文化が要る場合は7.3確定ゲート | **未編集**。J1〜J6の方針承認を条文確定へ流用しない |

正式契約の指名受取者が、候補の各行について原典・完全な正常/拒否出力・入力schemaの閉包・既存caseとの非重複・digest前後値・7.7の要否を確認する。P-6の独立検証者は作成者と分け、現行109件と追加パケットの範囲・結果を別に記録する。正式受理時には固定版・原典対応・独立レビュー採否・P-6結果/未検証範囲をPOへ提示する。
