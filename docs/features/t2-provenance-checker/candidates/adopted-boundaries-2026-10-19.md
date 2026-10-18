# PO採用5件の候補境界と受領条件

2026-10-19、POの本会話での採用を候補へ実装した。候補作者の人工fixtureによる検査であり、正本/正式契約の確定、P-6、製品出力検証、署名、担当受理ではない。candidateId=`t2-p8-followup-v1`、schemaVersion=1を保持し、境界fixtureのbyte SHA-256を候補schemaのconstとbundleで固定する。旧固定版との識別にはgit commitとdigestを使う。

## 宣言前評価とphase

`normalize_p8_candidate_context(request, projection=…, authorizations=…)`の公開候補型:

- request: `scope:{tenantId,gameId}, projectionRevision:int, phase, gameEnded:bool`。
- phase: `playing | condition-locked | declared | reopened`。requestは選択権を持たず、信頼側投影と完全一致が必要。
- projection: 同scopeの順序付きreceipt列。各receiptはsequence、receiptId、eventRef、eventVersion、kind、timing、thirdOut、authorizationRef、basedOnEvaluationRef、afterを持つ。afterはphase/gameEnded/decision/evaluationRef。decisionは既存T2の6フィールド型を検査する。
- `kind=evaluation`は共有終了判定核の出力投影。通常は`timing=post-play`が完了評価。第3アウトのpost-playは暫定であり、**同じeventRef/eventVersionのpost-turn（攻守交代後）まで完了しない**。未完の列や暫定評価を参照した宣言を拒否する。
- 「直前」は、宣言イベントの直前の受理済み投影prefixにおける最後の完了評価を指す。宣言receiptのbasedOnEvaluationRefとafter.evaluationRefで固定し、そこでのdetected/lock/outcomeを保持する。宣言後はphase=declared、gameEnded=true、prompt=false。3値を再計算/上書きしない。
- `kind=declaration/reopen`には別入力の認可済みreceiptが必要。認可IDだけでなくscope/eventRef/action/expectedRevision/allowを全照合する。declared状態からの通常evaluationは禁止し、受理済みreopenを必要とする。
- reopenedはgameEnded=false、lock=false。終了条件が継続する場合detected=true/prompt=true。次の評価で条件が消えればdetected=falseを認める。promptは宣言の必要状態であり、毎球の強制dialogや再ロックの指示ではない。

**信頼境界**: 545のtenant/game認可済みイベント適用サービスが、保存済み受理イベント・共有核投影・操作認可記録を同じprefixで取得し、projection/authorizationsをサーバー側引数として渡す。request body内の投影/認可を流用しない。fixture中のproducer名やallowという文字列は認証手段ではない。この候補はadapterの責務と照合器までであり、実在する製品endpointへの配線や認可実装完了を主張しない。

候補再生はrevision0から始まる評価/操作receiptの連続列を検査し、third-outの2評価では同じrevisionを共有する。製品の全イベント列や途中snapshotをそのまま入力するAPIではない。製品adapterが不関与イベントも含む実際のrevisionと対応させる責務は545に残り、途中snapshotの採用は本候補で許可していない。JSON永続化後の再読込と別CLIプロセスで同じ列を再生する試験を行う。計算核のコピー実装は追加していない。

入力権限は既存操作認可から取得する。保持されたlock/detected等から独自に権限を広げない。E09のロック中undo可/交代不可とundo後の状態・終了条件再評価は既承認候補を保持し、宣言後のundo等へ拡張しない。

## サヨナラ前後得点

`normalize_p8_candidate_score(request, authoritative_observation=…)`:

