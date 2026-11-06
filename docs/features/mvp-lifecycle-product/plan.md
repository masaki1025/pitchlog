---
feature: mvp-lifecycle-product
status: active
branch: feature/mvp-lifecycle-product-connection
承認: PO委任によるCodex主担当/root判断（2026-11-06、既MVP終了・追記再開の実装接合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 終了・追記再開の製品接続

単一7.3ゲート98344baaで確定した要件2.20・同期0.13・data-model1.6・ADR003 0.11に従う。基本2回＋限定追加2回を維持し、計画で新しい野球意味やD5/拒否順を再裁定しない。既mvp-lifecycle-product-author-20261106 packet 2f464208ef8ed53e78048ea5370e55204b60584b7397b51272882b1bed91fee8（基点89f0189c、40path）と外部FE6 a36c323bを再利用する。現在の取消修復2b1533aeを通常merge済み。rootを本WT唯一writerとし、作者/非作者はcache-onlyへ分離する。外部UI6は別担当の枝で修復中、同pathを並行編集しない。

1. 既packetの40pathとbootstrap差分を現在の実契約へ再基線し、閉V7 confirmed/confirmed_prefix/queued_predecessor と確定/予約target、先行未処理、唯一artifactの制御計算を実装する。単一核を維持し、未対応prefix操作を飛ばして成功させない。共有FE6/mountの編集はせず接合差分で渡す。対象はpacket記載pathと対応する既prefix/bridge/正式schema・V5/eventKind13/C12・入力契約の必要最小追随。
2. 同TX lifecycle admission/head/checkpoint/games.status/終了版/真正stats receipt/pointerを接続する。0043、制約、ACL/owner、関数body/registryはrootが正式資産へ直列反映する。既ownerの便宜的権限拡大、test-only finalize、成功真偽の外部注入をしない。新生成pin/artifact/D11と正式受理はsource固定後に公式helperで派生し独立確認する。
3. 外部UI6の修復候補を非作者確認後に接合し、実記録画面から終了→再開→記録追加→再終了→再取得/reloadを通す。同本文/D5/attempt再送、通信断/再起動、先行要求待ち、二重tab、終了後ロック、越境拒否、途中故障全rollbackをowned実PGで確認する。性能閾値や正常通信時更新保証を緩めない。
4. 真正終了/再開providerを成績のlatest confirmed/current openへ接続し、訂正/再終了の二重計上なしと成績/CSVを確認する。P3は既担当/契約依存を分離し未実装を成功にしない。実機/運用TLS/復旧は準備・証拠と未実施を区別する。

各stepの候補source/根拠/独立レビュー/検査を固定し、step単位commitする。共有認可・tenant・7.7はroot直列、source未固定の中間pushを避ける。main/develop/共有DB/運用秘密は触らない。全4stepの完了やMVP完成を、step1のfixture成功に置き換えない。


step1の入力codec部分を採用（2026-11-06、PO委任Codex /root判断）: packet reflection2の新2path、非作者REPORT SHA256 18b098878e303f43eaa94f731d8aaa965065ce22757341325f384cb88f346b2eで旧P1全2解消・後発P1なし。57unit/Ruff/Ty成功。D1は既WireD1整数、D2は既ordering上限を単一参照し、D4参照は既Generation純shape。旧flatや欠落/NaN/上限外を補修せず内容拒否する。型検査を権限・真正CP・先行実結果の成立と混同しない。残step1は予約/先行prefixのサーバー解決・唯一artifact・bridge/正式contract・接合、step2同TXprovider以降は未完。本人署名/P6blindでない。


2026-11-06 2時間試行のstep3候補接合（PO委任Codex/root判断）: POが統合候補まで実装後にまとめてレビュー・検査する方式を18:37:31から採用。外部FE6修復48d61a8b（対象50件、版0拒否・耐久版根拠不足の非成功を含む）を未正式受理の接合候補として本WTへ移す。既step3の非作者確認は候補固定後へ移し、正式統合前に必須とする。追加所有はGameScreenLifecycleProduct.vueと専用spec、GameScreenRecordedRestore.vueのmountのみ。実HTTPS/4利用者環境確認/認証epoch/実WebLocks/耐久storeを供給し、常時trueのwriterや固定成功を使わない。元48d61枝・既レビュー連鎖を保持。NP ad7f3c8bを70f800a1へ通常mergeし取消後の接合を共通化、全MVP成立の主張ではない。


