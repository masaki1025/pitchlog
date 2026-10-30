---
feature: mvp-first-pitch-t2-connection
status: active
承認: 済（2026-10-26・PO委任によるCodex判断・最初の一球限定）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-first-pitch-t2-connection
created: 2026-10-26
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 初球T1/T2単一評価の有限追補案

作者候補・未承認・未実装。基線920191f3、既数学9path/型adapter2pathの承認・レビューと旧T2候補を保持。本反映の作者はt1_remaining_out3_casesであり、以前のT2候補の非作者レビューを本反映へ転用しない。

## 1. 背景・目的

[TSK544](https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f)の数学T1と、545所有T2の初回接続依存を進める。[要件正本](../../requirements/requirements-pitchlog-2026-07-22.md)FR-003/FR-005/FR-014、NFR-018/019を根拠に、実createのgame_other R9/L9/DHtrue・cold[]/TBnullを最初の必須正例へ追加する。旧R7/R9・Lnull・dh booleanを保持する。既規則から決まる非該当評価の接続であり新しい野球意味を追加しない。

## 2. スコープ

新操作 `deriveFirstPitchWithContinuation` は `{t1:既FirstPitchRequest,rules:保存規則wire}` を受ける。同artifact内の共有private T1評価helperを1回だけ呼び、その同before/board/DerivedをT2純核へ渡す。既deriveStateの入出力/4errorと既gameEndDecisionの6outcomeは不変。

T2が扱うのは初回表・0out・S0B0→S0B1・空塁・0–0・通常初期状態だけ。R7/Lnull、R9/Lnull、R9/L9を区別し、dhはbooleanを保持。両側TBfalse、balls以外のstate/scoreboard全field不変、同打順を必須とする。before/afterのbatter実IDは既数学ABIに無いため生成せず、trusted初期名簿/同T1評価refのprivate結合で保存前に照合する。

サービス/HTTP/UI・実start・認可/記録権/RG1・D5再送/結果不明・実DB保存・一般T2やE11/E07の再裁定は本単位へ含めない。それらと真正初期sourceは実API保存前の接続依存であり、T1数学本体を開始待ちへ戻さない。

## 3. 影響する正本・exact対象案

requirements/design/ADR/development/opsの意味改訂なし。実装は既採用規範の限定評価。rootが既親計画追補と次の12pathだけを正式指定し、必要7.7の実影響を照合する。

| 区分 | exact paths |
| --- | --- |
| 新契約候補 | `contracts/state-transition/t2_first_pitch_continuation_schema_v1.json`、`t2_first_pitch_continuation_v1.d.ts`、`t2_first_pitch_continuation_cases_v1.json` |
| 新純核 | `frontend/src/domain/firstPitchContinuation.ts`、`frontend/src/domain/firstPitchContinuation.spec.ts` |
| 既単一入口/検査 | `frontend/src/domain/publicApi.ts`、`publicApi.spec.ts`、`firstPitchArtifact.spec.ts` |
| 同一再現artifact | `frontend/public/domain/pitchlog-domain.js`、`pitchlog-domain.json` |
| 新Python型caller | `backend/src/pitchlog/domainrt/first_pitch_continuation.py`、`backend/tests/domainrt/test_first_pitch_continuation.py` |

略記は各行の直前directoryを共通接頭辞とする。既state.ts/stateRules.ts/stateTypes.ts、旧first_pitch.py/host.py、既6outcome、build/checker/拒否条件は変更しない。entry.tsは既自動domainOperations exportを再利用し編集不要。ブラウザwrapperは現在pingだけであり、この単位の提供済み画面機能とは数えず後続へ残す。

## 4. 実装方針とステップ

コア領域（状況/終了計算）。publicApiの既正規化/derive呼出を共有private helperへ抽出し、既deriveStateはそのwrapperのままにする。新操作だけが同評価結果をT2へ渡す。Pythonから旧deriveState→新T2の二回呼出、Python式、case/期待lookup、8代表行fallthroughで非成立とする実装は禁止。構文/型/build検査は既拒否を維持し、sourceを許容構文へ合わせる。