- request: scope、projectionRevision、eventRef、beforeScore/afterScore（各home/away非負整数）。
- observation: producer=`shared-state-transition-projection`、scope/eventRef、beforeAppliedVersion/afterAppliedVersion、beforeScore/afterScore。
- beforeは**評価対象プレイを適用する直前の受理prefix**、afterは**その同じプレイを共有計算核で適用した直後**。afterVersion=beforeVersion+1、request.revision=afterVersion。取り消し・再適用時はその時点の受理prefixから取得し直す。クライアントから送った得点と照合して異なれば拒否し、推測補正しない。
- 544が共有状態遷移核/投影器から両観測を出す。545が同scope・event・revisionで取得して渡す。照合器は得点加算やサヨナラ判定を実装しない。人工fixtureの逆転/同点の得点は独立期待値ではない。既存の信頼された製品投影への実接続は受領条件。

## kind/payload拒否境界

既存descriptorの`event.operationKind`7値と`event.operationPayload`6タグを使う。per-pitch/undoはnot-applicable、それ以外はkindと同名のpayloadタグが正常。state-correctionは既存FR-040の採用宣言が必要。標準fixtureは非採用のため正常6/拒否36であり、採用宣言時の正常試験も別に置く。payload内部の製品固有フィールドschemaを新設したとは扱わない。

既存handoffエラー名との対応: 欠落/型不正/未知kind/tag/矛盾は`HANDOFF_SHAPE`、未知fieldは`UNKNOWN_FIELD`、信頼投影や認可・得点観測との不一致は`MAPPING`。新しいネットワーク応答コードの正式制定ではない。拒否時に矛盾した要求を修正/捨てて通さない。試験は入力が不変なことも検査する。

## GAP-05の表示受領物

E07=Bを維持しT2 decision.xMarkは単一値のまま。表示は対象cellごとの契約へ収容する。cellは`inning:int, half:top|bottom`、開始判定は最初の投球の有無とは区別する（攻撃開始済みで初球前なら0）。

- 攻撃開始済みセルは記録得点を表示。
- 未開始の裏で、対応する表が完了し終了条件が裏攻撃を不要とするセルはX。
- それ以外の未開始セル（将来回等）はblank。評価状態が裏を指すだけでは開始済みとしない。

`displayCases`5件は具体cell、started、pairedTopCompleted、endConditionMakesBottomUnnecessary、recordedScoreを固定する。比較型はscope/projectionRevision/targetCell/displayで、blank=`""`、0=`"0"`、X=`"X"`を区別する。`compare_p8_candidate_display`はoracleと出力の同一対象/prefix/表示を完全比較する。現在の5件の比較相手は**人工出力**であり、表示関数は実行していない。

受取担当は表示契約/FR-030・U-F8（TSK-523側）と545の引渡し境界。実際の担当者名・受理日・受理返信は未取得。表示担当が既存投影から対象cell/started/得点を得て製品表示関数を実行し、同一prefixの独立期待値と全5件以上で比較する。独立確認者が既存E11/E07確認をP-6へ転記せず別対象版で期待値を確定する。受領・独立期待値・実製品比較がすべて成立するまで**GAP-05はopen**。

## 受領条件と正式ゲート

| 受取先 | 渡す具体物 | receiverDoDへの対応・未成立条件 |
| --- | --- | --- |
| 544 | score観測型/2 fixture、kind/payload42 fixture、正規化器、E12相関21件 | 新入力の全projectionと共有核投入証跡が必要。製品runner/revision/CI、採用FR-040のmanifestと担当受理は未 |
| 545 | phase/保持参照型、5投影列・認可照合、E02/E09/E10候補、E08/E06/E04の5case、E12導出器、provenance/両loader | 既存248caseと候補の製品消費、新入力projection/認可接続、runner/revision/CI、P-6・正式版・担当受理は未 |
| 表示側 | 5セルfixture、比較型/比較器、blank/0/X変異試験、上記GAP条件 | 表示oracle独立作成と製品出力取得・比較・担当返信は未。依頼物準備と実受理を区別する |

正本patchは未適用。正本7.6確定ゲート、正式契約/schema/descriptorへの具体反映と7.7（先行受理履歴を保持）、実版の人間再署名/逐行確認、P-6独立期待値の受理、担当の実受領はそれぞれ未成立。要件のE12追補の別枝統合/版調整も未完として扱う。追加コードレビューが合格してもこれらを代替しない。