2026-11-06 19:45 JSTの統合候補接合（PO委任Codex/root判断）: 2時間試行の一試合到達へ、root専有本WTに操作担当のfeature/mvp-game-operations-product@2bdf48ecを通常mergeする。担当plan（4900ef9c）と各操作の閉条件/限定実画面証拠を維持し、root本計画の終了再開を操作担当の成果と取り違えない。別枝を消さず、共有sourceの衝突だけrootが直列解決する。formal overlayは固定packet到着後に照合し、単一artifactは終了再開/交代との合成sourceから公式builderで再生成する。未完の正式資産・独立最終レビュー・全CIを通過済みとしない。


2時間試行の終了再開R2同版接合（2026-11-06、PO委任Codex/root判断）: cache基線ec23＋R1固定packetからR2全163pathを照合し、154をactualへ接合。source3競合は旧省略保持の同義format・JSONB括弧・有限互換validatorの型狭化として解決。衝突したartifact2・witness/manifest/数学case5・旧profile test1・公式prepare body1の計9はroot既修復を保持して合成sourceから再生成する。root P0修復/物理走者P1/同期C2/取消D5先行再掲を失わない。cache実HTTP v3 end→reopen→追加play→reendはrun25 clean 1passed131秒だが、actual合成版/画面/全CI/正式7.7はまだ未成立。R2 Ty/Ruff成功、独立最終確認は同版固定後。0042→0043既設resume、v1/v2/nonCP/P3は未達として維持する。


step3の実画面E2E追加（2026-11-06、PO委任Codex/root判断）: GameScreenLifecycleProduct.e2e.ts/専用Playwright config/backend実DB wrapperを追加。UIで新規作成→開始→1球→終了v1→再開→既NP画面から2球→再終了v2→reloadを同じ候補で実測し、DBの6accepted原本と真正confirmed_ended/source_count3を別literalで照合する。既外部E2Eの未接続driverを成功stubで置換せず、実画面のボタン/唯一核/実APIを使用。まだ実行前で、準備完了を実証成功にしない。


単一artifact再束縛（2026-11-06、PO委任Codex/root判断）: root合成source9805045fをcache作者が公式builderで生成し、唯一artifact9ae9d16db1f2fa48905eb0ac951c8cb3ce5704dfe308df95a7a0bba155f33d19へ接合。patch55abded5a39fea258876884ea99d5b3c66efa7d10b89d00dc635d8b3be8c695dの22pathを全before/after SHA照合し採用候補とする。旧数学D11 134＋prefix19、旧Git4e8の53witnessを新hostと全値比較し、数学期待を採取し直していない。7manifest/識別値/lineup digest/有限v2witnessを公式派生、authz547body全byte一致・checker/限定33成功は作者証拠。正式7.7/最終非作者確認/全CI/同版実画面は未了、旧NP CPと未掲載候補artifactの互換は自動拡張しない。


合成実画面r1: 同版94baでUI新規作成→開始→1球保存は通過、終了POST404で停止。同期C2登録へLC transportのPOSTだけtenantBoundが追随せず期待tenant/challengeを送っていないと特定。GET/通常球/取消と同じtenantBound:trueをLC POSTへ加え、原body/attempt不変を既API spec完全一致期待でも固定する。API-only候補成功を画面完走へ広げない。


### ステップ4・正式統合前の基線接合（2026-11-07、PO委任Codex主担当/root判断）

既実画面結合候補60f39f1042e18d2bfe3bf882dd24dc3caccda0aeを不変更で保全し、root専有の新WT/枝feature/mvp-nonplay-formal-connectionで、PR197最終候補d8e8b34d8a5f12665530226ec0f539804c06791cのCI修復を通常mergeする。PR197はまだ公開CI中であり、ここで正式developの統合済みとは記録しない。公開197のbranch/HEADは変更しない。

既step4の正式資産/独立確認/CI/通常統合準備の具体化に限り、repo/runtime候補原本・生成module、DB fixtureとnative登録試験の6競合をrootが直列解決する。既製品の認可・記録権・原子性・単一核と旧拒否対向を保持する。生成物は片側の完全byte選択または公式rendererから再導出し、手で生成moduleの値を作らない。旧候補payloadに残る未受理履歴を正式197受理へ読み替えず、次段の対象source固定と正式base確定後、公式helperで必要差分の完全前後値を導出し別非作者確認・委任受理を行う。

この段階では申告敬遠/CSV/P3/復旧の後発実装を一括移植しない。各専用枝/証拠/編集所有を保持し、現在候補の開始・通常入力・取消・交代・終了再開の供給を197修復で失わないことを局所検査する。rootの統合準備をMVP完成や正式提供としない。