| # | 有限実装 | 合格条件 |
| --- | --- | --- |
| 1 | 新ABI/12作者caseと単一評価TS純核・同artifact | 新操作の閉形状/5local error枝、R9/L9正例と旧正例、未評価がok:false、T1一回呼出、旧deriveState全値/既4code/全23flag/一deltaを保持、同artifact実Node/ブラウザ・再現hash、非作者source確認 |
| 2 | typed Python callerと最終接合 | 既FirstPitchRequest/FirstPitchValue/DecimalIntegerとJSON重複/非有限拒否を再利用。固定open_domain_hostだけ、nested immutable/alias-only/canonical decimal/closed union、実host全値と故障検査、必要全件CI/最終HEAD/PO委任証拠 |

新契約の受理とsource実装はroot承認/非作者確認後のみ。step1未完のままstep2を完成扱いにしない。共有publicApi/artifactはrootの単一writerで既T1枝へ直列接合する。

## 5. DoD

両評価済み時だけ `ok:true,value:{t1全値,t2:評価済み非成立}`。T1失敗は既4code envelope。T1成功/T2未評価は新操作固有 `ok:false,error:T2_NOT_EVALUATED,value:{t1全値,t2:未評価}` で、partial T1を保存可能と扱わない。新codeを既deriveStateの4enumやHTTP/sync codeへ混ぜない。

正規化した実R/L、空cold、延長境界前、表・不変得点を読んだ根拠だけを返す。lock/prompt/xMark等の固定falseを詰めず、既lifecycleをclearしない。範囲外/故障/未供給は非成功へ閉じる。数学結果と真正source/認可/同TX保存は別で、外形/refのshapeだけではReadyにならない。

## 6. テスト計画

一致性は旧T1 fullvalueを変更せず新値t1へ照合し、artifactとPython callerで同一結果を消費する。単体はR9/L9/DHtrue＋旧R7/9null、正しい型の未対応rules、T1未対応、全strictfield/十進/alias/tuple、同before/Derivedと非ball field不変を検査。新helperのT1呼出一回はtest-only spy/静的呼出関係と実artifact結果で確認し、製品へ注入可能hookを公開しない。

対向例はT1成功/T2未評価のpartial frameがok:falseで保存候補へ流れないこと、R7終了局面がR9代表行に非一致でも非成立とならないこと、callerがafter/t2/bindingを供給するとINVALID_REQUESTになること。型callerの故障と実host成功を分け、既208/既frontend回帰を保持する。実owner binding/認可/TX/DB負例は後続の接続検査で必須であり、この構造候補の成功と混同しない。


## 操作単位の正式採用と限定開始記録

2026-10-26 JST、Codex /rootはPO委任と最初の一球の操作単位への変更指示に基づき、作者plan aebb2fc5a5825fa5871f8874a07621dd7446522dc3e9cda4c3a3521d3d1683f0 / ABI schema7be1b18643b1b58bc34752ec1f30109cf9c0cc3c06b84de6868b4d2170c51645を採用する。候補作成へ不関与のt2_first_pitch_plan_reviewによる独立REVIEW172fe6c3422b7df5c9282fcc3a24823de5591370962b638a507c96f7563052cdはP0/P1/P2=0、原典・manifest33・12case形状・独立負形状22・旧ABI/6outcome保持・tscを確認。新しい意味判断は不要。旧T1/545の承認・全MVP義務・既レビュー系列を保全し、本書はその初回非終了接続の有限単位である。

別none-forkの純入力導出はmanifest78f149cdee7587cfa0a4d93200df502e8ea185c412937ee383c669902a1d7b1e/入力N01〜03とprimary2資料だけを渡し、derivation76210a061889d5cce15ef234764352d5b3ca0d24dac1db6ff10eaa55caf1928d・audit822273dbf94a71a6e9e4518a488f7e24a7d4f1707bf19335b1f6f26069b83d58・seal794603dc5f5868c6912b45ee327f06dec6ec09d9e124d509366ef310d96ddd03を先封印。rootがSHA/0444を実照合後だけ作者3正例を開示し、比較33f3a81894222bd67cd63664b67b1b43654e49d13448c2966e906949a44a6464/曝露監査ec7d92880231e0fd5cc4b85f3148f6db5c8570b6556d38e58c8b758fc3f20095を受領した。比較可能な3件のT2 tag・実R/L・家族別非成立根拠は同値、不一致0/投影内unknown0。旧封印4fileは不変。

