# 通常37の有限prefix接続ABI候補

状態: 20case候補を非作者再確認P0/P1/P2=0・PO委任主担当判断でsource開始受理（74444640/b2e1108a）。正式全T2受理・実保存成立とは別。既計画5stepの有限追補であり、新全体計画ではない。機械形/20caseの正は `contracts/state-transition/ordinary37_continuation_candidate_v1.json`。

新公開operation `deriveOrdinaryPitchWithContinuation` のrequestは exact `version,prefixRef,rules,t1,prior`。t1は旧ordinaryのeventKind/resultId/pitchEventKind/beforeだけ（historyを受けない）。prefixRefは exact `version,tenantId,gameId,generation,length`、UUIDはlowercase8-4-4-4-12、generationはD4（記録世代）のopaque string（1..128文字）/lengthは非負整数の正準十進文字列。refの真正性は文字列検査では成立しない。サービスが確認済checkpoint/prefixの同game/rules/水位から供給する。

priorは started-initial / evaluated-prefix / locked-prefix の閉union。prefixRef/rules/afterを必須とし、evaluated-prefixだけは前回の評価済T2完全値を必須とする。startはlength0かつ実開始の正規状態のみ。callerのgameEnded=falseや自称openを権限根拠にしない。ref/rules/beforeの完全一致、未評価/未知T2拒否、既lock保持を行う。既first-ball T2封筒はそのまま読み、ordinaryの新no-end封筒と区別する。

内部で旧deriveOrdinaryPitchへ局所history.stack=[]を与え、T1を一度評価。同じderivedをT2へ渡す。T1成功出力からhistoryContextを取り除き、その唯一要素をnewHistoryEntryへ移す（0件/複数なら閉拒否）。成功は exact `ok,value:{t1,t2,newHistoryEntry,previousPrefixRef,nextPrefixRef}`。nextは同参照のlengthだけn+1。newHistoryEntryはfull historyではない。S2ファウルで差分空でも1件を保つ。旧full stack APIは不変。

T2は保存規則・位置・cold全段/DRAW分岐・T1不変条件を実評価する。前回lockや終端済を得点/アウト不変だけで解除しない。source着手の閉範囲は通常37のみ。E11/E07/GAP05、得点を伴うcold/walkoff競合、終端操作へ解釈を拡張しない。

case期待値は作者による完全response候補であり、独立受理済ゴールデンではない。source specではschema全封筒検査と既数学caseを基にした全値exact照合を組み合わせる。合成entry成功を実prefix/認可/DBの成功や独立blind検証へ読み替えない。

refのgenerationは既D4を指し、recovery_generationの正整数型とは別である。lengthはordinary-only確認済prefixに含まれる支持37投球entryの確定水位であり、一般履歴長/D1/D2/PlayRow番号との一致を仮定しない。後続の取消/訂正を含む一般履歴設計を置き換えない。保存rulesはrefだけでなく実内容を完全一致させ、DRAW-01..04の相関を実検査する。今回の閉範囲は通常open系列であり、再開後homelead等を恒久的に禁止する仕様を新設しない。

#### 前回T2の意味束縛（非作者P1反映、2026-10-30）

rules/afterの対比較に加え、prior.t2自身のbasisをprior.rules/afterへ意味束縛する。旧初球封筒は対応する初球after（1表/S0B1/0out/空塁/打順1/無得点・全board0/TBなし）とR/L/cold/TBの既閉条件を照合する。新ordinary封筒はR/L実値・回/表裏/TB・cold全段の順序付き分岐・DRAWを保存rules/afterへ照合する。未知/不一致はT2_NOT_EVALUATED。純数学内部一致は実prefix真正性の代わりではない。

成功期待値は既数学封筒＋静的after/T2/ref/history値から完全responseを組み、全項目のexact比較を行う。候補JSONは20caseへ追加し、旧T2移植・新basis回/cold/L不一致の対向を含む。元の16件固定を品質条件にせず、部分一致へ緩めない。
