# 終了・追記再開の7.3起案作業ログ（2026-11-06、cache-only）

- actual worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-nonplay-product-connection`、開始HEAD `2e0205908108492fc72d8378803e7d68a34b6983`、featureブランチ。作業木へは未反映。
- 根拠: `/home/ymdms/.cache/pitchlog/mvp-lifecycle-product-author-20261106/packet.json` SHA256 `2f464208ef8ed53e78048ea5370e55204b60584b7397b51272882b1bed91fee8`。同cacheの`MINIMUM-INTERFACE.md`と`formal-proposals/sync-protocol-v0.13-draft.md`、`adr003-d11-registration-draft.md`を照合。作者の実PG・全API・実画面合格報告はない。
- PO権限: rootからの既PO委任。技術wire/保存形の具体化は許可。野球の意味、D5、拒否順、Shouldの再裁定は対象外。人間本人の逐行確認・署名を代理記録しない。
- 7.3適用版: **v1.19**。approved条文コミット `3092c6dbfd7e69a2cc96efccd46de72a87f4841b`。現HEADの7.3節と同コミットの7.3節は同じSHA256 `c2955c8a4616414524983f484b836fc84415e44e1bcb465bc9824ae12a4548f9`。実適用版は初回敵対レビュー時に再照合する（7.3-1）。
- 初回全対象: 要件書v2.20、同期プロトコルv0.13、データモデルv1.6の**全文**を一括１件でレビューする。３文書の新履歴行とfrontmatterはすべて`in-review`。承認・approved化・索引current切替は未実施。
- 受理scope案: 既Must6種へ追記再開を末尾追加し、#13 `game_reopen`をD1/D2付きP1/端末送信P2とする。閉V7のend/reopen・最新target全３値、真正control bridge、独立lifecycle admission/head、sameTXのstatus/成績版/receiptと旧確定版失効を規範にする。FR-005の自動検知とFR-010の宣言は分離し、reopen中の終了条件由来lockだけを解除する。正式contract/enum/CHECK、実DDL/ACL、実PG/実機は後続実装の受け取り先。
- 既規範保全: 旧#1〜#12、FR-040 Should、P3訂正、DI2/DI3/DI5、C2/RG1、結果不明・旧要求後着遮断、既全caseを変更しない。`docs/legacy/`・共有台帳・実DB・`.env`・P6へ不触。
- 現在の段階: 草案生成と整合確認。敵対レビュー0回、採否0件、反映0周。root/POの承認はまだない。


## rootによる実起案（2026-11-06）

- actual worktreeを feature/mvp-lifecycle-product-connection（起点a7cc3c0b）へ分離し、3文書のbefore/after全SHAをpacket eeecf3c2…と照合して起案。旧cache-only記述は作成時履歴であり、ここからactual in-review。
- 適用版暫定は7.3 v1.19/条文コミット3092c6dbfd7e69a2cc96efccd46de72a87f4841b。初回開始前に現条文と固定版を再照合する。全3正本の全文を対象とし、今回が初回。非作者レビュー前にapprovedにはしない。
- PO委任によるroot判断はこの起案とレビュー実施順のみ。意味/正式本文の最終受理は未成立。

- 初回開始前のroot再照合: 現7.3節は固定条文コミットと全byte一致。節SHA256 c2955c8a4616414524983f484b836fc84415e44e1bcb465bc9824ae12a4548f9。適用版はv1.19を維持する。

- 初回前の記録訂正: 7.3-1の「approved条文を収録する最新コミット」は起案第一親 `a7cc3c0baa05fd1a1639e1f98e8f8f7bb39ad229`。3092c6dbは条文の元固定点として保持し、ゲートの適用条文コミットはこの第一親へ訂正。条文全byte/SHAは同一で版v1.19不変。非作者レビューはまだ開始していない。


# 7.3初回否決・反映1周目 worklog 案（未確定）

対象は `feature/mvp-lifecycle-product-connection` の `0962102a8a1ad853a0fd7f0a4d2b1831a9d26dd0`。適用条文はハーネス7.3 v1.19、初回全文レビューは `~/.cache/pitchlog/lifecycle-gate-first-independent-20261106/REPORT.md`（P0=0/P1=6/P2=1、否決）。rootの全7件採用方針を**候補**へ写した。これはPO本人の逐行承認でも反映コミットでもない。採用を伴う初回なので、実際に反映した場合のカウンタは `確定ゲート周回 0→1`、コミット件名はステップ記法を付けず `反映1周目` を含む。次周は「初回反映差分＋影響節」であり、全文実施済みと扱わない。

| 指摘 | 原レビューの分類 | 典拠（初回レビューの所在） | 採否と根拠／候補差分 |
| --- | --- | --- | --- |
| 1 | P1・起因・(A) | sync-protocol 7-5-A:1243, 8-5:1423、data-model B01/B06:2430-2443,2491-2523、requirements 6.2:1057-1060 | **全採用案**。端末`game_reopen`はD1付きP2でD5+範囲の意図を同TXで保存。B06の操作ID方式は同期イベントを発行しない既規定の管理削除・復元・再開だけ。FR-008単なる再表示では発火0。同一状態変更で両意図を作らず、既5範囲の選択子と期限例外を保持。 |
| 2 | P1・起因・(A) | requirements 4.0-4:207-208, FR-007:312-313, FR-010:332-338、sync-protocol 7-5-A:1243-1247 | **全採用案。ただしwire形はroot技術判断待ち**。`checkpointRef`を確定CP／先行キューCP依存の閉union、reopen targetを確定終了版／先行終了予約値の閉unionにする。先行のD4/D1/D5・予約eventId/receiptIdを同じ不変本文へ固定し、サーバー実受理結果からのみCP/終了版を解決。未成立は既prefix未処理としてD5未消費、成立後の差違は既B3a/P5へ。stored DI2を先に再掲し、結果不明の再送・旧要求終結・後着遮断・不可分置換を保持。端末で存在しないCP digest/終了versionを作らない。 |
| 3 | P1・起因・(A) | requirements FR-007:283-291、data-model 6-1-d:1386-1390、sync-protocol 7-5-A:1249-1251 | **全採用案。ただしP3 receipt供給はroot技術判断待ち**。終了後P3は終了版version/eventId/completion receiptを動かさず、訂正後stats新版本・headの公開stats pointer・P3自身のD5/T6確定結果に結合するpublic pointer receiptをP3 T1/T2/T4/T6/T7と同TXにする。後続reopen targetのreceiptIdは元の終了receiptであり公開pointer receiptとは別。P3が安定receiptを供給できない場合、この方式を成立済みにしない。 |
| 4 | P1・起因・(A) | sync-protocol 5-5:621, 7-5-A:1243-1245, 8-1:1384-1388, 11-2:1423、data-model 5-3:950-953、DI2:730-736 | **全採用案**。#13未使用D5のfreshは必ずP2/T5共通allocator/O4。同D5同本文の既受理はDI2再掲でP1再適用しない。#5と旧#1〜#12の経路・意味を変えない。 |
| 5 | P1・非起因・(-) | sync-protocol 2-5:132-150,5-5:621,8-1:1423,11-2:1979-1995、scripts/design_relations/sync-protocol.json:710-775 | **全採用案**。`R-PARTICIPATION`のsourceに`13:追記再開+P2`を追加し、7-2/8-1/11-2の期待subsetだけに追加。6-4の「再開2択」は別の再開境界なので追加しない。旧全14要素と他9 relationは全値保持。 |
| 6 | P1・非起因・(-) | sync-protocol 7-5-A:1251-1253,8-1:1380-1388,10-3:1843-1854、data-model M05:1112-1137,6-1-d:1388-1390 | **全採用案**。既T集合を変えず、P2制御のT2/T3/T4/T5/T6内側にCP/bridge/admission/status/head/stats/S/credit/意図/D5結果/receiptを固定。終了後P3はT4/T6/T7内側でstats版/head公開pointer/receipt/無効化意図を観測。10-3のexact内側キー、注入点、部分確定拒否を明記。`R-TXN-ROUTE`にCL1と各伝播先を機械追加し、旧関係全値維持。実JSON/runner値は実装段で作る。 |
| 7 | P2・非起因・(-) | sync-protocol V5:282、requirements 用語:154、sync-protocol 4-6:464-470 | **全採用案**。典拠欄の「Must 6種」を「Must 7種」へだけ修正。Should条件付き1種の意味は不変。 |

**起因集計**: 起因4件（指摘1〜4）、非起因3件（指摘5〜7）。(A)4件、(B)0件、(-)3件。7件全採用案・不採用0。ただし指摘2/3の具体wire/receipt選択はroot裁定前であり、候補を採用済み・承認済みとは数えない。

**影響節/次周**: requirements 4.0-4, FR-007/010, 6.2; sync 2-5,4-3 V5,5-5,7-1/2/5-A,8-1,9-2,10-2/3,11-2; data-model 5-4 M05,6-1-d,11-2 B01/B06; relation manifest `R-PARTICIPATION`/`R-TXN-ROUTE`。正本の既FR-007/010、旧#1〜#12、D5/DI2/DI3/DI5、P3の終了後V12不要とB9/B8等の拒否順は保持対象。


### PO委任によるrootの反映判断（2026-11-06）

判断者Codex /root、対象0962102aからcandidate.patch SHA472260ef63cf2282201e8b4f6eefd37a89f9cb6bd6d32a25391c51f82acd42d9。初回P1全6/P2全1を採用。不採用0、終結済み一覧は上表7件。前記作者案の「root判断待ち」2点は次の技術仕様として選択Aを採る（正本最終承認ではなく反映判断）。

- checkpoint/targetの閉unionは、先行要求の予約IDと耐久本文を変更せず、同tenant/D4/D1/D5の実受理結果からのみ解決する契約とする。予約値を確定値や記録員観測と扱わず、未成立/差違/結果不明は既拒否順・D5扱いへ従う。閉contract/solver/再送・後着遮断ケースは後続実装に必要で、今成立済みとしない。実Port完成を規範具体化の前提に追加しない。
- 終了後P3は終了宣言のversion/event/completion receiptを維持し、P3自身の真正T6結果に束縛するpublic pointer receiptを同TXで一度だけ保存する方式とする。任意receiptやtest-only finalizeでは供給しない。新規の意味変更・新規秘密発行はなく、訂正成績と同D5再掲の既保証を具体化する。P3のprivate発行/一意保存/再掲・故障対向は未実装義務として保持。

反映1は三正本＋機械manifest、planカウンタ0→1、同worklog採否を単一commitで固定する。次は第2回（反映差分と影響節）。正式contract/実装/DB/全MVP成立やPO本人逐行確認の記録ではない。


# 7.3 第2回否決・反映2周目 worklog 案（未確定）

対象は`feature/mvp-lifecycle-product-connection`の`e7af4801b549c8c98f6fcd2623ea0a8bf11703c5`。初回全文レビューはP1=6/P2=1、反映1周目は既記録のまま。第2回は初回反映差分と影響節の独立レビュー（`~/.cache/pitchlog/lifecycle-gate-second-independent-20261106/REPORT.md`）でP0=0/P1=3/P2=0の否決。root方針に基づく**3件全採用候補、不採用0**。本記録は実反映・承認・人間逐行確認を示さない。採用された場合の反映カウンタは1→2で、初回7件と第2回3件を合算して10件、レビュー回数は2のまま保持する。

| 第2回指摘 | 分類 | 典拠・反例 | 採否案と根拠 |
| --- | --- | --- | --- |
| 1 | P1・起因・(A) | 第2回REPORT 1、sync 7-5-A、requirements FR-010、data-model 6-1-b/6-1-d。未送信投球→交代→終了では交代はCP非生成で旧V7の先行CP参照が閉じない | **全採用案**。queuedは直前D1の実受理prefix終端、confirmed_prefixは確定CP後の実受理終端とし、非CP操作も唯一artifact+保存原本で全件再現する。未供給operation・結果不明・旧CPでのすり替えを拒否。閉union第3variantはrootの技術判断と追加レビューへ明示する |
| 2 | P1・非起因・(A) | 第2回REPORT 2、requirements E-1、ADR-003 D-6/D-8、sync 10-2。FR-007をD-8に載せると旧閉enum/5種と衝突し、載せないと規範行義務を欠く | **全採用案**。ADR-003 0.11 in-reviewを同一ゲートへ追加し、D-6 7 Must/D-8 `game-reopen`・FR-007/常設6種へ限定拡張。既B7・数学cases・他operation/undoを維持。正式schema/case/runnerは実装段で検証し、未供給を合格にしない |
| 3 | P1・起因・(-) | 第2回REPORT 3、sync 2-5 R-TXN-ROUTE/9-2 P2・P3/10-3。CL1が9-2表の外だけにあり各列の責務が空白 | **全採用案**。P2/P3表内の意味規則・保存・強制・故障系を埋め、manifestに表行同居を要求するCL2/CL3を追加。旧P1〜P5/T集合、他10関係を維持 |

起因2件、非起因1件。(A)2件、(B)0件、(-)1件。第1回7件の採否・分類と反例を上書きしない。射程追加は新ADR-003 v0.11（全文とD-6/D-8影響節）と3正本の反映差分/影響節・relation manifest。PO委任の限定追加レビュー1回は**未実施**であり、基本枠2回の数え直しをしない。ハーネス7.3の最終承認を自認しない。反映コミットを行う場合はステップ表記を付けず「反映2周目」を含む件名とする。


### 第2回後のPO委任判断・限定追加1回の裁定（2026-11-06、Codex /root）

対象e7af4801→patch SHA01f8d043ba8a6e278c4d65de45f8d3acac53586cf0262706f21e3ee981a54e5b。第2回P1全3件を採用、不採用0。初回7件/第2回3件、基本枠2回消費済みを維持する。既PO委任の「必要な限定追加レビュー」「合意済み方針の正式整合変更」を根拠に、追加敵対レビューを1回だけ認める。対象は本反映差分と影響節、および今回射程へ追加するADR-003全文（D-6/D-8とFR-007伝播を重点確認）。他3正本は既全文済みで初回扱いへ戻さない。適用7.3 v1.19/条文コミットa7cc3c0baa05fd1a1639e1f98e8f8f7bb39ad229不変。

技術選択はconfirmed_prefixの第3閉variantを採る。同期済み非CP操作も実終端D4/D1/D5と既確定基点を束縛して唯一artifact/保存原本から復元し、古いCPを現在値とみなさない。全ての操作へ新CP保存を要求する変更は採らず、結果不足・未対応操作・結果不明は既順序で閉拒否する。今のprovider/caseの供給完了を意味しない。野球結果/D5再送/拒否先行順の新裁定は行わない。

射程追加理由: ADR D-8の閉enumがFR-007を欠く原典矛盾を同時に直すため、ADR-003 v0.11を同じゲートでin-review化する。既承認v0.10を無審査で書換えた扱いにせず、今回の追加全文審査を受ける。B-7式/丸め/旧数学caseは不変。反映カウンタ1→2。正本の最終承認/本人署名/実装・PG・MVP成立ではない。