これは入力観測を前提とする限定独立導出と曝露後比較である。通常勝敗終了の完全閉表未確認・厳密blind資格非保証・自己申告読取監査の精度留保を維持し、T1全値・真正ref・認可/保存・内部一回評価・負形状・全P6を認証しない。P6未曝露や全成立を新agentだけから主張しない。rootはこの限定意味の確認を当単位の純核着手に受理し、実source一回呼出/正規rules/全入出力/故障は実装後に非作者が別検査する。

新3contractファイルはレビュー済み候補byteをそのまま採用し、AUTHOR/NOT_IMPLEMENTEDの生成時provenanceラベルを消さない。正式な採用の根拠・対象SHA・判断者・日時は本節で示す。格納だけで実装完了・全契約発効・API提供とはしない。必要な正式bootstrap/7.7・影響metadataは実差分からrootが照合し、未受理を成功へしない。

本節までの条件でステップ1のTS純核・共有private一回評価・同artifact・試験だけを実装開始可とする。作者t1_remaining_out3_casesの唯一編集はfrontend新純核2pathと既publicApi/publicApi.spec/firstPitchArtifact.spec/生成artifact2pathの計7path。contracts3/plan/Git/共有台帳はrootが唯一writer、Python新caller2pathはステップ2の指示まで編集しない。既state.ts/stateRules.ts/stateTypes.ts/既first_pitch.py/host.py/既4codeは不変。AST/拒否を変えずsourceを許可構文へ合わせ、scope外・partialを保存成功にしない。新規実装はsource確認を受けた後に接合する。

2026-10-26 JST、ステップ1 source7は作者handofff47cac8e0a6f95477ac991128589e108adf3bc6ac195f6aaebc75558fa880f69で固定。非作者creation_pathのreview f7e08bc53726e14862b6a0955ba0b4fb992f06ab057c50d9b414844ab8b7851f/evidence94097cedee84f3ec17a7f81043187b692d6a5e2079f1c9b9b74f0c4d699ef54eはP0/P1/P2=0。独立134検査1.83s、実artifact391要求schema違反0/旧deriveState差0、製品open_domain_host12全値、guard付き再build同hashc970af6d103b1536ee1aebe6422bd82df2dc80b23188f041fe691a6dcd6f9d04/10826byteを確認。作者全frontend94file/1994成功101.36s・Chromium149headless12全値/schema12は別証拠。共有T1 helperを1回だけ呼ぶsource spyと同before/board/Derived identityを確認し、artifactへ計数hookは追加しない。旧T1全値/4code/23flag/一delta/保護11path/guard5は不変。rootは実SHA照合後PO委任により当source7を受理。数学接続の成功であり真正source/認可/同TX/API/DB/全T2/実機は未達。ステップ2は新Python型caller2pathに限り次の作者へ委任し、source/再計算/expected lookupを増やさず固定hostの新操作一回呼出へ接ぐ。

2026-10-26 JST、ステップ2 Python caller2sourceを作者handoff6327835fad48fd51937560ee279b74b5dacb2b04df8dff11783f6a42975afdd5で固定。別非作者t2_first_pitch_plan_reviewのREVIEW e58cb3cead3fe1512d4e9e8df595450a5f4f759adf0392204f84b85293696c02は指摘0、独立関連4module279成功3.65s/Ruffty・追加故障16形状拒否・強制変更host0・固定operation1回・保護13asset不変を確認。rootはcaller8706488eb1d06e032f8b83427ebea02188d44be236087a793331e5ddc022096f/testdad7624d29b82423c0943f6c7e1d5ccea751858c94f694e29ec6138ba34d9f9eをSHA照合しPO委任により有限数学呼出部品を受理。旧decoder alias反例は別有限是正としてfirst-pitch枝で256回帰確認済み、新callerは全wire同値/typed member検査で局所拒否。正常instance再検証を妨げた中間20失敗/初回2失敗も保全。rootが次にその依存修正を通常mergeし、同artifact/旧caller/新callerをまとめて再確認する。必要全件CI/最終HEAD/公開証拠・真正初期ref/owner認可/RG1/同期保存/API/UI・全T2/MVPは未了であり、279成功をそれらの達成としない。
