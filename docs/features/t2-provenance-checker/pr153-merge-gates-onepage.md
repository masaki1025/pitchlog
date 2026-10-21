# TSK-564 / #153 統合残ゲート・受理・後続範囲（一枚）

**照合基線**: develop `fb719e368f6dbc8a178cba9d42af875553c1bc1f`を既存枝へ通常merge=`2b83471ad14151c554f1407caaf25d261d30ec8f`（競合なし）。旧コード/候補固定点=`5a9e37bd263787106f08bb05224f01333e79ffc3`、今回一次是正=`e0eb936f`、署名対象T2 digest=`sha256:e93f30f75b97f580d3ee0984ff4300bb7a35544a4568a0fedfabf32da81e1ec4`。本人確認者は本会話で**山田正輝**と指定（未実施）。条文/対象資産との対応と最終差分の提示方法は[本人確認依頼](human-review-request.md)、固定P-6入力/原典/提出先は[P-6パケット](p6-transfer/README.md)。新規PRなし、[既存Draft #153](https://github.com/masaki1025/pitchlog/pull/153)で継続。U-S1の担当整理とは別。

## 今回の明示許可・一次レビュー結果・本人確認依頼（現況）

**本人回答の更新**: 本人から「確認した」「空欄でいいから作業を開始して」を受領。旧固定HEAD72e1c147への確認応答は受領済み、範囲/方法/実施日/限定再署名は空欄で保持する。既存[本人確認依頼の転記準備欄](human-review-request.md)に再計算digestと空欄の転記案を用意した。正式署名記録は未更新で、署名不一致は未解消。未回答情報や宣誓の推定補完、旧署名の転記、ゲートの緩和は行わない。

**許可根拠**: POの本会話の新指示「#153に限り、Claude一次レビューの代替として、候補作成に関与していない別Codexセッションによる一次レビューを許可します。この指示を今回の明示的な許可根拠として記録してください」。[PRコメント6314710443](https://github.com/masaki1025/pitchlog/pull/153#issuecomment-6314710443)へ原文を記録した。以下の旧「許可未確認」はこの指示前の観察で、再承認待ちには戻さない。

| 一次レビューの実績 | 固定対象・独立性・結果 |
| --- | --- |
| 対象 | base9136c2da、HEAD `f9f972f3086743a3b146e0d7c451cb7bccc23d49`の全PR差分32ファイル。binary diff SHA-256=`81c3f1e6538c5c8683625f2ab202147971a8890aeeb7fe3d42e36886a63ed12e` |
| 実施モデル/独立性 | 開示モデル=GPT-6ベースCodex（正確なruntime ID不明）。新規セッション `/root/pr153_primary_review`、履歴継承なし、候補/コード/規範行/case/期待値の作成修正に不関与、read-only。別の一次レビュー1回として実施 |
| 観点/結果 | 全差分の要件適合・規約・NFR-018を確認。**P0=0/P1=1/P2=0**。製品核コピーは未検出。レビュー担当は関連727試験、TS loader18試験、ruff/ty、候補CLI/provenance repository、パケット全件と10原典hashを確認 |
| 指摘と採否 | P1を全件採用。E06 ONE-OF-TWOの5回裏7対0に10点差@5/7点差@7では成立0なのに1/cold-end。`e0eb936f`で候補だけ7点差@5/10点差@7へ交換し、既承認の設定2段・成立1段/出力を保持。候補固有入力の照合と旧反例/点差不足/開始回前の3拒否試験を追加。一般コールド計算は複製しない |
| 是正後の扱い | 作者の影響検査で是正を確認する。**是正差分は独立再レビュー未実施**で、元の0/1/0を0/0/0へ書き換えない。既存敵対レビュー基本2＋追加2/最新0/0/0は別履歴として保持。P-6とは別 |

**署名と本人確認への影響**: 正式T2/schema/provenanceはレビュー対象f9f972f3から不変。RFC8785現物digest=`sha256:e93f30f75b97f580d3ee0984ff4300bb7a35544a4568a0fedfabf32da81e1ec4`を最新基線fb719e36で再計算。D1〜D4全true、provenance以外の全フィールド/8行/248case/拒否12は旧署名対象と一致。候補E06の是正は署名対象digestを変えず、本人逐行確認には是正3ファイルと記録差分を追加する。

**是正後検査**: 最新develop取込後の関連6ファイルは736 passed/12.36秒（旧反例等3件を含む）、TS loader18 passed/1.54秒、ruff/ty/docs-status/計画正本同期/diff-check合格。是正commit e0eb936fのbinary diff SHA-256=`9701154adc2834b3d03b37d8f4a9ed7ced1abf53e681fdc5ee681a803d6c048d`。最終HEADのCIはpush後に確認し、既知署名失敗を除外しない。

**未再レビュー差分**: (1) e0eb936fの候補JSON/検査器/回帰試験とworklog、(2) 今回の一枚/本人依頼/plan/worklogの許可・結果追記、(3) develop9136c2da→fb719e36の通常merge。取り込み先47ファイルと本PR32パスは重複0。どの追加分もf9一次レビュー済みとしない。全対象一覧は末尾、最終HEAD/全差分SHA/固定リンクは既存#153本文先頭へ固定する。

**本人回答待ち**: [既存の確認依頼/回答欄](human-review-request.md)。山田正輝の本人逐行確認とprovenance限定再署名はともに未実施。対象/範囲/実方法/実施日/留保を実回答で受けた後だけ転記し、署名追加差分は別提示する。旧チェックだけでは成立としない。署名schemaの方法はdirect-clause-comparisonであり、追加provenance/未実施の記載を典拠・承認範囲と実際に直接突合したかも回答していただく。未実施の独立導出やP-6署名を宣誓しない。

**留保**: 新意味・正式契約・正本確定・7.7の変更は今回なし。P-6部分提出は未受理、GAP-05 open、544/523限定受領は保持し、後続全完成を器候補の統合条件にしない。旧計画Codex追認はPR後の完了ゲートとして別管理。本一次レビューを旧計画追認やP-6へ転用しない。最終CIと人間の実操作は未完のまま。Draft解除・merge・公開なし。

## 2026-10-21 統合直前の更新（以下の旧観察より優先）

- 公開旧HEAD `8de07d98`に対する最新完走CIは[run39163174868](https://github.com/masaki1025/pitchlog/actions/runs/39163174868)。harnessのみ署名digest不一致で1 failed / 29,633 passed / 2 skipped、他11ジョブ成功。PRの逐行確認チェックは入っているが実施記録の対象/範囲/方法が空欄で、本人確認成立とはしない。新HEADのCIはpush後に別途回収する。
- 通常merge後も正式T2/schema/両loader/検査器/候補は8de07d98から不変。関連727試験、被覆変異/取込検査経路289試験、TS loader18試験、ruff、ty、計画正本同期が合格。D1〜D4全true、8規範行/248case/validationErrorsはprovenance除去後の旧署名と一致。取り込んだ他担当71ファイルは基線の変更であり、本担当の新実装とはしない。
- **一次レビューの許可根拠は未確認**。544からの中継は「既存の今回限定のCodex代替一次レビュー許可が利用できる場合」という条件付きで、544/564の取得済み履歴に原文/対象/追加回数は見つかっていない。既存の基本2＋追加2を一次レビューへ推定転用しない。POには、既存許可の原文/対象を示すか、固定最終差分に対する候補非関与Codexの一次レビュー代替1回を認めるか、規定のClaude担当を指名するかだけを判断依頼する。未承認の追加レビューは起動しない。
- **523は候補責任分界を限定受領済み**。正式カード返信 `3fe93b75-e687-8183-8fa4-001d9d0b0249`を直接取得し[#153コメント](https://github.com/masaki1025/pitchlog/pull/153#issuecomment-6264381651)へ記録。同一scope/prefix/cell表示=523後任、cell/started/表完了/裏不要=545信頼投影、記録得点=544共有T1、生成formatter利用。5セル/E07=B/E02/E09/E10を候補として受領。正式セル公開型/実投影formatter提供SHA/独立oracle/製品比較は未受領、GAP-05 open。後続#166を#153の統合条件にしない。
- **P-6は部分結果の提出あり・所有側受理未成立**。[提出コメント](https://github.com/masaki1025/pitchlog/pull/153#issuecomment-6291294608)はT2規範行4 verified/4 blocked、case136 verified/112 blocked、拒否12 verified、mismatch0と報告。未曝露性の制限とT1側不足も記録されている。これは提出報告の回収であり、本担当の独立再検証/受理ではない。正式provenanceは`not-performed`のまま。旧パケットは固定履歴として保全し、部分提出をP-6全成立へ昇格させない。今回の器/候補の統合条件に追加しない。
- 本人が回答する対象はPR本文で固定する新HEADと全差分SHA。実施日/範囲/方法とprovenance限定再署名の実回答後だけ記録する。署名記録の追加差分は別提示し、元の確認を新HEADへ自動延長しない。

以下の表の「未指定/未実施/返信未取得」と旧CIは当初の観察履歴を含む。523/P-6/CIの現況は上記を優先し、正式受理や本人行為への推定転用はしない。

**統合する範囲**は承認済み計画どおり「provenanceの器/検査器/両loader・fixture」と「P-8の未正式候補/能動検査/受渡し記録」。**P-8正式資産の完成を意味しない**。後続もTSK-564の引継ぎ範囲として追跡し、新規PRや担当移管を勝手に決めない。P-6の未実施を署名更新で消さず、T1/T2製品開始条件P-2/P-6/P-7/P-8は未成立のまま維持する。最新UX1計画ではP-1/P-3/P-4/P-5/P-9は成立、545はT1(PR-1a)マージも必要。

| #153統合に必須の残件 | 対象・閉じる条件 | 実施担当/現況 |
| --- | --- | --- |
| 1. gate6再署名 | 下記のprovenance追加だけの現物/差分/D1〜D4を人間が実確認→明示再署名→実施者/日/範囲/方法だけを記録→署名test合格 | 計画上PO。**今回の確認/再署名は未実施**。564は資料準備と実施後の転記のみ |
| 2. PRレビュー記録 | 今回PO明示許可の未関与Codex代替一次1回を全差分f9で実施、0/1/0。P1全件採用・e0eb936fで是正。基本2＋追加2は別に保持 | **一次実施済み**。是正後の作者検査と未再レビュー差分を明示し、本人へ提出。追加レビューの無断起動なし |
| 3. 本人逐行確認 | 最終PR全差分を人間本人が確認し、PRの必須チェックと「対象/範囲/方法」を本人が記入。独立コードレビュー/署名材料生成は代替不可 | **実確認者=山田正輝（指定済み・未実施）**。core-guardは未チェックを理由に失敗 |
| 4. 最終必須CIと統合判断 | 1〜3の実行後、固定した最終版で必須CI全緑、残件/後続範囲を明記して人間が統合判断。既知失敗を除外しない | 564が検査/差分提示、人間がmerge。完走済みa5a2aa38のCIはharness署名1失敗（29,633 passed/2 skipped）、core-guard失敗、backend/frontend合格。最新取込後は関連707件/18.54秒、ruff/ty/候補CLI/正本差分同期/docs-status/D1〜D4合格（全harness再実行とは区別） |

**旧計画のCodex追認**は計画/代替レビュー版を対象とする未実施の**完了ゲート**（計画書はPR後の追認とする）。実施担当/証跡は未指定・未取得。今回の限定コードレビューを計画追認済みとせず、根拠なく新しい製品着手条件にも加えない。正式provenance差分の受理もPO/契約所有側の実確認で行い、Draft許可を受理へ流用しない。

| 544/545/523の受理回答 | 固定版/具体的受入条件 | 確認できた回答・残り |
| --- | --- | --- |
| 544 | a5a2aa38/コード5a9e37bd。score2/操作42/E12相関21、同一scope/event/prefixの共有T1核の得点供給、undo後再評価 | **候補の責任分担として受領済み**。#155の[UX1 worklog](../../worklog/2026-10-10-ux1-state-calc.md)「2026-10-19 #153受渡し後の担当受領と開始条件」で直接確認。得点供給だけを受領し、T2認可/phase・表示oracle・正式契約/P-6の受理には拡張しない。既存の544担当の指名/受諾を未指定に戻さない |
| 545 | 同コードのphase/保持評価参照/認可照合/context5/lifecycle3/decision5/E12/provenance。着手前は型/版/投影・認可・score受取の責任範囲、実装後はrunner/全case/実投影/共有核投入の結合証跡 | **受理回答未取得**。送付comment `3fd93b75-e687-812d-b9f1-001d5941192a`。受取りは既存主担当へ集約。既送の差分依頼へ回答待ちで重複送付しない。今回の未回答は後続の正式化/製品引渡しの待ちであり、器/候補だけの#153統合に全受理を追加しない |
| 523/表示側 | 同コードのセル5件/比較器/blank・0・X拒否試験。対象cell/started/表完了/裏不要/得点の供給元と表示責務を明示 | **受理回答未取得**。送付comment `3fd93b75-e687-810d-9219-001d6ae5d03e`。受取りは既存523主担当へ集約。既送依頼へ回答待ちで重複送付しない。後続の正式表示型/実装引渡しで必要な受理。製品比較は実装後であり、#153統合や着手前に要求しない |

Notionコメントに新返信はなくても、統合済みworklogの544回答を受理証拠として採用する。545/523の役割窓口へは直接送付可能。今回の返信様式は **「対象commit・受領する公開型/責任・未受領の範囲/理由・受理区分・実施担当」**。送信成功を受理回答とせず、同一版の照会を連続送信しない。

| P-6/再署名/人間確認 | 対象と実施内容 | 実施担当・指名が必要なもの |
| --- | --- | --- |
| P-6 T2 | 現行正式8規範行/248caseと原典（対象digest上記）を作成者以外が原典から先に期待値導出→全件照合→範囲/結果/本人の独立性を所有側が受理。将来の正式P-8追補は別の固定版で追加検証 | **独立検証者未指定、受理実施者も未指定**（既存窓口236/538）。POが未関与者を指名。契約/case/候補を作成・修正した本Codex/担当自身を指名しない。自己試験・今回コードレビュー・既存DeepSeek E11/E07確認はP-6でない |
| P-6 T1 | 544側の正式行/case/閉入力制約・得点上限等。T2と範囲を分け、候補のscore2/操作42の自己一致で代替しない | **独立検証者未指定**。544の実装担当の指名済みと独立検証担当を混同しない。PO/UX1・所有側が対象版を固定 |
| gate6再署名 | D1〜D4は最新developでも全true。provenance除去後digest=旧署名3514e1c6…、現物=e93f30f7…、8行/248case/validationErrors不変。POは追加provenance全内容、固定版、限定範囲を実確認してから明示再署名。P-6はnot-performedを保持 | 計画上PO（旧記録の氏名/日付を新実施証拠へ流用しない）。564は本人の確認/署名を代行しない |
| PR本人確認 | provenance schema/検査器/両loader/候補/試験/受渡しを含む最終差分の逐行確認。チェック・実施方法は本人が記入 | **確認本人=山田正輝（本会話で指定済み、未実施）**。再署名と別項目で管理 |

P-6は元provenance計画の実施対象外で、未実施の閉じた形を正しく保持するのが#153の責務。**P-6完了をprovenance器だけの統合へ一律上乗せせず、P-8正式完成/545着手には引き続き必要**。同様に、正本7.6・正式P-8凍結資産7.7は未適用の後続ゲートであり、再署名だけで成立させない。

| DRAW/GAP-05 | #153で完了させる範囲 | 明示的な後続（未完/担当） |
| --- | --- | --- |
| DRAW-01〜04（設定拒否/有効） | 01=L<R、02=M≤0、03=R<タイブレーク発動≤L、04=先行拒否非該当という既決意味と、既存単一軸invalid12件では相関を保証しない不足を記録。01〜10の未被覆宣言とGAP-04集約resolvedの差を隠さない | 正式相関型/要求/正常・拒否case/保存検証との対応→必要な7.6/7.7→P-6/所有側受理。**564契約候補、550保存担当**。正式受理実施者は未指定 |
| DRAW-05 | 既存T1参照ST-OPERATION-e6c67c06707d5759と未被覆宣言を照合し、参照ありを全件被覆としない | T1行/宣言済み同点・最終score帰属の正式対応/P-6。**544/契約所有側** |
| DRAW-06/10 | 宣言済み非同点/最終回裏完了非同点の責任分界と、T1は得点供給だけ受領したことを記録 | 勝敗・終了の正式収容先と行/case。**545/546・契約所有側**。546への分担線回答待ち、実受取担当未確認。意味の推定裁定をしない |
| DRAW-07〜09 | 上限なし継続/有限Lの裏未完/裏完了同点の既決条件、通常/limit既存行との未閉鎖対応を記録 | 正式case/評価時点/軸間制約・被覆台帳・P-6/受理。**564/545契約側**。自動終了へ変更しない |
| GAP-05（5セル） | E07=B単一xMark保持。X/将来blank/開始済3/宣言後未開始blank/初球前開始済0の5具体入力・比較器・結合漏れ拒否を保存し、対象cell/供給元/受入条件と送付状態を記録。**openを保持** | 表示契約の正式型/必要な正本7.6・凍結7.7、523/545の責任受理、未関与者の独立oracle、実表示出力比較。**523表示、545状態、544得点、独立oracle担当未指定**。実比較は対象実装後DoD。正式T2のblank0行/0caseを解消済みとしない |

**まとめて必要な指名/判断**: ①作成未関与のP-6 T1/T2検証担当と236/538側の受理実施者、②反対側Claude一次レビュー担当/旧計画Codex追認担当と既履歴のゲート対応（新枠が要る場合のみ範囲・回数を承認）、③表示の独立oracle担当（後続正式化時）。PR本人確認者は山田正輝と指定済み。545/523の受取りは既存主担当へ集約し、再指名/同一依頼の再送はしない。再署名は既定POの**実確認待ち**であり、署名更新許可を実施事実に置換しない。後続の正式契約/P-6/製品実装を完了済みとする承認は求めない。

本表の#153候補統合と後続正式化の境界は人間の統合判断時にも確認する。TSK-564の未完責任や既定開始条件を省略する承認ではない。

**今回の直接依頼（資料固定49c018ee、コード5a9e37bd）**: 544へ再照会せず、545へ#155後の得点受取/phase認可/DRAW収容の差分確認（comment `3fd93b75-e687-81a0-82b8-001decaaf1a0`）、523へ得点/状態/表示の分界とGAP担当確認（`3fd93b75-e687-811a-bfcb-001d00148857`）、546へDRAW-06/10の分担線確認（`3fd93b75-e687-8138-b3e3-001d6740b7e0`）、POへ上記指名の一括依頼（564カード `3fd93b75-e687-819e-bbfd-001dd43ea178`）を送付。新回答の受理ではない。受理状態は本文表のまま。

更新: 山田正輝さんへの本人確認依頼とP-6引継ぎ資料を固定した。P-6は未関与Codex担当の確保待ちで、集合確定と検証可能性を区別し、WALK-OFF前得点不足/評価文脈/未正式DRAW・GAP-05を推定verifiedにしない。

## 最終提出の対象・未再レビュー差分・採否

最終HEAD/全binary diff SHA-256/固定比較リンクは、この資料のcommit後に既存#153本文先頭へ記載する。比較元はfb719e36。一次対象f9以後は上記E06候補是正・通常merge・許可/結果資料追記がある。正式T2と署名対象は不変。追加資料差分は未再レビューとして本人確認対象へ明示し、既存レビュー0/0/0を資料まで拡張しない。

採否: 基本第1回CLI予約値偽装P1は採用し26f5c949で是正、基本第2回0/0/0。追加第1回の表示入力/典拠結合P1は採用し5a9e37bdで是正、追加第2回0/0/0。未解消の実装指摘は0件、不採用はなし。一次レビュー成立の根拠不足と未再レビュー資料を隠さない。

全対象ファイル（比較元fb719e36対提出HEAD、32件）:

```text
backend/src/pitchlog/domaincheck/runners/handoff.py
contracts/state-transition/appendix_e_consumer_handoff_v1.json
contracts/state-transition/game_end_contract_schema_v1.json
contracts/state-transition/game_end_contract_v1.json
docs/features/t2-provenance-checker/candidates/README.md
docs/features/t2-provenance-checker/candidates/adopted-boundaries-2026-10-19.md
docs/features/t2-provenance-checker/candidates/p8_boundary_evidence_v1.json
docs/features/t2-provenance-checker/candidates/p8_candidate_schema_v1.json
docs/features/t2-provenance-checker/candidates/p8_candidate_v1.json
docs/features/t2-provenance-checker/candidates/requirements-followup.patch
docs/features/t2-provenance-checker/handoff-and-gates-2026-10-19.md
docs/features/t2-provenance-checker/harness-failure-disposition-2026-10-18.md
docs/features/t2-provenance-checker/human-review-request.md
docs/features/t2-provenance-checker/p6-transfer/README.md
docs/features/t2-provenance-checker/p6-transfer/inputs-without-decisions.json
docs/features/t2-provenance-checker/p6-transfer/manifest.json
docs/features/t2-provenance-checker/p8-fixed-candidate-report-2026-10-19.md
docs/features/t2-provenance-checker/p8-followup-scope-candidate-2026-10-18.md
docs/features/t2-provenance-checker/p8-human-decisions-and-receivers-2026-10-18.md
docs/features/t2-provenance-checker/plan.md
docs/features/t2-provenance-checker/pr153-merge-gates-onepage.md
docs/features/t2-provenance-checker/research.md
docs/worklog/2026-10-17-t2-provenance-checker.md
docs/worklog/2026-10-18-t2-provenance-checker.md
frontend/src/testing/handoffLoader.spec.ts
frontend/src/testing/handoffLoader.ts
scripts/check_deriver_dependencies.py
scripts/check_provenance.py
scripts/check_required_set_coverage.py
tests/domain/runners/fixtures/handoff-loader/mutations.json
tests/domain/runners/test_handoff_loader.py
tests/test_game_end_contract_schema.py
```
